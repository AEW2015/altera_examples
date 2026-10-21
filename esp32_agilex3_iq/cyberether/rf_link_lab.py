#!/usr/bin/env python3
"""RF Link Lab: display saved measurements and explicitly request bounded acquisitions."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

class CaptureManager:
    def __init__(self, snapshot, root=ROOT):
        self.snapshot = Path(snapshot).resolve()
        self.root = Path(root)
        self.guard = threading.Lock()
        self.job = {'busy': False, 'status': 'idle'}
        self.child = None
        self.closed = False

    def state(self):
        with self.guard:
            job = dict(self.job)
        try:
            snapshot = json.loads(self.snapshot.read_text())
            if not isinstance(snapshot, dict):
                raise ValueError('Snapshot is not an object')
            error = None
        except FileNotFoundError:
            snapshot, error = {}, 'Waiting for the first capture'
        except (OSError, ValueError) as exc:
            snapshot, error = {}, str(exc)
        # These are explicitly separate historical FPGA measurements, with
        # source hashes. A fresh host capture must not silently discard them.
        if snapshot.get('provenance', {}).get('kind') == 'physical_rf':
            try:
                evidence = json.loads((self.root / 'cyberether/run/rf-link-fpga-evidence.json').read_text())
                for key in ('fpga_result', 'fpga_fir_result'):
                    if key in evidence:
                        snapshot.setdefault(key, evidence[key])
            except (OSError, ValueError, TypeError):
                pass
        try:
            qualification = json.loads((self.root / 'cyberether/run/ber-qualification/qualification.json').read_text())
        except (OSError, ValueError):
            qualification = None
        return {'snapshot': snapshot, 'job': job, 'snapshot_error': error,
                'qualification': qualification}

    def qualify(self, data):
        """Bounded offline experiment. Never changes the live RF snapshot."""
        if data != {}:
            raise ValueError('BER qualification uses the documented fixed settings')
        with self.guard:
            if self.closed or self.job['busy']:
                raise RuntimeError('Another experiment is running or the server is stopping')
            run = self.root / 'cyberether/run'
            run.mkdir(parents=True, exist_ok=True)
            owner = (run / 'rf-link-capture.lock').open('a')
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                owner.close()
                raise RuntimeError('Another experiment owns acquisition')
            out = run / 'ber-qualification'
            command = [sys.executable, str(self.root / 'scripts/check_rf_ber.py'),
                       '--output', str(out), '--frames', '1000', '--payload-bytes', '16']
            # Explicit lab runtime root, recursively: extended batches are nested.
            # Offline aggregation rejects other proof kinds and deduplicates CI8 SHA.
            command += ['--proof-dir', str(run)]
            self.job = dict(busy=True, status='running', started_at=time.time(),
                            output=str(out), requested={'experiment': 'AWGN BER simulation + saved RF audit',
                                                        'frames_per_point': 1000, 'hardware': False})
            threading.Thread(target=self._run, args=(command, out, owner), daemon=True).start()
            return dict(self.job)

    def capture(self, data, synthetic=False):
        allowed = {'payload', 'symbol_us', 'pulse_cycles', 'captures', 'modulation'} | ({'coded_flips'} if synthetic else set())
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Unknown capture option')
        captures = data.get('captures', 4)
        modulation = data.get('modulation', 'BPSK')
        if modulation not in ('BPSK', 'QPSK'):
            raise ValueError('modulation must be BPSK or QPSK')
        if type(captures) is not int or captures not in (4, 64):
            raise ValueError('captures must be 4 or 64')
        payload = data.get('payload', 165)
        symbol = data.get('symbol_us', 8)
        pulse = data.get('pulse_cycles')
        for name, value, lo, hi in [('payload', payload, 0, 255), ('symbol_us', symbol, 8, 15)]:
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f'{name} must be an integer in {lo}..{hi}')
        if pulse is not None and (type(pulse) is not int or not 1 <= pulse <= 8192):
            raise ValueError('pulse_cycles must be an integer in 1..8192')
        flips = data.get('coded_flips', 0)
        if synthetic and (type(flips) is not int or flips not in (0, 2)):
            raise ValueError('coded_flips must be 0 or 2')
        if modulation == 'QPSK' and flips:
            raise ValueError('FEC challenge is the BPSK reference; select Clean reference for QPSK')
        if not synthetic:
            try:
                active = json.loads((self.root / 'cyberether/run/active-fpga.json').read_text())
            except (OSError, ValueError):
                active = {}
            if not isinstance(active, dict) or active.get('iq_bridge') is not True:
                raise RuntimeError('Restore runtime FPGA hub first')
        with self.guard:
            if self.closed or self.job['busy']:
                raise RuntimeError('An acquisition is already running or the server is stopping')
            self.snapshot.parent.mkdir(parents=True, exist_ok=True)
            lock = (self.root / 'cyberether/run/rf-link-capture.lock')
            lock.parent.mkdir(parents=True, exist_ok=True)
            owner = lock.open('a')
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                owner.close()
                raise RuntimeError('Another RF Link Lab owns acquisition')
            out = self.root / 'cyberether/run' / ('rf-link-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns()))
            script = 'check_rf_qpsk.py' if modulation == 'QPSK' else 'check_rf_bpsk.py'
            command = [sys.executable, str(self.root / 'scripts' / script), '--output', str(out), '--snapshot', str(self.snapshot), '--captures', str(captures), '--payload', str(payload), '--symbol-us', str(symbol)]
            if synthetic:
                command += ['--synthetic', '--synthetic-coded-flips', str(flips)]
            if pulse is not None:
                command += ['--pulse-cycles', str(pulse)]
            self.job = dict(busy=True, status='running', started_at=time.time(), output=str(out), requested=dict(modulation=modulation, captures=captures, payload=payload, symbol_us=symbol, pulse_cycles=pulse, synthetic=synthetic, coded_flips=flips if synthetic else None))
            threading.Thread(target=self._run, args=(command, out, owner), daemon=True).start()
            return dict(self.job)

    def _run(self, command, out, owner):
        log = out.with_suffix('.log')
        error = None
        code = None
        try:
            with log.open('w') as stream:
                with self.guard:
                    if self.closed:
                        raise RuntimeError('Server stopping')
                    self.child = subprocess.Popen(command, cwd=self.root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                    child = self.child
                try:
                    code = child.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    raise RuntimeError('Capture exceeded its 180 second limit')
                if code:
                    error = f'Capture failed (exit {code}); inspect {log}'
        except Exception as exc:
            error = str(exc)
        finally:
            owner.close()
            with self.guard:
                self.child = None
                self.job.update(busy=False, status='error' if error else 'complete', error=error, exit_code=code, log=str(log), finished_at=time.time())

    def close(self):
        with self.guard:
            self.closed = True
            child = self.child
        if child and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            except ProcessLookupError:
                pass

def handler_for(manager):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, data, mime='application/json'):
            body = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                self.reply(200, Path(__file__).with_suffix('.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/state':
                self.reply(200, manager.state())
            elif path == '/health':
                self.reply(200, {'status': 'ready'})
            else:
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in ('/api/capture', '/api/synthetic', '/api/qualify'):
                self.reply(404, {'error': 'Not found'}); return
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                self.reply(403, {'error': 'Cross-origin capture rejected'}); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'Use application/json'}); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    raise ValueError('Invalid request length')
                data = json.loads(self.rfile.read(length))
                job = manager.qualify(data) if path == '/api/qualify' else manager.capture(data, synthetic=path == '/api/synthetic')
                self.reply(202, job)
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except RuntimeError as exc:
                self.reply(409, {'error': str(exc)})
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'cyberether/run/rf-link-state.json')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8770)
    args = parser.parse_args()
    manager = CaptureManager(args.input)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(manager))
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    print(f'RF Link Lab listening on {args.host}:{args.port}; RF only starts with Capture RF', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        server.server_close()
if __name__ == '__main__':
    main()
