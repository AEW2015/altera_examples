#!/usr/bin/env python3
"""Offline paired audit of saved physical captures; never changes live DSP.

Re-acquire without a payload reference. The experimental estimator uses only
known sync transitions to estimate pulse centres and a quiet-window sampling
phase. Payload references are read only after independent decoding to count BER.
This replays existing captures, not new RF evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from rf_bpsk import receive,int_bits,frame_bits,crc8,decode


def refine(iq,frame,*,rate=16e6,symbol_us=8,fit_period=False):
    """Training-only transition centroid fit, followed by independent Viterbi."""
    z=iq[:,0].astype(float)+1j*iq[:,1].astype(float);sps=rate*symbol_us/1e6
    marker=int_bits(0x0651,16);time=np.arange(len(z))/rate
    mixed=z*np.exp(-2j*np.pi*frame['carrier_hz']*time)
    lag=max(1,round(.5e-6*rate));derivative=np.angle(mixed[lag:]*np.conj(mixed[:-lag]));ks=[];centres=[]
    for k in np.flatnonzero(marker[1:]!=marker[:-1])+1:
        centre=frame['start_sample']+k*sps-.42*sps;lo=max(0,round(centre-.30*sps));hi=min(len(derivative),round(centre+.30*sps)+1)
        weights=np.maximum(abs(derivative[lo:hi])-.1,0)
        if weights.sum()>0:
            ks.append(k);centres.append(float(np.dot(np.arange(lo,hi)+lag/2,weights)/weights.sum()))
    if len(ks)<5: return None
    period,intercept=np.polyfit(ks,centres,1)
    residual=float(np.max(abs(np.array(centres)-np.polyval([period,intercept],ks))))
    if abs(period/sps-1)>.015 or residual>4: return None
    if not fit_period:
        period=sps;intercept=float(np.mean(np.array(centres)-np.array(ks)*sps))
    # Pulse centre plus half a symbol is the centre of the following quiet
    # interval, independent of pulse width. Average symmetric samples there.
    width=max(2,round(.16*sps));ix=np.rint(intercept+np.arange(64)*period+sps/2-width/2).astype(int)
    if ix.min()<0 or ix.max()+width>len(z): return None
    sampled=np.array([mixed[i:i+width].mean() for i in ix]);sync=1.-2.*marker
    slope,phase=np.polyfit(np.arange(16),np.unwrap(np.angle(sampled[:16]*sync)),1,w=np.maximum(abs(sampled[:16]),1e-9))
    corrected=sampled*np.exp(-1j*(phase+slope*np.arange(64)));llr=corrected[16:60].real;decoded=decode(llr);payload=int(np.packbits(decoded[:8])[0]);crc=int(np.packbits(decoded[8:16])[0]);sync_errors=int(np.count_nonzero((corrected[:16].real<0)!=marker))
    return dict(payload=payload,crc_ok=crc==crc8(bytes([payload])),sync_errors=sync_errors,coded_llr=llr.tolist(),decoded_bits=decoded.tolist(),period=period,training_fit_residual=residual,start_sample=int(ix[0]))


def measure(frame,payload):
    acquired=frame['sync_errors']<=1
    return dict(acquired=int(acquired),crc_valid=int(acquired and frame['crc_ok']),coded_errors=int(np.count_nonzero((np.array(frame['coded_llr'])<0)!=frame_bits(payload)[16:60])) if acquired else 0,coded_bits=44 if acquired else 0,payload_errors=int(np.count_nonzero(np.array(frame['decoded_bits'])[:8]!=int_bits(payload,8))) if acquired else 0,payload_bits=8 if acquired else 0)


def audit(directories):
    output=dict(kind='offline_same_capture_bpsk_timing_comparison',new_rf_captures=0,rows=[])
    for directory in directories:
        directory=directory.resolve()
        proof=json.loads((directory/'proof.json').read_text())
        if proof['kind']!='physical_rf_bpsk': raise ValueError('only actual BPSK RF captures accepted')
        for index,row in enumerate(proof['rows']):
            path=directory/f'capture-{index:03d}.ci8';raw=path.read_bytes();iq=np.frombuffer(raw,np.int8).reshape(-1,2)
            # No known payload enters acquisition or refinement.
            report=receive(iq,symbol_us=row['config']['period_us']);payload=row['config']['payload']
            item=dict(capture=str(path.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest(),acquisition_failure=report['acquisition_failures'],frames=[])
            for frame in report['candidates']:
                if frame['sync_errors']>1: continue
                refinements={}
                for name,fit in [('fixed_period',False),('training_period',True)]:
                    new=refine(iq,frame,symbol_us=row['config']['period_us'],fit_period=fit)
                    refinements[name]=dict(accepted=new is not None,metrics=measure(new,payload) if new is not None else None,estimated_period=new['period'] if new else None)
                item['frames'].append(dict(baseline=measure(frame,payload),variants=refinements))
            output['rows'].append(item)
    output['totals']={}
    for variant in ['baseline','fixed_period','training_period']:
        totals=dict(captures=len(output['rows']),acquisition_failures=sum(r['acquisition_failure'] for r in output['rows']),refinement_rejections=0,acquired=0,crc_valid=0,coded_errors=0,coded_bits=0,payload_errors=0,payload_bits=0)
        for row in output['rows']:
            for frame in row['frames']:
                measured=frame['baseline'] if variant=='baseline' else frame['variants'][variant]['metrics']
                if measured is None: totals['refinement_rejections']+=1;continue
                for key,value in measured.items():totals[key]+=value
        totals['crc_failures']=totals['acquired']-totals['crc_valid']
        totals['sync_rejections']=sum(len(r['frames']) for r in output['rows'])-totals['refinement_rejections']-totals['acquired']
        output['totals'][variant]=totals
    output['conclusion']='Experimental variants are offline replay only; no live decoder change authorized by this audit.'
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directories',nargs='+',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();result=audit(args.directories);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['totals'],indent=2))
if __name__=='__main__':main()
