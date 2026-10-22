#!/usr/bin/env python3
"""Explicit checkpoint11 SOF / capture-app / boot-monitor programming.

No default action, automatic build, ESP32 programming, radio command or RF TX.
Only this checkout's recorded notebook demo may be stopped. Unrelated serial or
JTAG owners cause refusal. Programming records are host hints, not device hashes.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from common import ROOT,local_tools,tool_exe
from lessons import stop_demo
from nios_software import software_env
import wifi64_fpga
STAGE=wifi64_fpga.STAGE
RUN=ROOT/'cyberether/run'
ACTIVE=RUN/'active-fpga.json'
APP_MARKER=RUN/'wifi64-capture-app-active.json'
APP_DIR=ROOT/'simulation/wifi64-capture-app'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def source_guard(manifest,base):
    files=manifest.get('files')
    if not isinstance(files,dict) or not files:raise RuntimeError('ELF build has no source hashes')
    for name,expected in files.items():
        path=Path(name);path=path if path.is_absolute() else base/path
        if sha(path)!=expected:raise RuntimeError('ELF build/source hash mismatch: '+name)

def elf_guard(action):
    if action=='capture-app':
        meta=json.loads((APP_DIR/'BUILD_RESULT.json').read_text());elf=APP_DIR/'wifi64_capture_app.elf'
        if meta.get('status')!='PASS_BUILD' or meta.get('stage')!=11 or meta.get('ram_bytes')!=262144 or meta.get('elf_sha256')!=sha(elf):raise RuntimeError('Capture-app build/ELF/platform mismatch')
        source_guard(meta,ROOT);return elf,meta['elf_sha256']
    elf=STAGE/'sw/monitor.elf';meta=json.loads((STAGE/'sw/BUILD_RESULT.json').read_text())
    if meta.get('status')!='PASS' or meta.get('ram_bytes')!=262144 or meta.get('files',{}).get('monitor.elf')!=sha(elf):raise RuntimeError('Checkpoint11 monitor build/ELF/platform mismatch')
    source_guard(meta,STAGE/'sw');return elf,sha(elf)

def owners():
    found=set()
    for fds in Path('/proc').glob('[0-9]*/fd'):
        try:
            paths=list(fds.iterdir());cmd=(fds.parent/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        name=Path(cmd[0].decode(errors='replace')).name if cmd else ''
        if name in ('juart-terminal','quartus_pgm','niosv-download','niosv-gdb-server','openocd'):found.add('JTAG owner PID '+fds.parent.name+' ('+name+')')
        for path in paths:
            try:target=os.readlink(path)
            except OSError:continue
            if target.startswith('/dev/ttyUSB'):found.add('serial owner PID '+fds.parent.name+' ('+target+')')
    return sorted(found)

def resolve_cable(requested,env):
    listing=subprocess.check_output(['jtagconfig'],env=env,text=True,timeout=20)
    cables=[(match[1],match[2].rstrip()) for match in re.finditer(r'^(\d+)\) (.+)$',listing,re.M)]
    matches=[number for number,label in cables if requested==number or requested==label]
    if len(matches)!=1:raise RuntimeError('Exact JTAG cable name/number not found: '+requested)
    return matches[0]

def active_guard(meta):
    active=json.loads(ACTIVE.read_text())
    if active.get('stage_relative')!=str(STAGE.relative_to(ROOT)) or active.get('sha256')!=meta['sha256']:raise RuntimeError('Matching checkpoint11 SOF must be loaded before ELF download')

def write_json(path,data):
    temporary=path.with_name(path.name+'.tmp');temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(path)

def program(action,cable=None):
    # Required first gate: includes frozen build-helper fingerprints as well as
    # RTL/software/source fingerprint, SOF hash, checkpoint and build status.
    meta=wifi64_fpga.check()
    if not local_tools():raise RuntimeError('Run locally beside Quartus/Nios tools; Docker forwarding is not supported')
    if action not in ('fpga','capture-app','monitor'):raise ValueError('Explicit fpga/capture-app/monitor action required')
    elf=None;elf_sha=None
    if action!='fpga':elf,elf_sha=elf_guard(action)
    env=software_env();requested=cable or os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]')
    RUN.mkdir(parents=True,exist_ok=True)
    with (RUN/'rf-link-capture.lock').open('a') as rf,(RUN/'nios-fir.lock').open('a') as nios:
        fcntl.flock(rf,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(nios,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if action!='fpga':active_guard(meta)
        stop_demo()
        held=owners()
        if held:raise RuntimeError('Release devices before programming: '+', '.join(held))
        selected=resolve_cable(requested,env)
        # Recheck frozen inputs after releasing owned viewers and resolving the
        # target, before any programming record is invalidated or hardware write.
        fresh=wifi64_fpga.check()
        if fresh['sha256']!=meta['sha256']:raise RuntimeError('FPGA artifact changed during programming setup')
        if action!='fpga':
            checked_path,checked_sha=elf_guard(action)
            if checked_path!=elf or checked_sha!=elf_sha:raise RuntimeError('ELF changed during programming setup')
        stamp=time.time_ns();record=RUN/('wifi64-program-'+str(stamp)+'.json');log=RUN/('wifi64-program-'+str(stamp)+'.log')
        result={'action':action,'stage':11,'fpga_sha256':meta['sha256'],'elf_sha256':elf_sha,'cable':requested,'cable_index':selected,
                'started_unix':time.time(),'completed':False,'tx_started':False,'device_hash_verified':False,
                'record_origin':'host programming attempt; not device hash readback','log':str(log)}
        if ACTIVE.exists():result['prior_active_record']=json.loads(ACTIVE.read_text())
        write_json(record,result)
        if action=='fpga':
            # A failed/partial SOF programming attempt must not leave a previous
            # stage's active record available to acquisition tools.
            ACTIVE.unlink(missing_ok=True);APP_MARKER.unlink(missing_ok=True)
            command=[str(tool_exe('quartus_pgm')),'-c',selected,'-m','JTAG','-o','p;'+str(STAGE/'iq_bridge_vds.sof')+'@1']
        else:
            APP_MARKER.unlink(missing_ok=True)
            command=['niosv-download','-c',selected,'-d','0','-i','0','-r','-g',str(elf)]
        result['command']=command;write_json(record,result)
        try:
            with log.open('x') as stream:subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
            now=time.time()
            if action=='fpga':
                active=dict(meta,stage_relative=str(STAGE.relative_to(ROOT)),programmed_unix=now,hardware_verified=False)
                write_json(ACTIVE,active)
            else:
                marker={'stage':11,'app':action,'elf_sha256':elf_sha,'fpga_sha256':meta['sha256'],'programmed_unix':now,
                        'device_hash_verified':False,'record_origin':'host successful ELF download; not device hash readback'}
                write_json(APP_MARKER,marker)
            result.update(completed=True,finished_unix=now)
        except Exception as exc:
            result.update(error=str(exc),finished_unix=time.time());write_json(record,result);raise
        write_json(record,result);print(json.dumps(result,indent=2));return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('fpga','capture-app','monitor'));p.add_argument('--cable');args=p.parse_args(argv)
    try:program(args.action,args.cable);return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print('program_wifi64: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
