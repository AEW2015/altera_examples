"""On-board 64-QAM qualification helpers, with independent host audits.

Nios generates 12-uniform approximate Gaussian noise; FPGA does all modem DSP.
"""
from __future__ import annotations
import math
import numpy as np
from modem_reference import conv_encode, quantized_mapping, fixedpoint_soft_demapper, viterbi_decode, fec_payload_plot

NOISE_MODEL = 'Nios xorshift32; sum of 12 uniform bytes; approximate Gaussian, not exact AWGN'

def next_random(state):
    x = int(state)
    x ^= (x << 13) & 0xffffffff
    x ^= x >> 17
    x ^= (x << 5) & 0xffffffff
    return x & 0xffffffff

def replay_reference(seed, sigma, frames):
    if not 0 < seed < 2**31 or not 0 <= sigma <= 8192 or not 1 <= frames <= 32:
        raise ValueError('Invalid on-board replay configuration')
    state = seed
    mapping = quantized_mapping('64QAM')
    for _ in range(frames):
        bits = []
        for _ in range(256):
            state = next_random(state); bits.append(state & 1)
        bits = np.asarray(bits, dtype=np.uint8)
        coded = conv_encode(bits)
        padded = np.pad(coded, (0, (-len(coded)) % 6))
        labels = padded.reshape(-1, 6) @ (1 << np.arange(5, -1, -1))
        tx = mapping[labels]
        rx = tx.astype(np.int32).copy()
        for i in range(len(tx)):
            for axis in range(2):
                z = -1530
                for _ in range(12):
                    state = next_random(state); z += state & 255
                magnitude = (abs(z) * sigma + 128) >> 8
                rx[i, axis] += -magnitude if z < 0 else magnitude
        rx = np.clip(rx, -32768, 32767).astype(np.int16)
    return dict(bits=bits, coded=coded, tx=tx, rx=rx, next_state=state)

def unpack_bits(words, count):
    return np.asarray([(int(words[i >> 5]) >> (i & 31)) & 1 for i in range(count)], dtype=np.uint8)

def read_snapshot(owner):
    sizes = (88, 88, 8, 8, 17, 131)
    calls = [('MSGET', kind, start, min(8, size-start))
             for kind, size in enumerate(sizes) for start in range(0, size, 8)]
    words = [[] for _ in sizes]
    for begin in range(0, len(calls), 8):
        batch = calls[begin:begin+8]
        replies = owner.commands(batch)
        for call, reply in zip(batch, replies):
            _, kind, offset, count = call
            if (reply['kind'], reply['offset'], reply['count']) != (kind, offset, count):
                raise RuntimeError('Snapshot row association mismatch')
            packed = reply['bits']
            words[kind].extend((packed >> (32*(count-i-1))) & 0xffffffff for i in range(count))
    iq = lambda w: np.asarray(w, dtype='<u4').view('<i2').reshape(-1, 2)
    llr = np.asarray(words[5], dtype='<u4').view('i1').astype(np.int32)[:524]
    return dict(tx=iq(words[0]), rx=iq(words[1]), bits=unpack_bits(words[2],256),
                decoded=unpack_bits(words[3],256), coded=unpack_bits(words[4],524), llr=llr)

def correction_overlay(actual):
    """Reconstruct the same coded-symbol sequence from real decoded payload.

    Display-only host re-encoding/remapping, never a cleaned received waveform.
    Wrong decoded bits must remain visible as wrong reconstructed symbols.
    """
    payload, decoded = np.asarray(actual['bits']), np.asarray(actual['decoded'])
    if payload.shape != (256,) or decoded.shape != payload.shape or not np.isin(payload,[0,1]).all() or not np.isin(decoded,[0,1]).all():
        raise ValueError('Overlay requires the actual 256-bit payload and FPGA decoded bits')
    coded = conv_encode(decoded)
    padded = np.pad(coded,(0,(-len(coded))%6))
    labels = padded.reshape(-1,6) @ (1 << np.arange(5,-1,-1))
    restored = quantized_mapping('64QAM')[labels]
    if np.asarray(actual['tx']).shape != restored.shape or np.asarray(actual['rx']).shape != restored.shape:
        raise ValueError('Overlay must pair the same 88 symbol positions')
    raw_wrong = (np.asarray(actual['llr'])<0) != np.asarray(actual['coded'])
    if raw_wrong.shape != (524,):raise ValueError('Overlay requires 524 coded decisions')
    before_wrong = np.pad(raw_wrong,(0,4)).reshape(-1,6).any(axis=1)
    after_wrong = (restored != actual['tx']).any(axis=1)
    xy = lambda a:(np.asarray(a,dtype=float)/8192).tolist()
    return dict(before_xy=xy(actual['rx']),after_xy=xy(restored),reference_xy=xy(actual['tx']),
                before_wrong=before_wrong.tolist(),after_wrong=after_wrong.tolist(),
                raw_bit_errors=int(raw_wrong.sum()),coded_bits=524,
                payload_bit_errors=int(np.count_nonzero(decoded!=payload)),payload_bits=256,
                wrong_reconstructed_symbols=int(after_wrong.sum()),symbols=len(restored),
                origin='Host display re-encodes and remaps actual FPGA-decoded payload bits',
                received_waveform_changed=False)


def attach_correction_overlays(proof, output):
    """Enrich older saved proofs from their audited physical snapshot files."""
    from pathlib import Path
    if proof.get('status')!='PASS':return proof
    for row in proof['rows']:
        audit=row['snapshot_audit'];plots=audit['plots']
        if plots.get('correction_overlay'):continue
        path=Path(output)/('esn0-'+format(row['esn0_db'],'g')+'-last-frame.npz')
        with np.load(path,allow_pickle=False) as data:actual={k:data[k] for k in data.files}
        # Recheck the existing snapshot before using its decoded bits for display.
        checked=audit_snapshot(actual,audit['seed'],row['sigma_q313'],audit['frames_in_chunk'])
        if checked['raw_errors']!=audit['raw_errors'] or checked['payload_errors']!=audit['payload_errors']:
            raise RuntimeError('Saved correction snapshot disagrees with recorded FPGA audit')
        np.testing.assert_array_equal(plots['mapped_xy'],checked['plots']['mapped_xy'])
        np.testing.assert_array_equal(plots['noisy_xy'],checked['plots']['noisy_xy'])
        plots['correction_overlay']=checked['plots']['correction_overlay']
    return proof


def audit_snapshot(actual, seed, sigma, frames):
    expected = replay_reference(seed, sigma, frames)
    for name in ('bits','coded','tx','rx'):
        np.testing.assert_array_equal(actual[name], expected[name], err_msg='FPGA/Nios mismatch: '+name)
    llr = fixedpoint_soft_demapper(actual['rx'], '64QAM')[:524]
    np.testing.assert_array_equal(actual['llr'], llr)
    decoded = viterbi_decode(llr)
    np.testing.assert_array_equal(actual['decoded'], decoded)
    delta = actual['rx'].astype(float)-actual['tx']
    noise_energy = float(np.mean(np.sum(delta*delta, axis=1)))
    signal_energy = float(np.mean(np.sum(actual['tx'].astype(float)**2, axis=1)))
    xy = lambda a: (np.asarray(a, dtype=float)/8192).tolist()
    return dict(status='PASS', all_fields_exact=True,
                source='Actual FPGA CI16 symbols and decoder output; Nios noise replay',
                seed=seed, frames_in_chunk=frames,
                measured_snapshot_esn0_db=10*math.log10(signal_energy/noise_energy) if noise_energy else None,
                raw_errors=int(np.count_nonzero((llr<0)!=actual['coded'])),
                payload_errors=int(np.count_nonzero(decoded!=actual['bits'])),
                plots=dict(correction_overlay=correction_overlay(actual), mapped_xy=xy(actual['tx']), noisy_xy=xy(actual['rx']),
                           post_fec=fec_payload_plot(actual['bits'], actual['decoded'], '64QAM')))

def summarize(rows):
    for row in rows:
        row['pre_fec_ber'] = row['raw_errors']/row['coded_bits'] if row['coded_bits'] else None
        row['post_fec_ber'] = row['decoded_errors']/row['payload_bits'] if row['payload_bits'] else None
        row['zero_error_95_upper_bound'] = -math.expm1(math.log(.05)/row['payload_bits']) if row['payload_bits'] and not row['decoded_errors'] else None
    return rows
