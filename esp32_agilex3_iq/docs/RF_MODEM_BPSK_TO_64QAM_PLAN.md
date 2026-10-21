# RF modem roadmap: measured BPSK toward 64-QAM

Status: **framed BPSK and preliminary framed QPSK are measured on the installed original-ESP32 transmitter; the 100,000-bit RF BER target remains open. The final checkpoint07 SPI→capture-RAM→FIR image passed cold-boot and bounded hardware checks. Raw-IQ synchronization remains on the host, continuous capture is open, and a separate known PMOD A TX attempt now hangs in PHY setup before frame configuration.** The [RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md) records the BPSK protocol and runs. The [QPSK qualification](QPSK_QUALIFICATION.md) records v5 installation and QPSK captures. The [BER qualification guide](BER_QUALIFICATION.md) documents the CLI, API and synthetic/RF boundaries.

## Current measured system

PMOD A has the original ESP32 v5 phase-pulse image, PMOD B has combined SPI receiver firmware installed (SPI ON, BOOT OFF), and RFS2 retains UART RX firmware. Final checkpoint07 SOF `19ff94b02e3670587ada244a3ce6eb41aed2dbd0f21970a0db17c9dc8a06fa2b` passes fresh-boot, SPI, FIR and bounded RFS2 UART checks; source fingerprint `463977275485c8dd9412f351dfef365ca6c96b7a2ab4d4cfc8dea51d94951898`. PMOD A serial INFO works, but the known v5 TX attempt watchdog-hangs during PHY tone setup before `FRAME_CFG`; no TX frame was configured or captured in that attempt. A WDT-recovery/timing v6 build exists but is not flashed or qualified. PMOD A does not play arbitrary IQ. Raw-IQ acquisition, timing, demapping and frame synchronization for the modem still run on the host.

```mermaid
flowchart LR
    A[PMOD A v5\nphase-pulse framed TX] -. 2.4 GHz RF .-> R[RFS2 UART RX\nfirmware retained]
    R -. UART RX path retained; route recheck pending .-> H[Host modem processing\nsync / symbols / FEC / CRC]
    A -. passive RF observation .-> B[PMOD B combined SPI RX\nSPI ON, BOOT OFF]
    B --> M[Checkpoint07 FPGA\nSPI → capture RAM → FIR II]
    M --> H2[Host checker\npaired raw/FIR audit]
    H -. recovered symbols .-> V[Checkpoint 06 FPGA replay\nseparate proof]
```

| Evidence | Measured result | Boundary |
|---|---|---|
| PMODA → RFS2 BPSK | 92 captures, 93 valid frames, 75/4092 coded errors → 0/744 payload errors | Earlier aggregate; sparse captures; host synchronization and FEC; hard and soft both have zero observed payload errors |
| v5 BPSK regression | 4 captures, 4 valid frames, 1/176 coded error → 0/32 payload errors | Separate regression batch after v5 installation |
| PMODA → PMODB BPSK | 4 captures, 4 valid frames, 4/176 coded errors → 0/32 payload errors | Keep separate from RFS2 totals; may observe the same transmissions |
| PMODA → RFS2 QPSK, 12 µs | Run QPSK-004: 32 new captures, 21 CRC-valid frames, 11 acquisition failures; 0/924 coded → 0/168 payload errors | Preliminary framed RF result; only 168 decoded payload bits, far below the BER qualification target |
| FPGA FIR | 32,760 complex samples; exact match to integer reference | Separate paired raw/FIR experiment, not a modem synchronizer |
| Integrated checkpoint07 SPI + FIR | Fresh boot reads all 16 default taps (2048); exact Hamming result for 16,380 complex samples; profile/settings restore verified | Final SOF `19ff94b0…`, source fingerprint `46397727…`; cold-boot proof `spi-fir-boot-fixed-synthetic-001` |
| Checkpoint07 route guards/recovery | Invalid 40 MHz/2417 MHz profile returns error128; 1024 samples returns error32 without arming; subsequent valid SPI raw and four passive RFS2 UART0 captures pass | Proof `spi-profile-rejection-recovery-001`; PMOD A UART INFO works but its TX setup watchdog-hangs before frame configuration |
| Checkpoint07 transport rates | Matched profile-2 RF capture, 16,380 complex samples: 79,164 useful input B/s at 2 Mbaud vs 126,048 B/s at 4 Mbaud | Excludes Nios setup/verification; FPGA CS-active ingress remains 591,134 B/s. Matched evidence on earlier 6b980718 image; final-image GUI batch stopped after one verified pair and an A INFO timeout |
| Final-image browser RF check | One passive RF Hamming capture at 4 Mbaud passed; raw/FIR payloads bit-exact and no JavaScript errors | `browser-final-single-001`; separate from the failed GUI liveness soak and does not qualify A TX or continuous operation |
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

The [BER guide](BER_QUALIFICATION.md) provides a reproducible seeded AWGN sweep and a saved-proof RF audit. Its current 1,000-frame, 16-byte simulation has 704 hard versus 8 soft payload errors at 4 dB on the same samples, and 0 soft errors at 6 dB (128,000 tested bits; one-sided 95% bit bound 2.3404 × 10⁻⁵ under an independent-bit assumption, with the frame bound reported separately). This is simulation, not RF. The extended BPSK audit has 420 captures / 441 acquired frames, 438 CRC passes / 3 failures, 337/19404 coded errors → 1/3528 payload errors. The extended QPSK audit has 324 captures / 163 acquired frames, 153 CRC passes / 10 failures, 161 no-acquisition captures and 200/7172 coded → 37/1304 payload errors. All 744 unique raw captures passed length/CRC/SHA integrity checks; all 580 new captures were independently blind-redecoded without a payload oracle. Repeated payload/settings groups are not a calibrated BER curve, and these results do not establish a soft RF advantage or meet the 100,000-bit target. Receiver groups remain separate; observing one transmission on two radios does not add unique delivered packets.

Run longer, independently captured batches at fixed settings and at several controlled operating points. Retain every attempt, including capture transport failures, no-sync windows, CRC failures and decoded errors. Report exact numerators and denominators for coded bits, payload bits, complete CRC checks and capture attempts. A sparse snapshot does not establish how many RF frames were transmitted between windows; do not invent a delivery denominator.

At each point, target at least 100,000 payload bits where practical. Report a confidence bound alongside zero observed errors (for example, a one-sided 95% binomial upper bound) and avoid treating repeated processing of one capture as new RF evidence. Add deterministic synthetic tests for known CFO, timing offset, phase ambiguity, noise and CRC failures as controls; label those separately from RF. Preserve RF capture IDs and proof hashes.

**Exit:** reproducible RF batches have explicit settings, independent capture IDs, all failure counts and bit denominators; synthetic controls catch expected injected faults; confidence bounds are computed from the actual tested bits.

### 2. Integrate and qualify sample transport

Separate [SPI transport](SPI_TRANSPORT.md) and [SPI FPGA-meter](SPI_FPGA_METER.md) projects pass bounded synthetic and channel-8 RF hardware qualification on PMOD B. The latest repeat batch contains 24 captures (12 synthetic and 12 RF), 393,120 complex samples and commits 1–24; independent NumPy meter values and hashes passed. Final checkpoint07 cold-booted with all 16 default coefficients read as 2048, then matched the exact Hamming FIR reference for 16,380 complex samples and restored settings. A realistic Questa READY regression fails on the first stale-HIGH implementation and passes with the observed-LOW-then-HIGH reservation handshake. Profile rejects (error128 for invalid rate/frequency; error32 for invalid sample count, no arm) were followed by valid SPI raw and four passive RFS2 UART0 captures. PMOD A UART INFO responds, but v5 TX is currently unavailable after a watchdog hang in PHY setup before frame configuration.

Retain the existing UART measurements as the comparison baseline. Measure payload rate, command/turnaround time, loss, backpressure and sustained capture coverage on the actual installed path. For integrated SPI, measure clock rate, framing overhead, sustained bytes/s, buffer-full behavior, dropped blocks and recovery under contention. SPI clocking is transport timing and supplies no RF sample-phase coherence.

At 5 MHz, FPGA-counted CS-active payload ingress is about 591 kB/s; complete host captures reach about 106–110 kB/s because UART egress and sequential control remain limiting. CS-active time excludes READY wait and inter-transaction/UART gaps. These are distinct measurements, not a sustained SPI-to-host speedup.

**Completed evidence:**

Final checkpoint07 SOF `19ff94b0…` passed fresh-boot coefficient readback and bounded SPI/FIR qualification. Startup read all 16 default taps as 2048; the exact Hamming test processed 16,380 complex samples and settings restoration passed. Invalid profile controls returned error128 (40 MHz/2417 MHz) and error32 (1024 samples, no arm); a subsequent valid SPI raw capture and four passive RFS2 UART0 captures passed. The profile-rejection/recovery proof is kept separate from RF BER. PMOD A UART INFO works before TX, but a known v5 TX attempt watchdog-hangs in PHY setup (`chip_sleep_prot_en` → `esp_phy_wifi_tx_tone`) before `FRAME_CFG`, with no RF samples; afterward A becomes UART-unresponsive until a manual reset. The v6 WDT-recovery/timing application SHA-256 `baac3d3881539cb4321c09bda7245b7a3823762d2b3639e6e21c7d9579fc1dbb` is built, not flashed; automatic reboot recovery is not yet hardware-proven, and its 500 ms job bound begins after blocking PHY setup rather than including setup time. The previous checkpoint03 127-byte text limit caused an extended TX configuration response to be rejected; its retained failed job remains excluded from qualified RF evidence.

**Next execution checklist:**

1. Keep the cold-boot tap check in regression: all 16 defaults must read back as 2048, each selected FIR profile must match its exact reference, and settings must restore after capture.
2. Requalify PMOD A TX. The v5 PHY setup hang occurs before `FRAME_CFG`; test the separate unflashed v6 recovery build only after the board reset is available, and do not count it as RF evidence until complete frames are captured.
3. The matched profile-2 RF readout comparison is 79,164 B/s at 2 Mbaud vs 126,048 B/s at 4 Mbaud for 16,380 complex samples, excluding Nios setup/verification. Run repeats and include measured setup and verification separately.
4. Complete continuous capture/recovery soak and report accepted/rejected/drop counts, buffer pressure, recovery and full host delivery. The final-SOF GUI batch failed its A-liveness check after one synthetic SPI/FIR pair; cleanup verified UART was restored to 2 Mbaud and FIR settings restored. A separate final-SOF one-shot RF Hamming/FIR browser check passed bit-exactly, but does not replace the soak. Repeat after manual A reset and transmitter recovery.
5. Verify all three radio paths and GUI applied-controls/capture provenance together. RFS2 passive UART0 has four passing captures; PMOD A UART INFO works, but PMOD A TX remains blocked by the PHY setup hang.

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

**Next exit:** extend QPSK to at least 100,000 payload bits across independently captured runs and operating points; retain acquisition failures, CRC failures and exact denominators. Evaluate the 12 µs timing margin and consistency, then qualify the host-to-FPGA replay path as a separate throughput/evidence step. The integrated SPI/FIR path has bounded cold-boot and RF evidence; continuous coverage and repeated matched-rate measurements remain open. Recover PMOD A TX after the PHY setup watchdog, then repeat the GUI liveness soak. v6 is not installed; treat a transmitter timing change as a separate optional experiment behind explicit UI/readback, regression and RF gates. Keep 16/64-QAM RF gated on amplitude-linear transmitter evidence.

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
