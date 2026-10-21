#!/usr/bin/env python3
"""Explicit checkpoint07 SPI→capture RAM→FIR II qualification, no programming.

Requires installed PMOD B SPI firmware and loaded integrated checkpoint07.
Default input is the ESP32 generated deterministic CI8 pattern, not RF.
--rf captures real RF on fixed channel8. --tx-bpsk optionally stimulates it
using already-installed PMOD A v4/v5; this never flashes either device.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import fcntl
import json
from pathlib import Path
import sys
import signal
import time
import zlib
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir,PROFILES
from spi_fir_qualification import verify_fir,snapshot,verify_restoration,restoration_plan
from check_rf_bpsk import atomic_json,fields
from check_rf_bpsk_fir import signed_taps,capture_pair,idle_readback
from rf_bpsk import frame_bits,receive


def spi_status(text):
    parts=text.split()
    if len(parts)!=9 or parts[0]!='SPI':
        raise ValueError('Invalid integrated SPI status envelope')
    values=[int(s,16) for s in parts[1:]]
    version,requested,flags,sequence,commits,rejects,low,high=values
    if version!=0x00030001 or requested not in (0,1) or flags&~3:
        raise ValueError('Wrong integrated SPI backend version or flags')
    return dict(version=f'{version:08x}',requested_synthetic=bool(requested),valid=bool(flags&1),
        synthetic=bool(flags&2),sequence=sequence,commit_count=commits,reject_count=rejects,
        ingress_cycles=(high<<32)|low)


def verify_association(raw,filtered,status_before,status_after,taps,fir_status,*,synthetic,profile,nearest):
    if (raw.kind,filtered.kind)!=(1,6):raise ValueError('Expected raw1 and FIR6 representations')
    if raw.source!=2 or raw.samples!=16380 or raw.rate!=16000000 or raw.frequency!=2447000000:
        raise ValueError('Wrong fixed PMOD B SPI capture profile')
    for name in ('source','job','samples','rate','frequency','first_tick','last_tick'):
        if getattr(raw,name)!=getattr(filtered,name):raise ValueError('Raw/FIR capture association mismatch')
    descriptor=0x80010000|(int(nearest)<<8)|profile
    if filtered.aux!=((raw.raw_crc<<32)|descriptor):raise ValueError('FIR original CRC/descriptor mismatch')
    if taps!=PROFILES[profile]:raise ValueError('Applied FIR coefficients differ from requested profile')
    for data,expected in ((raw.payload,raw.raw_crc),(filtered.payload,filtered.raw_crc)):
        if zlib.crc32(data)!=expected:raise ValueError('Capture payload CRC mismatch')
    advance=(status_after['commit_count']-status_before['commit_count'])&0xffffffff
    if not 0<advance<0x80000000 or not status_after['valid'] or status_after['synthetic']!=synthetic or status_after['requested_synthetic']!=synthetic:
        raise ValueError('No fresh matching SPI capture committed')
    if status_before.get('valid'):
        sequence_advance=(status_after['sequence']-status_before['sequence'])&0xffffffff
        if not 0<sequence_advance<0x80000000:raise ValueError('SPI capture sequence did not advance')
    if not status_after['ingress_cycles']:raise ValueError('Missing measured SPI ingress cycles')
    for key,value in dict(job=raw.job,samples=raw.samples,source=2,raw_crc=raw.raw_crc,
        filtered_crc=filtered.raw_crc,profile=profile,round=int(nearest)).items():
        if fir_status.get(key)!=value:raise ValueError(f'FIR status mismatch: {key}')
    proof=verify_fir(raw.payload,filtered.payload,taps,nearest=nearest,raw_crc=raw.raw_crc,
        filtered_crc=filtered.raw_crc,reported_clips=fir_status.get('clips'))
    proof.update(descriptor=f'{descriptor:08x}',same_capture_association=True,spi_status=status_after,
        spi_commits_advanced=advance,spi_reject_counter_change=(status_after['reject_count']-status_before['reject_count'])&0xffffffff)
    return proof


def termination_requested(_signal,_frame):
    raise KeyboardInterrupt('Termination requested')


def main():
    # Direct SIGTERM must unwind ownership/settings cleanup. Viewer cancellation
    # should target this PID only so its JTAG helper remains available to restore.
    signal.signal(signal.SIGTERM,termination_requested)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port');p.add_argument('--output',required=True,type=Path);p.add_argument('--snapshot',type=Path)
    p.add_argument('--confirm-spi-image',action='store_true');p.add_argument('--rf',action='store_true')
    p.add_argument('--profile',type=int,choices=(1,2),default=2)
    p.add_argument('--host-baud',type=int,choices=(2000000,4000000),default=2000000,help='Host FPGA UART only; restored to2M afterwards; SPI stays5MHz')
    p.add_argument('--round',type=int,choices=(0,1),default=1,dest='nearest')
    p.add_argument('--tx-bpsk',action='store_true',help='Bounded PMOD A BPSK job, only with --rf')
    p.add_argument('--payload',type=int,choices=range(256),default=165,metavar='0..255')
    args=p.parse_args()
    if not args.confirm_spi_image:p.error('Requires explicitly loaded checkpoint07: --confirm-spi-image')
    if args.tx_bpsk and not args.rf:p.error('--tx-bpsk requires --rf')
    requested=dict(mode='rf' if args.rf else 'synthetic',source=2,samples=16380,sample_rate_hz=16000000,
        frequency_hz=2447000000,host_baud=args.host_baud,profile=args.profile,round_nearest=bool(args.nearest),tx_bpsk=args.tx_bpsk)
    proof=dict(kind='physical_rf_spi_fir' if args.rf else 'synthetic_spi_fir_hardware',completed=False,
        requested=requested,raw_iq_uploaded_from_host=False)
    lock=ROOT/'cyberether/run/rf-link-capture.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        lease=stack.enter_context(lock.open('a'))
        try:fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another RF/SPI acquisition owns the FPGA') from None
        args.output.mkdir(parents=True,exist_ok=False)
        def publish():atomic_json(args.output/'proof.json',proof)
        publish()
        try:
            bridge=stack.enter_context(Bridge(args.port))
            identity=bridge.prepare_sdr(2,2447,16000000)
            if 'SPI_PROXY' not in identity:raise RuntimeError('Checkpoint07 SPI proxy identity required; wrong loaded image')
            proof['image_identity']=identity
            view=None
            def restore_host_baud(exc_type=None,exc=None,tb=None):
                if exc is not None:proof['error']=proof.get('error') or str(exc) or type(exc).__name__
                try:
                    if args.host_baud!=2000000:
                        restored=bridge.set_host_baud(2000000)
                    else:restored=bridge.status()
                    proof['host_baud_restored']=dict(baud=2000000,status=restored,scope='CRC-valid IQB1 status received with host UART configured at2M')
                    proof['completed']=bool(proof.get('capture_verified')) and not proof.get('error')
                    if view is not None and proof['completed']:
                        view['status']='PASS'
                        view['readback']['host_baud_restored']=2000000
                        if args.snapshot:atomic_json(args.snapshot,view)
                    elif args.snapshot and proof.get('error'):
                        atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error=proof['error'],requested=requested))
                    publish()
                    if proof['completed']:print(json.dumps(dict(status='PASS',output=str(args.output),verification=proof['verification']),indent=2))
                except BaseException as error:
                    proof['completed']=False;proof['host_baud_restore_error']=str(error);publish()
                    if args.snapshot:atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error='Host baud restoration failed: '+str(error),requested=requested))
                    raise
            stack.push(restore_host_baud)
            if args.host_baud!=2000000:
                proof['host_baud_applied']=dict(baud=args.host_baud,status=bridge.set_host_baud(args.host_baud),
                    scope='CRC-valid IQB1 status received after changing host and FPGA UART baud; not a dedicated baud-register readback')
            else:proof['host_baud_applied']=dict(baud=2000000,scope='SPI proxy identity/status read at default2M host UART')
            mode='RF' if args.rf else 'SYNTH'
            mode_reply=bridge.radio_command(2,'SPI_MODE '+mode,'OK SPI_MODE ')
            if mode_reply!='OK SPI_MODE '+mode:raise ValueError('SPI mode readback mismatch')
            baseline=spi_status(bridge.radio_command(2,'SPI?','SPI '))
            if baseline['requested_synthetic']==args.rf:raise ValueError('SPI requested mode status mismatch')
            nios=stack.enter_context(NiosFir(pause_monitor=False))
            original=nios.status();old_taps=signed_taps(nios)
            proof['fir_original']=dict(status=original,coefficients=old_taps)
            try:
                nios.command('PAIR',0);nios.preset(args.profile)
                if nios.command('ROUND',args.nearest).get('nearest')!=args.nearest:raise ValueError('ROUND readback mismatch')
                if nios.command('PAIR',1).get('enabled')!=1:raise ValueError('PAIR readback mismatch')
                applied=nios.status();taps=signed_taps(nios)
                if (applied['pair'],applied['configured_round'],applied['configured_profile'])!=(1,args.nearest,args.profile):raise ValueError('FIR configuration readback mismatch')
                proof['fir_applied']=dict(status=applied,coefficients=taps)
                tx_config=None
                if args.tx_bpsk:
                    bridge.control(2,1,2000000)
                    tx_identity=bridge.radio_command(1,'INFO','TX_PROBE,')
                    if not tx_identity.startswith(('TX_PROBE,v=4,','TX_PROBE,v=5,','TX_PROBE,v=6,')):raise ValueError('Installed PMOD A framed TX probe required')
                    bitline=bridge.radio_command(1,f'FRAMEBITS {args.payload}','FRAMEBITS,')
                    bitfields=dict(s.split('=',1) for s in bitline.split(',')[1:])
                    if bitfields['bits']!=''.join(str(int(x)) for x in frame_bits(args.payload)):raise ValueError('TX frame encoder readback mismatch')
                    caps=fields(bridge.radio_command(1,'PHASECAP','PHASECAP,'))
                    if caps['cpu']!=160000000:raise ValueError('TX calibrated pulse requires160MHz CPU')
                    bridge.radio_write(1,f'FRAME 8 500 120 {args.payload} 8 670\n')
                    tx_config=fields(bridge.wait_text(1,'FRAME_CFG,',10))
                    if (tx_config['payload'],tx_config['period_us'],tx_config['pulse_cycles'],tx_config['bits'],tx_config['step'])!=(args.payload,8,670,64,3):raise ValueError('TX FRAME settings mismatch')
                started=time.monotonic()
                try:
                    if args.tx_bpsk:raw,filtered,timing=capture_pair(bridge,2,started)
                    else:
                        raw,filtered=bridge.paired_capture(2,16380,16000000,timeout=20)
                        timing=dict(end_to_end_s=time.monotonic()-started)
                finally:
                    if args.tx_bpsk:bridge.radio_write(1,'STOP\n')
                (args.output/'raw.ci8').write_bytes(raw.payload);(args.output/'filtered.ci8').write_bytes(filtered.payload)
                status=spi_status(bridge.radio_command(2,'SPI?','SPI '));fir_status=nios.status();readback_taps=signed_taps(nios)
                verified=verify_association(raw,filtered,baseline,status,readback_taps,fir_status,
                    synthetic=not args.rf,profile=args.profile,nearest=bool(args.nearest))
                if not args.rf:
                    if raw.payload!=bytes((n*37+11)&255 for n in range(len(raw.payload))):raise AssertionError('ESP32 synthetic input bytes differ')
                if args.tx_bpsk:
                    proof['tx_readback']=idle_readback(bridge,tx_config['job'])
                    proof['tx_config']=tx_config
                    proof['raw_report']=receive(raw.iq(),rate=raw.rate,symbol_us=8,expected_payload=args.payload)
                    proof['filtered_report']=receive(filtered.iq(),rate=filtered.rate,symbol_us=8,expected_payload=args.payload)
                timing.update(ingress_s=status['ingress_cycles']/50000000.,fpga_fir_s=fir_status['cycles']/50000000.)
                timing.setdefault('end_to_end_s',timing.get('full_pair_elapsed_seconds'))
                timing['ingress_payload_bytes_s']=len(raw.payload)/timing['ingress_s']
                timing['end_to_end_bytes_s']=len(raw.payload)/timing['end_to_end_s']
                provenance=dict(origin='PMOD B SPI CI8 → FPGA capture RAM → FIR II → host UART',
                    fpga_processing='SPI packet CRC/order qualification and reloadable16tap FIR II',
                    spi_sequence=status['sequence'],iqb1_job=raw.job,raw_transport=raw.metadata(),filtered_transport=filtered.metadata(),
                    rf_sample_timestamps=False,tick_scope='50MHz FPGA proxy/UART receipt clock, not coherent RF timestamps',
                    sample_rate_scope='Configured nominal16MS/s; not RF-measured',gain_scope='Fixed ESP32 RF-profile hardware AGC; SPI proxy has no gain control')
                view=snapshot(raw.payload,filtered.payload,kind=proof['kind'],requested=requested,
                    readback=dict(image_identity=identity,host_baud=args.host_baud,host_baud_scope=proof['host_baud_applied']['scope'],mode='synthetic' if status['synthetic'] else 'rf',source=2,sequence=status['sequence'],profile=args.profile,
                        round_nearest=bool(args.nearest),coefficients=readback_taps,spi=status),
                    verification=verified,timing=timing,provenance=provenance)
                view['status']='FRAME_VERIFIED'
                proof.update(verification=verified,timing=timing,provenance=view['provenance'],readback=view['readback'])
                if args.snapshot:atomic_json(args.snapshot,view)
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
            proof['capture_verified']=True;publish()
        except BaseException as error:
            proof['error']=str(error) or type(error).__name__;publish()
            if args.snapshot:atomic_json(args.snapshot,dict(schema='spi-pipeline-v1',status='ERROR',updated_at=time.time(),error=str(error) or type(error).__name__,requested=requested))
            raise


if __name__=='__main__':main()
