# Original ESP32 attenuation probe — compile only

**Not installed or RF-qualified. No arbitrary-IQ playback or QAM claim.** This
separate original-chip image tests the next amplitude-control hypothesis from
[the research gate](../../docs/ORIGINAL_IQ_TX_RESEARCH_20261021.md). Existing v6
and native Wi-Fi firmware remain separate.

```text
CONTROL 30        unchanged-code control, <=30 ms requested setup/job deadline
ATTEN 120 30      baseline → trial code 120 → baseline, same deadline
STOP             immediate known tone-enable clearing; worker performs API stop
STATE            original tone-register readback (does not initialize RF)
INFO             identity of this diagnostic and busy state
```

No command should be sent to hardware until a future explicit guided install
and independent receiver acquisition are prepared. The current build helper
**does not** register the image with the programmer or flash it.

## What it changes

Uses the proven original-chip SDK certification initialization, channel 8 / 2447 MHz,
backoff command 120, UART0 GPIO17/16 at 2 Mbaud, unicore profile. Startup leaves RF
uninitialized. `CONTROL` leaves the readback baseline attenuation unchanged;
`ATTEN` accepts only trial codes 120..127. These are **uncalibrated codes**, not
output power or a known dB scale. Direction, settling and AM/PM need measurement.

Three plateaus share the time remaining **after setup**, within a requested
3..50 ms job deadline. The start timestamp precedes PHY/TX calls, so setup consumes
that budget. The first initialization is expected to consume much or all of
a 50 ms job: a cancelled first attempt is not RF success. After cleanup and
the two-second quiet period, a later explicitly requested bounded CONTROL can
exercise the initialized path. There is no unbounded RF warmup command. A high-priority 1 ms guard repeatedly clears the **known original-chip
tone-enable fields** when STOP/deadline occurs, without waiting on a vendor API
mutex. Worker cleanup restores saved **attenuation bits only**, retaining the
disabled enables, calls the known vendor stop routines and enforces 2 s quiet.

Trial/return readbacks require all other tone1 fields, tone2 and extension to
match the baseline. `BASELINE`, `TRIAL`, `RETURN`, `RESTORED`, `OFF` preserve raw
readbacks. Baseline/trial/return registers and timestamps are buffered in RAM;
all job telemetry is formatted and emitted only after tone clearing and vendor
stop. Every output row is globally serialized and spaced by at least 2 ms,
including INFO/IDENT and OFF/DONE, to avoid the bridge text queue dropping rows.
Do not poll unrelated commands during an amplitude measurement.

`TIMING` reports setup and the observed register interval from tone
API return to clearing; it is **not an independent measurement of RF duration**.
`EDGES` reports actual software scheduling, not precise RF edges. `DONE` records
restoration and tone-enable readback; it does not certify external RF-off.

This is a software guard. A blocking PHY API can hang, delay cleanup or re-key
hardware after a guard clear. Repeated register clearing and the 5 s watchdog
recovery policy are not an independently proven 50 ms RF cut-off. Hardware
qualification must measure these failure cases before relying on this image.

## Build and offline checks

Run beside the pinned SDK/tools, locally or in a container:

```bash
export ATUM_ESP_IDF=/path/to/pinned/esp-idf-sdr
# Set IDF_TOOLS_PATH to that SDK's installed tools if not the default.
bash scripts/build_original_iq_probe.sh
.venv-notebooks/bin/python -m unittest cyberether.tests.test_original_iq_probe -v
```

App project: `atum_original_iq_tx_probe`. Output:
`build-original-iq-tx-probe/atum_original_iq_tx_probe.bin`.
No automatic NVS erase fallback. A future install needs the existing PMOD A
manual reset sequence, preserved backup and programmer whitelist/profile support.
No programmer change is included here.
