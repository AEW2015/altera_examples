# Modem Lab · BPSK to 64-QAM

Modem Lab is a local teaching tool for constellation mapping, impairments, synchronization, soft decisions and bit-error counting. Its browser page uses the Python reference receiver and labels its results **Python simulation**. The current UI does not open a radio, use FPGA capture data, or claim an RF measurement. **RF transmit qualification is blocked:** only the original ESP32 modules are installed, and none has a qualified arbitrary-IQ playback path. The separate FPGA symbol-level backend can still be simulated and built.

## Start the browser lab

From the example root, with the notebook environment installed:

```bash
.venv-notebooks/bin/python cyberether/modem_lab.py --open
```

Open `http://127.0.0.1:8769/` if the browser does not open. To reach the page from another machine, bind to the LAN with `.venv-notebooks/bin/python cyberether/modem_lab.py --host 0.0.0.0` and connect to the host's reachable LAN address on port 8769. The server prints localhost when `--open` is used with a wildcard bind; use the LAN address in the remote browser. Stop the server with Ctrl+C.

Choose BPSK, QPSK, 16-QAM or 64-QAM, adjust SNR, carrier offset, timing offset and optional two-path multipath, then run a burst. The seed makes the payload and impairment noise repeatable. The page shows the ideal mapped points, oversampled raw samples, recovered symbols, eye traces and simulated spectrum. It reports acquisition/header/CRC state, normalized RMS EVM, pre-FEC coded errors, and hard/soft FEC payload errors with their tested bit counts.

## Read the evidence

- **Raw IQ** is oversampled input to the software receiver. Its points are not symbol decisions.
- **Recovered symbols** come from the simulated synchronization/equalization path and are compared with known transmitted symbols to calculate EVM.
- **Pre-FEC BER** counts coded bits before the decoder. Hard and soft post-FEC counts measure the decoded payload over the same seeded channel run.
- **Zero errors** means no errors among the displayed tested bits. It is not a claim that the true BER is zero.
- **Run ID and seed** identify a reproducible software result. The capture ID, FPGA image and RF timestamp fields are explicitly absent.

The known payload is used to measure errors and EVM. It does not replace received decisions. The controls change the software channel only; no control is applied to hardware. This UI never reports a real capture ID, FPGA image or RF timestamp.

## Optional FPGA symbol loopback

The FPGA panel is disabled by default. To expose its manual action, start the same page with:

```bash
.venv-notebooks/bin/python cyberether/modem_lab.py --open --enable-fpga-action
```

This flag does not open JTAG. The service first checks that the active image manifest names checkpoint 06 and that its recorded SOF file SHA matches the successful build and local SOF file. That is a manifest/file check, not a readback of the full image from the device; the manual action separately reads and verifies modem block ID `0x4d440601`. It also refuses to act while a matching CyberEther viewer, Nios/JTAG owner or active rate monitor is present. It never stops or replaces an existing process. Only after clicking **Run FPGA symbol loopback** and accepting the browser prompt does it create a `NiosFir` owner with monitor pausing disabled, then pass that owner to `ModemFPGA`.

The test sends 128 seeded information bits through the FPGA encoder/mapper, then deliberately changes one nearest-neighbor symbol before the FPGA max-log demapper and soft Viterbi. It checks the encoder and mapper against independent references, compares fixed-point max-log values and raw error counts, and verifies that FEC recovers the original payload. The result carries the checkpoint tag, manifest-selected SOF file SHA, modem block ID readback, measured FPGA encode/decode cycles, coded/decoded error counts and independent reference comparisons. It reports symbol-rate RTL evidence only. The Python waveform synchronizer is not part of this result, and no RF transmitter, radio capture, EVM or RF BER is claimed. If an existing owner is already available in an embedding application, pass that owner to `run_fpga_symbol_test(owner, body, checkpoint)`; the helper does not open or close it.

The normal notebook launch leaves this optional action disabled. The notebook starts the service on `0.0.0.0` for LAN access and prints `lan_ip()` as the suggested browser URL. Its offline model cells and default browser controls do not touch hardware.

## Python reference

`cyberether/modem_reference.py` contains the numerical reference functions. From the example's Python environment:

```python
from cyberether.modem_reference import run_experiment
result = run_experiment(
    modulation="16QAM", snr_db=18, cfo_hz=1500,
    timing_offset=0.25, multipath=False, seed=7,
    payload_bits=2048, decode_mode="soft",
)
print(result["metrics"])
```

Notebook [08 · Modem Lab](../notebooks/08_modem_lab.ipynb) walks through the same model, includes the saved native VDS GUI export, and starts the browser page. Its Questa simulation, VDS generation and SOF build cells call the actual tool functions with progress, behind default-false switches. The offline Python cells do not require Quartus, a board, an ESP32 or RF hardware.

## FPGA simulation and build

The separate RTL checkpoint is **06 · modem symbol path**. The implemented boundary is symbol-level encoding/mapping, soft demapping and FEC. Waveform-level RRC shaping, carrier/timing acquisition and equalization remain Python reference work until matching RTL exists. The board inventory has only original ESP32 TX/RX candidates, so arbitrary-IQ RF transmit qualification is currently unavailable. Consult the generated command help and RTL checkpoint README for exact source files and simulator options:

Run the actual RTL assertions in Questa, generate the native VDS project, or build its SOF with these commands:

```bash
.venv-notebooks/bin/python scripts/simulate_modem.py       # actual RTL simulation; no board access
.venv-notebooks/bin/python scripts/simulate_modem.py --gui  # open the saved Questa waveform
.venv-notebooks/bin/python scripts/modem_fpga.py generate   # generate VDS and complete project
.venv-notebooks/bin/python scripts/modem_fpga.py build      # Quartus compile; no programming
```

The matching convenience command `.venv-notebooks/bin/python scripts/modem_fpga.py simulate` runs the RTL simulation. For options and tool discovery, use `--help` on either script.

These commands are for local simulation/design generation/build. They do not program the FPGA or flash a radio. The Python UI remains a reference even after the RTL checkpoint builds. An FPGA or RF result must be collected and labeled through an independent evidence path before the UI can claim hardware provenance.

Notebook 08 has a separate checkpoint programming cell, guarded by `RUN_PROGRAM_MODEM = False`. The explicit `program()` call checks the source fingerprint and image SHA against `BUILD_RESULT.json`, stops only this checkout's recorded notebook demo, refuses remaining serial/JTAG owners, and uses `ATUM_JTAG_CABLE`. Running that cell replaces the active FPGA design; it is outside the default Run All path and does not flash or reset an ESP32.
