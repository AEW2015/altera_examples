#!/usr/bin/env python3
"""Fair symbol-rate Python AWGN comparison: SVG joint trellis versus K7/QPSK.

Both schemes carry one payload bit per symbol before six termination symbols;
each transmitted endpoint has unit energy. This excludes pulse shaping, timing
recovery, RF, quantization and hardware. Shared noise improves reproducibility,
without claiming that an attractive constellation has better coding gain.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from common import ROOT
from svg_modem import encode, decode, load_graph, GRAPH
sys.path.insert(0, str(ROOT / 'cyberether'))
import modem_reference as baseline


def run(*, payload_bits=100096, frame_bits=256, levels=(0., 2., 4.), seed=19):
    if payload_bits < 1 or not 1 <= frame_bits <= 256:
        raise ValueError('Positive payload size and1..256 frame bits required')
    if not levels or any(not np.isfinite(db) for db in levels):
        raise ValueError('Finite Es/N0 operating points required')
    started = time.monotonic()
    points = load_graph()
    qpsk, labels = baseline.constellation('QPSK')
    if not np.array_equal(baseline.soft_demapper(qpsk, 'QPSK') < 0, labels.reshape(-1)):
        raise AssertionError('QPSK labels/soft-metric sign mismatch')
    if not np.allclose(abs(points) ** 2, 1) or not np.allclose(abs(qpsk) ** 2, 1):
        raise AssertionError('Both alphabets must have unit endpoint energy')
    frames = math.ceil(payload_bits / frame_bits)
    symbol_count = payload_bits + 6 * frames
    rate = payload_bits / symbol_count
    payload_rng = np.random.default_rng(seed)
    noise_rngs = [np.random.default_rng(np.random.SeedSequence([seed, 0x46414952, k])) for k in range(len(levels))]
    rows = []
    for db in levels:
        row = {'es_n0_db': float(db), 'eb_n0_db': float(db - 10 * np.log10(rate)),
               'payload_bits': payload_bits, 'symbols_including_tails': symbol_count,
               'coded_bits_including_tails_qpsk': 2 * symbol_count,
               'svg': {'payload_bit_errors': 0, 'nearest_symbol_errors': 0, 'frame_errors': 0},
               'qpsk': {'payload_bit_errors': 0, 'nearest_symbol_errors': 0,
                        'coded_bit_errors': 0, 'frame_errors': 0}}
        rows.append(row)
    remaining = payload_bits
    frame = 0
    while remaining:
        count = min(frame_bits, remaining)
        bits = payload_rng.integers(0, 2, count, dtype=np.uint8)
        svg_tx = encode(bits)
        pairs = svg_tx['coded_pairs']
        coded = baseline.conv_encode(bits)
        if not np.array_equal(np.column_stack((pairs >> 1, pairs & 1)).reshape(-1), coded):
            raise AssertionError('Encoder polynomial/bit-order mismatch')
        svg_nodes = svg_tx['node_path'][1:]
        svg_symbols = points[svg_nodes]
        qpsk_symbols = baseline.map_bits(coded, 'QPSK')
        if frame == 0:
            if not np.array_equal(baseline.viterbi_decode(baseline.soft_demapper(qpsk_symbols, 'QPSK')), bits):
                raise AssertionError('Noiseless QPSK round trip failed')
            if not np.array_equal(decode(svg_symbols)['decoded_bits'], bits):
                raise AssertionError('Noiseless SVG round trip failed')
        if len(svg_symbols) != len(qpsk_symbols) or len(svg_symbols) != count + 6:
            raise AssertionError('Unequal channel uses')
        for k, db in enumerate(levels):
            noise_variance = 10 ** (-float(db) / 10)
            sigma = np.sqrt(noise_variance / 2)
            # Exact same realization and channel-use count for both schemes.
            noise = sigma * (noise_rngs[k].standard_normal(count + 6) +
                             1j * noise_rngs[k].standard_normal(count + 6))
            svg_rx, qpsk_rx = svg_symbols + noise, qpsk_symbols + noise
            svg_decoded = decode(svg_rx)['decoded_bits']
            llr = baseline.soft_demapper(qpsk_rx, 'QPSK', noise_variance=noise_variance)
            qpsk_decoded = baseline.viterbi_decode(llr)
            svg_errors = int(np.count_nonzero(svg_decoded != bits))
            qpsk_errors = int(np.count_nonzero(qpsk_decoded != bits))
            row = rows[k]
            row['svg']['payload_bit_errors'] += svg_errors
            row['svg']['nearest_symbol_errors'] += int(np.count_nonzero(
                np.argmin(abs(svg_rx[:, None] - points) ** 2, axis=1) != svg_nodes))
            row['svg']['frame_errors'] += int(svg_errors > 0)
            row['qpsk']['payload_bit_errors'] += qpsk_errors
            nearest = np.argmin(abs(qpsk_rx[:, None] - qpsk) ** 2, axis=1)
            tx_labels = coded.reshape(-1, 2)
            row['qpsk']['nearest_symbol_errors'] += int(np.count_nonzero(
                np.any(labels[nearest] != tx_labels, axis=1)))
            row['qpsk']['coded_bit_errors'] += int(np.count_nonzero(labels[nearest].reshape(-1) != coded))
            row['qpsk']['frame_errors'] += int(qpsk_errors > 0)
        remaining -= count
        frame += 1
        if frame % 50 == 0 or remaining == 0:
            print(f'Compared {payload_bits - remaining:,}/{payload_bits:,} payload bits per noise level ({frame}/{frames} frames)', flush=True)
    for row in rows:
        for scheme in ('svg', 'qpsk'):
            metrics = row[scheme]
            metrics['payload_ber'] = metrics['payload_bit_errors'] / payload_bits
            metrics['nearest_symbol_error_rate'] = metrics['nearest_symbol_errors'] / symbol_count
            metrics['frame_error_rate'] = metrics['frame_errors'] / frames
            metrics['zero_error_bit_bound_95_independence_assumed'] = 1 - 0.05 ** (1 / payload_bits) if metrics['payload_bit_errors'] == 0 else None
            metrics['zero_frame_error_upper_95'] = 1 - 0.05 ** (1 / frames) if metrics['frame_errors'] == 0 else None
    return {'schema': 'svg-qpsk-fair-comparison-v1', 'simulation_only': True,
            'hardware_access': False, 'rf_tested': False,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': time.monotonic() - started,
            'seed': seed, 'payload_bits_per_level': payload_bits,
            'frame_payload_bits': frame_bits, 'frame_count': frames,
            'tail_bits_per_frame': 6, 'symbols_per_level': symbol_count,
            'endpoint_symbol_energy': 1, 'effective_payload_bits_per_symbol': rate,
            'comparison': 'Same payloads, six zero tails, unit endpoint energy and identical complex AWGN realizations per frame/level; soft ML decoding for both.',
            'svg_decoder': '320-state joint graph/K7 squared-Euclidean Viterbi',
            'qpsk_decoder': 'K7(171,133)64-state Viterbi with exact separable-QPSK soft LLRs; positive means zero;171 first',
            'scope': 'Known symbol timing and phase; no waveform energy/bandwidth, synchronization, quantization or RF effects. No free-distance or coding-gain claim.',
            'confidence_note': 'FEC errors can cluster within a frame; bitwise binomial bounds assume independent bit errors. Frame-level zero-error bounds use independent frame trials.',
            'denominators': {'payload_ber': 'payload_bit_errors / payload_bits',
                             'nearest_symbol_error_rate': 'nearest_symbol_errors / symbols_including_tails',
                             'qpsk_raw_coded_ber': 'coded_bit_errors / (2*symbols_including_tails)',
                             'eb_n0_db': 'es_n0_db-10log10(payload_bits/symbols_including_tails)'},
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), ROOT / 'scripts/svg_modem.py',
                                        ROOT / 'cyberether/modem_reference.py', GRAPH]},
            'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bits', type=int, default=100096)
    parser.add_argument('--frame-bits', type=int, default=256)
    parser.add_argument('--levels', nargs='+', type=float, default=[0, 2, 4])
    parser.add_argument('--seed', type=int, default=19)
    parser.add_argument('--output', type=Path, default=ROOT / 'cyberether/run/svg-qpsk-comparison.json')
    args = parser.parse_args()
    result = run(payload_bits=args.bits, frame_bits=args.frame_bits, levels=args.levels, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    for row in result['results']:
        print(f"Es/N0 {row['es_n0_db']:g}dB: SVG {row['svg']['payload_bit_errors']}/{args.bits}; K7/QPSK {row['qpsk']['payload_bit_errors']}/{args.bits} payload errors")
    print('Python simulation saved:', args.output)


if __name__ == '__main__':
    main()
