#!/usr/bin/env python3
"""Incremental RF amplitude calibration using the installed combined image.

RF jobs require --transmit. Each candidate follows an unchanged-code control;
only measured, qualified levels permit the next eight-code increment. Saved IQ
is audited on the host for engineering calibration, not final FPGA modem DSP.
No programming, reset buttons, arbitrary IQ or custom QAM qualification.
"""
import argparse,fcntl,hashlib,json,math,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from common import ROOT
from analyze_original_iq_transitions import load

def assess(report,control=False,reference=None):
    """Conservative measurement gates; all amplitudes are uncalibrated ADC units."""
    names=('amplitude_adc','phase_rms_deg','fit_residual_rms_adc') if control else ('high_amplitude_adc','low_amplitude_adc','amplitude_ratio','fit_residual_rms_adc')
    if report.get('two_levels_detected') or control:
        if any(not isinstance(report.get(k),(int,float)) or not math.isfinite(report[k]) for k in names):return 'nonfinite_or_missing_measurement'
    if control:
        if report.get('two_levels_detected'):return 'control_has_unexpected_levels'
        amp=report.get('amplitude_adc',0)
        if not 50<=amp<=110:return 'control_headroom_or_signal'
        if report.get('phase_rms_deg',999)>8 or report.get('fit_residual_rms_adc',999)>8:return 'control_fit_quality'
        return None
    if not report.get('two_levels_detected'):return 'sparse_capture_missed_transitions'
    hi=report.get('high_amplitude_adc',0);lo=report.get('low_amplitude_adc',0)
    if not reference or not .85*reference<=hi<=1.15*reference:return 'reference_amplitude_changed'
    if lo<8:return 'weak_level_not_qualified'
    if report.get('fit_residual_rms_adc',999)>max(5,.12*hi):return 'fit_residual'
    if not 0<report.get('amplitude_ratio',0)<1:return 'unexpected_gain_ratio'
    return None

def summarize(rows):
    levels=[]
    for code in sorted({r['code'] for r in rows if r.get('qualified')}):
        group=[r['measurement'] for r in rows if r['code']==code and r.get('qualified')]
        ratios=np.array([r['amplitude_ratio'] for r in group])
        phases=np.array([r['low_relative_phase_deg'] for r in group])
        levels.append({'code':code,'qualified_captures':len(group),'ratio_mean':float(ratios.mean()),'ratio_min':float(ratios.min()),'ratio_max':float(ratios.max()),
                       'relative_db':float(20*np.log10(ratios.mean())),'phase_mean_deg':float(np.angle(np.mean(np.exp(1j*np.deg2rad(phases))))*180/np.pi)})
    return {'levels':levels,'host_dsp':True,'scope':'End-to-end TX/RX engineering fit; not isolated TX AM/PM or an applied calibration LUT',
            'custom_qam_qualified':False,'phase_continuity_qualified':False,'absolute_power_calibrated':False}

def render(report,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    summary=summarize(report['observations']);report['summary']=summary
    if not summary['levels']:return
    plt.style.use('dark_background');fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    levels=summary['levels'];codes=[r['code'] for r in levels];means=np.array([r['ratio_mean'] for r in levels])
    errors=np.array([[r['ratio_mean']-r['ratio_min'] for r in levels],[r['ratio_max']-r['ratio_mean'] for r in levels]])
    axes[0].errorbar(codes,means,yerr=errors,fmt='o-',color='#70e5d4',capsize=4)
    for squared in (2,10,18,26,34,50,58,74,98):axes[0].axhline(math.sqrt(squared/98),color='#ffd083',alpha=.18,lw=1)
    axes[0].set(xlabel='Measured attenuation code',ylabel='Amplitude relative to same-capture high level',ylim=(0,1.08),title='Measured amplitude • required 64-QAM radii in gold')
    axes[1].plot(codes,[r['phase_mean_deg'] for r in levels],'o-',color='#ffd083')
    axes[1].set(xlabel='Measured attenuation code',ylabel='Low / high model phase difference (degrees)',title='Includes TX, RX and fitting effects')
    fig.suptitle('Original ESP32 RF calibration • independent RFS2 raw captures')
    fig.text(.5,.02,'Offline host engineering analysis • FPGA capture transport • custom QAM and phase continuity remain unqualified',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.06,1,.94]);temp=output/'amplitude-calibration.tmp.png';fig.savefig(temp,dpi=150);plt.close(fig);temp.replace(output/'amplitude-calibration.png')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transmit',action='store_true',required=True)
    p.add_argument('--hours',type=float,default=3);p.add_argument('--spacing-seconds',type=float,default=90)
    p.add_argument('--max-code',type=int,choices=range(24,121,8),default=120);p.add_argument('--repeats',type=int,choices=range(2,6),default=3)
    p.add_argument('--port',default='/dev/ttyUSB0');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not 0<a.hours<=6 or not 3<=a.spacing_seconds<=600:p.error('hours >0..6; spacing 3..600 seconds')
    output=a.output.resolve();output.relative_to((ROOT/'cyberether/run').resolve());output.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'state':'running','started_unix':time.time(),'hours':a.hours,'observations':[],'controls':[],'native_checks':[],'calibration_state':'running','max_code':a.max_code,'repeats':a.repeats}
    report['source_sha256']={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ('tx_lab_calibration.py','tx_lab_control.py','original_iq_control.py','analyze_original_iq_transitions.py')}
    started=time.monotonic();deadline=started+a.hours*3600;sequence=0;logs=[];report['commands']=logs
    def save():
        report['updated_unix']=time.time();temp=output/'status.tmp';temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(output/'status.json')
    def run(script,*args):
        nonlocal sequence
        sequence+=1;log=output/f'command-{sequence:03d}.log';entry={'script':script,'args':list(map(str,args)),'log':log.name,'started_unix':time.time()};logs.append(entry);save()
        env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        with log.open('x') as stream:result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
        entry['returncode']=result.returncode;save()
        if result.returncode:raise RuntimeError(script+' failed; inspect '+log.name)
    def mode(selected):run('tx_lab_control.py','--port',a.port,'--mode',selected)
    def capture(code,name,initialize=False,delay=10):
        target=output/(name+'.json')
        args=['--transmit','--port',a.port,'--rx-gain',0,'--expect-mac','78:21:84:d4:4f:98','--milliseconds',50 if initialize else 30,'--capture-delay-ms',delay,'--output',target]
        if not initialize:args+=['--level',code,'--train-period-us',64]
        run('original_iq_control.py',*args)
        proof=json.loads(target.read_text())
        if not proof.get('completed') or proof.get('cleanup_errors'):raise RuntimeError('Capture cleanup failed')
        if initialize:return None
        measurement,*_=load(ROOT,target);return measurement
    def native(index):
        mode('PHASE');mode('NATIVE');target=output/f'native-{index:03d}.json'
        run('wifi64_ota.py','--transmit','--port',a.port,'--channel',11,'--count',2,'--power',8,'--gap',2,'--run',(int(report['started_unix'])+index)&0xffffffff,'--output',target)
        proof=json.loads(target.read_text());report['native_checks'].append({'proof':str(target.relative_to(ROOT)),'completed':proof.get('completed'),'qualified_packets':proof.get('monitor',{}).get('qualified_packets')});save();mode('AMP')
    lease=(ROOT/'cyberether/run/tx-lab-orchestration.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    save()
    try:
        native(0);capture(0,'initialization',True);time.sleep(3)
        previous=1.;native_index=1;next_native=started+1200
        for code in range(24,a.max_code+1,8):
            if time.monotonic()>=deadline:report['calibration_state']='time_limit';break
            control=capture(0,f'code-{code:03d}-control');report['controls'].append(control)
            error=assess(control,control=True)
            if error:raise RuntimeError(error)
            reference=control['amplitude_adc'];good=[]
            for attempt in range(a.repeats+2):
                if time.monotonic()>=deadline:break
                time.sleep(3)
                measurement=capture(code,f'code-{code:03d}-attempt-{attempt:02d}',delay=(7,11,17,5,13,9,15)[attempt%7])
                error=assess(measurement,reference=reference)
                row={'code':code,'attempt':attempt,'measurement':measurement,'qualified':error is None,'rejection':error};report['observations'].append(row)
                if error is None:good.append(measurement['amplitude_ratio'])
                render(report,output);save()
                if error in ('reference_amplitude_changed','unexpected_gain_ratio'):raise RuntimeError(error)
                if len(good)>=a.repeats:break
                # Sparse coverage gets a bounded number of attempts, never a
                # relabelled or spliced synthetic transition.
                time.sleep(a.spacing_seconds)
            if len(good)<a.repeats:report['calibration_state']='gated_incomplete_measurement';report['gated_code']=code;break
            ratio=float(np.mean(good))
            if ratio>previous+.05 or ratio<previous*.5:report['calibration_state']='gated_transfer_discontinuity';report['gated_code']=code;break
            previous=ratio
            if time.monotonic()>=next_native:
                native(native_index);native_index+=1;next_native=time.monotonic()+1200
                capture(0,f'initialization-{native_index:03d}',True);time.sleep(3)
            remaining=deadline-time.monotonic()
            if remaining>0:time.sleep(min(a.spacing_seconds,remaining))
        else:report['calibration_state']='planned_levels_measured'
        # Calibration gates halt new candidate codes. Independent known native
        # Wi-Fi checks may continue; no PHASE RF jobs are scheduled.
        mode('AMP');save()
        while time.monotonic()<deadline:
            if time.monotonic()>=next_native:
                native(native_index);native_index+=1;next_native=time.monotonic()+1200
            time.sleep(min(30,max(0,deadline-time.monotonic())))
        report['state']='finished'
    except BaseException as error:report.update(state='stopped',error=str(error))
    finally:
        try:mode('AMP');report['final_rf_off_verified']=True
        except BaseException as error:report['cleanup_error']=str(error);report['state']='stopped'
        render(report,output);report['finished_unix']=time.time();save();lease.close()
    print(json.dumps(report,indent=2));return 0 if report['state']=='finished' else 2
if __name__=='__main__':raise SystemExit(main())
