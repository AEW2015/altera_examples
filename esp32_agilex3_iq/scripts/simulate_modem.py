#!/usr/bin/env python3
"""Run actual synthesizable modem RTL in Questa against independent Python vectors.

Tests all constellation points, terminated encoder, max-log soft metrics,
full-frame Viterbi, a deliberate one-bit symbol error and parameter boundaries.
No FPGA/JTAG/serial device is opened. --gui opens the saved Questa waveform.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
import numpy as np
from common import ROOT,tool_command,tool_path
sys.path.insert(0,str(ROOT/'cyberether'))
from modem_reference import MODES,BITS_PER_SYMBOL,conv_encode,quantized_mapping,viterbi_decode
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem'

def simulate(gui=False):
 out=STAGE/'results/modem-simulation';out.mkdir(parents=True,exist_ok=True)
 code='''`timescale 1ns/1ps
module tb_modem;
logic clk=0;always #10 clk=~clk;logic reset=1;
logic[3:0]avs_address=0;logic avs_read=1,avs_write=0;logic[31:0]avs_writedata=0;logic[3:0]avs_byteenable=15;wire[31:0]avs_readdata;wire avs_waitrequest;
iq_modem dut(.*);
task wr(input integer a,input logic[31:0]d);begin @(negedge clk);avs_address=4'(a);avs_writedata=d;avs_write=1;@(negedge clk);avs_write=0;end endtask
task wait_done;integer n;begin n=0;avs_address=1;#1;while((avs_readdata&3)!=2)begin @(negedge clk);n++;if(n>100000)$fatal(1,"timeout state %h",avs_readdata);end if(avs_readdata&4)$fatal(1,"error");end endtask
task dump(input string path,input integer regnum,input integer count);integer f;begin f=$fopen(path,"w");for(integer j=0;j<count;j++)begin wr(4,32'(j));repeat(2)@(negedge clk);avs_address=4'(regnum);#1;$fwrite(f,"%08x\\n",avs_readdata);end $fclose(f);end endtask
initial begin
repeat(5)@(negedge clk);reset=0;
'''
 cases=[]
 for case in (*MODES, '64QAM-AWGN'):
  mode=case.split('-')[0]
  bps=BITS_PER_SYMBOL[mode];bits=np.random.default_rng(123+bps).integers(0,2,256,dtype=np.uint8);coded=conv_encode(bits);mapping=quantized_mapping(mode)
  padded=np.pad(coded,(0,(-len(coded))%bps));labels=padded.reshape(-1,bps).dot(1<<np.arange(bps-1,-1,-1));iq=mapping[labels]
  # One wrong coded bit: nearest different Gray label, correctable by FEC.
  noisy=iq.copy();noisy[10]=mapping[int(labels[10])^1]
  expected_errors=1
  if case.endswith('AWGN'):
   noisy=iq.astype(np.int64)+np.rint(np.random.default_rng(405).normal(0,850,iq.shape)).astype(np.int64)
   expected_errors=27
  prefix=case.lower()
  code+=f'// {mode}: every point must match the Python Q3.13 LUT.\n'
  for label,(ri,rq) in enumerate(mapping):code+=f'if(dut.mapped({label},{bps})!==32\'h{int(rq)&65535:04x}{int(ri)&65535:04x})$fatal(1,"{mode} mapping label {label}");\n'
  code+=f'wr(2,{bps});wr(3,256);\n'
  for i,bit in enumerate(bits):code+=f'wr(4,{i});wr(5,{int(bit)});\n'
  code+=f'wr(1,1);wait_done();dump("{prefix}-coded.txt",7,{len(coded)});dump("{prefix}-tx.txt",6,{len(iq)});\n'
  for i,(ri,rq) in enumerate(noisy):code+=f'wr(4,{i});wr(6,32\'h{int(rq)&65535:04x}{int(ri)&65535:04x});\n'
  code+=f'wr(1,2);wait_done();dump("{prefix}-decoded.txt",9,256);dump("{prefix}-soft.txt",8,{len(coded)});\n'
  code+=f'avs_address=12;#1;if(avs_readdata!={expected_errors})$fatal(1,"wrong raw error count %d",avs_readdata);avs_address=13;#1;if(avs_readdata!=0)$fatal(1,"FEC did not correct error");\n'
  cases.append((case,mode,bits,coded,iq,noisy,expected_errors))
 code+='wr(2,3);avs_address=1;#1;if(!(avs_readdata&4))$fatal(1,"bad mode accepted");\n'
 code+='$display("PASS actual RTL BPSK/QPSK/16QAM/64QAM encoder mapper soft demapper Viterbi");$finish;end\nendmodule\n'
 (out/'tb_modem.sv').write_text(code)
 commands=['onerror {quit -force -code 1}','vlib work','vmap work work',f'vlog -sv -work work {{{tool_path(STAGE/"rtl/iq_modem.sv")}}} {{{tool_path(out/"tb_modem.sv")}}}', 'vsim -voptargs=+acc -wlf wave.wlf work.tb_modem','log -r /*','run -all','quit -force -code 0']
 (out/'run.do').write_text('\n'.join(commands)+'\n')
 from notebook_progress import progress
 with progress('Questa: encoder, four constellations, soft demapper and Viterbi'):
  with (out/'questa.log').open('w')as log:subprocess.run(tool_command(['/opt/altera/questa_fse/bin/vsim','-c','-do','run.do'],cwd=out),cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
 if 'PASS actual RTL' not in (out/'questa.log').read_text():raise RuntimeError('Simulation assertion failed; see '+str(out/'questa.log'))
 checks=[]
 for case,mode,bits,coded,iq,noisy,expected_errors in cases:
  prefix=case.lower();read=lambda suffix:np.array([int(x,16)for x in (out/f'{prefix}-{suffix}.txt').read_text().split()],dtype=np.uint32)
  assert np.array_equal(read('coded'),coded),mode+' encoder'
  actual=read('tx').astype('<u4').view('<i2').reshape(-1,2);assert np.array_equal(actual,iq),mode+' mapper'
  assert np.array_equal(read('decoded'),bits),mode+' decoded'
  points=quantized_mapping(mode).astype(np.int64);bps=BITS_PER_SYMBOL[mode];labels=((np.arange(len(points))[:,None]>>np.arange(bps-1,-1,-1))&1)
  distances=np.sum((noisy[:,None,:].astype(np.int64)-points[None,:,:])**2,axis=2)
  soft=np.column_stack([np.min(distances[:,labels[:,j]==1],axis=1)-np.min(distances[:,labels[:,j]==0],axis=1)for j in range(bps)])
  soft=np.clip(soft>>18,-127,127).reshape(-1)[:len(coded)].astype(np.int32)
  assert np.array_equal(read('soft').view(np.int32),soft),mode+' soft metric'
  assert np.array_equal(viterbi_decode(soft),bits),mode+' independent Viterbi'
  checks.append(dict(case=case,modulation=mode,payload_bits=len(bits),symbols=len(iq),all_mapping_points=len(points),raw_coded_errors=expected_errors,decoded_payload_errors=0,encoder_bit_exact=True,mapper_bit_exact=True,max_log_bit_exact=True))
 result=dict(source_sha256=hashlib.sha256((STAGE/'rtl/iq_modem.sv').read_bytes()).hexdigest(),status='PASS',actual_rtl=True,processor_simulated=False,rf_tested=False,checks=checks)
 (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if gui:subprocess.Popen(tool_command(['/opt/altera/questa_fse/bin/vsim','-view','wave.wlf'],cwd=out),cwd=out)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gui',action='store_true');a=p.parse_args();simulate(a.gui)
