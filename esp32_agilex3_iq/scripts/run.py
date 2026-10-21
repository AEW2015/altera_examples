#!/usr/bin/env python3
"""Load checkpoint 5 or run its browser lab; never stops another checkout's demo."""
import argparse,hashlib,json,os,subprocess,sys
from common import ROOT,CONTAINER,container_root,env,stages
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('load','serve'));p.add_argument('--host',default='127.0.0.1');a=p.parse_args();stage=stages()[-1]
if a.action=='load':
    build=stage/'BUILD_RESULT.json'
    if not build.exists():p.error('Run scripts/build.py 5 first')
    meta=json.loads(build.read_text());image=stage/'iq_bridge_vds.sof'
    if meta['status']!='PASS_BUILD'or hashlib.sha256(image.read_bytes()).hexdigest()!=meta['sha256']:p.error('Build/image identity mismatch')
    # Scan both PID namespaces. Refuse to reprogram an active acquisition owner.
    scan='''import os,sys
from pathlib import Path
for p in Path('/proc').glob('[0-9]*/fd'):
 try:files=list(p.iterdir())
 except OSError:continue
 for f in files:
  try:t=os.readlink(f)
  except OSError:continue
  if t.startswith('/dev/ttyUSB'):raise SystemExit('Stop serial owner PID '+p.parent.name+' before programming')
'''
    subprocess.run([sys.executable,'-c',scan],check=True)
    subprocess.run(['docker','exec',CONTAINER,'python3','-c',scan],check=True)
    cable=os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]')
    subprocess.run(['docker','exec','-u','dev',CONTAINER,'/opt/altera/quartus/bin/quartus_pgm','-c',cable,'-m','JTAG','-o','p;'+container_root()+'/'+str(image.relative_to(ROOT))+'@1'],check=True)
    r=ROOT/'cyberether/run';r.mkdir(exist_ok=True);(r/'active-fpga.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('Loaded checkpoint 5. Every live result is checked against its independent integer reference.')
else:
    if not(ROOT/'cyberether/run/active-fpga.json').exists():p.error('Load checkpoint 5 first')
    args=[str(ROOT/'.venv-notebooks/bin/python'),str(ROOT/'cyberether/start_iq_bridge_lab.py'),'--host',a.host]
    os.execve(args[0],args,env())
