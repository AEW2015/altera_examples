#!/usr/bin/env python3
"""Bounded framed-QPSK RF capture, independent host recovery and honest BER.

Requires explicitly installed probe v5/v6 and an IQB1 runtime hub. Does not flash
either device. --synthetic is a separately labelled, hardware-free preview.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
from common import ROOT
sys.path.insert(0, str(ROOT/'cyberether'))
from rf_qpsk import frame_states, receive, synthesize
from tx_job_readback import validate_tx_on


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def fields(line):
    return {k: int(v) for k, v in (x.split('=', 1) for x in line.split(',')[1:])}


def snapshot(proof, requested, status, error=None):
    rows = proof['rows']
    reports = [r['report'] for r in rows]
    plot_index = next((i for i in range(len(rows)-1, -1, -1) if reports[i]['valid_frames']), len(rows)-1)
    plot_row = rows[plot_index] if rows else None
    totals = {key: sum(r[key] for r in reports) for key in
              ('valid_frames', 'acquisition_failures', 'coded_errors',
               'coded_bits', 'payload_errors', 'payload_bits')}
    acquired = sum(r['acquired_frames'] for r in reports)
    failed = sum(r['crc_failures'] for r in reports)
    totals.update(captures=len(rows), frame_failures=failed,
                  crc_pass=totals['valid_frames'], crc_total=acquired)
    if not reports:
        totals = {k: None for k in totals}
    return dict(schema='rf-link-v1', modulation='QPSK', status=status,
                updated_at=plot_row['captured_at'] if plot_row else time.time(),
                status_updated_at=time.time(),
                provenance=dict(kind='synthetic' if proof['kind']=='synthetic_qpsk' else 'physical_rf',
                    description='Generated phase-ramp test fixture' if proof['kind']=='synthetic_qpsk'
                    else 'PMOD A ESP32 RF → ESP32 RX → Agilex 3 capture RAM; host synchronization/FEC'),
                controls=dict(requested=requested, readback=rows[-1]['config'] if rows else None),
                timing=dict(sample_rate_hz=16000000, symbol_rate_hz=1e6/requested['symbol_us'],
                            cpu_hz=rows[-1]['config'].get('cpu') if rows else None,
                            captured_seconds=sum(r['capture_seconds'] for r in reports),
                            clock_note='Radio clocks independent; FPGA ticks timestamp UART receipt, not RF sample phase'),
                pipeline=[dict(label=label, location=location, status='reference' if proof['kind']=='synthetic_qpsk' else 'measured')
                          for label, location in [('Phase-pulse TX','PMOD A ESP32'),('Raw CI8 RX','ESP32'),
                              ('Capture RAM / transport','Agilex 3 FPGA'),('Carrier / timing / frame acquisition','Host'),
                              ('Soft demap / K7 FEC / CRC','Host')]],
                metrics=totals, plots=plot_row['report']['plots'] if plot_row else {}, error=error,
                plot_capture=dict(index=plot_index, source_sha256=plot_row['transport'].get('payload_sha256') if plot_row else None, crc_valid=bool(plot_row and plot_row['report']['valid_frames']),
                                  captured_at=plot_row['captured_at'] if plot_row else None),
                notes=['Plots retain the latest CRC-valid capture within this batch; counts include every attempt. Plot age refers to those displayed samples.',
                       'BER includes synchronized CRC-failed frames; unsynchronized captures have their own counter.',
                       'Frames outside sparse capture windows are unobserved. No delivery ratio is inferred.',
                       'Synthetic QPSK uses at least two full frame periods; actual RF snapshots remain 16,380 samples.',
                       'The on-air frame carries one payload byte; CRC and six termination bits are separate.',
                       'FPGA symbol/FEC replay is a separate explicitly measured step, not live waveform synchronization.',
                       proof.get('pulse_profile','Pulse widths selected independently; synthetic fixture uses generated phase ramps.')])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--port')
    parser.add_argument('--captures', type=int, choices=range(1, 65), default=4, metavar='1..64')
    parser.add_argument('--payload', type=int, choices=range(256), default=165, metavar='0..255')
    parser.add_argument('--channel', type=int, choices=range(1, 12), default=8)
    parser.add_argument('--source', type=int, choices=[0, 2], default=0)
    parser.add_argument('--symbol-us', type=int, choices=range(8, 16), default=12, metavar='8..15')
    parser.add_argument('--pulse-cycles', type=int, default=335, help='Quarter-turn request cycles; experimental RF calibration')
    parser.add_argument('--half-cycles', type=int, default=670)
    parser.add_argument('--three-cycles', type=int, default=1005)
    parser.add_argument('--rx-gain', type=int, choices=range(128), default=0, metavar='0..127')
    parser.add_argument('--backoff-qdb', type=int, choices=range(80, 121), default=120, metavar='80..120')
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--synthetic-coded-flips',type=int,choices=[0,1,2,4,8],default=0,
                        help='Synthetic transmitted coded-bit errors; never added to RF data')
    args = parser.parse_args()
    if args.synthetic_coded_flips:
        parser.error('QPSK harness currently uses waveform noise; coded-flips control unsupported')
    if args.synthetic_coded_flips and not args.synthetic:
        parser.error('--synthetic-coded-flips requires --synthetic')
    args.output.mkdir(parents=True, exist_ok=False)
    requested = dict(channel=args.channel, payload=args.payload, symbol_us=args.symbol_us,
                     pulse_cycles=args.pulse_cycles,half_cycles=args.half_cycles,three_cycles=args.three_cycles, rx_gain=args.rx_gain, source=args.source,backoff_qdb=args.backoff_qdb)
    requested['synthetic_coded_flips']=args.synthetic_coded_flips if args.synthetic else None
    proof = dict(kind='synthetic_qpsk' if args.synthetic else 'physical_rf_qpsk',
                 completed=False, rows=[], requested=requested, processing='Host synchronization/demapping/FEC; FPGA capture transport only')

    def publish(status, error=None):
        atomic_json(args.output/'proof.json', proof)
        if args.snapshot:
            atomic_json(args.snapshot, snapshot(proof, requested, status, error))

    def record(iq, config, transport, stats):
        index = len(proof['rows'])
        raw = np.asarray(iq, dtype=np.int8)
        (args.output/f'capture-{index:03d}.ci8').write_bytes(raw.tobytes())
        report = receive(raw, rate=16000000, symbol_us=args.symbol_us, expected_payload=args.payload)
        proof['rows'].append(dict(config=config, transport=transport, stats=stats,
                                  captured_at=time.time(), report=report))
        publish('capturing')
        print(json.dumps(dict(capture=index, acquired=report['acquired_frames'],
              crc_valid=report['valid_frames'], coded_errors=report['coded_errors'],
              coded_bits=report['coded_bits'], payload_errors=report['payload_errors'],
              payload_bits=report['payload_bits'])), flush=True)

    publish('starting')
    try:
        if args.synthetic:
            for index in range(args.captures):
                iq = synthesize(args.payload, symbol_us=args.symbol_us, seed=index+1,
                                offset_samples=47+index*137,
                                samples=max(16380, 2*64*round(16*args.symbol_us)))
                record(iq, dict(payload=args.payload, period_us=args.symbol_us, bits=64,
                       step=3, synthetic=True), dict(origin='synthetic fixture; no hardware'), {})
        else:
            from iq_bridge import Bridge
            from nios_fir import NiosFir
            from check_esp32_nco import state
            with NiosFir(pause_monitor=False) as nios:
                nios.command('PAIR', 0)
            with Bridge(args.port) as bridge:
                bridge.control(2, 1, 2000000)
                proof['identity'] = bridge.radio_command(1, 'INFO', 'TX_PROBE,')
                if not proof['identity'].startswith(('TX_PROBE,v=5,','TX_PROBE,v=6,')):
                    raise RuntimeError('Framed RF requires explicitly installed v5/v6 probe')
                bitline = bridge.radio_command(1, f'QFRAMEBITS {args.payload}', 'QFRAMEBITS,')
                encoded = dict(x.split('=', 1) for x in bitline.split(',')[1:])
                expected = ''.join(str(int(x)) for x in frame_states(args.payload))
                if encoded['states'] != expected or int(encoded['payload']) != args.payload:
                    raise RuntimeError('Transmitter frame encoder readback mismatch')
                proof['framebits_readback'] = bitline
                caps = fields(bridge.radio_command(1, 'PHASECAP', 'PHASECAP,'))
                pulse=args.pulse_cycles
                if caps['cpu'] !=160000000:
                    raise ValueError('QPSK pulse widths require explicit requalification at this CPU clock')
                if min(pulse,args.half_cycles,args.three_cycles)<=0 or max(pulse,args.half_cycles,args.three_cycles)>min(8192,caps['cpu']*args.symbol_us*4//5000000):
                    raise ValueError('Every transition must fit within80% of symbol')
                proof['pulse_profile']='Experimental QPSK widths; quarter/half measured separately, complete frame RF qualification required'
                proof['receiver'] = bridge.prepare_sdr(args.source, 2407+5*args.channel, 16000000)
                old_gain = bridge.radio_command(args.source, 'GAIN?', 'GAIN ')
                try:
                    bridge.radio_command(args.source, f'GAIN MANUAL {args.rx_gain}', 'OK')
                    gain = bridge.radio_command(args.source, 'GAIN?', 'GAIN ')
                    if gain.split()[1:3] != ['MANUAL', str(args.rx_gain)]:
                        raise RuntimeError('RX gain readback mismatch')
                    proof['gain_readback'] = gain
                    for _ in range(args.captures):
                        bridge.radio_write(1, f'QFRAME {args.channel} 500 {args.backoff_qdb} {args.payload} {args.symbol_us} {pulse} {args.half_cycles} {args.three_cycles}\n')
                        config = fields(bridge.wait_text(1, 'QFRAME_CFG,', 10))
                        if (config['payload'], config['period_us'], config['quarter_cycles'], config['half_cycles'],config['three_cycles'],config['symbols'], config['step']) != (args.payload, args.symbol_us, pulse, args.half_cycles,args.three_cycles,64, 3):
                            raise RuntimeError('TX frame settings readback mismatch')
                        started = time.monotonic()
                        try:
                            acknowledgement=validate_tx_on(bridge.wait_text(1,'TX_ON,',.4),config,
                                channel=args.channel,backoff_qdb=args.backoff_qdb,limit_ms=500)
                            config['tx_on_readback']=acknowledgement
                            config['channel']=acknowledgement['channel']
                            config['backoff']=acknowledgement['backoff_qdb']
                            config['capture_trigger']='Matched QFRAME_CFG and actual TX_ON job/channel/backoff/duration'
                            proof['last_tx_on_readback']=acknowledgement
                            frame = next(bridge.captures(1, args.source, 16380, 16000000, pipeline=False))
                        finally:
                            bridge.radio_write(1, 'STOP\n')
                        # Preserve the raw capture even if subsequent control evidence fails.
                        (args.output/f'capture-{len(proof["rows"]):03d}.ci8').write_bytes(frame.payload)
                        if time.monotonic()-started > .48:
                            raise RuntimeError('Capture transfer exceeded the bounded transmit window')
                        deadline = time.monotonic()+3
                        while True:
                            idle = bridge.radio_command(1, 'INFO', 'TX_PROBE,')
                            if 'busy=0' in idle:
                                break
                            if time.monotonic() > deadline:
                                raise RuntimeError('Transmitter did not report idle')
                        quiet = state(bridge.radio_command(1, 'STATE', 'TONE_STATE,'))
                        if any((quiet[k]>>18)&255 for k in ('tone1','tone2')) or quiet['ext']&3:
                            raise RuntimeError('Transmitter did not restore disabled tones')
                        stats = fields(bridge.radio_command(1, 'PHASESTAT', 'PHASESTAT,'))
                        if stats['job'] != config['job']:
                            raise RuntimeError('TX timing statistics job mismatch')
                        config['channel'] = args.channel
                        config['idle_readback'] = idle
                        config['quiet_readback'] = quiet
                        record(frame.iq(), config, frame.metadata(), stats)
                    proof['hub_status'] = bridge.status()
                finally:
                    bridge.radio_write(1, 'STOP\n')
                    parts = old_gain.split()
                    bridge.radio_command(args.source, 'GAIN HARDWARE' if parts[1]=='HARDWARE' else 'GAIN MANUAL '+parts[2], 'OK')
        proof['completed'] = True
        publish('complete')
    except BaseException as error:
        proof['completed'] = False
        proof['error'] = str(error) or type(error).__name__
        publish('error', proof['error'])
        raise


if __name__ == '__main__':
    main()
