#!/usr/bin/env python3
"""Build an Atum ROM/runtime UART bridge; --load explicitly replaces the FPGA image."""
import argparse
import os
from pathlib import Path
import subprocess

from common import ROOT, local_tools, tool_env, tool_exe, resolve_uart

PINS = dict(HOST_RX='L1', HOST_TX='T6', RFS2_TX='H13', RFS2_RX='K13',
            PMOD0_TX='AB9', PMOD0_RX='P6', PMOD1_TX='AK1', PMOD1_RX='AJ6',
            A_RX='F27', A_TX='B14', A_GPIO0='H27', B_RX='B19', B_TX='F21', B_GPIO0='A14')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', choices=['rfs2', 'pmod-a', 'pmod-b'])
    parser.add_argument('--mode', choices=['rom', 'runtime'], default='rom')
    parser.add_argument('--load', action='store_true')
    parser.add_argument('--port', help='Atum host UART; detected by USB identity or ATUM_UART')
    parser.add_argument('--simulate', action='store_true', help='Run assertion-based Questa simulation without loading hardware')
    args = parser.parse_args()
    if not local_tools():
        parser.error('Run locally beside the Quartus tools.')
    src = ROOT / 'fpga_hub/esp32_programmer'
    out = src / 'run' / (args.module + '-' + args.mode)
    out.mkdir(parents=True, exist_ok=True)
    env = tool_env()
    if args.simulate:
        commands = f'onerror {{quit -code 1}}\nvlib work\nvlog -sv {{{src / "esp32_programmer.sv"}}} {{{src / "tb_programmer.sv"}}}\nvsim work.tb_programmer\nrun -all\nquit -code 0\n'
        (out / 'simulate.do').write_text(commands)
        result = subprocess.run([str(tool_exe('vsim')), '-c', '-do', 'do simulate.do'], cwd=out, env=env, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (out / 'simulation.log').write_text(result.stdout)
        if 'PASS: 6 routes x 64 combinations' not in result.stdout or '** Fatal:' in result.stdout or '** Error:' in result.stdout:
            raise RuntimeError('Bridge assertions failed; inspect ' + str(out / 'simulation.log'))
        print('PASS: 6 routes x 64 combinations; GPIO0 low/Z and inactive isolation')
        return
    qsf = ['set_global_assignment -name FAMILY "Agilex 3"',
           'set_global_assignment -name DEVICE A3CZ135BB18AE7S',
           'set_global_assignment -name TOP_LEVEL_ENTITY esp32_programmer',
           f'set_global_assignment -name SYSTEMVERILOG_FILE "{src / "esp32_programmer.sv"}"',
           'set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"',
           'set_global_assignment -name RESERVE_ALL_UNUSED_PINS_NO_OUTPUT_GND "AS INPUT TRI-STATED"',
           f'set_parameter -name TARGET {["rfs2", "pmod-a", "pmod-b"].index(args.module)}',
           f'set_parameter -name ROM_MODE {int(args.mode == "rom")}']
    for name, pin in PINS.items():
        qsf.extend([f'set_location_assignment PIN_{pin} -to {name}',
                    f'set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to {name}'])
    (out / 'esp32_programmer.qsf').write_text('\n'.join(qsf) + '\n')
    (out / 'esp32_programmer.qpf').write_text('PROJECT_REVISION = "esp32_programmer"\n')
    with (out / 'build.log').open('w') as log:
        subprocess.run([str(tool_exe('quartus_sh')), '--flow', 'compile', 'esp32_programmer'], cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    sof = out / 'esp32_programmer.sof'
    print('Built:', sof)
    if args.load:
        from lessons import stop_demo
        from flash_esp32 import serial_owners
        try:
            port = resolve_uart(args.port)
        except RuntimeError as error:
            parser.error(str(error))
        stop_demo()
        if serial_owners(port):
            parser.error('Stop unrelated serial readers before loading the UART bridge.')
        cable = os.getenv('ATUM_JTAG_CABLE', 'Atum A3 Nano [1-4.3-iface0]')
        subprocess.run([str(tool_exe('quartus_pgm')), '-c', cable, '-m', 'JTAG', '-o', 'p;' + str(sof) + '@1'], env=env, check=True)
        # This image has no Nios/DSP; invalidate the previous runtime identity.
        (ROOT / 'cyberether/run/active-fpga.json').unlink(missing_ok=True)
        print('Bridge loaded. ROM mode still requires the selected ESP32 reset button. Restore a lesson SOF before CyberEther.')


if __name__ == '__main__':
    main()
