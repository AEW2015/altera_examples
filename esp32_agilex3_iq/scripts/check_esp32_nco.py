#!/usr/bin/env python3
"""Measure the original ESP32's bounded NCO step probe; no arbitrary-IQ claim.

Requires v2/v3 probe on PMOD A and an IQB1 FPGA hub. No programming or flashing.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir

def state(text):
    d={k:v for k,v in (x.split('=',1) for x in text.split(',')[1:])}
    return {k:int(v,10 if k=='mode12' else 16) for k,v in d.items()}

def verify_controls(before,after,step):
    protected=0xf003fc00|(1<<18)
    for name in ('tone1','tone2'):
        if before[name]&protected!=after[name]&protected:raise ValueError('Tone mode/attenuation/enable changed')
    hires=before['mode12']
    for k,name in enumerate(('tone1','tone2')):
        actual=((after[name]&1023)<<2)|((after['ext']>>(2*k))&3) if hires else after[name]&1023
        if actual!=step:raise ValueError('NCO step readback mismatch')

def spectrum(frame):
    a=frame.iq();z=a[:,0].astype(float)+1j*a[:,1].astype(float)
    w=np.hanning(len(z));p=np.abs(np.fft.fftshift(np.fft.fft(z*w))/w.sum())**2
    f=np.fft.fftshift(np.fft.fftfreq(len(z),1/frame.rate));i=int(np.argmax(p))
    return dict(peak_hz=float(f[i]),peak_db=float(10*np.log10(max(p[i],1e-20))),rail_percent=float(100*np.mean(np.any((a==-128)|(a==127),axis=1)))),f,10*np.log10(np.maximum(p,1e-20))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port');p.add_argument('--output',type=Path,required=True);p.add_argument('--rx-gain',type=int,choices=range(128),metavar='0..127',default=0);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    proof=dict(kind='original ESP32 scalar NCO frequency probe',arbitrary_iq_verified=False,rows=[],completed=False,processing='host FFT; FPGA capture transport')
    spectra=[]
    try:
        with NiosFir(pause_monitor=False)as n:n.command('PAIR',0)
        with Bridge(a.port)as b:
            b.control(2,1,2000000);proof['identity']=b.radio_command(1,'INFO','TX_PROBE,')
            if not proof['identity'].startswith(('TX_PROBE,v=2,','TX_PROBE,v=3,')):raise RuntimeError('NCO requires probe firmware v2/v3')
            proof['receiver']=b.prepare_sdr(0,2447,16000000)
            old=b.radio_command(0,'GAIN?','GAIN ')
            try:
                proof['rx_gain_readback']=b.radio_command(0,f'GAIN MANUAL {a.rx_gain}','OK')
                proof['rx_gain_code']=a.rx_gain
                for step in [0,1,2,4,8,16,32]:
                    b.radio_write(1,f'NCO 8 3000 96 {step}\n')
                    before=state(b.wait_text(1,'NCO_BEFORE,',10));proof['pending_step']=dict(step=step,before=before);after=state(b.wait_text(1,'NCO_STATE,',4))
                    proof['pending_step']['after']=after
                    verify_controls(before,after,step);on=b.wait_text(1,'TX_ON,',4);started=time.monotonic()
                    frames=[];proof['pending_step']['captures']=frames
                    try:
                        for i,frame in enumerate(b.captures(3,0,8192,16000000,pipeline=False)):
                            row,f,db=spectrum(frame);row['transport']=frame.metadata();frames.append(row)
                            (a.output/f'step-{step}-{i}.ci8').write_bytes(frame.payload)
                            if i==2:spectra.append((step,f,db))
                    finally:
                        capture_elapsed=time.monotonic()-started
                        b.radio_write(1,'STOP\n')
                    restored=state(b.wait_text(1,'NCO_RESTORED,',4));off=None
                    # Back-to-back restore/stop/command text can exceed the
                    # hub's telemetry slots. Re-query explicit state; never
                    # infer RF stop solely from an absent event.
                    try:off=b.wait_text(1,'TX_OFF,',.3)
                    except TimeoutError:pass
                    idle=b.radio_command(1,'INFO','TX_PROBE,')
                    quiet=state(b.radio_command(1,'STATE','TONE_STATE,'))
                    if 'busy=0' not in idle or any((quiet[k]>>18)&255 for k in ('tone1','tone2')):
                        raise RuntimeError('Radio did not establish idle with both tones disabled')
                    if restored!=before:raise RuntimeError('Tone registers were not restored')
                    if capture_elapsed>2.5:raise RuntimeError('NCO capture timing invalid')
                    proof['rows'].append(dict(step=step,before=before,after=after,restored=restored,on=on,off=off,stop_event_observed=off is not None,idle_readback=idle,quiet_readback=quiet,capture_elapsed_s=capture_elapsed,captures=frames,hub_status=b.status()))
                    print('step',step,'peak Hz',[r['peak_hz'] for r in frames],flush=True)
                x=np.array([r['step'] for r in proof['rows']]);peaks=np.array([np.median([c['peak_hz'] for c in r['captures']]) for r in proof['rows']]);delta=np.abs(peaks-peaks[0]);grid=160000000/(4096 if proof['rows'][0]['before']['mode12'] else 1024)
                errors=np.abs(delta-x*grid)
                proof.update(completed=True,nominal_step_hz=grid,peak_hz=peaks.tolist(),shift_hz=delta.tolist(),grid_error_hz=errors.tolist(),nco_frequency_verified=bool(np.max(errors)<max(20000,grid*.2) and max(c['rail_percent'] for r in proof['rows'] for c in r['captures'])<1))
            finally:
                b.radio_write(1,'STOP\n');prior=old.split();b.radio_command(0,'GAIN HARDWARE' if prior[1]=='HARDWARE' else 'GAIN MANUAL '+prior[2],'OK')
    except BaseException as error:
        proof['error']=str(error);raise
    finally:(a.output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,2,figsize=(13,4))
    for step,f,db in spectra:ax[0].plot(f/1e6,db,label=str(step),alpha=.8)
    ax[0].set(xlabel='RX offset (MHz)',ylabel='Relative bin power (dB)',title='Real RF: NCO frequency steps');ax[0].legend(title='Raw step',ncol=2)
    ax[1].plot(x,delta/1e3,'o-',label='Measured shift');ax[1].plot(x,x*grid/1e3,'--',label='ROM-derived nominal grid');ax[1].set(xlabel='Raw NCO code',ylabel='Absolute shift from step 0 (kHz)',title='Frequency control qualification');ax[1].legend();fig.tight_layout();fig.savefig(a.output/'nco-evidence.png',dpi=150)
    print(json.dumps({k:v for k,v in proof.items() if k!='rows'},indent=2))
    if not proof['nco_frequency_verified']:raise SystemExit('Frequency shift not qualified; inspect RF and readback evidence.')
if __name__=='__main__':main()
