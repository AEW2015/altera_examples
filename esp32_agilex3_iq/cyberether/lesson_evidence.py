"""Lesson evidence and explicitly offline previews. No device access on import/call."""
import time
import numpy as np
from nios_fir import PROFILES, fixed_reference
import nios_ddc
from iq_lab_samples import load_sample

NAMES={1:'Raw IQ bridge',2:'Nios V transfer monitor',3:'FIR II filter',4:'Frequency translation / decimation',5:'Gain / power meters'}
# TEST 2's literal 32-word sequence in the checkpoint-3 capture RTL.
FIR_WORDS=[0x2030,0x4f06,0x1edc,0xeb12,0x1747,0x421b,0x0cee,0xd61f,
 0x0050,0x2a1f,0xf4ee,0xbe1b,0xe947,0x1512,0xe2dc,0xb106,
 0xe030,0x11fa,0xe2c4,0xb5ee,0xe919,0x1ee5,0xf4b2,0xcae1,
 0x0010,0x36e1,0x0cb2,0xe2e5,0x1719,0x4bee,0x1ec4,0xeffa]

def fir_fixture(kind):
    if kind=='fpga-impulse':
        data=np.zeros((128,2),np.int8);data[0]=[64,32];return data
    if kind!='fpga-tones':raise ValueError('Unknown FIR pattern')
    return np.tile(np.array([[v&255,v>>8]for v in FIR_WORDS],np.uint8).view(np.int8),(4,1))

def evidence(state,lesson,now=None):
    now=time.time()if now is None else now
    settings=state.get('settings',{});mode=settings.get('view','raw')
    c=state.get('latest',{}).get(mode);rows=[]
    def add(label,want,actual,ok=None):
        rows.append(dict(label=label,requested=want,applied=actual,ok=ok))
    if not c:return dict(status='ERROR'if state.get('status')in ('OFFLINE','STOPPED')else'WAITING',rows=[],reason=state.get('error')or'No result for this experiment yet',result=None)
    cfg=c.get('acquisition',{});meta=c.get('ddc',{});raw=c.get('raw',{})
    pattern=cfg.get('ddc_input','live')if mode=='ddc'else cfg.get('input_kind','live')
    synthetic=raw.get('source')==3
    keys=['view']
    if mode=='ddc':keys+=['ddc_input','tuning_hz','decimation','ddc_bypass']
    elif lesson==3:keys+=['input_kind','round']
    if not synthetic:keys+=['source','channel','rate','samples','gain_mode','gain_code']
    if lesson==5:keys+=['digital_gain_q8','digital_gain_bypass']
    matches=all(cfg.get(k, 'live'if k=='input_kind'else None)==settings.get(k,'live'if k=='input_kind'else None)for k in keys)
    if synthetic:
        add('Input',settings.get('ddc_input')if mode=='ddc'else settings.get('input_kind','live'),pattern,matches)
        add('Pattern identity','FPGA source 3 + exact fixture',c.get('pattern_identity_verified',c.get('snapshot_crc_verified',False)),c.get('pattern_identity_verified',c.get('snapshot_crc_verified',False))is True)
    else:
        add('Radio',settings.get('source'),raw.get('source'),settings.get('source')==raw.get('source'))
        add('RF center (MHz)',2407+5*settings.get('channel',2),raw.get('frequency',0)/1e6,raw.get('frequency')==(2407+5*settings.get('channel',2))*1000000)
    expected_samples=128 if pattern.startswith('fpga-')else 4096 if synthetic else settings.get('samples')
    expected_rate=16000000 if synthetic else settings.get('rate')
    if not synthetic and c.get('receiver_gain'):
        gain=c['receiver_gain'];actual=gain.get('mode')
        add('Receiver gain mode',settings.get('gain_mode'),actual,gain.get('readback_verified')is True and actual==settings.get('gain_mode'))
        if settings.get('gain_mode')=='MANUAL':add('Receiver gain code',settings.get('gain_code'),gain.get('manual_code'),settings.get('gain_code')==gain.get('manual_code'))
    add('Input samples',expected_samples,raw.get('samples'),expected_samples==raw.get('samples'))
    add('Nominal sample rate',expected_rate,raw.get('rate'),expected_rate==raw.get('rate'))
    if mode in ('boxcar','hamming'):
        coeff=PROFILES[1 if mode=='boxcar'else 2]
        add('FIR coefficients',mode+' / 16 taps','16 coefficients verified'if c.get('coefficients')==coeff else'not verified',c.get('coefficients')==coeff)
        add('Rounding',settings.get('round'),c.get('round_nearest'),settings.get('round')==c.get('round_nearest'))
    if meta:
        rate=raw.get('rate',16000000)
        want=nios_ddc.phase_increment(settings.get('tuning_hz',0),rate)
        phase=meta.get('phase');hz=(phase if phase is not None and phase<2**31 else (phase or 0)-2**32)*rate/2**32
        add('Mixer shift (Hz)',settings.get('tuning_hz'),round(hz,4)if phase is not None else None,want==phase)
        add('Decimation',settings.get('decimation'),meta.get('decimation'),settings.get('decimation')==meta.get('decimation'))
        add('Bypass flags',settings.get('ddc_bypass'),meta.get('bypass_flags'),settings.get('ddc_bypass')==meta.get('bypass_flags'))
        if lesson==5:
            add('Digital gain Q8',settings.get('digital_gain_q8'),meta.get('digital_gain_q8'),settings.get('digital_gain_q8')==meta.get('digital_gain_q8'))
            add('Gain bypass',settings.get('digital_gain_bypass'),meta.get('digital_gain_bypass'),settings.get('digital_gain_bypass')==meta.get('digital_gain_bypass'))
        add('Output samples',(raw.get('samples',0)+settings.get('decimation',1)-1)//settings.get('decimation',1),meta.get('output_samples'),meta.get('output_samples')==(raw.get('samples',0)+settings.get('decimation',1)-1)//settings.get('decimation',1))
    error=meta.get('max_reference_error',c.get('max_reference_error'))
    crc=c.get('snapshot_crc_verified')if synthetic else c.get('transport_crc_verified')
    add('Payload CRC',True,crc,crc is True)
    if mode!='raw':add('Integer error (LSB)',0,error,error==0)
    if lesson==2:
        telemetry=state.get('telemetry',{})
        counter_age=max(0,now-telemetry.get('received_unix',0))
        add('Nios counter window','Fresh sequence (<5 s)',telemetry.get('seq'),telemetry.get('seq')is not None and counter_age<5)
        for key,label in (('capture_errors','Counter capture errors'),('radio_errors','Counter UART errors')):
            add(label,0,telemetry.get(key),telemetry.get(key)==0)
    age=max(0,now-c.get('captured_unix',0))
    failures=[r['label']for r in rows if r['ok']is False]
    status='VERIFIED';reason='Metadata and CRC verified'+('; FPGA output matches integer reference'if mode!='raw'else'; no arithmetic stage in this checkpoint')
    if state.get('status')in ('OFFLINE','STOPPED'):status='ERROR';reason=state.get('error')or'Acquisition stopped'
    elif not matches:status='APPLYING';reason='Last result belongs to earlier settings; waiting for matching result'
    elif failures:status='MISMATCH';reason='Failed: '+', '.join(failures)
    elif age>(30 if meta else 8):status='STALE';reason='Held result is too old to count as a fresh verification'
    elif state.get('status')=='PAUSED':status='HELD';reason='Verified result held while acquisition is paused'
    return dict(status=status,reason=reason,rows=rows,age_seconds=round(age,2),result=c,synthetic=synthetic,
        capture_id=str(c.get('captured_unix'))+':'+str(raw.get('job'))+':'+str(raw.get('raw_crc')),
        plot_context=[mode,pattern,raw.get('source'),raw.get('frequency'),raw.get('rate'),meta.get('output_rate')],
        scope='Configuration and digital output; nominal RF clock/center metadata is not an independent RF measurement')

def spectrum(data):
    z=np.asarray(data,float);z=z[:,0]+1j*z[:,1];w=np.hanning(len(z))
    db=20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(z*w)))/max(1,w.sum()),1e-9))
    edges=np.linspace(0,len(db),min(1024,len(db))+1,dtype=int)
    return [float(max(db[a:b]))for a,b in zip(edges[:-1],edges[1:])]

def plot_data(c):
    raw=c.get('raw',{});meta=c.get('ddc',{});fs=raw.get('rate',16000000)
    output=c.get('ddc_wave')or (c.get('waveform',[[],[]])+[[]])[1]
    return dict(input_spectrum=c.get('spectra_db',[[]])[0],output_spectrum=c.get('ddc_spectrum_db')or(c.get('spectra_db',[[],[]])+[[]])[1],
        input_rate=fs,output_rate=meta.get('output_rate',fs),waveform=c.get('waveform',[[]])[0],output_waveform=output,
        scatter=c.get('scatter',[[]])[0],output_scatter=output,
        coefficients=c.get('coefficients')or(nios_ddc.COEFFICIENTS.tolist()if meta and not meta.get('bypass_flags',0)&2 else []),
        tones=(c.get('tone_measurements')or {}).get('tones',[]),meters=meta.get('gain_meters',{}))

def preview(lesson,settings):
    """HOST reference preview. Never labelled as measured/verified FPGA output."""
    lesson=int(lesson)
    if lesson not in NAMES:raise ValueError('Lesson must be 1..5')
    if lesson==3:
        raw=fir_fixture('fpga-impulse'if settings.get('input_kind')=='fpga-impulse'else'fpga-tones')
        coeff=PROFILES[1 if settings.get('view')=='boxcar'else 2]
        out=fixed_reference(raw,coeff,settings.get('round',True));meta={}
    else:
        raw,_=load_sample('single-tone'if lesson==5 else'two-tone');coeff=None;out=None;meta={}
        if lesson>=4:
            phase=nios_ddc.phase_increment(settings.get('tuning_hz',0),16000000)
            m=settings.get('decimation',1);flags=settings.get('ddc_bypass',0)
            out=nios_ddc.reference(raw,phase,m,flags)['result']
            out,meters=nios_ddc.gain_reference(out,settings.get('digital_gain_q8',256),settings.get('digital_gain_bypass',True))
            meta=dict(output_rate=16000000//m,bypass_flags=flags,gain_meters=meters)
    c=dict(raw=dict(rate=16000000),spectra_db=[spectrum(raw)]+([spectrum(out.astype(float)/(128 if lesson>=4 else 1))]if out is not None else []),
        waveform=[raw[:256].tolist()]+([out[:256].tolist()]if out is not None and lesson==3 else []),
        scatter=[raw[:256].tolist()],coefficients=coeff,ddc=meta)
    if lesson>=4:c.update(ddc_wave=(out[:256].astype(float)/128).tolist())
    return dict(origin='HOST SOFTWARE PREVIEW — NOT HARDWARE VERIFICATION',lesson=lesson,plots=plot_data(c))

def capture_fir_test(nios,config):
    """Run existing TEST/RUN/DUMP IP path; reject a wrong fixture or readback."""
    import hashlib,zlib
    from iq_lab_samples import SyntheticSnapshot
    kind=config['input_kind'];expected=fir_fixture(kind)
    nios.command('PAIR',0)
    nios.command('TEST',1 if kind=='fpga-impulse'else 2);nios.wait(2)
    nios.run(1)
    meta,raw,filtered=nios.dump()
    coeff=PROFILES[1 if config['view']=='boxcar'else 2]
    if (meta['source'],meta['samples'],meta['rate'],meta['frequency'],meta['mode'],meta['round'])!=(3,128,16000000,0,1,int(config['round'])):
        raise ValueError('FIR test configuration readback mismatch')
    if raw.tobytes()!=expected.tobytes()or meta['coefficients_current']!=coeff or meta['profile']!=(1 if config['view']=='boxcar'else 2):
        raise ValueError('FIR fixture/coefficient identity mismatch')
    if not np.array_equal(filtered,fixed_reference(raw,coeff,config['round'])):
        raise ValueError('FIR test integer reference mismatch')
    def wrap(data,crc):
        payload=data.tobytes()
        if zlib.crc32(payload)!=crc:raise ValueError('FIR test payload CRC mismatch')
        return SyntheticSnapshot(payload,dict(source=3,samples=128,rate=16000000,frequency=0,job=meta['job'],raw_crc=crc,
            length=len(payload),capture_us=0,signal_origin='FPGA deterministic test; no RF acquisition',
            sample_format='ci8',payload_sha256=hashlib.sha256(payload).hexdigest(),capture_time_synchronized=False))
    return wrap(raw,meta['raw_crc']),wrap(filtered,meta['filtered_crc']),meta
