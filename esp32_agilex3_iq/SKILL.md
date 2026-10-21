---
name: atum-a3-iq-lab
description: Build, explain, simulate and run this repository's ESP32 SDR, Atum A3 Nano Agilex 3 FPGA, Nios V and CyberEther lessons, including firmware programming and RF Arcade.
---

# Atum A3 IQ lab

Work from the directory containing this file. Commands run **beside installed Quartus/Questa tools**, on a Linux host or inside a desktop container. Do not hardcode Docker, another checkout, `/home/dev`, or a particular tool installation into new source. `scripts/common.py` discovers tools and the repository root. Respect the user's existing authorization and current hardware wiring.

## Choose the workflow

- Lesson overview, tool install and board pins: [README.md](README.md).
- FPGA, RF Arcade and offline firmware notebooks: [notebooks/README.md](notebooks/README.md). Edit `scripts/make_notebooks.py` when changing authored lesson content, then regenerate the notebooks. Preserve existing cell IDs and keep live tokens/captures out of outputs. Each introduction explains **what is added, why it is useful and how it is implemented**.
- Notebook progress: `scripts/notebook_progress.py` provides plain-HTML activity bars and elapsed time without widgets. Long `Lesson` methods use `@task`; authored Python model cells use `with progress(...)`. Keep percentages indeterminate unless the tool supplies a reliable total.
- Native Quartus VDS: [docs/VDS_WALKTHROUGH.md](docs/VDS_WALKTHROUGH.md). Checkpoint construction/connection Tcl is the editable source of truth; `src/vds/` and vendor HDL are generated. `lesson.generate()` exports the **actual VDS GUI** PDF/PNG. Graphviz topology is a separate optional aid.
- Complete Quartus projects: after generation/build, `scripts/quartus_project.py` packages the QPF/QSF, explicit SDC, system and leaf-IP QIPs, generated HDL and Nios initialization HEX. Notebook output links to the prepared QPF and full ZIP. Keep the diagram-export project complete too; copying only QPF/QSF omits constraints. `scripts/quartus_project.py all --verify` checks extracted builds without accessing hardware.
- CPU software: [software/README.md](software/README.md). `scripts/nios_software.py 2 --open` generates the official HAL BSP/apps and opens RiscFree; checkpoints 2–5 contain Nios V. Keep the JTAG UART driver polled, because the monitor owns the command FIFO directly. `scripts/nios_download.py` checks the active checkpoint and resolves the target cable.
- ESP32 builds, wiring and flash: [docs/ESP32_FIRMWARE.md](docs/ESP32_FIRMWARE.md). Source is `unified/`; SDK/upstream commits are pinned in `scripts/fetch.py`. RFS2 uses application UART GPIO1/3; Digilent Pmods use GPIO17/16 but their ROM loader uses J2 GPIO1/3. Use the correct build profile. Firmware is GPLv3-derived; retain `unified/LICENSE.ESP-SDR` and notices.
- FIR examples and custom taps: [docs/FIR_FILTER_LIBRARY.md](docs/FIR_FILTER_LIBRARY.md). Use `fir_controls.FIRControls` through the existing acquisition owner; never create a second UART/JTAG client. Selecting or previewing a GUI example does not apply it; use the explicit Apply button and require matching readback/reference evidence. FIR test tones are −0.5/+4 MHz; DDC test tones are +0.5/+6 MHz at 16 MS/s.
- Original ESP32 TX probe: [firmware/esp32_tx_probe/README.md](firmware/esp32_tx_probe/README.md). Build separately with `scripts/build_tx_probe.sh`; explicit bounded CW jobs only. Preserve the chosen radio flash privately, restore the runtime FPGA hub before normal boot, and qualify RF using a different receiver. The tone test does not qualify arbitrary IQ.
- Modem Lab: [docs/MODEM_LAB.md](docs/MODEM_LAB.md) and [docs/MODEM_IMPLEMENTATION_STATUS.md](docs/MODEM_IMPLEMENTATION_STATUS.md). Notebook08 has the Python waveform reference and separate checkpoint06 symbol/FEC actions. Legacy `Lesson` remains checkpoints01–05; use `scripts/modem_fpga.py` for06. Never label Python synchronization as FPGA or original-ESP32 tone TX as arbitrary IQ. Original-chip TX evidence is in [docs/ESP32_TX_INVESTIGATION.md](docs/ESP32_TX_INVESTIGATION.md).
- Presentation: [docs/RF_ARCADE.md](docs/RF_ARCADE.md). `scripts/demo_night.py --host <reachable-IP>` uses checkpoint 5; it is part of this branch, not an external demo.

## Hardware distinctions that matter

The board is **Atum A3 Nano / Agilex 3 / A3CZ135BB18AE7S**, 50 MHz. Radio 0 is RFS2 ESP32, radio 1 is PMOD A ESP32, radio 2 is PMOD B ESP32. Do not label it Agilex 5. Reference the current QSF/bridge wiring rather than guessing connector orientation.

One board image and acquisition owner are shared. A ROM programmer image contains no DSP or Nios and replaces the active lesson design. It must isolate inactive UARTs and drive GPIO0 only low or high-Z. A runtime lesson must be restored after flashing. The Pmod ROM requires a manual reset while GPIO0 is low; normal boot requires release and another reset. Do not claim a button press, target identity, flash or hardware test occurred without evidence. Adding a programmer utility does not itself call for reflashing working radios.

Use `flash_esp32.py --dry-run` while developing packaging. Actual flash commands use the IDF flash manifest, check the RFS2/Pmod pin profile, reject busy serial ports and optionally verify `--expect-mac`. The normal IQB1 hub is not a transparent ROM flashing bridge. Do not replace the current wiring with temporary J1-to-J2 jumpers when the direct RFS2 JP1-to-Pmod J2 wiring is installed.

## Explain the signal honestly

ESP32 delivers sparse CI8 IQ bursts over UART. These receivers are not calibrated general-purpose SDRs or coherent angle-of-arrival sensors. Receipt timestamps do not establish RF sample phase alignment. Original-ESP32 Wi-Fi acquisition covers 2.4 GHz, not 5 GHz.

Agilex 3 performs FIR, NCO/complex mixing, filtering/decimation, gain and integer power/peak/clip metering. Host Python transports data, verifies an independent integer reference and calculates display FFT/logarithms. IQ scatter is not recovered Wi-Fi/QPSK symbols. Distinguish real RF from FPGA-generated clean patterns and compiled FPGA allocation from live activity. No SSID/header decoder is part of these five checkpoints.

## Validate and report

- Host tests: `.venv-notebooks/bin/python -m unittest discover -s cyberether/tests -q`.
- Firmware: `bash scripts/build_firmware.sh rfs2` and `bash scripts/build_firmware.sh pmod`; separate output directories avoid mixing application UART pins. Shared SDK installation is locked; do not bypass that by installing the SDK concurrently.
- Programmer routing simulation: `.venv-notebooks/bin/python scripts/esp32_bridge.py pmod-a --simulate` tests all six routes and GPIO0 release behavior. Building a bridge does not load it; `--load` does.
- FPGA lesson build/simulation/program commands are in the notebook and README. Reuse an SOF only when its source fingerprint and image SHA match; do not equate successful compilation with hardware qualification.
- Record relevant results in [VALIDATION.md](VALIDATION.md), with the tested image/profile and practical limits. Generated databases, SDKs, BSPs, binaries, credentials and live invitation tokens stay ignored. Publish source and reproducible scripts; retain the saved, non-sensitive diagram PNGs.
