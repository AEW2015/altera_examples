# RF modem roadmap: measured BPSK toward 64-QAM

Status: **v6 framed BPSK/QPSK RF captures and checkpoint08 SPI/FIR plus coarse preamble observation are measured; BER remains preliminary and watchdog recovery is unproven. The 100,000-bit RF target, continuous capture, raw-IQ FPGA synchronization and higher-QAM RF remain open.** The [RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md) records the BPSK protocol and runs. The [QPSK qualification](QPSK_QUALIFICATION.md) records historical v5 and current v6 captures. The [BER qualification guide](BER_QUALIFICATION.md) documents the CLI, API and synthetic/RF boundaries.

## Current measured system

PMOD A runs the flashed v6 phase-pulse probe (normal boot identity passes, `busy=0`, 160 MHz); PMOD B has combined SPI receiver firmware (SPI ON, BOOT OFF), and RFS2 retains UART RX firmware. Checkpoint07 SOF `91a0b547a3c5b0ae8b780c89c31a19940dbf20e660f2ceea5ad602845e9e7881`, source `e35b970c093464de6fab3a149e8a603938435d3ca05215e551a16925f1e93db7`, established the four-line whole-text status FIFO and actual `TX_ON` acknowledgement with zero drops. The currently loaded checkpoint08 image is SOF `cf2eea090cd7825d23087b2e0dbacc2e5b08c3aa898e98aff5b43ef64205145d`, source `dd6bf7276d85b1a1f73619a69e9aaab6a786184e86ade61af66b6ab414b1f439`; it retains SPI/capture/FIR and adds a raw-sample coarse preamble detector. The current checkpoint08 fit uses 29,472/45,800 ALMs (64%), 152/353 M20Ks (43%) and 24/368 reported DSP units (7%); the added block is a coarse raw-IQ preamble observer, not a full synchronizer or decoder. The FPGA computes candidate scores, while fine timing/carrier recovery, demapping and frame decode remain on the host. v6 RFS2 batches yield small BPSK/QPSK denominators and mixed CRC results; see [QPSK qualification](QPSK_QUALIFICATION.md). Watchdog recovery remains unproven. The earlier v5 PHY setup watchdog hang is historical. PMOD A does not play arbitrary IQ; raw-IQ acquisition, timing, demapping and frame synchronization remain on the host.

```mermaid
flowchart LR
    A[PMOD A v6\nphase-pulse framed TX] -. 2.4 GHz RF .-> R[RFS2 UART RX\nfirmware retained]
    R -. measured UART capture path .-> H[Host modem processing\nsync / symbols / FEC / CRC]
    A -. passive RF observation .-> B[PMOD B combined SPI RX\nSPI ON, BOOT OFF]
    B --> M[Checkpoint08 FPGA\nSPI → capture RAM → FIR II + raw preamble observer]
    M --> H2[Host checker\npaired raw/FIR audit]
    H -. recovered symbols .-> V[Checkpoint 06 FPGA replay\nseparate proof]
```

| Evidence | Measured result | Boundary |
|---|---|---|
| PMODA → RFS2 BPSK | 92 captures, 93 valid frames, 75/4092 coded errors → 0/744 payload errors | Earlier aggregate; sparse captures; host synchronization and FEC; hard and soft both have zero observed payload errors |
| v5 BPSK regression | 4 captures, 4 valid frames, 1/176 coded error → 0/32 payload errors | Separate regression batch after v5 installation |
| PMODA → PMODB BPSK | 4 captures, 4 valid frames, 4/176 coded errors → 0/32 payload errors | Keep separate from RFS2 totals; may observe the same transmissions |
| PMODA → RFS2 QPSK, v5 12 µs | 32 captures, 21 CRC-valid frames, 11 acquisition failures; 0/924 coded → 0/168 payload errors | Historical v5 baseline |
| v6 RFS2 BPSK | 8 captures, 9 acquired frames, 8 CRC pass / 1 fail; 16/396 coded → 0/72 soft payload errors (hard 1/72) | `rf-v6-bpsk-rfs2-002`; first incomplete attempt had no IQB1 capture |
| v6 RFS2 QPSK, 12 µs | 64 captures, 34 CRC-pass frames, 30 no-acquisition; 0/1496 coded → 0/272 payload errors | Finite new run; no BER qualification |
| v6 RFS2 QPSK, 10 µs CLI | 32 captures, 30 CRC-pass frames, 2 no-acquisition; 0/1320 → 0/240 payload errors | Separate finite batch; not a guarantee |
| v6 RFS2 QPSK, 10 µs GUI | 4 captures, 5 acquired frames, 3 CRC pass / 2 fail; 35/220 → 6/40 soft payload errors | Separate browser run; combined with 32-capture CLI: 36 captures, 35 acquired, 33 pass / 2 fail, 2 no-acquisition; 35/1540 → 6/280 |
| v6 RFS2 QPSK, 9 µs | 32 captures, 30 acquired, 23 CRC pass / 7 fail, 2 no-acquisition; 171/1320 → 27/240 soft payload errors (hard 21/240) | No soft-FEC benefit claim |
| v6 RFS2 QPSK, 8 µs | 32 captures, zero acquired; TX completed zero frames | No bits tested; BER undefined, TX timing failure |
| Checkpoint08 coarse preamble | Synthetic/saved-IQ replay and passive PMOD B snapshot passed exact full-trace reference checks; passive peak 4,141/32,768 remained below 24,576 threshold | SOF `cf2eea09…`; passive transport/CRC and mode/detector cleanup pass, but no preamble detection; no payload/FEC decode; see [preamble lab](FPGA_PREAMBLE_LAB.md) |
| FPGA FIR | 32,760 complex samples; exact match to integer reference | Separate paired raw/FIR experiment, not a modem synchronizer |
| Integrated checkpoint07 SPI + FIR | Previous 19ff image passed fresh-boot FIR and settings restore; current status-FIFO image passes 12-pair GUI RF/synthetic regression, exact Hamming reference and UART liveness | Current SOF `91a0b547…`, source `e35b970c…`; current GUI proofs `spi-gui-1792621578444678407` and `spi-fir-browser-fifo-final.json` |
| Checkpoint07 route guards/recovery | Invalid 40 MHz/2417 MHz profile returns error128; 1024 samples returns error32 without arming; subsequent valid SPI raw and four passive RFS2 UART0 captures pass | Proof `spi-profile-rejection-recovery-001`; the earlier v5 PHY setup watchdog hang is historical; v6 strict TX_ON acknowledgements now pass |
| Checkpoint07 transport rates | Matched profile-2 RF capture, 16,380 complex samples: 79,164 useful input B/s at 2 Mbaud vs 126,048 B/s at 4 Mbaud | Excludes Nios setup/verification; FPGA CS-active ingress remains 591,134 B/s. Matched evidence on earlier 6b980718 image; an earlier GUI attempt stopped after one pair and an A INFO timeout; after v6 normal boot, the 12-capture GUI run passed (six synthetic/six RF, 196,560 complex samples, exact raw/FIR, both UART checks, settings restored) |
| Final-image browser RF check | One passive RF Hamming capture at 4 Mbaud passed; raw/FIR payloads bit-exact and no JavaScript errors | `browser-final-single-001`; historical earlier liveness failure is retained; later 12-capture v6 GUI run passed, but neither qualifies continuous operation or modem BER |
| Checkpoint07 text status FIFO | Actual TX_PROBE v6 `TX_ON` line delivered and acknowledged for job 4, channel 8, attenuation code 120, 50 ms; zero text drops/errors | Hardware proof `tx-status-fifo-hardware-001`; current queue implementation uses ALMs for status buffering, not RF DSP |
| RFS2 RF audit | 172 unique v6 captures passed raw CRC/length/SHA and blind re-decode, including the four-capture browser group | `rf-v6-independent-audit/qualification.json`; keep run groups and payload denominators separate |
| A→B v6 BPSK through SPI/FIR | One acquired frame; raw and filtered CRC both failed, 10/44 coded errors → 0/8 payload errors; 725 FIR clipped samples | Historical diagnostic; transport and FIR arithmetic do not imply modem-frame success |
| FPGA symbol/FEC replay | 1/44 coded errors → 0/8 payload errors | Host recovered symbols supplied to checkpoint 06; synchronization remains host-side |
| FPGA QPSK symbol/FEC replay | One QPSK-004 frame; 0/44 coded → 0/8 payload errors; CRC passed | 22 host-recovered symbols rotated −135° for FPGA map; 3,100 FPGA cycles (62 µs at 50 MHz), 68.328 s JTAG transaction; checkpoint 03 restored afterward |
| FPGA SPI meter | 24 alternating bounded captures: 12 synthetic + 12 RF, 393,120 complex samples, commits 1–24 | Independent NumPy integer meter and hash audit passed; CS-active SPI ingress ~591 kB/s; host delivery ~106–110 kB/s; not a continuous soak |

No evidence here qualifies arbitrary-IQ playback on an original ESP32, continuous reception, unique transmitted-frame coverage between snapshots, or QAM amplitude linearity. See [measured BPSK runs](RF_BPSK_WALKTHROUGH.md) for denominator definitions and reproduction commands.

## Goal and modulation ladder

Extend the measured custom fixed-frequency link through **BPSK → QPSK → 16-QAM → 64-QAM**. Keep this separate from Wi-Fi networking. The three-radio foundation and fuller BER accounting live in [SDR_MODEM_FEC_PLAN.md](SDR_MODEM_FEC_PLAN.md).

| Mode | Constellation | Coded bits/symbol | Rate-1/2 information bits/symbol* | Additional qualification |
|---|---:|---:|---:|---|
| BPSK | 2 | 1 | 0.5 | Existing framed baseline; extend BER evidence |
| QPSK | 4 | 2 | 1 | Preliminary framed RF at 12 µs; extend acquisition and BER coverage |
| 16-QAM | 16 | 4 | 2 | Qualify amplitude levels, gain/phase tracking and equalization |
| 64-QAM | 64 | 6 | 3 | Qualify tight EVM/error budget and RF linearity |

*Before preamble, pilots, header, CRC, padding and encoder tail. Compare at matched documented symbol energy and rate assumptions.

## Work order and exit gates

### 1. Qualify the BPSK measurement baseline

The [BER guide](BER_QUALIFICATION.md) provides a reproducible seeded AWGN sweep and a saved-proof RF audit. Its current 1,000-frame, 16-byte simulation has 704 hard versus 8 soft payload errors at 4 dB on the same samples, and 0 soft errors at 6 dB (128,000 tested bits; one-sided 95% bit bound 2.3404 × 10⁻⁵ under an independent-bit assumption, with the frame bound reported separately). This is simulation, not RF. The recursive aggregate now covers 916 unique captures (744 historical plus 172 v6), all passing integrity checks and blind re-decode. BPSK totals are 428 captures / 450 acquired frames, 446 CRC passes / 4 failures, 353/19800 coded errors → 1/3600 payload errors. QPSK totals are 488 captures / 262 acquired frames, 243 CRC passes / 19 failures, 227 no-acquisition captures and 406/11528 coded → 70/2096 payload errors. These group totals mix payloads/settings and are not operating-point BER estimates. Repeated payload/settings groups are not a calibrated BER curve, and these results do not establish a soft RF advantage or meet the 100,000-bit target. Receiver groups remain separate; observing one transmission on two radios does not add unique delivered packets.

Run longer, independently captured batches at fixed settings and at several controlled operating points. Retain every attempt, including capture transport failures, no-sync windows, CRC failures and decoded errors. Report exact numerators and denominators for coded bits, payload bits, complete CRC checks and capture attempts. A sparse snapshot does not establish how many RF frames were transmitted between windows; do not invent a delivery denominator.

At each point, target at least 100,000 payload bits where practical. Report a confidence bound alongside zero observed errors (for example, a one-sided 95% binomial upper bound) and avoid treating repeated processing of one capture as new RF evidence. Add deterministic synthetic tests for known CFO, timing offset, phase ambiguity, noise and CRC failures as controls; label those separately from RF. Preserve RF capture IDs and proof hashes.

**Exit:** reproducible RF batches have explicit settings, independent capture IDs, all failure counts and bit denominators; synthetic controls catch expected injected faults; confidence bounds are computed from the actual tested bits.

### 2. Integrate and qualify sample transport

Separate [SPI transport](SPI_TRANSPORT.md) and [SPI FPGA-meter](SPI_FPGA_METER.md) projects pass bounded synthetic and channel-8 RF hardware qualification on PMOD B. The latest repeat batch contains 24 captures (12 synthetic and 12 RF), 393,120 complex samples and commits 1–24; independent NumPy meter values and hashes passed. Final checkpoint07 cold-booted with all 16 default coefficients read as 2048, then matched the exact Hamming FIR reference for 16,380 complex samples and restored settings. A realistic Questa READY regression fails on the first stale-HIGH implementation and passes with the observed-LOW-then-HIGH reservation handshake. Profile rejects (error128 for invalid rate/frequency; error32 for invalid sample count, no arm) were followed by valid SPI raw and four passive RFS2 UART0 captures. The earlier v5 TX attempt watchdog-hung in PHY setup before frame configuration. Current v6 has bounded RFS2 BPSK/QPSK RF results, with seven CRC failures in the 9 µs QPSK run and no completed TX frames at 8 µs; watchdog recovery remains unqualified. The earlier A→B BPSK-through-SPI/FIR diagnostic failed raw and filtered CRC (10/44 coded errors; 0/8 payload; 725 clips).

Retain the existing UART measurements as the comparison baseline. Measure payload rate, command/turnaround time, loss, backpressure and sustained capture coverage on the actual installed path. For integrated SPI, measure clock rate, framing overhead, sustained bytes/s, buffer-full behavior, dropped blocks and recovery under contention. SPI clocking is transport timing and supplies no RF sample-phase coherence.

At 5 MHz, FPGA-counted CS-active payload ingress is about 591 kB/s; complete host captures reach about 106–110 kB/s because UART egress and sequential control remain limiting. CS-active time excludes READY wait and inter-transaction/UART gaps. These are distinct measurements, not a sustained SPI-to-host speedup.

**Completed evidence:**

The previous checkpoint07 image `19ff94b0…` passed fresh-boot coefficient readback and bounded SPI/FIR qualification; the current 91a0 status-FIFO image passes a 12-pair GUI regression. Before v6 programming, the v5 TX attempt watchdog-hung in PHY setup (`chip_sleep_prot_en` → `esp_phy_wifi_tx_tone`) before `FRAME_CFG`; no RF samples were captured, and A became UART-unresponsive. A private 2 MiB backup was verified against MAC `78:21:84:d4:4f:98`; its application matched v5 SHA `057dda48…`. V6 app SHA `baac3d3881539cb4321c09bda7245b7a3823762d2b3639e6e21c7d9579fc1dbb` was flashed and verify-flash passed. Normal boot passes identity `TX_PROBE,v=6,rev=300,mac=78:21:84:d4:4f:98`, `busy=0`, CPU 160 MHz. Strict matching `TX_ON` acknowledgement now passes through the current whole-line status FIFO with zero text drops. New bounded RF runs are summarized above; automatic watchdog recovery remains unproven. The 500 ms phase-work budget starts after blocking PHY setup, not before it. The previous checkpoint03 127-byte text limit rejection remains historical and is excluded from RF totals.

**Next execution checklist:**

1. Keep the cold-boot tap check in regression: all 16 defaults must read back as 2048, each selected FIR profile must match its exact reference, and settings must restore after capture.
2. Continue v6 TX and watchdog-recovery qualification. Bounded RF frames now pass at 9–12 µs, with mixed CRC failures at 9 µs; 8 µs produces no TX frames. The current runs do not prove watchdog recovery or BER improvement.
3. The matched profile-2 RF readout comparison is 79,164 B/s at 2 Mbaud vs 126,048 B/s at 4 Mbaud for 16,380 complex samples, excluding Nios setup/verification. Run repeats and include measured setup and verification separately.
4. The current 91a0-SOF GUI batch passes as a bounded 12-capture run: six synthetic and six passive RF snapshots, 196,560 complex samples, exact raw/FIR, both UART liveness checks and restored settings. The earlier one-pair A-liveness failure remains historical. Continue to require continuous-coverage/recovery and full host-delivery accounting; GUI transport success is separate from modem CRC results.
5. Verify all three radio paths and GUI applied-controls/capture provenance together. Current-image SPI/FIR and RF Link Lab GUI runs pass bounded controls/readback checks. The independent saved-raw audit passed byte integrity and blind re-decode for all 172 unique captures, including the four-capture browser group; the 10 µs CLI and GUI results remain separately reported. Preserve the mixed 9 µs CRC results and 8 µs zero-TX-frame negative result. The 100,000-bit qualification target and automatic watchdog-recovery test remain open.

The checkpoint07 controller RTL extends the radio text bound to 255 bytes; its
boundary test accepts lengths127,128,255 and rejects256. The final SOF,
generated VDS and project ZIP built successfully; cold boot, profile guards,
recovery and SPI/FIR checks passed. [Notebook09](../notebooks/09_spi_iq_fir.ipynb)
has all 23 default/offline cells executed successfully; build, program and
capture actions remain explicit.

**Exit:** cold boot reads back the selected 16 taps, same-capture FPGA FIR/meter outputs match the independent checker, PMOD A/RFS2 paths are revalidated, and a repeatable continuous-run report measures loss, recovery and end-to-end throughput. Compare UART/SPI only at matched source and settings; keep UART if SPI does not improve useful captured data rate reliably.

### 3. Qualify and frame QPSK

The four-state phase-pulse gate passed, then v5 was flashed and verified with startup identity `TX_PROBE,v=5` and application SHA-256 `057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`. BPSK regression passed 4/4 captures with 4 valid frames and 1/176 coded → 0/32 payload errors. See [QPSK qualification](QPSK_QUALIFICATION.md) for the framed RF runs and limits.

Framed QPSK showed a clear timing boundary. The 8 µs QPSK-001 run acquired no frames: TX reported zero completed frames and 5,080 missed slots. Retain it as a negative result. At 12 µs, QPSK-002 yielded four valid frames in eight captures in the original proof; the improved blind receiver later recovered five valid frames from those same captures, with three acquisition failures and 0/220 coded → 0/40 payload errors. That receiver reanalysis is not new RF evidence. At 10 µs, QPSK-003 acquired 12/16 captures, with six CRC-valid and six CRC-failed frames, four acquisition failures, 112/528 coded errors and 19/96 payload errors. At 12 µs, QPSK-004 used 32 new captures and recovered 21 valid frames, with 11 acquisition failures, no CRC failures among acquired frames, and 0/924 coded → 0/168 payload errors. The checker default is now 12 µs.

Checkpoint 06 also decoded one QPSK-004 frame after the host supplied its 22 recovered symbols rotated −135° to match the FPGA map: 0/44 coded errors → 0/8 payload errors and valid CRC. The FPGA kernel took 3,100 cycles (62 µs at 50 MHz); the JTAG transaction took 68.328 s. This replay does not move synchronization into FPGA; raw-IQ carrier, timing and frame recovery remain host work.

**Next exit:** extend QPSK to at least 100,000 payload bits across independently captured runs and operating points; retain acquisition failures, CRC failures and exact denominators. Evaluate the 12 µs timing margin and consistency, then qualify the host-to-FPGA replay path as a separate throughput/evidence step. The integrated SPI/FIR path has bounded cold-boot and RF evidence; continuous coverage and repeated matched-rate measurements remain open. V6 normal boot now passes; qualify watchdog recovery, TX frames and GUI liveness. Do not claim BER improvement without new measurements. Keep 16/64-QAM RF gated on amplitude-linear transmitter evidence.

### 4. Gate amplitude modulation on a proven transmitter

The existing original-ESP32 frame path changes phase through brief scalar-frequency increments. It does not provide arbitrary-IQ playback or qualified amplitude-linear symbols. Before 16-QAM or 64-QAM RF work, prove a real transmitter path's sample format, rate, buffer capacity, update timing, output level, compression, image leakage and EVM on the exact board and settings. A supported replacement transmitter is an option only after those measurements.

**Exit:** measured amplitude and phase error support the selected constellation at the intended symbol rate and backoff, with clipping/compression and EVM evidence. Until this gate passes, keep QAM work in clearly identified Python or FPGA loopback.

### 5. Extend the reusable modem and FPGA receiver

The long-term signal chain is:

```text
TX: payload → CRC/FEC → mapper → frame/training → pulse shaping → qualified RF playback
RX: IQ capture → sync/CFO/timing → matched filter/equalizer → soft demap → Viterbi/CRC/BER
```

The Python reference already covers the four constellations, framing and impairment studies. Checkpoint 06 implements symbol-level mapping/demapping and K=7 FEC, but receives host-synchronized symbols rather than raw RF. Add acquisition/timing/frequency/phase stages to FPGA only with explicit stream formats, fixed-point scaling, frame markers and independent reference checks. The existing FPGA FIR and DDC are not a complete modem synchronizer.

**Exit:** per-block vectors pass for ideal and impaired inputs; FPGA handles real capture samples through acquisition to decoded frame without host symbol decisions; lock loss, reacquisition, CRC and BER counters have tested denominators. Report post-fit resources and timing from the actual build.

## Evidence presentation

Keep source and processing provenance visible: Python synthetic, FPGA-generated, FPGA replay of host-recovered symbols, or actual RF capture. Show applied settings and readbacks, capture/frame IDs, acquisition and CRC failures, coded and payload errors with denominators, and the observation window. Display constellations only as recovered symbols when synchronization has actually occurred. The independent monitor is a separate observation, not a coherent antenna or second unique-delivery count.

For QAM, define normalized mapping, bit order, pilots, training, filter delays, quantization and signed soft metrics in a versioned waveform contract with golden vectors. Compare EVM using a declared reference normalization and state which gain/phase/equalizer corrections were removed. EVM improvement does not by itself establish lower BER.

## References

- [Current real-RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md)
- [BER qualification CLI, API and results](BER_QUALIFICATION.md)
- [QPSK phase-state qualification procedure](QPSK_QUALIFICATION.md)
- [Three-radio modem/FEC foundation and BER accounting](SDR_MODEM_FEC_PLAN.md)
- [Modem implementation status](MODEM_IMPLEMENTATION_STATUS.md)
- [Original ESP32 TX investigation](ESP32_TX_INVESTIGATION.md)
- [Wi-Fi gateway plan](WIFI_GATEWAY_FPGA_PLAN.md) (separate application)
