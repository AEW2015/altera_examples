# Checkpoint 06: buffered FPGA modulation and FEC

This separate native Visual Designer Studio project extends checkpoint 05 with a
Nios-controlled **symbol-rate modem accelerator**. Existing notebooks 01–05 and
RF Arcade keep their original image selection.

```text
Nios V / JTAG UART
        │ Avalon-MM at 0x10060000
        ▼
Input bit RAM → K=7 rate-1/2 convolutional encoder → Gray BPSK/QPSK/16/64-QAM
                                                          │
                                                 CI16 symbol RAM
                                                          │
                            max-log soft demapper → terminated soft Viterbi
                                                          │
                                            decoded RAM / BER counters
```

All blocks shown inside the accelerator execute in RTL. Host Python uploads
vectors and compares independent results. The existing FIR II, NCO/DDC and gain
blocks remain in the same VDS design. **The modem is not yet wired as a complete
raw-RF receiver:** frame detection, RRC pulse shaping/matched filtering, symbol
timing recovery, carrier tracking and equalization are reference-model stages.
CI16 uploaded to this accelerator must already be symbol aligned, carrier
corrected and normalized. The FPGA symbol RAM is not an ESP32 TX playback API.

## Build and simulate where Quartus tools are installed

From the example root, using the notebook venv:

```bash
.venv-notebooks/bin/python scripts/simulate_modem.py
.venv-notebooks/bin/python scripts/simulate_modem.py --gui
.venv-notebooks/bin/python scripts/modem_fpga.py generate
.venv-notebooks/bin/python scripts/modem_fpga.py build
```

`--gui` runs the asserted module simulation then opens the recorded waveform in
Questa. Use `add wave -r /tb_modem/dut/*` in its Transcript to inspect states,
IQ, metrics and survivor memory. The simulation does not simulate Nios or RF.

The native QPF is `iq_bridge_vds.qpf`; it has explicit Atum A3 Nano pin assignments
and a 20 ns clock constraint in `iq_bridge_vds.sdc`. `generate` rebuilds Nios
firmware and VDS/IP and exports the complete project. `build` additionally fits
and assembles the SOF. No command above programs the FPGA or opens a serial port.

## Program checkpoint 06 explicitly

After a successful source-matched build, stop acquisition and release serial/JTAG
owners, then run:

```bash
.venv-notebooks/bin/python scripts/modem_fpga.py program
```

This verifies the SOF hash and source fingerprint, stops only this checkout's
recorded notebook viewer, refuses remaining serial/JTAG sessions, and selects the
Atum A3 Nano cable explicitly (`ATUM_JTAG_CABLE` can override its name). It writes
`active-fpga.json` only after programming succeeds. It does not flash ESP32s.

## Python control after loading checkpoint 06

Use the same JTAG ownership rules as the earlier lessons. Do not open this
session while another acquisition owner is running. If an owner already exists,
pass that instance into `ModemFPGA` instead of constructing another `NiosFir`.

```python
import sys
sys.path[:0] = ['scripts', 'cyberether']
import numpy as np
from nios_fir import NiosFir
from modem_fpga import ModemFPGA

bits = np.random.default_rng(42).integers(0, 2, 128, dtype=np.uint8)
with NiosFir() as owner:
    modem = ModemFPGA(owner)
    tx = modem.encode(bits, bps=6)  # 1=BPSK, 2=QPSK, 4=16-QAM, 6=64-QAM
    rx = modem.decode(tx['iq'])    # replace with corrected symbol-rate IQ later
    print(rx['raw_errors'], rx['decoded_errors'], rx['cycles'])
```

`encode` preserves the reference source/coded bits so `decode` can count errors.
Frames hold **1–256 information bits**, plus six zero tail bits. Convolutional
polynomials are octal **171, 133**, newest bit in bit 0, output 171 first.
QAM bits are MSB first, I-axis group before Q-axis group; each ascending axis
level index has Gray label `index ^ (index >> 1)`. BPSK uses 0→+1, 1→−1.
Constellations have unit average symbol energy before Q3.13 quantization
(scale 8192, nearest even). Incomplete final symbol groups are padded with zeros;
padding is discarded before Viterbi decoding. Soft metrics are positive for bit
zero, clipped to ±127 after a fixed max-log squared-distance scale (`>>18`).

## Register map

All addresses below are **32-bit word offsets** from `0x10060000`. Writes require
all byte lanes. Configuration and RAM writes are ignored while busy. Nios
commands `FIR <id> MREAD <offset>` / `MWRITE <offset> <signed32>` expose the map.

| Word | Read | Write |
|---:|---|---|
| 0 | ID `0x4d440601` | — |
| 1 | bit0 busy, bit1 done, bit2 error | 1 encode/map; 2 demap/decode |
| 2 | bits per symbol | 1, 2, 4, 6 |
| 3 | information-bit count | 1–256 |
| 4 | selected RAM index | RAM index |
| 5 | source bit at index | source bit |
| 6 | CI16 symbol, I low half / Q high half | CI16 symbol |
| 7 | encoded bit | — |
| 8 | signed soft bit metric | — |
| 9 | decoded bit | — |
| 10 | symbol count including final padding | — |
| 11 | processing cycles, 50 MHz | — |
| 12 | hard coded-bit errors versus encoded reference | — |
| 13 | decoded information-bit errors | — |
| 14 | maximum information bits (256) | — |
| 15 | constellation scale (8192) | — |

Run `encode` first to establish frame sizing and comparison references; then
upload received symbols and run `decode`. BER denominators differ: word 12 uses
`2*(payload_bits+6)` coded bits; word 13 uses `payload_bits` information bits.
The full-frame Viterbi traceback ends in state zero and uses all six tail bits.

## Qualification boundary

`simulate_modem.py` checks every mapping point, full encoder output, quantized
soft metrics and decoded bits against independent Python calculations. Each mode
includes an intentionally wrong Gray-coded symbol that causes one coded-bit
error, which the RTL Viterbi corrects. A fixed 64-QAM Gaussian-noise vector also
produces 27 coded-bit errors out of 524 and zero decoded payload errors out of
256. This is a deterministic FEC proof, not a
coding-gain curve, RF test or Wi-Fi PHY. Native build and physical FPGA results
must be reported separately. ESP32 arbitrary-IQ TX support must be qualified for
the exact device family before attempting an over-air modem.

## Recorded build qualification (2026-10-21)

Quartus Prime Pro 26.1.1 generated, fitted and assembled the native VDS project
for `A3CZ135BB18AE7S`: **28,058 / 45,800 ALMs (61%)**, **146 / 353 M20Ks (41%)**,
and **32 / 368 reported DSP blocks (9%)**, including the existing checkpoint 05
pipeline. At 50 MHz, final setup slack was **+1.194 ns** and hold slack
**+0.026 ns**. Both clock domains passed; the source fingerprint and SOF SHA were
checked. These are compiled allocations, not live activity percentages.

The actual 18-cell Quartus VDS GUI diagram was exported and every cell label
validated in its native PDF. Five module simulations passed (four modulation
modes plus noisy 64-QAM), with exact integer encoder/mapping/soft-metric checks.
Physical-board and RF qualification are separate steps; see the repository's
`VALIDATION.md` for subsequent hardware results.

## Physical FPGA check (2026-10-21)

The guarded image was programmed on the Atum A3 Nano. All four modulation modes
passed 32-bit encoder/map/demap/decoder comparisons against independent Python
results. Noisy 64-QAM corrected 6/76 coded errors to 0/32 payload errors.
Run `scripts/check_modem_hardware.py` from the example root after programming.
`--payload-bits 256` selects a slower full-capacity test; only the 32-bit physical
hardware run is qualified here. The 256-bit case is covered by actual Questa.
RF waveform synchronization and actual ESP32 QAM transmission remain separate.
