#!/usr/bin/env python3
"""Generate independent IQS1 vectors and qualify FPGA packet/meter RTL in Questa."""
import subprocess,sys
from common import ROOT,tool_command,tool_path,tool_exe,tool_env
sys.path.insert(0,str(ROOT/'cyberether'))
from spi_ci8 import encode,CHUNK
out=ROOT/'simulation/spi_meter';out.mkdir(parents=True,exist_ok=True)
data=bytes((n*37+11)&255 for n in range(32760))
packets=b''.join(encode(2,0,n,len(data),data[n:n+CHUNK],synthetic=True) for n in range(0,len(data),CHUNK))
(out/'valid_capture.hex').write_text('\n'.join(f'{v:02x}' for v in packets)+'\n')
rtl=ROOT/'fpga_hub/iq_bridge/spi_meter'
sources=[rtl/'rtl/iq_spi_capture_meter.sv',rtl/'rtl/iq_spi_meter_top.sv',
 ROOT/'fpga_hub/iq_bridge/spi_transport/rtl/iq_spi_master.sv',
 ROOT/'fpga_hub/iq_bridge/vds_demo_01_raw/rtl/uart_fractional.sv',
 rtl/'sim/tb_iq_spi_capture_meter.sv',rtl/'sim/tb_iq_spi_meter_top.sv']
for top,marker in [('tb_iq_spi_capture_meter','PASS SPI capture meter'),('tb_iq_spi_meter_top','PASS SPI meter board')]:
 script=out/(top+'.do');script.write_text('\n'.join(['onerror {quit -code 1}','vlib work','vlog -sv +define+IQ_SPI_SIM '+' '.join('{'+tool_path(s)+'}' for s in sources),'vsim -c work.'+top,'run -all','quit -code 0'])+'\n')
 subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
 log=(out/'transcript').read_text();(out/(top+'.log')).write_text(log)
 assert marker in log
print('FPGA packet/meter and complete board-path qualifications passed')
