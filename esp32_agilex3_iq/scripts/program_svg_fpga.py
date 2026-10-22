#!/usr/bin/env python3
"""Explicitly program the standalone internal SVG modem. Never commands RF TX."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from common import ROOT, tool_exe, tool_env
from program_wifi64 import owners, resolve_cable, write_json

STAGE = ROOT / 'fpga_hub/iq_bridge/svg_modem'
BUILD = STAGE / 'run/build'
RUN = ROOT / 'cyberether/run'


def checked_image():
    manifest = json.loads((BUILD / 'BUILD_RESULT.json').read_text())
    image = BUILD / manifest.get('image_file', 'output_files/svg_demo.sof')
    if manifest.get('status') != 'PASS_BUILD' or manifest.get('device') != 'A3CZ135BB18AE7S':
        raise RuntimeError('A successful matching A3 Nano build is required')
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest.get('image_sha256'):
        raise RuntimeError('SVG SOF hash mismatch')
    files = manifest.get('source_hashes')
    if not isinstance(files, dict) or not files:
        raise RuntimeError('Build manifest lacks source hashes; rebuild before programming')
    for name, expected in files.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Build source changed: ' + name)
    proof = json.loads((STAGE / 'results/simulation/validation.json').read_text())
    if proof.get('passed') is not True or proof.get('actual_rtl') is not True:
        raise RuntimeError('Run scripts/simulate_svg_modem.py before programming')
    for name, expected in proof.get('source_sha256', {}).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('RTL changed since passing simulation: ' + name)
    if manifest.get('minimum_slack_ns', -1) < 0:
        raise RuntimeError('Passing timing analysis is required before programming')
    return image, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cable', default=os.getenv('ATUM_JTAG_CABLE', 'Atum A3 Nano [1-4.3-iface0]'))
    args = parser.parse_args()
    image, meta = checked_image()
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / 'rf-link-capture.lock').open('a') as rf, (RUN / 'nios-fir.lock').open('a') as jtag:
        fcntl.flock(rf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(jtag, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = owners()
        if held:
            raise RuntimeError('Release devices before programming: ' + ', '.join(held))
        environment = tool_env()
        cable = resolve_cable(args.cable, environment)
        active = RUN / 'active-fpga.json'
        record = dict(action='program-svg', started_unix=time.time(), complete=False,
                      image_sha256=meta['image_sha256'], cable=args.cable, tx_started=False,
                      prior_active=json.loads(active.read_text()) if active.exists() else None)
        stamp = str(time.time_ns())
        record_path = RUN / ('svg-program-' + stamp + '.json')
        log = RUN / ('svg-program-' + stamp + '.log')
        record['log'] = str(log)
        write_json(record_path, record)
        checked_image()
        active.unlink(missing_ok=True)
        (RUN / 'wifi64-capture-app-active.json').unlink(missing_ok=True)
        try:
            with log.open('w') as output:
                subprocess.run([str(tool_exe('quartus_pgm')), '-c', cable, '-m', 'JTAG',
                                '-o', 'p;' + str(image) + '@1'],
                               env=environment, stdout=output, stderr=subprocess.STDOUT,
                               check=True, timeout=180)
            record.update(complete=True, finished_unix=time.time())
            write_json(active, dict(stage_relative=str(STAGE.relative_to(ROOT)),
                                    sha256=meta['image_sha256'], source_fingerprint=meta['source_fingerprint'],
                                    programmed_unix=time.time(), hardware_verified=False,
                                    rf_transmitted=False, role='internal SVG graph modem'))
        except Exception as exc:
            record.update(error=str(exc), finished_unix=time.time())
            raise
        finally:
            write_json(record_path, record)
        print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
