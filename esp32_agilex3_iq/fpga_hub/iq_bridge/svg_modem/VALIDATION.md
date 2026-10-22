# SVG modem validation · Atum A3 Nano / Agilex 3

Recorded on 2026-10-22. This is an internal, buffered FPGA loopback, with no RF
transmission or ESP32 firmware change. Runtime payload generation, K7 encoding,
edge mapping, waveform generation, bounded uniform noise, nearest-point and
joint decoding, and error counting execute in RTL. The host transfers and plots
the results; separate offline Python models audit them.

## Fitted image

| Property | Result |
|---|---|
| Device | A3CZ135BB18AE7S |
| Clock | 50 MHz |
| SOF SHA256 | `5c48cf3fc00f9215f56d3d52afa37e413a426b06df1c02086fd6753a3b4dff91` |
| Source fingerprint | `c0bf807c24b30264770a1289652c6e0bd168e0bbf21a4cedf5f4afd112cb8d6a` |
| ALMs | 3,084 / 45,800 |
| Registers | 3,477 |
| RAM blocks | 68 / 353 |
| Reported DSP units | 7 / 368 |
| Worst setup slack | +5.628 ns |
| Worst hold slack | +0.061 ns |

These are compiled resource allocations, not live activity percentages. The
image hash comes from the build/programming record, not a device hash readback.
The physical interface returns design ID `0x53564701` and checked configuration
readbacks before each frame.

## Physical sweeps

Each row uses 391 separately terminated seeded frames, 256 payload bits and six zero tail
bits per frame: **100,096 payload bits and 102,442 symbol decisions**. Seeds run
from 7 through 397. Circle edges use the arc waveform; star edges use straight
interpolation. Each edge has 16 buffered CI16 samples.

| Uniform noise bound | Wrong nearest symbols / 102,442 | Decoded payload errors / 100,096 | Frames with payload errors / 391 |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 6,000 | 19,017 | 0 | 0 |
| 10,000 | 47,644 | 19,697 | 379 |

The bound is in CI16 units at nominal radius8192. It is not an AWGN SNR.
Nearest-symbol errors and decoded-bit errors have different denominators and
must not be labeled as pre/post bit BER. Zero observed errors do not establish
perfect decoding; errors within a coded frame are correlated.

The displayed seed7 / bound6000 frame has **47/262 wrong nearest symbols and
0/256 decoded payload errors**, with 4192 TX/RX waveform samples. Processing
takes 254,462 FPGA clocks (5.08924 ms at 50 MHz), excluding JTAG transfers and
display work. The decoder receives known edge-end strobes. This does not test
unknown symbol-clock acquisition, carrier recovery, RF or continuous DAC output.

## Reproduce

Run these explicitly beside installed Quartus/Questa tools. Programming replaces
the active FPGA image; the viewer itself performs no hardware access.

```sh
python scripts/simulate_svg_modem.py
python scripts/build_svg_fpga.py
python scripts/program_svg_fpga.py
python scripts/svg_fpga_capture.py capture --noise 6000 --seed 7
python scripts/audit_svg_capture.py cyberether/run/svg-constellation-result.json
python scripts/svg_fpga_capture.py sweep --bits 100096 --noise 6000 --seed 7 \
  --output cyberether/run/svg-hardware-sweep-6000.json
python scripts/audit_svg_capture.py cyberether/run/svg-hardware-sweep-6000.json --all-frames
python scripts/start_svg_lab.py serve --host 127.0.0.1 --port 8775
```

See `audit_svg_capture.py --help` for output paths. Raw run JSON, WLF recordings,
Quartus databases and SOFs stay outside Git. The checked-in sources, scripts and
notebook recreate them. [Run/restore guide](README.md).

All1173 sweep-frame metrics/counters were independently recomputed, and the
final frame from each sweep passed full TX/RX waveform, symbol, source-bit,
traceback and decoded-bit comparisons. Linear-mode waveform readback at bound6000
and a one-bit noiseless physical frame also pass the independent audit. The
reference uses integer squared components for CI16 metrics; floating magnitude
then squaring can introduce a one-LSB artifact. Deliberately corrupted saved
sample/metric records are rejected by the auditor.
