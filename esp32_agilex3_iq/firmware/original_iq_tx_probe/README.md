# Original ESP32 attenuation probe

**V1 stable amplitude changes measured. V2 failed PHY-init stack testing; V3
fix built, not installed. No
arbitrary-IQ playback or QAM qualification.** This
separate original-chip image tests the next amplitude-control hypothesis from
[the research gate](../../docs/ORIGINAL_IQ_TX_RESEARCH_20261021.md). Existing v6
and native Wi-Fi firmware remain separate.

```text
CONTROL 30        unchanged-code control, <=30 ms requested setup/job deadline
ATTEN 120 30      baseline → trial code 120 → baseline, same deadline
STOP             immediate known tone-enable clearing; worker performs API stop
STATE            original tone-register readback (does not initialize RF)
INFO             identity of this diagnostic and busy state
LEVEL 24 50      v2: explicit code0..127 with the same three slow plateaus
TRAIN 24 30 32   v2: repeat baseline/trial at requested32us period, <=30ms budget
```

No RF command should be sent until guided installation and independent receiver
acquisition are prepared. The build helper records image hashes but never flashes
or transmits. The programmer now accepts this image **only on PMOD A**, with
the explicit diagnostic, certification and unicore flags and UART17/16 checked.

## What it changes

Uses the proven original-chip SDK certification initialization, channel 8 / 2447 MHz,
backoff command 120, UART0 GPIO17/16 at 2 Mbaud, unicore profile. Startup leaves RF
uninitialized. `CONTROL` leaves the readback baseline attenuation unchanged;
`ATTEN` accepts only trial codes 120..127. These are **uncalibrated codes**, not
output power or a known dB scale. Direction, settling and AM/PM need measurement.

V1 independent RF captures now show reproducible baseline RMS96–97ADC units
versus4.20–4.25 for code120, with TX-off1.05–1.12 at manual RX gain0 and no rail
hits. That is about27.18dB total ADC power difference, not a calibrated RF gain
law. Code121 was4.37; one nearby-code observation does not establish monotonicity
or usable fine steps. See [measured results](../../docs/ORIGINAL_IQ_AMPLITUDE_RESULTS.md).

V2 retains ATTEN120..127 and adds LEVEL/TRAIN0..127. It reports `v=2,amp_train=1`.
Its initial worker stack overflowed on hardware; do not qualify that image.
V3 reports `v=3,amp_train=1`, moves traces to static RAM, uses an8192-byte worker
stack and emits INFO stack_min plus an after-job STACK row. Build-time compiler
frame checks require the worker frame to be static and <=512bytes; the compiled
V3 frame is384bytes. Vendor call-tree depth still needs measured runtime margin.
TRAIN alternates only attenuation, saves the first16 register-edge timestamps,
and reports edge count and maximum software lateness. It deliberately yields
every32 edges so STOP and the guard can run. These scheduling gaps are part of
the experiment: this is not a uniform sample-clock or FPGA-timed waveform.
Its purpose is to capture multiple transitions within one raw-RX snapshot and
measure settling/phase disturbance. It is not a QAM modem or SRAM playback.

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
See [the execution plan](../../docs/CUSTOM_QAM_EXECUTION_PLAN.md) for the current
programmer integration and one-job transport controller. Installing this image
does not establish original-chip arbitrary-IQ transmission.
