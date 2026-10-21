"""Integer differential QPSK training detector reference, no hardware I/O.

This is coarse synchronization only: no payload demap, FEC or RF phase lock.
Averaging rounds toward negative infinity, exactly like a signed arithmetic
right shift. Default16-sample window and4-sample stride are hardware contracts.
"""
from __future__ import annotations
import numpy as np
from rf_qpsk import TRAINING


def _iq(values):
    a=np.asarray(values)
    if a.ndim!=2 or a.shape[1]!=2 or not np.isfinite(a).all() or np.any(a!=np.floor(a)) or np.any(a < -128) or np.any(a>127):
        raise ValueError('Expected finite signed CI8 integer pairs')
    return a.astype(np.int64)


def transitions(states=TRAINING):
    a=np.asarray(states)
    if a.shape!=(32,) or np.any(a!=np.floor(a)) or np.any(a<0) or np.any(a>3):
        raise ValueError('Exactly32cardinalQPSKstatesrequired')
    # Training state s has phase -pi*s/2. Conjugate expected transition
    # therefore rotates a measured differential product by +pi*delta/2.
    return (np.diff(a.astype(np.int64))&3).tolist()


def evaluate(iq,start,sps=160,window=16,states=TRAINING,min_energy=7936):
    """One candidate; Python integers preserve the FPGA's required bit widths."""
    a=_iq(iq)
    if not isinstance(sps,int) or not 128<=sps<=240 or not isinstance(window,int) or window!=16:
        raise ValueError('sps128..240andwindow16required')
    if not isinstance(start,int) or start<0 or start+31*sps+window>len(a):
        raise ValueError('Complete32-symboltrainingwindowrequired')
    y=np.array([np.sum(a[start+k*sps:start+k*sps+window],axis=0)//window for k in range(32)],np.int64)
    products=[];real=imag=energy=0
    for k,rotation in enumerate(transitions(states)):
        i,q=map(int,y[k]);j,r=map(int,y[k+1])
        dr=j*i+r*q;di=r*i-j*q # y[k+1]*conj(y[k])
        rr,ri=((dr,di),(-di,dr),(-dr,-di),(di,-dr))[rotation]
        real+=rr;imag+=ri;energy+=dr*dr+di*di
        products.append([rr,ri])
    numerator=real*real+imag*imag;denominator=31*energy
    if not isinstance(min_energy,int) or min_energy<0:raise ValueError('Nonnegative integer minimum energy required')
    score=(numerator<<15)//denominator if denominator and energy>=min_energy else 0
    return dict(start=start,score_q15=min(score,32768),score=min(score,32768)/32768.,
        normalized_score_unthresholded=numerator/denominator if denominator else 0.,min_energy=min_energy,energy_pass=energy>=min_energy,
        sum_real=real,sum_imag=imag,differential_energy=energy,numerator=numerator,denominator=denominator,
        averages=y.tolist(),rotated_products=products)


def scan(iq,*,sps=160,window=16,stride=4,threshold_q15=24576,min_energy=7936,states=TRAINING):
    """All complete training windows; stable ranking prefers earlier equal peaks."""
    a=_iq(iq)
    if not isinstance(sps,int) or not 128<=sps<=240 or window!=16:
        raise ValueError('sps128..240andwindow16required')
    if not isinstance(stride,int) or not 1<=stride<=16 or not 0<=threshold_q15<=32768:raise ValueError('Positive stride<=16andQ15thresholdrequired')
    if not isinstance(min_energy,int) or min_energy<0:raise ValueError('Nonnegative integer minimum energy required')
    if len(a)>16384:raise ValueError('Capturemustfit16kcomplexsamples')
    last=len(a)-31*sps-window
    if last<0:raise ValueError('Capturecannotcontaincomplete32-symboltraining')
    # Prefix sums retain exact signed16sample sums; vectorize candidates but
    # retain int64 for every accumulation (bounded <2**40).
    delta=np.asarray(transitions(states));starts=np.arange(0,last+1,stride,dtype=np.int64)
    sums=np.vstack((np.zeros((1,2),np.int64),np.cumsum(a,axis=0,dtype=np.int64)))
    indices=starts[:,None]+np.arange(32)*sps
    y=(sums[indices+window]-sums[indices])//window
    dr=y[:,1:,0]*y[:,:-1,0]+y[:,1:,1]*y[:,:-1,1]
    di=y[:,1:,1]*y[:,:-1,0]-y[:,1:,0]*y[:,:-1,1]
    rr=np.where(delta==0,dr,np.where(delta==1,-di,np.where(delta==2,-dr,di)))
    ri=np.where(delta==0,di,np.where(delta==1,dr,np.where(delta==2,-di,-dr)))
    sr=np.sum(rr,axis=1);si=np.sum(ri,axis=1);energy=np.sum(dr*dr+di*di,axis=1)
    numerator=sr*sr+si*si;denominator=31*energy
    # Full-scale CI8 bounds: numerator/denominator unsigned40 bits, and
    # numerator<<15 unsigned55 bits. Python integers make division exact.
    scores=np.array([min(32768,(int(n)<<15)//int(d)) if d and e>=min_energy else 0 for n,d,e in zip(numerator,denominator,energy)],np.int64)
    rank=np.argsort(-scores,kind='stable');best=int(rank[0])
    return dict(schema='qpsk-differential-preamble-v1',processing='host integer reference; not FPGA execution',
        sps=sps,window=window,stride=stride,threshold_q15=threshold_q15,min_energy=min_energy,
        best_start=int(starts[best]),best_score_q15=int(scores[best]),
        best_sum_real=int(sr[best]),best_sum_imag=int(si[best]),best_energy=int(energy[best]),
        detected=bool(energy[best]>0 and energy[best]>=min_energy and scores[best]>=threshold_q15),
        starts=starts.tolist(),scores_q15=scores.tolist(),ranked_starts=starts[rank].tolist(),
        differential_energy=energy.tolist(),sum_real=sr.tolist(),sum_imag=si.tolist())
