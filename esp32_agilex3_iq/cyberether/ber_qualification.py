"""BER qualification: explicit AWGN simulation and separate saved RF evidence.

No acquisition, carrier recovery, RF impairment or FPGA execution is simulated
by the symbol experiment. Hard and soft decoders see exactly the same samples.
"""
from __future__ import annotations
import math
import json
from pathlib import Path
import numpy as np
from modem_reference import conv_encode, viterbi_decode
from rf_bpsk import crc8, frame_bits, int_bits
from tx_job_readback import validate_tx_on


def error_metric(errors, trials, confidence=.95):
    """Counts plus exact one-sided zero-event binomial limit (not a BER floor).

    Applying a bit-binomial limit to decoded bits assumes independent errors;
    decoder errors are correlated. Use frame limits for independent frames.
    """
    errors, trials = int(errors), int(trials)
    if not 0 <= errors <= trials or not 0 < confidence < 1:
        raise ValueError('invalid error count, denominator or confidence')
    return dict(errors=errors, trials=trials, rate=errors/trials if trials else None,
                confidence=confidence,
                zero_error_upper=(-math.expm1(math.log1p(-confidence)/trials)
                                  if trials and errors == 0 else None))


def noise_sigma(ebn0_db, information_bits, coded_bits):
    """Real AWGN std for Es=1, Eb=Es/R, R=K/N including CRC and tail cost."""
    if not np.isfinite(ebn0_db) or not 0 < information_bits <= coded_bits:
        raise ValueError('finite Eb/N0 and valid code dimensions required')
    rate = information_bits/coded_bits
    return math.sqrt(1/(2*rate*10**(float(ebn0_db)/10)))


def _crc_valid(decoded):
    data = np.packbits(np.asarray(decoded, dtype=np.uint8)).tobytes()
    return crc8(data[:-1]) == data[-1]


def run_sweep(ebn0_db=(-2., 0., 2., 4., 6.), *, frames=100, payload_bytes=16,
              seed=20261021, confidence=.95, progress=None):
    """Terminated K7(171,133) BPSK, perfect synchronization, random bytes+CRC8.

    Eb/N0 refers to encoder information bits (payload+CRC). Preamble and guard
    overhead are excluded; six tail bits ARE included in the effective rate.
    Uncoded reference uses separate BPSK symbols at the same information Eb/N0.
    """
    values = [float(x) for x in ebn0_db]
    if not values or not all(np.isfinite(values)) or not 1 <= frames <= 100000 or not 1 <= payload_bytes <= 4096:
        raise ValueError('need finite sweep, 1..100000 frames and 1..4096 payload bytes')
    if not isinstance(frames, int) or not isinstance(payload_bytes, int):
        raise ValueError('frame and byte counts must be integers')
    payload_bits, info_bits = payload_bytes*8, (payload_bytes+1)*8
    coded_bits = 2*(info_bits+6)
    points = []
    # Independent child RNG streams make each point reproducible and paired
    # hard/soft comparisons valid without depending on point execution order.
    streams = np.random.SeedSequence(seed).spawn(len(values))
    for point_index, (db, stream) in enumerate(zip(values, streams)):
        if progress:
            progress(point_index, len(values), db)
        rng = np.random.default_rng(stream)
        sigma = noise_sigma(db, info_bits, coded_bits)
        counts = dict(coded=0, uncoded=0, hard=0, soft=0)
        bad_frames = dict(hard=0, soft=0)
        crc_fail = dict(hard=0, soft=0)
        undetected = dict(hard=0, soft=0)
        for _ in range(frames):
            payload = rng.integers(0, 256, payload_bytes, dtype=np.uint8).tobytes()
            info = np.unpackbits(np.frombuffer(payload+bytes([crc8(payload)]), dtype=np.uint8))
            coded = conv_encode(info, terminate=True)
            received = 1.-2.*coded+sigma*rng.standard_normal(coded_bits)
            hard_bits = (received < 0).astype(np.uint8)
            counts['coded'] += int(np.count_nonzero(hard_bits != coded))
            uncoded_rx = 1.-2.*info[:payload_bits]+math.sqrt(1/(2*10**(db/10)))*rng.standard_normal(payload_bits)
            counts['uncoded'] += int(np.count_nonzero((uncoded_rx < 0) != info[:payload_bits]))
            for name, decoded in [('hard', viterbi_decode(hard_bits, soft=False)),
                                  ('soft', viterbi_decode(received, soft=True))]:
                errors = int(np.count_nonzero(decoded[:payload_bits] != info[:payload_bits]))
                counts[name] += errors
                crc_ok = _crc_valid(decoded)
                # A payload can be correct while its decoded CRC byte is not.
                # Frame reliability includes both outcomes, unlike payload BER.
                bad_frames[name] += bool(errors) or not crc_ok
                crc_fail[name] += not crc_ok
                undetected[name] += bool(errors) and crc_ok
        point = dict(ebn0_db=db, noise_sigma_real=sigma,
                     coded_channel=error_metric(counts['coded'], frames*coded_bits, confidence),
                     uncoded=error_metric(counts['uncoded'], frames*payload_bits, confidence),
                     uncoded_theory_ber=.5*math.erfc(math.sqrt(10**(db/10))))
        for name in ('hard', 'soft'):
            point[name] = dict(payload=error_metric(counts[name], frames*payload_bits, confidence),
                               frames=error_metric(bad_frames[name], frames, confidence),
                               crc_failures=crc_fail[name], crc_checks=frames,
                               undetected_payload_error_frames=undetected[name])
        points.append(point)
    if progress:
        progress(len(values), len(values), None)
    return dict(schema='rf-ber-sweep-v1', origin='synthetic symbol AWGN simulation',
                processing='host Python; no FPGA or RF execution', seed=seed,
                frames_per_point=frames, payload_bytes=payload_bytes,
                information_bits=info_bits, coded_bits=coded_bits,
                effective_code_rate=info_bits/coded_bits,
                normalization='Eb per encoder information bit including CRC8; finite tail cost included; preamble/guard excluded',
                synchronization='perfect symbol timing/carrier; acquisition NOT tested',
                confidence_note='Zero-event bit limits assume independent bits; post-FEC errors correlate. Frame errors include wrong payload OR failed CRC, including CRC-only corruption. Frame limits use independently generated frames.',
                points=points)


def transmitter_settings(proof,config):
    """Separate firmware/actual acknowledgements; requested defaults prove nothing."""
    identity=proof.get('identity') or 'unknown'
    firmware='unknown'
    if isinstance(identity,str) and identity.startswith('TX_PROBE,'):
        firmware=next((part for part in identity.split(',') if part.startswith('v=') and part[2:].isdigit()),'unknown')
        if firmware!='unknown':firmware='v'+firmware[2:]
    verified=False
    acknowledgement=config.get('tx_on_readback')
    if isinstance(acknowledgement,dict):
        try:
            actual=validate_tx_on(acknowledgement['line'],config,channel=config['channel'],
                backoff_qdb=config['backoff'],limit_ms=500)
            verified=all(acknowledgement.get(key)==actual[key] for key in ('id','channel','backoff_qdb','limit_ms'))
        except (KeyError,TypeError,ValueError):
            pass
    return dict(tx_identity=identity,tx_firmware=firmware,tx_ack_verified=bool(verified))


def aggregate_rf(proof_paths, *, reference_payload=None, confidence=.95, modulation='BPSK'):
    """Aggregate physical RF proofs of ONE modulation, deduplicated by raw CI8 SHA256.

    Recompute BER using saved candidate metrics and transmitted configuration,
    or an explicit reference byte. CRC-failed synchronized candidates count.
    CRC validity is always read independently of the known BER reference.
    This audits saved reports, not raw IQ; no new RF processing is performed.
    """
    if modulation not in ('BPSK','QPSK'):
        raise ValueError('modulation must be BPSK or QPSK')
    physical_kind='physical_rf_'+modulation.lower()
    max_sync_errors=2 if modulation=='QPSK' else 1
    if reference_payload is not None:
        frame_bits(reference_payload)
    seen, groups, skipped, duplicates, excluded = set(), {}, [], 0, 0
    for item in proof_paths:
        path = Path(item)
        proof = json.loads(path.read_text())
        if proof.get('kind') != physical_kind:
            excluded += 1
            continue
        for index, row in enumerate(proof.get('rows', [])):
            sha = row.get('transport', {}).get('payload_sha256')
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha.lower()):
                skipped.append(dict(proof=str(path), row=index, reason='missing/invalid raw SHA256'))
                continue
            key = sha.lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            report = row.get('report', {})
            source = row.get('transport', {}).get('source', 'unknown')
            config = row.get('config', {})
            settings = dict(transmitter_settings(proof,config),modulation=modulation, payload=config.get('payload'), source=source, channel=config.get('channel'), backoff=config.get('backoff',proof.get('requested',{}).get('backoff_qdb')),
                rx_gain=proof.get('gain_readback'), symbol_us=config.get('period_us'), pulse_cycles=config.get('pulse_cycles'),
                quarter_cycles=config.get('quarter_cycles'),half_cycles=config.get('half_cycles'),three_cycles=config.get('three_cycles'))
            setting_key = json.dumps(settings, sort_keys=True)
            group = groups.setdefault(setting_key, dict(settings=settings, source=source, captures=0, acquisition_failures=0,
                acquired_frames=0, crc_pass=0, crc_failures=0, coded_errors=0, coded_bits=0,
                payload_errors=0, payload_bits=0, unreferenced_frames=0, hard_payload_errors=0,
                hard_crc_failures=0, soft_frame_errors=0, hard_frame_errors=0))
            group['captures'] += 1
            acquired = [r for r in report.get('candidates', []) if r.get('sync_errors', 999) <= max_sync_errors]
            group['acquisition_failures'] += not bool(acquired)
            group['acquired_frames'] += len(acquired)
            ref = reference_payload if reference_payload is not None else row.get('config', {}).get('payload')
            for candidate in acquired:
                group['crc_pass'] += bool(candidate['crc_ok'])
                group['crc_failures'] += not candidate['crc_ok']
                if ref is None:
                    group['unreferenced_frames'] += 1
                    continue
                expected = frame_bits(ref)[16:60]
                llr = np.asarray(candidate.get('coded_llr', []), dtype=float)
                decoded = np.asarray(candidate.get('decoded_bits', []))
                if llr.shape != (44,) or decoded.shape != (16,) or not np.isfinite(llr).all() or np.any((decoded != 0) & (decoded != 1)):
                    raise ValueError(f'invalid saved candidate metrics: {path} row {index}')
                group['coded_errors'] += int(np.count_nonzero((llr < 0) != expected))
                group['coded_bits'] += 44
                group['payload_errors'] += int(np.count_nonzero(decoded[:8] != int_bits(ref, 8)))
                group['payload_bits'] += 8
                hard_decoded = viterbi_decode((llr < 0).astype(np.uint8), soft=False)
                hard_errors = int(np.count_nonzero(hard_decoded[:8] != int_bits(ref, 8)))
                group['hard_payload_errors'] += hard_errors
                group['hard_crc_failures'] += not _crc_valid(hard_decoded)
                group['hard_frame_errors'] += bool(hard_errors) or not _crc_valid(hard_decoded)
                group['soft_frame_errors'] += bool(np.count_nonzero(decoded[:8] != int_bits(ref, 8))) or not candidate['crc_ok']
    totals = {k: sum(g[k] for g in groups.values()) for k in ('captures', 'acquisition_failures', 'acquired_frames',
        'crc_pass', 'crc_failures', 'coded_errors', 'coded_bits', 'payload_errors', 'payload_bits', 'unreferenced_frames',
        'hard_payload_errors', 'hard_crc_failures', 'hard_frame_errors', 'soft_frame_errors')}
    def metrics(row):
        row['coded'] = error_metric(row['coded_errors'], row['coded_bits'], confidence)
        row['payload'] = error_metric(row['payload_errors'], row['payload_bits'], confidence)
        row['acquisition'] = error_metric(row['acquisition_failures'], row['captures'], confidence)
        referenced_frames = row['payload_bits']//8
        row['hard'] = dict(payload=error_metric(row['hard_payload_errors'], row['payload_bits'], confidence),
            frames=error_metric(row['hard_frame_errors'], referenced_frames, confidence),
            crc_failures=row['hard_crc_failures'], crc_checks=referenced_frames)
        row['soft'] = dict(payload=row['payload'],
            frames=error_metric(row['soft_frame_errors'], referenced_frames, confidence),
            crc_failures=row['crc_failures'], crc_checks=row['acquired_frames'])
    for row in [totals, *groups.values()]:
        metrics(row)
    return dict(schema='rf-ber-evidence-v1', origin='saved physical RF capture reports', modulation=modulation,
                reference='configured transmitted payload' if reference_payload is None else f'explicit payload byte {reference_payload}',
                totals=totals, receivers=list(groups.values()), setting_groups=list(groups.values()), duplicate_captures_excluded=duplicates,
                non_rf_proofs_excluded=excluded, skipped=skipped,
                note='Setting groups keep transmitter identity/firmware/actual TX acknowledgement/modulation/payload/receiver/channel/gain/symbol/pulse/backoff distinct; null means unrecorded, never inferred. Hard/soft use the same saved LLR. Frame errors include wrong payload OR failed CRC. Totals are evidence audit, not a controlled cross-setting comparison. Deduplicated by raw CI8 SHA256. Saved metrics audited; raw IQ not re-decoded. Capture gaps are unobserved. Bit confidence limits assume independent errors; captures/frames may correlate.')
