#!/usr/bin/env python3
"""Manage this checkout's RF Link Lab; starting the page never starts RF."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from common import ROOT
from lessons import lan_ip

RUN = ROOT / 'cyberether/run'
META = RUN / 'rf-link-lab-service.json'

def owned(meta):
    try:
        args = Path('/proc', str(meta['pid']), 'cmdline').read_bytes().split(b'\0')
        return str(ROOT / 'cyberether/rf_link_lab.py').encode() in args
    except (OSError, KeyError, ValueError):
        return False

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['start', 'stop', 'status'], default='start', nargs='?')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8770)
    p.add_argument('--input', type=Path, default=RUN / 'rf-link-state.json')
    a = p.parse_args()
    RUN.mkdir(exist_ok=True)
    try:
        meta = json.loads(META.read_text())
    except (OSError, ValueError):
        meta = {}
    live = owned(meta)
    if a.action == 'status':
        print(json.dumps(dict(meta, running=live), indent=2)); return
    if a.action == 'stop':
        if live:
            os.kill(meta['pid'], signal.SIGTERM)
            for _ in range(120):
                if not owned(meta):
                    break
                time.sleep(.1)
            if owned(meta):
                raise RuntimeError('Service still stopping; no unrelated process was terminated')
        META.unlink(missing_ok=True)
        print('RF Link Lab stopped'); return
    if live:
        print('Already running:', meta['url']); return
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind((a.host, a.port))
    command = [sys.executable, str(ROOT / 'cyberether/rf_link_lab.py'), '--host', a.host, '--port', str(a.port), '--input', str(a.input.resolve())]
    with (RUN / 'rf-link-lab-service.log').open('a') as log:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('Server exited; inspect cyberether/run/rf-link-lab-service.log')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health', timeout=1) as response:
                    if json.load(response).get('status') == 'ready':
                        break
            except (OSError, ValueError):
                time.sleep(.1)
        else:
            raise TimeoutError('RF Link Lab did not become ready')
    except BaseException:
        proc.terminate(); proc.wait(timeout=8); raise
    hostname = lan_ip() if a.host == '0.0.0.0' else a.host
    meta = dict(pid=proc.pid, url=f'http://{hostname}:{a.port}/', port=a.port, input=str(a.input.resolve()), started_unix=time.time())
    META.write_text(json.dumps(meta, indent=2) + '\n')
    print(meta['url'])
    print('RF starts only with Capture RF; page owns no serial or JTAG device')

if __name__ == '__main__':
    main()
