#!/usr/bin/env python3
"""Explicit hardware test of Wi-Fi primitives on checkpoint06's Nios V.

No radio commands or RF. Temporarily downloads CPU software, then restores the
original boot monitor. The FPGA image is unchanged. Selftest uses offline data.
"""
import argparse,fcntl,hashlib,json,os,queue,shutil,subprocess,threading,time
from pathlib import Path
from common import ROOT,local_tools,tool_exe
from nios_software import software_env

def run(out):
    if not local_tools():raise RuntimeError('Run beside Quartus/Nios tools')
    stage=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem'
    active=json.loads((ROOT/'cyberether/run/active-fpga.json').read_text())
    if active['stage_relative']!=str(stage.relative_to(ROOT)):raise RuntimeError('Requires active checkpoint06')
    built=ROOT/'simulation/wifi64-nios-selftest'
    build=json.loads((built/'BUILD_RESULT.json').read_text())
    for name,digest in build['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Stale selftest source: '+name)
    app=built/'wifi64_selftest.elf';restore=stage/'sw/monitor.elf'
    if hashlib.sha256(app.read_bytes()).hexdigest()!=build['elf_sha256']:raise RuntimeError('Stale selftest ELF')
    if not restore.is_file():raise RuntimeError('Missing rollback monitor ELF')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    env=software_env();proc=None;logs=[]
    proof=dict(source='offline-fixture',processing='Nios V software on Agilex 3',tx_started=False,hardware_tested=False,fpga_sof_sha256=active['sha256'],elf_sha256=build['elf_sha256'])
    def download(path,name):
        cmd=['niosv-download','-c',os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]'),'-d','0','-i','0','-r','-g',str(path)]
        # Downloader requires cable number; resolve exact board identity.
        import re
        listing=subprocess.check_output(['jtagconfig'],env=env,text=True)
        targets=[(m[1],m[2]) for m in re.finditer(r'^(\d+)\) (.+)$',listing,re.M)]
        selected=[n for n,label in targets if cmd[2] in (n,label)]
        if len(selected)!=1:raise RuntimeError('Exact JTAG cable not found')
        cmd[2]=selected[0]
        result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
        (out/(name+'.log')).write_text(result.stdout);result.check_returncode()
    run_dir=ROOT/'cyberether/run'
    with (run_dir/'rf-link-capture.lock').open('a') as rf,(run_dir/'nios-fir.lock').open('a') as ni:
        fcntl.flock(rf,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(ni,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Immutable copies keep measurement identity stable across later builds.
        shutil.copy2(app,out/'tested.elf');shutil.copy2(restore,out/'restore.elf')
        proof['restore_elf_sha256']=hashlib.sha256((out/'restore.elf').read_bytes()).hexdigest()
        try:
            download(out/'tested.elf','download-selftest')
            proc=subprocess.Popen([str(tool_exe('juart-terminal')),'-q','-c',os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]'),'-d','1','-i','0','--no-quit-on-ctrl-d'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            messages=queue.Queue()
            def reader():
                for line in proc.stdout:messages.put(line)
            threading.Thread(target=reader,daemon=True).start()
            deadline=time.monotonic()+60;triggered=False
            while time.monotonic()<deadline:
                try:line=messages.get(timeout=1)
                except queue.Empty:continue
                logs.append(line)
                if 'WIFI64_SELFTEST' in line:print(line.strip(),flush=True)
                if 'WIFI64_SELFTEST,READY,' in line and not triggered:
                    proc.stdin.write('T\n');proc.stdin.flush();triggered=True
                if 'WIFI64_SELFTEST,SUMMARY,' in line:
                    if 'passed=5,total=5' not in line:raise RuntimeError('Nios selftest failed')
                    proof.update(hardware_tested=True,status='PASS_NIOS_PRIMITIVES');break
            else:raise TimeoutError('Nios selftest timeout')
        except BaseException as e:proof['error']=str(e);raise
        finally:
            if proc:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            try:
                download(out/'restore.elf','restore-monitor');proof['monitor_restored']=True
            finally:
                (out/'jtag.log').write_text(''.join(logs));(out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(out)
    return proof
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hardware',action='store_true',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output)
