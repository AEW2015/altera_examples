#!/usr/bin/env python3
"""Generate/build/program separate checkpoint07: SPI B ingress + FIR II + UART A/RFS2.

Build and simulate never access devices. Program is explicit and requires idle
serial/JTAG owners; hardware qualification is a separate bounded checker action.
"""
import argparse,fcntl,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
from common import ROOT,tool_command,tool_env,tool_exe,tool_path,local_tools
from lessons import fingerprint,stop_demo
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_07_spi_fir'

def build_inputs():
 files=[Path(__file__).resolve(),*sorted((STAGE/'scripts').glob('*.py'))]
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}

def build_command(commands):
 """Native VDS needs X even in Tcl mode; create a private display if needed."""
 display=os.getenv('DISPLAY',':0')
 try:
  available=subprocess.run(tool_command(['xdpyinfo','-display',display],display=display),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0
 except (FileNotFoundError,subprocess.TimeoutExpired):available=False
 if available:return tool_command(['bash','-c',' && '.join(commands)],cwd=STAGE,display=display)
 return tool_command(['xvfb-run','-a','-s','-screen 0 1600x1000x24 -nolisten tcp','bash','-c',' && '.join(commands)],cwd=STAGE)

def build(generate_only=False):
 STAGE.joinpath('run').mkdir(exist_ok=True)
 with (STAGE/'run/build.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  before=fingerprint(STAGE);inputs_before=build_inputs()
  commands=['bash scripts/build_firmware.sh','quartus_sh -t scripts/create_vds.tcl','quartus_sh -t scripts/connect_vds.tcl']
  if not generate_only:commands+=['quartus_sh --flow compile iq_bridge_vds','quartus_sta -t scripts/report_timing.tcl']
  with (STAGE/'run/build.log').open('w') as log:
   subprocess.run(build_command(commands),cwd=STAGE,env=tool_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
  after=fingerprint(STAGE)
  if before!=after or inputs_before!=build_inputs():raise RuntimeError('Authored source or board constraints changed during build; rebuild before reuse')
  if not generate_only:
   fit=(STAGE/'iq_bridge_vds.fit.summary').read_text();sta=(STAGE/'iq_bridge_vds.sta.summary').read_text()
   slacks=[float(x)for x in re.findall(r'Slack : (-?[\d.]+)',sta)]
   if 'Successful' not in fit or not slacks or min(slacks)<0:raise RuntimeError('Fit/timing failed; inspect reports')
   def count(pattern):
    found=re.search(pattern,fit);return int(found[1].replace(',',''))if found else None
   meta=dict(status='PASS_BUILD',source_fingerprint=after,build_inputs_sha256=build_inputs(),sha256=hashlib.sha256((STAGE/'iq_bridge_vds.sof').read_bytes()).hexdigest(),checkpoint=7,device='A3CZ135BB18AE7S',clock_hz=50000000,spi_hz=5000000,minimum_reported_slack_ns=min(slacks),hardware_verified=False,iq_bridge=True,fpga_fir=True,fpga_ddc=False,fpga_gain_meter=False,fpga_modem=False,source2_transport='SPI',radio_transports={'0':'UART','1':'UART','2':'SPI'},spi_proxy_version='00030001',spi_frequency_mhz=2447,spi_rate_hz=16000000,spi_samples=16380,resources=dict(ALMs=count(r'Logic utilization \(in ALMs\) : ([\d,]+)'),M20Ks=count(r'Total RAM Blocks : ([\d,]+)'),DSP_reported=count(r'Total DSP Blocks : ([\d,]+)')))
   (STAGE/'BUILD_RESULT.json').write_text(json.dumps(meta,indent=2)+'\n')
  from quartus_project import export_project
  export_project(STAGE)
 return STAGE/'iq_bridge_vds.qpf'

OWNER_SCAN="""import os
from pathlib import Path
owners=set()
for fds in Path('/proc').glob('[0-9]*/fd'):
 try:files=list(fds.iterdir());cmd=(fds.parent/'cmdline').read_bytes().split(b'\\0')
 except OSError:continue
 if cmd and Path(cmd[0].decode(errors='replace')).name in ('juart-terminal','quartus_pgm','niosv-download','niosv-gdb-server','openocd'):owners.add('JTAG owner '+fds.parent.name)
 for fd in files:
  try:target=os.readlink(fd)
  except OSError:continue
  if target.startswith('/dev/ttyUSB'):owners.add('serial owner '+fds.parent.name+' '+target)
if owners:raise SystemExit('Release devices first: '+', '.join(sorted(owners)))
"""

def program(cable=None):
 image=STAGE/'iq_bridge_vds.sof';manifest=STAGE/'BUILD_RESULT.json'
 if not image.is_file() or not manifest.is_file():raise RuntimeError('Build checkpoint07 before programming')
 meta=json.loads(manifest.read_text())
 if meta.get('checkpoint')!=7 or meta.get('status')!='PASS_BUILD' or meta.get('sha256')!=hashlib.sha256(image.read_bytes()).hexdigest() or meta.get('source_fingerprint')!=fingerprint(STAGE) or meta.get('build_inputs_sha256')!=build_inputs():raise RuntimeError('Checkpoint07 source/image mismatch; rebuild')
 stop_demo()
 run=ROOT/'cyberether/run';run.mkdir(parents=True,exist_ok=True)
 with (run/'rf-link-capture.lock').open('a') as capture_lock:
  fcntl.flock(capture_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  scan=OWNER_SCAN
  subprocess.run([sys.executable,'-c',scan],check=True)
  if not local_tools():subprocess.run(tool_command(['python3','-c',scan]),check=True)
  selected=cable or os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]')
  with (STAGE/'run/program.log').open('w')as log:
   subprocess.run(tool_command([str(tool_exe('quartus_pgm')),'-c',selected,'-m','JTAG','-o','p;'+tool_path(image)+'@1']),stdout=log,stderr=subprocess.STDOUT,check=True)
  meta.update(stage_relative=str(STAGE.relative_to(ROOT)),programmed_unix=time.time(),hardware_verified=False)
  (run/'active-fpga.json').write_text(json.dumps(meta,indent=2)+'\n')
  print('Loaded checkpoint07; verify physical SPI? and same-capture FIR before claiming hardware qualification.')
  return meta

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['generate','build','simulate','program']);p.add_argument('--cable');a=p.parse_args()
 if a.action=='simulate':subprocess.run([sys.executable,str(ROOT/'scripts/simulate_spi_pipeline.py')],check=True)
 elif a.action=='program':program(a.cable)
 else:print(build(a.action=='generate'))
