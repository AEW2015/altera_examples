# QPSK qualification on the installed original ESP32

The v5 results below remain the historical baseline. The flashed v6 app now passes startup and bounded RFS2 RF tests: BPSK acquired nine frames from eight captures (eight CRC pass, one fail); QPSK results vary by symbol period, with the 9 µs batch showing coded and payload errors. Strict `TX_ON` readback now gates capture on the actual channel/backoff/duration. These short runs do not meet the 100,000-payload-bit target, and watchdog recovery remains unproven.

This remains a bounded scalar NCO phase-pulse link. It does not provide arbitrary Cartesian IQ playback or FPGA raw-waveform synchronization. The host still performs carrier/timing/frame recovery and FEC; Agilex transports captures and separately processes recovered symbols in checkpoint 06.

## Phase-state gate

The four-state gate used v4 `FASTPHASE` on PMOD A, RFS2 at channel 8 / 2447 MHz, 16 MS/s, manual gain 0, 160 MHz CPU, step 3, pattern `165` (`0xA5`) and 32 µs symbols. The 335-cycle quarter-turn case qualified in 3/3 captures with balanced clusters roughly 90° apart. The zero-pulse CW controls (0/3) and 670-cycle antipodal BPSK controls (0/3) correctly failed four-state qualification. The proof and raw capture hashes are at `cyberether/run/phase-qpsk-gate-001/four-state-proof.json`.

These are the historical v4 phase-control settings. Load the intended compatible
probe and runtime hub before any physical repeat. The current v6 image has passed
normal boot, but its RF transmission and watchdog-recovery behavior remain
unqualified.

```bash
.venv-notebooks/bin/python scripts/check_esp32_phase.py \
  --output cyberether/run/phase-qpsk-repeat \
  --fast-step 3 --pulse-cycles 670 --symbol-us 32 \
  --pattern 165 --repeats 3 --rx-gain 0 --backoff-qdb 120

.venv-notebooks/bin/python scripts/check_phase_states.py \
  cyberether/run/phase-qpsk-repeat \
  --output cyberether/run/phase-qpsk-repeat/four-state-proof.json
```

The first command makes bounded RF captures; the second checks saved CI8 hashes and analyzes phase plateaus offline. The analysis reports cluster population/coherence, quarter-turn events and clipping/headroom, but does not decode QPSK bits. Use a new output directory for every run.

## v5 firmware and frame contract

The v5 transmitter was flashed and verified. Startup identified `TX_PROBE,v=5`; the application SHA-256 was `057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`. The BPSK regression passed with four valid frames from four captures and 1/176 coded errors → 0/32 payload errors.

Before v6 programming, PMOD A was backed up privately (2 MiB) and MAC-verified
as `78:21:84:d4:4f:98`; the backup application matches the preserved v5 SHA-256
`057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`. The v6
WDT-recovery/timing application SHA-256
`baac3d3881539cb4321c09bda7245b7a3823762d2b3639e6e21c7d9579fc1dbb` was flashed,
and separate verify-flash passed. Proof is
`cyberether/run/tx-probe-private/v6-watchdog-install/install-record.json`.
The v6 startup identity subsequently passed with `busy=0` and 160 MHz CPU; see
`cyberether/run/pmod-a-v6-watchdog-boot.json`. The flash and startup results
preserve the old v5 baseline but establish neither v6 RF transmission nor WDT
recovery.

v5 retains the bounded v4 controls and adds `QFRAMEBITS payload8` for encoder readback plus:

```text
QFRAME 8 500 120 165 12 335 670 1005
```

The arguments are channel, duration (50–500 ms), backoff (80–120 quarter-dB), payload byte, symbol period, and independent requests for +1/+2/+3 phase-state transitions. At 160 MHz the provisional requests are 335/670/1005 cycles. `QFRAME_CFG` returns the applied values, CPU clock, job and 64-symbol frame length. The frame has 32 training states, 22 K=7 coded QPSK symbols and 10 zero-state guards. Gray labels are `00→0`, `01→1`, `11→2`, `10→3`; state k ideally has phase −k·90°. The receiver needs a 54-symbol training-and-body span (32 training + 22 coded symbols); the 10 trailing guards need not fit in the capture.

## Physical QPSK runs

| Run | Symbol period | Captures | Acquired / CRC-valid frames | Acquisition / CRC failures | Coded errors / bits → payload errors / bits | Result |
|---|---:|---:|---:|---:|---:|---|
| QPSK-001 | 8 µs | 8 | 0 / 0 | 8 / — | — | Negative result: TX reported zero completed frames and 5,080 missed slots |
| QPSK-002 | 12 µs | 8 | 5 / 5 after receiver update | 3 / 0 | 0/220 → 0/40 | Original proof had four valid frames; blind offline reanalysis recovered five from the same raw captures |
| QPSK-003 | 10 µs | 16 | 12 / 6 | 4 / 6 | 112/528 → 19/96 | Six synchronized frames failed CRC; BER includes them |
| QPSK-004 | 12 µs | 32 | 21 / 21 | 11 / 0 | 0/924 → 0/168 | v5 baseline; kept as separate historical evidence |

### v6 RFS2 batches

These are separate new captures on v6, PMOD A → RFS2 channel 8, requested attenuation code 120, 16 MS/s; host performs synchronization and FEC. The exact `TX_ON` line is now acknowledged before the matching receiver capture. Attenuation code is not calibrated output power.

| Symbol period | Captures | Acquired | CRC pass / fail | No acquisition | Coded errors / bits → soft payload errors / bits | Notes |
|---:|---:|---:|---:|---:|---:|---|
| 8 µs | 32 | 0 | 0 / 0 | 32 | — (0 bits tested) | TX completed zero frames; BER is undefined, this is a timing failure |
| 9 µs | 32 | 30 | 23 / 7 | 2 | 171/1320 → 27/240 | Hard payload errors 21/240; no soft-FEC benefit claim |
| 10 µs CLI | 32 | 30 | 30 / 0 | 2 | 0/1320 → 0/240 | Finite batch only |
| 10 µs GUI | 4 | 5 frames | 3 / 2 | 0 | 35/220 → 6/40 | Two frames failed CRC within four captures; separate browser proof |
| 10 µs CLI + GUI | 36 | 35 | 33 / 2 | 2 | 35/1540 → 6/280 | Combined observed group; do not generalize from this small sample |
| 12 µs | 64 | 34 | 34 / 0 | 30 | 0/1496 → 0/272 | Best acquisition coverage remains limited; use as a finite result |

The four-capture 10 µs GUI run had an actual `TX_ON` acknowledgement for job 176, channel 8, attenuation code 120 and 500 ms. Its 3 CRC-valid frames and 2 failed frames are counted separately above. The independent saved-raw audit passes for all 172 unique v6 captures, including the four browser captures, with length/CRC/SHA and blind re-decode checks. Proofs are under `cyberether/run/rf-v6-{bpsk-rfs2-002,qpsk-8us-001,qpsk-9us-001,qpsk-10us-001,qpsk-12us-001}/proof.json`, `rf-v6-independent-audit/qualification.json` and `rf-link-20261021-222650-1792621610926103009/proof.json`.

QPSK-002's receiver update searches the 32-state training sequence without payload knowledge and decodes the 22-symbol body. It needs 54 total training/body symbols, not the trailing guards. The original and updated analyses share the same eight RF captures: use the updated decode result to assess receiver behavior, but count only eight captures as RF evidence. The QPSK-004 acquisition rate was 21/32. Its zero-error observation covers only 168 decoded payload bits; sparse capture gaps are unobserved.

The host harness supports a generated software preview or bounded physical capture. The 12 µs setting remains the CLI default; it is not a guarantee of capture or CRC success.

```bash
.venv-notebooks/bin/python scripts/check_rf_qpsk.py \
  --synthetic --output cyberether/run/qpsk-model

.venv-notebooks/bin/python scripts/check_rf_qpsk.py \
  --output cyberether/run/qpsk-rf --captures 32
```

The synthetic preview is not RF. Physical runs use the installed v6 probe and normal IQB1 hub; the checker does not flash devices. The 12 µs default is retained, while the 8, 9 and 10 µs results above remain separate. No operating point meets the 100,000-bit target. Automatic watchdog recovery still requires a deliberate hardware qualification.

## Extended RF audit

The historical audit and v6 captures are recursively aggregated in `ber-qualification/qualification.json`. Across 916 unique captures (744 historical plus 172 v6), all raw files passed length, CRC, SHA-256 and blind-redecode checks. The 164 v6 QPSK captures comprise the distinct timing groups above; their combined total and the historical aggregate mix payloads/settings and are not operating-point BER curves:

|Scope|Captures|Acquired|CRC pass / fail|No acquisition|Coded errors / bits|Payload errors / bits|
|---|---:|---:|---:|---:|---:|---:|
|New v6 QPSK captures|164|99|90 / 9|66|206 / 4356|33 / 792|
|Historical + v6 QPSK aggregate|488|262|243 / 19|227|406 / 11528|70 / 2096|


The aggregate is saved in `cyberether/run/ber-qualification/qualification.json`;
the independent v6 raw audit is in
`cyberether/run/rf-v6-independent-audit/qualification.json`. These totals include
capture attempts and decoder failures; they do not turn the repeated payloads
or settings into independent operating-point trials. Empty failed QPSK
configuration jobs are tracked separately and add no RF bits. The 100,000-bit
RF target at controlled operating points remains open.

## FPGA symbol/FEC replay

One QPSK-004 frame was replayed through checkpoint 06 using its 22 host-recovered symbols rotated −135° to match the FPGA map. The FPGA returned 0/44 coded errors → 0/8 payload errors with valid CRC. Kernel time was 3,100 cycles (62 µs at 50 MHz); the JTAG transaction took 68.328 seconds. Checkpoint 03 was restored afterward. This validates one symbol/FEC frame; it does not move raw-IQ carrier, timing or frame synchronization into FPGA. Replaying the saved frame adds no new RF evidence.

## What caused the four new CRC failures?

Read-only analysis retained every failure and used the saved measured symbols:

| Capture | Measured evidence | Interpretation |
|---|---|---|
| Extended `01-qpsk`, 62 | Body matches restarted training with 3.46° residual RMS after a linear phase fit | Restart near the end of training |
| Extended `03-qpsk`, 2 | All 22 body states exactly match last training state `2`, followed by `TRAINING[0:21]`; original training had zero symbol errors | Clear transmitted marker-restart signature |
| Extended `07-qpsk`, 5 | 19/22 body hard states match the same restart pattern; training has substantial phase/timing error | Restart plus timing/phase distortion |
| Extended `07-qpsk`, 37 | Body remains near +60° residual phase, with only 0.24°/symbol slope | Phase jump or training/timing bias; cause remains unresolved |

These are structured phase errors rather than an ordinary noise cloud. The
transmitter reported 86–89 missed slots over each affected 500 ms job; those
counters cannot identify the exact 1 ms snapshot. Test the v6 scheduling change
after v6 normal boot. If the remaining phase offset persists, investigate
training-fit robustness and add explicit tracking pilots before increasing
modulation order. Flash verification alone does not qualify v6 operation or
establish a BER improvement.

The local evidence is `cyberether/run/rf-qpsk-failure-diagnostic.json`: it records
raw SHA-256 identities, capture indices, training residuals, measured body states
and restart-template comparisons. Known payloads were used only for this
post-capture diagnosis. Live acquisition uses the fixed training sequence without
a payload oracle; no receiver code, original proofs or failure denominators were
changed by this analysis.

## Remaining QPSK gate

Accumulate at least 100,000 payload bits over independent physical captures and controlled operating points. Keep acquisition failures, CRC failures, hard/soft decoder outcomes and exact coded/payload denominators separate. The latest v6 batches remain small: 12 µs has 34 CRC-valid frames from 64 captures; 10 µs CLI has 30 from 32, while its separate GUI batch adds two CRC failures; 9 µs has seven CRC failures. The 8 µs batch completed no TX frames, so BER is undefined. These results do not qualify an RF BER curve, watchdog recovery or continuous link reliability.

For synthetic confidence bounds and BPSK RF auditing, see [BER qualification](BER_QUALIFICATION.md). For the full staged roadmap, see [BPSK to 64-QAM plan](RF_MODEM_BPSK_TO_64QAM_PLAN.md).
