#!/usr/bin/env python3
"""Offline phase-pulse investigation for CI8 RX captures; no device access.

Measured clusters are not decoded symbols. A squared-phase carrier estimate
removes the 180-degree ambiguity without fitting samples to BPSK decisions.
The analysis cannot by itself identify which transmitter caused a phase event.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import hashlib

import numpy as np


def load_ci8(path):
    data = Path(path).read_bytes()
    if len(data) % 2:
        raise ValueError('CI8 file must contain interleaved signed I/Q byte pairs')
    return np.frombuffer(data, dtype=np.int8).reshape(-1, 2)


def _complex(iq):
    a = np.asarray(iq)
    if a.ndim == 2 and a.shape[1] == 2:
        return a[:, 0].astype(float)+1j*a[:, 1].astype(float)
    if a.ndim == 1 and np.iscomplexobj(a):
        return a.astype(complex)
    raise ValueError('expected CI8 [N,2] pairs or a complex vector')


def _mad(a):
    return float(1.4826*np.median(abs(a-np.median(a))))


def estimate_carrier(z, rate, expected_offset_hz=5e6, search_width_hz=250e3):
    """FFT coarse acquisition, then median squared-phase lag frequencies.

    The robust derivative favors the majority constant-frequency plateaus. It
    does not fit a line through unwrapped square phase, which would incorrectly
    count continuous π phase ramps as carrier drift. Frequency is ambiguous
    modulo Fs/2 before the coarse spectral prior; report the chosen branch.
    """
    n = len(z)
    nfft = max(4096, 1 << (n-1).bit_length())
    window = np.hanning(n)
    spectrum = abs(np.fft.fft(z*window, n=nfft))**2
    frequencies = np.fft.fftfreq(nfft, 1/rate)
    selection = np.ones(nfft, bool) if expected_offset_hz is None else abs(frequencies-expected_offset_hz) <= search_width_hz
    if not np.any(selection):
        raise ValueError('frequency search window lies outside Nyquist range')
    candidates = np.flatnonzero(selection)
    peak = candidates[int(np.argmax(spectrum[candidates]))]
    coarse = float(frequencies[peak])
    mixed = z*np.exp(-2j*np.pi*coarse*np.arange(n)/rate)
    amplitude = abs(mixed)
    threshold = max(float(np.median(amplitude))*.3, 1e-12)
    valid = amplitude > threshold
    unit = mixed/np.maximum(amplitude, 1e-12)
    squared = unit*unit
    estimates = []
    for lag in (16, 32, 64):
        good = valid[lag:] & valid[:-lag]
        differences = np.angle(squared[lag:]*np.conj(squared[:-lag]))[good]
        if len(differences) < 128:
            continue
        # FFT acquisition puts residual near zero; lag64 resolves +/-62.5kHz
        # at16MS/s, sufficient for the narrow phase-pulse experiment.
        # A simple median is biased when positive phase pulses occupy20%.
        # Isolate the dense plateau component before estimating its center.
        center = float(np.median(differences))
        width = max(3*_mad(differences), 1e-4)
        chosen = abs(differences-center) < width
        for _ in range(3):
            clean = differences[chosen]
            center = float(np.mean(clean))
            width = max(3*_mad(clean), 1e-4)
            chosen = abs(differences-center) < width
        residual = float(center*rate/(4*np.pi*lag))
        estimates.append(dict(lag_samples=lag, carrier_hz=coarse+residual,
                              robust_spread_hz=_mad(differences)*rate/(4*np.pi*lag)))
    if not estimates:
        raise ValueError('not enough above-threshold samples for carrier estimation')
    carrier = float(np.median([row['carrier_hz'] for row in estimates]))
    return dict(carrier_hz=carrier, coarse_peak_hz=coarse,
                lag_estimates=estimates,
                lag_disagreement_hz=float(np.ptp([row['carrier_hz'] for row in estimates])),
                peak_over_band_median_db=float(10*np.log10((spectrum[peak]+1e-20)/(np.median(spectrum[selection])+1e-20))),
                method='coarse FFT branch + robust squared-phase lag median',
                ambiguity='Squared phase alone is modulo Fs/2; coarse spectrum selects the branch.')


def _groups(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def analyze_iq(iq, rate=16e6, expected_offset_hz=5e6, search_width_hz=250e3,
               plateau_window_us=8., expected_pulse_us=None, *,
               _carrier_override=None, _refine=True):
    """Return JSON-safe measured phase evidence and data for diagnostic plots.

    A constant global phase is left untouched. No bit labels, ideal-state
    replacement, known symbol decisions, timing oracle or phase snap is used.
    Frequency excursions and phase changes are detected from received samples.
    """
    z = _complex(iq)
    if len(z) < 512 or not np.isfinite(z).all() or not np.isfinite(rate) or rate <= 0:
        raise ValueError('need at least512 finite IQ samples and a positive sample rate')
    if expected_offset_hz is not None and not np.isfinite(expected_offset_hz):
        raise ValueError('frequency prior must be finite')
    if not np.isfinite(search_width_hz) or search_width_hz <= 0:
        raise ValueError('frequency search width must be positive and finite')
    if expected_pulse_us is not None and (not np.isfinite(expected_pulse_us) or not 0 <= expected_pulse_us <= 1000):
        raise ValueError('expected pulse metadata must be0..1000us')
    if len(z) > 1_000_000:
        raise ValueError('offline burst limit is one million samples')
    if not np.isfinite(plateau_window_us) or not 1 <= plateau_window_us <= 100:
        raise ValueError('plateau window must be1..100us')
    carrier = _carrier_override or estimate_carrier(z, rate, expected_offset_hz, search_width_hz)
    n = len(z)
    t = np.arange(n)/rate
    corrected = z*np.exp(-2j*np.pi*carrier['carrier_hz']*t)
    amplitude = abs(corrected)
    median_amp = float(np.median(amplitude))
    valid = amplitude > max(median_amp*.3, 1e-12)
    unit = corrected/np.maximum(amplitude, 1e-12)
    phase = np.unwrap(np.angle(corrected))
    lag = max(4, int(round(rate*4e-6)))
    lag = min(lag, n//8)
    # Four-microsecond phase difference, then short averaging. Phase pulses are
    # measured as finite ramps; an instantaneous reset remains visible too.
    difference = np.angle(corrected[lag:]*np.conj(corrected[:-lag]))*rate/(2*np.pi*lag)
    kernel = max(3, int(round(rate*.5e-6)))
    frequency = np.convolve(np.pad(difference, (kernel//2, kernel-1-kernel//2), mode='edge'), np.ones(kernel)/kernel, mode='valid')
    freq_valid = valid[lag:] & valid[:-lag]
    spread = _mad(frequency[freq_valid]) if freq_valid.any() else float('inf')
    threshold = max(8000., 8*spread)
    mask = (abs(frequency) > threshold) & freq_valid
    # The4us derivative window and RX ringing can split one physical phase
    # transition into several lobes. Require6us of quiet to separate events;
    # this is detector resolution, not the requested TX pulse duration.
    hole_limit = max(1, int(rate*6e-6))
    for begin, end in _groups(~mask):
        if begin > 0 and end < len(mask) and end-begin <= hole_limit:
            mask[begin:end] = True
    events = []
    plateau_excluded = np.zeros(n, bool)
    margin = max(4, int(rate*2e-6))
    width = max(8, int(rate*plateau_window_us*1e-6))
    for begin, end in _groups(mask):
        if (end-begin)/rate < 1e-6:
            continue
        center_begin, center_end = begin+lag//2, end+lag//2
        if center_begin-margin-width < 0 or center_end+margin+width > n:
            continue
        before = unit[center_begin-margin-width:center_begin-margin]
        after = unit[center_end+margin:center_end+margin+width]
        before_good = valid[center_begin-margin-width:center_begin-margin]
        after_good = valid[center_end+margin:center_end+margin+width]
        if before_good.mean() < .8 or after_good.mean() < .8:
            continue
        c_before, c_after = np.mean(before[before_good]), np.mean(after[after_good])
        change = float(np.angle(c_after*np.conj(c_before))*180/np.pi)
        # For a smooth ramp this preserves extra turns; when SNR is poor, unwrap
        # may fail, so coherence/SNR gates accompany this diagnostic quantity.
        p_before = float(np.median(phase[center_begin-margin-width:center_begin-margin]))
        p_after = float(np.median(phase[center_end+margin:center_end+margin+width]))
        events.append(dict(start_sample=int(center_begin), end_sample=int(center_end),
                           start_us=float(center_begin/rate*1e6), end_us=float(center_end/rate*1e6),
                           duration_us=float((end-begin)/rate*1e6),
                           phase_change_deg=change,
                           unwrapped_phase_change_deg=float((p_after-p_before)*180/np.pi),
                           before_coherence=float(abs(c_before)), after_coherence=float(abs(c_after)),
                           peak_excursion_hz=float(frequency[begin:end][np.argmax(abs(frequency[begin:end]))]),
                           near_pi=bool(abs(abs(change)-180) <= 30 and min(abs(c_before), abs(c_after)) > .85)))
        plateau_excluded[max(0, center_begin-margin):min(n, center_end+margin)] = True
    plateau = valid & ~plateau_excluded
    values = unit[plateau]
    if len(values) < 128:
        raise ValueError('not enough plateau samples for phase statistics')
    if _refine:
        estimates, weights = [], []
        for begin, end in _groups(plateau):
            if end-begin < max(128, int(rate*8e-6)):
                continue
            # Separate intercept per measured plateau; no alignment to ideal
            # 0/pi states and no fit across the deliberate phase transitions.
            ph = np.unwrap(np.angle(unit[begin:end]**2))
            samples = np.arange(end-begin, dtype=float)
            samples -= samples.mean()
            slope = float(samples @ (ph-ph.mean()) / (samples@samples))
            estimates.append(carrier['carrier_hz']+slope*rate/(4*np.pi))
            weights.append(float((end-begin)**3))
        if estimates:
            estimates = np.asarray(estimates)
            keep = abs(estimates-np.median(estimates)) <= max(50., 4*_mad(estimates))
            refined = dict(carrier)
            refined['carrier_hz'] = float(np.average(estimates[keep], weights=np.asarray(weights)[keep]))
            refined['plateau_fit_carriers_hz'] = estimates.tolist()
            refined['refinement'] = 'Squared-phase slope fits within detected plateau intervals; independent intercepts'
            return analyze_iq(iq, rate, expected_offset_hz, search_width_hz,
                              plateau_window_us, expected_pulse_us,
                              _carrier_override=refined, _refine=False)
    first, second = np.mean(values), np.mean(values*values)
    axis = np.angle(second)/2
    partition = np.real(values*np.exp(-1j*axis)) >= 0
    clusters = []
    for choice in (False, True):
        selected = values[partition == choice]
        c = np.mean(selected) if len(selected) else 0j
        clusters.append(dict(samples=int(len(selected)), fraction=float(len(selected)/len(values)),
                             mean_phase_deg=float(np.angle(c)*180/np.pi), coherence=float(abs(c))))
    separation = float(abs(np.angle(np.exp(1j*(clusters[1]['mean_phase_deg']-clusters[0]['mean_phase_deg'])*np.pi/180)))*180/np.pi)
    rails = float(np.mean((z.real <= -128) | (z.real >= 127) | (z.imag <= -128) | (z.imag >= 127))*100)
    near_fullscale = float(np.mean((abs(z.real) >= 120) | (abs(z.imag) >= 120))*100)
    component_values, component_counts = np.unique(np.r_[z.real, z.imag], return_counts=True)
    dominant_codes_fraction = float(np.sort(component_counts)[-4:].sum()/(2*n))
    quality_notes = []
    if near_fullscale > 50:
        quality_notes.append('Most samples are near CI8 full scale; exact rail count does not exclude upstream limiting. Reacquire with more headroom before trusting phase.')
    if dominant_codes_fraction > .8:
        quality_notes.append('Four or fewer component codes dominate; phase estimates may be quantization/limiting dominated.')
    pi_events = sum(row['near_pi'] for row in events)
    qualified = bool(abs(first) < .7 and abs(second) > .8 and separation > 150
                     and min(c['fraction'] for c in clusters) > .15
                     and min(c['coherence'] for c in clusters) > .85
                     and pi_events >= 2 and rails < 1 and near_fullscale < 50
                     and carrier['peak_over_band_median_db'] > 12)
    hist, boundaries = np.histogram(np.angle(values), bins=72, range=(-np.pi, np.pi))
    stride = max(1, n//3000)
    trace_stride = max(1, n//4096)
    def xy(a):
        return np.column_stack((a.real, a.imag)).tolist()
    report = dict(source='Offline host analysis of supplied IQ; not FPGA demodulation',
                  sample_count=n, sample_rate_hz=float(rate), capture_duration_us=float(n/rate*1e6),
                  carrier=carrier, expected_pulse_us=expected_pulse_us,
                  metrics=dict(two_phase_clusters_observed=qualified,
                      first_circular_moment=float(abs(first)), second_circular_moment=float(abs(second)),
                      measured_cluster_separation_deg=separation, clusters=clusters,
                      detected_events=len(events), near_pi_events=int(pi_events),
                      plateau_samples=int(plateau.sum()), clipped_percent=rails,
                      near_fullscale_percent=near_fullscale,
                      four_dominant_component_codes_fraction=dominant_codes_fraction,
                      quality_notes=quality_notes,
                      median_magnitude=median_amp, frequency_noise_mad_hz=spread,
                      event_threshold_hz=threshold, event_quiet_resolution_us=6.,
                      qualification='Measured antipodal plateaus plus >=2 coherent near-pi events; no known bits or phase snapping'),
                  events=events, plots=dict(raw_xy=xy(z[::stride]), corrected_xy=xy(corrected[::stride]),
                      time_us=(t[::trace_stride]*1e6).tolist(), phase_deg=(phase[::trace_stride]*180/np.pi).tolist(),
                      frequency_time_us=((np.arange(len(frequency))+lag/2)/rate*1e6)[::trace_stride].tolist(),
                      residual_frequency_hz=frequency[::trace_stride].tolist(),
                      histogram_centers_deg=((boundaries[:-1]+boundaries[1:])/2*180/np.pi).tolist(),
                      histogram_counts=hist.tolist()),
                  limits=['Two clusters do not prove transmitted bits or BER.',
                          'CFO estimator assumes a majority of constant-frequency plateaus.',
                          'Known interference can also create phase structure.',
                          'No continuous RX timing/carrier loop or channel equalizer is implemented.'])
    return report


def plot_report(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p, metrics = report['plots'], report['metrics']
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, key, title in ((axes[0,0], 'raw_xy', 'Actual supplied IQ'),
                            (axes[0,1], 'corrected_xy', 'Carrier corrected · no phase snapping')):
        a = np.asarray(p[key])
        ax.scatter(a[:,0], a[:,1], s=3, alpha=.35)
        ax.set(title=title, xlabel='I (sample units)', ylabel='Q (sample units)', aspect='equal')
        ax.grid(alpha=.2)
    axes[0,2].bar(p['histogram_centers_deg'], p['histogram_counts'], width=4.8)
    axes[0,2].set(title='Measured plateau phase density', xlabel='Phase (degrees)', ylabel='Samples')
    axes[1,0].plot(p['time_us'], p['phase_deg'], lw=.8)
    axes[1,0].set(title='Carrier-corrected unwrapped phase', xlabel='Capture time (µs)', ylabel='Phase (degrees)')
    axes[1,1].plot(p['frequency_time_us'], np.asarray(p['residual_frequency_hz'])/1000, lw=.8)
    axes[1,1].axhline(metrics['event_threshold_hz']/1000, c='r', ls='--', alpha=.5)
    axes[1,1].axhline(-metrics['event_threshold_hz']/1000, c='r', ls='--', alpha=.5)
    axes[1,1].set(title='Measured frequency excursions', xlabel='Capture time (µs)', ylabel='Residual offset (kHz)')
    changes = [event['unwrapped_phase_change_deg'] for event in report['events']]
    axes[1,2].scatter(range(len(changes)), changes)
    axes[1,2].axhline(180, c='gray', ls='--'); axes[1,2].axhline(-180, c='gray', ls='--')
    axes[1,2].set(title='Measured before/after changes', xlabel='Detected event', ylabel='Unwrapped phase change (degrees)', ylim=(min([-200., *changes])-5, max([200., *changes])+5))
    title = 'Two antipodal phase clusters observed' if metrics['two_phase_clusters_observed'] else 'Two-state phase evidence NOT established'
    fig.suptitle(title+' · offline host analysis, no bit/BER claim')
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def synthetic_capture(kind='phase-pulses', seed=42, rate=16e6, n=8192,
                      carrier_hz=5.123e6, pulse_us=12.8, spacing_us=80., noise_sigma=1., symbol_bits=None, symbol_us=64.):
    """Explicit synthetic controls, returned CI8; never substituted for RF data."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)/rate
    phase = np.zeros(n)
    amplitude = np.full(n, 40.)
    if symbol_bits is None:
        starts = np.arange(50e-6, n/rate, spacing_us*1e-6)
    else:
        bits = np.asarray(symbol_bits)
        if len(bits) < 2 or not np.isin(bits, [0, 1]).all():
            raise ValueError('synthetic symbol_bits must be a binary pattern')
        starts = [index*symbol_us*1e-6 for index in range(1, int(n/rate/(symbol_us*1e-6))+1) if bits[index % len(bits)] != bits[(index-1) % len(bits)]]
    for start in starts if pulse_us > 0 else []:
        ramp = np.clip((t-start)/(pulse_us*1e-6), 0, 1)
        if kind in ('phase-pulses', 'ringing-pulses'):
            phase += (2*np.pi*39062.5*pulse_us*1e-6)*ramp
            if kind == 'ringing-pulses':
                # Explicit synthetic transient, zero at both endpoints. It
                # challenges event fragmentation, not a fitted RF channel.
                phase += .35*np.sin(4*np.pi*ramp)*np.sin(np.pi*ramp)**2
        elif kind == 'reset-pulses':
            phase += np.where((t >= start) & (t < start+pulse_us*1e-6), np.pi*ramp, 0)
        elif kind == 'small-pulses':
            phase += .25*np.pi*ramp
    if kind == 'ook':
        amplitude = 40.*((np.floor(t/(spacing_us*1e-6)).astype(int) & 1) == 0)
    elif kind == 'qpsk':
        phase = (np.floor(t/(40e-6)).astype(int) % 4)*np.pi/2
    elif kind not in ('phase-pulses', 'ringing-pulses', 'reset-pulses', 'small-pulses', 'cw', 'noise'):
        raise ValueError('unknown synthetic control')
    z = amplitude*np.exp(1j*(2*np.pi*carrier_hz*t+.73+phase))
    if kind == 'noise':
        z *= 0
    z += noise_sigma*(rng.normal(size=n)+1j*rng.normal(size=n))
    return np.clip(np.rint(np.column_stack((z.real, z.imag))), -128, 127).astype(np.int8)


def self_test(output=None):
    results = {}
    for kind in ('phase-pulses', 'ringing-pulses', 'cw', 'ook', 'qpsk', 'reset-pulses', 'small-pulses', 'noise'):
        iq = synthetic_capture(kind)
        r = analyze_iq(iq)
        results[kind] = r['metrics']
        assert r['metrics']['two_phase_clusters_observed'] == (kind in ('phase-pulses', 'ringing-pulses')), (kind, r['metrics'])
        if kind == 'phase-pulses':
            assert abs(r['carrier']['carrier_hz']-5.123e6) < 300
            assert r['metrics']['near_pi_events'] >= 4
        if output:
            folder = Path(output)/('synthetic-'+kind)
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'capture.ci8').write_bytes(iq.tobytes())
            (folder/'analysis.json').write_text(json.dumps(r, indent=2)+'\n')
            plot_report(r, folder/'phase-analysis.png')
    print('Synthetic controls PASS: plain/ringing phase pulses qualify; CW/OOK/QPSK/reset/small/noise do not')
    return results


def review_captures(roots, output, rate=16e6, expected_offset_hz=0., search_width_hz=250e3):
    """Reanalyze existing case/capture.ci8 trees without modifying their proofs."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for root in map(Path, roots):
        for capture in sorted(root.glob('*/capture.ci8')):
            r = analyze_iq(load_ci8(capture), rate, expected_offset_hz, search_width_hz)
            digest = hashlib.sha256(capture.read_bytes()).hexdigest()
            r['capture'] = dict(file=str(capture), sha256=digest,
                                origin='Independent offline reanalysis; source/transport evidence remains in original proof.json')
            folder = output/root.name/capture.parent.name
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'analysis.json').write_text(json.dumps(r, indent=2, allow_nan=False)+'\n')
            plot_report(r, folder/'phase-analysis.png')
            changes = np.array([e['unwrapped_phase_change_deg'] for e in r['events']])
            rows.append(dict(batch=root.name, case=capture.parent.name, capture_sha256=digest,
                             cfo=r['carrier']['carrier_hz'], two=r['metrics']['two_phase_clusters_observed'],
                             events=r['metrics']['detected_events'], nearpi=r['metrics']['near_pi_events'],
                             m2=r['metrics']['second_circular_moment'],
                             median_phase=float(np.median(changes)) if len(changes) else None,
                             min_phase=float(np.min(changes)) if len(changes) else None,
                             max_phase=float(np.max(changes)) if len(changes) else None))
    if not rows:
        raise ValueError('no case/capture.ci8 files found in review roots')
    summary = dict(source='Offline reanalysis; no new hardware access or captures',
                   analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   detector_quiet_us=6., unique_capture_hashes=len(set(r['capture_sha256'] for r in rows)),
                   captures=rows)
    (output/'physical-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', nargs='?', type=Path)
    p.add_argument('--rate', type=float, default=16e6)
    p.add_argument('--expected-offset-hz', type=float, default=5e6)
    p.add_argument('--search-width-hz', type=float, default=250e3)
    p.add_argument('--pulse-us', type=float)
    p.add_argument('--output', type=Path)
    p.add_argument('--review-root', action='append', type=Path, default=[], help='offline case/capture.ci8 tree; repeat to compare batches')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args(argv)
    if args.self_test:
        self_test(args.output)
        return 0
    if args.review_root:
        if args.capture or not args.output:
            p.error('--review-root needs --output and no positional capture')
        summary = review_captures(args.review_root, args.output, args.rate, args.expected_offset_hz, args.search_width_hz)
        print(json.dumps(summary, indent=2))
        return 0
    if not args.capture or not args.output:
        p.error('capture and --output required, or use --self-test')
    iq = load_ci8(args.capture)
    result = analyze_iq(iq, args.rate, args.expected_offset_hz, args.search_width_hz,
                        expected_pulse_us=args.pulse_us)
    result['capture'] = dict(file=args.capture.name, sha256=hashlib.sha256(args.capture.read_bytes()).hexdigest(),
                             origin='Supplied file; transport/hardware provenance must be checked separately')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    plot_report(result, args.output/'phase-analysis.png')
    print(json.dumps(dict(carrier=result['carrier'], metrics=result['metrics'], events=result['events']), indent=2))
    print('Saved:', args.output/'phase-analysis.png')


if __name__ == '__main__':
    main()
