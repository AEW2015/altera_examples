#!/usr/bin/env python3
"""Generate/build checkpoint06 or control its symbol-rate FPGA modem over Nios JTAG.

Only explicit program() or a caller-provided NiosFir session accesses hardware.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
import numpy as np
from common import ROOT,tool_command,tool_env
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem'
sys.path.insert(0,str(ROOT/'cyberether'))

class ModemFPGA:
    """Use the existing Nios owner; never create a second acquisition session.

    Example: with NiosFir() as owner: modem=ModemFPGA(owner)
    Input is symbol-rate, carrier/timing/gain corrected CI16 Q3.13 IQ, not raw RF.
    """
    def __init__(self,owner):
        self.owner=owner
        if self.read(0)!=0x4d440601:raise RuntimeError('Checkpoint06 modem ID not present')
    def read(self,address):return self.owner.command('MREAD',int(address))['bits']
    def write(self,address,value):
        value=int(value)&0xffffffff
        if value>=0x80000000:value-=0x100000000
        return self.owner.command('MWRITE',int(address),value)
    def wait(self,timeout=15):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            state=self.read(1)
            if state&4:raise RuntimeError('FPGA modem rejected configuration')
            if state&2 and not state&1:return
            time.sleep(.01)
        raise TimeoutError('FPGA modem did not finish')
    def _indexed(self,address,count):
        out=[]
        for i in range(count):self.write(4,i);out.append(self.read(address))
        return out
    def encode(self,bits,bps=2):
        a=np.asarray(bits)
        if a.ndim!=1 or not 1<=len(a)<=256 or not np.isin(a,[0,1]).all():raise ValueError('1..256 binary payload bits required')
        if bps not in (1,2,4,6):raise ValueError('bps must be1,2,4,6')
        self.write(2,bps);self.write(3,len(a))
        for i,b in enumerate(a):self.write(4,i);self.write(5,int(b))
        self.write(1,1);self.wait()
        words=np.asarray(self._indexed(6,self.read(10)),dtype='<u4')
        iq=words.view('<i2').reshape(-1,2).copy()
        coded=np.asarray(self._indexed(7,(len(a)+6)*2),dtype=np.uint8)
        return dict(iq=iq,coded=coded,cycles=self.read(11),origin='FPGA encoder + mapper',sample_scale=8192)
    def decode(self,iq):
        a=np.asarray(iq)
        if a.ndim!=2 or a.shape!=(self.read(10),2) or not np.isfinite(a).all() or not np.equal(a,np.rint(a)).all() or (np.abs(a)>32767).any():raise ValueError('Expected integer CI16 symbol pairs matching encode frame')
        for i,(ri,rq) in enumerate(a.astype(np.int16)):
            self.write(4,i);self.write(6,(int(ri)&65535)|((int(rq)&65535)<<16))
        self.write(1,2);self.wait()
        count=self.read(3)
        bits=np.asarray(self._indexed(9,count),dtype=np.uint8)
        llr=np.asarray(self._indexed(8,(count+6)*2),dtype=np.uint32).view(np.int32)
        return dict(bits=bits,llr=llr,raw_errors=self.read(12),decoded_errors=self.read(13),cycles=self.read(11),origin='FPGA max-log demapper + soft Viterbi')

def _program(cable=None):
    """Explicitly program source-matched checkpoint06; refuse active device owners.

    Stops only this checkout's recorded notebook demo. Other checkouts and
    unrelated serial/JTAG sessions are reported and left running.
    """
    import hashlib
    from lessons import fingerprint,stop_demo
    from notebook_progress import progress
    image=STAGE/'iq_bridge_vds.sof';manifest=STAGE/'BUILD_RESULT.json'
    if not image.is_file() or not manifest.is_file():raise RuntimeError('Build checkpoint06 before programming')
    meta=json.loads(manifest.read_text())
    if meta.get('status')!='PASS_BUILD' or meta.get('sha256')!=hashlib.sha256(image.read_bytes()).hexdigest() or meta.get('source_fingerprint')!=fingerprint(STAGE):
        raise RuntimeError('Checkpoint06 build/image/source mismatch; rebuild before programming')
    stop_demo()
    scan="""import os
from pathlib import Path
owners=set()
for fds in Path('/proc').glob('[0-9]*/fd'):
 try:files=list(fds.iterdir());cmd=(fds.parent/'cmdline').read_bytes().split(b'\\0')
 except OSError:continue
 if cmd and Path(cmd[0].decode(errors='replace')).name in ('juart-terminal','quartus_pgm','niosv-download','niosv-gdb-server','openocd'):owners.add('JTAG owner PID '+fds.parent.name)
 for f in files:
  try:target=os.readlink(f)
  except OSError:continue
  if target.startswith('/dev/ttyUSB'):owners.add('serial owner PID '+fds.parent.name+' ('+target+')')
if owners:raise SystemExit('Release devices before programming: '+', '.join(sorted(owners)))
"""
    subprocess.run([sys.executable,'-c',scan],check=True)
    from common import local_tools,tool_path
    if not local_tools():subprocess.run(tool_command(['python3','-c',scan]),check=True)
    selected=cable or os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]')
    STAGE.joinpath('run').mkdir(exist_ok=True)
    with progress('Program checkpoint06 on '+selected):
        with (STAGE/'run/program.log').open('w')as log:
            subprocess.run(tool_command(['/opt/altera/quartus/bin/quartus_pgm','-c',selected,'-m','JTAG','-o','p;'+tool_path(image)+'@1']),stdout=log,stderr=subprocess.STDOUT,check=True)
    meta.update(stage_relative=str(STAGE.relative_to(ROOT)),iq_bridge=True,fpga_fir=True,fpga_ddc=True,fpga_gain_meter=True,fpga_modem=True,modem_symbol_rate=True,programmed_unix=time.time(),hardware_verified=False)
    run=ROOT/'cyberether/run';run.mkdir(exist_ok=True)
    (run/'active-fpga.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('Loaded checkpoint06:',image)
    return meta

def program(cable=None):
    """Serialize programming with every RF/replay acquisition owner."""
    import fcntl
    run=ROOT/'cyberether/run';run.mkdir(parents=True,exist_ok=True)
    with (run/'rf-link-capture.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _program(cable)


def build(generate_only=False):
    from notebook_progress import progress
    STAGE.joinpath('run').mkdir(exist_ok=True)
    commands=['bash scripts/build_firmware.sh','quartus_sh -t scripts/create_vds.tcl','quartus_sh -t scripts/connect_vds.tcl']
    if not generate_only:commands.append('quartus_sh --flow compile iq_bridge_vds')
    with progress('Generate native modem VDS' if generate_only else 'Build FPGA modem checkpoint06'):
        with (STAGE/'run/build.log').open('w') as log:
            subprocess.run(tool_command(['bash','-c',' && '.join(commands)],cwd=STAGE),cwd=STAGE,env=tool_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
    if not generate_only:
        import hashlib,re
        fit=(STAGE/'iq_bridge_vds.fit.summary').read_text();sta=(STAGE/'iq_bridge_vds.sta.summary').read_text()
        slacks=[float(x)for x in re.findall(r'Slack : (-?[\d.]+)',sta)]
        if 'Successful' not in fit or not slacks or min(slacks)<0:raise RuntimeError('Fit/timing failed; inspect reports')
        from lessons import fingerprint
        def count(pattern):
            found=re.search(pattern,fit)
            return int(found[1].replace(',',''))if found else None
        resources=dict(ALMs=count(r'Logic utilization \(in ALMs\) : ([\d,]+)'),M20Ks=count(r'Total RAM Blocks : ([\d,]+)'),DSP_reported=count(r'Total DSP Blocks : ([\d,]+)'))
        result=dict(source_fingerprint=fingerprint(STAGE),status='PASS_BUILD',resources=resources,fpga_modem=True,modem_symbol_rate=True,checkpoint=6,device='A3CZ135BB18AE7S',clock_hz=50000000,minimum_reported_slack_ns=min(slacks),sha256=hashlib.sha256((STAGE/'iq_bridge_vds.sof').read_bytes()).hexdigest(),hardware_verified=False)
        (STAGE/'BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    from quartus_project import export_project
    export_project(STAGE)
    return STAGE/'iq_bridge_vds.qpf'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['generate','build','simulate','program']);a=p.parse_args()
    if a.action=='simulate':subprocess.run([sys.executable,str(ROOT/'scripts/simulate_modem.py')],check=True)
    elif a.action=='program':program()
    else:print(build(a.action=='generate'))
