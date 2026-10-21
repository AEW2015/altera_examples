#!/usr/bin/env python3
"""Standalone SPI RTL qualification; no UART/JTAG/hardware access."""
import subprocess
from common import ROOT,tool_command,tool_path,tool_exe,tool_env
out=ROOT/'simulation'/'spi';out.mkdir(parents=True,exist_ok=True)
rtl=ROOT/'fpga_hub/iq_bridge/spi_transport'
sources=[rtl/'rtl/iq_spi_master.sv',rtl/'rtl/iq_spi_qualification_top.sv',
 ROOT/'fpga_hub/iq_bridge/vds_demo_01_raw/rtl/uart_fractional.sv',
 rtl/'sim/tb_iq_spi_master.sv',rtl/'sim/tb_iq_spi_qualification.sv']
for top,marker in [('tb_iq_spi_master','PASS SPI modes0-3'),('tb_iq_spi_qualification','PASS SPI board top')]:
 commands=['onerror {quit -code 1}','vlib work',
  'vlog -sv +define+IQ_SPI_SIM '+' '.join('{'+tool_path(s)+'}' for s in sources),
  'vsim -c work.'+top,'run -all','quit -code 0']
 script=out/(top+'.do');script.write_text('\n'.join(commands)+'\n')
 subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
 log=(out/'transcript').read_text();(out/(top+'.log')).write_text(log)
 assert marker in log
print('SPI core and complete board-top qualifications passed')
