#!/usr/bin/env python3
"""Regenerate vendor IP, rebuild Nios firmware and compile the selected VDS checkpoints."""
import argparse,concurrent.futures,hashlib,json,re,subprocess,time
from common import ROOT,CONTAINER,container_root,stages

def build(stage):
    out=stage/'run';out.mkdir(exist_ok=True);(stage/'results').mkdir(exist_ok=True);started=time.time();commands=[]
    if(stage/'scripts/build_firmware.sh').exists():commands.append('bash scripts/build_firmware.sh')
    commands+=['quartus_sh -t scripts/create_vds.tcl','quartus_sh -t scripts/connect_vds.tcl']
    if not args.generate_only:commands.append('quartus_sh --flow compile iq_bridge_vds')
    command='export PATH=/opt/altera/quartus/bin:$PATH; '+' && '.join(commands)
    with(out/'build.log').open('w')as log:
        subprocess.run(['docker','exec','-u','dev','-e','DISPLAY='+args.display,'-w',container_root()+'/'+str(stage.relative_to(ROOT)),CONTAINER,'bash','-c',command],stdout=log,stderr=subprocess.STDOUT,check=True)
    if args.generate_only:
        print(stage.name,'PASS generation',flush=True);return dict(status='PASS_GENERATED')
    fit=(stage/'iq_bridge_vds.fit.summary').read_text();sta=(stage/'iq_bridge_vds.sta.summary').read_text();slacks=[float(x)for x in re.findall(r'Slack : (-?[\d.]+)',sta)]
    assert 'Successful'in fit and 'A3CZ135BB18AE7S'in fit and slacks and min(slacks)>=0
    def count(pattern):
        m=re.search(pattern,fit);return int(m[1].replace(',',''))if m else 0
    result=dict(status='PASS_BUILD',device='A3CZ135BB18AE7S',clock_hz=50000000,stage_relative=str(stage.relative_to(ROOT)),sha256=hashlib.sha256((stage/'iq_bridge_vds.sof').read_bytes()).hexdigest(),seconds=round(time.time()-started,2),resources=dict(ALMs=count(r'Logic utilization \(in ALMs\) : ([\d,]+)'),M20Ks=count(r'Total RAM Blocks : ([\d,]+)'),DSP_reported=count(r'Total DSP Blocks : ([\d,]+)')),minimum_reported_slack_ns=min(slacks),hardware_verified=False,iq_bridge=True,fpga_fir=int(stage.name[9:11])>=3,fpga_ddc=int(stage.name[9:11])>=4,fpga_replay_patterns=int(stage.name[9:11])>=4,fpga_gain_meter=int(stage.name[9:11])>=5)
    (stage/'BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(stage.name,'PASS',result['seconds'],'s',flush=True);return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',choices=['all','1','2','3','4','5']);p.add_argument('--jobs',type=int,choices=(1,2),default=2);p.add_argument('--display',default=':93');p.add_argument('--generate-only',action='store_true',help='Rebuild firmware and native VDS/IP without fitting the FPGA');args=p.parse_args();selected=stages()if args.checkpoint=='all'else[stages()[int(args.checkpoint)-1]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs)as pool:list(pool.map(build,selected))
