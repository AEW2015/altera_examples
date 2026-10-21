#!/usr/bin/env python3
"""Capture one RF burst as paired raw/FPGA-FIR IQ and decode both independently.

Requires existing checkpoint03-compatible FIR image and PMOD A probe v4. No
flashing, programming, host IQ upload or synthetic RF substitution occurs.
The transmit window is checked at the raw capture header, not after the slower
paired UART transfer. Both representations are associated with the same job,
UART receipt timestamps and original raw CRC before any DSP result is accepted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir, PROFILES, fixed_reference
from rf_bpsk import frame_bits, receive
from check_rf_bpsk import atomic_json, fields
from check_esp32_nco import state
from notebook_progress import task


def signed_taps(nios):
    words=[nios.command('READCOEFF',i)['bits']&65535 for i in range(16)]
    return [v if v<32768 else v-65536 for v in words]


def capture_pair(bridge,source,started,timeout=12):
    """Read CRC-qualified pair, stopping TX immediately at its raw header."""
    job=bridge.submit(source,16380,16000000)
    frames={}
    header_elapsed=None
    def raw_header(header):
        nonlocal header_elapsed
        if (header.job,header.source,header.samples,header.rate)!=(job,source,16380,16000000):
            raise ValueError('Raw header association mismatch')
        if header_elapsed is not None:
            raise ValueError('Duplicate raw capture header')
        header_elapsed=time.monotonic()-started
        bridge.radio_write(1,'STOP\n')
    deadline=time.monotonic()+timeout
    try:
        while set(frames)!={1,6}:
            if time.monotonic()>=deadline:
                raise TimeoutError('Raw/FIR pair incomplete')
            if bridge.responses:
                frame=bridge.responses.popleft()
                if frame.kind==1:raw_header(frame)
            else:
                frame=bridge.read_frame(max(.01,deadline-time.monotonic()),on_capture_header=raw_header)
            if frame.kind==5:
                raise RuntimeError(f'FPGA paired capture error{frame.error:#x},job{frame.job}')
            if frame.kind not in (1,6):continue
            if (frame.job,frame.source,frame.samples,frame.rate)!=(job,source,16380,16000000):
                raise ValueError('Raw/FIR pair association mismatch')
            if frame.kind in frames:raise ValueError('Duplicate pair representation')
            frames[frame.kind]=frame
    finally:
        bridge.radio_write(1,'STOP\n')
    if header_elapsed is None or header_elapsed>=.48:
        raise RuntimeError('Raw capture header exceeded bounded RF window')
    return frames[1],frames[6],dict(raw_header_elapsed_seconds=header_elapsed,
            full_pair_elapsed_seconds=time.monotonic()-started,
            tx_stop_trigger='Raw IQB1 header, before raw payload transfer',
            timing_scope='Raw sample buffer complete before its header; later paired UART transfer is not RF exposure')


def verify_pair(raw,filtered,taps,status):
    if raw.kind!=1 or filtered.kind!=6:
        raise ValueError('Expected raw kind1 and filtered kind6')
    names=('job','source','samples','rate','frequency','first_tick','last_tick')
    if any(getattr(raw,k)!=getattr(filtered,k) for k in names):
        raise ValueError('Raw/FIR pair metadata mismatch')
    if filtered.aux>>32!=raw.raw_crc:
        raise ValueError('Filtered descriptor original raw CRC mismatch')
    descriptor=filtered.aux&0xffffffff
    if descriptor!=0x80010102:
        raise ValueError('Expected reloadable Hamming profile2 with nearest rounding')
    if taps!=PROFILES[2]:raise ValueError('Hamming coefficients changed')
    nearest=bool(descriptor&256)
    expected=fixed_reference(raw.iq(),taps,round_nearest=nearest)
    error=int(np.max(abs(expected.astype(np.int16)-filtered.iq().astype(np.int16))))
    if error:raise AssertionError(f'FPGA FIR differs from independent integer reference by{error}')
    full=np.column_stack([np.convolve(raw.iq()[:,i].astype(np.int64),taps)[:raw.samples] for i in range(2)])
    scaled=(full+16384)>>15
    clips=int(np.count_nonzero(np.any((scaled>127)|(scaled < -128),axis=1)))
    expected_status=dict(job=raw.job,samples=raw.samples,source=raw.source,raw_crc=raw.raw_crc,
                         filtered_crc=filtered.raw_crc,round=1,profile=2,clips=clips)
    for key,value in expected_status.items():
        if status.get(key)!=value:raise ValueError(f'FIR status mismatch: {key}')
    return dict(max_reference_error=error,bit_exact=True,round_nearest=nearest,
                descriptor=f'{descriptor:08x}',coefficients=taps,clips=clips,
                actual_status=status,processing_seconds=status['cycles']/50000000.,
                configured_clock_hz=50000000,
                reference_scope='Independent host integer convolution/rounding/saturation of SAME raw RF CI8')


def idle_readback(bridge,job):
    deadline=time.monotonic()+3
    while True:
        idle=bridge.radio_command(1,'INFO','TX_PROBE,')
        if 'busy=0' in idle:break
        if time.monotonic()>deadline:raise RuntimeError('TX did not report idle')
    quiet=state(bridge.radio_command(1,'STATE','TONE_STATE,'))
    if any((quiet[k]>>18)&255 for k in ('tone1','tone2')) or quiet['ext']&3:
        raise RuntimeError('TX did not restore disabled tones')
    stats=fields(bridge.radio_command(1,'PHASESTAT','PHASESTAT,'))
    if stats['job']!=job:raise ValueError('TX statistics job mismatch')
    return dict(idle=idle,quiet=quiet,stats=stats)


@task('Capture and verify paired FPGA FIR IQ')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--port')
    p.add_argument('--captures',type=int,choices=range(1,17),default=2,metavar='1..16')
    p.add_argument('--payload',type=int,choices=range(256),default=165,metavar='0..255')
    p.add_argument('--rx-gain',type=int,choices=range(128),default=0)
    p.add_argument('--pulse-cycles',type=int,default=670)
    args=p.parse_args()
    if not 1<=args.pulse_cycles<=1024:p.error('Pulse must fit the8us symbol')
    args.output.mkdir(parents=True,exist_ok=False)
    proof=dict(kind='physical_rf_bpsk_fir',completed=False,rows=[],
               processing='Real RF RX → FPGA FIR II16taps; host carrier/timing/acquisition/demap/FEC/CRC',
               raw_iq_uploaded_from_host=False,
               symbol_fec_in_fpga=False,
               unobserved_gaps='Sparse capture windows only; no intervening frames or delivery ratio inferred')
    def publish():atomic_json(args.output/'proof.json',proof)
    publish()
    try:
        with NiosFir(pause_monitor=False) as nios:
            original=nios.status();old_taps=signed_taps(nios)
            proof['fir_original']=dict(status=original,coefficients=old_taps)
            try:
                nios.command('PAIR',0)
                nios.preset(2)
                if nios.command('ROUND',1).get('nearest')!=1:raise ValueError('ROUND readback mismatch')
                if nios.command('PAIR',1).get('enabled')!=1:raise ValueError('PAIR readback mismatch')
                configured=nios.status();taps=signed_taps(nios)
                if (configured['pair'],configured['configured_round'],configured['configured_profile'])!=(1,1,2):
                    raise ValueError('FIR settings readback mismatch')
                proof['fir_configured']=dict(status=configured,coefficients=taps)
                with Bridge(args.port) as bridge:
                    bridge.control(2,1,2000000)
                    proof['identity']=bridge.radio_command(1,'INFO','TX_PROBE,')
                    if not proof['identity'].startswith(('TX_PROBE,v=4,','TX_PROBE,v=5,','TX_PROBE,v=6,')):raise RuntimeError('Requires installed v4/v5 probe')
                    bitline=bridge.radio_command(1,f'FRAMEBITS {args.payload}','FRAMEBITS,')
                    bitfields=dict(x.split('=',1) for x in bitline.split(',')[1:])
                    if bitfields['bits']!=''.join(str(int(x)) for x in frame_bits(args.payload)) or int(bitfields['payload'])!=args.payload:
                        raise ValueError('TX frame encoder readback mismatch')
                    proof['framebits_readback']=bitline
                    caps=fields(bridge.radio_command(1,'PHASECAP','PHASECAP,'))
                    if caps['cpu']!=160000000:raise ValueError('Pulse profile requires160MHz CPU')
                    proof['receiver']=bridge.prepare_sdr(0,2447,16000000)
                    previous_gain=bridge.radio_command(0,'GAIN?','GAIN ')
                    try:
                        bridge.radio_command(0,f'GAIN MANUAL {args.rx_gain}','OK')
                        gain=bridge.radio_command(0,'GAIN?','GAIN ')
                        if gain.split()[1:3]!=['MANUAL',str(args.rx_gain)]:raise ValueError('RX gain readback mismatch')
                        proof['gain_readback']=gain
                        proof['initial_hub_status']=bridge.idle_status()
                        for index in range(args.captures):
                            bridge.radio_write(1,f'FRAME 8 500 120 {args.payload} 8 {args.pulse_cycles}\n')
                            config=fields(bridge.wait_text(1,'FRAME_CFG,',10))
                            if (config['payload'],config['period_us'],config['pulse_cycles'],config['bits'],config['step'])!=(args.payload,8,args.pulse_cycles,64,3):
                                raise ValueError('TX settings readback mismatch')
                            started=time.monotonic()
                            raw,filtered,timing=capture_pair(bridge,0,started)
                            # Keep original bytes even if later control/reference checks fail.
                            (args.output/f'raw-{index:03d}.ci8').write_bytes(raw.payload)
                            (args.output/f'fir-{index:03d}.ci8').write_bytes(filtered.payload)
                            quiet=idle_readback(bridge,config['job'])
                            fir_status=nios.status()
                            actual_taps=signed_taps(nios)
                            evidence=verify_pair(raw,filtered,actual_taps,fir_status)
                            # Each path acquires independently. Expected payload only
                            # instruments BER; it cannot supply frame/timing decisions.
                            reports={key:receive(frame.iq(),rate=frame.rate,symbol_us=8,expected_payload=args.payload)
                                     for key,frame in [('raw',raw),('filtered',filtered)]}
                            proof['rows'].append(dict(config=config,timing=timing,tx_readback=quiet,
                                   raw_transport=raw.metadata(),filtered_transport=filtered.metadata(),
                                   fir=evidence,raw_report=reports['raw'],filtered_report=reports['filtered'],
                                   captured_at=time.time()))
                            publish()
                            print(json.dumps(dict(capture=index,bit_exact=evidence['bit_exact'],
                                   raw_crc_valid=reports['raw']['valid_frames'],fir_crc_valid=reports['filtered']['valid_frames'],
                                   raw_coded_errors=reports['raw']['coded_errors'],fir_coded_errors=reports['filtered']['coded_errors'],
                                   raw_header_seconds=timing['raw_header_elapsed_seconds'],full_pair_seconds=timing['full_pair_elapsed_seconds'])),flush=True)
                        final=bridge.status();proof['final_hub_status']=final
                        for key in ('host_command_errors','radio_framing_errors','capture_errors'):
                            if final[key]!=proof['initial_hub_status'][key]:raise RuntimeError(f'New FPGA error counter:{key}')
                    finally:
                        bridge.radio_write(1,'STOP\n')
                        parts=previous_gain.split()
                        bridge.radio_command(0,'GAIN HARDWARE' if parts[1]=='HARDWARE' else 'GAIN MANUAL '+parts[2],'OK')
                        proof['gain_restored']=bridge.radio_command(0,'GAIN?','GAIN ')
            finally:
                # Leave paired streaming disabled, then restore prior filter config.
                proof['pair_disabled']=nios.command('PAIR',0)
                profile=original.get('configured_profile',0)
                if profile in (1,2):nios.preset(profile)
                else:nios.coefficients(old_taps)
                nios.command('ROUND',original.get('configured_round',0))
                proof['fir_restored']=dict(status=nios.status(),coefficients=signed_taps(nios))
                publish()
        proof['completed']=True;publish()
    except BaseException as error:
        proof['error']=str(error);publish();raise


if __name__=='__main__':main()
