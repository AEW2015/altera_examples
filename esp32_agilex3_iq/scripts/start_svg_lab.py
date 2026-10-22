#!/usr/bin/env python3
"""Serve the local SVG edge/FEC viewer; simulation is an explicit CLI action."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'cyberether' / 'svg_constellation.html'
GRAPH = ROOT / 'examples' / 'svg_constellations' / 'pentagram_circle.graph.json'
TIME_VIEW = ROOT / 'examples' / 'svg_constellations' / 'constellation_time.html'
RESULT = ROOT / 'cyberether' / 'run' / 'svg-constellation-result.json'


def _run_reference(args: argparse.Namespace) -> None:
    """Run the pure host reference only when the operator explicitly asks."""
    candidates = (ROOT / 'scripts' / 'svg_modem.py',)
    reference = next((path for path in candidates if path.is_file()), None)
    if reference is None:
        raise SystemExit('SVG reference is not available yet; no result was generated.')
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(reference), '--output', str(RESULT),
               '--bits', str(args.bits), '--snr-db', str(args.snr_db),
               '--seed', str(args.seed), '--mode', args.mode, '--sps', str(args.sps)]
    subprocess.run(command, cwd=ROOT, check=True)
    print(f'Wrote host simulation result: {RESULT}')
    print('Python simulation only; no serial port or hardware was accessed.')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/':
            return self._file(PAGE, 'text/html; charset=utf-8')
        if path == '/time':
            return self._file(TIME_VIEW, 'text/html; charset=utf-8')
        if path == '/api/graph':
            return self._file(GRAPH, 'application/json; charset=utf-8')
        if path == '/api/result':
            if not RESULT.is_file():
                return self._json({'available': False, 'message': 'No result yet. Use the explicit Python simulation CLI action.'}, 200)
            return self._file(RESULT, 'application/json; charset=utf-8', no_cache=True)
        if path == '/health':
            return self._json({'status': 'ready', 'result_available': RESULT.is_file()})
        return self._json({'error': 'Not found'}, 404)

    def _file(self, path: Path, content_type: str, no_cache: bool = False):
        try:
            body = path.read_bytes()
        except OSError:
            return self._json({'error': 'Not found'}, 404)
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        if no_cache:
            self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f'[svg-lab] {self.address_string()} {fmt % args}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('serve', 'simulate'), nargs='?', default='serve')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8775)
    p.add_argument('--bits', type=int, default=256)
    p.add_argument('--snr-db', type=float, default=8.0)
    p.add_argument('--seed', type=int, default=20261022)
    p.add_argument('--mode', choices=('arc', 'linear', 'hold'), default='arc')
    p.add_argument('--sps', type=int, default=16)
    args = p.parse_args()
    if args.action == 'simulate':
        _run_reference(args)
        return
    if not PAGE.is_file() or not GRAPH.is_file():
        p.error('viewer page or graph fixture is missing')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving SVG constellation lab at http://{args.host}:{args.port}/')
    print('Read-only local result viewer. No hardware, serial, FPGA or RF access.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
