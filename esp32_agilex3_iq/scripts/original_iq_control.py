#!/usr/bin/env python3
"""One explicit original-chip amplitude job and independent raw RX snapshot.

No programming, automatic repetition, waveform DSP, BER or custom-QAM claim.
Run only after the diagnostic is installed on PMOD A and stage11 restored.
"""
from __future__ import annotations
import argparse,fcntl,json,os,sys,time
from pathlib import Path
from common import ROOT
from wifi64_capture_ota import CaptureMonitorBridge,arm_bridge,save_raw
from nios_fir import NiosFir
from wifi64_capture import checked,artifact_guard

class OriginalIqBridge(CaptureMonitorBridge):
    """Detect a diagnostic panic/reboot immediately; cleanup remains usable."""
    watch_faults=False
    def _ingest(self,frame):
        super()._ingest(frame)
        if self.watch_faults and frame.kind==3 and frame.source==1:
            line=frame.payload.decode('ascii',errors='replace')
            if any(marker in line for marker in ('stack overflow','Guru Meditation','panic\'ed','OIQ,READY,')):
                self.watch_faults=False
                raise RuntimeError('PMOD A diagnostic fault/reboot during job: '+line.strip())

def fields(line):
    return dict(piece.split('=',1) for piece in line.split(',') if '=' in piece)

def job_command(code,milliseconds,level=None,period=None):
    if type(milliseconds) is not int or not 3<=milliseconds<=50:raise ValueError('Requested duration must be3..50ms')
    if code is not None and (type(code) is not int or not 120<=code<=127):raise ValueError('Trial code must be120..127')
    if level is not None and (code is not None or type(level) is not int or not 0<=level<=127):raise ValueError('One level0..127 or attenuation code required')
    if period is not None:
        selected=level if level is not None else code
        if selected is None or type(selected) is not int or not 0<=selected<=127 or type(period) is not int or not 32<=period<=128:raise ValueError('Training requires a code and32..128us period')
        return f'TRAIN {selected} {milliseconds} {period}'
    if level is not None:return f'LEVEL {level} {milliseconds}'
    if code is None:return f'CONTROL {milliseconds}'
    return f'ATTEN {code} {milliseconds}'

def idle(bridge,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        line=bridge.radio_command(1,'INFO','OIQ,INFO,',timeout=2)
        bridge.wait_text(1,'OIQ,IDENT,',2)
        if fields(line).get('busy')=='0':return line
        time.sleep(.02)
    raise TimeoutError('Diagnostic did not report idle')

def run(args):
    level=getattr(args,'level',None);period=getattr(args,'train_period_us',None)
    command=job_command(args.atten,args.milliseconds,level,period)
    if not args.transmit:raise ValueError('--transmit explicitly required')
    output=Path(args.output).resolve();output.relative_to((ROOT/'cyberether/run').resolve())
    # Reserve all evidence paths before hardware access; never overwrite captures.
    output.parent.mkdir(parents=True,exist_ok=True)
    proof={'kind':'original ESP32 attenuation hypothesis', 'completed':False,
           'tx_requested':False,'arbitrary_iq_verified':False,'qam_verified':False,
           'host_dsp':False,'ber_measured':False,'command':command,
           'snapshot_scope':'Sparse raw snapshot; no assumed plateau or transition alignment',
           'requested_delay_ms':args.capture_delay_ms,'started_unix':time.time()}
    with output.open('x') as record:
      try:
        private=output.with_name(output.stem+'.private');private.mkdir(mode=0o700,exist_ok=False)
        with (ROOT/'cyberether/run/rf-link-capture.lock').open('a') as lease:
          fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
          artifact_guard()
          with NiosFir(pause_monitor=False) as owner:
            checked(owner,'WCANCEL',required=('state','valid'))
            with OriginalIqBridge(args.port,background=True) as bridge:
              original_gain=None
              try:
                bridge.control(2,1,2000000)
                info=bridge.radio_command(1,'INFO','OIQ,INFO,');ident=bridge.wait_text(1,'OIQ,IDENT,',2)
                if fields(info).get('chip')!='esp32' or fields(info).get('iq')!='unverified' or fields(info).get('busy')!='0':raise RuntimeError('Wrong/busy diagnostic image')
                if fields(info).get('v')=='2':raise RuntimeError('V2 diagnostic has a known PHY-init stack overflow; install corrected V3 before RF')
                if (level is not None or period is not None) and (fields(info).get('v') not in ('2','3') or fields(info).get('amp_train')!='1'):raise RuntimeError('LEVEL/TRAIN requires installed v2+ amplitude firmware')
                if fields(ident).get('mac','').lower()!=args.expect_mac.lower():raise RuntimeError('PMOD A identity mismatch')
                proof.update(identity=ident,info=info,receiver=bridge.prepare_sdr(0,2447,40000000))
                original_gain=bridge.radio_command(0,'GAIN?','GAIN ')
                gain_code=getattr(args,'rx_gain',None)
                requested_gain='GAIN HARDWARE' if gain_code is None else 'GAIN MANUAL '+str(gain_code)
                bridge.radio_command(0,requested_gain,'OK')
                proof['gain']=bridge.radio_command(0,'GAIN?','GAIN ')
                expected_gain='GAIN HARDWARE ' if gain_code is None else f'GAIN MANUAL {gain_code} '
                if not proof['gain'].startswith(expected_gain):raise RuntimeError('Experiment gain mode/code readback mismatch')
                job=arm_bridge(bridge,16380)
                proof['tx_requested']=True;bridge.watch_faults=True;bridge.radio_write(1,command+'\n')
                proof['start']=bridge.wait_text(1,'OIQ,START,',3)
                # Host scheduling is not an RF trigger. Firmware edges are saved
                # separately; no plateau/phase label is assigned to the samples.
                time.sleep(args.capture_delay_ms/1000)
                bridge.radio_write(0,'CAP16 16380 1\n')
                frame=bridge.capture(job,16380,timeout=8,expected_frequency=2447000000)
                proof['snapshot']=frame.metadata();proof['archive']=save_raw(frame,private,job)
                proof['done']=bridge.wait_text(1,'OIQ,DONE,',8)
                if fields(proof['done']).get('job')!=fields(proof['start']).get('job'):raise RuntimeError('Diagnostic job mismatch')
                d=fields(proof['done'])
                proof['register_trial_qualified']=all(d.get(k)=='1' for k in ('gain_restored','fields_ok','rf_off'))
                proof['physical_rf_off_measured']=False
                proof['completed']=True
              finally:
                bridge.watch_faults=False
                failures=[]
                for name,action in [
                  ('stop',lambda:bridge.radio_command(1,'STOP','OIQ,STOP,',3)),
                  ('idle',lambda:idle(bridge)),
                  ('bridge_cancel',lambda:bridge.control(6,0)),
                  ('mirror_cancel',lambda:checked(owner,'WCANCEL',required=('state','valid')))]:
                    try:proof[name]=str(action())
                    except Exception as e:failures.append(name+': '+str(e))
                if original_gain is not None:
                    try:
                        parts=original_gain.split();restore='GAIN HARDWARE' if parts[1]=='HARDWARE' else 'GAIN MANUAL '+parts[2]
                        bridge.radio_command(0,restore,'OK');proof['restored_gain']=bridge.radio_command(0,'GAIN?','GAIN ')
                        if proof['restored_gain']!=original_gain:failures.append('gain restoration readback mismatch')
                    except Exception as e:failures.append('gain restoration: '+str(e))
                proof['radio_lines']=list(bridge.observed_radio_lines)
                proof['cleanup_errors']=failures
                if failures:raise RuntimeError('; '.join(failures))
      except BaseException as error:
        proof.update(completed=False,error=str(error));raise
      finally:
        proof['finished_unix']=time.time();record.write(json.dumps(proof,indent=2)+'\n');record.flush()
    return proof

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transmit',action='store_true',required=True)
    codes=parser.add_mutually_exclusive_group()
    codes.add_argument('--atten',type=int,choices=range(120,128))
    codes.add_argument('--level',type=int,choices=range(128),help='v2+: explicit amplitude code0..127; use the corrected v3 firmware')
    parser.add_argument('--train-period-us',type=int,choices=range(32,129),help='v2+: alternate baseline/trial at requested period; scheduling gaps are recorded')
    parser.add_argument('--milliseconds',type=int,choices=range(3,51),default=50)
    parser.add_argument('--capture-delay-ms',type=int,choices=range(31),default=10)
    parser.add_argument('--rx-gain',type=int,choices=range(128),help='Explicit manual RX gain code; omitted keeps hardware AGC')
    parser.add_argument('--expect-mac',required=True);parser.add_argument('--port')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:result=run(args);print(json.dumps(result,indent=2));return 0
    except Exception as error:print('original_iq_control: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
