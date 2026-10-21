# Original ESP32 NCO probe evidence

The original chip has a concrete programmable tone path. **Its six arguments
are two enable/frequency/attenuation triples, not Cartesian I and Q samples.**
This note establishes the ABI from original-chip SDK debug information and ROM
instructions, then defines the next bounded frequency experiment. It does not
claim that the new experiment has already run or that a 64-QAM transmitter exists.

## Strongest evidence: retained vendor DWARF

The inspected SDK is `25fe69f946311abdaf9ad56591f25fedbc20ac98`.
Original-chip `libphy.a` SHA-256:
`c2521071695734afa8f6f1ca3d3b604a1d08dd63fe52060449a11cfe8bac5740`.

Unlike the official ROM ELFs, `libphy.a:phy_chip_v7.o` retains DWARF information.
It gives these **actual formal parameter names** for the MHz wrapper:

```c
void ram_start_tx_tone(
    int tone1_en, int freq_1_mhz, int tone1_atten,
    int tone2_en, int freq_2_mhz, int tone2_atten);
```

The PHY function-table member at byte offset **68** is `start_tx_tone_step_`.
Its DWARF type is a pointer to a void function with arguments:

```text
bool, sint16, uint8, bool, sint16, uint8
```

In this vendor compilation, `bool` is an unsigned-byte typedef; the intended
inputs are still **0 or 1**. The MHz wrapper occupies table offset **72**.
Both types and offsets agree with the disassembly. These names remove the
ambiguity caused by labeling the frequency arguments “i” and “q”.

## What the ROM instructions do

The official original-chip rev0/rev300 ROM images agree on the examined path.
The initial table entry at offset 68 points to `rom_start_tx_tone_step` at
`0x400035d0`. See [the full investigation](ESP32_TX_INVESTIGATION.md) for ROM
hashes, table initialization and SDK patch details.

| Item | Proven operation | Remaining interpretation/measurement |
|---|---|---|
| Tone 1 control | `0x600060b8`; SDK RAM code accesses `0x3ff460b8` | RF offset sign and actual output response |
| Tone 2 control | `0x600060bc`; corresponding original-chip access window | Relationship/combination of the two tone sources |
| Enable argument | Unsigned byte shifted left 18; normal input 0/1 | Never treat the field as a linear amplitude |
| Attenuation argument | Negated, reduced to 8 bits, shifted left 10 | Physical dB/code, linearity and safe useful range on this chip |
| Frequency argument | A wrapped frequency increment; low ten bits in control | Physical offset verification against independent RX |
| Control bit 29 | Selects the wrapper's 10-bit versus 12-bit frequency handling | Do not toggle it as a guessed bandwidth/rate setting |
| 12-bit extension | Low two frequency bits for each tone go to bits 1:0 / 3:2 of `0x600050a8`; remaining ten bits go to each control word | Capture the original value and preserve unrelated bits |
| High control nibble | Existing bits 31:28 preserved independently in each word | Other fields must be reconstructed exactly |

For ordinary nonnegative wrapped increments, the rebuilt tone word is:

```text
old bits31:28 | enable<<18 | ((−attenuation)&255)<<10 | frequency_bits
```

The routine also clears bits 27:26. It rebuilds the full enable byte in bits
25:18; reading only bit 18 is insufficient to confirm an ordinary pre-probe
state. Reject an unexpected enable byte or nonzero bits 27:26 before calling it
in a preservation experiment.

**The attenuation byte is not a signed linear I/Q amplitude.** Its proven
meaning is a vendor `tone*_atten` parameter encoded as a negated byte. A physical
dB law does not follow from the encoding alone. Preserve the vendor CW setting
for the first frequency experiment; do not import another chip's gain curve.

### Frequency conversion and expected scale

For bounded integer MHz arguments, the wrapper computes:

```text
bit29 clear: step = trunc(freq_MHz × 32/5)  modulo 1024
bit29 set:   step = trunc(freq_MHz × 128/5) modulo 4096
```

Truncation is toward zero. The script independently checks the compiler's
multiply-high/divide-by-five instruction sequence for all integer inputs −80..80.

The parameter names and conversion imply the following **nominal prediction**:

| Raw step | 10-bit mode | 12-bit mode |
|---:|---:|---:|
| 1 | 156.25 kHz | 39.0625 kHz |
| 8 | 1.25 MHz | 312.5 kHz |
| 16 | 2.5 MHz | 625 kHz |
| 32 | 5 MHz | 1.25 MHz |

Equivalently, the nominal arithmetic corresponds to a 160 MHz phase-generator
reference and a 10/12-bit increment. This is an inference from vendor MHz
conversion—not a measured original-chip clock or RF offset. Confirm it with RX
before reporting it as a calibrated capability. It is unrelated to our selected
16/40/80 MS/s RX capture rate.

### Important negative-step trap

The raw ABI says `sint16`, but the implementation sign-extends that argument and
masks it with `0x0fffffff` before combining the fields. A direct raw step of
**−1** can therefore fill attenuation and enable bits with ones. This is not a
safe way to request a negative offset.

The SDK MHz wrapper avoids this by masking the computed increment to **10 or
12 bits first**. For a later negative-frequency experiment, use the original MHz
wrapper or the correctly wrapped positive N-bit code; do not pass a negative
raw `sint16`. The first proposed probe restricts raw steps to **0..32**.

## Original-chip vendor call-site checks

The following register-window call arguments are visible immediately before
calls through the original PHY table. Xtensa windowed calls place the six
arguments in `a10..a15` before `callx8`.

| Caller in `librftest.a` | Observed arguments to table offset 68 | What it supports |
|---|---|---|
| `set_freq_test` | `(1, 32, 80, 0, 0, 0)` | Enable, raw increment, positive attenuation, second tone disabled |
| `get_path_loss_offset` | `(1, 64, 20, 0, 0, 0)`; later `(0, 64, 40, 0, 0, 0)` | Enable/disable is distinct from frequency and attenuation |
| `test_tx_vdd33` | `(1, 128, variable_attenuation, 0, 0, 0)` | Another ordinary positive increment |

`rfcal_txiq` in `libphy.a` similarly calls the raw-step entry with one enabled
tone, a frequency increment and a separate attenuation argument. These internal
calls support the ABI interpretation; they are not authorization to run complete
calibration/test routines or change their unrelated registers.

## What transfers from the S3 polar transmitter

Inspected source:
[`jochenhammes/esp32-sdr-trx`](https://github.com/jochenhammes/esp32-sdr-trx/tree/e1aebbf2ef508c7199a9b6c6c277b57fe0b51aa9),
commit `e1aebbf2ef508c7199a9b6c6c277b57fe0b51aa9`.
The source is Zero-Clause BSD. This evidence note does not copy its firmware.

Its S3 firmware steers a fractional PLL word for frequency, applies a measured
attenuation curve for envelope level, and tracks update deadlines and buffer
failures. Its host converts analytic signals into envelope and phase derivative.
That is a useful **polar-modulation architecture**, distinct from SRAM IQ
playback. [S3 firmware](https://github.com/jochenhammes/esp32-sdr-trx/blob/e1aebbf2ef508c7199a9b6c6c277b57fe0b51aa9/firmware/src/radio.c),
[host modulation model](https://github.com/jochenhammes/esp32-sdr-trx/blob/e1aebbf2ef508c7199a9b6c6c277b57fe0b51aa9/src/espdr/txmodes.py)

Its experiments reject interpreting tone frequency fields as I/Q sample inputs.
They also find a discontinuous gain region and qualify a separate useful range.
Those observations motivate measuring our original chip first; its S3 register
addresses, gain table, update rate and PLL scaling are **not transferable device
settings**. [S3 research evidence](https://github.com/jochenhammes/esp32-sdr-trx/blob/e1aebbf2ef508c7199a9b6c6c277b57fe0b51aa9/docs/research/TX-RESEARCH.md)

```text
Possible later original-chip polar modem

FPGA complex waveform → envelope + phase derivative
                                 │
              measured gain map + original-chip frequency actuator
                                 │
                      bounded, timed TX updates
```

This requires an original-chip gain calibration and frequency actuator with
sufficient resolution, bandwidth and stable phase behavior. The coarse NCO grid
alone does not establish that. No arbitrary phase argument or direct static-IQ
input has been identified in the six-argument tone ABI.

## Next bounded experiment

1. Start from the already qualified reduced-power CW diagnostic. Snapshot both
   tone control words, enables/attenuation bytes, bit 29 and the extension word.
2. Reject unexpected control state. Keep enables, attenuation and mode unchanged;
   vary only the wrapped raw increment over `0, 8, 16, 32`. The disabled tone may
   have its increment changed too, but must remain disabled.
3. Capture the independent receiver with enough bandwidth to cover the expected
   displacement. Measure actual offset against the initial CW, clipping, image
   levels and power. A peak outside the receiver band is not a failed transmitter.
4. Stop on deadline, record STOP/idle, and verify baseline/restore. Do not reuse
   a session's apparent gain/phase calibration after a retune without checking it.
5. Only after offset/sign are measured, try a locally timed two-frequency
   sequence and compare detected bits/FEC. Keep host-timed OOK evidence separate.

A static-IQ experiment needs a genuine amplitude/phase actuator or independently
proven orthogonal static sources. Enabling “tone 2” is not sufficient evidence
of a Q axis, and feeding cosine/sine values into frequency arguments is invalid.

## Reproduce the offline evidence

```bash
.venv-notebooks/bin/python scripts/investigate_esp32_nco.py --self-test
.venv-notebooks/bin/python scripts/investigate_esp32_nco.py \
  --idf-root "$IDF_PATH" \
  --upstream-root vendor/esp32-sdr-trx
```

The script reads the original archives, extracts the retained DWARF ABI and
selected call-site disassembly, fingerprints sources, and emits a pure Python
register-word model under `cyberether/run/nco-investigation/`. It never accesses
serial/JTAG or starts RF. `report.json` and the `.debug.txt`/`.disasm.txt` files
are local ignored evidence; the documentation and reproducible script are the
reviewable source deliverables.
