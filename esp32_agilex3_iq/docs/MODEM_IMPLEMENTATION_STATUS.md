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
| Original ESP32 framed BPSK | Installed v5 compact repeated frame, independent host acquisition/FEC, RF Link Lab and notebook08 | Historical 28 direct captures: 20/1232 coded → 0/224 payload errors. Current full saved audit across RFS2 and PMOD B: 100 captures / 101 CRC-valid frames, 80/4444 → 0/808; includes the separate v5 regression (4/4 valid, 1/176 → 0/32) |
| Original ESP32 framed QPSK | Installed v5 `QFRAME`, independent blind host synchronization/demapping/FEC; v6 built but unflashed | Best run at 12 µs: 21 valid frames / 32 captures, 11 acquisition failures, 0/924 → 0/168. Saved-proof aggregate: 64 captures, 37 acquired, 31 CRC pass / 6 fail, 27 acquisition failures, 112/1628 → 19/296. The 54-symbol QPSK-002 reanalysis is not included in aggregate counts. Source v5 checkpoint: `ba208dc`. See [QPSK qualification](QPSK_QUALIFICATION.md) |
| FPGA FIR on BPSK RF IQ | Existing FIR II, paired raw/filtered capture | Two actual RF snapshots, 32,760 complex samples; exact integer-reference match and valid CRC after filtering |
| FPGA decoding of recovered RF symbols | Checkpoint06 BPSK/QPSK soft demapper and K7 Viterbi | BPSK replay: 1/44 → 0/8. QPSK-004 replay: 0/44 → 0/8 with CRC; 3,100 cycles / 62 µs FPGA time, 68.328 s JTAG transaction. Host synchronization retained |
| BER qualification | `scripts/check_rf_ber.py` and `cyberether/ber_qualification.py` | Seeded synthetic AWGN sweep plus separate BPSK and QPSK saved-proof audits; see [BER qualification](BER_QUALIFICATION.md). The live comparison action is simulation plus saved evidence, not an RF run |
| SPI IQ transport | ESP32/FPGA SPI transport prototype | Bounded synthetic/RF hardware checks passed, including FPGA integer power/peak/clips; 5 MHz active ingress ~591 kB/s, host ~106–113 kB/s. Standalone image; hub integration remains open |
| ESP32 original-chip arbitrary-IQ TX | Unresolved | Offline SDK/ROM investigation; no positive RF playback claim |
| Optional S3 TX loader | New GPL application plus CRC uploader, pinned component/SDK | USB and UART transport variants compile; ELF RF SRAM-overlap check passes; not flashed/RF-qualified |
| Independent RX/monitor role | Existing original ESP32 capture capability | Not yet exercised as a complete three-radio modulated link |
| Modem Lab GUI/notebook08 | Python plots plus an explicitly separate optional FPGA symbol transaction | Mode/provenance/readback guards, notebook and browser validation |

The FPGA accelerator accepts **already synchronized, normalized symbol-rate CI16 IQ**, not unprocessed radio waveforms. It operates on up to 256 information bits per coded block. Internal FPGA mapping is not itself transmission from an ESP32. The QPSK RF replay used 22 symbols recovered by the host, rotated −135° for the FPGA mapper; it did not execute raw-waveform synchronization in FPGA. Existing FPGA FIR/DDC/gain blocks retain their existing radio path; wiring all raw-IQ modem stages into that path remains work.

The [RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md) explains the compact BPSK
format and host/FPGA boundary. [QPSK qualification](QPSK_QUALIFICATION.md)
records the installed v5 frame protocol, all measured symbol-period outcomes,
and the single-frame FPGA replay. `scripts/check_rf_bpsk.py` and
`scripts/check_rf_qpsk.py` save actual CI8 with setting/encoder readbacks and
host acquisition; their explicit synthetic modes bypass hardware. The separate
FPGA replay checkers consume recovered host symbols and require checkpoint06
already loaded. `check_rf_bpsk_fir.py` separately verifies FPGA filtering on a
paired raw RF snapshot. The [BER qualification guide](BER_QUALIFICATION.md)
covers deterministic AWGN simulation and auditing saved RF proofs without
starting a capture. It reports BPSK and QPSK audits separately. The RF Link Lab
shows BPSK totals and a QPSK table by symbol period/payload; its aggregate keeps
the original QPSK-002 proof's four valid frames and does not count the blind
54-symbol reanalysis of the same captures again.

## Recorded numerical results

A seeded host 64-QAM simulation processed 100,352 payload bits at each Es/N0 point. At 16 dB, hard-decision Viterbi produced 1846 payload errors while soft-decision Viterbi produced zero observed errors. At 12 dB, soft decoding still produced 3724 errors and 48/49 frames failed CRC. Those failures are included in payload error counts. Acquisition/header failures have their own counters. These are simulations, not RF measurements or equal-Eb/N0 coding-gain claims.

Actual RTL simulation verifies all 86 constellation points across the four modes, coded outputs and soft metrics. A 64-QAM noise vector produces 27 wrong coded bits among 524; the RTL soft decoder recovers all 256 information bits. This is a symbol-level experiment with host-generated impairments. See VALIDATION.md for actual build/hardware results as they become available.

## Remaining gates

1. Extend BPSK/QPSK RF evidence across at least 100,000 payload bits and controlled operating points; report acquisition, CRC and payload errors with denominators. Current QPSK best is 0/168 payload errors from 21 valid frames in 32 captures at 12 µs; its saved-proof aggregate includes 19/296 payload errors.
2. Add FPGA waveform shaping/matched filtering, preamble/frame acquisition, timing/frequency/phase recovery and equalization with module-level reference checks. Raw-IQ synchronization remains host-side; existing FIR/DDC and recovered-symbol replay are not a complete FPGA receiver.
3. Measure physical SPI throughput and loss against the UART baseline. Bounded transport and FPGA-meter hardware checks pass; continuous streaming and integrated-hub operation remain unqualified. Exercise independent monitor capture and measure real capture coverage and RF error behavior.
4. Qualify amplitude-linear transmission before 16/64-QAM RF. Retain clearly labeled FPGA/Python examples if the RF chain cannot meet the measured error budget.

The current demo has real compact BPSK and preliminary QPSK RF frames, separate FPGA FIR verification, and FPGA FEC replay of host-recovered symbols. The complete over-the-air three-radio modem, continuous FPGA waveform synchronization, 100,000-bit RF qualification and higher-QAM RF remain unfinished until their gates pass. Raw captures, executed notebooks, build databases and test logs stay ignored; source and saved diagrams/screenshots are committed.

Physical checkpoint06 FPGA tests passed all four modulation modes on 32-bit frames. Fit uses 61% ALMs and meets setup/hold timing. The independent hardware symbol/noise checker is `scripts/check_modem_hardware.py`; this does not qualify raw-RF acquisition or the ESP32 IQ transmitter. See [validation](../VALIDATION.md).
