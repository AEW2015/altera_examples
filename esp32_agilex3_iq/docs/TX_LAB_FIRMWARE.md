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
accepts at most 50 ms and requires backoff >=96 quarter-dB units; it adds a
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
