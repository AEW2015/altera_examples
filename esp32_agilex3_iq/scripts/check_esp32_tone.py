#!/usr/bin/env python3
"""Observe a bounded original-ESP32 tone using a second installed receiver.

Requires the normal IQB1 FPGA hub and explicitly flashed TX probe on Pmod A.
Never programs firmware/FPGA. All display FFT/power calculations run on host.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir

def metrics(iq,rate,offset_hz=5e6):
    z=iq[:,0].astype(float)+1j*iq[:,1].astype(float)
    w=np.hanning(len(z)); p=np.abs(np.fft.fftshift(np.fft.fft(z*w))/w.sum())**2
    f=np.fft.fftshift(np.fft.fftfreq(len(z),1/rate))
    # Test both IQ signs; original-chip IQ orientation is not assumed.
    band=np.abs(np.abs(f)-offset_hz)<150000
    tone=float(np.sum(p[band]))
    return dict(relative_band_db=float(10*np.log10(max(tone,1e-20))),
        rail_percent=float(100*np.mean(np.any((iq==-128)|(iq==127),axis=1))),
        peak_offset_hz=float(f[np.flatnonzero(band)[np.argmax(p[band])]])),f,10*np.log10(np.maximum(p,1e-20))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port');p.add_argument('--tx-source',type=int,choices=[1,2],default=1)
    p.add_argument('--rx-source',type=int,choices=[0,1,2],default=0)
    p.add_argument('--channel',type=int,choices=range(2,12),default=3)
    p.add_argument('--backoff-qdb',type=int,choices=range(80,121),default=96)
    p.add_argument('--automatic-stop',action='store_true',help='Observe the three-second firmware deadline instead of issuing STOP after capture')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.tx_source==a.rx_source:p.error('TX and RX must be different radios')
    a.output.mkdir(parents=True,exist_ok=False)
    tx_mhz=2412+5*(a.channel-1); rx_mhz=tx_mhz-5
    proof=dict(kind='physical original ESP32 bounded CW test',arbitrary_iq_verified=False,
        tx_source=a.tx_source,rx_source=a.rx_source,tx_mhz=tx_mhz,rx_mhz=rx_mhz,
        backoff_qdb=a.backoff_qdb,automatic_stop=a.automatic_stop,spectrum_backend='host numpy FFT',rows=[],completed=False)
    spectra={};host_start=time.monotonic()
    try:
        with NiosFir(pause_monitor=False) as n:
            proof['fpga_control']=n.command('PAIR',0)
        with Bridge(a.port) as b:
            b.control(2,a.tx_source,2000000)
            proof['tx_identity']=b.radio_command(a.tx_source,'INFO','TX_PROBE,')
            proof['rx_identity']=b.prepare_sdr(a.rx_source,rx_mhz,16000000)
            proof['rx_gain_before']=b.radio_command(a.rx_source,'GAIN?','GAIN ')
            try:
                b.radio_command(a.rx_source,'GAIN MANUAL 20','OK')
                proof['rx_gain']=b.radio_command(a.rx_source,'GAIN?','GAIN ')
                if not proof['rx_gain'].startswith('GAIN MANUAL 20 '):
                    raise RuntimeError('Receiver gain readback does not match the fixed test gain')
                def collect(label,count):
                    levels=[]
                    for i,frame in enumerate(b.captures(count,a.rx_source,8192,16000000,pipeline=False)):
                        row,f,db=metrics(frame.iq(),frame.rate)
                        row.update(phase=label,index=i,host_elapsed_s=time.monotonic()-host_start,transport=frame.metadata())
                        proof['rows'].append(row);levels.append(row['relative_band_db'])
                        (a.output/f'{label}-{i}.ci8').write_bytes(frame.payload)
                        spectra[label]=(f,db)
                        print(label,json.dumps(row),flush=True)
                    return float(np.median(levels))
                b.radio_command(a.tx_source,'STOP','STOP_REQUESTED,');time.sleep(.1)
                off=collect('before',4)
                b.radio_write(a.tx_source,f'TONE {a.channel} 3000 {a.backoff_qdb}\n')
                proof['on_ack']=b.wait_text(a.tx_source,'TX_ON,',10)
                t_on=time.monotonic()
                try:on=collect('during',4)
                finally:
                    if not a.automatic_stop:b.radio_write(a.tx_source,'STOP\n')
                proof['during_collection_s']=time.monotonic()-t_on
                proof['off_ack']=b.wait_text(a.tx_source,'TX_OFF,',5)
                expected_reason='deadline' if a.automatic_stop else 'stop'
                if 'reason='+expected_reason not in proof['off_ack']:
                    raise RuntimeError('Tone stop reason differs from the requested test')
                time.sleep(.15)
                after=collect('after',4)
                proof.update(before_db=off,during_db=on,after_db=after,rise_db=on-off,
                    fall_db=on-after,completed=True,
                    tone_observed=bool(on-off>=6 and on-after>=6 and proof['during_collection_s']<2.5
                        and max(r['rail_percent'] for r in proof['rows'])<1))
            finally:
                b.radio_write(a.tx_source,'STOP\n')
                original=proof['rx_gain_before'].split()
                restore='GAIN HARDWARE' if original[1]=='HARDWARE' else 'GAIN MANUAL '+original[2]
                proof['rx_gain_restored']=b.radio_command(a.rx_source,restore,'OK')
    finally:
        (a.output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,2,figsize=(12,4))
    for phase,(f,db) in spectra.items():ax[0].plot(f/1e6,db,label=phase,alpha=.8)
    ax[0].set(xlabel='Offset from RX tuning (MHz)',ylabel='Relative FFT bin power (dB)',title='Physical RF captures · host FFT')
    ax[0].legend()
    colors={'before':'gray','during':'orange','after':'royalblue'}
    for phase in colors:
        rows=[r for r in proof['rows'] if r['phase']==phase]
        ax[1].scatter([r['host_elapsed_s'] for r in rows],[r['relative_band_db'] for r in rows],c=colors[phase],label=phase)
    ax[1].set(xlabel='Host receipt time (s)',ylabel='Relative ±5 MHz band power (dB)',title='On/off evidence · fixed RX gain')
    ax[1].legend();fig.tight_layout();fig.savefig(a.output/'tone-evidence.png',dpi=150)
    print(json.dumps({k:v for k,v in proof.items() if k!='rows'},indent=2))
    if not proof['tone_observed']:raise SystemExit('Tone not qualified: inspect evidence; no arbitrary-IQ claim.')
if __name__=='__main__':main()
