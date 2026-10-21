# Clean IQ lesson samples

Deterministic synthetic signals, not received Wi-Fi. Signed interleaved I8,Q8, 4096 complex samples, nominal 16 MS/s. SHA256 and CRC32 are in manifest.json. The FPGA test generator emits the same integer bytes.

| File | Signal |
|---|---|
| two-tone.ci8 | +0.5 MHz desired tone (48 counts) + +6 MHz interferer (64 counts) |
| single-tone.ci8 | +0.5 MHz tone (96 counts) |
| impulse.ci8 | I=96, Q=48 at sample 0, then zeros |

For two-tone, tune +500000 Hz and decimate 4. Mixer-only folds the interferer to +1.5 MHz; mixer + FIR suppresses it. Pin the mixer-only result, enable filtering and rerun to overlay the same input. The tone meter is host analysis of actual FPGA output, not calibrated RF power.

Python: `np.fromfile('two-tone.ci8', dtype=np.int8).reshape(-1, 2)`.

Fs describes the logical sample timeline for DSP; the FPGA writes these samples to RAM without transmitting RF.
