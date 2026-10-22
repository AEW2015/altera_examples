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

def fields(line):
    return dict(piece.split('=',1) for piece in line.split(',') if '=' in piece)

def job_command(code,milliseconds):
    if type(milliseconds) is not int or not 3<=milliseconds<=50:raise ValueError('Requested duration must be3..50ms')
    if code is None:return f'CONTROL {milliseconds}'
    if type(code) is not int or not 120<=code<=127:raise ValueError('Trial code must be120..127')
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
    command=job_command(args.atten,args.milliseconds)
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
            with CaptureMonitorBridge(args.port,background=True) as bridge:
              original_gain=None
              try:
                bridge.control(2,1,2000000)
                info=bridge.radio_command(1,'INFO','OIQ,INFO,');ident=bridge.wait_text(1,'OIQ,IDENT,',2)
                if fields(info).get('chip')!='esp32' or fields(info).get('iq')!='unverified' or fields(info).get('busy')!='0':raise RuntimeError('Wrong/busy diagnostic image')
                if fields(ident).get('mac','').lower()!=args.expect_mac.lower():raise RuntimeError('PMOD A identity mismatch')
                proof.update(identity=ident,info=info,receiver=bridge.prepare_sdr(0,2447,40000000))
                original_gain=bridge.radio_command(0,'GAIN?','GAIN ')
                bridge.radio_command(0,'GAIN HARDWARE','OK')
                proof['gain']=bridge.radio_command(0,'GAIN?','GAIN ')
                if not proof['gain'].startswith('GAIN HARDWARE '):raise RuntimeError('Fixed experiment gain mode readback mismatch')
                job=arm_bridge(bridge,16380)
                proof['tx_requested']=True;bridge.radio_write(1,command+'\n')
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
    parser.add_argument('--atten',type=int,choices=range(120,128))
    parser.add_argument('--milliseconds',type=int,choices=range(3,51),default=50)
    parser.add_argument('--capture-delay-ms',type=int,choices=range(31),default=10)
    parser.add_argument('--expect-mac',required=True);parser.add_argument('--port')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:result=run(args);print(json.dumps(result,indent=2));return 0
    except Exception as error:print('original_iq_control: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
