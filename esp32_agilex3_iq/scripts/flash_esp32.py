#!/usr/bin/env python3
"""Flash the built RF suite through a direct UART or temporary FPGA ROM bridge."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from common import ROOT


def serial_owners(port):
    """Find Linux processes holding the selected device, including by-id aliases."""
    target = Path(port).resolve()
    owners = set()
    for proc in Path('/proc').glob('[0-9]*'):
        if proc.name == str(os.getpid()):
            continue
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    if fd.resolve() == target:
                        owners.add(int(proc.name))
                except OSError:
                    pass
        except OSError:
            pass
    return sorted(owners)


def profile(module):
    return 'rfs2' if module == 'rfs2' else 'pmod'


def images(build, module):
    """Use IDF's actual offsets and reject a firmware profile with the wrong pins."""
    build = Path(build).resolve()
    desc = json.loads((build / 'project_description.json').read_text())
    cfg = json.loads((build / 'config/sdkconfig.json').read_text())
    diagnostic = desc['project_name'] == 'atum_esp32_tx_probe'
    wifi64 = desc['project_name'] == 'wifi64_tx'
    wifi64_monitor = desc['project_name'] == 'wifi64_monitor'
    original_iq = desc['project_name'] == 'atum_original_iq_tx_probe'
    if original_iq and (module != 'pmod-a' or not cfg.get('ATUM_ORIGINAL_IQ_TX_PROBE') or
                        not cfg.get('ESP_PHY_ENABLE_CERT_TEST') or not cfg.get('FREERTOS_UNICORE')):
        raise ValueError('Original-chip amplitude diagnostic requires pmod-a only and its explicit certification/unicore build profile.')
    if wifi64 and module != 'pmod-a':
        raise ValueError('Native Wi-Fi 64-QAM transmitter is configured for pmod-a only.')
    if wifi64_monitor and module != 'pmod-b':
        raise ValueError('Native Wi-Fi monitor is configured for pmod-b only.')
    cache = (build / 'CMakeCache.txt').read_text() if (build / 'CMakeCache.txt').exists() else ''
    spi = desc['project_name'] == 'esp32_spi_probe' or (desc['project_name'] == 'atum_rf_suite' and
            'IQ_SPI_RX_PROFILE:BOOL=ON' in cache.splitlines())
    if spi and module != 'pmod-b':
        raise ValueError('Separate SPI qualification images are explicitly configured for pmod-b only.')
    if desc['target'] != 'esp32' or desc['project_name'] not in ('atum_rf_suite', 'atum_esp32_tx_probe', 'esp32_spi_probe', 'wifi64_tx', 'wifi64_monitor', 'atum_original_iq_tx_probe'):
        raise ValueError('Expected an original-ESP32 RF suite or bounded TX probe build.')
    if diagnostic and (not cfg.get('ATUM_TX_PROBE') or profile(module) != 'pmod'):
        raise ValueError('The bounded TX probe is explicitly configured for a Pmod only.')
    expected = (1, 3) if spi or profile(module) == 'rfs2' else (17, 16)
    console = (1, 3) if cfg.get('ESP_CONSOLE_UART_DEFAULT') else tuple(cfg.get('ESP_CONSOLE_UART_' + key + '_GPIO') for key in ('TX', 'RX'))
    actual = console if desc['project_name'] == 'esp32_spi_probe' or wifi64 or wifi64_monitor or original_iq else tuple(cfg.get('ESP_SDR_UART_' + key + '_PIN') for key in ('TX', 'RX'))
    if actual != expected:
        raise ValueError(f'{module} needs application UART TX/RX {expected}; this build has {actual}.')
    if profile(module) == 'pmod' and console != expected:
        raise ValueError('Pmod console must also use the selected UART profile pins.')
    spec = json.loads((build / 'flasher_args.json').read_text())
    pairs = []
    end = 0
    for offset, name in sorted(spec['flash_files'].items(), key=lambda p: int(p[0], 0)):
        path = (build / name).resolve()
        if not path.is_relative_to(build) or not path.is_file():
            raise ValueError('Missing or out-of-build firmware image: ' + str(path))
        start = int(offset, 0)
        if start < end or start + path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Overlapping image or image outside the supported 2 MiB flash layout.')
        end = start + path.stat().st_size
        pairs.append((offset, path))
    if {int(offset, 0) for offset, _ in pairs} != {0x1000, 0x8000, 0x10000}:
        raise ValueError('Expected bootloader, partition table and application offsets.')
    return spec, pairs


def record(build, module):
    spec, pairs = images(build, module)
    desc = json.loads((build / 'project_description.json').read_text())
    sdk = Path(desc['idf_path'])
    commit = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'], text=True).strip()
    data = dict(profile=profile(module), chip='esp32', esptool_python=sys.executable,
                sdk_commit=commit, sdk_path=str(sdk),
                flash_files={offset: dict(file=str(path.relative_to(build)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for offset, path in pairs})
    (build / 'FIRMWARE_BUILD.json').write_text(json.dumps(data, indent=2) + '\n')
    print('Firmware build recorded:', build / 'FIRMWARE_BUILD.json')


def tool_command(python, port, baud, reset, major, action, spec, pairs):
    modern = major >= 5
    def flag(value):
        if modern:
            return value
        return '--' + value[2:].replace('-', '_') if value.startswith('--') else value.replace('-', '_')
    command = [str(python), '-m', 'esptool', '--chip', 'esp32', '--port', port,
               '--baud', str(baud), '--before', flag('default-reset' if reset == 'auto' else 'no-reset'),
               '--after', flag('hard-reset' if reset == 'auto' else 'no-reset')]
    if action == 'info':
        return command + ['--no-stub', flag('read-mac')]
    command += [flag('write-flash' if action == 'flash' else 'verify-flash')]
    if action == 'flash':
        command += [flag(v) if v.startswith('--') else v for v in spec['write_flash_args']]
    return command + [value for offset, path in pairs for value in (offset, str(path))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', choices=['rfs2', 'pmod', 'pmod-a', 'pmod-b'], required=True)
    parser.add_argument('--port', help='Direct ROM UART port; the normal IQB1 hub protocol cannot flash an ESP32')
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--action', choices=['info', 'flash', 'verify'], default='flash')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--reset', choices=['manual', 'auto'], default='manual', help='Auto requires a direct adapter wired to EN/GPIO0')
    parser.add_argument('--esptool-python', type=Path, help='Python interpreter with esptool (normally read from the build record)')
    parser.add_argument('--expect-mac', help='Refuse to write unless the ROM reports this MAC')
    parser.add_argument('--dry-run', action='store_true', help='Validate images and print the command without opening hardware')
    parser.add_argument('--record-build', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    build = (args.build_dir or ROOT / ('build-esp32' if profile(args.module) == 'rfs2' else 'build-esp32-pmod')).resolve()
    try:
        spec, pairs = images(build, args.module)
        if args.record_build:
            record(build, args.module)
            return
        if not args.port:
            parser.error('--port is required; select the module ROM UART, not a running IQB1 hub.')
        python = args.esptool_python
        manifest = build / 'FIRMWARE_BUILD.json'
        if manifest.exists():
            data = json.loads(manifest.read_text())
            for offset, path in pairs:
                if hashlib.sha256(path.read_bytes()).hexdigest() != data['flash_files'][offset]['sha256']:
                    raise ValueError('Firmware image changed since the recorded build; rebuild before flashing.')
            python = python or Path(data['esptool_python'])
        python = python or Path(sys.executable)
        version = subprocess.check_output([str(python), '-m', 'esptool', 'version'], text=True, stderr=subprocess.STDOUT)
        match = re.search(r'(?:esptool v|^)([45])\.', version, re.M)
        if not match:
            raise ValueError('Expected esptool 4.x or 5.x; use the pinned SDK Python interpreter.')
        major = int(match[1])
        command = tool_command(python, args.port, args.baud, args.reset, major, args.action, spec, pairs)
        print('Module:', args.module, '| firmware profile:', profile(args.module), '| reset:', args.reset, flush=True)
        if args.dry_run:
            import shlex
            print(shlex.join(command))
            return
        owners = serial_owners(args.port)
        if owners:
            raise ValueError(f'Serial port is already open by PID(s) {owners}; stop that acquisition first.')
        # Exclusive open catches an active acquisition owner without resetting the device.
        import serial
        check = serial.Serial(port=None, baudrate=args.baud, exclusive=True)
        check.dtr = False
        check.rts = False
        check.port = args.port
        check.open()
        check.close()
        if args.expect_mac:
            # A no-reset probe must leave the loader at its initial baud for
            # the following esptool process, which reconnects at 115200.
            probe = tool_command(python, args.port, 115200, args.reset, major, 'info', spec, pairs)
            output = subprocess.check_output(probe, text=True, stderr=subprocess.STDOUT)
            macs = re.findall(r'(?i)\bMAC:\s*([0-9a-f:]{17})', output)
            if args.expect_mac.lower() not in [mac.lower() for mac in macs]:
                raise ValueError('Target MAC does not match --expect-mac; no flash write attempted.')
        subprocess.run(command, check=True)
        if args.reset == 'manual':
            print('ROM session complete. Release GPIO0 / restore the runtime FPGA image, then reset the selected ESP32 for normal boot.')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
