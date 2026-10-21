#!/usr/bin/env python3
"""Merged snapshot + DDC + actual generated I/Q FIR II; no modeled FIR arithmetic."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,zlib,os
from common import ROOT,tool_command,tool_path
import numpy as np
S=Path(os.environ['ATUM_SIM_STAGE']);sys.path.insert(0,str(ROOT/'cyberether'))
from nios_ddc import reference
out=S/'results/notebook/simulation';out.mkdir(parents=True,exist_ok=True)
def container(p):return tool_path(p)
cases=[];stim=[]
n=np.arange(256);z=48*np.exp(2j*np.pi*n/32)+64*np.exp(2j*np.pi*3*n/8);raw=np.rint(np.column_stack((z.real,z.imag))).astype(np.int8)
for flags,m in [(0,4),(1,1),(2,4),(3,1)]:cases.append((raw,0x08000000,flags,m))
for i,(a,phase,flags,m)in enumerate(cases):
 path=out/f'raw-{i}.hex';path.write_text('\n'.join(f'{int(q)&255:02x}{int(v)&255:02x}'for v,q in a)+'\n')
 stim.append(f'capture("{container(path)}",{len(a)},32\'h{zlib.crc32(a.tobytes()):08x});drun(32\'h{phase:08x},{flags},{m},"out-{i}.txt");')
bench='''`timescale 1ns/1ps
module tb_ddc;
logic clk=0;always #10 clk=~clk;logic reset=1,bus_reset=0;
logic cap_write=0,cap_commit=0,cap_bank=0;logic[14:0]cap_waddr=0,cap_samples=0;logic[15:0]cap_wdata=0;
logic[31:0]cap_job=42,cap_crc=0,cap_rate=16000000,cap_frequency=2417000000;logic[1:0]cap_source=0;
logic uart_arm=0,uart_owned=0;logic[13:0]uart_index=0;wire uart_enable,uart_available,uart_done,uart_fault;
wire[15:0]uart_q;wire[31:0]uart_crc,uart_profile;
wire[15:0]fir_data;wire fir_valid;wire[1:0]fir_error;wire[55:0]fir_result=0;wire fir_result_valid=0;wire[1:0]fir_result_error=0;
logic[5:0]avs_address=0;logic avs_read=1,avs_write=0;logic[31:0]avs_writedata=0;logic[3:0]avs_byteenable=15;wire[31:0]avs_readdata;wire avs_waitrequest;
wire ddc_ready,ddc_exclusive;wire[13:0]ddc_addr;wire[15:0]ddc_q;wire[319:0]ddc_meta;wire[31:0]ddc_epoch;
iq_fir_capture snapshot(.*);
logic[4:0]address=0;logic read=1,write=0;logic[31:0]writedata=0;wire[31:0]readdata;
wire fir_reset_n;wire[15:0]i_data,q_data;wire in_valid,q_in_valid;wire[1:0]in_error,q_in_error;
wire[38:0]i_result,q_result;wire i_valid,q_valid;wire[1:0]i_error,q_error;
iq_ddc_engine engine(.source_ready(ddc_ready),.source_q(ddc_q),.source_addr(ddc_addr),.source_meta(ddc_meta),.source_epoch(ddc_epoch),.exclusive(ddc_exclusive),.*);
@CORES@
task fw(input[5:0]a,input[31:0]d);begin @(negedge clk);avs_address=a;avs_writedata=d;avs_write=1;@(negedge clk);avs_write=0;end endtask
task dw(input[4:0]a,input[31:0]d);begin @(negedge clk);address=a;writedata=d;write=1;@(negedge clk);write=0;end endtask
reg[15:0]samples[0:16383];
task capture(input string path,input integer n,input[31:0]crc);begin
 fw(1,1);cap_samples=15'(n);cap_crc=crc;$readmemh(path,samples,0,n-1);
 for(integer k=0;k<n;k++)begin @(negedge clk);cap_write=1;cap_waddr=15'(k);cap_wdata=samples[k];@(negedge clk);cap_write=0;end
 @(negedge clk);cap_commit=1;@(negedge clk);cap_commit=0;repeat(4)@(negedge clk);if(!ddc_ready)$fatal(1,"snapshot not ready");
end endtask
task drun(input[31:0]phase,input integer flags,m,input string path);integer timeout,f;reg[31:0]epoch;begin
 dw(2,phase);dw(3,32'(flags|(m<<8)));dw(4,1);address=4;#1;if(readdata!=1)$fatal(1,"DDC rejected");
 epoch=ddc_epoch;fw(1,1);if(ddc_epoch!=epoch || uart_available)$fatal(1,"snapshot not protected");
 address=1;timeout=0;#1;while(readdata&1)begin @(negedge clk);timeout++;if(timeout>3000000)$fatal(1,"DDC timeout");end
 if(readdata!=4)$fatal(1,"DDC fault %h",readdata);
 address=6;#1;f=$fopen(path,"w");
 for(integer k=0;k<readdata;k++)begin end
 address=6;#1;timeout=readdata;
 for(integer k=0;k<timeout;k++)begin dw(20,32'(k));repeat(3)@(negedge clk);address=21;#1;$fwrite(f,"%08x\\n",readdata);end
 $fclose(f);
end endtask
initial begin repeat(8)@(negedge clk);reset=0;repeat(64)@(negedge clk);
@STIM@
$display("PASS merged DDC actual FIR II");$finish;end
endmodule
'''
cores=[];files=[]
for lane in('i','q'):
 ip=S/f'gen/vds/iq_bridge_system/ip/iq_bridge_system_ddc_fir_{lane}';qip=ip/f'iq_bridge_system_ddc_fir_{lane}.qip'
 files.extend((kind,ip/name)for kind,name in re.findall(r'-name (VHDL_FILE|VERILOG_FILE) \[file join \$::quartus\(qip_path\) "([^"]+)"\]',qip.read_text()))
 for p in ip.glob('**/*_rm.hex'):shutil.copy2(p,out/p.name)
 cores.append(f'iq_bridge_system_ddc_fir_{lane} core_{lane}(.clk(clk),.reset_n(fir_reset_n),.ast_sink_data({lane}_data),.ast_sink_valid({"in_valid"if lane=="i"else"q_in_valid"}),.ast_sink_error({"in_error"if lane=="i"else"q_in_error"}),.ast_source_data({lane}_result),.ast_source_valid({lane}_valid),.ast_source_error({lane}_error));')
(out/'tb.sv').write_text(bench.replace('@CORES@','\n'.join(cores)).replace('@STIM@','\n'.join(stim)))
cmd=['onerror {quit -force -code 1}','vlib work','vmap work work']
for kind,p in files:cmd.append(('vcom -2008'if kind=='VHDL_FILE'else'vlog')+' -work work {'+container(p)+'}')
cmd+=['vlog -sv -work work {'+container(S/'rtl/iq_fir_capture.sv')+'} {'+container(S/'rtl/iq_ddc_engine.sv')+'} {'+container(out/'tb.sv')+'}','vsim -voptargs=+acc -wlf wave.wlf -t ps -L altera_mf -L altera_lnsim -L tennm work.tb_ddc','log /*','run -all','quit -force -code 0']
(out/'run.do').write_text('\n'.join(cmd)+'\n')
if '--reuse'not in sys.argv:
    with(out/'questa.log').open('w')as log:subprocess.run(tool_command(['/opt/altera/questa_fse/bin/vsim','-c','-do','run.do'],cwd=out),cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
assert 'PASS merged DDC actual FIR II'in((out/'questa.log').read_text()+(out/'transcript').read_text()), 'Simulation must finish successfully before validating'
checks=[]
for i,(raw,phase,flags,m)in enumerate(cases):
 words=[int(x,16)for x in(out/f'out-{i}.txt').read_text().split()];actual=np.frombuffer(b''.join(x.to_bytes(4,'little')for x in words),'<i2').reshape(-1,2);expected=reference(raw,phase,m,flags)['result'];assert np.array_equal(actual,expected),(i,actual[:10].tolist(),expected[:10].tolist())
 checks.append(dict(samples=len(raw),phase=phase,flags=flags,decimation=m,exact=True))
report=dict(status='PASS',actual_generated_vendor_fir=True,merged_snapshot_arbitration=True,checks=checks,source_sha256={str(p.relative_to(S)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [S/'rtl/iq_fir_capture.sv',S/'rtl/iq_ddc_engine.sv']+[p for _,p in files]})
(S/'results/ddc-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='PASS',actual_generated_vendor_fir=True,exact_cases=len(checks)),indent=2))
