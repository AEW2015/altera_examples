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
| Original ESP32 framed BPSK | Installed v5 compact repeated frame, independent host acquisition/FEC, RF Link Lab and notebook08 | Historical 28 direct captures: 20/1232 coded → 0/224 payload errors. Extended audit: 420 captures / 441 acquired, 438 CRC pass / 3 fail, 337/19404 coded → 1/3528 payload errors; all 744 unique BPSK/QPSK captures passed raw integrity checks, 580 new captures independently blind-redecoded |
| Original ESP32 framed QPSK | Installed v5 `QFRAME`, independent blind host synchronization/demapping/FEC; v6 is not installed | Best individual run at 12 µs: 21 valid / 32 captures, 11 acquisition failures, 0/924 → 0/168. Extended aggregate: 324 captures, 163 acquired, 153 CRC pass / 10 fail, 161 no acquisition, 200/7172 → 37/1304. Not a calibrated BER curve or 100,000-bit qualification. The 54-symbol QPSK-002 reanalysis remains excluded; see [QPSK qualification](QPSK_QUALIFICATION.md) |
| FPGA FIR on BPSK RF IQ | Existing FIR II, paired raw/filtered capture | Two actual RF snapshots, 32,760 complex samples; exact integer-reference match and valid CRC after filtering |
| FPGA decoding of recovered RF symbols | Checkpoint06 BPSK/QPSK soft demapper and K7 Viterbi | BPSK replay: 1/44 → 0/8. QPSK-004 replay: 0/44 → 0/8 with CRC; 3,100 cycles / 62 µs FPGA time, 68.328 s JTAG transaction. Host synchronization retained |
| BER qualification | `scripts/check_rf_ber.py` and `cyberether/ber_qualification.py` | Seeded synthetic AWGN sweep plus separate BPSK and QPSK saved-proof audits; see [BER qualification](BER_QUALIFICATION.md). The live comparison action is simulation plus saved evidence, not an RF run |
| SPI IQ transport and FIR II | Combined SPI firmware on PMOD B; final checkpoint07 SPI→capture-RAM→FIR II SOF installed | Standalone SPIQ0002: 24 alternating captures (12 synthetic, 12 RF; 393,120 complex samples; commits 1–24), independent NumPy meter/hash audit passed. Final SOF `19ff94b0…`, source `46397727…`: cold boot read all 16 default taps (2048); exact Hamming FIR/reference passed for 16,380 complex samples; settings restore passed. Invalid 40 MHz/2417 MHz returned error128; 1024 samples returned error32 without arming; subsequent valid SPI raw and 4 passive RFS2 UART0 captures passed. Matched profile-2 RF measured 79,164 useful input B/s at 2 Mbaud and 126,048 B/s at 4 Mbaud, excluding Nios setup/verification; CS-active ingress remains 591,134 B/s. Realistic Questa READY regression fails the old handshake and passes observed-LOW→HIGH reservation. PMOD A UART INFO works before TX, but the known v5 TX attempt watchdog-hangs in PHY setup before `FRAME_CFG` and leaves A UART-unresponsive until manual reset. Final-image GUI batch verified one pair then failed A INFO liveness; cleanup restored 2-Mbaud host UART and FIR settings. A separate final-image 4-Mbaud Hamming RF browser pair passed bit-exact raw/FIR with no JS errors, not a soak pass. v6 WDT-recovery/timing app `BAAC3D…` is built but not flashed or hardware-qualified |
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

Current installation keeps PMOD A v5 phase-pulse TX and RFS2 UART RX firmware;
PMOD B has the combined SPI receiver firmware installed (SPI ON, BOOT OFF).
The FPGA runs final checkpoint07 SOF `19ff94b0…` (source fingerprint
`46397727…`). Fresh boot read all sixteen 2048 default taps, the exact Hamming
reference matched for 16,380 complex samples, and prior settings restored.
Invalid profile controls returned their expected errors and were followed by a
valid SPI raw capture and four passive RFS2 UART0 captures. PMOD A UART INFO
works before TX, but the known v5 TX attempt watchdog-hangs during PHY setup
before `FRAME_CFG`; no RF samples were captured, and A remains UART-unresponsive
until manual reset. Therefore the FPGA/SPI/FIR and RFS2 bounded paths are
demonstrated, while PMOD A TX and the complete three-radio modem are not
qualified. The v6 WDT-recovery/timing app `BAAC3D…` is built but not flashed;
automatic reboot recovery remains unproven. A final-image GUI batch verified one
synthetic pair then failed A INFO liveness; cleanup verified the host UART was
restored to 2 Mbaud and FIR settings were restored. This is not a soak pass.
An independent final-image 4-Mbaud Hamming RF browser capture passed bit-exact
raw/FIR comparison with no JavaScript errors; it remains a single bounded pair.
Capture tests remain bounded, not continuous streaming qualification. CS-active
ingress excludes READY waits and UART/inter-transaction gaps; full host delivery
remains UART limited.

## Recorded numerical results

A seeded host 64-QAM simulation processed 100,352 payload bits at each Es/N0 point. At 16 dB, hard-decision Viterbi produced 1846 payload errors while soft-decision Viterbi produced zero observed errors. At 12 dB, soft decoding still produced 3724 errors and 48/49 frames failed CRC. Those failures are included in payload error counts. Acquisition/header failures have their own counters. These are simulations, not RF measurements or equal-Eb/N0 coding-gain claims.

Actual RTL simulation verifies all 86 constellation points across the four modes, coded outputs and soft metrics. A 64-QAM noise vector produces 27 wrong coded bits among 524; the RTL soft decoder recovers all 256 information bits. This is a symbol-level experiment with host-generated impairments. See VALIDATION.md for actual build/hardware results as they become available.

## Remaining gates

1. Extend BPSK/QPSK RF evidence across at least 100,000 payload bits and controlled operating points; report acquisition, CRC and payload errors with denominators. Current QPSK best individual run is 0/168 payload errors from 21 valid frames in 32 captures at 12 µs; the extended grouped audit has 37/1304 payload errors across 324 captures and remains below the target.
2. Preserve the checkpoint07 cold-boot tap readback and profile-specific exact-reference output as regression checks on future builds. The final image passed this bounded gate.
3. Requalify PMOD A TX; the v5 test stalls in PHY setup before frame configuration. The v6 WDT recovery is built but unflashed and unproven. Do not count this TX failure as a SPI failure.
4. Repeat matched 2/4-Mbaud RF measurement (current pair: 79,164 vs 126,048 useful input B/s; excludes Nios setup/verification), then run continuous-coverage and recovery tests after A manual reset/TX recovery. The final-image GUI batch failed A liveness after one verified pair; a separate one-shot RF browser check passed, but the soak did not.
5. Validate the three-radio GUI workflow on the integrated image. Require explicit Apply/readback for controls, acquisition-owner locking, capture provenance, loss counters and expected behavior for RF/synthetic transitions.
6. Add FPGA waveform shaping/matched filtering, preamble/frame acquisition, timing/frequency/phase recovery and equalization with module-level reference checks. Raw-IQ synchronization remains host-side; existing FIR/DDC and recovered-symbol replay are not a complete FPGA receiver.
7. Keep a v6 TX timing change separate and optional; it is not installed. Qualify amplitude-linear transmission before 16/64-QAM RF, with measured levels, backoff, compression and EVM. Retain clearly labeled FPGA/Python examples until that gate passes.

The current demo has real compact BPSK and preliminary QPSK RF frames, bounded integrated SPI/FIR hardware proof, and FPGA FEC replay of host-recovered symbols. The complete over-the-air three-radio modem, continuous FPGA waveform synchronization, PMOD A TX recovery, 100,000-bit RF qualification and higher-QAM RF remain unfinished until their gates pass. Raw captures, executed notebooks, build databases and test logs stay ignored; source and saved diagrams/screenshots are committed.

Physical checkpoint06 FPGA tests passed all four modulation modes on 32-bit frames. Fit uses 61% ALMs and meets setup/hold timing. The independent hardware symbol/noise checker is `scripts/check_modem_hardware.py`; this does not qualify raw-RF acquisition or the ESP32 IQ transmitter. See [validation](../VALIDATION.md).
