"""Experimental original-chip QPSK pulse-frame host reference (not FPGA DSP)."""
import numpy as np
from rf_bpsk import int_bits, crc8, frame_bits, estimate_carrier, _complex, decode
TRAINING = np.array([int(x) for x in '01320312023110233012032120310302'], dtype=np.uint8)
FRAME_SYMBOLS=64
DECODE_SYMBOLS=54  # Guards need not be captured to decode training + body.

def frame_states(payload):
    bits=frame_bits(payload)[16:60].reshape(-1,2)
    states=(bits[:,0]<<1)|(bits[:,0]^bits[:,1])
    return np.r_[TRAINING,states,np.zeros(10,np.uint8)]

def synthesize(payload=165, *,rate=16e6,symbol_us=8.,pulse90_us=2.17,samples=16380,offset_samples=47,cfo_hz=17321.,phase=.7,amplitude=35.,noise_std=1.,seed=1,phase_errors=(0.,0.,0.)):
    """Generated phase ramps only; never an RF capture or firmware upload."""
    sps=round(rate*symbol_us/1e6);states=frame_states(payload);count=samples+offset_samples+sps
    trace=np.zeros(count);level=0.;previous=0
    for start in range(0,count,sps):
        current=int(states[(start//sps)%64]);delta=(current-previous)%4;end=min(count,start+sps)
        pulse=round(rate*pulse90_us*delta/1e6)
        if pulse>=sps: raise ValueError('phase transition must fit symbol')
        if delta:
            angle=-np.pi/2*delta+phase_errors[delta-1]
            trace[start:end]=level+angle*np.minimum(np.arange(end-start)+1,pulse)/pulse;level+=angle
        else: trace[start:end]=level
        previous=current
    rng=np.random.default_rng(seed);z=amplitude*np.exp(1j*(trace+2*np.pi*cfo_hz*np.arange(count)/rate+phase))
    z+=noise_std*(rng.standard_normal(count)+1j*rng.standard_normal(count));z=z[offset_samples:offset_samples+samples]
    return np.clip(np.rint(np.c_[z.real,z.imag]),-128,127).astype(np.int8)

def receive(iq,*,rate=16e6,symbol_us=8.,known_payload=None,expected_payload=None,min_sync=.86,timing_step=4,cfo_search_hz=15000.):
    if expected_payload is not None:
        if known_payload is not None and expected_payload!=known_payload: raise ValueError('conflicting references')
        known_payload=expected_payload
    if known_payload is not None: frame_states(known_payload)
    z=_complex(iq);sps=round(rate*symbol_us/1e6);window=max(2,round(.10*sps))
    if len(z)<DECODE_SYMBOLS*sps or not np.isfinite(z).all() or rate<=0: raise ValueError('need finite complete54symbol training/body capture')
    training=np.exp(-.5j*np.pi*TRAINING);carrier=estimate_carrier(z,rate);time=np.arange(len(z))/rate
    candidates=[];correlation=np.zeros(len(z))
    for residual in np.linspace(-cfo_search_hz,cfo_search_hz,31):
        freq=carrier+residual;mixed=z*np.exp(-2j*np.pi*freq*time);integral=np.r_[0j,np.cumsum(mixed)];averages=(integral[window:]-integral[:-window])/window
        for offset in range(0,sps,timing_step):
            y=averages[offset::sps]
            if len(y)<DECODE_SYMBOLS: continue
            dot=np.correlate(y,training,'valid');energy=np.convolve(abs(y)**2,np.ones(32),'valid');score=abs(dot)/np.sqrt(np.maximum(32*energy,1e-20));locations=offset+np.arange(len(score))*sps;correlation[locations]=np.maximum(correlation[locations],score)
            for start in np.flatnonzero(score[:len(y)-DECODE_SYMBOLS+1]>=min_sync): candidates.append((float(score[start]),offset+int(start)*sps,float(freq)))
    candidates.sort(reverse=True);attempts=[];occupied=[]
    for score,start,freq in candidates:
        if any(abs(start-other)<sps*.75 for other in occupied): continue
        occupied.append(start);ix=start+np.arange(DECODE_SYMBOLS)*sps;sampled=np.array([np.mean(z[i:i+window]*np.exp(-2j*np.pi*freq*time[i:i+window])) for i in ix]);phi=np.unwrap(np.angle(sampled[:32]*np.conj(training)));slope,intercept=np.polyfit(np.arange(32),phi,1,w=np.maximum(abs(sampled[:32]),1e-9));corrected=sampled*np.exp(-1j*(intercept+slope*np.arange(DECODE_SYMBOLS)));corrected/=max(float(np.median(abs(corrected))),1e-12)
        hardstates=np.rint(-np.angle(corrected)/(np.pi/2)).astype(int)%4;sync_errors=int(np.count_nonzero(hardstates[:32]!=TRAINING))
        # Cardinal Gray labels:00 +I,01 -Q,11 -I,10 +Q.
        body=corrected[32:54];llr=np.c_[body.real-body.imag,body.real+body.imag].reshape(-1);decoded=decode(llr);payload=int(np.packbits(decoded[:8])[0]);gotcrc=int(np.packbits(decoded[8:16])[0]);row=dict(start_sample=start,sync_score=score,sync_errors=sync_errors,carrier_hz=float(freq+slope*rate/(2*np.pi*sps)),payload=payload,crc_received=gotcrc,crc_ok=gotcrc==crc8(bytes([payload])),symbols=np.c_[body.real,body.imag].tolist(),coded_llr=llr.tolist(),decoded_bits=decoded.tolist(),coded_errors=None,coded_bits=None,payload_errors=None,payload_bits=None)
        if known_payload is not None: row.update(coded_errors=int(np.count_nonzero((llr<0)!=frame_bits(known_payload)[16:60])),coded_bits=44,payload_errors=int(np.count_nonzero(decoded[:8]!=int_bits(known_payload,8))),payload_bits=8)
        attempts.append(row)
        if len(attempts)>=32: break
    acquired=[x for x in attempts if x['sync_errors']<=2];frames=[x for x in acquired if x['crc_ok']];const=np.array([p for row in acquired for p in row['symbols']]).reshape(-1,2);stride=max(1,len(z)//2048);specstride=max(1,len(z)//1024);spec=abs(np.fft.fftshift(np.fft.fft(z*np.hanning(len(z)))))**2
    return dict(schema='esp32-phase-qpsk-v1',processing='host Python',sample_rate_hz=rate,samples=len(z),capture_seconds=len(z)/rate,symbol_us=symbol_us,carrier_initial_hz=carrier,valid_frames=len(frames),frames=frames,candidates=attempts,acquired_frames=len(acquired),sync_failure=not bool(acquired),acquisition_failures=int(not bool(acquired)),crc_failures=sum(not x['crc_ok'] for x in acquired),known_pattern=known_payload is not None,coded_errors=sum(x['coded_errors'] for x in acquired) if known_payload is not None else None,coded_bits=44*len(acquired) if known_payload is not None else None,payload_errors=sum(x['payload_errors'] for x in acquired) if known_payload is not None else None,payload_bits=8*len(acquired) if known_payload is not None else None,plots=dict(spectrum=dict(x=np.fft.fftshift(np.fft.fftfreq(len(z),1/rate))[::specstride].tolist(),y=(10*np.log10(np.maximum(spec[::specstride],1e-12))).tolist()),raw_iq=dict(i=z.real[::stride].tolist(),q=z.imag[::stride].tolist(),sample=np.arange(len(z))[::stride].tolist()),constellation=dict(i=const[:,0].tolist(),q=const[:,1].tolist()),correlation=dict(x=np.arange(len(z))[::timing_step].tolist(),y=correlation[::timing_step].tolist())),unobserved_gaps='Sparse capture gaps unobserved; no packet delivery ratio inferred.')
