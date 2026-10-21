#!/usr/bin/env python3
"""Generate official Nios V HAL BSP/apps; optionally open Ashling RiscFree IDE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from common import ROOT, altera_root, local_tools, stages, tool_env


def software_env():
    env = tool_env()
    root = altera_root()
    compiler = Path(os.getenv('ATUM_RISCV_GCC', str(root / 'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc')))
    env['PATH'] = os.pathsep.join([str(root / 'niosv/bin'), str(compiler.parent), env['PATH']])
    return env


def software_stage(checkpoint):
    if checkpoint == 6:
        return ROOT / 'fpga_hub/iq_bridge/vds_demo_06_modem'
    if checkpoint not in range(2, 6):
        raise ValueError('Nios checkpoint 2–6 required')
    return stages()[checkpoint - 1]


def generate(checkpoint, build=True, refresh_sources=False):
    stage = software_stage(checkpoint)
    system = stage / 'src/vds/iq_bridge_system/iq_bridge_system.vds'
    if not system.exists():
        raise RuntimeError('Generate checkpoint 06 first: python scripts/modem_fpga.py generate' if checkpoint == 6 else f'Generate checkpoint {checkpoint} first: python scripts/build.py {checkpoint} --generate-only')
    out = ROOT / 'software' / f'checkpoint_{checkpoint:02d}'
    bsp = out / 'bsp'
    bsp.mkdir(parents=True, exist_ok=True)
    env = software_env()

    def run(args, log):
        print('Running:', ' '.join(map(str, args)), flush=True)
        with (out / log).open('w') as stream:
            result = subprocess.run(list(map(str, args)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'Command failed; see {out / log}')

    # Preserve BSP edits; require polled JTAG so the HAL ISR cannot steal the
    # monitor's command bytes (fir_control.h owns that FIFO directly).
    settings = bsp / 'settings.bsp'
    options = ['--update'] if settings.exists() else [
        '--create', '--quartus-project=' + str(stage / 'iq_bridge_vds.qpf'),
        '--system=' + str(system), '--cpu-instance=cpu', '--type=hal']
    run(['niosv-bsp', *options, '--cmd=set_setting altera_avalon_jtag_uart_driver.enable_small_driver true',
         settings], 'bsp-generation.log')
    applications = {
        'hello_world': ROOT / 'software/hello_world/main.c',
        'iq_monitor': stage / 'sw/main.c',
    }
    result = dict(checkpoint=checkpoint, system=str(system.relative_to(ROOT)),
                  system_sha256=hashlib.sha256(system.read_bytes()).hexdigest(),
                  bsp=str(bsp.relative_to(ROOT)), applications={}, built_unix=time.time())
    for name, source in applications.items():
        app = out / name
        app.mkdir(exist_ok=True)
        local_source = app / 'main.c'
        # Keep editable sources inside each IDE project; preserve the user's edits.
        if refresh_sources or not local_source.exists():
            shutil.copy2(source, local_source)
        for header in source.parent.glob('*.h'):
            if refresh_sources or not (app / header.name).exists():
                shutil.copy2(header, app / header.name)
        run(['niosv-app', '--app-dir=' + str(app), '--bsp-dir=' + str(bsp),
             '--srcs=' + str(local_source), '--elf-name=' + name + '.elf'], name + '-generate.log')
        launch = ET.Element('launchConfiguration', type='org.eclipse.ui.externaltools.ProgramLaunchConfigurationType')
        for key, value in {
            'org.eclipse.ui.externaltools.ATTR_LOCATION': sys.executable,
            'org.eclipse.ui.externaltools.ATTR_WORKING_DIRECTORY': str(ROOT),
            'org.eclipse.ui.externaltools.ATTR_TOOL_ARGUMENTS': f'"{ROOT / "scripts/nios_download.py"}" {checkpoint} {name} --ide-build',
        }.items():
            ET.SubElement(launch, 'stringAttribute', key=key, value=value)
        ET.SubElement(launch, 'booleanAttribute', key='org.eclipse.ui.externaltools.ATTR_BUILDER_ENABLED', value='false')
        ET.ElementTree(launch).write(app / f'Run checkpoint {checkpoint} {name}.launch', encoding='UTF-8', xml_declaration=True)
        if build:
            run(['cmake', '-S', app, '-B', app / 'build', '-G', 'Unix Makefiles',
                 '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], name + '-configure.log')
            run(['cmake', '--build', app / 'build', '--parallel', '4'], name + '-build.log')
            elf = app / 'build' / (name + '.elf')
            result['applications'][name] = dict(elf=str(elf.relative_to(ROOT)), sha256=hashlib.sha256(elf.read_bytes()).hexdigest())
    (out / 'BUILD_RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Checkpoint {checkpoint}: BSP + Hello World + IQ monitor ready in {out}', flush=True)
    return out


def open_ide():
    ide = Path(os.getenv('ATUM_RISCFREE', str(altera_root() / 'riscfree/RiscFree/RiscFree')))
    if not ide.is_file():
        raise RuntimeError('Set ATUM_RISCFREE to the installed RiscFree executable.')
    workspace = ROOT / 'software/workspace'
    log = ROOT / 'software/riscfree.log'
    with log.open('a') as stream:
        subprocess.Popen([str(ide), '-data', str(workspace)], cwd=ROOT, env=software_env(),
                         stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    print('RiscFree workspace:', workspace)
    print('File > Import Nios V CMake Project: import the bsp and application directories separately.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', choices=['2', '3', '4', '5', '6', 'all'])
    parser.add_argument('--generate-only', action='store_true', help='Generate the BSP and app CMake files without compiling')
    parser.add_argument('--open', action='store_true', help='Open the official RiscFree IDE on the current desktop')
    parser.add_argument('--refresh-sources', action='store_true', help='Replace editable app main.c copies with the repository examples')
    args = parser.parse_args()
    if not local_tools():
        parser.error('Run beside Quartus/Nios tools (ATUM_TOOLS_MODE=local).')
    env = software_env()
    for tool in ('niosv-bsp', 'niosv-app', 'cmake', 'make', 'riscv32-unknown-elf-gcc'):
        if not shutil.which(tool, path=env['PATH']):
            parser.error(f'Missing {tool}; check the installed Quartus/Nios V/RiscFree paths.')
    for checkpoint in range(2, 6) if args.checkpoint == 'all' else [int(args.checkpoint)]:
        generate(checkpoint, build=not args.generate_only, refresh_sources=args.refresh_sources)
    if args.open:
        open_ide()
