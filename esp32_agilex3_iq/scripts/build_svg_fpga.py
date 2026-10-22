#!/usr/bin/env python3
"""Generate and compile the standalone A3 Nano SVG modem FPGA project.

This is a build-only flow. It never programs the FPGA or opens UART/JTAG.
Set ATUM_TOOLS_MODE=docker to use the configured Quartus container.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, altera_root, quartus_root, tool_command, tool_env, tool_path

STAGE = ROOT / 'fpga_hub' / 'iq_bridge' / 'svg_modem'
RUN = STAGE / 'run'
DEFAULT_BUILD = RUN / 'build'


def write_project_files(build: Path) -> None:
    """Create the small board project around the generated Platform Designer system."""
    (build / 'svg_demo.qpf').write_text('PROJECT_REVISION = "svg_demo"\n')
    rom_dir = build / 'rtl'
    rom_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STAGE / 'rtl' / 'svg_waveform.hex', rom_dir / 'svg_waveform.hex')
    qsf = [
        'set_global_assignment -name FAMILY "Agilex 3"',
        'set_global_assignment -name DEVICE A3CZ135BB18AE7S',
        'set_global_assignment -name TOP_LEVEL_ENTITY svg_demo_top',
        'set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"',
        'set_global_assignment -name RESERVE_ALL_UNUSED_PINS_NO_OUTPUT_GND "AS INPUT TRI-STATED"',
        'set_global_assignment -name SYSTEMVERILOG_FILE ../../rtl/svg_demo_top.sv',
        'set_global_assignment -name HEX_FILE rtl/svg_waveform.hex',
        'set_global_assignment -name SDC_FILE svg_demo.sdc',
        'set_global_assignment -name NUM_PARALLEL_PROCESSORS 4',
        'set_global_assignment -name IP_SEARCH_PATHS "../../ip/**/*;$::env(QUARTUS_ROOTDIR)/../ip/**/*"',
        'set_location_assignment PIN_A8 -to CLOCK_50',
        'set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to CLOCK_50',
    ]
    (build / 'svg_demo.qsf').write_text('\n'.join(qsf) + '\n')
    (build / 'svg_demo.sdc').write_text(
        'create_clock -name clk50 -period 20.000 [get_ports CLOCK_50]\n'
        'create_clock -name altera_reserved_tck -period 62.500 [get_ports altera_reserved_tck]\n'
        'set_clock_groups -asynchronous -group [get_clocks altera_reserved_tck]\n'
        'derive_clock_uncertainty\n'
    )


def run_step(name: str, command: list[str], *, cwd: Path, log_path: Path) -> None:
    print(f'{name}…', flush=True)
    with log_path.open('w') as log:
        subprocess.run(tool_command(command, cwd=cwd), cwd=cwd,
                       env=tool_env(), stdout=log, stderr=subprocess.STDOUT,
                       check=True)


def source_manifest() -> tuple[dict[str, str], str]:
    paths = sorted(
        [p for p in (STAGE / 'rtl').glob('*') if p.suffix in ('.sv', '.hex')]
        + [STAGE / 'ip' / 'svg_modem_mm_hw.tcl',
           STAGE / 'scripts' / 'create_system.tcl',
           ROOT / 'scripts' / 'build_svg_fpga.py']
    )
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in paths}
    fingerprint = hashlib.sha256()
    for relative, digest in hashes.items():
        fingerprint.update(relative.encode())
        fingerprint.update(bytes.fromhex(digest))
    return hashes, fingerprint.hexdigest()


def assert_sources_unchanged(expected: tuple[dict[str, str], str]) -> None:
    current = source_manifest()
    if current != expected:
        raise RuntimeError('Build inputs changed during Quartus run; refusing a result manifest')


def report_metrics(build_dir: Path) -> tuple[dict[str, int | None], dict[str, float]]:
    fit_files = list(build_dir.glob('**/svg_demo.fit.summary'))
    sta_files = list(build_dir.glob('**/svg_demo.sta.summary'))
    if not fit_files or not sta_files:
        raise RuntimeError('Quartus fit or timing summary is missing')
    fit_text = fit_files[0].read_text(errors='replace')
    sta_text = sta_files[0].read_text(errors='replace')
    if 'Fitter Status : Successful' not in fit_text:
        raise RuntimeError('Quartus fit summary does not report a successful fit')
    resources: dict[str, int | None] = {}
    for key, pattern in {
        'ALMs': r'Logic utilization \(in ALMs\)\s*:\s*([\d,]+)',
        'registers': r'Total dedicated logic registers\s*:\s*([\d,]+)',
        'RAM_blocks': r'Total RAM Blocks\s*:\s*([\d,]+)',
        'DSP_blocks': r'Total DSP Blocks\s*:\s*([\d,]+)',
    }.items():
        match = re.search(pattern, fit_text)
        resources[key] = int(match.group(1).replace(',', '')) if match else None

    timing: dict[str, float] = {}
    for kind in ('Setup', 'Hold'):
        matches = [float(value) for value in re.findall(
            rf"Type\s*:\s*{kind}\b[^\n]*\nSlack\s*:\s*(-?[\d.]+)", sta_text)]
        if not matches:
            raise RuntimeError(f'Quartus timing summary has no {kind.lower()} slack values')
        timing[f'min_{kind.lower()}_slack_ns'] = min(matches)
    return resources, timing


def build(build_dir: Path, *, generate_only: bool = False) -> Path:
    required = [
        STAGE / 'rtl' / 'svg_demo_top.sv',
        STAGE / 'rtl' / 'svg_modem_mm.sv',
        STAGE / 'rtl' / 'svg_graph_encoder.sv',
        STAGE / 'rtl' / 'svg_graph_decoder.sv',
        STAGE / 'rtl' / 'svg_edge_waveform.sv',
        STAGE / 'rtl' / 'svg_waveform.hex',
        STAGE / 'ip' / 'svg_modem_mm_hw.tcl',
        STAGE / 'scripts' / 'create_system.tcl',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit('Build inputs are missing: ' + ', '.join(missing))
    initial_sources = source_manifest()
    build_dir.mkdir(parents=True, exist_ok=True)
    write_project_files(build_dir)

    qsys_script = altera_root() / 'qsys' / 'bin' / 'qsys-script'
    qsys_generate = altera_root() / 'qsys' / 'bin' / 'qsys-generate'
    quartus_sh = quartus_root() / 'bin' / 'quartus_sh'
    ip_search = f'{tool_path(STAGE / "ip")},$'
    run_step('Create JTAG-to-Avalon system',
             [str(qsys_script), f'--script={tool_path(STAGE / "scripts/create_system.tcl")}',
              f'--search-path={ip_search}', '--quartus-project=svg_demo', '--rev=svg_demo'], cwd=build_dir,
             log_path=build_dir / 'qsys-script.log')
    system_file = build_dir / 'svg_modem_system.qsys'
    if not system_file.is_file():
        raise RuntimeError('Platform Designer did not create svg_modem_system.qsys')
    run_step('Generate Platform Designer HDL',
             [str(qsys_generate), str(tool_path(system_file)), '--synthesis=SYSTEM_VERILOG',
              '--family=Agilex 3', '--part=A3CZ135BB18AE7S', f'--search-path={ip_search}',
              '--quartus-project=svg_demo', '--rev=svg_demo'],
             cwd=build_dir, log_path=build_dir / 'qsys-generate.log')
    # qsys-script emits both QSYS_FILE and leaf IP_FILE assignments when it is
    # given a Quartus project. Quartus 26 treats the QSYS_FILE as a second
    # registration of the generated root QIP, so use the root QIP directly.
    qsf_path = build_dir / 'svg_demo.qsf'
    qsf_lines = [line for line in qsf_path.read_text().splitlines()
                 if '-name QSYS_FILE ' not in line and '-name QIP_FILE ' not in line]
    qsf_lines.append('set_global_assignment -name QIP_FILE svg_modem_system/svg_modem_system.qip')
    qsf_path.write_text('\n'.join(qsf_lines) + '\n')
    if generate_only:
        assert_sources_unchanged(initial_sources)
        print('Generated system and Quartus project; compilation was skipped.')
        return build_dir / 'svg_demo.qpf'

    assert_sources_unchanged(initial_sources)
    run_step('Compile Agilex 3 design',
             [str(quartus_sh), '--flow', 'compile', 'svg_demo'], cwd=build_dir,
             log_path=build_dir / 'quartus-compile.log')
    assert_sources_unchanged(initial_sources)
    image_candidates = [build_dir / 'output_files' / 'svg_demo.sof',
                        build_dir / 'svg_demo.sof']
    existing_images = [candidate for candidate in image_candidates if candidate.is_file()]
    image = max(existing_images, key=lambda candidate: candidate.stat().st_mtime) if existing_images else None
    if image is None:
        raise RuntimeError('Quartus compile finished without svg_demo.sof')
    resources, timing = report_metrics(build_dir)
    timing_pass = timing['min_setup_slack_ns'] >= 0 and timing['min_hold_slack_ns'] >= 0
    source_hashes, source_fingerprint = source_manifest()
    result = {
        'status': 'PASS_BUILD' if timing_pass else 'FAIL_TIMING',
        'stage': 'standalone-svg-modem',
        'device': 'A3CZ135BB18AE7S',
        'family': 'Agilex 3',
        'clock_hz': 50000000,
        'jtag_avalon_master': True,
        'hardware_programmed': False,
        'hardware_verified': False,
        'source_fingerprint': source_fingerprint,
        'source_hashes': source_hashes,
        'resources': resources,
        'timing': timing,
        'minimum_slack_ns': min(timing.values()),
        'image_file': str(image.relative_to(build_dir)),
        'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
        'built_unix': time.time(),
    }
    (build_dir / 'BUILD_RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    if timing_pass:
        print(f'PASS_BUILD: {image}')
    else:
        print(f'FAIL_TIMING: {timing}; FPGA image was not marked program-ready.')
    print('Build complete. The FPGA was not programmed or hardware-tested.')
    if not timing_pass:
        raise SystemExit(2)
    return build_dir / 'svg_demo.qpf'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate-only', action='store_true',
                        help='create Platform Designer and Quartus sources without compiling')
    parser.add_argument('--build-dir', type=Path, default=DEFAULT_BUILD,
                        help='generated project directory (default: fpga_hub/iq_bridge/svg_modem/run/build)')
    parser.add_argument('--clean', action='store_true', help='remove the selected generated project first')
    args = parser.parse_args()
    build_dir = args.build_dir.expanduser().resolve()
    if args.clean and build_dir.exists():
        if not build_dir.is_relative_to(ROOT):
            parser.error('--clean requires a build directory inside this checkout')
        shutil.rmtree(build_dir)
    qpf = build(build_dir, generate_only=args.generate_only)
    print(qpf)


if __name__ == '__main__':
    main()
