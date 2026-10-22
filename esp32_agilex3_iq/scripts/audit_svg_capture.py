#!/usr/bin/env python3
"""Audit saved SVG FPGA capture against independent geometry/noise/trellis models.

Offline only: never acquires, programs, or transmits. Normalized display IQ is
converted back to its exact original CI16 integers before comparison.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from common import ROOT
from svg_modem import encode, decode, load_graph


def advance(value):
    value = (value ^ (value << 13)) & 0xffffffff
    value ^= value >> 17
    return (value ^ (value << 5)) & 0xffffffff


def reference(count, seed, amplitude, arc):
    data_rng = seed
    bits = []
    for _ in range(count):
        bits.append(data_rng & 1)
        data_rng = advance(data_rng)
    tx = encode(bits)
    quantize = lambda x: np.copysign(np.floor(np.abs(x) + .5), x).astype(np.int64)
    points = quantize(np.column_stack((load_graph().real, load_graph().imag)) * 8192)
    angles = np.pi / 2 - np.arange(5) * 2 * np.pi / 5
    t = np.arange(1, 17)[:, None] / 16
    chunks = []
    for a, b in zip(tx['node_path'][:-1], tx['node_path'][1:]):
        delta = (b - a) % 5
        if arc and delta in (1, 4):
            theta = angles[a] + (-1 if delta == 1 else 1) * (2 * np.pi / 5) * t[:, 0]
            wave = quantize(np.column_stack((np.cos(theta), np.sin(theta))) * 8192)
        else:
            wave = quantize(points[a] + (points[b] - points[a]) * t)
        wave[-1] = points[b]
        chunks.append(wave)
    clean = np.concatenate(chunks)
    received = []
    i_rng, q_rng = seed ^ 0x9e3779b9, seed ^ 0x243f6a88
    i_rng, q_rng = i_rng or 1, q_rng or 2
    signed = lambda x: x - 65536 if x & 32768 else x
    for i, q in clean:
        ni, nq = signed(i_rng >> 16) * amplitude // 32768, signed(q_rng >> 16) * amplitude // 32768
        received.append([np.clip(i + ni, -32768, 32767), np.clip(q + nq, -32768, 32767)])
        i_rng, q_rng = advance(i_rng), advance(q_rng)
    received = np.asarray(received, dtype=np.int64)
    rx = received[15::16]
    constellation = points[:, 0] + 1j * points[:, 1]
    samples = rx[:, 0] + 1j * rx[:, 1]
    decoded = decode(samples, points=constellation)
    delta = rx[:, None, :] - points[None, :, :]
    nearest = np.argmin(np.sum(delta * delta, axis=2), axis=1)
    difference = rx - points[decoded['node_path'][1:]]
    integer_metric = int(np.sum(difference * difference))
    if decoded['metric'] != integer_metric:
        raise AssertionError('Reference traceback metric differs from exact int64 sum')
    return {'payload_bits': bits, 'tx_nodes': tx['node_path'], 'coded_pairs': tx['coded_pairs'],
            'tx_symbols': points[tx['node_path'][1:]], 'tx_wave': clean, 'rx_wave': received,
            'rx_symbols': rx, 'decoded_bits': decoded['decoded_bits'],
            'decoded_nodes': decoded['node_path'], 'nearest_nodes': nearest,
            'symbol_errors': int(np.count_nonzero(nearest != tx['node_path'][1:])),
            'payload_errors': int(np.count_nonzero(decoded['decoded_bits'] != bits)),
            'metric': integer_metric}



def reference_counters(count, seed, amplitude):
    # Endpoint-only independent model: skip the15 intervening noise RNG words,
    # preserving their exact effect on state without generating display traces.
    rng = seed
    bits = []
    for _ in range(count):
        bits.append(rng & 1)
        rng = advance(rng)
    tx = encode(bits)
    points = np.rint(load_graph() * 8192)
    i_rng, q_rng = (seed ^ 0x9e3779b9) or 1, (seed ^ 0x243f6a88) or 2
    signed = lambda x: x - 65536 if x & 32768 else x
    noise = []
    for _ in range(count + 6):
        for skip in range(15):
            i_rng, q_rng = advance(i_rng), advance(q_rng)
        noise.append([signed(i_rng >> 16) * amplitude // 32768,
                      signed(q_rng >> 16) * amplitude // 32768])
        i_rng, q_rng = advance(i_rng), advance(q_rng)
    clean = points[tx['node_path'][1:]]
    noisy = np.column_stack((clean.real, clean.imag)) + np.asarray(noise)
    noisy = np.clip(noisy, -32768, 32767)
    y = noisy[:, 0] + 1j * noisy[:, 1]
    decoded = decode(y, points=points)
    integer_points = np.column_stack((points.real, points.imag)).astype(np.int64)
    integer_noisy = noisy.astype(np.int64)
    delta = integer_noisy[:, None, :] - integer_points[None, :, :]
    nearest = np.argmin(np.sum(delta * delta, axis=2), axis=1)
    difference = integer_noisy - integer_points[decoded['node_path'][1:]]
    integer_metric = int(np.sum(difference * difference))
    if decoded['metric'] != integer_metric:
        raise AssertionError('Reference traceback metric differs from exact int64 sum')
    return [int(np.count_nonzero(nearest != tx['node_path'][1:])),
            int(np.count_nonzero(decoded['decoded_bits'] != bits)), integer_metric]


def audit_frames(data):
    totals = dict(symbol_errors=0, payload_errors=0, payload_denominator=0,
                  symbol_denominator=0, frames_with_payload_errors=0)
    for index, frame in enumerate(data['sweep_frames']):
        count, seed, amplitude = frame['payload_count'], frame['seed'], frame['noise_amplitude']
        expected = reference_counters(count, seed, amplitude)
        actual = [frame['symbol_errors'], frame['payload_errors'], frame['final_metric']]
        if actual != expected or frame['status'] != 2 or frame['symbol_count'] != count + 6 or frame['wave_count'] != (count + 6) * 16:
            raise AssertionError(f'Sweep frame{index} differs from independent counter/metric reference')
        totals['symbol_errors'] += expected[0]
        totals['payload_errors'] += expected[1]
        totals['payload_denominator'] += count
        totals['symbol_denominator'] += count + 6
        totals['frames_with_payload_errors'] += int(expected[1] > 0)
        if (index + 1) % 50 == 0 or index + 1 == len(data['sweep_frames']):
            print(f'Independently audited {index + 1}/{len(data["sweep_frames"])} FPGA frames', flush=True)
    summary = data['sweep_summary']
    expected_summary = [totals['payload_errors'], totals['payload_denominator'], totals['symbol_errors'],
                        totals['symbol_denominator'], totals['frames_with_payload_errors']]
    actual_summary = [summary[k] for k in ('payload_bit_errors', 'payload_bit_denominator',
                                          'nearest_node_symbol_errors', 'nearest_node_symbol_denominator',
                                          'frames_with_payload_errors')]
    if expected_summary != actual_summary:
        raise AssertionError('Aggregate FPGA sweep summary differs from independently audited frames')
    return {'passed': True, 'frames_audited': len(data['sweep_frames']),
            'all_frame_metrics_and_counters_exact': True, **totals}

def audit(path, *, all_frames=False):
    data = json.loads(path.read_text())
    if data.get('simulation_only') or not data.get('implemented_in_fpga') or data.get('rf_tested'):
        raise ValueError('Expected a genuine saved internal FPGA result, without RF claims')
    hardware = data['hardware']
    if hardware.get('fpga_id') != 0x53564701:
        raise AssertionError('Unexpected FPGA design identity')
    count, seed = hardware['payload_count_readback'], hardware['seed_readback']
    amplitude, arc = hardware['noise_amplitude_readback'], hardware['mode_readback']
    expected = reference(count, seed, amplitude, arc)
    checks = {}

    def compare(name, actual, reference):
        a, b = np.asarray(actual), np.asarray(reference)
        if a.shape != b.shape or not np.array_equal(a, b):
            raise AssertionError(f'{name} mismatch: actual shape{a.shape}, expected{b.shape}')
        checks[name] = {'exact': True, 'values': int(a.size)}

    def integer_iq(value):
        a = np.asarray(value) * 8192
        if not np.array_equal(a, np.rint(a)) or np.any(a < -32768) or np.any(a > 32767):
            raise AssertionError('Display IQ cannot be restored to exact CI16')
        return a.astype(np.int64)

    compare('source_bits', data['payload_bits'], expected['payload_bits'])
    compare('transmitted_nodes', data['tx']['node_path'], expected['tx_nodes'])
    compare('coded_pairs_derived_from_nodes', data['tx']['coded_pairs'], expected['coded_pairs'])
    compare('transmitted_symbols', integer_iq(data['tx']['symbols']), expected['tx_symbols'])
    compare('received_symbols', integer_iq(data['rx']['symbols']), expected['rx_symbols'])
    compare('transmitted_waveform', integer_iq(data['waveform']['tx_samples']), expected['tx_wave'])
    compare('received_waveform', integer_iq(data['waveform']['rx_samples']), expected['rx_wave'])
    compare('decoded_payload_bits', data['rx']['decoded_bits'], expected['decoded_bits'])
    compare('decoded_nodes', data['rx']['decoded_node_path'], expected['decoded_nodes'])
    compare('nearest_nodes_display', data['rx']['nearest_nodes'], expected['nearest_nodes'])
    compare('hardware_metric', hardware['final_metric'], expected['metric'])
    compare('nearest_symbol_counter', data['rx']['hard_symbol_errors'], expected['symbol_errors'])
    compare('decoded_payload_counter', data['rx']['decoded_bit_errors'], expected['payload_errors'])
    final = data['sweep_frames'][-1]
    compare('last_frame_hardware_counters', [final['symbol_errors'], final['payload_errors'], final['final_metric']],
            [expected['symbol_errors'], expected['payload_errors'], expected['metric']])
    build_path = ROOT / 'fpga_hub/iq_bridge/svg_modem/run/build/BUILD_RESULT.json'
    build = json.loads(build_path.read_text())
    for relative, digest in build['source_hashes'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise AssertionError('Current source differs from the recorded build: ' + relative)
    matching_programs = []
    for program_path in (ROOT / 'cyberether/run').glob('svg-program-*.json'):
        program = json.loads(program_path.read_text())
        if program.get('complete') and program.get('image_sha256') == build['image_sha256']:
            matching_programs.append(program_path)
    program_record = max(matching_programs, key=lambda p: p.stat().st_mtime) if matching_programs else None
    frames_audit = audit_frames(data) if all_frames else None
    return {'all_frames_audit': frames_audit, 'schema': 'svg-independent-hardware-audit-v1', 'passed': True,
            'audit_type': 'offline independent reference comparison of saved FPGA RAM/counter readbacks',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'capture_file': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            'capture_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'capture_provenance': data['provenance'], 'audit_hardware_access': False,
            'rf_tested': False, 'frame_payload_bits': count, 'frame_seed': seed,
            'noise_amplitude': amplitude, 'mode': 'arc' if arc else 'linear',
            'hardware_core_id': hardware['fpga_id'],
            'matching_program_record': str(program_record.relative_to(ROOT)) if program_record else None,
            'program_record_sha256': hashlib.sha256(program_record.read_bytes()).hexdigest() if program_record else None,
            'image_sha256': build['image_sha256'], 'source_fingerprint': build['source_fingerprint'],
            'hardware_source_hashes': build['source_hashes'],
            'reference_sources_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in [Path(__file__), ROOT / 'scripts/svg_modem.py']},
            'checks': checks, 'symbol_errors': expected['symbol_errors'], 'symbol_denominator': count + 6,
            'payload_errors': expected['payload_errors'], 'payload_denominator': count,
            'final_metric': expected['metric'],
            'scope': 'Full vectors independently checked for the final captured frame. all_frames_audit records whether all earlier frame counters/metrics were also independently decoded; timing uses known strobes, not recovered RF synchronization.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--all-frames', action='store_true', help='Independently decode and audit every saved sweep-frame counter/metric')
    args = parser.parse_args()
    path = args.capture.resolve()
    output = args.output or path.with_name(path.stem + '-audit.json')
    result = audit(path, all_frames=args.all_frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"PASS full saved FPGA frame audit: {result['symbol_errors']}/{result['symbol_denominator']} symbol errors, {result['payload_errors']}/{result['payload_denominator']} payload errors; {output}")


if __name__ == '__main__':
    main()
