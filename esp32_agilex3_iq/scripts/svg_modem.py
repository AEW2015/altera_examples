#!/usr/bin/env python3
"""Five-point SVG graph modem reference. Python simulation only; no RF or FPGA I/O.

Symbols are destinations on a graph. Dense waveform samples are a separate
pulse-shaping illustration, with ideal receiver timing and no channel filtering.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / 'examples/svg_constellations/pentagram_circle.graph.json'
DELTAS = np.array([1, 2, -1, -2], dtype=int)


def load_graph(path=GRAPH):
    data = json.loads(Path(path).read_text())
    points = np.array([complex(n['i'], n['q']) for n in data['nodes']])
    if len(points) != 5 or not np.allclose(abs(points), 1):
        raise ValueError('Expected five unit-circle vertices')
    observed = {(int(t['source'][1:]), int(t['edge_bits'], 2)): int(t['target'][1:])
                for t in data['directed_transitions']}
    expected = {(v, p): (v + int(DELTAS[p])) % 5 for v in range(5) for p in range(4)}
    if observed != expected:
        raise ValueError('Fixture does not match the checked edge assignment')
    return points


def bits_array(bits):
    a = np.asarray(bits)
    if a.ndim != 1 or not np.all((a == 0) | (a == 1)):
        raise ValueError('Bits must be a one-dimensional sequence of zero or one')
    return a.astype(np.uint8)


def branch(memory, bit):
    """Match checkpoint06: shift input into LSB, output171 first, then133."""
    register = (int(memory) << 1) | int(bit)
    pair = (((register & 0o171).bit_count() & 1) << 1) | ((register & 0o133).bit_count() & 1)
    return register & 63, pair


def encode(bits, *, start_node=0, terminate=True):
    payload = bits_array(bits)
    if not 0 <= start_node < 5:
        raise ValueError('Invalid starting vertex')
    stream = np.r_[payload, np.zeros(6, dtype=np.uint8)] if terminate else payload
    node, memory = start_node, 0
    path, pairs, states = [node], [], [node * 64]
    for bit in stream:
        memory, pair = branch(memory, bit)
        node = (node + int(DELTAS[pair])) % 5
        path.append(node); pairs.append(pair); states.append(node * 64 + memory)
    return {'node_path': np.array(path), 'coded_pairs': np.array(pairs),
            'state_path': np.array(states), 'final_state': node * 64 + memory,
            'stream_bits': stream}


def graph_encode(bits, start_node=0):
    """Constraint-only baseline: two input bits per edge; no FEC guarantee."""
    a = bits_array(bits)
    if len(a) % 2:
        raise ValueError('Graph-only mode requires an even bit count')
    pairs = a[::2] * 2 + a[1::2]
    path = [start_node]
    for p in pairs:
        path.append((path[-1] + int(DELTAS[p])) % 5)
    return np.array(path)


def predecessors():
    """Exactly two predecessors/state: one survivor bit is sufficient."""
    parents = np.zeros((320, 2), dtype=np.int16)
    for state in range(320):
        node, memory = divmod(state, 64)
        bit = memory & 1
        for choice in range(2):
            previous_memory = (memory >> 1) | (choice << 5)
            next_memory, pair = branch(previous_memory, bit)
            assert next_memory == memory
            previous_node = (node - int(DELTAS[pair])) % 5
            parents[state, choice] = previous_node * 64 + previous_memory
    return parents


PARENTS = predecessors()


def decode(observations, *, payload_bits=None, start_node=0, terminated=True, points=None):
    y = np.asarray(observations, dtype=complex)
    if y.ndim != 1 or not np.all(np.isfinite(y)):
        raise ValueError('Observations must be finite complex samples')
    if not 0 <= start_node < 5:
        raise ValueError('Invalid starting vertex')
    if terminated and len(y) < 6:
        raise ValueError('Terminated frames need six tail symbols')
    expected = len(y) - (6 if terminated else 0)
    if payload_bits is None:
        payload_bits = expected
    if payload_bits != expected:
        raise ValueError('Payload length does not match observations and termination')
    if points is None:
        points = load_graph()
    metrics = np.full(320, np.inf)
    metrics[start_node * 64] = 0
    survivors = np.zeros((len(y), 320), dtype=np.uint8)
    offset = 0.0
    rows = np.arange(320)
    nodes = rows // 64
    for step, sample in enumerate(y):
        candidates = metrics[PARENTS]
        choice = np.argmin(candidates, axis=1)
        delta = sample - points[nodes]
        # Direct squares preserve exact integer CI16 metrics in float64;
        # abs(complex)**2 would introduce a rounded square-root intermediate.
        metrics = candidates[rows, choice] + delta.real ** 2 + delta.imag ** 2
        survivors[step] = choice
        minimum = float(np.min(metrics))
        metrics -= minimum
        offset += minimum
    eligible = np.arange(0, 320, 64) if terminated else rows
    final_state = int(eligible[np.argmin(metrics[eligible])])
    metric = float(metrics[final_state] + offset)
    state = final_state
    path = [state]
    stream = []
    for step in range(len(y) - 1, -1, -1):
        stream.append(state & 1)
        state = int(PARENTS[state, survivors[step, state]])
        path.append(state)
    if state != start_node * 64:
        raise RuntimeError('Traceback did not reach the initialized state')
    stream = np.array(stream[::-1], dtype=np.uint8)
    states = np.array(path[::-1])
    return {'decoded_bits': stream[:payload_bits], 'stream_bits': stream,
            'node_path': states // 64, 'state_path': states,
            'final_state': final_state, 'metric': metric}


def shape_waveform(path, *, mode='arc', sps=16, points=None):
    if mode not in ('arc', 'linear', 'hold') or not isinstance(sps, int) or sps < 1:
        raise ValueError('Expected arc/linear/hold and positive integer sps')
    if points is None:
        points = load_graph()
    t = np.arange(1, sps + 1) / sps
    chunks = []
    for a, b in zip(path[:-1], path[1:]):
        x, y = points[a], points[b]
        delta = (int(b) - int(a)) % 5
        if mode == 'hold':
            chunk = np.full(sps, y)
        elif mode == 'arc' and delta in (1, 4):
            angle = -2 * np.pi / 5 if delta == 1 else 2 * np.pi / 5
            chunk = x * np.exp(1j * angle * t)
        else:
            chunk = x + (y - x) * t
        chunk[-1] = y  # exact symbol-center compatibility, no rounded trigonometry drift
        chunks.append(chunk)
    return np.concatenate(chunks) if chunks else np.array([], dtype=complex)


def xy(a):
    a = np.asarray(a)
    return np.column_stack((a.real, a.imag)).tolist()


def simulate(*, seed=7, snr_db=7.0, payload_bits=256, mode='arc', sps=16):
    if payload_bits < 1 or payload_bits > 65536 or not np.isfinite(snr_db):
        raise ValueError('Expected1..65536 payload bits and finite Es/N0')
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, payload_bits, dtype=np.uint8)
    points = load_graph()
    tx = encode(bits)
    waveform = shape_waveform(tx['node_path'], mode=mode, sps=sps, points=points)
    sigma = np.sqrt(0.5 * 10 ** (-snr_db / 10))
    noisy = waveform + sigma * (rng.standard_normal(len(waveform)) + 1j * rng.standard_normal(len(waveform)))
    observations = noisy[sps - 1::sps]
    decoded = decode(observations, points=points)
    nearest = np.argmin(abs(observations[:, None] - points) ** 2, axis=1)
    errors = int(np.count_nonzero(decoded['decoded_bits'] != bits))
    hard = int(np.count_nonzero(nearest != tx['node_path'][1:]))
    recovered = encode(decoded['decoded_bits'])
    effective_rate = payload_bits / len(observations)
    graph_hash = hashlib.sha256(GRAPH.read_bytes()).hexdigest()
    return {'schema': 'svg-modem-simulation-v1', 'simulation_only': True,
            'implemented_in_fpga': False, 'rf_tested': False,
            'receiver_timing': 'ideal known symbol boundaries; timing recovery not modeled',
            'noise_model': 'independent complex AWGN per sample; no receive filtering',
            'decoder_input': 'noisy oversampled waveform at each segment endpoint',
            'seed': seed, 'snr_db': snr_db, 'es_n0_db': snr_db,
            'eb_n0_db': float(snr_db - 10 * np.log10(effective_rate)),
            'effective_payload_bits_per_symbol': effective_rate,
            'payload_bits': bits.tolist(), 'constellation': xy(points),
            'graph_sha256': graph_hash,
            'code': {'polynomials_octal': ['171', '133'], 'states': 320,
                     'start_node': 0, 'start_memory': 0, 'tail_bits': 6,
                     'branch_metric': 'squared Euclidean distance; per-step normalization'},
            'tx': {'node_path': tx['node_path'].tolist(), 'coded_pairs': tx['coded_pairs'].tolist(),
                   'symbols': xy(points[tx['node_path'][1:]]), 'final_state': tx['final_state']},
            'rx': {'symbols': xy(observations), 'nearest_nodes': nearest.tolist(),
                   'decoded_bits': decoded['decoded_bits'].tolist(),
                   'decoded_node_path': decoded['node_path'].tolist(),
                   'reencoded_node_path': recovered['node_path'].tolist(),
                   'final_state': decoded['final_state'], 'path_metric': decoded['metric'],
                   'hard_symbol_errors': hard, 'symbol_count': len(observations),
                   'hard_symbol_error_rate': hard / len(observations),
                   'decoded_bit_errors': errors, 'payload_bit_count': payload_bits,
                   'post_fec_ber': errors / payload_bits,
                   'decoded_symbol_errors': int(np.count_nonzero(decoded['node_path'][1:] != tx['node_path'][1:])),
                   'note': 'Hard symbol errors and payload BER have different denominators; corrected points are decoder-selected ideal destinations, not cleaned RF samples.'},
            'waveform': {'sps': sps, 'mode': mode, 'tx_samples': xy(waveform),
                         'rx_samples': xy(noisy),
                         'sample_symbol_indices': np.repeat(np.arange(len(observations)), sps).tolist()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'cyberether/run/svg-modem.json')
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--snr-db', type=float, default=7)
    parser.add_argument('--bits', type=int, default=256)
    parser.add_argument('--mode', choices=['hold', 'linear', 'arc'], default='arc')
    parser.add_argument('--sps', type=int, default=16)
    args = parser.parse_args()
    result = simulate(seed=args.seed, snr_db=args.snr_db, payload_bits=args.bits, mode=args.mode, sps=args.sps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Python simulation: {result['rx']['hard_symbol_errors']}/{result['rx']['symbol_count']} symbol errors; {result['rx']['decoded_bit_errors']}/{args.bits} payload errors. Saved {args.output}")


if __name__ == '__main__':
    main()
