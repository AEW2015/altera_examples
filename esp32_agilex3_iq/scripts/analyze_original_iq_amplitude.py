#!/usr/bin/env python3
"""Offline engineering audit of saved RF amplitude snapshots; never opens hardware.

Host NumPy metrics are explicitly separate from the display-only-host final FPGA
demo. No phase-continuity, calibrated-power, arbitrary-IQ or QAM claim.
"""
import argparse,hashlib,json,math,zlib
from pathlib import Path
import numpy as np

def samples(root,row):
    archive=row['archive'];meta=row.get('snapshot',row.get('metadata'))
    path=(root/archive['path']).resolve();path.relative_to((root/'cyberether/run').resolve())
    data=path.read_bytes()
    if len(data)!=32760 or meta['samples']!=16380 or meta['source']!=0 or meta['rate']!=40000000 or meta['frequency']!=2447000000 or meta['error']!=0:raise ValueError('Wrong capture profile')
    if hashlib.sha256(data).hexdigest()!=archive['sha256'] or zlib.crc32(data)!=meta['raw_crc']:raise ValueError('Raw integrity mismatch')
    a=np.frombuffer(data,np.int8).reshape(-1,2).astype(float)
    if np.any((a==-128)|(a==127)):raise ValueError('Clipped capture is excluded from amplitude comparison')
    return a[:,0]+1j*a[:,1]

def analyze(root,proof_paths,off_path):
    rows=[];waves=[]
    for path in proof_paths:
        p=json.loads(Path(path).read_text())
        if p.get('kind')!='original ESP32 attenuation hypothesis' or not p.get('completed') or not p.get('register_trial_qualified') or p.get('cleanup_errors') or p.get('gain')!='GAIN MANUAL 0 0 81 1':raise ValueError('Unqualified job / gain mismatch')
        z=samples(root,p);rms=float(np.sqrt(np.mean(abs(z)**2)))
        f=np.fft.fftfreq(len(z),1/40000000);power=abs(np.fft.fft(z*np.hanning(len(z))))**2;band=abs(f)<100000;peak=float(f[np.flatnonzero(band)[np.argmax(power[band])]])
        rows.append({'proof':str(path),'command':p['command'],'rms_adc':rms,'peak_baseband_hz':peak,'rail_components':0});waves.append(z)
    off=json.loads(Path(off_path).read_text())
    if off.get('kind')!='passive RX after amplitude jobs' or not off.get('completed') or off.get('tx_started') is not False or off.get('gain')!='GAIN MANUAL 0 0 81 1':raise ValueError('Wrong passive evidence')
    off_waves=[samples(root,r) for r in off['captures']]
    off_rms=[float(np.sqrt(np.mean(abs(z)**2))) for z in off_waves]
    controls=[r['rms_adc'] for r in rows if r['command'].startswith('CONTROL ')]
    atten=[r['rms_adc'] for r in rows if r['command'].startswith('ATTEN 120 ')]
    ratio=20*math.log10(float(np.median(controls))/float(np.median(atten))) if controls and atten else None
    report={'kind':'offline host audit of independently captured original-chip amplitude RF',
      'host_dsp':True,'live_fpga_dsp':False,'absolute_power_calibrated':False,
      'phase_continuity_qualified':False,'qam_qualified':False,'arbitrary_iq_verified':False,
      'snapshot_alignment':'Separate untriggered snapshots; not a chronological symbol stream',
      'rows':rows,'passive_rms_adc':off_rms,'control_to_code120_total_power_difference_db':ratio,
      'scope':'Total ADC power ratio; not calibrated radiated attenuation or EVM; does not distinguish analog compression'}
    return report,waves,off_waves

def plot(report,waves,off_waves,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.style.use('dark_background')
    fig,ax=plt.subplots(1,2,figsize=(12,4.8));fig.patch.set_facecolor('#071822')
    rows=report['rows'];labels=[r['command'].replace(' 50','') for r in rows]+['TX OFF']
    levels=[r['rms_adc'] for r in rows]+[float(np.median(report['passive_rms_adc']))]
    colors=['#ffd083' if x.startswith('CONTROL') else '#70e5d4' for x in labels[:-1]]+['#8ca6bc']
    ax[0].bar(range(len(levels)),levels,color=colors);ax[0].set_xticks(range(len(levels)),labels,rotation=30,ha='right');ax[0].set_ylabel('Complex RMS · ADC units');ax[0].set_title('Real RF · fixed RX gain code 0')
    for i,value in enumerate(levels):ax[0].text(i,value+1,f'{value:.2f}',ha='center',fontsize=9)
    control=next((i for i,r in enumerate(rows) if r['command'].startswith('CONTROL ')),0)
    atten=next((i for i,r in enumerate(rows) if r['command'].startswith('ATTEN 120 ')),0)
    for z,label,color in [(waves[control],rows[control]['command']+' snapshot','#ffd083'),(waves[atten],rows[atten]['command']+' snapshot','#70e5d4'),(off_waves[0],'TX OFF snapshot','#8ca6bc')]:
        # Radius traces have individual capture origins; phase is not aligned.
        n=800;ax[1].plot(np.arange(n)/40,abs(z[:n]),label=label,color=color,linewidth=.8,alpha=.85)
    ax[1].set(xlabel='Time within each separate snapshot (µs)',ylabel='|I + jQ| · ADC units',title='Separate captures · no phase continuity claim');ax[1].legend(fontsize=8)
    fig.suptitle('Original ESP32 amplitude actuator · independent RFS2 RF capture',fontsize=14)
    fig.text(.5,.01,'Offline host analysis · FPGA capture transport · no custom-QAM or arbitrary-IQ TX claim',ha='center',fontsize=9,color='#9db6c0');fig.tight_layout(rect=[0,.05,1,.94]);fig.savefig(path,dpi=160);plt.close(fig)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,action='append',required=True);p.add_argument('--off',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];report,waves,off=analyze(root,a.proof,a.off)
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');plot(report,waves,off,a.output/'amplitude.png');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
