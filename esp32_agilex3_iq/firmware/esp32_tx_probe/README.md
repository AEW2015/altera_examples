# Original ESP32 TX probe

Bounded RF diagnostics for the installed original ESP32. The image supports a
vendor scalar tone and a guarded phase-pulse experiment. It does not provide
arbitrary-IQ playback or a framed BPSK/QAM modem. It uses Espressif's
`esp_phy_cert_test.h` API and does not write guessed S3 playback registers.

The separate image is for a Digilent Pmod ESP32: application UART TX/RX GPIO17/16
at 2 Mbaud, bootloader J2 GPIO1/3. Leave the two switches OFF as in the project's
existing UART/programmer setup. RF is not initialized at boot. `TONE` and `NCO`
jobs have a 50–3000 ms deadline, channel 1–11 and 80–120 quarter-dB attenuation
(20–30 dB relative vendor backoff, **not calibrated output power**). `PHASE`
jobs are limited to 50–500 ms with the same channel/backoff bounds. The worker
checks cancellation and deadlines after the vendor tone call returns; ordinary
jobs poll at 5 ms, while phase jobs schedule symbols using the CPU cycle counter
and check cancellation during busy waits. These are firmware guards, not an
independently timed RF shutdown guarantee if the CPU or RF call hangs.

Build beside the pinned ESP-IDF tools:

```bash
# Optional: select an existing checkout of the exact pinned SDK.
export ATUM_ESP_IDF=/path/to/esp-idf-sdr
export IDF_TOOLS_PATH=/path/to/its/espressif-tools
bash scripts/build_tx_probe.sh
```

The build records SDK and image hashes under ignored `build-esp32-tx-probe/`.
It does not program hardware. Save a full private flash backup of the chosen
module in the ROM session before changing its firmware; NVS may contain secrets.

Follow [the existing bridge/reset procedure](../../docs/ESP32_FIRMWARE.md) using
`--build-dir build-esp32-tx-probe` with `flash_esp32.py`. Restore the previous
runtime FPGA hub before normal boot. Only the selected ESP32 firmware changes.
The original RF-suite build remains available separately for restoration.

Commands, each terminated by a newline:

| Command | Behavior |
|---|---|
| `INFO` | Identity, chip revision, MAC, pins, busy state and firmware version; no RF initialization |
| `TONE 3 3000 96` | Channel 3, maximum 3 seconds, 24 dB vendor power backoff |
| `STATE` | Read tone control words after RF has been initialized |
| `STOP` | Request cancellation; poll `INFO` for `busy=0` and `STATE` for disabled tones |

Once the image is booted and the normal IQB1 FPGA hub restored, stop the current
viewer using its own checkout's `lessons.stop_demo()`, then run from this example:

```bash
.venv-notebooks/bin/python scripts/check_esp32_tone.py \
  --port /dev/ttyUSB0 --tx-source 1 --rx-source 0 \
  --output cyberether/run/tone-test-001
```

This opens one FPGA UART owner, briefly uses the Nios owner to disable paired
FIR output, then captures RFS2 before/during/after a bounded PMOD A tone. RX gain
is fixed. Saved CI8 captures, transport CRCs, firmware identity, tone acknowledgments,
relative powers and PNG stay local. FFT/power analysis is host Python. The check
requires a 6 dB rise and fall, less than 1% ADC rail hits and collection inside the
tone window. It is diagnostic evidence, not calibrated RF characterization.

The SDK documents these API calls in its
[RF calibration guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/RF_calibration.html).
Source tracing and the remaining arbitrary-IQ gate are in
[ESP32_TX_INVESTIGATION.md](../../docs/ESP32_TX_INVESTIGATION.md).

A host-timed OOK example reuses the same probe firmware without another flash:

```bash
.venv-notebooks/bin/python scripts/check_esp32_ook.py \
  --port /dev/ttyUSB0 --payload-hex a55a0123456789ff \
  --output cyberether/run/ook-test-new
```

The detector trains on separate off/on captures and compares measured bits with
the requested payload. The host coordinates each capture slot; this does not
provide independent frame/symbol synchronization or FPGA detection/FEC. Actual
qualification and saved plots: [bring-up results](../../docs/ESP32_TX_BRINGUP_RESULTS.md).

## v2 NCO frequency probe

The v2 image adds `STATE` (read-only, after RF initialization) and
`NCO channel duration_ms backoff_qdb raw_step`. The raw step is limited to
**0..32**, not a signed IQ value or a frequency in Hz. Original-chip SDK DWARF
identifies the ROM function as **two tone-generator enable/frequency/attenuation
triples**. The code preserves the vendor enables, attenuation and resolution
mode; it rejects unexpected enable/reserved fields. The same positive step is
written to both generators, including the frequency field of a disabled one.
Original frequency/extension values are restored through the ROM routine before
the vendor stop sequence; their exact before/after/restored words are logged.

The predicted grid is 156.25 kHz or 39.0625 kHz per step, depending on the existing
mode. An original ESP32 PMOD-A v2 → RFS2 sweep measured the mode-12 displacement
for raw steps 0..32 in agreement with the nominal grid at 1.953125 kHz receiver
FFT resolution. This is relative-frequency evidence, not calibrated absolute
frequency or power. There is no Cartesian I/Q injection in this interface.
[Measured results](../../docs/ESP32_NCO_RF_RESULTS.md) and [ABI evidence with the
offline model](../../docs/ESP32_NCO_PROBE_EVIDENCE.md).

After explicitly installing v2 and restoring the FPGA hub:

```bash
.venv-notebooks/bin/python scripts/check_esp32_nco.py \
  --port /dev/ttyUSB0 --output cyberether/run/nco-new
```

The checker rejects v1, captures seven raw step settings, checks mode/gain/enable
and step readback, checks restoration, and compares measured RF frequency shifts
with the nominal grid. The plots use host FFTs. The cited sweep established this
bounded scalar-tone displacement, not arbitrary IQ, symbol modulation or an
absolute frequency calibration.

## v3 phase-pulse timing probe

The v3 firmware adds `PHASECAP`, `PHASE`, and `PHASESTAT` for a bounded
frequency-increment pulse experiment. These commands schedule toggles of the
already-qualified low frequency bit in tone 1; they do not feed cosine/sine
samples or decoded bits to the radio. The extension register is restored after
each pulse, then the vendor tone and RF test mode are stopped when the job
completes.

| Command | Syntax / response | Meaning |
|---|---|---|
| `PHASECAP` | `PHASECAP,cpu=…,half_cycles=…,step_nom_mHz=39062500` | Reports current CPU clock, nominal half-turn cycle count and nominal mode-12 step in millihertz. It does not measure RF phase. |
| `PHASE` | `PHASE channel duration_ms backoff_qdb pattern symbol_us pulse_cycles` | Start a guarded repeating pattern of CPU-timed increments. Pattern is a decimal 8-bit value sent MSB first and repeated. |
| `PHASESTAT` | `PHASESTAT,job=…,cpu=…,symbols=…,flips=…,min=…,max=…,late=…` | Read scheduled symbol count, transition count, minimum/maximum pulse widths in CPU cycles and late-slot count for the current/last job. |

The parser bounds PHASE to channel 1–11, duration 50–500 ms, backoff 80–120
quarter-dB, pattern 0–255, symbol period 32–256 µs and pulse width 0–8192 CPU
cycles. The firmware also rejects a pulse wider than half a symbol. It requires
the canonical high-resolution state: tone 1 enabled at raw step zero, tone 2
disabled, and the relevant reserved/extension fields clear. It changes only
tone 1 extension bit 0 during a pulse; the main tone words are not rewritten.
On completion or STOP, the saved extension value is written back and the vendor
tone/RF test mode are stopped.

`min`/`max` in `PHASESTAT` are measured CPU cycle deltas around the firmware's
register pulse. They are **CPU timing**, not a measurement of RF phase or exact
RF pulse duration. The nominal conversion `39062.5 Hz × pulse duration` is only
a hypothesis because register-store latency, scheduling, the RF accumulator's
continuity and the receiver all affect what appears over the air. The
independent receiver analysis is the evidence for any RF phase change.

Independent RFS2 measurements now show persistent approximately 180° changes
for the full-width pulses, with carrier-only and half-width negative controls.
[Measured results and timing limits](../../docs/ESP32_PHASE_RF_RESULTS.md).
Do not infer decoded bits, a preamble/header, BER or arbitrary-IQ capability
from those states. See the experiment's
[measurement and interpretation guide](../../docs/ESP32_PHASE_PROBE.md).

After explicitly installing v3 and restoring the FPGA hub, run the independent
capture/checker on the Linux host or container with the board attached:

```bash
.venv-notebooks/bin/python scripts/check_esp32_phase.py \
  --port /dev/ttyUSB0 --output cyberether/run/phase-test-new
```

Options are `--repeats 1..5` (default 2), `--rx-gain 0..127` (default 0),
`--backoff-qdb 80..120` (default 96), `--pattern 0..255` (decimal; default 165),
`--symbol-us 32..256` (default 64), and optional `--pulse-cycles N` (1..8192)
to override the CPU-derived nominal half-turn width. The checker also requires
`--output` and accepts optional `--port`; inspect
`scripts/check_esp32_phase.py --help` for current details. It records zero-pulse,
half-width and nominal-half-turn captures, receiver analysis and state/telemetry
proof. `--pulse-cycles` changes the test duration only; it is never a requested
or assumed RF phase. No command in the README builds or flashes a device by
default; retain the full backup and existing safe flash/restore procedure above.

## v4 compact framed BPSK experiment

v4 adds a **hardware-tested compact framed phase-pulse BPSK** transmitter. It uses
the same original-chip scalar tone path; it is not an arbitrary-IQ upload API.
Its independent host receiver and live graphs are described in
[RF BPSK walkthrough](../../docs/RF_BPSK_WALKTHROUGH.md).

```text
16 sync bits      44 K7(171,133) coded bits                 4 guard bits
0x0651        |   payload8 + CRC8 + six zero tail bits  |   0000
              <-------- 64 symbols, repeated --------->
```

All fields are MSB first. CRC8 uses polynomial `0x07`, initial value zero, over
the payload byte. The encoder starts in state zero each frame and terminates
with six zero bits. State `0` maps to the positive BPSK phase; state `1` to its
opposite. The sync word combines a 13-bit Barker sequence and fixed version bits
`001`; the format has no variable length/header fields. Native C tests compare
all 256 encoded payloads with independent Python references.

| Command | Result |
|---|---|
| `FRAMEBITS 165` | Read-only `FRAMEBITS,payload=165,bits=<64 binary digits>`; no RF initialization |
| `FRAME 8 500 120 165 8 670` | Repeated frames, channel 8, 500 ms maximum, payload `0xA5`, 8 µs symbols, measured-profile 670-cycle request |
| `FASTPHASE 8 500 120 165 32 670 3` | Faster phase diagnostic using extension step 3 and repeated 8-bit pattern |
| `PHASECAP` | Also reports `fast_half_cycles` and `fast_step=3` |
| `PHASESTAT` | Also reports missed/rescheduled slots and completed 64-symbol frames |

`FRAME` emits `FRAME_CFG` with job, CPU clock, symbol period, pulse cycles,
payload, frame length and step. `FASTPHASE` emits `PHASE_CFG`. Both retain
`TX_ON`/`TX_OFF`, the 50–500 ms bound, channel 1–11 and backoff 80–120. Frame
payloads are 0–255; fast symbols are 8–256 µs. Pulse requests are 0–8192 cycles
and must fit within 80% of the symbol period; zero is a diagnostic negative
control, not a usable modulation setting. The host frame demo accepts 8–15 µs
symbols because a longer frame does not fit its fixed receiver snapshot.

Step 3 nominally gives a 4.267 µs half-turn, much faster than the earlier step-1
experiment. Independent RFS2 measurements qualified a 670-cycle request at 160 MHz on the installed PMOD A. Other settings need their own qualification. Pulses mask
interrupts only during their bounded individual width; the full job does not
mask interrupts. The worker records late/missed slots and restarts a damaged
frame at its marker. A symbol counter or completed-frame count proves firmware
scheduling only, not successful RF reception.

After explicit installation and restoring the runtime hub:

```bash
.venv-notebooks/bin/python scripts/check_rf_bpsk.py \
  --output cyberether/run/rf-bpsk-new --captures 4 --payload 165 \
  --snapshot cyberether/run/rf-link-state.json
```

The host verifies frame-bit and setting readbacks, records actual CI8 and CRC
metadata, stops the transmitter and restores receiver gain. Carrier/timing/frame
recovery and FEC in this initial capture command run on the **host**. Known bits
are used only after recovery to count errors. CRC-failed synchronized frames
remain in BER counts; unobserved gaps and acquisition failures stay separate.
The separate `check_rf_bpsk_fpga.py` can replay measured, host-synchronized symbols
through the existing FPGA demapper/FEC after explicitly loading checkpoint 06.

## v5: experimental Gray QPSK phase frames

v5 retains every v4 command and adds independently calibrated transitions:

```text
QFRAMEBITS 165
QFRAME 8 500 120 165 8 335 670 1005
STOP
```

`QFRAME` arguments are channel, bounded duration (50–500 ms), attenuation
(80–120 quarter-dB), payload byte, symbol period (8–256 µs), and three requested
CPU pulse widths for +1/+2/+3 phase-state advances modulo four. The measured
RF phase advances in the negative direction. The three widths are independent;
firmware does not assume that doubling a pulse request doubles the phase.
The largest request must fit within 80% of a symbol. Requests run only at an
explicit command; normal startup leaves RF disabled. `STOP` remains available
between the short interrupt-masked pulses. The worker uses `xTaskCreate`, also
on the pinned SDK's single-core configuration.

The provisional 160 MHz profile is **335 / 670 / 1005 request cycles**. Quarter
and half turns were measured separately at a longer symbol period. A complete
8 µs QPSK frame, especially the three-quarter transition, needs its own RF
qualification; compiling the image or decoding the Python fixture is not that
qualification. `QFRAME_CFG` reports the CPU clock, all three requests, payload,
symbol period, job ID and 64-symbol size for matching against each capture.

```text
32 known training states | 22 QPSK coded symbols | 10 zero-state guards
01320312023110233012032120310302
```

The body is the same payload8 + CRC8 + six terminating zeros encoded with K=7
(171,133 octal) as v4. Adjacent coded-bit pairs use cardinal Gray labels:
`00→state0`, `01→state1`, `11→state2`, `10→state3`. State `k` ideally has phase
`−k·π/2`. On each symbol the firmware advances by `(target-current) mod 4`;
unchanged states require no pulse. It tracks the actual applied state across a
missed deadline, abandons the damaged frame and restarts its training marker.
This remains a scalar NCO phase-pulse experiment, not arbitrary Cartesian IQ or
a pulse-shaped standards-compliant QPSK transmitter.

`QFRAMEBITS payload8` reports the actual 64 state digits without initializing RF.
Native tests compare all 256 payloads against the independent Python encoder.
`cyberether/rf_qpsk.py` estimates carrier/timing/phase from fixed training,
soft-demaps the captured body, then runs Viterbi and CRC on the host. Optional
known payload is only a BER reference after acquisition. The synthetic test
includes phase ramps, random capture phase, CFO and noise, and is labelled as
simulation. Hardware capture requires already-installed v5 firmware:

```bash
python scripts/check_rf_qpsk.py --synthetic --output cyberether/run/qpsk-model
python scripts/check_rf_qpsk.py --output cyberether/run/qpsk-rf --captures 4
```

The second command uses the existing FPGA capture transport and briefly enables
PMOD A RF; it does not flash either device. Use the shared RF Link capture lock
and one acquisition owner. The script verifies state-encoder/configuration
readbacks, saves original CI8, checks transmitter idle/tone-off and restores RX
gain. Sparse gaps between captures are not counted as error-free traffic.

## v6: cycle-bounded phase scheduling

v6 preserves the v5 commands and replaces the wall-clock call in every symbol
with a cached CPU-cycle deadline. At phase-loop entry it reads elapsed wall time
once, subtracts that setup time from the original bounded job duration, and
checks that the remaining cycle budget is positive and below `2^31`. Signed
32-bit deadline comparisons remain valid when the hardware counter wraps.
The build rejects dynamic frequency scaling (`CONFIG_PM_ENABLE` must be off);
the qualified profile uses a fixed 160 MHz CPU. A symbol whose scheduled start
is outside the deadline is not transmitted.

The interrupt mask still covers only an individual frequency pulse. UART STOP,
missed-slot restart, tone-off and register restoration retain their existing
behavior. This is software scheduling: an in-progress short pulse and interrupt
latency still set the stop granularity; it is not a hardware RF kill timer.
Native tests exercise counter wrap, exact expiration, expired setup budgets and
the removal of per-symbol wall-clock reads. RF testing must separately establish
whether this reduces missed deadlines or enables complete 8 µs QPSK frames.
The previously qualified v5 firmware is retained privately before rebuilding;
v6 compilation by itself is not a new RF qualification.
