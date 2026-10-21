# Original ESP32 TX probe

First hardware gate for the modem experiment: prove carrier transmission and a
clean stop on the installed original ESP32. This is **CW only**, not arbitrary IQ
playback, BPSK or QAM. It uses Espressif's `esp_phy_cert_test.h` API and does not
write guessed S3 playback registers.

The separate image is for a Digilent Pmod ESP32: application UART TX/RX GPIO17/16
at 2 Mbaud, bootloader J2 GPIO1/3. Leave the two switches OFF as in the project's
existing UART/programmer setup. RF is not initialized at boot. Each explicit job
has a 50–3000 ms deadline, channel 1–11, and 80–120 quarter-dB attenuation
(20–30 dB relative vendor backoff, **not calibrated output power**). The worker
checks STOP/deadline every 5 ms after the vendor tone call returns. A firmware
hang is not an independently timed RF shutdown guarantee.

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
| `INFO` | Identity, chip revision, MAC, pins, busy state; no RF initialization |
| `TONE 3 3000 96` | Channel 3, maximum 3 seconds, 24 dB vendor power backoff |
| `STOP` | Request cancellation; wait for `TX_OFF` to establish completion |

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
mode. That is a source-derived prediction until an independent RF sweep passes.
There is no phase argument and no Cartesian I/Q injection in this interface.
[Evidence and exact offline model](../../docs/ESP32_NCO_PROBE_EVIDENCE.md).

After explicitly installing v2 and restoring the FPGA hub:

```bash
.venv-notebooks/bin/python scripts/check_esp32_nco.py \
  --port /dev/ttyUSB0 --output cyberether/run/nco-new
```

The checker rejects v1, captures seven raw step settings, checks mode/gain/enable
and step readback, checks restoration, and compares measured RF frequency shifts
with the nominal grid. The plots use host FFTs. Until measured successfully,
**v2 NCO control is built software, not qualified RF operation**.
