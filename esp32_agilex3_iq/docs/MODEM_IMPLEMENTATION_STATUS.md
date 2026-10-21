# Modem Lab implementation status

This page records the boundary between the working modem reference, FPGA accelerator and RF hardware. It is not a claim that every stage of the roadmap has been implemented.

| Function | Current implementation | Qualification |
|---|---|---|
| Gray BPSK/QPSK/16-QAM/64-QAM | Python reference and checkpoint06 RTL | Exhaustive mapping vectors; actual Questa and physical FPGA 32-bit frame tests |
| K7 rate-1/2 convolutional encoding | Python and FPGA RTL | Bit-exact comparison, six termination bits; physical FPGA verified |
| Max-log soft demapping and Viterbi | Python and FPGA RTL | Metric/decoded-bit comparison; actual FPGA noisy64-QAM corrected 6/76 coded errors to 0/32 payload errors |
| Preamble/header/CRC/scrambling | Python framed modem | All modulation modes, valid/failed frame tests |
| RRC waveform, fractional acquisition, CFO correction, trained equalizer and pilot tracking | Python reference | Impairment simulations; not an FPGA raw-IQ receiver |
| Native VDS design | New 18-block checkpoint06, retaining existing bridge/FIR/DDC/gain | Actual native GUI export; build evidence recorded separately |
| Original ESP32 carrier / host-timed OOK TX | Separate bounded diagnostic, PMOD A → RF → RFS2 | [Actual bring-up results](ESP32_TX_BRINGUP_RESULTS.md); host detector, FPGA transport only |
| Original ESP32 frequency / phase control | Guarded scalar NCO and CPU-timed phase-pulse diagnostics | [Measured relative-frequency sweep](ESP32_NCO_RF_RESULTS.md); [30 actual phase/control captures](ESP32_PHASE_RF_RESULTS.md), no framed bits/BER |
| ESP32 original-chip arbitrary-IQ TX | Unresolved | Offline SDK/ROM investigation; no positive RF playback claim |
| Optional S3 TX loader | New GPL application plus CRC uploader, pinned component/SDK | USB and UART transport variants compile; ELF RF SRAM-overlap check passes; not flashed/RF-qualified |
| Independent RX/monitor role | Existing original ESP32 capture capability | Not yet exercised as a complete three-radio modulated link |
| Modem Lab GUI/notebook08 | Python plots plus an explicitly separate optional FPGA symbol transaction | Mode/provenance/readback guards, notebook and browser validation |

The FPGA accelerator accepts **already synchronized, normalized symbol-rate CI16 IQ**, not unprocessed radio waveforms. It operates on up to 256 information bits per coded block. Internal FPGA mapping is not itself transmission from an ESP32. Existing FPGA FIR/DDC/gain blocks retain their existing radio path; wiring all raw-IQ modem stages into that path remains work.

## Recorded numerical results

A seeded host 64-QAM simulation processed 100,352 payload bits at each Es/N0 point. At 16 dB, hard-decision Viterbi produced 1846 payload errors while soft-decision Viterbi produced zero observed errors. At 12 dB, soft decoding still produced 3724 errors and 48/49 frames failed CRC. Those failures are included in payload error counts. Acquisition/header failures have their own counters. These are simulations, not RF measurements or equal-Eb/N0 coding-gain claims.

Actual RTL simulation verifies all 86 constellation points across the four modes, coded outputs and soft metrics. A 64-QAM noise vector produces 27 wrong coded bits among 524; the RTL soft decoder recovers all 256 information bits. This is a symbol-level experiment with host-generated impairments. See VALIDATION.md for actual build/hardware results as they become available.

## Remaining gates

1. Turn the measured original-chip phase-control path into a framed BPSK experiment with independent symbol/frame recovery. Arbitrary-IQ/amplitude-linear playback for higher QAM remains unqualified; prove that path or qualify a supported replacement transmitter. [Original-chip investigation](ESP32_TX_INVESTIGATION.md) tracks concrete binary/ROM evidence.
2. Add FPGA waveform shaping/matched filtering, preamble/frame acquisition, timing/frequency/phase recovery and equalization with module-level reference checks. Existing FIR/DDC alone does not constitute a complete modem synchronizer.
3. Connect real received frames through the FPGA stages, exercise independent monitor capture, and measure actual capture coverage, RF error floor and BER across modulation modes.
4. Qualify real-RF 64-QAM empirically; retain visibly labeled FPGA/Python examples if the RF chain cannot meet the error budget.

The current useful demo is Python waveform synchronization plus the independently tested FPGA symbol/FEC checkpoint. The complete over-the-air three-radio modem remains unfinished until those gates pass. Raw captures, executed notebooks, build databases and test logs stay ignored; source and saved diagrams/screenshots are committed.

Physical checkpoint06 FPGA tests passed all four modulation modes on 32-bit frames. Fit uses 61% ALMs and meets setup/hold timing. The independent hardware symbol/noise checker is `scripts/check_modem_hardware.py`; this does not qualify raw-RF acquisition or the ESP32 IQ transmitter. See [validation](../VALIDATION.md).
