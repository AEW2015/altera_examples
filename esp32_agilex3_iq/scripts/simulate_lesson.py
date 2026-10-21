#!/usr/bin/env python3
"""Small assertion-checked real RTL/IP simulations with saved Questa wave databases."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from common import ROOT,stages,tool_command,tool_path
p=argparse.ArgumentParser();p.add_argument('checkpoint',type=int,choices=range(1,6));a=p.parse_args();stage=stages()[a.checkpoint-1];out=stage/'results/notebook/simulation';out.mkdir(parents=True,exist_ok=True)
if a.checkpoint in (3,4):
 subprocess.run([sys.executable,str(ROOT/'scripts'/('simulate_fir.py'if a.checkpoint==3 else 'simulate_ddc.py'))],env=dict(os.environ,ATUM_SIM_STAGE=str(stage)),check=True)
 top='tb_fir'if a.checkpoint==3 else'tb_ddc'
 result=json.loads((stage/'results'/('fir-validation.json'if a.checkpoint==3 else'ddc-validation.json')).read_text())
else:
 if a.checkpoint==1:
  top='tb_uart';rtl=stage/'rtl/uart_fractional.sv'
  bench='''`timescale 1ns/1ps
module tb_uart;
reg clk=0;always #10 clk=~clk;
reg reset=1,start=0;reg[7:0]send_data=0;wire tx,busy,done,valid,framing_error;wire[7:0]data;
reg[31:0]baud=2000000;integer received=0,f;
uart_fractional_tx u_tx(.clk(clk),.reset(reset),.start(start),.data(send_data),.baud(baud),.tx(tx),.busy(busy),.done(done));
uart_fractional_rx u_rx(.clk(clk),.reset(reset),.rx(tx),.baud(baud),.valid(valid),.data(data),.framing_error(framing_error));
always @(posedge clk)begin
 if(framing_error)$fatal(1,"UART framing");
 if(valid)begin if(data!==8'(received*37+11))$fatal(1,"UART data mismatch");$fwrite(f,"%0d,%0d\\n",received,data);received=received+1;end
end
initial begin f=$fopen("uart.csv","w");repeat(5)@(negedge clk);reset=0;
 for(integer k=0;k<8;k++)begin wait(!busy);@(negedge clk);send_data=8'(k*37+11);start=1;@(negedge clk);start=0;wait(done);repeat(8)@(negedge clk);end
 repeat(100)@(negedge clk);if(received!=8)$fatal(1,"missing bytes");$fclose(f);$display("PASS UART real 8N1 roundtrip, eight binary bytes");$finish;end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
'''
 elif a.checkpoint==2:
  top='tb_monitor';rtl=stage/'rtl/iq_transfer_monitor.sv'
  from monitor_bench import bench

 else:
  top='tb_gain_lesson';rtl=stage/'rtl/iq_gain_meter.sv';bench=(ROOT/'simulation/tb_gain_lesson.sv').read_text();bench=bench.replace('iq_gain_meter dut(.*);', '''integer csv;
initial csv=$fopen("gain.csv","w");
always @(posedge clk)begin #1;if(output_valid)$fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\\n",gain_q8,bypass,$signed(input_i),$signed(output_i),pre_power,post_power,clips);end
iq_gain_meter dut(.*);''')
 (out/'tb.sv').write_text(bench)
 commands=['onerror {quit -force -code 1}','vlib work','vlog -sv {'+tool_path(rtl)+'} tb.sv',f'vsim -voptargs=+acc -wlf wave.wlf work.{top}','log /*','run -all','quit -force -code 0']
 (out/'run.do').write_text('\n'.join(commands)+'\n')
 with(out/'questa.log').open('w')as log:subprocess.run(tool_command(['/opt/altera/questa_fse/bin/vsim','-c','-do','run.do'],cwd=out),cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
 assert 'PASS'in(out/'questa.log').read_text();result=dict(status='PASS',level='real module RTL',processor_simulated=False,checkpoint=a.checkpoint)
(out/'gui.do').write_text('\n'.join(line for line in (out/'run.do').read_text().splitlines() if line.strip()!='quit -force -code 0')+'\nview wave\nadd wave -r /*\nwave zoom full\n')
(out/'view.do').write_text(f'view wave\nadd wave -r wave:/{top}/*\nupdate\nwave zoom full\n')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS checkpoint',a.checkpoint,'→ wave.wlf + view.do')
