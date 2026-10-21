#!/usr/bin/env python3
"""Install a local Atum A3 Nano example in the Quartus New Project Wizard."""
import argparse,datetime,json,shutil,zipfile
from pathlib import Path
from common import ROOT,stages
p=argparse.ArgumentParser();p.add_argument('--quartus-root',default='/opt/altera/quartus');p.add_argument('--install',action='store_true');a=p.parse_args()
r=Path(a.quartus_root)
starter=stages()[0]
if not(starter/'src/vds/iq_bridge_system/iq_bridge_system.vds').exists():raise SystemExit('First run scripts/build.py 1 --generate-only to create the editable starter')
out=ROOT/'board';out.mkdir(exist_ok=True);archive=out/'top.zip'
# Source and IP parameter definitions only; no fitted device or generated HDL.
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED)as z:
 for f in starter.rglob('*'):
  rel=f.relative_to(starter)
  if not f.is_file()or any(x in rel.parts for x in ('gen','qdb','dni','run','results','tmp-clearbox')):continue
  if f.suffix in('.qpf','.qsf','.sdc','.sv','.vds','.ip','.tcl','.py'):z.write(f,'Atum_A3_Nano_IQ_Bridge/'+str(rel))
entry=dict(id='990002',group_id='990002',revision=1,title='Atum A3 Nano IQ Bridge - VDS Education Starter',source='Quartus Prime Pro',category='Board Template',family='Intel Agilex® 3 FPGA',quartus_version='26.1.1',devkit='Terasic Atum A3 Nano',description='Editable raw IQ bridge; five source checkpoints in altera_examples.',rich_description='<p>Atum A3 Nano / A3CZ135BB18AE7S. Six-block native VDS raw-IQ starter. Regenerate from the supplied Tcl scripts before compiling.</p>',documentations=[],ip_cores=[],url='',downloadUrl='par/990002/top.zip',eula_id='',device_part='A3CZ135BB18AE7S',os='')
if a.install:
 catalog=r/'common/board_designs/designs_cat2.json';data=json.loads(catalog.read_text())
 shutil.copy2(catalog,catalog.with_suffix('.json.backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')))
 data['designs']=[x for x in data['designs']if str(x.get('id'))!='990002'];data['designs'].insert(0,entry)
 dest=r/'common/board_designs/par/990002/top.zip';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(archive,dest);catalog.write_text(json.dumps(data,indent=2)+'\n')
print('Prepared board/top.zip'+('; installed, restart Quartus'if a.install else'; add --install with Quartus write access to install'))
