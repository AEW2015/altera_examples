#!/usr/bin/env python3
"""Bounded alternating SPI snapshots/FIR qualification; no programming or TX.

Sequential snapshots are not a continuous ADC stream. Unobserved RF between
captures has no inferred delivery/drop rate. All hardware access is explicit.
"""
import argparse
from contextlib import ExitStack
import fcntl
from pathlib import Path
import sys
import signal
import time
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir,PROFILES
from check_rf_bpsk import atomic_json
from check_rf_bpsk_fir import signed_taps
from check_spi_fir import spi_status,verify_association
from spi_fir_qualification import snapshot,verify_restoration,restoration_plan


def summary(rows,attempts,error=None,active_attempt=None):
    verified_rejects=sum(r['verification']['spi_reject_counter_change'] for r in rows)
    failed_rejects=None
    active=active_attempt or {}
    if active.get('index') not in {r.get('index') for r in rows} and 'spi_before' in active and 'spi_after' in active:
        failed_rejects=(active['spi_after']['reject_count']-active['spi_before']['reject_count'])&0xffffffff
    return dict(attempts=attempts,verified_pairs=len(rows),failed_attempts=attempts-len(rows),
        synthetic_pairs=sum(r['mode']=='synthetic' for r in rows),rf_pairs=sum(r['mode']=='rf' for r in rows),
        samples_verified=sum(r['verification']['samples'] for r in rows),
        observed_spi_reject_counter_advance=verified_rejects+(failed_rejects or 0),
        verified_pair_spi_reject_counter_advance=verified_rejects,failed_attempt_spi_reject_counter_advance=failed_rejects,
        reject_counter_scope='Known before/after counters only; failed attempt may lack a final counter. Intentional stale/mode boundary discards are not RF packet loss.',
        elapsed_pair_seconds=sum(r['timing']['end_to_end_s'] for r in rows),error=error,
        packet_drop_rate=None,unobserved_gaps='Sequential bounded snapshots, not continuous ADC. No RF drop/delivery rate inferred for capture gaps.')


def termination_requested(_signal,_frame):
    raise KeyboardInterrupt('Termination requested')


def main():
    signal.signal(signal.SIGTERM,termination_requested)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--port')
    p.add_argument('--snapshot',type=Path)
    p.add_argument('--fast-readback',action='store_true',help='Coefficient reads before/after batch; status+integer reference every pair under exclusive ownership')
    p.add_argument('--confirm-spi-image',action='store_true')
    p.add_argument('--captures',type=int,choices=range(1,129),default=16,metavar='1..128')
    p.add_argument('--host-baud',type=int,choices=(2000000,4000000),default=2000000)
    p.add_argument('--profile',type=int,choices=(1,2),default=2)
    args=p.parse_args()
    if not args.confirm_spi_image:p.error('Explicit loaded checkpoint07 required: --confirm-spi-image')
    proof=dict(kind='alternating_spi_fir_snapshot_soak',completed=False,attempts=0,rows=[],
        requested=dict(captures=args.captures,profile=args.profile,round_nearest=True,host_baud=args.host_baud,fast_readback=args.fast_readback),
        coefficient_readback_scope='Before and after batch only; per-pair profile/status and integer reference remain checked under exclusive UART/JTAG ownership' if args.fast_readback else 'Actual coefficient registers read before, after and on every pair',
        scope='Real FPGA SPI/FIR hardware test; generated synthetic and physical RF snapshots separately labelled; no RF transmission by this script')
    lock=ROOT/'cyberether/run/rf-link-capture.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        lease=stack.enter_context(lock.open('a'))
        try:fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another RF/SPI owner is active') from None
        args.output.mkdir(parents=True,exist_ok=False)
        def publish():
            proof['summary']=summary(proof['rows'],proof['attempts'],proof.get('error'),proof.get('active_attempt'))
            atomic_json(args.output/'proof.json',proof)
        publish()
        try:
            bridge=stack.enter_context(Bridge(args.port))
            identity=bridge.prepare_sdr(2,2447,16000000)
            if 'SPI_PROXY' not in identity:raise RuntimeError('Integrated checkpoint07 SPI proxy identity required')
            proof['image_identity']=identity
            latest_view=None
            def restore_baud(exc_type=None,exc=None,tb=None):
                if exc is not None:proof['error']=proof.get('error') or str(exc) or type(exc).__name__
                try:
                    status=bridge.set_host_baud(2000000) if args.host_baud!=2000000 else bridge.status()
                    proof['host_baud_restored']=dict(baud=2000000,status=status)
                    proof['completed']=len(proof['rows'])==args.captures and not proof.get('error')
                    if args.snapshot:
                        if proof['completed'] and latest_view is not None:
                            latest_view['status']='PASS';latest_view['readback']['host_baud_restored']=2000000
                            latest_view['batch']['completed']=True;atomic_json(args.snapshot,latest_view)
                        elif proof.get('error'):atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error=proof['error'],requested=proof['requested'],batch=dict(total=args.captures,verified_pairs=len(proof['rows']),completed=False)))
                    publish()
                except BaseException as error:
                    proof['completed']=False;proof['baud_restore_error']=str(error);publish()
                    if args.snapshot:atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error='Host baud restore failed: '+str(error),requested=proof['requested']))
                    raise
            stack.push(restore_baud)
            proof['host_baud_applied']=dict(baud=args.host_baud,status=bridge.set_host_baud(args.host_baud) if args.host_baud!=2000000 else bridge.status(),
                scope='CRC-valid IQB1 communication at configured host UART rate; SPI stays5MHz')
            nios=stack.enter_context(NiosFir(pause_monitor=False))
            original=nios.status();old_taps=signed_taps(nios)
            proof['fir_original']=dict(status=original,coefficients=old_taps)
            try:
                nios.command('PAIR',0);nios.preset(args.profile)
                if nios.command('ROUND',1).get('nearest')!=1:raise ValueError('ROUND readback mismatch')
                if nios.command('PAIR',1).get('enabled')!=1:raise ValueError('PAIR readback mismatch')
                configured=nios.status();taps=signed_taps(nios)
                if taps!=PROFILES[args.profile] or (configured['pair'],configured['configured_round'],configured['configured_profile'])!=(1,1,args.profile):raise ValueError('FIR applied setting mismatch')
                proof['fir_applied']=dict(status=configured,coefficients=taps)
                for index in range(args.captures):
                    proof['attempts']+=1;publish()
                    mode='SYNTH' if index%2==0 else 'RF'
                    proof['active_attempt']=dict(index=index,mode=mode);publish()
                    if bridge.radio_command(2,'SPI_MODE '+mode,'OK SPI_MODE ')!='OK SPI_MODE '+mode:raise ValueError('SPI mode command mismatch')
                    before=spi_status(bridge.radio_command(2,'SPI?','SPI '))
                    proof['active_attempt']['spi_before']=before;publish()
                    if before['requested_synthetic']!=(mode=='SYNTH'):raise ValueError('SPI requested mode readback mismatch')
                    started=time.monotonic();raw,filtered=bridge.paired_capture(2,16380,16000000,timeout=20)
                    elapsed=time.monotonic()-started
                    (args.output/f'raw-{index:03d}.ci8').write_bytes(raw.payload)
                    (args.output/f'filtered-{index:03d}.ci8').write_bytes(filtered.payload)
                    after=spi_status(bridge.radio_command(2,'SPI?','SPI '));fir=nios.status()
                    proof['active_attempt'].update(raw_transport=raw.metadata(),filtered_transport=filtered.metadata(),spi_after=after,fir_status=fir);publish()
                    actual_taps=taps if args.fast_readback else signed_taps(nios)
                    verified=verify_association(raw,filtered,before,after,actual_taps,fir,synthetic=mode=='SYNTH',profile=args.profile,nearest=True)
                    if mode=='SYNTH' and raw.payload!=bytes((n*37+11)&255 for n in range(len(raw.payload))):raise ValueError('Deterministic ESP32 synthetic bytes differ')
                    ingress=after['ingress_cycles']/50000000.
                    row=dict(index=index,mode='synthetic' if mode=='SYNTH' else 'rf',verification=verified,
                        raw_transport=raw.metadata(),filtered_transport=filtered.metadata(),
                        timing=dict(ingress_s=ingress,fpga_fir_s=fir['cycles']/50000000.,end_to_end_s=elapsed,
                            ingress_payload_bytes_s=len(raw.payload)/ingress,end_to_end_bytes_s=len(raw.payload)/elapsed),
                        spi_before=before,spi_after=after,captured_at=time.time())
                    proof['rows'].append(row);publish()
                    requested=dict(proof['requested'],mode='synthetic' if mode=='SYNTH' else 'rf',source=2,samples=raw.samples,sample_rate_hz=raw.rate,frequency_hz=raw.frequency)
                    latest_view=snapshot(raw.payload,filtered.payload,kind='synthetic_spi_fir_hardware' if mode=='SYNTH' else 'physical_rf_spi_fir',
                        requested=requested,readback=dict(image_identity=identity,mode=requested['mode'],source=2,sequence=after['sequence'],profile=args.profile,round_nearest=True,coefficients=actual_taps,coefficient_readback_scope=proof['coefficient_readback_scope'],host_baud=args.host_baud,spi=after),
                        verification=verified,timing=row['timing'],provenance=dict(origin='PMOD B SPI CI8 → FPGA capture RAM → FIR II → host UART',fpga_processing='SPI packet qualification and16tap FIR II',spi_sequence=after['sequence'],iqb1_job=raw.job,raw_transport=raw.metadata(),filtered_transport=filtered.metadata(),rf_sample_timestamps=False,scope='Sequential snapshot batch; no continuous ADC/drop-rate claim'))
                    latest_view['status']='FRAME_VERIFIED'
                    latest_view['batch']=dict(index=index,total=args.captures,verified_pairs=len(proof['rows']),completed=False)
                    if args.snapshot:atomic_json(args.snapshot,latest_view)
                    if index%4==0 or index==args.captures-1:
                        bridge.control(2,1,2000000)
                        bridge.control(2,0,2000000)
                        row['uart_path_checks']=dict(pmod_a=bridge.radio_command(1,'INFO','TX_PROBE,'),
                            rfs2=bridge.radio_command(0,'MODE?','RF_MODE,'),scope='UART command path liveness only; no TX or coherent timing claim')
                    proof.pop('active_attempt',None);publish()
                    print(f'{index+1}/{args.captures} {mode}: raw/FIR CRC + integer reference PASS, seq={after["sequence"]}, rejectsΔ={verified["spi_reject_counter_change"]}',flush=True)
                final_taps=signed_taps(nios)
                if final_taps!=taps:raise ValueError('FIR coefficients changed during soak')
                proof['fir_final_coefficients']=final_taps
                if latest_view is not None:latest_view['readback']['final_coefficient_readback_verified']=True
            finally:
                proof['pair_disabled']=nios.command('PAIR',0)
                plan=restoration_plan(original,old_taps)
                if plan['method']=='preset':nios.preset(plan['profile'])
                else:nios.coefficients(old_taps)
                nios.command('ROUND',original.get('configured_round',0))
                restored_status=nios.status();restored_taps=signed_taps(nios)
                proof['fir_restored']=dict(status=restored_status,coefficients=restored_taps,restoration=plan,
                    normalized_profile_from=plan['normalized_profile_from'],profile_label_preserved=plan['profile_label_preserved'])
                proof['fir_restored']['verified']=verify_restoration(restored_status,restored_taps,original,old_taps,expected_profile=plan['profile']);publish()
        except BaseException as error:
            proof['error']=str(error) or type(error).__name__;publish()
            if args.snapshot:atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error=str(error) or type(error).__name__,requested=proof['requested'],batch=dict(total=args.captures,verified_pairs=len(proof['rows']),completed=False)))
            raise
    print(args.output/'proof.json')


if __name__=='__main__':main()
