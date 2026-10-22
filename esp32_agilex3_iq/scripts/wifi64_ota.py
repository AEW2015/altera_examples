#!/usr/bin/env python3
"""Explicit bounded native Wi-Fi TX + independent ESP32 packet/rate proof.

Host only transports and parses device telemetry. No host waveform/DSP/BER.
Opening/importing this module does not access hardware or start RF.
"""
from __future__ import annotations
import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from wifi64_control import LOCK,fields,transmit,validate_request,query,poll_idle
from wifi64_records import LineAssembler,Wifi64MonitorJoiner,expected_packet_map

MON='WIFI64_MON,'
RUN_DIR=ROOT/'cyberether/run'
LATEST_POINTER=RUN_DIR/'wifi64-ota-latest.json'

def validate_output_path(path):
    run_dir=RUN_DIR.resolve()
    resolved=Path(path).resolve()
    try:relative=resolved.relative_to(run_dir)
    except ValueError as exc:raise ValueError('Published proof output must resolve inside '+str(run_dir)) from exc
    if not relative.parts:raise ValueError('Proof output path must name a file inside the run directory')
    return resolved

def failure_proof(error):
    return {'kind':'independent native Wi-Fi64 OTA packet observation',
            'source':'ota-native-wifi64','finished_unix':time.time(),
            'error':str(error),'completed':False}

def publish_proof(output,pointer=None):
    """Atomically publish a repo-relative pointer to a closed proof file."""
    output=validate_output_path(output).resolve(strict=True)
    if not output.is_file():raise ValueError('Published proof output is not a file')
    relative=output.relative_to(ROOT.resolve()).as_posix()
    target=Path(pointer) if pointer is not None else LATEST_POINTER
    target.parent.mkdir(parents=True,exist_ok=True)
    payload={'path':relative}
    fd,temp_name=tempfile.mkstemp(prefix='.wifi64-ota-latest.',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(payload,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp_name,target)
    except BaseException:
        try:os.unlink(temp_name)
        except OSError:pass
        raise
    return payload

class MonitorBridge(Bridge):
    """Retain every radio's text while commands wait for another radio.

    IQB1 text envelopes contain complete UART lines: FPGA strips their newline.
    Newline is restored at each envelope boundary for the bounded assembler.
    CRC checking remains in Bridge.read_frame; this adapter never bypasses it.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.text_queues={n:collections.deque() for n in range(3)}
        self.assemblers={n:LineAssembler() for n in range(3)}
        self.monitor_lines=[]

    def _ingest(self,frame):
        if getattr(frame,'_wifi64_ingested',False):return
        frame._wifi64_ingested=True
        if frame.kind!=3:return
        # Assemblers support newline-delimited byte streams; the FPGA envelope
        # itself replaces the delimiter when forwarding a complete UART line.
        data=frame.payload if frame.payload.endswith(b'\n') else frame.payload+b'\n'
        for line in self.assemblers[frame.source].feed(data):
            if len(self.text_queues[frame.source])>=1024:raise BufferError('Radio text queue exceeded1024lines')
            self.text_queues[frame.source].append(line)
            if frame.source==2:
                if len(self.monitor_lines)>=1024:raise BufferError('Monitor exceeded1024lines')
                self.monitor_lines.append(line)

    def read_frame(self,*args,**kwargs):
        frame=super().read_frame(*args,**kwargs);self._ingest(frame);return frame

    def _next(self,timeout):
        frame=self.responses.popleft() if self.responses else self.read_frame(timeout)
        self._ingest(frame)
        if frame.kind==5:raise RuntimeError(f'FPGA error {frame.error:#x}')
        if frame.kind in (1,6):raise RuntimeError('Unexpected IQ capture during packet-only monitor job')
        return frame

    def wait_text(self,source,prefix,timeout=4):
        deadline=time.monotonic()+timeout
        while True:
            queue=self.text_queues[source]
            for index,line in enumerate(queue):
                if line.startswith(prefix):
                    del queue[index];return line
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError(f'No radio response {prefix!r}')
            self._next(remaining)

    def collect(self,seconds=1):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:self._next(max(.001,deadline-time.monotonic()))
            except TimeoutError:break


def monitor_command(bridge,command,verb,timeout=4):
    line=bridge.radio_command(2,command,MON+verb+',',timeout)
    parsed=fields(line)
    if parsed.get('record')!=verb or parsed.get('error','0')!='0':raise RuntimeError('Monitor command failed: '+line)
    return line


def run_job(bridge,args):
    proof={'kind':'independent native Wi-Fi64 OTA packet observation','source':'ota-native-wifi64',
           'host_processing':'transport and telemetry parsing only; no host DSP or BER',
           'raw_iq_decoded':False,'pre_fec_ber_measured':False,'completed':False,
           'monitor':{},'transmitter':{},'started_unix':time.time()}
    monitor_started=False
    try:
        bridge.control(2,1,2_000_000);bridge.control(2,2,2_000_000)
        proof['fpga_baseline_status']=bridge.status()
        proof['monitor']['info_line']=monitor_command(bridge,'INFO','INFO')
        proof['monitor']['initial_stop_line']=monitor_command(bridge,'STOP','STOP')
        baseline=monitor_command(bridge,'STATUS','STATUS');proof['monitor']['baseline_status_line']=baseline
        if fields(baseline).get('listening')!='0':raise RuntimeError('Monitor did not stop before job')
        listen=monitor_command(bridge,f'LISTEN {args.channel} 10000','LISTEN')
        if fields(listen).get('ok')!='1' or fields(listen).get('ch')!=str(args.channel):raise RuntimeError('Monitor LISTEN readback mismatch')
        proof['monitor']['listen_line']=listen;monitor_started=True
        # The preceding STOP/STATUS/LISTEN handshake bounds this observation.
        bridge.monitor_lines.clear()
        proof['transmitter']=transmit(bridge,args)
        bridge.collect(1)
    except Exception as exc:proof['error']=str(exc)
    finally:
        # A receiver/setup failure must still leave an explicit TX-off proof.
        try:
            proof["final_tx_stop_line"]=query(bridge,"STOP","STOP")
            proof["final_tx_idle_line"]=poll_idle(bridge)
            proof["final_tx_idle_verified"]=True
        except Exception as exc:proof["final_tx_idle_error"]=str(exc)
        try:
            stop=monitor_command(bridge,'STOP','STOP');proof['monitor']['stop_line']=stop
            state=monitor_command(bridge,'STATUS','STATUS');proof['monitor']['status_line']=state
            proof['monitor']['stopped_verified']=fields(stop).get('listening')=='0' and fields(state).get('listening')=='0'
        except Exception as exc:proof['monitor']['stop_error']=str(exc)
    try:
        proof['fpga_final_status']=bridge.status()
        before=proof.get('fpga_baseline_status',{})
        proof['fpga_error_deltas']={key:(proof['fpga_final_status'][key]-before[key])&0xffffffff for key in ('host_command_errors','radio_framing_errors','capture_errors','text_drops')}
        proof['fpga_transport_clean']=not any(proof['fpga_error_deltas'].values())
    except Exception as exc:proof['fpga_status_error']=str(exc)
    lines=list(bridge.monitor_lines) if monitor_started else []
    proof['monitor']['lines']=lines
    try:
        joiner=Wifi64MonitorJoiner(expected=expected_packet_map(args.run,args.count,args.seed))
        for line in lines:joiner.feed(line)
        audit=joiner.audit()
        audit['duplicates']=[{'run':key[0],'packet':key[1],'types':kinds} for key,kinds in audit['duplicates'].items()]
        audit['joined']=list(audit['joined'].values())
        proof['monitor']['audit']=audit
        observed=[joiner.joined((args.run,i)) for i in range(args.count)]
        proof['monitor']['expected_observations']=observed
        good=[r for r in observed if r and r.get('qualified') and r.get('channel')==args.channel and r.get('length')==92]
        proof['monitor']['qualified_packets']=len(good)
        proof['native_rate54_observed_over_air']=bool(good)
        proof['all_requested_packets_observed']=len(good)==args.count
        state=fields(proof['monitor'].get('status_line',''))
        baseline=fields(proof['monitor'].get('baseline_status_line',''))
        drops=(int(state.get('drops','0'))-int(baseline.get('drops','0')))&0xffffffff
        proof['monitor']['drop_delta']=drops
        proof['completed']=bool(proof['transmitter'].get('tx_success') and proof.get('final_tx_idle_verified') and proof['monitor'].get('stopped_verified') and proof.get('fpga_transport_clean') and len(good)==args.count and drops==0 and 'error' not in proof)
    except Exception as exc:proof['audit_error']=str(exc)
    proof['finished_unix']=time.time()
    return proof


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transmit',action='store_true',required=True,help='explicitly permit one bounded native RF packet job')
    p.add_argument('--output',type=Path,required=True,help='new proof JSON, never overwrite')
    p.add_argument('--publish',action='store_true',help='atomically update the read-only latest-proof pointer')
    p.add_argument('--port');p.add_argument('--channel',type=int,default=8);p.add_argument('--count',type=int,default=4)
    p.add_argument('--power',type=int,default=8);p.add_argument('--gap',type=int,default=2)
    p.add_argument('--run',type=lambda x:int(x,0),default=time.time_ns()&0xffffffff)
    p.add_argument('--seed',type=lambda x:int(x,0),default=1)
    args=p.parse_args(argv)
    try:
        validate_request(args)
        if args.publish:args.output=validate_output_path(args.output)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        # Reserve before any device opens: an existing path never triggers RF.
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump({'completed':False,'status':'reserved-before-device-access'},stream);stream.flush()
            try:
                LOCK.parent.mkdir(parents=True,exist_ok=True)
                with LOCK.open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with MonitorBridge(args.port) as bridge:proof=run_job(bridge,args)
            except Exception as exc:proof=failure_proof(exc)
            stream.seek(0);json.dump(proof,stream,indent=2);stream.write('\n');stream.truncate()
        if args.publish:publish_proof(args.output)
        print(json.dumps(proof,indent=2));return 0 if proof.get('completed') else 2
    except (OSError,RuntimeError,ValueError) as exc:
        print('wifi64_ota: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
