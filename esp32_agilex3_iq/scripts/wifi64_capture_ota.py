#!/usr/bin/env python3
"""Explicit short native Wi-Fi TX -> raw RFS2 IQ -> checkpoint11 Nios decode.

Host transports controls/data and parses identity; no host RF DSP or BER.
No programming/flashing. Importing this file starts no devices or transmission.
"""
from __future__ import annotations
import argparse,collections,fcntl,hashlib,json,os,sys,time
from pathlib import Path
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import encode_command
from nios_fir import NiosFir
from wifi64_ota import MonitorBridge,monitor_command
from wifi64_control import fields,query,require_ok
import wifi64_capture as reader

PADS=(0,7,14)
FREQ=2447000000
RATE=40000000

class CaptureMonitorBridge(MonitorBridge):
    """Retain IQ while text commands wait, with one bounded acquisition owner."""
    def __init__(self,*args,**kwargs):
        self.observed_frames=collections.deque(maxlen=256)
        self.observed_tx_lines=collections.deque(maxlen=256)
        self.observed_radio_lines=collections.deque(maxlen=256)
        super().__init__(*args,**kwargs);self.capture_frames=collections.deque()
    def _ingest(self,frame):
        fresh=not getattr(frame,'_wifi64_ingested',False)
        super()._ingest(frame)
        if fresh:
            self.observed_frames.append({'host_monotonic':time.monotonic(),'kind':frame.kind,'source':frame.source,'job':frame.job})
            if frame.kind==3:
                row={'host_monotonic':time.monotonic(),'source':frame.source,'line':frame.payload.decode('ascii',errors='replace').rstrip('\r\n')}
                self.observed_radio_lines.append(row)
                if frame.source==1:self.observed_tx_lines.append(row)
    def _next(self,timeout):
        frame=self.responses.popleft() if self.responses else self.read_frame(timeout)
        self._ingest(frame)
        if frame.kind==5:raise RuntimeError(f'FPGA error {frame.error:#x}, job{frame.job}')
        if frame.kind in (1,6) and not getattr(frame,'_wifi64_capture_stored',False):
            frame._wifi64_capture_stored=True
            if len(self.capture_frames)>=2:raise BufferError('Unexpected additional IQ capture')
            self.capture_frames.append(frame)
        return frame
    def capture(self,job,samples,timeout=12,expected_frequency=FREQ):
        end=time.monotonic()+timeout
        while not self.capture_frames:
            self._next(max(.001,end-time.monotonic()))
            if time.monotonic()>=end and not self.capture_frames:raise TimeoutError('Raw capture deadline')
        frame=self.capture_frames.popleft()
        if (frame.kind,frame.job,frame.source,frame.samples,frame.rate,frame.frequency)!=(1,job,0,samples,RATE,expected_frequency):
            raise RuntimeError('Raw capture identity/profile mismatch')
        return frame

def channel_frequency(channel):
    if not 1<=channel<=11:raise ValueError('channel1..11 required')
    return (2412+5*(channel-1))*1000000


def trigger_wire(samples,pad):
    """One write, START first. Spaces delay CAP newline without extra commands.

    Each forwarded ASCII byte costs20 IQBC bytes. At2Mbaud8N1, one padding
    byte adds nominal100us of host wire time; NOT an RF/sample timestamp.
    """
    if samples not in (8192,16380) or not 0<=pad<=14:raise ValueError('Bounded capture/padding required')
    cap=f'CAP16 {samples} 1'+(' '*pad)+'\n'
    return b''.join(encode_command(1,source,arg=byte) for source,text in ((1,'START\n'),(0,cap)) for byte in text.encode('ascii'))

def arm_bridge(bridge,samples):
    """Arm only; Bridge.submit would immediately append CAP16 itself."""
    job=bridge.next_job();bridge.send(3,0,job=job,value=samples)
    end=time.monotonic()+5
    while time.monotonic()<end:
        frame=bridge._next(max(.001,end-time.monotonic()))
        if frame.kind==2 and frame.job==job and frame.source==0:return job
    raise TimeoutError('Bridge raw arm not acknowledged')

def wait_terminal(bridge,timeout=3):
    """Accept explicit DONE/CANCELLED, preserving interleaved counter rows."""
    end=time.monotonic()+timeout;deferred=[]
    try:
        while True:
            remaining=end-time.monotonic()
            if remaining<=0:raise TimeoutError('No TX DONE/CANCELLED terminal')
            line=bridge.wait_text(1,'WIFI64_TX,',remaining)
            if line.startswith(('WIFI64_TX,DONE,','WIFI64_TX,CANCELLED,')):return line
            deferred.append(line)
            if len(deferred)>64:raise BufferError('Too many nonterminal TX rows')
    finally:
        bridge.text_queues[1].extendleft(reversed(deferred))

def tx_block(bridge,command,verb):
    line=query(bridge,command,verb)
    require_ok(line,verb)
    submitted=bridge.wait_text(1,'WIFI64_TX,SUBMITTED,',2)
    counters=bridge.wait_text(1,'WIFI64_TX,COUNTERS,',2)
    return {'line':line,'submitted':submitted,'counters':counters}

def tx_identity(bridge):
    info=query(bridge,'INFO','INFO');require_ok(info,'INFO')
    ident=bridge.wait_text(1,'WIFI64_TX,IDENT,',2)
    status=bridge.wait_text(1,'WIFI64_TX,STATUS,',2)
    bridge.wait_text(1,'WIFI64_TX,SUBMITTED,',2);bridge.wait_text(1,'WIFI64_TX,COUNTERS,',2)
    f=fields(status)
    if f.get('busy')!='0' or f.get('rf')!='0' or f.get('stop_err')!='0' or f.get('armed')!='0':raise RuntimeError('Transmitter not initially idle')
    mac=fields(ident).get('mac','')
    if len(bytes.fromhex(mac.replace(':','')))!=6:raise RuntimeError('Invalid transmitter MAC')
    return {'info':info,'identity':ident,'status':status,'mac':mac}

def packet_identity(decoded,mac,run,count,seed):
    """Parse device-decoded identity only; no waveform processing or BER."""
    try:
        p=bytes.fromhex(decoded.get('decoded_psdu_hex',''))
        return bool(len(p)==92 and p[10:16]==bytes.fromhex(mac.replace(':','')) and
                    p[24:32]==b'W64A\x01\x36\x40\x00' and
                    int.from_bytes(p[32:36],'little')==run and
                    int.from_bytes(p[36:40],'little')<count and
                    int.from_bytes(p[40:44],'little')==seed)
    except ValueError:return False

def cleanup(bridge,owner,cancel_mirror=True):
    """Every independent cleanup is attempted even if another one fails."""
    result={}
    actions=[
        ('tx_stop',lambda:tx_block(bridge,'STOP','STOP')),
        ('monitor_stop',lambda:monitor_command(bridge,'STOP','STOP')),
        ('bridge_cancel',lambda:bridge.control(6,0))]
    if cancel_mirror:actions.append(('mirror_cancel',lambda:reader.checked(owner,'WCANCEL',required=('state','valid'))))
    for name,action in actions:
        try:
            value=action();result[name]=value.metadata() if hasattr(value,'metadata') else value
        except Exception as exc:result[name+'_error']=str(exc)
    try:
        end=time.monotonic()+3
        while True:
            state=tx_block(bridge,'STATUS','STATUS');f=fields(state['line'])
            if f.get('busy')=='0' and f.get('rf')=='0' and f.get('stop_err')=='0' and f.get('armed')=='0':
                result['tx_idle']=state;result['tx_idle_verified']=True;break
            if time.monotonic()>=end:raise TimeoutError('TX did not reach verified idle')
    except Exception as exc:result['tx_idle_error']=str(exc)
    result['monitor_stop_verified']=bool(fields(result.get('monitor_stop','')).get('listening')=='0')
    result['mirror_cancel_verified']=bool(result.get('mirror_cancel',{}).get('state')==0 and result.get('mirror_cancel',{}).get('valid')==0) if cancel_mirror else None
    return result

def reserve_raw_directory(output):
    """Reserve a private new ignored directory before any device access."""
    output=Path(output).resolve()
    output.relative_to((ROOT/'cyberether/run').resolve())
    directory=output.with_name(output.stem+'.private')
    directory.mkdir(mode=0o700,exist_ok=False)
    return directory


def save_raw(frame,directory,run):
    """Byte-for-byte transport archive only; never inspect/process IQ."""
    if directory is None:return None
    payload=frame.payload
    if len(payload)!=frame.samples*2:raise ValueError('Raw archive length mismatch')
    path=Path(directory)/f'run-{run}-job-{frame.job}.ci8'
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    return {'path':str(path.relative_to(ROOT.resolve())),'bytes':len(payload),
            'sha256':hashlib.sha256(payload).hexdigest(),'sample_format':'ci8',
            'host_dsp':False,'rf_content_verified':False}


def attempt(bridge,owner,args,run,pad):
    channel=getattr(args,'channel',8);frequency=channel_frequency(channel)
    conjugate=getattr(args,'conjugate_q',0)
    proof={'run':run,'channel':channel,'requested_frequency':frequency,'conjugate_q':conjugate,'phase_padding_bytes':pad,'tx_start_requested':False,
           'completed':False,'ota64_confirmed':False,'host_dsp':False,'ber_measured':False,
           'raw_transferred_for_transport_only':False,'capture_overlap_guaranteed':False}
    try:
        version=reader.checked(owner,'WVERSION',required=('version','ram_bytes','timer_base','cancel_supported','host_dsp'))
        if any(version[k]!=v for k,v in {'version':1,'ram_bytes':262144,'timer_base':0x50000,'cancel_supported':1,'host_dsp':0}.items()):raise RuntimeError('Dedicated cancellable checkpoint11 app required')
        proof['device_version']=version
        if conjugate and version.get('conjugate_supported')!=1:raise RuntimeError('On-device conjugation capability required')
        if version.get('conjugate_supported')==1:
            original=reader.checked(owner,'WSTATUS',required=('conjugate_q',))
            if original['conjugate_q'] not in (0,1):raise RuntimeError('Invalid original conjugation mode')
            proof['original_conjugate_q']=original['conjugate_q']
            cancelled=reader.checked(owner,'WCANCEL',required=('state','valid'))
            if cancelled['state'] or cancelled['valid']:raise RuntimeError('Mirror not idle before conjugation configuration')
            configured=reader.checked(owner,'WCONJ',conjugate,required=('conjugate_q',))
            readback=reader.checked(owner,'WSTATUS',required=('conjugate_q',))
            if configured['conjugate_q']!=conjugate or readback['conjugate_q']!=conjugate:raise RuntimeError('Conjugation configuration readback mismatch')
            proof['conjugation_readback']=readback
        identity=tx_identity(bridge);proof['transmitter']=identity
        cfg=f'CONFIG {channel} {args.power} {args.count} 2 {run} {args.seed}'
        require_ok(query(bridge,cfg,'CONFIG'),'CONFIG')
        readback=query(bridge,'CONFIG?','CONFIG');actual=fields(readback)
        expected={'ch':str(channel),'power_qdbm':str(args.power),'count':str(args.count),'gap_ms':'2','run':str(run),'seed':str(args.seed)}
        if any(actual.get(k)!=v for k,v in expected.items()):raise RuntimeError('TX configuration mismatch')
        proof['configuration']=readback
        if args.monitor:
            monitor_command(bridge,'STOP','STOP')
            listen=monitor_command(bridge,f'LISTEN {channel} 10000','LISTEN')
            if fields(listen).get('ok')!='1' or fields(listen).get('ch')!=str(channel):raise RuntimeError('Passive monitor did not listen')
            proof['monitor_listen']=listen
        # WARM clears old ready identity. A ARM may initialize/calibrate slowly;
        # bridge's5s capture timeout starts only AFTER the radio is prepared.
        proof['mirror_arm']=reader.checked(owner,'WARM',required=('state','pair'))
        if proof['mirror_arm']['state']&3!=1 or proof['mirror_arm']['pair']!=0:raise RuntimeError('Manual raw mirror not armed')
        arm=query(bridge,'ARM','ARM');require_ok(arm,'ARM')
        if fields(arm).get('ch')!=str(channel):raise RuntimeError('TX ARM channel mismatch')
        proof['tx_arm']=arm
        # ARM is serialized after earlier INFO/CONFIG telemetry; discard only
        # their retained text, so new SUBMITTED/COUNTERS cannot use stale rows.
        bridge.text_queues[1].clear()
        job=arm_bridge(bridge,args.samples);proof['capture_job']=job
        wire=trigger_wire(args.samples,pad)
        proof['tx_start_requested']=True
        proof['trigger_host_started']=time.monotonic()
        bridge.port.write(wire);bridge.port.flush()
        proof['trigger_host_finished']=time.monotonic()
        start=bridge.wait_text(1,'WIFI64_TX,START,',3)
        proof['tx_start']=start
        done=wait_terminal(bridge,3)
        proof['tx_terminal']=done
        proof['tx_job_cancelled']=done.startswith('WIFI64_TX,CANCELLED,')
        proof['tx_terminal_scope']='firmware-deadline cancellation; not a successful TX job' if proof['tx_job_cancelled'] else 'normal TX completion'
        proof['tx_done' if not proof['tx_job_cancelled'] else 'tx_cancelled']=done
        if fields(start).get('job')!=fields(done).get('job'):raise RuntimeError('TX job association mismatch')
        submitted=fields(bridge.wait_text(1,'WIFI64_TX,SUBMITTED,',2))
        counters=fields(bridge.wait_text(1,'WIFI64_TX,COUNTERS,',2))
        proof['submitted']=submitted;proof['counters']=counters
        proof['tx_success']=not proof['tx_job_cancelled'] and all(int(submitted.get(k,-1))==v for k,v in {'accepted':args.count,'rejected':0}.items()) and all(int(counters.get(k,-1))==v for k,v in {'done':args.count,'failed':0,'rate54':args.count,'other':0}.items())
        raw=bridge.capture(job,args.samples,expected_frequency=frequency)
        proof['raw_transport']=raw.metadata();proof['raw_transferred_for_transport_only']=True
        proof['saved_raw']=save_raw(raw,getattr(args,'raw_dir',None),run)
        status=reader.checked(owner,'WSTATUS',required=('state','samples','job','source','rate','frequency','raw_crc','ddc_busy'))
        if status['state']&0x8b!=2 or status['ddc_busy'] or any(status[k]!=v for k,v in {'samples':args.samples,'job':job,'source':0,'rate':RATE,'frequency':frequency,'raw_crc':raw.raw_crc}.items()):raise RuntimeError('Frozen raw mirror differs from received transport')
        if version.get('conjugate_supported')==1 and status.get('conjugate_q')!=conjugate:raise RuntimeError('Frozen mirror conjugation mode mismatch')
        # TX is off and passive monitor is stopped BEFORE potentially long DSP.
        proof['pre_decode_cleanup']=cleanup(bridge,owner,cancel_mirror=False)
        if not proof['pre_decode_cleanup'].get('tx_idle_verified'):
            raise RuntimeError('Transmitter idle not verified before on-board DSP')
        proof['decoder']=reader.run(owner,decode=True,timeout=args.decode_timeout)
        if version.get('conjugate_supported')==1 and proof['decoder'].get('device_result',{}).get('conjugate_q')!=conjugate:raise RuntimeError('Decoded result conjugation mode mismatch')
        proof['known_a_identity']=packet_identity(proof['decoder'],identity['mac'],run,args.count,args.seed)
        proof['device_decode_accepted']=proof['decoder'].get('device_decode_accepted',False)
        proof['raw_known_a_decode_confirmed']=bool(proof['device_decode_accepted'] and proof['known_a_identity'])
        proof['ota64_confirmed']=bool(proof['raw_known_a_decode_confirmed'] and proof['tx_success'])
        proof['completed']=True
    except Exception as exc:
        proof['error']=str(exc)
        if proof['tx_start_requested']:
            # Stop RF first, retain frozen FIR RAM until diagnostics finish.
            # Missing TX telemetry does not imply the concurrent ADC failed.
            proof['failure_stop']=cleanup(bridge,owner,cancel_mirror=False)
            if 'raw_transport' not in proof and 'capture_job' in proof:
                try:
                    raw=bridge.capture(proof['capture_job'],args.samples,timeout=1,expected_frequency=frequency)
                    proof['raw_transport']=raw.metadata();proof['raw_transferred_for_transport_only']=True
                    proof['saved_raw']=save_raw(raw,getattr(args,'raw_dir',None),run)
                except Exception as capture_exc:proof['failure_capture_error']=str(capture_exc)
            try:proof['failure_mirror_status']=reader.checked(owner,'WSTATUS',required=('state','samples','job','source','rate','frequency','raw_crc','ddc_busy'))
            except Exception as status_exc:proof['failure_mirror_status_error']=str(status_exc)
    finally:
        capable=proof.get('device_version',{}).get('cancel_supported')==1
        proof['cleanup']=cleanup(bridge,owner,cancel_mirror=capable)
        if not proof['cleanup'].get('tx_idle_verified') or not proof['cleanup'].get('monitor_stop_verified') or (capable and not proof['cleanup'].get('mirror_cancel_verified')):
            proof['completed']=False;proof['ota64_confirmed']=False
        if 'original_conjugate_q' in proof:
            try:
                if not proof['cleanup'].get('mirror_cancel_verified'):raise RuntimeError('Cannot restore conjugation before verified WCANCEL')
                restored=reader.checked(owner,'WCONJ',proof['original_conjugate_q'],required=('conjugate_q',))
                readback=reader.checked(owner,'WSTATUS',required=('conjugate_q',))
                if restored['conjugate_q']!=proof['original_conjugate_q'] or readback['conjugate_q']!=proof['original_conjugate_q']:raise RuntimeError('Conjugation restore readback mismatch')
                proof['conjugation_restored']=readback
            except Exception as restore_exc:
                proof['conjugation_restore_error']=str(restore_exc);proof['completed']=False;proof['ota64_confirmed']=False
    proof['observed_radio_lines']=list(getattr(bridge,'observed_radio_lines',()))
    proof['observed_tx_lines']=list(getattr(bridge,'observed_tx_lines',()))
    proof['observed_frames']=list(getattr(bridge,'observed_frames',()))
    pending=getattr(bridge,'capture_frames',())
    proof['retained_capture_frames']=[frame.metadata() for frame in pending]
    return proof


def validate_args(args):
    channel_frequency(getattr(args,'channel',8))
    if getattr(args,'conjugate_q',0) not in (0,1):raise ValueError('conjugate-q0 or1 required')
    phase=getattr(args,'phase_pad',None)
    if phase is not None and (not 0<=phase<=14 or args.attempts!=1):raise ValueError('Explicit phase-pad0..14 requires attempts1')
    if getattr(args,'save_raw',False):
        try:Path(args.output).resolve().relative_to((ROOT/'cyberether/run').resolve())
        except ValueError as exc:raise ValueError('Raw archive proof must be inside cyberether/run') from exc
    if not 1<=args.attempts<=3:raise ValueError('1..3 explicitly bounded attempts required')
    if not 1<=args.count<=16 or not 8<=args.power<=40:raise ValueError('count1..16, power8..40 required')
    if args.samples not in (8192,16380):raise ValueError('samples8192 or16380 required')
    if not 1<=args.decode_timeout<=1800:raise ValueError('decode timeout1..1800 required')
    if not 0<=args.run<=0xffffffff-(args.attempts-1) or not 0<=args.seed<=0xffffffff:raise ValueError('u32 run/seed required without run wrap')


def run(bridge,owner,args,proof=None):
    validate_args(args)
    initial={'kind':'bounded native Wi-Fi -> raw RFS2 -> Nios receiver',
           'source':'ota-native-wifi64-raw-iq','channel':getattr(args,'channel',8),'requested_frequency':channel_frequency(getattr(args,'channel',8)),'conjugate_q':getattr(args,'conjugate_q',0),'host_dsp':False,'ber_measured':False,
           'completed':False,'ota64_confirmed':False,'attempts':[],
           'timing_scope':'Immediate ADC snapshot; no RF trigger or guaranteed overlap',
           'capture_aperture_us':args.samples/RATE*1e6,'started_unix':time.time()}
    if proof is None:proof=initial
    else:proof.update(initial)
    bridge.control(2,1,2000000);bridge.control(2,2,2000000)
    before=bridge.status();proof['bridge_before']=before
    if before.get('armed') or before.get('receiving') or before.get('bank_ready'):
        raise RuntimeError('Bridge has an existing acquisition; refusing to overwrite')
    proof['receiver_info']=bridge.prepare_sdr(0,proof['requested_frequency']//1000000,RATE)
    proof['original_gain']=bridge.radio_command(0,'GAIN?','GAIN ')
    proof['original_lpf']=bridge.radio_command(0,'LPF?','LPF ')
    try:
        if args.hardware_gain:bridge.radio_command(0,'GAIN HARDWARE','OK')
        if args.lpf64:bridge.radio_command(0,'LPF 64','OK')
        proof['gain_readback']=bridge.radio_command(0,'GAIN?','GAIN ')
        proof['lpf_readback']=bridge.radio_command(0,'LPF?','LPF ')
        if args.hardware_gain and proof['gain_readback'].split()[1]!='HARDWARE':raise RuntimeError('Hardware gain readback mismatch')
        if args.lpf64 and proof['lpf_readback'].split()[1]!='64':raise RuntimeError('LPF desired-code readback mismatch')
        for index in range(args.attempts):
            if index:time.sleep(2.05) # Additional host gap; firmware also enforces2s.
            phase=getattr(args,'phase_pad',None)
            row=attempt(bridge,owner,args,args.run+index,PADS[index] if phase is None else phase)
            proof['attempts'].append(row)
            proof['tx_start_requested']=any(item.get('tx_start_requested',False) for item in proof['attempts'])
            if row.get('ota64_confirmed'):break # Avoid additional RF once qualified.
            if not row.get('cleanup',{}).get('tx_idle_verified') or not row.get('cleanup',{}).get('mirror_cancel_verified'):break
        proof['completed']=bool(proof['attempts']) and all(row.get('completed') for row in proof['attempts'])
        proof['ota64_confirmed']=any(row.get('ota64_confirmed') for row in proof['attempts'])
    finally:
        original=proof['original_gain'].split()
        gain='GAIN HARDWARE' if original[1]=='HARDWARE' else 'GAIN MANUAL '+original[2]
        lpf=proof['original_lpf'].split()[1]
        for name,command,prefix in (('gain_restore',gain,'OK'),('lpf_restore','LPF AUTO' if lpf=='-1' else 'LPF '+lpf,'OK')):
            try:proof[name]=bridge.radio_command(0,command,prefix)
            except Exception as exc:proof[name+'_error']=str(exc);proof['completed']=False
    after=bridge.status();proof['bridge_after']=after
    proof['transport_error_deltas']={key:(after[key]-before[key])&0xffffffff for key in ('host_command_errors','radio_framing_errors','capture_errors','text_drops')}
    proof['transport_clean']=not any(proof['transport_error_deltas'].values())
    if not proof['transport_clean']:proof['ota64_confirmed']=False
    proof['finished_unix']=time.time()
    return proof


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transmit',action='store_true',required=True,help='explicit permission for bounded RF jobs')
    p.add_argument('--output',type=Path,required=True,help='new proof file; never overwrite')
    p.add_argument('--port');p.add_argument('--attempts',type=int,default=1)
    p.add_argument('--channel',type=int,default=8,help='Wi-Fi channel1..11; shared native TX and raw RX tuning')
    p.add_argument('--conjugate-q',type=int,choices=(0,1),default=0,help='on-device Nios input conjugation; host raw remains unchanged')
    p.add_argument('--phase-pad',type=int,help='explicit0..14 forwarding bytes; requires attempts1')
    p.add_argument('--save-raw',action='store_true',help='archive exact CI8 transport bytes privately; output must be in cyberether/run')
    p.add_argument('--count',type=int,default=2);p.add_argument('--power',type=int,default=8)
    p.add_argument('--samples',type=int,choices=(8192,16380),default=8192)
    p.add_argument('--run',type=lambda s:int(s,0),default=1);p.add_argument('--seed',type=lambda s:int(s,0),default=1)
    p.add_argument('--decode-timeout',type=float,default=600)
    p.add_argument('--monitor',action='store_true',help='also start passive PMOD B packet observation')
    p.add_argument('--hardware-gain',action='store_true',help='temporarily select receiver hardware AGC')
    p.add_argument('--lpf64',action='store_true',help='temporarily request LPF code64; uncalibrated bandwidth')
    args=p.parse_args(argv)
    try:validate_args(args)
    except ValueError as exc:p.error(str(exc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with args.output.open('x',encoding='utf-8') as stream:
            proof={'completed':False,'ota64_confirmed':False,'tx_start_requested':False}
            json.dump({'completed':False,'status':'reserved-before-device-access'},stream);stream.flush()
            try:
                args.raw_dir=reserve_raw_directory(args.output) if args.save_raw else None
                if args.raw_dir is not None:proof['raw_archive_directory']=str(args.raw_dir.relative_to(ROOT.resolve()))
                provenance=reader.artifact_guard()
                with reader.LOCK.open('a') as lease:
                    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with NiosFir(pause_monitor=False) as owner:
                        # Version/cancel capability is checked again per attempt.
                        with CaptureMonitorBridge(args.port,background=True) as bridge:
                            try:
                                proof=run(bridge,owner,args,proof=proof)
                            finally:
                                # Setup failures before attempt() must still
                                # stop both radios. WCANCEL is attempted only
                                # when the installed app advertises support.
                                try:
                                    caps=reader.checked(owner,'WVERSION',required=('cancel_supported',))
                                    capable=caps['cancel_supported']==1
                                except Exception:capable=False
                                proof['final_cleanup']=cleanup(bridge,owner,cancel_mirror=capable)
                                if not proof['final_cleanup'].get('tx_idle_verified') or not proof['final_cleanup'].get('monitor_stop_verified') or (capable and not proof['final_cleanup'].get('mirror_cancel_verified')):
                                    proof['completed']=False;proof['ota64_confirmed']=False
                proof['artifact_provenance']=provenance
            except Exception as exc:proof.update(completed=False,error=str(exc))
            stream.seek(0);json.dump(proof,stream,indent=2);stream.write('\n');stream.truncate()
        print(json.dumps(proof,indent=2));return 0 if proof.get('ota64_confirmed') and proof.get('completed') else 2
    except OSError as exc:print('wifi64_capture_ota: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
