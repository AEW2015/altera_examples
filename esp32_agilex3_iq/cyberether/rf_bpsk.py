"""Original ESP32 framed phase-pulse BPSK: host reference, never FPGA DSP.

Contract v1: marker 0x0651 (MSB first), then 44 K=7 (171,133 octal) coded
bits carrying payload8 + CRC8 (07, init0), plus six zero termination bits.
Encoder starts at zero each frame, four guard zeros complete the frame.
All 64 bits are absolute BPSK states (0:+1, 1:-1). Frequency pulses implement
state transitions and occupy the early part of each symbol. The receiver
integrates late-symbol samples, acquiring timing, carrier and phase from RX.
Only the sync marker participates in acquisition. Known payload is optional,
post-decode instrumentation; it cannot force synchronization or CRC success.
"""
from __future__ import annotations
import numpy as np
from modem_reference import conv_encode, viterbi_decode

MARKER = 0x0651
FRAME_SYMBOLS = 64


def int_bits(value, count):
    if not isinstance(value, (int, np.integer)) or not 0 <= value < 1 << count:
        raise ValueError(f'value must fit {count} bits')
    return ((value >> np.arange(count-1, -1, -1)) & 1).astype(np.uint8)


def crc8(data):
    crc = 0
    for byte in bytes(data):
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (7 if crc & 128 else 0)) & 255
    return crc


def encode(bits):
    return conv_encode(bits, terminate=True)


def decode(llr):
    return viterbi_decode(llr, soft=True, terminated=True)


def frame_bits(payload):
    if not isinstance(payload, (int, np.integer)) or not 0 <= payload < 256:
        raise ValueError('payload must be an unsigned byte')
    body = np.r_[int_bits(payload, 8), int_bits(crc8(bytes([payload])), 8)]
    return np.r_[int_bits(MARKER, 16), encode(body), np.zeros(4,np.uint8)]


def _complex(iq):
    a = np.asarray(iq)
    if a.ndim == 2 and a.shape[1] == 2:
        return a[:, 0].astype(float) + 1j*a[:, 1].astype(float)
    if a.ndim == 1 and np.iscomplexobj(a):
        return a.astype(complex)
    raise ValueError('expected signed CI8 [N,2] or complex samples')


def synthesize(payload=0xa5, *, rate=16e6, symbol_us=8., pulse_us=4.267,
               samples=16380, offset_samples=47, cfo_hz=17321., phase=.7,
               amplitude=35., noise_std=1., seed=1, pulse_error=0., coded_flips=()):
    """Synthetic test fixture, not actual RF or an ESP32 playback function.

    Late-symbol states are joined by positive phase ramps, as in the scalar
    NCO experiment. pulse_error is fractional phase-area error per transition.
    coded_flips corrupt specified transmitted coded bits before RF generation.
    """
    sps = int(round(rate*symbol_us/1e6))
    pulse = int(round(rate*pulse_us/1e6))
    if sps < 4 or not 0 < pulse < sps:
        raise ValueError('pulse must fit inside a symbol')
    bits = frame_bits(payload)
    for bit in coded_flips:
        if not 0 <= bit < 44:
            raise ValueError('coded flip index must be0..43')
        bits[16+int(bit)] ^= 1
    # Generate a history before cropping so an arbitrary capture start can cut
    # a pulse or frame. Positive π ramps accumulate physical phase.
    count = samples + offset_samples + 2*sps
    phase_trace = np.zeros(count)
    previous, level = int(bits[-1]), 0.
    for start in range(0, count, sps):
        bit = int(bits[(start//sps) % 64])
        end = min(start+sps, count)
        if bit != previous:
            phase_trace[start:end] = level + np.pi*(1+pulse_error)*np.minimum(np.arange(end-start)+1, pulse)/pulse
            level += np.pi*(1+pulse_error)
        else:
            phase_trace[start:end] = level
        previous = bit
    t = np.arange(count)/rate
    z = amplitude*np.exp(1j*(phase_trace+2*np.pi*cfo_hz*t+phase))
    rng = np.random.default_rng(seed)
    z += noise_std*(rng.standard_normal(count)+1j*rng.standard_normal(count))
    z = z[offset_samples:offset_samples+samples]
    return np.clip(np.rint(np.column_stack((z.real,z.imag))), -128,127).astype(np.int8)


def estimate_carrier(iq, rate=16e6):
    """Blind plateau-frequency mode, independent of transmitted payload."""
    z = _complex(iq)
    lag = max(1, int(round(rate*.5e-6)))
    p = z[lag:]*np.conj(z[:-lag])
    f = np.angle(p)*rate/(2*np.pi*lag)
    weight = np.abs(p)
    edges = np.linspace(-rate/(2*lag), rate/(2*lag), 401)
    hist, edges = np.histogram(f, bins=edges, weights=weight)
    peak = int(np.argmax(hist))
    center = (edges[peak]+edges[peak+1])/2
    selected = abs(f-center) < max(10000., rate/(2*lag)/100)
    if not np.any(selected):
        return float(center)
    return float(np.angle(np.sum(p[selected]))*rate/(2*np.pi*lag))


def receive(iq, *, rate=16e6, symbol_us=8., known_payload=None, expected_payload=None,
            min_sync=.84, cfo_search_hz=15000., timing_step=4):
    """Acquire frames from samples and return JSON-safe evidence and soft IQ.

    No frame timestamp, transmitted payload or ideal constellation is supplied
    to acquisition. A configured symbol rate is required (not blind rate search).
    Missing frames between sparse captures are explicitly unobserved, not BER0.
    crc_ok checks received CRC and is separate from optional known-pattern BER.
    """
    if expected_payload is not None:
        if known_payload is not None and known_payload != expected_payload:
            raise ValueError('conflicting optional BER payload references')
        known_payload = expected_payload
    z = _complex(iq)
    if rate <= 0 or symbol_us <= 0 or len(z) < 512 or not np.isfinite(z).all():
        raise ValueError('need finite samples and positive rate/symbol period')
    if known_payload is not None:
        frame_bits(known_payload)  # Validate without passing it into acquisition.
    sps = int(round(rate*symbol_us/1e6))
    window = max(2, int(round(sps*.16)))
    if len(z) < FRAME_SYMBOLS*sps or timing_step < 1:
        raise ValueError('capture must contain at least64 symbols')
    sync = 1.-2.*int_bits(MARKER,16)
    carrier = estimate_carrier(z,rate)
    candidates = []
    correlation = np.zeros(len(z))
    time = np.arange(len(z))/rate
    # Residual search is deliberately based on samples/sync only.
    for residual in np.linspace(-cfo_search_hz,cfo_search_hz,31):
        freq = carrier+residual
        mixed = z*np.exp(-2j*np.pi*freq*time)
        integral = np.r_[0j,np.cumsum(mixed)]
        averages = (integral[window:]-integral[:-window])/window
        for offset in range(0,sps,int(timing_step)):
            y = averages[offset::sps]
            if len(y) < 64:
                continue
            dot = np.correlate(y,sync,'valid')
            energy = np.convolve(abs(y)**2,np.ones(16),'valid')
            score = abs(dot)/np.sqrt(np.maximum(16*energy,1e-20))
            locations = offset+np.arange(len(score))*sps
            correlation[locations] = np.maximum(correlation[locations],score)
            # Only complete frames are considered, not truncated suffixes.
            for start in np.flatnonzero(score[:len(y)-63] >= min_sync):
                candidates.append((float(score[start]),offset+int(start)*sps,float(freq)))
    candidates.sort(reverse=True)
    frames, attempts = [], []
    occupied = []
    for score,start,freq in candidates:
        if any(abs(start-other)<sps*.75 for other in occupied):
            continue
        occupied.append(start)
        ix = start+np.arange(64)*sps
        # Recompute quiet-window values at candidate timing, then estimate the
        # small carrier slope from measured marker phase. Marker is training,
        # not a payload oracle. Real symbols remain noisy complex averages.
        sampled = np.array([np.mean(z[i:i+window]*np.exp(-2j*np.pi*freq*time[i:i+window])) for i in ix])
        phi = np.unwrap(np.angle(sampled[:16]*sync))
        slope, intercept = np.polyfit(np.arange(16),phi,1,w=np.maximum(abs(sampled[:16]),1e-9))
        corrected = sampled*np.exp(-1j*(intercept+slope*np.arange(64)))
        scale = max(float(np.median(abs(corrected))),1e-12)
        corrected /= scale
        hard_sync = (corrected[:16].real<0).astype(np.uint8)
        sync_errors = int(np.count_nonzero(hard_sync!=int_bits(MARKER,16)))
        llr = corrected[16:60].real
        decoded = decode(llr)
        payload = int(np.packbits(decoded[:8]).tobytes().hex(),16)
        got_crc = int(np.packbits(decoded[8:]).tobytes().hex(),16)
        crc_ok = got_crc==crc8(bytes([payload]))
        row = dict(start_sample=int(start),sync_score=score,sync_errors=sync_errors,
                   carrier_hz=float(freq+slope*rate/(2*np.pi*sps)),payload=payload,
                   crc_received=got_crc,crc_ok=bool(crc_ok),
                   constellation_i=corrected.real.tolist(),constellation_q=corrected.imag.tolist(),
                   coded_llr=llr.tolist(),decoded_bits=decoded.tolist(),
                   symbols=np.column_stack((corrected[16:60].real,corrected[16:60].imag)).tolist(),
                   coded_errors=None,coded_bits=None,payload_errors=None,payload_bits=None)
        if known_payload is not None:
            expected=frame_bits(known_payload)[16:60]
            row.update(coded_errors=int(np.count_nonzero((llr<0)!=expected)),coded_bits=44,
                       payload_errors=int(np.count_nonzero(decoded[:8]!=int_bits(known_payload,8))),payload_bits=8)
        attempts.append(row)
        if crc_ok and sync_errors<=1:
            frames.append(row)
        if len(attempts)>=32:
            break
    acquired = [x for x in attempts if x['sync_errors']<=1]
    coded_errors=sum(x['coded_errors'] or 0 for x in acquired)
    payload_errors=sum(x['payload_errors'] or 0 for x in acquired)
    stride=max(1,len(z)//2048)
    spec=abs(np.fft.fftshift(np.fft.fft(z*np.hanning(len(z)))))**2
    sx=np.fft.fftshift(np.fft.fftfreq(len(z),1/rate))
    specstride=max(1,len(z)//1024)
    const=np.array([pair for row in acquired for pair in row['symbols']]).reshape(-1,2)
    plots=dict(spectrum=dict(x=sx[::specstride].tolist(),y=(10*np.log10(np.maximum(spec[::specstride],1e-12))).tolist()),
               raw_iq=dict(i=z.real[::stride].tolist(),q=z.imag[::stride].tolist(),sample=np.arange(len(z))[::stride].tolist()),
               constellation=dict(i=const[:,0].tolist(),q=const[:,1].tolist()),
               correlation=dict(x=np.arange(len(z))[::timing_step].tolist(),y=correlation[::timing_step].tolist()))
    return dict(schema='esp32-phase-bpsk-v1',processing='host Python',sample_rate_hz=float(rate),
                samples=len(z),capture_seconds=float(len(z)/rate),symbol_us=float(symbol_us),
                carrier_initial_hz=carrier,valid_frames=len(frames),frames=frames,
                candidates=attempts,acquired_frames=len(acquired),sync_failure=not bool(acquired),
                acquisition_failures=int(not bool(acquired)),plots=plots,
                crc_failures=sum(not x['crc_ok'] for x in acquired),
                known_pattern=known_payload is not None,
                coded_errors=coded_errors if known_payload is not None else None,
                coded_bits=44*len(acquired) if known_payload is not None else None,
                payload_errors=payload_errors if known_payload is not None else None,
                payload_bits=8*len(acquired) if known_payload is not None else None,
                unobserved_gaps='Frames outside each captured sample window are unobserved; no BER or delivery ratio is inferred for gaps.')
