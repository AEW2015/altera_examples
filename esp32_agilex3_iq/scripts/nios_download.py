#!/usr/bin/env python3
"""Load a software ELF into the matching active Nios V checkpoint over JTAG."""
import argparse
import json
import os
import re
import subprocess

from common import ROOT, stages, local_tools
from lessons import stop_demo
from nios_software import software_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=int, choices=range(2, 6))
    parser.add_argument('app', choices=['hello_world', 'iq_monitor', 'boot_monitor'])
    parser.add_argument('--ide-build', action='store_true', help='Use RiscFree build/Default ELF instead of CLI build ELF')
    parser.add_argument('--device', type=int, default=0, help='Downloader device index (zero-based in Quartus 26.1.1)')
    parser.add_argument('--instance', type=int, default=0)
    args = parser.parse_args()
    if not local_tools():
        parser.error('Run beside the installed tools (ATUM_TOOLS_MODE=local).')
    stage = stages()[args.checkpoint - 1]
    state = ROOT / 'cyberether/run/active-fpga.json'
    if not state.exists() or json.loads(state.read_text()).get('stage_relative') != str(stage.relative_to(ROOT)):
        parser.error(f'Load the matching FPGA checkpoint first: python scripts/run.py load --checkpoint {args.checkpoint}')
    if args.app == 'boot_monitor':
        elf = stage / 'sw/monitor.elf'
    else:
        build = 'build/Default' if args.ide_build else 'build'
        elf = ROOT / 'software' / f'checkpoint_{args.checkpoint:02d}' / args.app / build / (args.app + '.elf')
    if not elf.exists():
        parser.error(f'Build this application first: {elf}')
    env = software_env()
    cable = os.getenv('ATUM_JTAG_CABLE', 'Atum A3 Nano [1-4.3-iface0]')
    listing = subprocess.check_output(['jtagconfig'], env=env, text=True)
    targets = [(m[1], m[2]) for m in re.finditer(r'^(\d+)\) (.+)$', listing, re.M)]
    matches = [index for index, name in targets if name == cable or index == cable]
    if len(matches) != 1:
        parser.error('Set ATUM_JTAG_CABLE to the exact name or number reported by jtagconfig.')
    stop_demo()
    command = ['niosv-download', '-c', matches[0], '-d', str(args.device), '-i', str(args.instance), '-r', '-g', str(elf)]
    print('Loading software only:', elf, flush=True)
    subprocess.run(command, env=env, check=True)
    print('Use juart-terminal to view output. The notebook-owned viewer is stopped; restart it after restoring the monitor.')


if __name__ == '__main__':
    main()
