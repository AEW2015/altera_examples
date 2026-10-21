# Original ESP32 phase-pulse experiment

**Question:** does a short frequency-increment pulse leave a persistent phase
change when the increment returns to zero, without rewriting the main tone
control word?

The existing RF NCO sweep established the original-chip 12-bit increment grid
at approximately **39,062.5 Hz per step**. That establishes frequency control;
it does not establish accumulator continuity or a Cartesian IQ input.

```text
TX increment:  0 ──────┌──── step1 ────┐──────── 0
                      │              │
                      └── 12.8 µs ───┘

If phase is continuous:
phase:         ────────╱───────────────  +π relative to previous plateau

If the update resets phase:
phase:         ────────╱?──────────────  behavior must be measured
```

For a continuous accumulator, the nominal extra phase is:

```text
Δφ = 2π × 39062.5 Hz × pulse duration
12.8 µs → π radians       6.4 µs → π/2 radians
```

At 160 MHz CPU frequency, 12.8 µs corresponds to 2048 cycles; at 240 MHz it is
3072 cycles. Those are target timings, not measured radio pulse widths. Actual
clock frequency, register-store latency, interrupts and memory ordering matter.
Record measured cycle deltas and independently inspect the received phase.

The proposed firmware operation changes only extension bit0 in
`0x600050a8`, then clears it while retaining the main control words and all
unrelated fields. This follows the original-chip register evidence; it is not
an instruction to copy another chip's addresses. The root operator owns that
bounded firmware/hardware experiment. The analyzer below never accesses it.

## Independent receiver analysis

[`scripts/analyze_esp32_phase.py`](../scripts/analyze_esp32_phase.py) reads supplied
**signed CI8** files. It does not contact serial/JTAG, command a transmitter,
reflash firmware, or replace samples with a modulation model.

```text
Actual IQ file → coarse spectrum → squared-phase CFO estimate
                                         ↓
                  detect frequency excursions and plateau intervals
                                         ↓
             refine CFO using an independent intercept per plateau
                                         ↓
       measured phase changes + circular moments + raw phase histogram
```

Squaring removes a 180° state ambiguity, but makes carrier frequency ambiguous
modulo half the sample rate. The coarse spectrum/prior chooses that branch.
The first estimator trims pulse outliers; refinement fits phase slopes only
inside detected plateaus, never across intentional phase changes. Separate
plateau intercepts are free: the algorithm does not force them to zero or π.

A single line fitted to unwrapped squared phase would be misleading here: a
continuous π ramp contains a complete squared-phase revolution and would bias
the estimated carrier. A simple median is also biased when positive pulses
occupy a substantial fraction of a burst. The two-stage estimator avoids those
specific problems, subject to the stated plateau and SNR assumptions.

Detected event measurements include:

- Before/after principal phase change and independently unwrapped phase change.
- Detected excursion span and peak frequency excursion (the span includes analysis-window and RX ringing effects).
- Before/after plateau coherence.
- Whether the measured change is within 30° of π, with coherent plateaus.

The target pulse width is saved as metadata only. It does not determine where
an event occurs or what phase change the analyzer reports.

## What establishes two measured phase states

Two clusters are not assumed by fitting a two-cluster model. The analyzer
requires all of these measured conditions:

| Evidence | Criterion |
|---|---|
| First circular moment | Below 0.7: rejects a single compact CW cluster |
| Second circular moment | Above 0.8: supports antipodal phase structure |
| Measured separation | Greater than 150° |
| Occupancy | Both measured phase groups exceed 15% of plateau samples |
| Within-group coherence | Both exceed 0.85 |
| Independent events | At least two coherent measured near-π transitions |
| Capture quality | Strong spectral candidate, low rail hits and useful CI8 headroom |

A second-moment axis is used to describe group occupancy and measured means.
It does not replace the raw scatter or phase histogram, and does not by itself
establish two clusters. Corrected plots retain actual phase ramps and noise;
there is no snapping to ideal constellation points.

**Two antipodal clusters do not establish decoded payload bits, transmitter
identity, a preamble/header, or BER.** Interference can also create phase
structure. Those claims require a subsequent framed modem and independent
source/transport evidence.

## Run on an actual supplied capture

For the current experiment, RX and TX use the same nominal carrier. The measured
carrier difference is near +17.6 kHz, so search around zero:

```bash
.venv-notebooks/bin/python scripts/analyze_esp32_phase.py capture.ci8 \
  --rate 16000000 --expected-offset-hz 0 --pulse-us 12.8 \
  --output cyberether/run/phase-analysis/my-capture
```

Files produced:

- `analysis.json`: capture hash, measured carrier/events/statistics and explicit limits.
- `phase-analysis.png`: raw/corrected scatter, phase histogram, phase trace,
  frequency trace and measured event phase changes.

The CLI's generic default frequency prior is +5 MHz for earlier offset-tuned
experiments. Use `--expected-offset-hz 0` for this same-carrier setup. A wrong
prior can select noise or a harmonic; its resulting estimates must not be used
as proof. Check the recorded spectrum/quality and the expected capture metadata.

For Python:

```python
from analyze_esp32_phase import load_ci8, analyze_iq, plot_report

result = analyze_iq(load_ci8("capture.ci8"), rate=16e6,
                    expected_offset_hz=0, expected_pulse_us=12.8)
print(result["carrier"])
print(result["metrics"])
print(result["events"])
plot_report(result, "phase-analysis.png")
```

The module lives in `scripts/`; notebook setup must put that directory on
`sys.path`, as the other lessons already do.

## Controls and current validation

Synthetic controls explicitly identify themselves as generated data:

```bash
.venv-notebooks/bin/python scripts/analyze_esp32_phase.py --self-test \
  --output cyberether/run/phase-analysis-controls
.venv-notebooks/bin/python -m unittest discover -s cyberether/tests \
  -p test_esp32_phase_analysis.py -v
```

Six test groups pass. The 16,380-sample, repeated `0xA5`, 64 µs-symbol synthetic
experiment produces measured near-π events and antipodal plateaus with 12.8 µs
pulses. Zero-width CW and 6.4 µs quadrature controls do not qualify as two-state
phase evidence. A synthetic endpoint-preserving ringing transient also passes with one event per
transition. CW, OOK, four-state phase, reset-at-pulse-end, smaller-phase and
noise controls also fail that qualification. Global phase and carrier-sign
changes do not alter the positive result. These are analyzer tests, not proof
that the ESP32's accumulator behaves that way.

An existing physical CW capture from `nco-test-002/step-0-0.ci8` was also analyzed
offline as a negative control: it did not establish two phase states. It shows
strong concentration near four extreme component codes, despite zero exact
rail hits. The analyzer flags that limited headroom/code concentration; it does
not reinterpret the file as unsigned IQ or claim that the estimated phase is
accurate. Reacquiring with suitable RX headroom is preferable to compensating
for an unknown limiting mechanism in software.

The physical zero-pulse CW, full-width and half-width experiments described
below now supply those attribution controls, with verified source/settings and
automatic stops. The conclusion comes from received measurements, not merely
the nominal 12.8 µs calculation.


## Physical pulse review and detector refinement

Independent offline review now covers **30 distinct physical capture files**
from `phase-test-001` through `phase-test-005`. No new hardware was accessed by
this review. Original proofs/captures remain unchanged; updated analysis is
saved separately with the analyzer SHA and each capture SHA.

| Cases | Captures | Result after grouping |
|---|---:|---|
| Zero-pulse CW | 10 | No detected events; two-state qualification false |
| Half-width controls | 10 | 91 measured events total; zero near-π events; two-state qualification false |
| Nominal half-turn pulses | 10 | 90 measured near-π events total; all captures show two persistent near-antipodal phase groups |

Counts vary with pattern, symbol period and capture boundaries; the detector
receives none of those known bits or expected transition counts. The 128 µs
symbol experiments have about half as many transitions as 64 µs, and the changed
`0x3C` pattern has fewer transitions than `0xA5`. Those controls strengthen
attribution to the programmed phase pulses.

The initial detector sometimes counted two or three derivative/ringing lobes as
separate events. It now requires **6 µs of quiet** between events after its
4 µs differential-phase window. This groups received ringing while preserving
separate transitions in these experiments. It does not use the nominal TX pulse
width to manufacture a transition. Closely spaced transitions below this
resolution can merge; faster-symbol work needs a separately qualified detector.
A synthetic smooth ringing transient with unchanged endpoint phases is included
as a regression, alongside all prior negative controls.

The received unwrapped phase contains persistent staircase changes, rather than
only a transient excursion that returns to the original plateau. Full-width
case medians in the first four batches are approximately −179° to −183°;
half-width controls produce approximately −91° to −96°. The negative sign is
measured in this receiver's IQ orientation. It is not flipped to match a presumed
TX convention. This is strong evidence for a useful **phase-continuous,
BPSK-like precursor**, without identifying decoded bits or BER.

### Calibration remains empirical

The fifth batch requests 2024 CPU cycles instead of 2048. It tests the hypothesis
that subtracting previously observed timing overhead will improve the phase.
Its first nominal capture has median −181.74° and second circular moment 0.996;
its second has median −173.93° and moment 0.896. Both pass the declared
near-antipodal criterion, but the latter is visibly less ideal. The phase error
is fairly consistent within that burst, so isolated IRQ overruns alone cannot
be assumed to explain it.

CPU min/max timing does not uniquely calibrate peripheral edge timing or received
RF phase. ADC/IQ distortion, residual carrier-estimation uncertainty, filtering,
and actual register timing remain possible contributors. These results do not
justify claiming that subtracting 24 cycles solved phase calibration. Keep raw
measurements and controls visible; further calibration must measure the actual
phase error rather than snap samples to ±1.

Reproduce a review without changing the original evidence:

```bash
.venv-notebooks/bin/python scripts/analyze_esp32_phase.py \
  --review-root cyberether/run/phase-test-001 \
  --review-root cyberether/run/phase-test-002 \
  --review-root cyberether/run/phase-test-003 \
  --review-root cyberether/run/phase-test-004 \
  --review-root cyberether/run/phase-test-005 \
  --expected-offset-hz 0 --output cyberether/run/phase-reanalysis
```

See [the physical RF phase results](ESP32_PHASE_RF_RESULTS.md) for the operator's
hardware settings, state/readback evidence and resulting demonstration scope.
