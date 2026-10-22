# Original ESP32 custom-QAM TX: evidence gate, 2026-10-21

**Outcome: a concrete amplitude-only probe can advance the installed-chip polar
backend. No original-ESP32 SRAM-to-DAC source has been established.** No hardware,
UART/JTAG, flash or RF was accessed during this investigation. This is Plan B's
offline decision gate, not a completed 64-QAM transmitter.

## A tempting new upstream result is S3-specific

Inspected the previously unreviewed `research/iq-tx` branch of
[jochenhammes/esp32-sdr-trx](https://github.com/jochenhammes/esp32-sdr-trx/tree/research/iq-tx),
pinned to `6de35a5138c8f6d7bf6af2b6c8dd0c99342e72f0` (2026-10-04).
Its [research index](https://github.com/jochenhammes/esp32-sdr-trx/blob/6de35a5138c8f6d7bf6af2b6c8dd0c99342e72f0/docs/research/README.md)
explicitly identifies an **ESP32-S3 QFN56 rev0.2**, sample bank `0x3fcd0000`
and PLAY register `0x60033d64`. Its Makefile uses the S3 toolchain and target.

The authors report independently received SRAM playback, but also failed CPU/GDMA
refilling while playing. The useful architectural lesson is **preload a finite
buffer and change it only while idle**. Their amplitude and image calibration
are board-specific S3 results. Neither those results nor the general word
“ESP32” in the main README establishes original-chip playback. Do not port the
register addresses. This source does not remove the installed-chip research gate.

## New actionable branch: preserve phase while changing amplitude only

Earlier firmware intentionally preserves the gain field while making phase
pulses. The next hypothesis is to change **only** that field during a canonical
zero-step tone, leaving phase-pulse timing and enable untouched.

Two separate original-chip controls exist in the inspected SDK/ROM:

| Control | Direct evidence | Proposed use and limit |
|---|---|---|
| Tone attenuation | `rom_start_tx_tone_step`: negates each u8 attenuation argument, puts it in bits17:10 of its tone word, retains the upper nibble. Original SDK alias for tone1 is `0x3ff460b8`. | First experiment: amplitude-only updates preserving every other tone field. Gain law, phase continuity and settling are unmeasured. |
| Global forced digital gain | `set_tx_dig_gain` DWARF says `void(int force_en, int force_value)`; instructions truncate value to8bits and write `0x3ff46000[9:2]`, then force bit0. | Alternative only if tone attenuation is ineffective. Different field and possible force/mux behavior; do not sweep it or combine both controls initially. |

An attenuation-field instruction model is provided in
[`analyze_original_polar_qam.py`](../scripts/analyze_original_polar_qam.py).
It produces **no hardware commands**. Its 1,024 preservation tests cover all 256
codes against four initial words. This validates masking/encoding arithmetic,
not RF amplitude transfer. The full six-argument ROM helper changes other
frequency/control fields too; it is not an amplitude-only operation.

## One bounded hardware hypothesis to test next

This is an implementation specification for a separate diagnostic, not an
instruction to write registers from the host:

1. Preserve the exact known-good image, chip identity and canonical tone state.
   Boot RF-off; retain STOP, busy rejection and restoration readback.
2. Within **one <=50 ms job**, alternate the existing baseline tone attenuation
   with two conservatively weaker codes. Determine the weakening direction from
   existing setup plus independent received power; do not assume the S3 gain law.
   Use >=2 s quiet between jobs. A watchdog or failed PHY call must not be treated
   as proven RF-off.
3. Update only bits17:10, record original/applied/restored words and timestamps.
   Assert that the enable, frequency, high-resolution mode and second-tone
   state remain unchanged. End by stopping through the known certification API.
4. RFS2 receives a chronological CI8 burst containing several transitions.
   Measure plateau amplitude, phase jump, settling duration, clipping and
   frequency shift; compare against unchanged-code controls. A power change
   alone does not prove a useful QAM actuator.
5. Require restoration and a subsequent ordinary passive capture. If amplitude
   has repeatable plateaus with tolerable AM/PM and settling, qualify a lookup
   table. Otherwise reject this candidate before adding QAM framing.

Root operator owns that hardware gate. This agent did not execute it.

## What square 64-QAM actually requires from a polar backend

```text
FPGA Gray mapper: I,Q in {±1,±3,±5,±7}
                   │
             radius / phase LUT
                   │
         calibrated amplitude + phase schedule
                   │
        ESP32 scalar tone actuator → RF
```

The 64 points require **nine distinct radii and 52 distinct phase directions**.
Their squared radii are `2,10,18,26,34,50,58,74,98`; the radius dynamic range is
**16.902 dB**. Eight independently signed I/Q levels do not mean eight polar
amplitude levels. Existing four-state phase evidence proves only a small subset.
All 4,096 directed point transitions may have different settling requirements.

The offline script enumerates the exact geometry and records these missing
measurements. It deliberately supplies no attenuation calibration and no phase
pulse durations. An ideal polar geometry plot would be synthetic—not measured
RF and not an acceptance test.

A plausible first target is **slow 16-QAM**, after amplitude transfer and additional
phase directions are measured. Rectangular plateau modulation is not automatically
an RRC-shaped modem: phase ramps, amplitude transients, spectral occupancy, EVM
and frame BER still need qualification. FPGA waveform generation and on-board RX
recovery remain later gates in [Plan B](CUSTOM_IQ_64QAM_OTA_PLAN.md).

## Reproduce the offline result

```bash
.venv-notebooks/bin/python scripts/analyze_original_polar_qam.py \
  --self-test \
  --output cyberether/run/original-iq-research-20261021/polar-requirements.json

git clone --branch research/iq-tx --depth 1 \
  https://github.com/jochenhammes/esp32-sdr-trx.git \
  cyberether/run/original-iq-research-20261021/upstream
# For stable reproduction, require the pinned revision above before inspection.
```

Local vendor evidence inspected:

| Artifact | SHA-256 |
|---|---|
| Original `set_tx_dig_gain.disasm.txt` | `896ea9ee2133c58e16965bcf1d8fb946fdcfbf8634cad4d4132eea56d5f08edd` |
| Original rev300 `rom_start_tx_tone_step.disasm.txt` | `bcbd51d30d44535fd5d300fc8284ef640d64ebd849dd657852007911d6aedc3f` |
| Original `phy_chip_v7.debug.txt` | `0ed1c8be4f1333b8d3b0400866a3192c18a6e753fafbf9841931b1d74ffa8e45` |
| Pinned S3 research `firmware/src/radio.c` | `acd34c1d9f8d17dd1632b9e9c2c82344da72c64df9f96d9664685613b12953e5` |

The disassembly files remain ignored local evidence under
`cyberether/run/esp32-tx-investigation/` and `cyberether/run/nco-investigation/`.
The SDK/archive identity is retained in [the original investigation](ESP32_TX_INVESTIGATION.md).
