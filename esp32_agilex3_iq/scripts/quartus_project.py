#!/usr/bin/env python3
"""Export a self-contained, generated-HDL Quartus project with all constraints."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from common import stages, tool_exe, tool_env


def check_project(project):
    """Check direct QSF inputs and every generated QIP's relative file references."""
    project = Path(project).resolve()
    qsf = (project / 'iq_bridge_vds.qsf').read_text()
    required = set()
    for line in qsf.splitlines():
        match = re.search(r'-name (?:SDC_FILE|SYSTEMVERILOG_FILE|QIP_FILE) (?:"([^"]+)"|(\S+))', line)
        if match:
            required.add(match[1] or match[2])
    if 'iq_bridge_vds.sdc' not in required:
        raise ValueError('Project does not explicitly assign iq_bridge_vds.sdc.')
    if 'gen/vds/iq_bridge_system/iq_bridge_system.qip' not in required:
        raise ValueError('Project does not assign the generated system QIP.')
    for name in required:
        path = (project / name).resolve()
        if not path.is_relative_to(project) or not path.is_file():
            raise ValueError('Missing/external Quartus source: ' + str(path))
    for qip in (project / 'gen').rglob('*.qip'):
        for name in re.findall(r'\[file join \$::quartus\(qip_path\) "([^"]+)"\]', qip.read_text()):
            path = (qip.parent / name).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                raise ValueError(f'{qip.relative_to(project)} references missing/external file: {name}')
    return sorted(required)


def prepare_project(stage, destination, archive=None):
    stage, destination = Path(stage).resolve(), Path(destination).resolve()
    qip = stage / 'gen/vds/iq_bridge_system/iq_bridge_system.qip'
    if not qip.is_file():
        raise ValueError('Generate native VDS/IP first; missing ' + str(qip))
    if destination == stage or stage.is_relative_to(destination):
        raise ValueError('Export destination must be a separate generated directory.')
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('iq_bridge_vds.qpf', 'iq_bridge_vds.sdc'):
        shutil.copy2(stage / name, destination / name)
    for name in ('rtl', 'ip', 'sw', 'scripts', 'src', 'gen'):
        target = destination / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
        if (stage / name).exists():
            shutil.copytree(stage / name, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.elf', '*.map', 'BUILD_RESULT.json'))
    # A generated QIP snapshot builds directly in the GUI. Native VDS metadata
    # remains available for viewing; rebuilding it uses the included Tcl scripts.
    lines = [line for line in (stage / 'iq_bridge_vds.qsf').read_text().splitlines()
             if not re.search(r'-name (?:VDS_FILE|VDS_IP_FILE|IP_SEARCH_PATHS|QIP_FILE)\b', line)]
    lines.append('set_global_assignment -name QIP_FILE gen/vds/iq_bridge_system/iq_bridge_system.qip')
    # VDS normally registers each leaf IP separately; its system QIP only
    # contains the interconnect/wrappers and does not include these QIPs.
    for child in sorted((stage / 'gen/vds/iq_bridge_system/ip').glob('*/*.qip')):
        lines.append('set_global_assignment -name QIP_FILE ' + str(child.relative_to(stage)))
    (destination / 'iq_bridge_vds.qsf').write_text('\n'.join(lines) + '\n')
    required = check_project(destination)
    (destination / 'OPEN_IN_QUARTUS.md').write_text('''# Open and build this exported project

Open **iq_bridge_vds.qpf** with Quartus Prime Pro 26.1.1 and Agilex 3 device support.
Choose **Processing → Start Compilation**. The QSF includes the board top, pin/
electrical assignments, the 50 MHz SDC and the generated system QIP. All QIP
implementation sources, IP constraints and Nios RAM initialization HEX files are
included; no ESP32 SDK, Nios compiler or original checkout is needed to compile.

The target is Atum A3 Nano / A3CZ135BB18AE7S. Compilation does not program hardware.

For the native block diagram, open Tools → Visual Designer Studio, then
src/vds/iq_bridge_system/iq_bridge_system.vds. This project compiles its generated
HDL snapshot. To change the native design, edit the supplied creation/connection
Tcl definitions and regenerate them locally with:

    quartus_sh -t scripts/create_vds.tcl
    quartus_sh -t scripts/connect_vds.tcl

The included sw/monitor.hex is already built where Nios is present. The Tcl
generation rebinds memory initialization to this extracted directory. To change
CPU code, use the repository's official BSP/application workflow.

Extract the ZIP to a work folder for edits: the build/notebook export directory
is regenerated. Do not open a lone downloaded QPF without its sibling files.
''')
    files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob('*')) if p.is_file()
             and (p.relative_to(destination).parts[0] in ('rtl', 'ip', 'sw', 'scripts', 'src', 'gen')
                  or p.name in ('iq_bridge_vds.qpf', 'iq_bridge_vds.qsf', 'iq_bridge_vds.sdc', 'OPEN_IN_QUARTUS.md'))
             and not any(part in ('db', 'qdb', 'dni', 'run', 'results') for part in p.relative_to(destination).parts)}
    manifest = dict(source_checkpoint=stage.name, project='iq_bridge_vds.qpf',
                    sdc='iq_bridge_vds.sdc', device='A3CZ135BB18AE7S',
                    compile_mode='generated QIP snapshot', direct_inputs=required, files=files)
    (destination / 'PROJECT_FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if archive:
        archive = Path(archive)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in [*files, 'PROJECT_FILES.json']:
                z.write(destination / name, stage.name + '/' + name)
    return destination / 'iq_bridge_vds.qpf'


def export_project(stage):
    stage = Path(stage)
    archive = stage / 'results' / (stage.name + '-quartus-project.zip')
    qpf = prepare_project(stage, stage / 'results/quartus_project', archive)
    print('Quartus project:', qpf, flush=True)
    print('Project ZIP:', archive, flush=True)
    return qpf, archive


def verify_archive(stage):
    """Compile an extracted archive in a new directory, without programming hardware."""
    stage = Path(stage)
    archive = stage / 'results' / (stage.name + '-quartus-project.zip')
    parent = Path(tempfile.mkdtemp(prefix='atum-quartus-portable-'))
    with zipfile.ZipFile(archive) as z:
        z.extractall(parent)
    project = parent / stage.name
    check_project(project)
    log = stage / 'results/portable-build.log'
    started = time.monotonic()
    with log.open('w') as f:
        result = subprocess.run([str(tool_exe('quartus_sh')), '--flow', 'compile', 'iq_bridge_vds'],
                                cwd=project, env=tool_env(), stdout=f, stderr=subprocess.STDOUT)
    proof = dict(status='PASS' if result.returncode == 0 else 'FAIL',
                 seconds=round(time.monotonic() - started, 1),
                 extracted_project=str(project / 'iq_bridge_vds.qpf'),
                 archive=str(archive), archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), log=str(log))
    if result.returncode == 0:
        proof['top_sdc_read'] = "Reading SDC File: 'iq_bridge_vds.sdc'" in log.read_text()
        slacks = [float(x) for x in re.findall(r'Slack : (-?[\d.]+)', (project / 'iq_bridge_vds.sta.summary').read_text())]
        proof['minimum_reported_slack_ns'] = min(slacks) if slacks else None
        if not proof['top_sdc_read'] or not slacks or min(slacks) < 0:
            proof['status'] = 'FAIL_CONSTRAINTS_OR_TIMING'
    (stage / 'results/portable-build.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(stage.name, 'extracted GUI-project build:', proof['status'], flush=True)
    if proof['status'] != 'PASS':
        raise RuntimeError('Extracted project failed; inspect ' + str(log))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', choices=['1', '2', '3', '4', '5', '7', '8', 'all'])
    parser.add_argument('--verify', action='store_true', help='Compile each ZIP after extracting to a fresh directory')
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    if args.checkpoint == 'all':
        selected = stages()  # Preserve the established 1–5 `all` scope.
    elif args.checkpoint == '8':
        from preamble_pipeline import STAGE
        selected = [STAGE]
    elif args.checkpoint == '7':
        # Import lazily: spi_pipeline imports this module inside its build path.
        from spi_pipeline import STAGE
        selected = [STAGE]
    else:
        selected = [stages()[int(args.checkpoint) - 1]]
    for stage in selected:
        export_project(stage)
    if args.verify:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            list(pool.map(verify_archive, selected))
