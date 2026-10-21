#!/usr/bin/env python3
"""Generate reproducible offline detector vectors; never acquires or uploads RF."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from preamble_reference import TRAINING,scan


def synthetic(states=TRAINING,*,samples=5120,sps=128,start=64,amplitude=60,cfo=17000,phase=.4,noise=1,seed=17):
    z=np.zeros(samples,complex)
    for k,state in enumerate(states):z[start+k*sps:start+(k+1)*sps]=amplitude*np.exp(-.5j*np.pi*state)
    z*=np.exp(1j*(phase+2*np.pi*cfo*np.arange(samples)/16e6))
    rng=np.random.default_rng(seed);z+=noise*(rng.standard_normal(samples)+1j*rng.standard_normal(samples))
    return np.clip(np.rint(np.c_[z.real,z.imag]),-128,127).astype(np.int8)


def write_case(directory,name,iq,sps,origin,stride=16):
    out=directory/name;out.mkdir(parents=True,exist_ok=True)
    result=scan(iq,sps=sps,stride=stride)
    words=[((int(q)&255)<<8)|(int(i)&255) for i,q in iq]
    (out/'iq.hex').write_text(''.join(f'{word:04x}\n' for word in words))
    for filename,key,width in [('scores.hex','scores_q15',4),('sum_real.hex','sum_real',8),('sum_imag.hex','sum_imag',8),('energy.hex','differential_energy',16)]:
        mask=(1<<(4*width))-1
        (out/filename).write_text(''.join(f'{int(v)&mask:0{width}x}\n' for v in result[key]))
    result.update(origin=origin,samples=len(iq),sample_format='16bit word: lowbyte signedI, highbyte signedQ',
        iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest())
    (out/'expected.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return dict(name=name,samples=len(iq),sps=sps,stride=stride,candidates=len(result['starts']),best_start=result['best_start'],
        best_score_q15=result['best_score_q15'],best_sum_real=result['best_sum_real'],best_sum_imag=result['best_sum_imag'],
        best_energy=result['best_energy'],detected=result['detected'],origin=origin)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'simulation/preamble')
    p.add_argument('--rf-proof',type=Path);p.add_argument('--rf-index',type=int,default=0)
    args=p.parse_args();rng=np.random.default_rng(23);n=5120
    cases=[('synthetic_cfo',synthetic(),128),('zeros',np.zeros((n,2),np.int8),128),
        ('cw',synthetic(states=np.zeros(32,int),start=0,noise=0),128),
        ('noise',rng.integers(-60,61,(n,2),dtype=np.int8),128),
        ('wrong_training',synthetic(states=TRAINING[::-1]),128),
        ('low_energy',synthetic(amplitude=2,noise=0),128)]
    manifest=[write_case(args.output,name,iq,sps,'Generated software fixture; no RF/hardware execution') for name,iq,sps in cases]
    manifest.append(write_case(args.output,'synthetic_stride4',synthetic(),128,'Generated software fixture; production4sample stride',stride=4))
    manifest.append(write_case(args.output,'exact_span',synthetic(samples=31*128+16,start=0,noise=0),128,'Generated software fixture; exactcomplete32samplewindow span, onecandidate',stride=1))
    if args.rf_proof:
        proof=json.loads(args.rf_proof.read_text())
        if proof.get('kind')!='physical_rf_qpsk':raise ValueError('Physical QPSK proof required')
        row=proof['rows'][args.rf_index]
        if not row['report']['frames']:raise ValueError('Choose a CRC-valid saved capture for positive vector')
        rawpath=args.rf_proof.parent/f'capture-{args.rf_index:03d}.ci8';raw=rawpath.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['transport']['payload_sha256']:raise ValueError('Saved RF raw hash mismatch')
        start=row['report']['frames'][0]['start_sample'];crop=max(0,start-64)
        iq=np.frombuffer(raw,np.int8).reshape(-1,2)[crop:crop+n]
        manifest.append(write_case(args.output,'real_valid',iq,round(row['config']['period_us']*16),
            dict(kind='Previously captured physical RF; offline replay fixture, not new acquisition',proof=str(args.rf_proof),capture=args.rf_index,raw_sha256=row['transport']['payload_sha256'],crop_start=crop,host_start_in_crop=start-crop)))
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
