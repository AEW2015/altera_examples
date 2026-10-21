#!/usr/bin/env python3
"""Offline Questa proof of raw-IQ FPGA preamble detector; never accesses hardware."""
import argparse,hashlib,json,subprocess,sys,fcntl,shutil
from pathlib import Path
from common import ROOT,tool_command,tool_path,tool_exe,tool_env

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rf-proof',type=Path);p.add_argument('--rf-index',type=int,default=0);a=p.parse_args()
 stage=ROOT/'fpga_hub/iq_bridge/vds_demo_08_preamble';out=ROOT/'simulation/preamble';out.mkdir(parents=True,exist_ok=True)
 with(out/'simulation.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  cmd=[sys.executable,str(ROOT/'scripts/preamble_vectors.py')]
  if a.rf_proof:cmd+=['--rf-proof',str(a.rf_proof),'--rf-index',str(a.rf_index)]
  subprocess.run(cmd,check=True)
  shutil.rmtree(out/'work',ignore_errors=True)
  rtl=stage/'rtl/iq_preamble.sv';bench=stage/'sim/tb_iq_preamble.sv';commands=['onerror {quit -force -code 1}','vlib work','vlog -sv {'+tool_path(rtl)+'} {'+tool_path(bench)+'}'];fixtures=[]
  for directory in sorted(out.iterdir()):
   ep=directory/'expected.json'
   if not ep.is_file():continue
   expected=json.loads(ep.read_text());n=sum(1 for _ in(directory/'iq.hex').open());count=len(expected['starts'])
   summary=[expected['best_start'],expected['best_score_q15'],expected['best_energy']&0xffffffff,expected['best_energy']>>32,expected['best_sum_real']&0xffffffff,expected['best_sum_imag']&0xffffffff,count,int(expected['detected'])]
   (directory/'summary.hex').write_text('\n'.join(f'{x:08x}'for x in summary)+'\n')
   commands+=['vsim -c -onfinish stop -voptargs=+acc work.tb_iq_preamble +DIR='+tool_path(directory)+' +N='+str(n)+' +SPS='+str(expected['sps'])+' +COUNT='+str(count)+' +STEP='+str(expected['stride']),'run -all','quit -sim'];fixtures.append(directory.name)
  if not fixtures:raise RuntimeError('No reference vectors generated')
  commands+=['quit -force -code 0'];do=out/'run.do';do.write_text('\n'.join(commands)+'\n')
  gui=[c.replace('vsim -c ','vsim ')for c in commands[:4]]+['view wave','add wave /tb_iq_preamble/dut/state /tb_iq_preamble/dut/start /tb_iq_preamble/dut/sum_r /tb_iq_preamble/dut/sum_i /tb_iq_preamble/dut/energy /tb_iq_preamble/dut/score /tb_iq_preamble/dut/best_score','run -all']
  (out/'gui.do').write_text('\n'.join(gui)+'\n')
  with(out/'questa.log').open('w')as log:subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(do)],cwd=out),cwd=out,env=tool_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
  text=(out/'questa.log').read_text()
  for name in fixtures:
   if not any('PASS preamble fixture' in l and '/'+name+':'in l for l in text.splitlines()):raise RuntimeError('Missing fixture PASS '+name)
  result=dict(status='PASS',hardware_access=False,processor_simulated=False,fixtures=fixtures,whole_trace_integer_exact=True,source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest()for x in(rtl,bench,stage/'ip/iq_preamble_hw.tcl')},tests=['all_trace_scores_and_best_metrics','zero_CW_noise_wrong_training_lowenergy','host_sequential_CRC_load','physical_CRC_bank_count_source_qualification','sync_Avalon_read_wait','bad_commands_config_bounds_freeze','cancel_reset'])
  result['reference_sha256']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest()for x in(ROOT/'cyberether/preamble_reference.py',ROOT/'scripts/preamble_vectors.py')}
  result['fixture_sha256']={name:{x.name:hashlib.sha256(x.read_bytes()).hexdigest()for x in((out/name/'iq.hex'),(out/name/'scores.hex'),(out/name/'expected.json'))}for name in fixtures}
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
