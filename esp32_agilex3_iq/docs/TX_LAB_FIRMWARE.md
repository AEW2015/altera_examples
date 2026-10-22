# One PMOD A TX image

Build `bash scripts/build_tx_lab.sh` with the pinned ESP-IDF SDK available through
`ATUM_ESP_IDF`. Building does not flash or transmit. Install on PMOD A only using
the existing ROM bridge/reset workflow, then restore checkpoint11 and its capture app.
RFS2 and PMOD B keep their existing firmware.

| Software mode | Commands retained | Purpose |
|---|---|---|
| AMP | INFO, STATE, STOP, CONTROL, ATTEN, LEVEL, TRAIN | Measured attenuation and repeated amplitude transitions |
| NATIVE | INFO, STATUS, CONFIG, CONFIG?, ARM, START, STOP | Native Wi-Fi 54 Mb/s / 64-QAM packet experiment |
| PHASE | INFO, STATE, STOP, PHASECAP, PHASESTAT, TONE, NCO, PHASE, FASTPHASE, FRAME, QFRAME, FRAMEBITS, QFRAMEBITS | Scalar carrier/phase and experimental BPSK/QPSK frames |

Use the existing experiment scripts after choosing the matching mode:

```sh
python scripts/tx_lab_control.py --mode AMP
python scripts/tx_lab_control.py --mode NATIVE
python scripts/tx_lab_control.py --mode PHASE
python scripts/tx_lab_control.py   # query only
```

The controller stops any job, requires quiet readback, requests a software restart,
and verifies the new mode and RF-off readiness. No reset button or flash is needed
for these mode changes. The FPGA image stays loaded. Each selected mode starts with
RF off; it never resumes an armed or active job. Cold boot, watchdog and panic reset
default to AMP. Only the explicit software mode change carries a selection through
RTC RAM, consumed on boot. The 2.1-second startup pause also enforces a mode-change
cooldown. Native and certification PHY contexts are separated by reboot.

AMP retains 3–50 ms jobs and a two-second cooldown. PHASE in this combined image
uses 50 ms jobs (the legacy parser minimum and the combined profile maximum) and requires backoff >=96 quarter-dB units; it adds a
repeated software deadline guard and a two-second cooldown. Native retains its
100 ms job deadline, bounded packet count and two-second cooldown. These are
software guards, not a verified hardware RF cutoff. All RF experiments remain
explicit actions, never startup actions. Stop and inspect after unexpected output.

The same source modules also build independently. The unified profile selects
the extra mode dispatcher and PHASE limits at compile time. Both certification
workers have 8 KiB stacks; build checks reject a local worker frame above 512 B.
Runtime stack headroom and real RF behavior still require hardware measurements.

This packages existing controls; it does not prove arbitrary Cartesian IQ playback
or custom 64-QAM RF transmission on an original ESP32. Additional firmware features
could still require a future installation, but switching these three experiments
and varying their exposed parameters does not.


## Unattended test batch

```sh
python scripts/tx_lab_soak.py --hours 3 --interval-minutes 20 --transmit \
  --output cyberether/run/tx-lab-soak-NEW
```

The output directory must be new. The batch changes modes without programming,
records sparse raw amplitude snapshots and checks two native Wi-Fi packets per
round through PMOD B. It leaves TX off between rounds and stops on the first
failed check. PHASE is exercised through software mode selection only; this batch
does not qualify received QPSK/64-QAM, constellation quality or BER. Each round has
at most 80 ms of requested amplitude jobs plus the native 100 ms job deadline;
PHY setup/shutdown and software deadlines are not a measured hardware RF cutoff.

The host accepts a missed startup announcement only when a fresh mode/quiet
readback succeeds. A switch that returns to the RF-off AMP fallback is retried
once; a repeated failure stops the batch. Mode transitions after certification
PHY use need this recovery path on the installed image; the reset cause has not
been isolated. No new flash or physical reset is performed by the runner.

Long PHASE startup/INFO messages and some TX acknowledgements were missed during
hardware checks. Saved short QFRAME telemetry includes configuration and TX_OFF,
but that attempt lacks TX_ON and is not accepted as an RF frame qualification.
The longer batch therefore excludes PHASE transmission.

The next calibration stage is described in
[Incremental amplitude calibration](TX_LAB_CALIBRATION.md). The stage11 text
transport update expands the old127-byte/single-line buffer to255 bytes and four
pending lines per radio, with whole-line overflow counts. This addresses missing
PHASE INFO/READY and back-to-back configuration/TX_ON messages. It changes FPGA
transport RTL; the ESP32 firmware stays installed. RTL simulation must pass and
the rebuilt SOF must pass fit/timing before hardware checks and calibration resume.
