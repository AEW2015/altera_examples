# RF modem roadmap: measured BPSK toward 64-QAM

Status: **framed BPSK and a preliminary framed QPSK link now work on the installed original ESP32 radios. QPSK is recovered at 12 µs symbols, but acquisition reliability and the 100,000-bit RF BER target remain open.** The [RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md) records the BPSK protocol and runs. The [QPSK qualification](QPSK_QUALIFICATION.md) records v5 installation and QPSK captures. The [BER qualification guide](BER_QUALIFICATION.md) documents the CLI, API and synthetic/RF boundaries.

## Current measured system

The installed path is PMOD A original ESP32 TX, RFS2 original ESP32 RX, and PMOD B as an independent receiver observation. The PMOD A v5 profile now sends bounded repeated 64-symbol phase-pulse BPSK and QPSK frames; it does not play arbitrary IQ. Agilex transports captures and has separately verified FIR and symbol/FEC functions. Raw-IQ acquisition, timing, demapping and frame synchronization still run on the host.

```mermaid
flowchart LR
    A[PMOD A original ESP32\nframed BPSK / QPSK phase pulses] -. 2.4 GHz RF .-> R[RFS2 original ESP32\nmain RX capture]
    A -. same RF .-> B[PMOD B original ESP32\nindependent RX observation]
    R --> F[Agilex 3\ncapture transport / optional FIR]
    F --> H[Host\nsync / symbols / FEC / CRC]
    H --> C[Evidence\nframes / BER counts]
    F -. recovered symbols .-> V[Checkpoint 06 FPGA\nsoft demap / Viterbi]
```

| Evidence | Measured result | Boundary |
|---|---|---|
| PMODA → RFS2 BPSK | 92 captures, 93 valid frames, 75/4092 coded errors → 0/744 payload errors | Earlier aggregate; sparse captures; host synchronization and FEC; hard and soft both have zero observed payload errors |
| v5 BPSK regression | 4 captures, 4 valid frames, 1/176 coded error → 0/32 payload errors | Separate regression batch after v5 installation |
| PMODA → PMODB BPSK | 4 captures, 4 valid frames, 4/176 coded errors → 0/32 payload errors | Keep separate from RFS2 totals; may observe the same transmissions |
| PMODA → RFS2 QPSK, 12 µs | Run QPSK-004: 32 new captures, 21 CRC-valid frames, 11 acquisition failures; 0/924 coded → 0/168 payload errors | Preliminary framed RF result; only 168 decoded payload bits, far below the BER qualification target |
| FPGA FIR | 32,760 complex samples; exact match to integer reference | Separate paired raw/FIR experiment, not a modem synchronizer |
| FPGA symbol/FEC replay | 1/44 coded errors → 0/8 payload errors | Host recovered symbols supplied to checkpoint 06; synchronization remains host-side |
| FPGA QPSK symbol/FEC replay | One QPSK-004 frame; 0/44 coded → 0/8 payload errors; CRC passed | 22 host-recovered symbols rotated −135° for FPGA map; 3,100 FPGA cycles (62 µs at 50 MHz), 68.328 s JTAG transaction; checkpoint 03 restored afterward |

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

The [BER guide](BER_QUALIFICATION.md) provides a reproducible seeded AWGN sweep and a saved-proof RF audit. Its current 1,000-frame, 16-byte simulation has 704 hard versus 8 soft payload errors at 4 dB on the same samples, and 0 soft errors at 6 dB (128,000 tested bits; one-sided 95% bit bound 2.3404 × 10⁻⁵ under an independent-bit assumption, with the frame bound reported separately). This is simulation, not RF. The current BPSK audit across both receivers has 100 captures / 101 CRC-valid frame observations, 80/4444 coded errors and 0/808 payload errors with both decoders. It includes the four-capture v5 regression. This demonstrates no hard/soft RF advantage at the observed errors. Receiver groups remain separate; observing one transmission on two radios does not add unique delivered packets.

Run longer, independently captured batches at fixed settings and at several controlled operating points. Retain every attempt, including capture transport failures, no-sync windows, CRC failures and decoded errors. Report exact numerators and denominators for coded bits, payload bits, complete CRC checks and capture attempts. A sparse snapshot does not establish how many RF frames were transmitted between windows; do not invent a delivery denominator.

At each point, target at least 100,000 payload bits where practical. Report a confidence bound alongside zero observed errors (for example, a one-sided 95% binomial upper bound) and avoid treating repeated processing of one capture as new RF evidence. Add deterministic synthetic tests for known CFO, timing offset, phase ambiguity, noise and CRC failures as controls; label those separately from RF. Preserve RF capture IDs and proof hashes.

**Exit:** reproducible RF batches have explicit settings, independent capture IDs, all failure counts and bit denominators; synthetic controls catch expected injected faults; confidence bounds are computed from the actual tested bits.

### 2. Measure sample transport before choosing SPI

Separate [SPI transport](SPI_TRANSPORT.md) and [SPI FPGA-meter](SPI_FPGA_METER.md) projects provide source, firmware, Questa tests and fitted images. They are qualification prototypes; physical testing is waiting for PMOD B’s programming reset. The live RF demo continues to use UART when its normal hub is loaded.

UART remains useful for bounded captures. Measure payload rate, command/turnaround time, loss, backpressure and sustained capture coverage on the actual installed path. Prototype SPI only after recording the UART baseline. Measure clock rate, framing overhead, sustained bytes/s, buffer-full behavior, dropped blocks and recovery under contention. SPI clocking is transport timing and supplies no RF sample-phase coherence.

The SPI probe and transport integration are nearing the build gate; physical SPI throughput and loss behavior have not yet been tested.

**Exit:** a repeatable report compares measured UART and SPI throughput and loss behavior on the same data contract. Keep UART if SPI does not improve useful captured data rate reliably.

### 3. Qualify and frame QPSK

The four-state phase-pulse gate passed, then v5 was flashed and verified with startup identity `TX_PROBE,v=5` and application SHA-256 `057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`. BPSK regression passed 4/4 captures with 4 valid frames and 1/176 coded → 0/32 payload errors. See [QPSK qualification](QPSK_QUALIFICATION.md) for the framed RF runs and limits.

Framed QPSK showed a clear timing boundary. The 8 µs QPSK-001 run acquired no frames: TX reported zero completed frames and 5,080 missed slots. Retain it as a negative result. At 12 µs, QPSK-002 yielded four valid frames in eight captures in the original proof; the improved blind receiver later recovered five valid frames from those same captures, with three acquisition failures and 0/220 coded → 0/40 payload errors. That receiver reanalysis is not new RF evidence. At 10 µs, QPSK-003 acquired 12/16 captures, with six CRC-valid and six CRC-failed frames, four acquisition failures, 112/528 coded errors and 19/96 payload errors. At 12 µs, QPSK-004 used 32 new captures and recovered 21 valid frames, with 11 acquisition failures, no CRC failures among acquired frames, and 0/924 coded → 0/168 payload errors. The checker default is now 12 µs.

Checkpoint 06 also decoded one QPSK-004 frame after the host supplied its 22 recovered symbols rotated −135° to match the FPGA map: 0/44 coded errors → 0/8 payload errors and valid CRC. The FPGA kernel took 3,100 cycles (62 µs at 50 MHz); the JTAG transaction took 68.328 s. This replay does not move synchronization into FPGA; raw-IQ carrier, timing and frame recovery remain host work.

**Next exit:** extend QPSK to at least 100,000 payload bits across independently captured runs and operating points; retain acquisition failures, CRC failures and exact denominators. Evaluate the 12 µs timing margin and consistency, then qualify the host-to-FPGA replay path as a separate throughput/evidence step. The new SPI path is still pending physical throughput/loss measurements. Keep 16/64-QAM RF gated on amplitude-linear transmitter evidence.

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
