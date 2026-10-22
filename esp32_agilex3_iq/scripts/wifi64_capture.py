#!/usr/bin/env python3
"""Transport-only reader for the dedicated checkpoint11 Nios receiver app.

Default: inspect WVERSION/WSTATUS, optionally individual cached points/bytes.
Only --decode invokes WRUN on an existing raw RAM capture. Never arms a capture,
programs hardware or transmits. No host FFT, synchronization, demap, FEC or BER.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time
from common import ROOT
from lessons import fingerprint
sys.path.insert(0,str(ROOT/'cyberether'))
from nios_fir import NiosFir
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_11_wifi64_ota'
ACTIVE=ROOT/'cyberether/run/active-fpga.json'
APP_DIR=ROOT/'simulation/wifi64-capture-app'
LOCK=ROOT/'cyberether/run/rf-link-capture.lock'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def artifact_guard():
    """Validate local artifacts/recorded image, not device-read hashes."""
    active=json.loads(ACTIVE.read_text());build=json.loads((STAGE/'BUILD_RESULT.json').read_text())
    sof=STAGE/'iq_bridge_vds.sof'
    if active.get('stage_relative')!=str(STAGE.relative_to(ROOT)):raise RuntimeError('Requires the explicitly loaded checkpoint11 image')
    if build.get('status')!='PASS_BUILD' or build.get('sha256')!=digest(sof) or active.get('sha256')!=build['sha256']:raise RuntimeError('Checkpoint11 SOF/build/active-record hash mismatch')
    if build.get('source_fingerprint')!=fingerprint(STAGE):raise RuntimeError('Checkpoint11 source fingerprint is stale; rebuild explicitly')
    app=json.loads((APP_DIR/'BUILD_RESULT.json').read_text());elf=APP_DIR/'wifi64_capture_app.elf'
    if app.get('status')!='PASS_BUILD' or app.get('stage')!=11 or app.get('ram_bytes')!=262144 or app.get('elf_sha256')!=digest(elf):raise RuntimeError('Dedicated capture-app ELF/build mismatch')
    for name,expected in app.get('files',{}).items():
        path=Path(name);path=path if path.is_absolute() else ROOT/path
        if digest(path)!=expected:raise RuntimeError('Capture-app source fingerprint mismatch: '+name)
    if not app.get('files'):raise RuntimeError('Capture app has no source fingerprint entries')
    hint={'fpga_sof_sha256':build['sha256'],'fpga_source_fingerprint':build['source_fingerprint'],
          'expected_capture_elf_sha256':app['elf_sha256'],'hash_origin':'host artifacts and programming record; not read from FPGA/CPU',
          'device_elf_hash_verified':False}
    marker=ROOT/'cyberether/run/wifi64-capture-app-active.json'
    if marker.exists():
        data=json.loads(marker.read_text());hint['optional_app_marker']={k:data[k] for k in ('elf_sha256','programmed_unix','stage') if k in data}
    return hint

def checked(owner,verb,*args,timeout=12,required=()):
    reply=owner.command(verb,*args,timeout=timeout)
    validate_reply(reply,verb,required)
    return reply

def validate_reply(reply,verb,required=()):
    if reply.get('verb')!=verb:raise RuntimeError('Unexpected Nios command echo for '+verb)
    for name in required:
        if name not in reply or not isinstance(reply[name],int) or isinstance(reply[name],bool):raise RuntimeError('Missing/invalid '+verb+' field '+name)

def rows(owner,verb,count):
    output=[]
    for start in range(0,count,16):
        indices=list(range(start,min(count,start+16)))
        replies=owner.commands([(verb,index) for index in indices],timeout=30)
        if len(replies)!=len(indices):raise RuntimeError('Incomplete '+verb+' batch')
        for index,reply in zip(indices,replies):
            names=('index','i','q','scale') if verb=='WPOINT' else ('index','value','packet_status')
            validate_reply(reply,verb,names)
            if reply['index']!=index:raise RuntimeError('Unexpected '+verb+' index')
            if verb=='WPOINT' and (reply['scale']!=8192 or not -32768<=reply['i']<=32767 or not -32768<=reply['q']<=32767):raise RuntimeError('Invalid device Q13 constellation point')
            if verb=='WBYTE' and not 0<=reply['value']<=255:raise RuntimeError('Invalid decoded byte')
            output.append(reply)
        print(f'{verb}: {len(output)}/{count}',file=sys.stderr,flush=True)
    return output

def run(owner,decode=False,points=(),bytes_=(),timeout=600,proof=None):
    initial={'source':'fpga-capture-ram','processing':'Nios receiver software on Agilex3; host transport/display only',
           'decode_requested':bool(decode),'completed':False,'tx_started':False,'capture_armed':False,
           'raw_iq_transferred_to_host':False,'ber_measured':False,'rf_reception_independently_verified':False,'started_unix':time.time()}
    if proof is None:proof=initial
    else:proof.update(initial)
    version=checked(owner,'WVERSION',required=('version','ram_bytes','timer_base','fir_id','host_dsp'))
    if any(version[key]!=expected for key,expected in {'version':1,'ram_bytes':262144,'timer_base':0x50000,'fir_id':0x46495231,'host_dsp':0}.items()):raise RuntimeError('Wrong dedicated checkpoint11 receiver-app version/platform')
    proof['device_version']=version
    status=checked(owner,'WSTATUS',required=('state','samples','job','source','rate','frequency','raw_crc','ddc_busy','valid','status'))
    proof['initial_status']=status
    if not decode:
        proof['cached_result_provenance']='WSTATUS exposes live capture metadata, not cached decode identity; selected points/bytes are not associated with a new RF capture'
        proof['selected_points']=[];proof['selected_bytes']=[]
        for index in points:
            row=checked(owner,'WPOINT',index,required=('index','i','q','scale'))
            if row['index']!=index or row['scale']!=8192:raise RuntimeError('Unexpected cached WPOINT reply')
            proof['selected_points'].append(row)
        for index in bytes_:
            row=checked(owner,'WBYTE',index,required=('index','value','packet_status'))
            if row['index']!=index or not 0<=row['value']<=255:raise RuntimeError('Unexpected cached WBYTE reply')
            proof['selected_bytes'].append(row)
        proof['completed']=True;proof['finished_unix']=time.time();return proof
    if (status['state']&0x8b)!=2 or status['ddc_busy'] or status['source']!=0 or status['rate']!=40000000 or not 1<=status['samples']<=16380:raise RuntimeError('No ready source0 40-MS/s raw capture; this tool never arms one')
    print('Running existing capture entirely on Nios; waiting for device result...',file=sys.stderr,flush=True)
    result=checked(owner,'WRUN',timeout=timeout,required=('valid','status','stage','accepted','rate_code','mbps','length','points','symbols','packet_status','fcs_crc','received_crc','job','source','rate','frequency','raw_crc','ticks_lo','ticks_hi','clock_hz'))
    proof['device_result']=result
    if result['valid']!=1 or not 0<=result['points']<=480 or not 0<=result['stage']<=5 or result['accepted'] not in (0,1):raise RuntimeError('Invalid device decoder summary')
    if any(result[key]!=status[key] for key in ('job','source','rate','frequency','raw_crc')):raise RuntimeError('Copied-capture identity differs from pre-decode snapshot')
    count=result['length'] if result['stage']>=4 else 0
    if not 0<=count<=256:raise RuntimeError('Device PSDU exceeds qualified decoder capacity')
    proof['constellation']=rows(owner,'WPOINT',result['points'])
    decoded=rows(owner,'WBYTE',count);proof['decoded_bytes']=decoded
    if any(row['packet_status']!=result['packet_status'] for row in decoded):raise RuntimeError('Decoded-byte status changed during transfer')
    proof['decoded_psdu_hex']=bytes(row['value'] for row in decoded).hex()
    final=checked(owner,'WSTATUS',required=('state','job','source','rate','frequency','raw_crc','valid','status'))
    proof['final_status']=final
    if final['valid']!=1 or final['status']!=result['status']:raise RuntimeError('Cached decoder result changed during readout')
    proof['capture_ram_changed_after_copy']=any(final[key]!=result[key] for key in ('job','source','rate','frequency','raw_crc'))
    # Acceptance is device telemetry; failed FCS bytes/points remain in this proof.
    accepted=bool(result['accepted']==1 and result['status']==0 and result['stage']==5 and result['packet_status']==0 and result['rate_code']==12 and result['mbps']==54 and result['fcs_crc']==result['received_crc'] and count>=4)
    if bool(result['accepted'])!=accepted:raise RuntimeError('Inconsistent device acceptance/FCS/header telemetry')
    proof['device_decode_accepted']=accepted
    proof['completed']=True;proof['finished_unix']=time.time();return proof

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--decode',action='store_true',help='explicitly run WRUN on an existing raw capture')
    parser.add_argument('--point',action='append',type=int,default=[],help='inspect a cached point index without running WRUN')
    parser.add_argument('--byte',dest='bytes_',action='append',type=int,default=[],help='inspect a cached decoded byte without running WRUN')
    parser.add_argument('--output',type=Path,required=True,help='new proof JSON; never overwrite')
    parser.add_argument('--timeout',type=float,default=600,help='WRUN device deadline, seconds (1..1800)')
    args=parser.parse_args(argv)
    if not 1<=args.timeout<=1800:parser.error('--timeout must be1..1800seconds')
    if any(not 0<=index<480 for index in args.point) or any(not 0<=index<256 for index in args.bytes_):parser.error('point index0..479; byte index0..255')
    if args.decode and (args.point or args.bytes_):parser.error('--decode reads the full result; --point/--byte are read-only cached inspection')
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump({'completed':False,'status':'reserved-before-device-access'},stream);stream.flush()
            proof={'completed':False,'tx_started':False,'capture_armed':False}
            try:
                hint=artifact_guard();proof['artifact_provenance']=hint;LOCK.parent.mkdir(parents=True,exist_ok=True)
                with LOCK.open('a') as lease:
                    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with NiosFir(pause_monitor=False) as owner:proof=run(owner,args.decode,args.point,args.bytes_,args.timeout,proof=proof)
                proof['artifact_provenance']=hint
            except Exception as exc:proof.update(completed=False,error=str(exc))
            stream.seek(0);json.dump(proof,stream,indent=2);stream.write('\n');stream.truncate()
        print(json.dumps(proof,indent=2));return 0 if proof.get('completed') else 2
    except (OSError,ValueError,RuntimeError) as exc:
        print('wifi64_capture: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
