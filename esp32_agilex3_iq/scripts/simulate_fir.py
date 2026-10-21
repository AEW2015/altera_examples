#!/usr/bin/env python3
"""Simulate actual generated FIR II VHDL with custom snapshot controller in Questa."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,zlib,os
from common import ROOT,tool_command,tool_path
import numpy as np
STAGE=Path(os.environ['ATUM_SIM_STAGE'])
sys.path.insert(0,str(ROOT/'cyberether'))
from nios_fir import fixed_reference,HAMMING
out=STAGE/'results/notebook/simulation';out.mkdir(parents=True,exist_ok=True)
ip=STAGE/'gen/vds/iq_bridge_system/ip/iq_bridge_system_fir_ii'
qip=ip/'iq_bridge_system_fir_ii.qip'
assert qip.exists()
files=[(kind,ip/name) for kind,name in re.findall(r'-name (VHDL_FILE|VERILOG_FILE) \[file join \$::quartus\(qip_path\) "([^"]+)"\]',qip.read_text())]
for p in ip.glob('**/*_rm.hex'):shutil.copy2(p,out/p.name)
raw=np.array([[-7+17*i,63-9*i] for i in range(8)],dtype=np.int8)
crc=zlib.crc32(raw.tobytes())
cap='\n'.join(f"@(negedge clk);cap_write=1;cap_waddr=15'd{i};cap_wdata=16'h{q&255:02x}{a&255:02x};cap_commit={int(i==7)};" for i,(a,q) in enumerate(raw.tolist()))
bench='''`timescale 1ns/1ps
module tb_fir;
logic clk=0;always #10 clk=~clk;
logic uart_arm=0,uart_owned=0;logic[13:0]uart_index=0;
wire uart_enable,uart_available,uart_done,uart_fault;wire[15:0]uart_q;wire[31:0]uart_crc,uart_profile;
logic reset=1,bus_reset=0,cap_write=0,cap_commit=0,cap_bank=0;
logic[14:0]cap_waddr=0,cap_samples=8;logic[15:0]cap_wdata=0;
logic[31:0]cap_job=32'h12345678,cap_crc=CAP_CRC,cap_rate=16000000,cap_frequency=2417000000;logic[1:0]cap_source=2;
wire[15:0]fir_data;wire fir_valid;wire[1:0]fir_error;
wire[55:0]fir_result;wire fir_result_valid;wire[1:0]fir_result_error;
logic[5:0]avs_address=0;logic avs_read=1,avs_write=0;logic[31:0]avs_writedata=0;logic[3:0]avs_byteenable=15;wire[31:0]avs_readdata;wire avs_waitrequest;
iq_fir_capture dut(.*);
logic[3:0]ca=0;logic cr=0,cw=0;logic[15:0]cd=0;wire[15:0]cq;wire cv,waitreq;
iq_bridge_system_fir_ii core(.clk(clk),.reset_n(!reset),.ast_sink_data(fir_data),.ast_sink_valid(fir_valid),.ast_sink_error(fir_error),.ast_source_data(fir_result),.ast_source_valid(fir_result_valid),.ast_source_error(fir_result_error),.coeff_in_clk(clk),.coeff_in_areset(!reset),.coeff_in_address(ca),.coeff_in_read(cr),.coeff_out_valid(cv),.coeff_out_waitrequest(waitreq),.coeff_out_data(cq),.coeff_in_we(cw),.coeff_in_data(cd));
task wr(input[5:0]a,input[31:0]d);begin @(negedge clk);avs_address=a;avs_writedata=d;avs_write=1;@(negedge clk);avs_write=0;end endtask
task wait_state(input integer mask);integer timeout;begin
 timeout=0;avs_address=1;#1;
 while(!(avs_readdata&mask) || (avs_readdata&8))begin @(negedge clk);timeout++;if(timeout>200000)$fatal(1,"FIR timeout state=%h",avs_readdata);end
end endtask
task coeff(input integer idx,input integer data);begin @(negedge clk);ca=4'(idx);cd=16'(data);cw=1;@(negedge clk);cw=0;repeat(5)@(negedge clk);end endtask
task check_clips(input integer expected);begin avs_address=17;#1;if(avs_readdata!=expected)$fatal(1,"clips expected %d got %d",expected,avs_readdata);end endtask
task dump(input string name,input integer n);integer f;reg[15:0]a,b;begin
 f=$fopen(name,"w");for(integer i=0;i<n;i++)begin wr(6,32'(i));repeat(3)@(negedge clk);avs_address=7;#1;a=avs_readdata[15:0];avs_address=8;#1;b=avs_readdata[15:0];$fwrite(f,"%04x %04x\\n",a,b);end $fclose(f);
end endtask
initial begin
 repeat(8)@(negedge clk);reset=0;repeat(64)@(negedge clk);
 for(integer i=0;i<16;i++)coeff(i,2048);
 wr(16,1);wait_state(2);wr(2,0);wr(1,2);wait_state(4);dump("bypass.txt",128);
 wr(2,1);wr(1,2);wait_state(4);dump("impulse.txt",128);
 for(integer i=0;i<16;i++)coeff(i,i==0?16384:i==1?8192:i==2?-4096:0);
 wr(1,2);wait_state(4);dump("custom.txt",128);
 for(integer i=0;i<16;i++)coeff(i,2048);
 wr(16,2);wait_state(2);wr(1,2);wait_state(4);dump("tones.txt",128);
 for(integer i=0;i<16;i++)coeff(i,32767);
 wr(1,2);wait_state(4);dump("saturation.txt",128);check_clips(CLIPS);
 for(integer i=0;i<16;i++)coeff(i,HAMMING_EXPR);
 wr(19,1);wr(20,2);wr(1,2);wait_state(4);dump("hamming-rounded.txt",128);
 for(integer i=0;i<16;i++)coeff(i,2048);
 wr(19,0);wr(1,1);
CAPTURE_STIM
 @(negedge clk);cap_write=0;cap_commit=0;wait_state(2);
 // An unarmed later write cannot overwrite the frozen source.
 @(negedge clk);cap_write=1;cap_waddr=0;cap_wdata=16'hffff;@(negedge clk);cap_write=0;
 wr(1,2);wait_state(4);dump("capture.txt",8);
 // Automatic paired-UART capture, with run descriptor and RAM index path.
 wr(18,1);wr(19,1);wr(20,1);
 @(negedge clk);uart_owned=1;uart_arm=1;@(negedge clk);uart_arm=0;
CAPTURE_STIM
 @(negedge clk);cap_write=0;cap_commit=0;wait_state(4);
 if(uart_profile!=32'h80010101)$fatal(1,"descriptor %h",uart_profile);
 begin integer f;f=$fopen("uart.txt","w");
 for(integer i=0;i<8;i++)begin @(negedge clk);uart_index=14'(i);repeat(3)@(negedge clk);$fwrite(f,"%04x\\n",uart_q);end
 $fclose(f);end
 @(negedge clk);uart_owned=0;
 avs_address=10;#1;if(avs_readdata!=0)$fatal(1,"FIR engine errors %d",avs_readdata);
 $display("PASS actual FIR II, bypass, impulse, custom coefficients, two-tone, qualified snapshot and frozen RAM");$finish;
end
endmodule
'''.replace('CAP_CRC',f"32'h{crc:08x}").replace('CAPTURE_STIM',cap).replace('CLIPS',str(125)).replace('HAMMING_EXPR','i==0?-42:i==1?-177:i==2?-406:i==3?-352:i==4?669:i==5?2961:i==6?5846:i==7?7885:i==8?7885:i==9?5846:i==10?2961:i==11?669:i==12?-352:i==13?-406:i==14?-177:i==15?-42:0')
(out/'tb_fir.sv').write_text(bench)
def container(p):return tool_path(p)
commands=['onerror {quit -force -code 1}','vlib work','vmap work work']
for kind,p in files:commands.append(('vcom -2008' if kind=='VHDL_FILE' else 'vlog')+' -work work {'+container(p)+'}')
commands+=['vlog -sv -work work {'+container(STAGE/'rtl/iq_fir_capture.sv')+'} {'+container(out/'tb_fir.sv')+'}', 'vsim -voptargs=+acc -wlf wave.wlf -t ps -L altera_mf -L altera_lnsim -L tennm work.tb_fir','log /*','run -all','quit -force -code 0']
(out/'run.do').write_text('\n'.join(commands)+'\n')
cmd=tool_command(['/opt/altera/questa_fse/bin/vsim','-c','-do','run.do'],cwd=out)
with (out/'questa.log').open('w') as log:subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
assert 'PASS actual FIR II' in (out/'questa.log').read_text()
checks={}
for name,coeff in [('bypass',None),('impulse',[2048]*16),('custom',[16384,8192,-4096]+[0]*13),('tones',[2048]*16),('saturation',[32767]*16),('capture',[2048]*16),('hamming-rounded',HAMMING)]:
 words=[line.split() for line in (out/(name+'.txt')).read_text().splitlines()]
 a=np.frombuffer(b''.join(int(x,16).to_bytes(2,'little') for x,y in words),np.int8).reshape(-1,2)
 b=np.frombuffer(b''.join(int(y,16).to_bytes(2,'little') for x,y in words),np.int8).reshape(-1,2)
 expected=a if coeff is None else fixed_reference(a,coeff,round_nearest=name=='hamming-rounded')
 assert np.array_equal(b,expected),(name,a[:20].tolist(),b[:20].tolist(),expected[:20].tolist())
 if name=='capture':assert np.array_equal(a,raw)
 checks[name]=dict(samples=len(a),bit_exact=True)
uart=np.frombuffer(b''.join(int(x,16).to_bytes(2,'little') for x in (out/'uart.txt').read_text().split()),np.int8).reshape(-1,2)
assert np.array_equal(uart,fixed_reference(raw,[2048]*16,True))
checks['automatic_uart']=dict(samples=8,bit_exact=True)
result=dict(status='PASS',actual_generated_fir_ii=True,processor_simulated=False,checks=checks,source_sha256={str(p.relative_to(STAGE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [STAGE/'rtl/iq_fir_capture.sv']+[p for kind,p in files]})
(STAGE/'results/fir-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
