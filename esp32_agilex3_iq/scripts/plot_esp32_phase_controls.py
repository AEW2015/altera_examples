#!/usr/bin/env python3
"""Plot measured CW/half-width/full-width controls from a phase-check run.

Reanalyzes saved CI8; never opens hardware or substitutes generated samples.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from analyze_esp32_phase import analyze_iq, load_ci8


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proof = json.loads((args.run/'proof.json').read_text())
    if not proof['completed']:
        raise ValueError('Use a completed physical capture run')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(14, 8))
    axes = np.array([[fig.add_subplot(2, 3, col+1, projection='polar') for col in range(3)],
                     [fig.add_subplot(2, 3, col+4) for col in range(3)]])
    cases = [('zero_pulse_control', 'Carrier only'),
             ('half_width_control', 'Half-width pulse'),
             ('nominal_half_turn', 'Full-width pulse')]
    for col, (case, title) in enumerate(cases):
        row = next(r for r in proof['rows'] if r['case'] == case)
        cfg = row['config']
        raw = args.run/f"{case}-{row['index']}"/'capture.ci8'
        report = analyze_iq(load_ci8(raw), rate=row['transport']['rate'],
                            expected_offset_hz=0,
                            expected_pulse_us=cfg['pulse_cycles']/cfg['cpu']*1e6)
        p = report['plots']
        counts = np.asarray(p['histogram_counts'])
        axes[0, col].bar(np.deg2rad(p['histogram_centers_deg']), counts/counts.sum(),
                         width=np.deg2rad(4.8), color=('#64748b', '#f59e0b', '#0891b2')[col])
        axes[0, col].set(title=title+' · measured phase density')
        phase = np.asarray(p['phase_deg'])
        axes[1, col].plot(p['time_us'], phase-phase[0], lw=1)
        axes[1, col].set(xlabel='Within-burst time (µs)',
                         ylabel='Carrier-corrected phase change (degrees)')
        axes[1, col].grid(alpha=.2)
    fig.suptitle('Original ESP32 phase control · measured by RFS2\n'
                 'Agilex 3 capture transport → host phase analysis · no payload/BER claim')
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    print(args.output)


if __name__ == '__main__':
    main()
