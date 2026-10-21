#!/usr/bin/env python3
"""Explicit FPGA 64-QAM symbol replay sweep; no UART, radio, or programming.

Output/progress JSON is updated after every bounded on-board chunk.
"""
import argparse,fcntl,json,math,signal,sys,time
from pathlib import Path
import numpy as np
from common import ROOT
sys.path[:0]=[str(ROOT/'cyberether'),str(ROOT/'scripts')]
from nios_fir import NiosFir
from modem_lab import require_modem_checkpoint
from qam64_sweep import NOISE_MODEL,read_snapshot,audit_snapshot,summarize

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');tmp.replace(path)

def run(output, levels=(12,16,20), payload_bits=100000, chunk_frames=16, seed=407):
    if not 256<=payload_bits<=1000000 or not 1<=chunk_frames<=32 or not 1<=len(levels)<=8 or len(set(levels))!=len(levels) or any(not math.isfinite(x) or not 6<=x<=30 for x in levels):
        raise ValueError('Use 256..1000000 bits, 1..32 frames/chunk, and 1..8 unique Es/N0 points between 6..30 dB')
    output=Path(output)
    if (output/'proof.json').exists():raise ValueError('Use a fresh output directory; refusing to replace a measured proof')
    checkpoint=require_modem_checkpoint();rng=np.random.default_rng(seed)
    proof=dict(status='RUNNING',source='Agilex 3 FPGA 64-QAM symbol modem',noise_model=NOISE_MODEL,
               rf_transmitted=False,waveform_synchronization_in_fpga=False,started_at=time.time(),
               image=checkpoint,settings=dict(levels_db=list(levels),target_payload_bits=payload_bits,frame_payload_bits=256,chunk_frames=chunk_frames,seed=seed),rows=[],progress={})
    started=time.monotonic();run_dir=ROOT/'cyberether/run';run_dir.mkdir(parents=True,exist_ok=True)
    try:
        with (run_dir/'rf-link-capture.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # Programming must hold the same lease; recheck after acquiring it.
            checkpoint=require_modem_checkpoint()
            if checkpoint['sha256']!=proof['image']['sha256']:raise RuntimeError('FPGA changed before sweep')
            with NiosFir(pause_monitor=False) as owner:
                if owner.command('MREAD',0)['bits']!=0x4d440601:raise RuntimeError('FPGA modem identity mismatch')
                proof['block_id']='0x4d440601';version=owner.command('MSVERSION')
                if version['version']!=1 or version['payload']!=256:raise RuntimeError('Sweep firmware not installed')
                proof['firmware_version']=version
                for level in levels:
                    sigma=int(round(8192/math.sqrt(2*10**(level/10))))
                    row=dict(esn0_db=level,sigma_q313=sigma,frames=0,payload_bits=0,coded_bits=0,raw_errors=0,decoded_errors=0,encode_cycles=0,decode_cycles=0,clips=0,chunks=[])
                    proof['rows'].append(row);frames=math.ceil(payload_bits/256)
                    while row['frames']<frames:
                        n=min(chunk_frames,frames-row['frames']);chunk_seed=int(rng.integers(1,2**31));t=time.monotonic()
                        r=owner.command('MSRUN',chunk_seed,sigma,n,timeout=90)
                        if r['clips']!=0 or r['verb']!='MSRUN' or (r['frames'],r['payload_bits'],r['coded_bits'])!=(n,n*256,n*524) or r['raw_errors']!=r['raw_audit'] or r['decoded_errors']!=r['decoded_audit'] or not 0<=r['raw_errors']<=r['coded_bits'] or not 0<=r['decoded_errors']<=r['payload_bits']:
                            raise RuntimeError('FPGA counters/chunk lengths failed independent Nios audit')
                        for key in ('frames','payload_bits','coded_bits','raw_errors','decoded_errors','encode_cycles','decode_cycles','clips'):row[key]+=r[key]
                        row['chunks'].append(dict(seed=chunk_seed,frames=n,raw_errors=r['raw_errors'],decoded_errors=r['decoded_errors'],raw_audit=r['raw_audit'],decoded_audit=r['decoded_audit'],counters_verified=True,seconds=time.monotonic()-t))
                        proof['progress']=dict(level_db=level,completed_payload_bits=sum(x['payload_bits'] for x in proof['rows']),total_payload_bits=frames*256*len(levels),elapsed_seconds=time.monotonic()-started)
                        summarize(proof['rows']);save(output/'proof.json',proof)
                        print(json.dumps(proof['progress']),flush=True)
                    snapshot=read_snapshot(owner)
                    audit=audit_snapshot(snapshot,chunk_seed,sigma,n)
                    if audit['raw_errors']>row['chunks'][-1]['raw_errors'] or audit['payload_errors']>row['chunks'][-1]['decoded_errors']:raise RuntimeError('Snapshot error counts exceed chunk counters')
                    row['snapshot_audit']=audit
                    np.savez(output/f'esn0-{level:g}-last-frame.npz',**snapshot)
                    proof['plots']=audit['plots'];proof['plot_level_db']=level;save(output/'proof.json',proof)
                if owner.command('MREAD',1)['bits']&1:raise RuntimeError('FPGA still busy after sweep')
                proof['cleanup']='FPGA idle verified; JTAG released on context exit'
        proof['status']='PASS';proof['completed_at']=time.time();proof['wall_seconds']=time.monotonic()-started
    except BaseException as exc:
        proof['status']='FAIL';proof['error']=str(exc);proof['wall_seconds']=time.monotonic()-started;save(output/'proof.json',proof);raise
    save(output/'proof.json',proof);return proof

if __name__=='__main__':
    def interrupted(*_):raise KeyboardInterrupt('Sweep interrupted; release FPGA/JTAG owner')
    signal.signal(signal.SIGTERM,interrupted)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--levels',type=float,nargs='+',default=[12,16,20]);p.add_argument('--payload-bits',type=int,default=100000);p.add_argument('--chunk-frames',type=int,default=16);p.add_argument('--seed',type=int,default=407);a=p.parse_args()
    result=run(a.output,a.levels,a.payload_bits,a.chunk_frames,a.seed);print(result['status'],a.output/'proof.json')
