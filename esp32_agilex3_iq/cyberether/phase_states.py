"""Measured four-state phase gate; no bits, payload or ideal-point replacement."""
import numpy as np


def qualify_states(iq, *, carrier_hz, rate=16e6, events=()):
    a = np.asarray(iq)
    if a.ndim != 2 or a.shape[1] != 2 or len(a) < 512:
        raise ValueError('need at least 512 signed IQ pairs')
    if not np.isfinite(a).all() or not np.isfinite(carrier_hz) or not np.isfinite(rate) or rate <= 0:
        raise ValueError('finite IQ/carrier and positive sample rate required')
    z = a[:, 0].astype(float)+1j*a[:, 1].astype(float)
    corrected = z*np.exp(-2j*np.pi*carrier_hz*np.arange(len(z))/rate)
    amplitude = abs(corrected)
    mask = amplitude > max(.3*np.median(amplitude), 1e-12)
    margin = int(round(rate*2e-6))
    for event in events:
        start, end = int(event['start_sample']), int(event['end_sample'])
        if not 0 <= start <= end <= len(z):
            raise ValueError('event lies outside capture')
        mask[max(0, start-margin):min(len(z), end+margin)] = False
    unit = corrected[mask]/np.maximum(amplitude[mask], 1e-12)
    if len(unit) < 128:
        raise ValueError('insufficient above-threshold plateau samples')
    moments = [float(abs(np.mean(unit**order))) for order in (1, 2, 4)]
    # Estimate one common rotation from measured samples. Retain every received
    # point; assigning a cluster for statistics never moves it to an ideal point.
    rotation = float(np.angle(np.mean(unit**4))/4)
    index = np.mod(np.rint((np.angle(unit)-rotation)/(np.pi/2)).astype(int), 4)
    clusters = []
    for state in range(4):
        selected = unit[index == state]
        mean = np.mean(selected) if len(selected) else 0j
        clusters.append(dict(state=state, samples=len(selected), fraction=len(selected)/len(unit),
                             phase_deg=float(np.angle(mean)*180/np.pi), coherence=float(abs(mean))))
    rails = float(np.mean((a <= -128).any(axis=1) | (a >= 127).any(axis=1)))
    near_fullscale = float(np.mean((abs(a.astype(float)) >= 120).any(axis=1)))
    event_changes = [float(e['phase_change_deg']) for e in events]
    quarter_events = sum(abs(abs(v)-90) <= 15 for v in event_changes)
    passed = bool(moments[0] < .3 and moments[1] < .3 and moments[2] > .9
                  and min(c['fraction'] for c in clusters) > .12
                  and min(c['coherence'] for c in clusters) > .9
                  and quarter_events >= 4 and rails < .01 and near_fullscale < .5)
    stride = max(1, len(corrected)//2500)
    return dict(four_states_qualified=passed, circular_moments=dict(first=moments[0], second=moments[1], fourth=moments[2]),
                clusters=clusters, coherent_quarter_events=quarter_events, plateau_samples=len(unit),
                rail_fraction=rails, near_fullscale_fraction=near_fullscale,
                rotation_deg=rotation*180/np.pi,
                plots=dict(i=corrected[::stride].real.tolist(), q=corrected[::stride].imag.tolist()),
                scope='Measured phase plateaus after independently estimated carrier removal; no framed QPSK decoding or BER')
