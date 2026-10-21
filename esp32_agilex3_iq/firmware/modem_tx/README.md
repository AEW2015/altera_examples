# Modem TX firmware (ESP32-S3)

This new application wraps the pinned GPL-3.0-or-later `esp32-iq-tx` component with a finite, CRC-checked waveform loader. It starts with **RF uninitialized**. `INIT` explicitly prepares RF and can briefly emit a calibration CW; `START` is a separate command. No Wi-Fi networking runs concurrently with raw-IQ playback. The original ESP32 and C5 are not supported by this application.

Use `python scripts/modem_tx.py fetch` to download the pinned component, then build in its documented **ESP-IDF v5.3.5** environment:

```sh
idf.py -C firmware/modem_tx -B "$PWD/build-modem-tx-s3" \
  -DIDF_TARGET=esp32s3 -DSDKCONFIG="$PWD/build-modem-tx-s3/sdkconfig" build
```

The build wrapper added to `scripts/modem_tx.py` checks the resulting ELF against the reserved S3 RF SRAM aperture. Flash only after that check passes. Firmware source and an executable build are not evidence of RF qualification. Retain the upstream GPL license/provenance, and never reflash the installed original radios with this S3 image.

Default control/data transport is native USB Serial/JTAG; logs use that console too. The host ignores startup log lines until the expected protocol reply. A `menuconfig` option selects a dedicated 2 Mbaud UART1 with configurable pins (defaults43/44, verify exact board routing) for future PMOD operation. USB programming remains available. The existing IQ hub does not yet implement this TX command/upload path; use direct USB for initial qualification.

Protocol: `INFO`, `INIT <2.4GHz-channel> <backoff-qdb>`, `RATE <sample-rate-Hz>`, `LOAD <sample-count> <crc32-hex>` followed after `READY <byte-count>` by little-endian IQ10 words, `START`, `STOP`. Channel changes require reboot. Each word contains signed I10 in bits9:0 and signed Q10 in bits19:10; upper12bits must be zero. Load count must fit driver capacity and loop alignment. Partial/CRC-invalid loads disable subsequent START until a valid load. Stop before loading/rate changes.

The host uploader should validate waveform bounds and packing before opening serial, wait for exact acknowledgment/readback, and never start RF automatically after a load. Periodic hardware S31 playback is outside this S3 application’s initial scope.

Prefer the verified build wrapper: `python scripts/modem_tx.py build` after exporting the pinned SDK. `pyelftools` (provided by ESP-IDF's Python environment) checks ELF SRAM overlap. Build output records the component/SDK/PHY hashes and explicitly leaves hardware qualification false.

Example commands with a dedicated S3 and a known valid `waveform.bin`:

```sh
python scripts/modem_tx.py check --file waveform.bin  # offline packing/bounds
python scripts/modem_tx.py info --port /dev/your-s3
python scripts/modem_tx.py init --port /dev/your-s3 --channel 1 --backoff-qdb 100
python scripts/modem_tx.py upload --port /dev/your-s3 --file waveform.bin
python scripts/modem_tx.py start --port /dev/your-s3
python scripts/modem_tx.py stop --port /dev/your-s3
```

`INIT` and `START` access RF; uploads never call either automatically. `INFO` and upload proof read driver state and CRC acknowledged after the memory-copy operation; they are not an independent RF or physical-SRAM readback measurement.

SDK bootstrap when v5.3.5 is not already installed: clone Espressif ESP-IDF tag `v5.3.5` with recursive submodules into `vendor/esp-idf-modem-tx`, verify commit `0c45a102a96e82000f145b786a20de229b9f8557`, run its `install.sh esp32s3` outside another Python venv, then source its `export.sh`. Use separate SDK/setup directories from the installed original ESP32 firmware.
