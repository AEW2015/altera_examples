#!/usr/bin/env python3
"""DDC commands through the existing Nios/JTAG owner; host reference is verification only."""
import json,time,zlib
from pathlib import Path
import numpy as np
PROFILE=json.loads((Path(__file__).with_name('ddc_profile.json')).read_text())
COEFFICIENTS=np.asarray(PROFILE['coefficients'],np.int64)
SINE=np.asarray(PROFILE['sine_q15'],np.int64)
def phase_increment(hz,rate):
    if type(hz)is not int or type(rate)is not int or rate<=0 or not -rate/2<=hz<rate/2:raise ValueError('Tuning outside Nyquist interval')
    v=(abs(hz)*(1<<32)+rate//2)//rate
    return (-v if hz<0 else v)&0xffffffff

def reference(raw,phase,decimation=1,flags=0):
    if decimation not in (1,2,4)or flags not in range(4)or not 0<=phase<=0xffffffff:raise ValueError('Invalid DDC settings')
    a=np.asarray(raw)
    if a.ndim!=2 or a.shape[1]!=2 or not 1<=len(a)<=16384 or np.any(a< -128)or np.any(a>127):raise ValueError('CI8 pairs required')
    x=a.astype(np.int64)*128;addr=((np.arange(len(x),dtype=np.int64)*phase)&0xffffffff)>>22
    si=SINE[addr];co=SINE[(addr+256)&1023]
    wide=np.column_stack([(x[:,0]*co+x[:,1]*si+16384)>>15,(x[:,1]*co-x[:,0]*si+16384)>>15])
    mixed=x if flags&1 else np.clip(wide,-32768,32767)
    f=np.column_stack([(np.convolve(mixed[:,c],COEFFICIENTS)[:len(x)]+16384)>>15 for c in (0,1)])
    y=mixed if flags&2 else np.clip(f,-32768,32767)
    return dict(result=y[::decimation].astype('<i2'),mixer_clips=0 if flags&1 else int(np.count_nonzero(np.any((wide < -32768)|(wide>32767),axis=1))),filter_clips=0 if flags&2 else int(np.count_nonzero(np.any((f < -32768)|(f>32767),axis=1))))

def gain_reference(data,gain_q8=256,bypass=True):
    if type(gain_q8)is not int or not 0<=gain_q8<=4096 or type(bypass)is not bool:raise ValueError('Invalid digital gain')
    a=np.asarray(data,dtype=np.int64)
    if a.ndim!=2 or a.shape[1]!=2 or np.any(a< -32768)or np.any(a>32767):raise ValueError('CI16 pairs required')
    wide=(a*gain_q8+128)>>8;b=a if bypass else np.clip(wide,-32768,32767)
    pre=np.sum(a*a,axis=1);post=np.sum(b*b,axis=1)
    meters=dict(meter_samples=len(a),pre_power=int(pre.sum()),pre_peak=int(pre.max())if len(a)else 0,pre_rails=int(np.count_nonzero(np.any((a==-32768)|(a==32767),axis=1))),post_power=int(post.sum()),post_peak=int(post.max())if len(a)else 0,gain_clips=0 if bypass else int(np.count_nonzero(np.any((wide< -32768)|(wide>32767),axis=1))))
    return b.astype('<i2'),meters

def power_dbfs(power,count=1):
    return float(10*np.log10(power/count/(32768.**2)))if power and count else None

def run(nios,rate,hz=500000,decimation=4,flags=0,gain_q8=256,gain_bypass=True):
    if decimation not in(1,2,4)or type(flags)is not int or flags not in range(4):raise ValueError('Invalid DDC configuration')
    gain_reference(np.zeros((1,2),np.int16),gain_q8,gain_bypass)
    gain_setting=(int(gain_bypass)<<16)|gain_q8
    if nios.command('DDCGAIN',int(gain_bypass),gain_q8)['gain']!=gain_setting:raise ValueError('Digital gain configuration readback mismatch')
    phase=phase_increment(hz,rate)
    if nios.command('DDCPHASE',phase>>16,phase&65535)['phase']!=phase:raise ValueError('DDC phase readback mismatch')
    config=0x10000|(decimation<<8)|flags
    if nios.command('DDCCONFIG',flags,decimation)['config']!=config:raise ValueError('DDC configuration readback mismatch')
    nios.command('DDCRUN');deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        state=nios.command('DDCSTATUS')
        if not state['state']&1:
            if state['state']&7!=4:raise RuntimeError('FPGA DDC fault or stale result')
            if(state['run_phase'],state['run_config'],state['rate'])!=(phase,config,rate):raise ValueError('DDC applied configuration mismatch')
            if nios.command('DDCLEVELS')['gain']!=gain_setting:raise ValueError('FPGA gain latched configuration mismatch')
            return state
        time.sleep(.03)
    raise TimeoutError('FPGA DDC processing timeout')

def dump(nios):
    meta=nios.command('DDCDUMP');raw=bytearray();output=bytearray();done=False;stage=0;deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        parts=nios.line(deadline).split(',')
        if parts==['DDCDONE',str(meta['id'])]:done=True;break
        if len(parts)!=5 or parts[1]!=str(meta['id'])or parts[0]not in('DDCRAW','DDCIQ'):continue
        target,width=(raw,2)if parts[0]=='DDCRAW'else(output,4)
        if width==4:stage=1
        elif stage:raise ValueError('DDC dump order changed')
        start,n=int(parts[2]),int(parts[3]);data=bytes.fromhex(parts[4])
        if start!=len(target)//width or not 1<=n<=32 or len(data)!=n*width:raise ValueError('DDC dump sequence/length')
        target.extend(data)
    if not done or len(raw)!=meta['samples']*2 or len(output)!=meta['output_samples']*4 or zlib.crc32(raw)!=meta['raw_crc']or zlib.crc32(output)!=meta['output_crc']:raise ValueError('DDC dump CRC/length failure')
    a=np.frombuffer(raw,np.int8).reshape(-1,2);b=np.frombuffer(output,'<i2').reshape(-1,2)
    m=(meta['config']>>8)&255;flags=meta['config']&3
    if meta['config']>>16!=1 or meta['config']&0xfc or m not in (1,2,4)or len(b)!=(len(a)+m-1)//m:raise ValueError('Unknown DDC profile or output length')
    expected=reference(a,meta['phase'],m,flags)
    levels=nios.command('DDCLEVELS')
    setting=levels['gain']
    if levels['capability']!=0x474e0101 or levels['epoch']!=meta['epoch']or setting & ~0x11fff or (setting&8191)>4096:raise ValueError('Unknown gain capability/profile or stale meters')
    processed,meters=gain_reference(expected['result'],setting&8191,bool(setting&65536))
    actual=dict(meter_samples=levels['samples'],pre_power=levels['pre_sum_lo']+(levels['pre_sum_hi']<<32),pre_peak=levels['pre_peak'],pre_rails=levels['pre_rails'],post_power=levels['post_sum_lo']+(levels['post_sum_hi']<<32),post_peak=levels['post_peak'],gain_clips=levels['clips'])
    if actual!=meters:raise ValueError('FPGA gain/power meter reference mismatch')
    expected['result']=processed
    meta.update(digital_gain_q8=setting&8191,digital_gain_bypass=bool(setting&65536),gain_meters=actual,pre_mean_dbfs=power_dbfs(actual['pre_power'],len(b)),post_mean_dbfs=power_dbfs(actual['post_power'],len(b)),pre_peak_dbfs=power_dbfs(actual['pre_peak']),post_peak_dbfs=power_dbfs(actual['post_peak']),meter_origin='FPGA integer power accumulators; host log10; uncalibrated complex CI16 dBFS')
    if not np.array_equal(b,expected['result'])or any(meta[k]!=expected[k]for k in('mixer_clips','filter_clips')):raise ValueError('FPGA DDC/reference mismatch')
    meta.update(max_reference_error=0,output_format='ci16_le',output_rate=meta['rate']//m,decimation=m,bypass_flags=flags,processing_seconds=meta['cycles']/50000000,readback_transport='Nios JTAG UART ASCII + CRC32; separate from IQB1 host UART',origin='FPGA NCO / mixer / FIR II / decimator / digital gain + power meters',scale_counts_per_ci8=128)
    return meta,a,b
