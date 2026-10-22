#!/usr/bin/env python3
"""One bounded installed-PHASE QPSK job and independent raw RFS2 snapshot.

Transport and telemetry only. No host synchronization, demapping, FEC or BER.
Requires the combined image; never flashes or programs. --transmit is explicit.
"""
import argparse,fcntl,json,time
from pathlib import Path
from common import ROOT
from tx_lab_control import switch,fields
from wifi64_capture import artifact_guard
from wifi64_capture_ota import CaptureMonitorBridge,arm_bridge,save_raw

def capture_wire(rate=16000000):
    codes={16000000:6,40000000:1,80000000:0}
    if rate not in codes:raise ValueError('Unsupported RX rate')
    return f'CAP16 16380 {codes[rate]}\n'

def quiet(bridge):
    line=bridge.radio_command(1,'MODE?','TXLAB,MODE,')
    if fields(line).get('mode')!='PHASE' or fields(line).get('quiet')!='1':raise RuntimeError('PHASE not quiet')
    state=bridge.radio_command(1,'STATE','TONE_STATE,');parsed=fields(state)
    if any(int(parsed[k],16)&(255<<18) for k in ('tone1','tone2')) or int(parsed['ext'],16)&3:raise RuntimeError('Tone enables not restored')
    return {'mode':line,'state':state}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transmit',action='store_true',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='/dev/ttyUSB0')
    p.add_argument('--payload',type=int,choices=range(256),default=165);a=p.parse_args()
    target=a.output.resolve();target.relative_to((ROOT/'cyberether/run').resolve());target.parent.mkdir(parents=True,exist_ok=True)
    proof={'completed':False,'host_dsp':False,'ber_measured':False,'custom_qam_qualified':False,'scope':'Sparse raw QPSK experiment; no recovered-symbol qualification','started_unix':time.time()}
    with target.open('x') as record:
     try:
      with (ROOT/'cyberether/run/rf-link-capture.lock').open('a') as lease:
       fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);proof['artifacts']=artifact_guard()
       with CaptureMonitorBridge(a.port,background=True) as b:
        gain=None
        try:
         proof['mode']=switch(b,'PHASE')
         proof['info']=b.radio_command(1,'INFO','TX_PROBE,')
         if fields(proof['info']).get('mac')!='78:21:84:d4:4f:98':raise RuntimeError('Wrong PMOD A identity')
         proof['receiver']=b.prepare_sdr(0,2447,16000000)
         gain=b.radio_command(0,'GAIN?','GAIN ');b.radio_command(0,'GAIN MANUAL 0','OK')
         proof['gain']=b.radio_command(0,'GAIN?','GAIN ')
         if proof['gain']!='GAIN MANUAL 0 0 81 1':raise RuntimeError('Wrong RX gain readback')
         b.radio_write(1,'TONE 8 50 120\n');proof['prime_on']=b.wait_text(1,'TX_ON,',10);proof['prime_off']=b.wait_text(1,'TX_OFF,',3)
         proof['prime_quiet']=quiet(b);time.sleep(3)
         job=arm_bridge(b,16380)
         proof['command']=f'QFRAME 8 50 120 {a.payload} 12 335 670 1005'
         b.radio_write(1,proof['command']+'\n');proof['config']=b.wait_text(1,'QFRAME_CFG,',3);proof['on']=b.wait_text(1,'TX_ON,',3)
         config=fields(proof['config']);on=fields(proof['on'])
         if config.get('job')!=on.get('id') or config.get('payload')!=str(a.payload) or on.get('limit_ms')!='50':raise RuntimeError('TX job/config mismatch')
         proof['capture_command']=capture_wire()
         b.radio_write(0,proof['capture_command'])
         end=time.monotonic()+12
         while not b.capture_frames:b._next(max(.001,end-time.monotonic()))
         frame=b.capture_frames.popleft()
         if (frame.kind,frame.job,frame.source,frame.samples,frame.rate,frame.frequency,frame.error)!=(1,job,0,16380,16000000,2447000000,0):raise RuntimeError('Capture profile/job mismatch')
         private=target.with_name(target.stem+'.private');private.mkdir(mode=0o700,exist_ok=False)
         proof['snapshot']=frame.metadata();proof['archive']=save_raw(frame,private,job)
         proof['off']=b.wait_text(1,'TX_OFF,',3)
         if fields(proof['off']).get('id')!=on['id']:raise RuntimeError('TX_OFF job mismatch')
         proof['quiet']=quiet(b);proof['phase_stats']=b.radio_command(1,'PHASESTAT','PHASESTAT,')
         if fields(proof['phase_stats']).get('job')!=on['id']:raise RuntimeError('PHASESTAT job mismatch')
         proof['completed']=True
        finally:
         cleanup=[]
         restore_gain='GAIN HARDWARE' if not gain or gain.startswith('GAIN HARDWARE') else 'GAIN MANUAL '+gain.split()[2]
         for name,action in [('stop',lambda:b.radio_write(1,'STOP\n')),('cancel',lambda:b.control(6,0)),('gain',lambda:b.radio_command(0,restore_gain,'OK')),('mode',lambda:switch(b,'AMP'))]:
          try:action()
          except Exception as error:cleanup.append(name+': '+str(error))
         proof['cleanup_errors']=cleanup;proof['radio_lines']=list(b.observed_radio_lines)
         if cleanup:raise RuntimeError('; '.join(cleanup))
     except BaseException as error:proof.update(completed=False,error=str(error))
     finally:
      proof['finished_unix']=time.time();record.write(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2));return 0 if proof['completed'] else 2
if __name__=='__main__':raise SystemExit(main())
