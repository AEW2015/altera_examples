"""Deterministic *host simulation* of the educational burst modem.

This is an independent floating-point reference, not operational FPGA DSP.
Bits are MSB first. QAM labels group I bits then Q bits. On each axis the
ascending amplitude index k has Gray label k^(k>>1). BPSK is 0:+1, 1:-1.
Convolutional code: initial state zero; reg=(state<<1)|bit; parity 171 then
133 (octal); state=reg&63. Six zero tail bits terminate the code. Soft values
are positive for bit zero. Energy-normalized constellations have mean Es=1.
"""
from __future__ import annotations

import binascii
import math
import struct
import zlib
from functools import lru_cache

import numpy as np

MODES = ('BPSK', 'QPSK', '16QAM', '64QAM')
BITS_PER_SYMBOL = dict(zip(MODES, (1, 2, 4, 6)))
VERSION = 1
# One repeated acquisition sequence followed by independent training.
_PRE = np.random.default_rng(148).integers(0, 2, 32, dtype=np.uint8)
PREAMBLE = np.tile(1. - 2. * _PRE, 2).astype(complex)
TRAINING = (1. - 2. * np.random.default_rng(921).integers(0, 2, 64)).astype(complex)
PILOTS = np.array([1, 1j, -1, -1j], dtype=complex)
HEADER_BYTES = 9
HEADER_CODE_BITS = 2 * (HEADER_BYTES * 8 + 6)
MAX_PAYLOAD_BYTES = 4096


def _mode(name):
    name = str(name).upper().replace('-', '').replace('_', '')
    if name not in MODES:
        raise ValueError('modulation must be BPSK, QPSK, 16QAM or 64QAM')
    return name


def _bits(bits):
    a = np.asarray(bits)
    if a.ndim != 1 or np.any((a != 0) & (a != 1)):
        raise ValueError('bits must be a one-dimensional binary sequence')
    return a.astype(np.uint8)


def bytes_to_bits(data):
    return np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8))


def bits_to_bytes(bits):
    a = _bits(bits)
    if len(a) % 8:
        raise ValueError('byte conversion requires a multiple of eight bits')
    return np.packbits(a).tobytes()


@lru_cache(maxsize=4)
def constellation(modulation='QPSK'):
    """Return (complex points, bit labels); rows are binary label order."""
    mode = _mode(modulation)
    width = BITS_PER_SYMBOL[mode]
    labels = ((np.arange(1 << width)[:, None] >> np.arange(width-1, -1, -1)) & 1).astype(np.uint8)
    if width == 1:
        points = np.array([1., -1.], dtype=complex)
    else:
        n = width // 2
        levels = 1 << n
        gray_to_level = np.zeros(levels)
        for k in range(levels):
            gray_to_level[k ^ (k >> 1)] = 2*k - levels + 1
        ids = np.arange(1 << width)
        points = (gray_to_level[ids >> n] + 1j*gray_to_level[ids & (levels-1)]) / np.sqrt(2*(levels*levels-1)/3)
    points.setflags(write=False)
    labels.setflags(write=False)
    return points, labels


def quantized_mapping(modulation='QPSK', scale=8192):
    """Signed Q3.13 defaults, nearest-even; array [label, I/Q]."""
    p, _ = constellation(modulation)
    q = np.rint(np.column_stack((p.real, p.imag)) * scale)
    if np.max(np.abs(q)) > 32767:
        raise ValueError('mapping does not fit signed 16-bit')
    return q.astype(np.int16)


def map_bits(bits, modulation='QPSK'):
    mode = _mode(modulation)
    b = _bits(bits)
    w = BITS_PER_SYMBOL[mode]
    if len(b) % w:
        raise ValueError('bit count must be a multiple of bits per symbol')
    ids = b.reshape(-1, w) @ (1 << np.arange(w-1, -1, -1))
    return constellation(mode)[0][ids]


def soft_demapper(symbols, modulation='QPSK', noise_variance=1.):
    """Max-log LLRs flattened MSB-first; positive favors 0 (complex E|n|²)."""
    if not np.isfinite(noise_variance) or noise_variance <= 0:
        raise ValueError('noise_variance must be positive')
    points, labels = constellation(_mode(modulation))
    x = np.asarray(symbols, dtype=complex).reshape(-1)
    distance = abs(x[:, None] - points[None, :])**2
    return np.column_stack([(distance[:, labels[:, k] == 1].min(axis=1) - distance[:, labels[:, k] == 0].min(axis=1))/noise_variance for k in range(labels.shape[1])]).reshape(-1)


def fixedpoint_soft_demapper(iq, modulation='QPSK', shift=18, limit=127):
    """Checkpoint06 independent integer max-log reference, positive means zero.

    Input CI16 [N,2], Q3.13; distances to quantized LUT points use int64.
    Arithmetic right shift and saturation deliberately match RTL, not a noise
    variance-scaled floating LLR. Return one signed metric per coded bit.
    """
    a = np.asarray(iq)
    if a.ndim != 2 or a.shape[1] != 2 or not np.all(np.isfinite(a)) or not np.all(a == np.rint(a)) or np.any(a < -32768) or np.any(a > 32767):
        raise ValueError('expected signed CI16 integer pairs')
    if not isinstance(shift, int) or not 0 <= shift <= 62 or not isinstance(limit, int) or not 1 <= limit <= 127:
        raise ValueError('invalid integer metric scale')
    points = quantized_mapping(modulation).astype(np.int64)
    labels = constellation(modulation)[1]
    delta = a.astype(np.int64)[:, None, :] - points[None, :, :]
    distance = np.sum(delta*delta, axis=2)
    metrics = np.column_stack([distance[:, labels[:, k] == 1].min(axis=1) - distance[:, labels[:, k] == 0].min(axis=1) for k in range(labels.shape[1])])
    return np.clip(metrics >> shift, -limit, limit).astype(np.int8).reshape(-1)


def hard_demapper(symbols, modulation='QPSK'):
    return (soft_demapper(symbols, modulation) < 0).astype(np.uint8)


@lru_cache(maxsize=1)
def _trellis():
    states = np.arange(64)
    next_state = np.zeros((64, 2), dtype=int)
    outputs = np.zeros((64, 2, 2), dtype=np.uint8)
    for state in states:
        for bit in (0, 1):
            reg = (int(state) << 1) | bit
            next_state[state, bit] = reg & 63
            outputs[state, bit] = [(reg & 0o171).bit_count() & 1, (reg & 0o133).bit_count() & 1]
    return next_state, outputs


def conv_encode(bits, terminate=True):
    b = _bits(bits)
    if terminate:
        b = np.r_[b, np.zeros(6, dtype=np.uint8)]
    state = 0
    result = []
    nxt, out = _trellis()
    for bit in b:
        result.extend(out[state, bit])
        state = nxt[state, bit]
    return np.array(result, dtype=np.uint8)


def viterbi_decode(values, soft=True, terminated=True):
    """Full-block 64-state ML decoding; removes six tail bits if terminated."""
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or len(a) % 2 or not np.all(np.isfinite(a)):
        raise ValueError('decoder expects a finite even-length metric vector')
    if not soft:
        a = 1. - 2.*_bits(a)
    a = a.reshape(-1, 2)
    _, out = _trellis()
    # Every next state has two predecessors, distinguishable by old bit 5.
    targets = np.arange(64)
    bit = targets & 1
    pred = np.column_stack((targets >> 1, (targets >> 1) | 32))
    expected = 1. - 2.*out[pred, bit[:, None], :].astype(float)
    metric = np.full(64, np.inf)
    metric[0] = 0.
    choices = np.zeros((len(a), 64), dtype=np.uint8)
    for t, pair in enumerate(a):
        candidates = metric[pred] - np.sum(expected * pair, axis=2)
        select = np.argmin(candidates, axis=1)
        choices[t] = select
        metric = candidates[targets, select]
        metric -= metric.min()
    state = 0 if terminated else int(np.argmin(metric))
    result = np.zeros(len(a), dtype=np.uint8)
    for t in range(len(a)-1, -1, -1):
        result[t] = state & 1
        state = pred[state, choices[t, state]]
    return result[:-6] if terminated else result


def scramble(bits):
    """Additive x^7+x^4+1 scrambler; same operation descrambles, seed 0x5d."""
    result = _bits(bits).copy()
    state = 0x5d
    for k in range(len(result)):
        feedback = ((state >> 6) ^ (state >> 3)) & 1
        result[k] ^= feedback
        state = ((state << 1) | feedback) & 127
    return result


def rrc_taps(sps=4, span=10, beta=.35):
    if not isinstance(sps, int) or sps < 2 or span < 2 or span % 2 or not 0 < beta <= 1:
        raise ValueError('RRC requires integer sps>=2, even span>=2, and 0<beta<=1')
    t = np.arange(-span*sps//2, span*sps//2+1)/sps
    h = np.zeros(len(t))
    for i, x in enumerate(t):
        if abs(x) < 1e-12:
            h[i] = 1 + beta*(4/np.pi-1)
        elif abs(abs(4*beta*x)-1) < 1e-10:
            h[i] = beta/np.sqrt(2)*((1+2/np.pi)*np.sin(np.pi/(4*beta))+(1-2/np.pi)*np.cos(np.pi/(4*beta)))
        else:
            h[i] = (np.sin(np.pi*x*(1-beta))+4*beta*x*np.cos(np.pi*x*(1+beta)))/(np.pi*x*(1-(4*beta*x)**2))
    return h/np.sqrt(np.sum(h*h))


def _header(payload_len, mode, coded, frame_id):
    h = struct.pack('>BBBHH', VERSION, MODES.index(mode), int(coded), payload_len, frame_id & 65535)
    return h + struct.pack('>H', binascii.crc_hqx(h, 0xffff))


def build_frame(payload=b'Agilex 3 modem', modulation='QPSK', coded=True, sps=4, frame_id=0):
    """Create a version-1 frame and oracle data used only by BER measurement.

    64-symbol repeated BPSK preamble, 64 training symbols, K7-protected BPSK
    header, then payload symbols with four known pilots preceding each <=32
    symbol block. Payload carries CRC32 then scrambles, codes and zero-pads.
    """
    mode = _mode(modulation)
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError('payload exceeds 4096-byte reference limit')
    data = payload + struct.pack('>I', zlib.crc32(payload))
    payload_bits = bytes_to_bits(data)
    scrambled = scramble(payload_bits)
    encoded = conv_encode(scrambled) if coded else scrambled
    width = BITS_PER_SYMBOL[mode]
    padded = np.pad(encoded, (0, (-len(encoded)) % width))
    mapped = map_bits(padded, mode)
    body = []
    for start in range(0, len(mapped), 32):
        body.extend(PILOTS)
        body.extend(mapped[start:start+32])
    header_bits = conv_encode(bytes_to_bits(_header(len(payload), mode, coded, frame_id)))
    symbols = np.r_[PREAMBLE, TRAINING, map_bits(header_bits, 'BPSK'), np.array(body)]
    h = rrc_taps(sps)
    # Guards make arbitrary positive acquisition offsets and RX filter tails explicit.
    impulses = np.zeros((len(symbols)-1)*sps+1, complex)
    impulses[::sps] = symbols
    guard = 16*sps
    waveform = np.r_[np.zeros(guard), np.convolve(impulses, h), np.zeros(guard)]
    return dict(waveform=waveform, symbols=symbols, payload=payload, payload_bits=payload_bits,
                coded_bits=encoded, mapped_symbols=mapped, modulation=mode, coded=bool(coded),
                sps=sps, frame_id=frame_id, symbol_start=guard+(len(h)-1)/2,
                format='modem-reference-v1', source='Python simulation')


def impair(waveform, snr_db=18., cfo_hz=1500., sample_rate=4e6, timing_offset=.25,
           phase=1.1, gain=.8, multipath=False, seed=7, sample_clock_ppm=0.):
    """AWGN SNR is Es/N0 at unit-energy matched-filter output (not Eb/N0).

    Apply a known bounded fractional delay, CFO and optional FIR channel.
    Noise is complex with E|n|²=|gain|²*10^(-EsN0/10). No automatic AGC.
    """
    if sample_rate <= 0 or not np.isfinite(snr_db) or abs(sample_clock_ppm) > 1000:
        raise ValueError('invalid impairment setting')
    x = np.asarray(waveform, dtype=complex)
    time = (np.arange(len(x))-timing_offset)*(1+sample_clock_ppm*1e-6)
    x = np.interp(time, np.arange(len(x)), x.real, left=0, right=0) + 1j*np.interp(time, np.arange(len(x)), x.imag, left=0, right=0)
    if multipath:
        channel = np.array([1., 0., .22*np.exp(.6j)]) if isinstance(multipath, (bool, np.bool_)) else np.asarray(multipath, complex)
        x = np.convolve(x, channel)
    x = gain*x*np.exp(1j*(phase+2*np.pi*cfo_hz*np.arange(len(x))/sample_rate))
    rng = np.random.default_rng(seed)
    variance = abs(gain)**2*10.**(-snr_db/10.)
    return x + np.sqrt(variance/2)*(rng.normal(size=len(x))+1j*rng.normal(size=len(x)))


def _sample(x, positions):
    return np.interp(positions, np.arange(len(x)), x.real) + 1j*np.interp(positions, np.arange(len(x)), x.imag)


def _acquire(matched, sps):
    """Search every sample; repetition estimates CFO, known preamble validates it."""
    n = len(matched)-len(PREAMBLE)*sps
    if n <= 0:
        return None
    # Vectorized search of all starts. Integer acquisition then fractional refinement.
    best, best_score = 0, -1.
    for batch in range(0, n, 2048):
        starts = np.arange(batch, min(n, batch+2048))
        samples = matched[starts[:, None] + np.arange(64)[None, :]*sps]
        rotation = np.angle(np.sum(samples[:, 32:]*np.conj(samples[:, :32]), axis=1))/(32*sps)
        corrected = samples*np.exp(-1j*rotation[:, None]*np.arange(64)[None, :]*sps)
        score = abs(corrected @ PREAMBLE.conj())**2/(64*np.sum(abs(corrected)**2, axis=1)+1e-15)
        index = int(np.argmax(score))
        if score[index] > best_score:
            best, best_score = int(starts[index]), float(score[index])
    trials = best+np.linspace(-.75, .75, 25)
    vals = np.array([_sample(matched, t+np.arange(64)*sps) for t in trials])
    rot = np.angle(np.sum(vals[:, 32:]*np.conj(vals[:, :32]), axis=1))/(32*sps)
    cor = vals*np.exp(-1j*rot[:, None]*np.arange(64)[None, :]*sps)
    scores = abs(cor @ PREAMBLE.conj())**2/(64*np.sum(abs(cor)**2, axis=1)+1e-15)
    k = int(np.argmax(scores))
    return float(trials[k]), float(rot[k]), float(scores[k])


def receive_frame(samples, sps=4, sample_rate=4e6, decode_mode='soft', equalize=True):
    """Acquire/decode without oracle payload, mode, phase, CFO or frame position.

    Short-burst reference: fractional timing is acquired once, pilots track
    block phase/gain, a trained 5-tap symbol-spaced equalizer corrects mild ISI.
    This does not implement a continuous timing loop or unrestricted channels.
    """
    if decode_mode not in ('soft', 'hard'):
        raise ValueError('decode_mode must be soft or hard')
    x = np.asarray(samples, dtype=complex).reshape(-1)
    result = dict(locked=False, header_ok=False, crc_ok=False, payload=b'', reason='no preamble',
                  source='Python simulation', raw_iq=x, recovered_symbols=np.array([], complex),
                  matched_symbols=np.array([], complex), pre_equalized_symbols=np.array([], complex))
    if len(x) < 128*sps or not np.all(np.isfinite(x)):
        return result
    matched = np.convolve(x, rrc_taps(sps))
    acquisition = _acquire(matched, sps)
    if acquisition is None or acquisition[2] < .45:
        return result
    start, omega, quality = acquisition
    # Correct before the matched filter to avoid frequency-offset filter loss.
    corrected = x*np.exp(-1j*omega*np.arange(len(x)))
    matched = np.convolve(corrected, rrc_taps(sps))
    positions = start+np.arange(max(0, int((len(matched)-start-1)//sps)))*sps
    symbols = _sample(matched, positions)
    if len(symbols) >= 128:
        known = np.r_[PREAMBLE, TRAINING]
        phase = np.unwrap(np.angle(symbols[:128]/known))
        slope, _ = np.polyfit(np.arange(8, 120), phase[8:120], 1)
        omega += slope/sps
        matched = np.convolve(x*np.exp(-1j*omega*np.arange(len(x))), rrc_taps(sps))
        symbols = _sample(matched, positions)
    result.update(locked=True, acquisition_score=quality, estimated_cfo_hz=omega*sample_rate/(2*np.pi),
                  timing_offset_samples=start % sps, frame_start_sample=start, matched_symbols=symbols.copy())
    if len(symbols) < 128+HEADER_CODE_BITS:
        result['reason'] = 'truncated header'
        return result
    # Training first removes scalar phase/gain. FIR inverse is trained, never payload-aided.
    gain = np.vdot(TRAINING, symbols[64:128])/len(TRAINING)
    if abs(gain) < 1e-9:
        result['reason'] = 'weak training'
        return result
    symbols /= gain
    pre_equalized = symbols.copy()
    taps = np.array([0., 0., 1., 0., 0.], complex)
    if equalize:
        centers = np.arange(66, 126)
        windows = symbols[centers[:, None]+np.arange(-2, 3)]
        gram = windows.conj().T@windows
        taps = np.linalg.solve(gram+.01*np.eye(5), windows.conj().T@TRAINING[2:62])
        padded = np.pad(symbols, (2, 2))
        symbols = np.lib.stride_tricks.sliding_window_view(padded, 5) @ taps
    header_symbols = symbols[128:128+HEADER_CODE_BITS]
    header_bits = viterbi_decode(soft_demapper(header_symbols, 'BPSK'), soft=True)
    header = bits_to_bytes(header_bits)
    if len(header) != HEADER_BYTES or binascii.crc_hqx(header[:-2], 0xffff) != int.from_bytes(header[-2:], 'big'):
        result['reason'] = 'header CRC failure'
        return result
    version, modeid, flags, payload_len, frameid = struct.unpack('>BBBHH', header[:-2])
    if version != VERSION or modeid >= len(MODES) or flags not in (0, 1) or payload_len > MAX_PAYLOAD_BYTES:
        result['reason'] = 'unsupported header'
        return result
    mode = MODES[modeid]
    coded = bool(flags)
    result.update(header_ok=True, modulation=mode, coded=coded, frame_id=frameid)
    bitcount = (payload_len+4)*8
    coded_count = 2*(bitcount+6) if coded else bitcount
    symbol_count = math.ceil(coded_count/BITS_PER_SYMBOL[mode])
    pos = 128+HEADER_CODE_BITS
    received, before, pilots_received = [], [], []
    for begin in range(0, symbol_count, 32):
        count = min(32, symbol_count-begin)
        if pos+4+count > len(symbols):
            result['reason'] = 'truncated payload'
            result['header_ok'] = True
            return result
        pilot = symbols[pos:pos+4]
        g = np.vdot(PILOTS, pilot)/4
        if abs(g) < .05:
            result['reason'] = 'weak pilots'
            return result
        # Block pilots estimate a scalar channel; derivative estimation from
        # four noisy pilots would add phase noise, especially on 64-QAM.
        block = symbols[pos+4:pos+4+count]/g
        received.extend(block)
        before.extend(pre_equalized[pos+4:pos+4+count])
        pilots_received.extend(pilot)
        pos += 4+count
    received = np.array(received)
    metrics = soft_demapper(received, mode)[:coded_count]
    hard_bits = (metrics < 0).astype(np.uint8)
    decoded_soft = viterbi_decode(metrics) if coded else hard_bits
    decoded_hard = viterbi_decode(hard_bits, soft=False) if coded else hard_bits
    decoded = decoded_soft if decode_mode == 'soft' else decoded_hard
    raw = bits_to_bytes(scramble(decoded))
    payload, crc = raw[:-4], raw[-4:]
    result.update(header_ok=True, crc_ok=zlib.crc32(payload) == int.from_bytes(crc, 'big'),
                  payload=payload, modulation=mode, coded=coded, frame_id=frameid,
                  recovered_symbols=received, pre_equalized_symbols=np.array(before),
                  soft_metrics=metrics, hard_bits=hard_bits,
                  decoded_soft_bits=scramble(decoded_soft), decoded_hard_bits=scramble(decoded_hard),
                  equalizer_taps=taps, reason='decoded', estimated_gain=complex(gain))
    return result


def run_experiment(modulation='QPSK', snr_db=18., cfo_hz=1500., timing_offset=.25,
                   multipath=False, seed=7, payload_bits=2048, decode_mode='soft',
                   sample_rate=4e6, sps=4, coded=True, equalize=True):
    """JSON-safe single-frame experiment for the notebook/browser.

    BER denominators include CRC bits for pre-FEC but exclude CRC/tail/padding
    for post-FEC. A failed acquisition has no bit BER: report null, count frame
    failures instead. Es/N0 is the noise control; this is NOT an equal-Eb/N0
    coded/uncoded comparison or an RF result.
    """
    mode = _mode(modulation)
    if payload_bits < 8 or payload_bits > MAX_PAYLOAD_BYTES*8 or payload_bits % 8:
        raise ValueError('payload_bits must be 8..32768 and byte aligned')
    rng = np.random.default_rng(seed)
    payload = rng.integers(0, 256, payload_bits//8, dtype=np.uint8).tobytes()
    tx = build_frame(payload, mode, coded, sps, frame_id=seed)
    x = impair(tx['waveform'], snr_db, cfo_hz, sample_rate, timing_offset,
               multipath=multipath, seed=seed+1)
    rx = receive_frame(x, sps, sample_rate, decode_mode, equalize)
    success = rx['header_ok'] and 'hard_bits' in rx
    metrics = dict(locked=rx['locked'], header_ok=rx['header_ok'], crc_ok=rx['crc_ok'],
                   cfo_hz=cfo_hz, estimated_cfo_hz=rx.get('estimated_cfo_hz'),
                   timing_offset_samples=rx.get('timing_offset_samples'), evm_percent=None,
                   pre_fec_errors=None, pre_fec_bits=0, pre_fec_ber=None,
                   post_fec_errors=None, post_fec_bits=0, post_fec_ber=None,
                   hard_fec_errors=None, soft_fec_errors=None,
                   acquisition_failures=int(not rx['locked']), frame_failures=int(not rx['crc_ok']),
                   reason=rx['reason'], noise_axis='Es/N0 dB', independent_frames=1,
                   source='Python simulation')
    if success:
        reference_energy = float(np.mean(abs(tx['mapped_symbols'])**2))
        errors = int(np.count_nonzero(rx['hard_bits'] != tx['coded_bits']))
        harderr = int(np.count_nonzero(rx['decoded_hard_bits'][:payload_bits] != tx['payload_bits'][:payload_bits]))
        softerr = int(np.count_nonzero(rx['decoded_soft_bits'][:payload_bits] != tx['payload_bits'][:payload_bits]))
        finalerr = softerr if decode_mode == 'soft' else harderr
        metrics.update(pre_fec_errors=errors, pre_fec_bits=len(tx['coded_bits']),
                       pre_fec_ber=errors/len(tx['coded_bits']),
                       post_fec_errors=finalerr, post_fec_bits=payload_bits,
                       post_fec_ber=finalerr/payload_bits, hard_fec_errors=harderr,
                       soft_fec_errors=softerr,
                       evm_percent=float(100*np.sqrt(np.mean(abs(rx['recovered_symbols']-tx['mapped_symbols'])**2)/reference_energy)),
                       pre_equalizer_evm_percent=float(100*np.sqrt(np.mean(abs(rx['pre_equalized_symbols']-tx['mapped_symbols'])**2)/reference_energy)),
                       evm_normalization='RMS known payload symbols; after trained gain/equalizer and block-pilot phase correction')
    def xy(a, maximum=1400):
        a = np.asarray(a)[:maximum]
        return np.column_stack((a.real, a.imag)).tolist()
    spec = np.fft.fftshift(np.fft.fft(x[:4096], n=4096))
    matched = np.convolve(x, rrc_taps(sps))
    eye = [matched[k:k+2*sps+1].real.tolist() for k in range(64*sps, min(len(matched)-2*sps, 64*sps+80*sps), sps)]
    return dict(source='Python simulation — no FPGA or RF acquisition',
                settings=dict(modulation=mode, snr_db=snr_db, cfo_hz=cfo_hz,
                              timing_offset=timing_offset, multipath=bool(multipath), seed=seed,
                              payload_bits=payload_bits, decode_mode=decode_mode, coded=bool(coded),
                              sample_rate=sample_rate, symbol_rate=sample_rate/sps, sps=sps, equalize=bool(equalize)),
                metrics=metrics,
                plots=dict(raw_xy=xy(x), matched_xy=xy(rx['matched_symbols']),
                           recovered_xy=xy(rx['recovered_symbols']),
                           ideal_xy=xy(constellation(mode)[0]),
                           eye=dict(x=(np.arange(2*sps+1)/sps).tolist(), traces=eye),
                           spectrum=dict(frequency_hz=np.fft.fftshift(np.fft.fftfreq(4096, 1/sample_rate)).tolist(),
                                         power_db=(20*np.log10(np.maximum(abs(spec), 1e-8))).tolist())),
                stages=['CRC32', 'Scramble', 'K7 171/133 FEC' if coded else 'Uncoded',
                        mode+' map', 'RRC', 'Simulated channel', 'Preamble/CFO',
                        'Matched filter/timing', 'Training equalizer', 'Pilot tracking',
                        'Soft demap', 'Viterbi' if coded else 'Hard bits', 'Descramble/CRC/BER'])


def tx_waveform(payload=b'A', modulation='QPSK', sample_rate=40e6, symbol_rate=1e6,
                amplitude=420, max_samples=16128, alignment=256, frame_id=0, coded=True):
    """Prepare host-generated SRAM playback IQ10 bytes, never claim FPGA TX.

    Each LE32 word stores two's-complement I[9:0], Q[19:10], bits31:20=0.
    RRC and framing are identical to build_frame, with guards reduced from
    16 to 2 symbols per side to fit short SRAM jobs. Padding is silence and
    is included in the returned waveform/sample count. Reject, never truncate.
    'amplitude' is a peak component target (1..511), not an RF gain setting.
    """
    ratio = sample_rate/symbol_rate
    sps = int(round(ratio))
    if sample_rate <= 0 or symbol_rate <= 0 or abs(ratio-sps) > 1e-9 or sps < 2:
        raise ValueError('sample_rate/symbol_rate must be an integer >=2')
    if not isinstance(alignment, int) or alignment <= 0 or max_samples < alignment:
        raise ValueError('invalid SRAM capacity/alignment')
    if not np.isfinite(amplitude) or not 1 <= amplitude <= 511:
        raise ValueError('IQ10 peak amplitude must be 1..511')
    tx = build_frame(payload, modulation, coded, sps, frame_id)
    x = tx['waveform'][14*sps:-14*sps]
    count = math.ceil(len(x)/alignment)*alignment
    if count > max_samples:
        raise ValueError(f'complete frame needs {count} aligned samples, SRAM capacity is {max_samples}; reduce payload or samples/symbol')
    x = np.pad(x, (0, count-len(x)))
    peak = max(float(np.max(abs(x.real))), float(np.max(abs(x.imag))))
    q = np.rint(np.column_stack((x.real, x.imag)) * amplitude/max(peak, 1e-12)).astype(np.int32)
    packed = ((q[:, 0] & 1023) | ((q[:, 1] & 1023) << 10)).astype('<u4').tobytes()
    return dict(iq10_bytes=packed, waveform=x, sample_count=count, payload_bytes=len(payload),
                sample_rate=sample_rate, symbol_rate=symbol_rate, sps=sps, amplitude=amplitude,
                peak_component=int(np.max(abs(q))), clipped_samples=0,
                duration_seconds=count/sample_rate, format='LE32 I10[9:0] Q10[19:10]',
                source='Host-generated modem reference; ESP32 TX not qualified',
                modulation=_mode(modulation), frame_id=frame_id)


def ber_sweep(modulation='64QAM', snr_values=(8, 12, 16, 20), seeds=range(5),
              payload_bits=2048, **kwargs):
    """Accumulate independent frames; failures remain separate from measured BER.

    This is a deterministic Es/N0 sweep. Call with >=100k payload bits/point
    for a serious plot; defaults are deliberately a quick educational preview.
    """
    seeds = tuple(seeds)
    if not seeds:
        raise ValueError('at least one seed is required')
    rows = []
    for snr in snr_values:
        totals = dict(snr_db=float(snr), frames=len(seeds), acquisition_failures=0,
                      frame_failures=0, pre_fec_errors=0, pre_fec_bits=0,
                      post_fec_errors=0, post_fec_bits=0, hard_fec_errors=0,
                      soft_fec_errors=0, observed_payload_bits=0)
        for seed in seeds:
            metrics = run_experiment(modulation, snr_db=snr, seed=seed,
                                     payload_bits=payload_bits, **kwargs)['metrics']
            for key in ('acquisition_failures', 'frame_failures', 'pre_fec_errors',
                        'pre_fec_bits', 'post_fec_errors', 'post_fec_bits',
                        'hard_fec_errors', 'soft_fec_errors'):
                if metrics[key] is not None:
                    totals[key] += metrics[key]
            totals['observed_payload_bits'] += metrics['post_fec_bits']
        totals['pre_fec_ber'] = totals['pre_fec_errors']/totals['pre_fec_bits'] if totals['pre_fec_bits'] else None
        totals['post_fec_ber'] = totals['post_fec_errors']/totals['post_fec_bits'] if totals['post_fec_bits'] else None
        totals['hard_fec_ber'] = totals['hard_fec_errors']/totals['post_fec_bits'] if totals['post_fec_bits'] else None
        totals['soft_fec_ber'] = totals['soft_fec_errors']/totals['post_fec_bits'] if totals['post_fec_bits'] else None
        rows.append(totals)
    return dict(source='Python simulation', noise_axis='Es/N0 dB', rows=rows,
                note='BER excludes undecodable headers/acquisition failures; those are counted separately. Zero observed errors is not zero true BER.')
