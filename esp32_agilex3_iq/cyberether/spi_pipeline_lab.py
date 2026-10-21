#!/usr/bin/env python3
"""Explicit bounded SPI experiments; idle pages never own UART or JTAG."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from rf_link_lab import CaptureManager, handler_for

ROOT = Path(__file__).resolve().parents[1]


def meter_snapshot(directory):
    """Display math only. Measurement values come from the verified FPGA proof."""
    from spi_fir_qualification import display_plots
    directory = Path(directory)
    proof = json.loads((directory / 'proof.json').read_text())
    raw = (directory / 'capture.ci8').read_bytes()
    from spi_meter import integer_reference
    import hashlib
    meter = proof['fpga_meter']
    if hashlib.sha256(raw).hexdigest() != proof['sha256']:
        raise ValueError('Saved capture hash differs from proof')
    if not proof['crc_all_pass'] or not meter['valid'] or not meter['reference_match'] or any(meter[k] != v for k, v in integer_reference(raw).items()):
        raise ValueError('Saved FPGA meter differs from raw integer reference')
    return dict(schema='spi-pipeline-v1', status='verified', updated_at=time.time(),
        kind=proof['kind'], requested=dict(mode=proof['requested_mode'], profile='meter'),
        readback=dict(image_identity=proof['fpga_identity'], source=proof['source'],
                      sequence=proof['sequence'], mode=proof['readback_mode']),
        verification=dict(bit_exact=proof.get('payload_exact'), meter_exact=True,
                          raw_crc=proof['crc_all_pass'], clips=meter['clip_samples']),
        meter=meter, timing=dict(ingress_s=meter['ingress_s'], end_to_end_s=proof['elapsed_s'],
                                ingress_payload_bytes_s=meter['ingress_payload_bytes_s'],
                                end_to_end_bytes_s=proof['end_to_end_bytes_s']),
        provenance=dict(raw_sha256=proof['sha256'], origin=proof['kind'], raw_uploaded=False,
            host_processing='Transport, independent integer verification, display FFT',
            fpga_processing='SPI CRC/order validation; integer power, peak and clipping'),
        plots=display_plots(raw), output=str(directory))


_STOP_LOCK = threading.Lock()

def stop_experiment(child):
    # close() and the experiment timeout can race; interrupt only once.
    with _STOP_LOCK:
        _stop_experiment(child)

def _stop_experiment(child):
    """Interrupt the checker first so its JTAG/baud restoration can finish."""
    if child.poll() is not None:
        return
    try:
        child.send_signal(signal.SIGINT)
        child.wait(timeout=30)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        # A stuck checker cannot promise restoration. Kill its remaining group;
        # its incomplete proof must never be presented as a verified capture.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


class SPIManager(CaptureManager):
    def __init__(self, snapshot, root=ROOT, port=None):
        super().__init__(snapshot, root)
        self.port = port

    def state(self):
        with self.guard:
            job = dict(self.job)
        try:
            snapshot = json.loads(self.snapshot.read_text())
        except (OSError, ValueError):
            snapshot = {}
        try:
            active = json.loads((self.root / 'cyberether/run/active-fpga.json').read_text())
        except (OSError, ValueError):
            active = {}
        # A manifest is a programming hint; every checker still probes hardware.
        checkpoint = active.get('checkpoint')
        return dict(snapshot=snapshot, job=job, recorded_checkpoint=checkpoint,
                    spi_capture_paused=checkpoint != 7)

    def capture(self, data, synthetic=False):
        if not isinstance(data, dict) or set(data) - {'pipeline', 'profile', 'host_baud', 'captures'}:
            raise ValueError('Unknown SPI experiment option')
        pipeline = data.get('pipeline', 'meter')
        profile = str(data.get('profile', 2))
        baud = data.get('host_baud', 2000000)
        captures = data.get('captures', 1)
        if pipeline not in ('meter', 'fir') or profile not in ('1', '2'):
            raise ValueError('Invalid pipeline or filter profile')
        if type(baud) is not int or baud not in (2000000, 4000000) or (pipeline == 'meter' and baud != 2000000):
            raise ValueError('Host UART must be 2 Mbaud, or 4 Mbaud for the FIR checkpoint')
        if type(captures) is not int or captures not in (1, 12) or (captures == 12 and pipeline != 'fir'):
            raise ValueError('Use one capture, or a 12-capture FIR experiment')
        with self.guard:
            if self.closed or self.job['busy']:
                raise RuntimeError('An experiment is already running or the page is stopping')
            run = self.root / 'cyberether/run'
            run.mkdir(parents=True, exist_ok=True)
            out = run / ('spi-gui-' + str(time.time_ns()))
            script = 'check_spi_meter.py' if pipeline == 'meter' else ('soak_spi_fir.py' if captures == 12 else 'check_spi_fir.py')
            command = [sys.executable, str(self.root / 'scripts' / script),
                       '--confirm-spi-image', '--output', str(out)]
            if pipeline == 'fir':
                if not (self.root / 'scripts' / script).exists():
                    raise RuntimeError('The integrated SPI FIR checker is not installed yet')
                command += ['--profile', profile, '--host-baud', str(baud), '--snapshot', str(self.snapshot)]
                if captures == 12:
                    command += ['--captures', '12', '--fast-readback']
            if self.port:
                command += ['--port', self.port]
            if not synthetic and captures == 1:
                command += ['--rf']
            self.job = dict(busy=True, status='running', started_at=time.time(),
                            requested=dict(mode='alternating synthetic / RF' if captures == 12 else ('synthetic' if synthetic else 'rf'),
                                           pipeline=pipeline, profile=profile, host_baud=baud, captures=captures), output=str(out))
            # Each checker takes the shared acquisition lock itself.
            threading.Thread(target=self._experiment, args=(command, out, pipeline), daemon=True).start()
            return dict(self.job)

    def qualify(self, data):
        raise ValueError('Use a bounded SPI capture')

    def _experiment(self, command, out, pipeline):
        error = None
        log = out.with_suffix('.log')
        try:
            with log.open('w') as stream:
                with self.guard:
                    if self.closed:
                        raise RuntimeError('Server stopping')
                    self.child = subprocess.Popen(command, cwd=self.root, stdout=stream,
                        stderr=subprocess.STDOUT, start_new_session=True)
                    child = self.child
                child.wait(timeout=180)
                if child.returncode:
                    raise RuntimeError(f'Experiment failed; inspect {log}')
            if pipeline == 'meter':
                snapshot = meter_snapshot(out)
                temporary = self.snapshot.with_suffix('.tmp')
                temporary.write_text(json.dumps(snapshot, allow_nan=False))
                temporary.replace(self.snapshot)
        except subprocess.TimeoutExpired:
            stop_experiment(child)
            error = 'Experiment exceeded its 180 second limit; inspect proof for restoration status'
        except Exception as exc:
            error = str(exc)
        finally:
            with self.guard:
                self.child = None
                self.job.update(busy=False, status='error' if error else 'complete',
                                error=error, log=str(log), finished_at=time.time())

    def close(self):
        with self.guard:
            self.closed = True
            child = self.child
        if child is not None:
            stop_experiment(child)


def main():
    from http.server import ThreadingHTTPServer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8771)
    parser.add_argument('--uart')
    parser.add_argument('--input', type=Path, default=ROOT / 'cyberether/run/spi-pipeline-state.json')
    args = parser.parse_args()
    manager = SPIManager(args.input, port=args.uart)
    base = handler_for(manager)
    class Handler(base):
        def do_GET(self):
            if self.path.split('?')[0] == '/':
                self.reply(200, Path(__file__).with_suffix('.html').read_bytes(), 'text/html; charset=utf-8')
            else:
                super().do_GET()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        server.server_close()


if __name__ == '__main__':
    main()
