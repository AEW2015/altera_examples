# Plan A — Native Wi-Fi 64-QAM over the air

Status: native Wi-Fi 64-QAM OTA is verified. PMOD B independently received
8/8 known PMOD A packets at 54 Mb/s on channel11 with matching payloads and clean
RX status. In a separate raw-IQ path, Stage11 Nios software decoded one known
92-byte packet from RFS2 IQ, with L-SIG RATE12/length92 and matching DATA FCS.
The real capture used conjugation and four DATA symbols; the computed and
received FCS matched `0x94dce7e8`. This is a finite CPU-software milestone; raw
BER, a 100,000-bit trial and RTL acceleration remain open. The earlier
first-capture acquisition failure is historical and retained in the
implementation status.
See [implementation status and next gates](WIFI64_IMPLEMENTATION_STATUS.md).
Hardware: installed original ESP32s, Atum A3 Nano / Agilex 3.
Host: control and display only. No runtime host synchronization, FFT, equalization,
demapping, FEC, CRC, reference generation or BER calculation.

## What this demonstrates

Send known packets through an ESP32's native 802.11g PHY, receive them as raw IQ
on a second ESP32, and decode them inside the FPGA. The transmitter's Wi-Fi
hardware performs its own scrambling/FEC/QAM/OFDM. This is genuine OTA 64-QAM,
but it is **not FPGA-generated TX IQ**. [Plan B](CUSTOM_IQ_64QAM_OTA_PLAN.md)
covers that separate goal.

```mermaid
flowchart LR
    P[FPGA/Nios: known payload + sequence] --> T[PMOD A ESP32: Wi-Fi FEC / 64-QAM / OFDM]
    T -. 2.462 GHz RF .-> R[RFS2 ESP32: raw IQ]
    R --> C[FPGA: CRC-qualified capture RAM]
    C --> S[FPGA/Nios: acquisition / CFO / timing]
    S --> F[FPGA: FFT / channel estimate / equalizer / pilots]
    F --> D[FPGA: soft demap / deinterleave / depuncture]
    D --> V[FPGA: Viterbi / descramble / CRC / BER]
    V --> H[Host: display measured results]
    T -. independent packet observation .-> M[PMOD B ESP32: PHY metadata + packet monitor]
    M --> C
```

Nios V is a processor inside the FPGA. A first implementation may put some
fixed-point acquisition/control algorithms there, but must label Nios software
versus RTL/IP explicitly. The host never fills in a missing runtime DSP stage.
Offline Python reference vectors and verification are allowed as development
checks; their results must not become the live receiver's output.

### Verified finite-burst milestone

The native monitor observed PMOD A's bounded channel11 burst as8/8 packets at
RATE12 (54 Mb/s), SIG mode0, RX state0 and matching bodies. Separately, the
Stage11 Nios C receiver processed a real RFS2 source0 capture (nominal40MS/s,
16,380 CI8 samples, conjugation enabled) and decoded RATE12, length92, four DATA
symbols/192 real Q13 points and a matching payload. Computed and received FCS
were both `0x94dce7e8`; the known offline 92-byte payload matched for run
2026102111, packet0, seed1. Nios processing took 7,515,341,840 ticks
(150.3068368s at50MHz). The source, native TX and monitor proofs are recorded in
`cyberether/run/wifi64-raw-native-ota-007.json`.

This establishes one captured-packet decode using Nios CPU software. It does
not establish raw BER, a 100,000-bit denominator, RTL acceleration or a
continuous streaming receiver. Earlier acquisition-failure results describe a
different capture/run and remain valid historical evidence.

## Roles and first operating point

| Item | Initial setting / purpose |
|---|---|
| PMOD A ESP32 | New, separate native packet TX firmware; preserve the v6 phase-pulse image |
| RFS2 ESP32 | Raw-IQ RX; first qualify nominal 40 MS/s, then FPGA decimate to 20 MS/s |
| PMOD B ESP32 | Independent promiscuous monitor, reporting actual packet PHY rate, RSSI and identity |
| Wi-Fi format | Legacy non-HT OFDM, 20-MHz channel, initial target 54 Mb/s |
| Modulation / code | 64-QAM, convolutional rate 3/4 at 54 Mb/s; 48 Mb/s / rate 2/3 is a later second point |
| Channel / gain | Explicitly configured and read back; choose a locally valid channel after checking occupancy |
| Payload | Known PRBS plus run/packet IDs from FPGA/Nios; no unrelated network credentials required |
| Host | Start/stop/settings commands, transport, plots, downloads; display device-computed metrics |

The rate is a PHY rate, not useful application throughput. A successful rate
configuration call does not prove what went over the air. Native Wi-Fi rate
selection and legacy 64-QAM parameters are documented in the sources below.

## A0 — Freeze the interfaces and protect the current demo

- Inventory actual chip/MAC, SDK, application UART pins and firmware/image hashes.
  Use RFS2 UART GPIO1/3 and PMOD A application UART GPIO17/16; its ROM loader uses
  the existing J2 wiring. Keep PMOD B's existing SPI configuration until its own
  monitor update is separately prepared.
- Create a separate firmware build profile and FPGA checkpoint; retain replay06,
  SPI07, preamble08 and the working BPSK/QPSK TX image. Do not silently extend an
  old programming manifest to cover changed source.
- Preserve full private flash/NVS backups and a documented restoration path.
  Build and test firmware before requesting the required manual PMOD resets.
- Define source tags: `ota-native-wifi64`, `fpga-test-vector`, and `saved-ota`.
  Keep received IQ distinct from any diagnostic reference or reconstructed plot.

Exit: reviewed formats, pin routing, rollback files and reproducible build commands.

## A1 — Native 64-QAM packet transmitter and independent monitor

Implement a bounded packet-TX application using the pinned original-ESP32 SDK:

1. Initialize the native Wi-Fi driver without association, automatic scanning or
   a background transmit loop. Select legacy 802.11g, channel and power settings.
2. Configure the packet TX rate using the API available in the pinned SDK;
   start with `WIFI_PHY_RATE_54M`. Do not transplant another chip's SDK ABI.
3. Transmit a supported non-QoS test frame with known payload, source address,
   sequence policy and MAC/FCS behavior. Verify whether the driver changes any
   header fields or generates the FCS. Use a sequence that the receiver can
   distinguish from other Wi-Fi traffic.
4. Expose INFO / CONFIG / ARM / bounded START / STOP / STATUS, with job IDs,
   requested rate, packet counts, driver completion/failure counts and timeouts.
   Only an explicit job starts RF; power-up, flashing and opening a viewer do not.
5. Use short packet trains with enforced quiet time. Initial engineering limit:
   at most 16 short packets per job, at least 2 ms between packets, a 100 ms
   absolute job deadline, and at least 2 seconds between jobs. The controller
   enforces these bounds. Record packet airtime estimates separately from the
   total job duration; neither is calibrated radiated power.
6. PMOD B independently records the received legacy PHY rate and matching packet
   IDs. Include TX failures and missing observations. Broadcast operation avoids
   ACK-driven retries, subject to verifying actual driver behavior.

Exit: matching native frames observed over RF at the actual 54-Mb/s rate, STOP
and idle verified, bounded job behavior tested. This establishes packet-level
64-QAM transmission, **not a raw-IQ constellation or pre-FEC BER result**.

## A2 — Qualify the raw-IQ capture path at Wi-Fi bandwidth

- A complete 20-MHz legacy OFDM waveform does not fit the current 16-MS/s
  capture profile. Qualify original-ESP32 RX40, analog bandwidth, signed IQ
  packing, channel frequency and gain against known signals.
- RFS2 UART supports burst transfer separately from its RF sample clock. Keep
  capture buffering on the ESP32/FPGA; slow UART readout does not reduce the RF
  sampling rate, but causes gaps between snapshots.
- At nominal 40 MS/s, 16,380 samples span about 409.5 microseconds. Select a short
  test packet and capture window with enough preamble and complete payload.
  Count truncated frames and captures without a packet.
- Existing PMOD B SPI firmware and FPGA profile are qualified at 16 MS/s. Do not
  claim a 40-MS/s SPI path until both firmware and FPGA framing/profile guards
  are extended and tested. RFS2 UART is the initial wideband route.
- Make FPGA/Nios arm the receiver before starting a bounded TX train. Add job,
  sequence, CRC and configuration association. A GPIO event or UART receipt
  timestamp is not the RF sample-start timestamp.

Exit: fresh, CRC-qualified raw RF captures at the required bandwidth, held in
FPGA RAM, with matching device/job/configuration provenance. No host IQ synthesis.

## A3 — Build and validate the receiver, block by block

| Stage | Work inside FPGA / Nios | Standalone verification |
|---|---|---|
| Input conditioning | Anti-alias FIR and 40→20-MS/s decimation; preserve timing metadata | Tones, impulse, alias rejection, saturation and passband tests |
| Acquisition | STF detection, coarse CFO, LTF timing and fine CFO | Known offsets, truncation, no-signal and wrong-preamble cases |
| OFDM | CP removal, 64-point FFT; 48 data and 4 pilot subcarriers | Bin order, FFT scaling, CP boundaries and known subcarrier vectors |
| Channel recovery | LTF channel estimate, equalization, pilot polarity and common-phase tracking | Gain/phase/multipath/CFO fixtures; fixed-point errors and clipping |
| L-SIG | BPSK demap, deinterleave, rate-1/2 decode, parity/tail/length validation | All supported RATE values, bad parity, impossible length and truncation |
| 64-QAM DATA | Correct Wi-Fi Gray labels/bit order; max-log metrics; 288 coded bits per OFDM symbol | Exhaustive 64-point labels, noise, metric sign and quantization |
| FEC | Per-symbol deinterleaving, rate-3/4 depuncturing with erasure LLRs, Viterbi | Puncture phase, SERVICE/tail/pad boundaries, injected errors |
| Packet / metrics | Scrambler recovery, descrambling, FCS, identity, expected-bit comparison | Known packets, corrupted frames, sequence wrap and CRC failures |

L-SIG and the preamble do not use 64-QAM. Plot only validated DATA subcarriers
as the recovered 64-QAM constellation. Require decoded legacy RATE/LENGTH and
matching native-monitor metadata before labeling a capture 54-Mb/s 64-QAM.

The current checkpoint06 modem is not a drop-in Wi-Fi decoder: it has a 256-bit
payload limit, unpunctured rate-1/2 coding and a symbol-rate input, and lacks the
puncturing and direct soft-LLR interface required by the Wi-Fi DATA path. The
successful Stage11 packet used a separate Nios C software receiver; it did not
remove these checkpoint06 limitations. RTL/IP acceleration still needs an LLR
input mode and sufficient frame/traceback capacity, or verified streaming
Viterbi. Budget SERVICE, MAC, payload, FCS, tail and pad bits; freeze encoder
polynomials, ordering and scrambler conventions against independent Wi-Fi
vectors before the RTL RF path is qualified.

Use native FFT/FIR IP or verified RTL, and use DSP/memory inference deliberately.
A Nios-only prototype is an explicitly labeled functional milestone; it does not
qualify the corresponding stage as accelerated RTL. Report fit, timing and
per-stage cycles after each hardware change.

Exit: a complete real RF packet yields device-computed payload and FCS, with
constellation/equalizer/LLR evidence. Runtime DSP remains off the host.

## A4 — BER, loss and display

- FPGA/Nios produces pre-FEC coded-bit errors only when the expected transmitted
  bitstream is known, including scrambling, interleaving and puncturing. State
  exactly which bits contribute to that denominator; do not count erasures or
  untransmitted punctured bits as received bits.
- Compare decoded payload against FPGA-generated expected payload, including
  decodable frames whose FCS fails. Keep acquisition failures, L-SIG failures,
  unknown identities, truncation, missing packets, native TX failures and
  duplicates in separate counters. Do not manufacture BER for unacquired frames.
- Native ESP32 packet reception alone often exposes successfully decoded packets;
  that is insufficient to claim raw pre-FEC BER. Label packet delivery/PER and
  raw-IQ BER as distinct measurements, with explicit denominators.
- Reach at least 100,000 uniquely identified payload bits per qualified RF
  operating point using spaced bursts. Extend the first tiny packet format only
  after decoder capacity and packet identity are verified. Keep captured versus
  unobserved transmitted traffic distinct because reception is sparse.
- Sweep measured RF operating conditions, initially TX backoff and RX gain.
  Report measured EVM/RSSI and calibration limits. Do not rename a vendor power
  code as SNR or reuse the simulated 12/16/20-dB noise axis as a measured RF axis.
- Display a compact paired layout: TX reference if the exact Wi-Fi waveform is
  reproducible on device, received equalized DATA symbols, decoded payload
  reconstruction, rate/FCS, pre-/post-FEC counts, failures and capture age.
  Mark transmitter PHY generation as ESP32-native, and host remapping as display
  reconstruction. The native PHY's internal TX IQ is not an FPGA mapper readback.

Exit: repeatable source-tagged OTA plots and device-computed BER/loss, with raw
capture hashes, actual RATE evidence, timing, firmware/SOF hashes and TX-off proof.

## Order and deliverables

1. A0/A1 firmware, protocol tests, build and manual-reset installation instructions.
2. Independent native packet/rate proof; retain original firmware rollback.
3. A2 wideband raw capture qualification.
4. A3 synthetic module/Questa tests, fixed-point reference checks and native VDS
   diagram; one finite raw-IQ packet has decoded on Nios, while continuous capture
   and RTL/IP acceleration remain open.
5. A4 display page, notebook, BER qualification and longer RF sweeps.

Implemented source locations: `firmware/wifi64_tx/`, `firmware/wifi64_monitor/`,
`sw/wifi64_*.h` and `fpga_hub/iq_bridge/vds_demo_11_wifi64_ota/`. PMOD A/B
independent RF reception and one finite raw-IQ packet decode are verified. BER,
100,000-bit RF qualification, continuous capture-RAM operation and RTL
acceleration remain open. See the implementation status for tested Nios modules
versus offline-only stages.

## References

- [Espressif original ESP32 Wi-Fi API](https://docs.espressif.com/projects/esp-idf/en/release-v5.4/esp32/api-reference/network/esp_wifi.html): native packet TX and rate configuration; verify the installed SDK version separately.
- [Non-HT Wi-Fi modulation/coding table](https://www.mathworks.com/help/wlan/ref/wlannonhtconfig.html): legacy 48/54-Mb/s 64-QAM parameters.
- [L-SIG fields and rate signaling](https://www.mathworks.com/help/wlan/ref/wlanlsig.html).
- [Current RF roadmap](RF_MODEM_BPSK_TO_64QAM_PLAN.md), [QPSK RF evidence](QPSK_QUALIFICATION.md), [FPGA replay scope](FPGA_64QAM_BER.md).
