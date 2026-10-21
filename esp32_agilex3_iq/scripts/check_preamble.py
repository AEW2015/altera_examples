#!/usr/bin/env python3
"""Verify checkpoint08 preamble RTL using IQ replay or one passive RF capture.

No command in this script starts a transmitter. --synthetic means FPGA replay
of Python-generated CI8, not over-the-air transmission. --passive observes
PMOD B SPI RF, with the detector connected directly to capture writes.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import zlib
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from nios_fir import NiosFir
from preamble_reference import scan
from rf_qpsk import synthesize


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)


def saved_origin(path,raw):
    result=dict(kind='saved_iq_replay',description='Saved CI8 uploaded to FPGA; no new RF transmission',file=str(path))
    try:
        proof=json.loads(path.with_name('proof.json').read_text())
        sha=hashlib.sha256(raw).hexdigest()
        rows=[r for r in proof.get('rows',[]) if r.get('transport',{}).get('payload_sha256')==sha]
        if len(rows)==1:
            result.update(original_kind=proof.get('kind'),original_transport=rows[0]['transport'],original_config=rows[0].get('config'),
                original_host_candidates=[{k:c.get(k) for k in ('start_sample','sync_errors','crc_ok')} for c in rows[0].get('report',{}).get('candidates',[])])
    except (OSError,ValueError,TypeError):pass
    return result


def verify_passive_spi(frame,before,after):
    if (frame.kind,frame.source,frame.samples,frame.rate,frame.frequency)!=(1,2,16380,16000000,2447000000):
        raise ValueError('Wrong passive SPI capture profile')
    advance=(after['commit_count']-before['commit_count'])&0xffffffff
    if not 0<advance<0x80000000 or not after['valid'] or after['synthetic'] or after['requested_synthetic'] or not after['ingress_cycles']:
        raise ValueError('Passive RF requires a fresh committed non-synthetic SPI capture')
    if before['valid'] and not 0<(after['sequence']-before['sequence'])&0xffffffff<0x80000000:
        raise ValueError('Passive SPI capture sequence did not advance')


def run(args):
    if args.output.exists():raise FileExistsError('Choose a new output directory')
    args.output.mkdir(parents=True)
    wall_start=time.monotonic()
    result=dict(started_at=time.time(),schema='fpga-preamble-v1',status='RUNNING',completed=False,tx_started=False,
        processing='Agilex 3: averaging, differential products, training correlation, normalization and peak detection; host: independent integer reference and plotting')
    def publish():
        result['updated_at']=time.time();atomic(args.output/'proof.json',result)
        if args.snapshot:atomic(args.snapshot,result)
    publish()
    try:
        active=json.loads((ROOT/'cyberether/run/active-fpga.json').read_text())
        if active.get('checkpoint')!=8 or not active.get('fpga_preamble'):raise RuntimeError('Program checkpoint08 explicitly before this check')
        result['image']=dict(sha256=active['sha256'],source_fingerprint=active['source_fingerprint'],checkpoint=8,scope='Local programming manifest hint, not a device-read image hash; actual block identity is probed separately')
        sps=round(16*args.symbol_us)
        if not 128<=sps<=240:raise ValueError('Symbol period must produce128..240samples/symbol')
        iq=None
        if args.input:
            raw=args.input.read_bytes()
            if len(raw)%2 or not 1<=len(raw)//2<=16384:raise ValueError('CI8 file must contain1..16384completeIQpairs')
            iq=np.frombuffer(raw,np.int8).reshape(-1,2);origin=saved_origin(args.input,raw)
        elif args.synthetic:
            iq=synthesize(payload=60,symbol_us=args.symbol_us,samples=10000,cfo_hz=17321.,seed=8)
            origin=dict(kind='synthetic_iq_replay',description='Python phase-ramp QPSK uploaded to FPGA, no radio transmission')
        else:origin=dict(kind='physical_rf',description='One passive PMOD B SPI snapshot, directly observed by FPGA detector; no TX command')
        n=len(iq) if iq is not None else 16380
        if n<31*sps+16:raise ValueError('Input cannot contain the complete32-symbol training window')
        result.update(provenance=origin,requested=dict(samples=n,sps=sps,stride=4,window=16,threshold_q15=args.threshold,min_energy=7936))
        publish()
        with ExitStack() as stack:
            lease=stack.enter_context((ROOT/'cyberether/run/rf-link-capture.lock').open('a'))
            try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Another acquisition owns the FPGA') from None
            control=stack.enter_context(NiosFir(log=args.output/'nios.log',pause_monitor=False))
            status=control.command('PSTATUS')
            if status['identity']!=0x50520801:raise RuntimeError('Actual FPGA preamble identity mismatch')
            control.command('PCLEAR')
            def clear_detector():
                control.command('PCLEAR')
                cleared=control.command('PSTATUS')
                if cleared['state'] or cleared['errors'] or cleared['written'] or cleared['candidates']:
                    raise RuntimeError(('Detector cleanup readback mismatch',cleared))
                result['cleanup_readback']=cleared
            stack.callback(clear_detector)
            config=control.command('PCONFIG',n,sps,args.threshold)
            if any(config[k]!=v for k,v in dict(samples=n,sps=sps,step=4,threshold=args.threshold,min_energy=7936).items()):raise ValueError('Detector configuration readback mismatch')
            result['configured']=config
            result['actual_block_identity']=status['identity']
            if iq is not None:
                raw=iq.astype(np.int8).tobytes();upload_start=time.monotonic();control.command('PBEGIN')
                for base in range(0,n,128):
                    calls=[];ends=[]
                    for offset in range(base,min(n,base+128),16):
                        block=raw[2*offset:2*min(n,offset+16)]
                        calls.append(('PLOAD',offset,block.hex()));ends.append(offset+len(block)//2)
                    replies=control.commands(calls)
                    if [r['written'] for r in replies]!=ends:raise ValueError('FPGA replay offset/count mismatch')
                    if base%2048==0 or ends[-1]==n:
                        result['progress']=dict(stage='Upload replay IQ',completed=ends[-1],total=n);publish()
                        print(f'Upload IQ {ends[-1]}/{n}',flush=True)
                control.command('PFINISH')
                result['replay_upload_seconds']=time.monotonic()-upload_start
            else:
                from iq_bridge import Bridge
                from check_spi_fir import spi_status
                bridge=stack.enter_context(Bridge(args.port))
                identity=bridge.prepare_sdr(2,2447,16000000)
                if 'SPI_PROXY' not in identity:raise ValueError('Actual SPI proxy identity mismatch')
                old=spi_status(bridge.radio_command(2,'SPI?','SPI '))
                mode='SYNTH' if old['requested_synthetic'] else 'RF'
                def restore_spi_mode():
                    if bridge.radio_command(2,'SPI_MODE '+mode,'OK SPI_MODE ')!='OK SPI_MODE '+mode:
                        raise RuntimeError('SPI mode restoration acknowledgement mismatch')
                    restored=spi_status(bridge.radio_command(2,'SPI?','SPI '))
                    if restored['requested_synthetic']!=old['requested_synthetic']:
                        raise RuntimeError('SPI requested-mode restoration mismatch')
                    result['spi_mode_restored']=restored
                stack.callback(restore_spi_mode)
                if bridge.radio_command(2,'SPI_MODE RF','OK SPI_MODE ')!='OK SPI_MODE RF':raise ValueError('SPI RF mode mismatch')
                baseline=spi_status(bridge.radio_command(2,'SPI?','SPI '))
                control.command('PARM',2)
                frame=next(bridge.captures(1,2,n,16000000,pipeline=False));iq=frame.iq();raw=frame.payload
                after=spi_status(bridge.radio_command(2,'SPI?','SPI '))
                verify_passive_spi(frame,baseline,after)
                result['transport']=frame.metadata();result['spi_before']=baseline;result['spi_after']=after
            frozen=control.command('PSTATUS')
            if not frozen['state']&2 or frozen['state']&16 or frozen['errors'] or frozen['samples']!=n or frozen['raw_crc']!=zlib.crc32(raw):raise ValueError(('Frozen buffer count/CRC/status mismatch',frozen))
            if args.passive and (frozen['job'],frozen['source'],frozen['rate'],frozen['frequency'])!=(frame.job,2,frame.rate,frame.frequency):raise ValueError('Physical capture identity mismatch')
            if not args.passive and frozen['source']!=3:raise ValueError('Replay must be identified as source3')
            result['frozen']=frozen;result['input_sha256']=hashlib.sha256(raw).hexdigest();(args.output/'input.ci8').write_bytes(raw)
            result['progress']=dict(stage='FPGA correlation');publish()
            print('Running FPGA differential preamble correlation',flush=True);control.command('PRUN');deadline=time.monotonic()+30
            while True:
                state=control.command('PSTATUS')
                if state['state']&16 or state['errors']:raise ValueError(('FPGA detector error',state))
                if state['state']&4 and not state['state']&1:break
                if time.monotonic()>deadline:raise TimeoutError('Preamble detector did not complete')
                time.sleep(.01)
            expected=scan(iq,sps=sps,threshold_q15=args.threshold)
            if state['candidates']!=len(expected['starts']):raise ValueError('FPGA candidate count mismatch')
            trace=[]
            for offset in range(0,state['candidates'],32):
                count=min(32,state['candidates']-offset);reply=control.command('PTRACES',offset,count)
                if (reply['index'],reply['count'])!=(offset,count):raise ValueError('Trace offset/count mismatch')
                trace.extend(reply['v'+str(i)] for i in range(count))
                if offset%512==0:
                    result['progress']=dict(stage='Verify score trace',completed=len(trace),total=state['candidates']);publish()
            if trace!=expected['scores_q15']:raise AssertionError('FPGA correlation trace differs from independent integer reference')
            for name in ('best_start','best_score'):
                if state[name]!=expected[name if name=='best_start' else 'best_score_q15']:raise AssertionError('FPGA peak mismatch: '+name)
            if bool(state['state']&32)!=expected['detected']:raise AssertionError('FPGA threshold decision mismatch')
            result.update(hardware=state,verification=dict(full_trace_bit_exact=True,max_q15_error=0,input_crc_verified=True,candidates=len(trace)),
                detected=expected['detected'],buffer_coverage=dict(complete54symbol_window_fits=expected['best_start']+53*sps+16<=n,scope='Host index/length check only; no payload decode or CRC claim'),reference=dict(best_start=expected['best_start'],best_score_q15=expected['best_score_q15']),
                plots=dict(correlation=dict(x=expected['starts'],fpga=trace,reference=expected['scores_q15']),
                    iq=dict(i=iq[::8,0].tolist(),q=iq[::8,1].tolist(),x=list(range(0,n,8)))),
                timing=dict(fpga_cycles=state['cycles'],fpga_seconds=state['cycles']/50e6,clock_hz=50000000),
                scope='Coarse preamble sample-window alignment, not precise TX boundary, carrier lock, payload demap or CRC success')
        result.update(status='PASS',completed=True,detector_cleared=True,wall_seconds=time.monotonic()-wall_start);publish();print(json.dumps({k:result[k] for k in ('status','detected','reference','verification','timing')},indent=2))
    except BaseException as error:
        result.update(status='ERROR',completed=False,error=str(error) or type(error).__name__);publish();raise
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--synthetic',action='store_true');g.add_argument('--input',type=Path);g.add_argument('--passive',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--snapshot',type=Path);p.add_argument('--symbol-us',type=float,default=10)
    p.add_argument('--threshold',type=int,choices=range(32769),default=24576,metavar='0..32768');p.add_argument('--port')
    args=p.parse_args();signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt('Termination requested')))
    return run(args)


if __name__=='__main__':main()
