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
| Original ESP32 framed BPSK | Installed v6 phase-pulse transmitter; host acquisition/FEC via RFS2 | New v6 batch: 8 captures, 9 acquired frames, 8 CRC pass / 1 fail; 16/396 coded → 0/72 soft payload errors (hard: 1/72). Earlier v5 audits remain historical and separately reported |
| Original ESP32 framed QPSK | Installed v6 `QFRAME`; host synchronization/demapping/FEC | New v6 batches: 12 µs 34/64 CRC-valid, 0/1496 coded → 0/272 payload; 10 µs CLI 30/32 valid, 0/1320 → 0/240; 9 µs 23/32 valid, 7 CRC failures, 171/1320 → 27/240 soft payload (hard 21/240); 8 µs TX completed no frames, so BER is undefined. Small separate GUI captures add two 10 µs CRC failures. See [QPSK qualification](QPSK_QUALIFICATION.md) |
| FPGA coarse QPSK preamble detector | Checkpoint08 raw-capture observer beside the existing FIR II; Avalon-MM at `0x10070000` | Synthetic, saved-IQ replay and passive PMOD B snapshot all have bit-exact score traces vs independent integer reference. Passive peak 4,141 is below 24,576; no detection. Coarse alignment only; no payload decode |
| FPGA FIR on BPSK RF IQ | Existing FIR II, paired raw/filtered capture | Two actual RF snapshots, 32,760 complex samples; exact integer-reference match and valid CRC after filtering |
| FPGA decoding of recovered RF symbols | Checkpoint06 BPSK/QPSK soft demapper and K7 Viterbi | BPSK replay: 1/44 → 0/8. QPSK-004 replay: 0/44 → 0/8 with CRC; 3,100 cycles / 62 µs FPGA time, 68.328 s JTAG transaction. Host synchronization retained |
| BER qualification | `scripts/check_rf_ber.py` and `cyberether/ber_qualification.py` | Seeded synthetic AWGN sweep plus separate BPSK and QPSK saved-proof audits; see [BER qualification](BER_QUALIFICATION.md). The live comparison action is simulation plus saved evidence, not an RF run |
| SPI IQ transport and FIR II | Combined SPI firmware on PMOD B; current checkpoint07 status FIFO + SPI→capture-RAM→FIR II SOF loaded | Earlier SPIQ0002 meter run: 24 captures (12 synthetic, 12 RF; 393,120 complex samples), independent meter/hash audit passed. Current SOF `91a0b547…`, source `e35b970c…`: four-line whole-line text FIFO passes actual `TX_ON` acknowledgement with zero status drops (`tx-status-fifo-hardware-001`). The FIFO uses 27,988/45,800 ALMs (61%), 120 RAMs and 16 reported DSP units; added ALMs are status buffering/control, not RF DSP. Fresh-boot FIR, settings and control-guard proof remains from the prior 19ff image; current image has passed a 12-pair GUI regression (6 synthetic/6 RF, 196,560 samples, exact integer match, UART liveness and restore; no JS errors). Matched RF readout rates remain 79,164 B/s at 2 Mbaud and 126,048 B/s at 4 Mbaud, excluding Nios setup/verification. v6 RF summaries are separately listed above; watchdog recovery and 100,000-bit BER remain open |
| ESP32 original-chip arbitrary-IQ TX | Unresolved | Offline SDK/ROM investigation; no positive RF playback claim |
| Optional S3 TX loader | New GPL application plus CRC uploader, pinned component/SDK | USB and UART transport variants compile; ELF RF SRAM-overlap check passes; not flashed/RF-qualified |
| Independent RX/monitor role | Existing original ESP32 capture capability | Not yet exercised as a complete three-radio modulated link |
| Modem Lab GUI/notebook08 | Python plots plus an explicitly separate optional FPGA symbol transaction | Mode/provenance/readback guards, notebook and browser validation |

Checkpoint08 is the current FPGA image: SOF `cf2eea090cd7825d23087b2e0dbacc2e5b08c3aa898e98aff5b43ef64205145d`, source fingerprint `dd6bf7276d85b1a1f73619a69e9aaab6a786184e86ade61af66b6ab414b1f439`. It preserves the checkpoint07 SPI/capture/FIR path and adds raw preamble observation on a dedicated parallel conduit. The monitor boot-memory fix reserves existing `PAIR`/`PRESET` commands; the FIR regression now passes exact Hamming output, CRC, coefficient restore and 2-Mbaud host UART checks. The routed implementation uses 29,472/45,800 ALMs (64%), 152/353 M20Ks (43%) and 24/368 reported DSP units (7%); the coarse detector scores the raw parallel branch, while fine timing/carrier recovery and frame decode remain host-side. The official checkpoint08 BSP, Hello World and monitor were rebuilt but not downloaded. Notebook10 regenerated and passed offline execution; the complete host suite passed 228 tests. See [FPGA Preamble Lab](FPGA_PREAMBLE_LAB.md) for image history and per-capture proofs.

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

Current PMOD A has v6 phase-pulse TX and RFS2 has UART RX firmware; PMOD B has
combined SPI receiver firmware (SPI ON, BOOT OFF). The current FPGA SOF is
`91a0b547a3c5b0ae8b780c89c31a19940dbf20e660f2ceea5ad602845e9e7881`, source
`e35b970c093464de6fab3a149e8a603938435d3ca05215e551a16925f1e93db7`. Its
four-line whole-text FIFO fixes the dropped `TX_ON` response: the hardware
acknowledgement proof has zero text drops, command/framing/capture errors, and
reports the actual channel 8 / attenuation code 120 / duration. Proof:
`cyberether/run/tx-status-fifo-hardware-001.json`. The build uses 27,988/45,800
ALMs (61%), 120 M20Ks and 16 reported DSPs; the added ALMs are status queue and
control logic, not RF processing.

The current-image GUI regression passed 12 alternating pairs (six synthetic,
six RF; 196,560 complex samples) with exact Hamming integer-reference matches,
settings restoration, both UART liveness checks and no JavaScript errors. Proofs
are `cyberether/run/spi-gui-1792621578444678407/proof.json` and
`cyberether/run/spi-fir-browser-fifo-final.json`; screenshot:
`docs/images/spi_pipeline_fir_lab.png`. It remains a bounded test, not continuous
coverage. Earlier v5 PHY setup watchdog failure and the first v6 A→B SPI/FIR
CRC-failed BPSK attempt remain historical; neither is an RF success claim.

v6 normal boot identity passes at 160 MHz with `busy=0`. New v6 RFS2 runs
acquired frames at 9, 10 and 12 µs, but the 9 µs batch had seven CRC failures;
8 µs completed no TX frames and has undefined BER. A separate four-capture
10 µs browser run had three CRC-valid frames and two CRC failures. The independent
saved-raw audit passed for all 172 unique captures, including GUI captures,
with blind re-decode. Watchdog recovery remains unproven, and the 100,000-bit
RF target remains open. Raw-IQ synchronization, timing, demapping and framing
remain host-side; full host delivery remains UART limited.

## Recorded numerical results

A seeded host 64-QAM simulation processed 100,352 payload bits at each Es/N0 point. At 16 dB, hard-decision Viterbi produced 1846 payload errors while soft-decision Viterbi produced zero observed errors. At 12 dB, soft decoding still produced 3724 errors and 48/49 frames failed CRC. Those failures are included in payload error counts. Acquisition/header failures have their own counters. These are simulations, not RF measurements or equal-Eb/N0 coding-gain claims.

Actual RTL simulation verifies all 86 constellation points across the four modes, coded outputs and soft metrics. A 64-QAM noise vector produces 27 wrong coded bits among 524; the RTL soft decoder recovers all 256 information bits. This is a symbol-level experiment with host-generated impairments. See VALIDATION.md for actual build/hardware results as they become available.

## Remaining gates

1. Extend v6 BPSK/QPSK RF evidence to at least 100,000 payload bits across controlled operating points. The current v6 groups have 72 BPSK payload bits and QPSK groups of 272 bits (12 µs), 280 bits (10 µs CLI + GUI), and 240 bits each (9 µs). Preserve all acquisition and CRC failures; the goal remains open.
2. Preserve the checkpoint07 cold-boot tap readback and profile-specific exact-reference output as regression checks on future builds. The final image passed this bounded gate.
3. Qualify v6 watchdog recovery and RF transmission after its passing normal boot; verify-flash and startup identity alone do not prove either. Keep the known v5 PHY setup hang distinct from SPI/FIR results.
4. Repeat matched 2/4-Mbaud RF measurement (79,164 vs 126,048 useful input B/s; excludes Nios setup/verification), then run continuous-coverage and recovery tests. The current 12-pair GUI test passes as a bounded run; continuous coverage remains open.
5. Validate the three-radio GUI workflow on the integrated image. Require explicit Apply/readback for controls, acquisition-owner locking, capture provenance, loss counters and expected behavior for RF/synthetic transitions.
6. Extend checkpoint08 coarse preamble scoring with waveform shaping/matched filtering, fine timing/frequency/phase recovery, frame validation and equalization. Raw-IQ synchronization and decoding remain host-side; current FPGA capture/FIR and preamble score are not a complete receiver.
7. The v6 TX timing/recovery app is flashed and normal-booted but not RF/WDT-qualified. Qualify amplitude-linear transmission before 16/64-QAM RF, with measured levels, backoff, compression and EVM. Retain clearly labeled FPGA/Python examples until that gate passes.

The current demo has real compact BPSK and preliminary QPSK RF frames, bounded integrated SPI/FIR hardware proof, and FPGA FEC replay of host-recovered symbols. The complete over-the-air three-radio modem, continuous FPGA waveform synchronization, PMOD A TX recovery, 100,000-bit RF qualification and higher-QAM RF remain unfinished until their gates pass. Raw captures, executed notebooks, build databases and test logs stay ignored; source and saved diagrams/screenshots are committed.

Physical checkpoint06 FPGA tests passed all four modulation modes on 32-bit frames. Fit uses 61% ALMs and meets setup/hold timing. The independent hardware symbol/noise checker is `scripts/check_modem_hardware.py`; this does not qualify raw-RF acquisition or the ESP32 IQ transmitter. See [validation](../VALIDATION.md).
