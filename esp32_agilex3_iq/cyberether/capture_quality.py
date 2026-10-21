"""Unscaled CI8 quality and explicit parent-to-DSP window provenance.

No calibration, SNR estimate, RF clock synchronization or clipping correction.
The full raw payload is always the parent; windows never combine captures.
"""
import hashlib
import json

CAPTURE_SAMPLES=(4096,8192,16380)
RATES_MSPS=(16,40,80)
WINDOW_SAMPLES=4096


def sha256(payload):return hashlib.sha256(payload).hexdigest()


def ci8_quality(payload):
    import numpy as np
    if not payload or len(payload)%2:raise ValueError('CI8 requires complete nonempty I/Q pairs')
    iq=np.frombuffer(payload,dtype=np.int8).reshape(-1,2).astype(np.float64)
    axes={}
    for index,name in enumerate(('i','q')):
        data=iq[:,index];peak=float(np.max(np.abs(data)))
        axes[name]=dict(mean_counts=float(np.mean(data)),rms_counts=float(np.sqrt(np.mean(data*data))),
            peak_abs_counts=peak,min_counts=int(np.min(data)),max_counts=int(np.max(data)),
            rail_samples=int(np.count_nonzero((data==-128)|(data==127))),
            rail_fraction=float(np.mean((data==-128)|(data==127))),
            unique_levels=int(len(np.unique(data))),headroom_counts=int(min(np.min(data)+128,127-np.max(data))))
    return dict(schema='ci8_unscaled_quality_v1',samples=len(iq),units='signed ADC counts before display gain',
        i=axes['i'],q=axes['q'],complex_rms_counts=float(np.sqrt(np.mean(np.sum(iq*iq,axis=1)))),
        any_rail_fraction=float(np.mean(np.any((iq==-128)|(iq==127),axis=1))),
        calibrated=False,snr_estimate_available=False)


def add_capture_arguments(parser):
    parser.add_argument('--samples',type=int,choices=CAPTURE_SAMPLES,default=4096)
    parser.add_argument('--rate',type=int,choices=RATES_MSPS,default=40,help='Nominal receiver MS/s; verified against LIMITS?')
    parser.add_argument('--gain-modes',nargs=3,choices=('MANUAL','HARDWARE'),default=['MANUAL']*3)
    parser.add_argument('--gain-indices',nargs=3,type=int,default=[10]*3,help='Per-radio manual codes; ignored for HARDWARE')
    parser.add_argument('--dsp-window-offset',type=int,default=0,help='Contiguous 4096-sample A3/A5 window offset in full raw burst')


def capture_settings(args):
    settings=dict(samples=getattr(args,'samples',4096),rate=getattr(args,'rate',40),
        gain_modes=list(getattr(args,'gain_modes',['MANUAL']*3)),gain_indices=list(getattr(args,'gain_indices',[10]*3)),
        dsp_window_offset=getattr(args,'dsp_window_offset',0))
    if settings['samples']not in CAPTURE_SAMPLES or settings['rate']not in RATES_MSPS:raise ValueError('Unsupported CI8 sample count or nominal rate')
    if len(settings['gain_modes'])!=3 or any(m not in('MANUAL','HARDWARE')for m in settings['gain_modes']):raise ValueError('Three gain modes required')
    if len(settings['gain_indices'])!=3 or any(type(c)is not int or c<0 or c>127 for c in settings['gain_indices']):raise ValueError('Gain codes must be integers0..127; actual range is read from receiver')
    offset=settings['dsp_window_offset']
    if type(offset)is not int or not 0<=offset<=settings['samples']-WINDOW_SAMPLES:raise ValueError('4096-sample DSP window must fit entirely in parent capture')
    return settings


def configure_receiver_gain(radio,command,mode,code,rate_hz):
    line=command(radio,'LIMITS?')
    if not line.startswith('LIMITS '):raise ValueError('Receiver LIMITS? response missing')
    limits=json.loads(line[7:]);gain=limits.get('gain')
    if not isinstance(gain,list)or len(gain)!=3 or any(type(v)is not int for v in gain)or gain[2]<=0 or gain[0]>gain[1]:raise ValueError('Invalid receiver gain limits')
    if rate_hz not in limits.get('rates',[]):raise ValueError('Requested sample rate absent from receiver LIMITS?')
    if 8 not in limits.get('bits',[]):raise ValueError('Receiver does not advertise 8-bit capture')
    if mode not in('MANUAL','HARDWARE'):raise ValueError('Unsupported gain mode')
    if mode=='MANUAL'and(not gain[0]<=code<=gain[1]or(code-gain[0])%gain[2]):raise ValueError('Manual gain outside receiver LIMITS?')
    command(radio,'GAIN HARDWARE'if mode=='HARDWARE'else f'GAIN MANUAL {code}')
    readback=command(radio,'GAIN?');parts=readback.split()
    if len(parts)!=6 or parts[0]!='GAIN' or parts[1]!=mode:raise ValueError('Receiver gain mode readback mismatch')
    actual,minimum,maximum,manual_enable=map(int,parts[2:])
    if minimum!=gain[0]or maximum!=gain[1]or actual!=(-1 if mode=='HARDWARE'else code)or manual_enable!=(mode=='MANUAL'):raise ValueError('Receiver gain code/limits/register readback mismatch')
    return dict(schema='receiver_gain_v1',mode=mode,manual_code=actual if mode=='MANUAL'else None,
        hardware_agc=mode=='HARDWARE',register_manual_enable=bool(manual_enable),readback=readback,
        limits=limits,readback_verified=True,readback_scope='configuration; hardware AGC instantaneous gain unavailable',
        gain_units='uncalibrated receiver code; not dB')


def make_dsp_window(payload,*,session_id,source_id,iq_sequence,offset_samples=0):
    if len(payload)%2 or not payload:raise ValueError('Invalid parent CI8 payload')
    if type(offset_samples)is not int or not 0<=offset_samples<=len(payload)//2-WINDOW_SAMPLES:raise ValueError('DSP window outside parent capture')
    selected=payload[offset_samples*2:(offset_samples+WINDOW_SAMPLES)*2]
    descriptor=dict(schema='rf_dsp_window_v1',parent_session_id=session_id,parent_source_id=source_id,
        parent_iq_sequence=iq_sequence,parent_payload_sha256=sha256(payload),parent_samples=len(payload)//2,
        offset_samples=offset_samples,samples=WINDOW_SAMPLES,payload_sha256=sha256(selected))
    return selected,descriptor


def resolve_dsp_window(payload,raw_meta,feature_meta=None):
    """Verify parent identity plus both hashes; legacy only accepts full4096."""
    feature_meta=feature_meta or raw_meta
    descriptor=feature_meta.get('dsp_window')
    if descriptor is None:
        if len(payload)!=WINDOW_SAMPLES*2 or raw_meta.get('samples')!=WINDOW_SAMPLES:raise ValueError('Long capture requires explicit DSP window metadata')
        if feature_meta.get('input_iq_sequence',raw_meta['sequence'])!=raw_meta['sequence']or feature_meta['session_id']!=raw_meta['session_id']or feature_meta['source_id']!=raw_meta['source_id']:raise ValueError('Legacy DSP parent identity mismatch')
        return payload
    if descriptor.get('schema')!='rf_dsp_window_v1':raise ValueError('Unknown DSP window schema')
    for dkey,mkey in(('parent_session_id','session_id'),('parent_source_id','source_id'),('parent_iq_sequence','sequence'),('parent_samples','samples')):
        if descriptor.get(dkey)!=raw_meta.get(mkey):raise ValueError('DSP window parent identity mismatch: '+dkey)
    if feature_meta['session_id']!=raw_meta['session_id']or feature_meta['source_id']!=raw_meta['source_id']or feature_meta.get('input_iq_sequence',raw_meta['sequence'])!=raw_meta['sequence']:raise ValueError('Feature parent identity mismatch')
    if raw_meta.get('dsp_window')is not None and raw_meta['dsp_window']!=descriptor:raise ValueError('Feature and raw DSP window descriptors differ')
    if descriptor['parent_samples']*2!=len(payload)or descriptor.get('parent_payload_sha256')!=sha256(payload):raise ValueError('DSP parent payload hash/length mismatch')
    if descriptor.get('samples')!=WINDOW_SAMPLES:raise ValueError('Unsupported DSP window size')
    offset=descriptor.get('offset_samples')
    if type(offset)is not int or not 0<=offset<=len(payload)//2-WINDOW_SAMPLES:raise ValueError('DSP window outside parent')
    selected=payload[offset*2:(offset+WINDOW_SAMPLES)*2]
    if sha256(selected)!=descriptor.get('payload_sha256'):raise ValueError('DSP window payload hash mismatch')
    return selected


def validate_dsp_window_reference(payload,descriptor,*,source_id,iq_sequence,session_id):
    """Validate selected-byte evidence when only the window is retained (event RAM)."""
    if descriptor.get('schema')!='rf_dsp_window_v1':raise ValueError('Unknown DSP window schema')
    if descriptor.get('parent_source_id')!=source_id or descriptor.get('parent_iq_sequence')!=iq_sequence or descriptor.get('parent_session_id')!=session_id:raise ValueError('Event DSP window parent identity mismatch')
    offset=descriptor.get('offset_samples');parent=descriptor.get('parent_samples')
    if type(parent)is not int or type(offset)is not int or not 0<=offset<=parent-WINDOW_SAMPLES:raise ValueError('Event DSP window outside parent')
    if descriptor.get('samples')!=WINDOW_SAMPLES or len(payload)!=WINDOW_SAMPLES*2 or descriptor.get('payload_sha256')!=sha256(payload):raise ValueError('Event DSP window payload hash/length mismatch')
    digest=descriptor.get('parent_payload_sha256')
    if not isinstance(digest,str)or len(digest)!=64 or any(c not in'0123456789abcdef'for c in digest):raise ValueError('Event DSP parent hash missing')
