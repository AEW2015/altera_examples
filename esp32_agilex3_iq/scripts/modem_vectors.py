#!/usr/bin/env python3
"""Generate reproducible *host-reference* modem vectors without hardware access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cyberether'))
from modem_reference import (MODES, BITS_PER_SYMBOL, constellation, quantized_mapping,
                             build_frame, run_experiment, ber_sweep, tx_waveform,
                             bytes_to_bits, conv_encode, rrc_taps)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--modulation', choices=MODES, default='QPSK')
    p.add_argument('--payload', default='A', help='UTF-8 payload, complete frame must fit TX SRAM')
    p.add_argument('--output', type=Path, default=ROOT/'cyberether/run/modem-vectors')
    p.add_argument('--snr-db', type=float, default=18.)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--sweep', action='store_true', help='also simulate an independent Es/N0 BER sweep')
    p.add_argument('--frames', type=int, default=5, help='frames per sweep point; 49*2048 bits >=100k')
    p.add_argument('--symbol-rate', type=float, default=1e6)
    args = p.parse_args(argv)
    if args.frames < 1:
        p.error('--frames must be positive')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    payload = args.payload.encode()
    # Capacity check occurs before writing any radio playback file.
    tx = tx_waveform(payload, args.modulation, symbol_rate=args.symbol_rate)
    iqpath = out/'tx_iq10.bin'
    iqpath.write_bytes(tx['iq10_bytes'])
    frame = build_frame(payload, args.modulation)
    np.savez_compressed(out/'reference.npz', waveform=frame['waveform'],
                        symbols=frame['symbols'], payload_bits=frame['payload_bits'],
                        coded_bits=frame['coded_bits'], mapped_symbols=frame['mapped_symbols'],
                        rrc_taps=rrc_taps())
    maps = {}
    for mode in MODES:
        points, labels = constellation(mode)
        maps[mode] = dict(bits_per_symbol=BITS_PER_SYMBOL[mode], labels=labels.tolist(),
                          normalized_iq=np.column_stack((points.real, points.imag)).tolist(),
                          q313_iq=quantized_mapping(mode).tolist())
    golden = dict(format='modem-reference-v1', source='Host simulation; no hardware accessed',
                  conventions=dict(bit_order='MSB first; I-axis bits before Q-axis bits',
                                   gray='ascending-axis index k has label k XOR (k >> 1)',
                                   bpsk='0:+1,1:-1', soft='positive means bit0',
                                   encoder='newest bit LSB; parity171 then133 octal; initial0; six zero tail'),
                  maps=maps,
                  encoder_input_bits=bytes_to_bits(b'Agilex').tolist(),
                  encoder_output_bits=conv_encode(bytes_to_bits(b'Agilex')).tolist(),
                  tx={k: v for k, v in tx.items() if k not in ('iq10_bytes', 'waveform')},
                  tx_sha256=hashlib.sha256(tx['iq10_bytes']).hexdigest())
    (out/'golden.json').write_text(json.dumps(golden, indent=2)+'\n')
    result = run_experiment(args.modulation, snr_db=args.snr_db, seed=args.seed)
    (out/'experiment.json').write_text(json.dumps(result, indent=2)+'\n')
    if args.sweep:
        curve = ber_sweep(args.modulation, seeds=range(args.seed, args.seed+args.frames))
        (out/'ber_sweep.json').write_text(json.dumps(curve, indent=2)+'\n')
    print(f'Host reference vectors: {out}')
    print(f'IQ10: {tx["sample_count"]} samples, {tx["sample_count"]*4} bytes; not transmitted')
    print(json.dumps(result['metrics'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
