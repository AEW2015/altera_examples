#!/usr/bin/env python3
"""Offline same-capture amplitude/phase engineering audit; no hardware access.

These host fits do not implement the final FPGA modem or qualify arbitrary IQ.
Phase estimates include the entire TX/RX path. Envelope timing is relative to
received threshold crossings, never host/register timestamps.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
from analyze_original_iq_amplitude import samples

def carrier_fit(obs,time,guess,bin_width,state=None):
    def solve(hz,full=False):
        carrier=np.exp(2j*np.pi*hz*time)
        design=np.column_stack((carrier,np.ones(len(time)))) if state is None else np.column_stack((carrier*state,carrier*(1-state),np.ones(len(time))))
        coefficients=np.linalg.lstsq(design,obs,rcond=None)[0]
        error=float(np.mean(abs(obs-design@coefficients)**2))
        return (error,coefficients) if full else error
    center=guess;span=bin_width*1.5
    for _ in range(6):
        grid=np.linspace(center-span,center+span,13);scores=[solve(hz) for hz in grid]
        center=float(grid[int(np.argmin(scores))]);span/=4
    error,coefficients=solve(center,True)
    return center,error,coefficients

def evaluate(z,rate=40000000,expected_abs_offset_hz=0):
    z=np.asarray(z,dtype=complex)
    if z.ndim!=1 or len(z)<1024 or not np.isfinite(z).all():raise ValueError('Finite one-dimensional IQ capture required')
    n=len(z);t=np.arange(n)/rate;radius=abs(z)
    envelope=np.convolve(np.pad(radius,(8,8),mode='edge'),np.ones(17)/17,mode='valid')
    low,high=np.percentile(envelope,[10,90]);threshold=(low+high)/2
    active=envelope>threshold
    result={'two_levels_detected':False,'samples':n,'rate':rate,'smoothing_samples':17,
      'phase_continuity_qualified':False,'arbitrary_iq_verified':False,'qam_qualified':False,
      'phase_scope':'Same-capture end-to-end AM/PM estimate; not isolated TX behavior',
      'timing_scope':'Relative to received 50% envelope crossings; receiver/smoothing limited'}
    freq=np.fft.fftfreq(n,1/rate);power=abs(np.fft.fft(z*np.hanning(n)))**2;band=abs(abs(freq)-expected_abs_offset_hz)<100000
    center=float(freq[np.flatnonzero(band)[np.argmax(power[band])]])
    if high-low<5 or high<1.2*max(low,1e-9):
        center,error,coef=carrier_fit(z,t,center,rate/n)
        rotated=(z-coef[1])*np.exp(-2j*np.pi*center*t)*np.exp(-1j*np.angle(coef[0]))
        result.update(carrier_fit_hz=center,amplitude_adc=float(abs(coef[0])),fit_residual_rms_adc=math.sqrt(error),
                      phase_rms_deg=float(np.sqrt(np.mean(np.angle(rotated)**2)))*180/np.pi)
        return result,envelope,rotated
    edges=np.flatnonzero(np.diff(active)!=0)+1
    boundaries=np.r_[0,edges,n];runs=[];trim=max(1,int(2e-6*rate));stable=np.zeros(n,dtype=bool)
    for start,stop in zip(boundaries[:-1],boundaries[1:]):
        if stop-start<8e-6*rate:continue
        runs.append({'start':int(start),'stop':int(stop),'high':bool(active[(start+stop)//2])})
        stable[start+trim:stop-trim]=True
    if sum(r['high'] for r in runs)<2 or sum(not r['high'] for r in runs)<2:return result,envelope,None
    use=np.flatnonzero(stable);time=t[use];obs=z[use];state=active[use].astype(float)
    center,error,coef=carrier_fit(obs,time,center,rate/n,state);hi,lo,dc=coef
    rotated=(z-dc)*np.exp(-2j*np.pi*center*t)*np.exp(-1j*np.angle(hi))
    phase=np.angle(rotated)*180/np.pi
    widths=np.diff(edges)/rate*1e6
    # Require sustained post-crossing agreement with the destination envelope.
    # This includes RX filtering and the explicit17-sample smoothing window.
    settling=[];hold=max(1,int(1e-6*rate))
    for edge in edges:
        target=high if active[edge] else low;tolerance=max(.05*(high-low),.02*target,1.)
        stop=min(n,int(edge+8e-6*rate))
        inside=abs(envelope[edge:stop]-target)<=tolerance
        if len(inside)<hold:continue
        good=np.convolve(inside.astype(int),np.ones(hold,dtype=int),mode='valid')==hold
        candidates=np.flatnonzero(good)
        if len(candidates):settling.append(float(candidates[0]/rate*1e6))
    delta=float(np.angle(lo/hi)*180/np.pi)
    result.update(two_levels_detected=True,received_edges=int(len(edges)),
      edges_us=(edges/rate*1e6).tolist(),runs=runs,carrier_fit_hz=center,
      high_amplitude_adc=float(abs(hi)),low_amplitude_adc=float(abs(lo)),
      dc_i=float(dc.real),dc_q=float(dc.imag),fit_residual_rms_adc=math.sqrt(error),
      amplitude_ratio=float(abs(lo/hi)),low_relative_phase_deg=delta,
      high_phase_rms_deg=float(np.sqrt(np.mean(phase[stable&active]**2))),
      low_phase_rms_deg=float(np.sqrt(np.mean(np.angle(np.exp(1j*np.deg2rad(phase[stable&~active]-delta)))**2)))*180/np.pi,
      interedge_min_us=float(widths.min()) if len(widths) else None,
      interedge_max_us=float(widths.max()) if len(widths) else None,
      settling_after_crossing_us=settling,
      settling_after_crossing_median_us=float(np.median(settling)) if settling else None)
    return result,envelope,rotated

def load(root,path):
    proof=json.loads(Path(path).read_text())
    if not proof.get('completed') or not proof.get('register_trial_qualified') or proof.get('cleanup_errors') or proof.get('gain')!='GAIN MANUAL 0 0 81 1':raise ValueError('Incomplete or wrong-gain experiment')
    frequency=proof['snapshot']['frequency']
    if frequency not in (2442000000,2447000000,2452000000):raise ValueError('Unexpected RX offset profile')
    z=samples(root,proof,expected_frequency=frequency);result,envelope,rotated=evaluate(z,expected_abs_offset_hz=abs(2447000000-frequency))
    result['rx_nominal_frequency_hz']=frequency
    result.update(proof=str(path),command=proof['command'],analysis_backend='offline host NumPy; FPGA capture transport',host_dsp=True)
    return result,z,envelope,rotated

def plot(rows,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.style.use('dark_background');fig,axes=plt.subplots(len(rows),2,figsize=(12,3.1*len(rows)),squeeze=False)
    for ax,(report,z,envelope,rotated) in zip(axes,rows):
        time=np.arange(len(z))/40
        caption=report['command']+' · RX '+str(report['rx_nominal_frequency_hz']//1000000)+' MHz'
        ax[0].plot(time,envelope,color='#70e5d4',lw=1);ax[0].set(title=caption,xlabel='Time inside this capture (µs)',ylabel='ADC units',ylim=(0,115))
        if rotated is not None:
            phase=np.angle(rotated)*180/np.pi
            ax[1].scatter(time[::8],phase[::8],s=1,c='#ffd083',alpha=.7)
            title=f"Model low/high phase Δ {report['low_relative_phase_deg']:.2f}°" if report['two_levels_detected'] else f"No transitions captured · phase RMS {report['phase_rms_deg']:.2f}°"
            ax[1].set(title=title,xlabel='Time inside this capture (µs)',ylabel='Phase after fitted CFO (degrees)',ylim=(-180,180))
        else:ax[1].text(.5,.5,'Unchanged-code control\nNo two-level transition detected',ha='center',va='center',transform=ax[1].transAxes);ax[1].set_axis_off()
    fig.suptitle('Original ESP32 amplitude transitions · real independent RFS2 captures',fontsize=14)
    fig.text(.5,.01,'Offline host engineering fit · includes TX + RX effects · no custom-QAM / arbitrary-IQ / uniform-clock claim',ha='center',fontsize=9,color='#9db6c0')
    fig.tight_layout(rect=[0,.04,1,.96]);fig.savefig(path,dpi=150);plt.close(fig)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',action='append',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];rows=[load(root,path) for path in a.proof]
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'analysis.json').write_text(json.dumps([r[0] for r in rows],indent=2)+'\n');plot(rows,a.output/'transitions.png')
    print(json.dumps([{k:v for k,v in r[0].items() if k not in ('runs','edges_us','settling_after_crossing_us')} for r in rows],indent=2))
if __name__=='__main__':main()
