# Five local FPGA lessons

Run Jupyter **where Quartus and Questa are installed**: a Linux host or a container desktop. All build, simulation, programming and viewer commands run directly in that environment. A browser can connect remotely.

```text
Python model → VDS topology → Questa waveform → SOF → Atum A3 Nano → CyberEther
```

| Open in order | Python model | Actual simulator test | Live page |
|---|---|---|---|
| [01 Raw IQ](01_raw_iq_bridge.ipynb) | CI8 waveform, scatter, FFT | UART TX/RX binary loopback | Real ESP32 burst |
| [02 Nios monitor](02_nios_transfer_monitor.ipynb) | Event counts and rates | All 16 counter windows, totals, coherent CSR snapshot | Live UART/payload rates |
| [03 FIR](03_fir_filter.ipynb) | Convolution and Q15 rounding | Generated FIR II + capture controller | Boxcar / Hamming |
| [04 DDC](04_ddc_frequency_translation.ipynb) | Mixing, filtering, aliasing | Generated I/Q FIR II + DDC RTL | Shift / filter / decimate |
| [05 Gain](05_gain_power_meters.ipynb) | Gain, saturation, power | Gain/meter RTL, exact integer assertions | Gain / power / clips |

## Install once

From the example root:

```bash
# Optional for tools not found on PATH or under /opt/altera:
export QUARTUS_ROOTDIR=/your/install/quartus
export QUESTA_ROOT=/your/install/questa_fse
export ATUM_ALTERA_ROOT=/your/install
# Keep the DISPLAY of your working desktop.
bash scripts/install_local.sh --system
.venv-notebooks/bin/python scripts/check_tools.py
.venv-notebooks/bin/jupyter lab notebooks --no-browser
```

Use your actual installation paths; omit the three exports for the standard installation. `--system` installs Debian/Ubuntu prerequisites through sudo. Omit it when dependencies are present. The installer creates `.venv-notebooks`, registers **Atum A3 IQ Demos**, downloads the pinned CyberEther runtime and builds its registration shim. Quartus, device support, Questa and the Nios toolchain must already be installed/licensed.

In VS Code select **Select Kernel → Python Environments → .venv-notebooks/bin/python** if the named Jupyter kernel does not appear. Open the folder in the same host/container environment where this venv was created; environments are not portable between them.

On this rig, the host has the stable by-id UART link; the current container exposes the same board as `/dev/ttyUSB0`. Set `export ATUM_UART=/dev/ttyUSB0` before starting Jupyter there, or set it in the configuration cell.

For a remote browser add `--ip=0.0.0.0`; use the Jupyter token printed in the terminal. Container users also need its ports reachable from the host. CyberEther uses 8687/8768 and TCP 40100–40103 by default. Set the notebook's `HOST` to the reachable host/container IP if automatic discovery returns an internal address.

## Demo sequence

1. Open notebook 01 and select **Atum A3 IQ Demos**.
2. Check the paths, board UART and JTAG cable in its configuration cell.
3. Run the Python model, then generate the native VDS design. Its PNG/SVG is rendered from actual Quartus-exported connections, with clock/reset fanout hidden.
4. Run the assertion-based RTL simulation and inspect its plot. The next cell prints commands to open the saved waveform in the Questa GUI.
5. Build and program. A fresh checkout performs a full compile. Later runs reuse only a source-matched, SHA-verified SOF; use `FORCE_REBUILD=True` for a fresh compile.
6. Open the focused CyberEther link printed by the final cell. Leave it running while presenting.
7. Run the next notebook. Programming stops the previous notebook-owned demo before replacing the board image.

Stop unrelated board acquisition services first. One physical board runs one checkpoint at a time. Existing compatible ESP32 firmware needs no reset-button presses; notebooks do not flash the radios.

The simulations test the named RTL/IP, not a complete Wi-Fi receiver or Nios instruction execution. Real DSP runs on the FPGA; the host handles transport, independent reference checks, plotting and display FFT. The final two lessons use FPGA-generated clean signals without RF transmission.

Generated diagrams, simulation waves, builds and captures remain under each checkpoint's ignored `results/` and `run/` directories. Live invitation tokens stay in ignored runtime files. Authored notebooks contain no tokens or captured network data.
