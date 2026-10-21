# QPSK qualification on the installed original ESP32

The installed PMOD A original ESP32 now runs verified v5 firmware and has transmitted framed phase-pulse QPSK recovered by RFS2. At 12 µs symbols, the latest batch recovered 21 valid frames from 32 new captures with no CRC failures; 11 captures failed acquisition. Its 0/168 payload-bit result is preliminary, far below the 100,000-bit BER target. Four-state phase control and the BPSK regression also passed.

This remains a bounded scalar NCO phase-pulse link. It does not provide arbitrary Cartesian IQ playback or FPGA raw-waveform synchronization. The host still performs carrier/timing/frame recovery and FEC; Agilex transports captures and separately processes recovered symbols in checkpoint 06.

## Phase-state gate

The four-state gate used v4 `FASTPHASE` on PMOD A, RFS2 at channel 8 / 2447 MHz, 16 MS/s, manual gain 0, 160 MHz CPU, step 3, pattern `165` (`0xA5`) and 32 µs symbols. The 335-cycle quarter-turn case qualified in 3/3 captures with balanced clusters roughly 90° apart. The zero-pulse CW controls (0/3) and 670-cycle antipodal BPSK controls (0/3) correctly failed four-state qualification. The proof and raw capture hashes are at `cyberether/run/phase-qpsk-gate-001/four-state-proof.json`.

To repeat on the currently installed v4 phase-control probe and runtime hub:

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
| QPSK-004 | 12 µs | 32 | 21 / 21 | 11 / 0 | 0/924 → 0/168 | Latest new batch; this is now the CLI default |

QPSK-002's receiver update searches the 32-state training sequence without payload knowledge and decodes the 22-symbol body. It needs 54 total training/body symbols, not the trailing guards. The original and updated analyses share the same eight RF captures: use the updated decode result to assess receiver behavior, but count only eight captures as RF evidence. The QPSK-004 acquisition rate was 21/32. Its zero-error observation covers only 168 decoded payload bits; sparse capture gaps are unobserved.

The host harness supports a generated software preview or bounded physical capture:

```bash
.venv-notebooks/bin/python scripts/check_rf_qpsk.py \
  --synthetic --output cyberether/run/qpsk-model

.venv-notebooks/bin/python scripts/check_rf_qpsk.py \
  --output cyberether/run/qpsk-rf --captures 32
```

The synthetic preview is not RF. Physical runs require installed v5 and the normal IQB1 hub; the checker does not flash devices. The 12 µs default reflects the current best measured acquisition setting, while 8 and 10 µs failures remain part of the evidence.

## FPGA symbol/FEC replay

One QPSK-004 frame was replayed through checkpoint 06 using its 22 host-recovered symbols rotated −135° to match the FPGA map. The FPGA returned 0/44 coded errors → 0/8 payload errors with valid CRC. Kernel time was 3,100 cycles (62 µs at 50 MHz); the JTAG transaction took 68.328 seconds. Checkpoint 03 was restored afterward. This validates one symbol/FEC frame; it does not move raw-IQ carrier, timing or frame synchronization into FPGA. Replaying the saved frame adds no new RF evidence.

## Remaining QPSK gate

Accumulate at least 100,000 payload bits over independent physical captures and controlled operating points. Keep acquisition failures, CRC failures, hard/soft decoder outcomes and exact coded/payload denominators separate. The latest 12 µs run has only 168 payload bits and 11 acquisition failures from 32 captures, so it demonstrates a working framed path but does not qualify an RF BER curve or continuous link reliability.

For synthetic confidence bounds and BPSK RF auditing, see [BER qualification](BER_QUALIFICATION.md). For the full staged roadmap, see [BPSK to 64-QAM plan](RF_MODEM_BPSK_TO_64QAM_PLAN.md).
