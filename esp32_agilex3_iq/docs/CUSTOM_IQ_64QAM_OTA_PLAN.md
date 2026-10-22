# Plan B — FPGA-generated 64-QAM through an ESP32 RF transmitter

Status: research-gated on the installed original ESP32s. No arbitrary-IQ TX
or custom 64-QAM RF result is established on these modules.
Offline review identified an original-chip attenuation-only probe candidate;
see [research](ORIGINAL_IQ_TX_RESEARCH_20261021.md) and
[implementation status](WIFI64_IMPLEMENTATION_STATUS.md). RF qualification is pending.
Host: control and display only. FPGA/ESP32 perform the live waveform generation,
reception, synchronization, decoding and error measurement.

## Goal and existing evidence

```mermaid
flowchart LR
    B[FPGA: payload / sequence / CRC] --> E[FPGA: scrambler / FEC]
    E --> Q[FPGA: Gray 64-QAM / pilots / framing]
    Q --> P[FPGA: pulse shaping / scaling / IQ packing]
    P --> U[UART or SPI: preload waveform]
    U --> T[PMOD A ESP32: proven IQ injection / DAC / RF]
    T -. 2.4 GHz RF .-> R[RFS2 ESP32: raw IQ capture]
    R --> S[FPGA: acquisition / timing / carrier / equalizer]
    S --> D[FPGA: demapper / Viterbi / CRC / BER]
    D --> H[Host: plots and controls]
    T -. independent observation .-> M[PMOD B ESP32 monitor]
```

The input is a known waveform generated inside the FPGA, not packet bytes
handed to the ESP32's Wi-Fi modem. [Plan A](NATIVE_WIFI_64QAM_OTA_PLAN.md)
is the separate native Wi-Fi alternative.

| Available today | Missing for this goal |
|---|---|
| Original-chip BPSK/QPSK phase-pulse RF evidence | Independent, sufficiently fast amplitude and phase control for all 64 states |
| Original-chip raw-IQ RX and scalar tone controls | Proven arbitrary waveform source selector / sample feed into original-chip TX |
| FPGA 64-QAM mapper, soft demapper and Viterbi replay | Live waveform shaping, raw-IQ synchronization and integrated RF decoding |
| Sparse UART and fixed-profile SPI capture | Qualified bidirectional custom-IQ transport / waveform ownership |
| Published S3/S31 SRAM playback implementation | Proof that any equivalent mechanism exists on the installed original ESP32s |

The chip having a Wi-Fi TX DAC does not establish an accessible arbitrary-IQ
input. Our existing phase controls are not an SRAM-to-DAC playback engine.
Do not label a native Wi-Fi packet or generated replay as completion of this plan.

The current [execution checklist](CUSTOM_QAM_EXECUTION_PLAN.md) narrows the next
step to the independently measured amplitude gate, with guarded programmer
support and a one-job capture controller. Compile and mock-test success do not
establish a working IQ input or RF QAM transmitter.

## B0 — Preserve the baseline and define the experiment

- Record chip/revision, MAC, SDK/PHY/ROM hashes, firmware, active SOF and wiring.
  Preserve private flash/NVS backups and known-good recovery images.
- Keep research firmware separate from v6 and the normal monitor. Its startup
  must leave RF off. Select the correct application versus bootloader UART pins.
- Record every hypothesis, source/disassembly reference, intended register field,
  expected result, readback, measured result and restoration result. No blind
  register sweeps or reuse of S3 addresses on the original chip.
- Set explicit research review checkpoints: one initial offline investigation
  session (suggested cap: four hours), then one narrowly scoped evidenced probe
  at a time. These are decision points, not success promises. Stop advancing a
  hypothesis that adds no new evidence, and record why.

Exit: recoverable target and a concrete hypothesis. Unresolved is a valid result.

## B1 — Find and qualify an original-chip waveform input

### Primary investigation: direct IQ injection / playback

Build on [the existing source/ROM investigation](ESP32_TX_INVESTIGATION.md):

1. Trace TX data-source selection, diagnostic SRAM ownership, clock gates,
   static-IQ or playback controls and patched runtime PHY function tables.
2. Establish actual argument widths and sample packing: signedness, I/Q order,
   integer scaling, stride, buffer ownership, alignment, sample count, rate,
   start/stop, looping and completion. Verify against the exact chip revision.
3. Compare the proven S3/S31 path as an architectural reference only. A similar
   register address or a TX dump buffer is not evidence of original-chip playback.
4. After an evidenced control path exists, build a guarded diagnostic. Start
   with a minimum-duration, low-level, preloaded pattern and automatic stop.
   Bound RF to at most 50 ms per probe and require at least two seconds quiet
   time. Enforce length/amplitude/rate limits and refuse overlapping jobs.
5. Compare at least two distinct uploaded IQ patterns with the same RF settings.
   Independent RX must recover the commanded change in amplitude and phase.
   Confirm on/off behavior and that changing the sample buffer changes RF.
6. Verify abort, restoration and subsequent ordinary receiver operation. Existing
   firmware watchdog hangs mean software deadlines are not an independently
   proven RF-off guarantee; test failures explicitly instead of assuming recovery.

Exit: two distinguishable arbitrary IQ patterns measured over RF, with readbacks,
input/capture hashes, sample-rate evidence, clipping, timing and TX-off evidence.
This proves the waveform path, not 64-QAM or BER yet.

### Secondary hypothesis: FPGA-driven polar modulation

If only the scalar tone path is accessible, investigate bounded amplitude/phase
updates as a **separate polar-modulation backend**:

- Characterize amplitude transfer and settling, phase increments, residual FM,
  update jitter, spurs and behavior when gain changes during transmission.
- A 64-QAM grid needs its commanded radii and phases, not just the four QPSK
  phase states. Verify every requested Cartesian point after conversion to
  amplitude/phase, including transitions between distant points.
- Put Cartesian-to-polar conversion and symbol scheduling in FPGA logic if this
  route advances. Qualify the ESP32 control path's actual update bandwidth.
- Do not call a gain/phase-register experiment raw sample playback. It can only
  satisfy the custom waveform goal if its complete recovered waveform, EVM and
  framed BER meet the same acceptance tests.

Exit: either a measured viable low-rate backend or a documented rejection.
Do not merge separate steady tones into a fabricated 64-QAM constellation.

## B2 — Decision gate: continue on original ESP32 or select new TX hardware

| Outcome | Next action |
|---|---|
| Direct original-chip IQ input is demonstrated | Continue with the installed transmitter and record its measured limits |
| Only a useful polar backend is demonstrated | Continue as explicitly labeled polar TX; qualify QAM states/transitions first |
| No usable source is established | Mark the original-chip backend unresolved; continue Plan A independently |
| A supported transmitter is later available | Port the same FPGA-generated waveform to S3/S31 playback and qualify it separately |

No hardware purchase or module replacement is assumed. The upstream S3/S31
implementation is a demonstrated starting point for IQ playback, not a guarantee
that a particular board or 64-QAM configuration meets our EVM/BER targets.

## B3 — Transport and waveform buffer

Only optimize transport after B1 proves that it has a real TX sink.

- Preload, CRC-check and acknowledge a finite waveform before RF begins. FPGA
  supplies the waveform; the ESP32 transports/presents it to the RF engine.
- Initial UART preload is acceptable. At 2 Mbaud, 8N1, the ideal ceiling is
  200 kB/s, or 50 kcomplex samples/s for four-byte CI16. This cannot continuously
  feed a 40-MS/s DAC, but can load a finite buffer for a short high-rate burst.
- Reuse SPI infrastructure only after defining TX framing, ready/busy, CRC,
  sample counts, sequence IDs and ownership. Current PMOD B capture SPI is an RX
  protocol, not an already working TX waveform interface.
- Discover original-chip limits rather than assuming S3 sample RAM dimensions.
  Reject oversized/unaligned buffers, underrun and stale sequence IDs.
- Include pre/post waveform guards and pulse-shaping transients. Avoid a phase
  or amplitude discontinuity at a loop seam; report looping separately from a
  single burst. Start/stop/timeout logic must work without a host polling loop.

Exit: exact input-byte delivery and finite, reproducible RF playback; no continuous
streaming claim. Keep full hashes and image/backend identity.

## B4 — FPGA TX chain and independent qualification

| Stage | Implementation / test |
|---|---|
| Payload/reference | FPGA/Nios PRBS + run/packet IDs; separate training, header, payload and CRC |
| Scramble/FEC | Explicit K7 rate-1/2 initial code and termination; exact reference vectors |
| Mapping | Exhaustive BPSK, QPSK, 16-QAM, then Gray 64-QAM labeling and normalization |
| Framing | Robust acquisition training, known pilots and header; do not require decoding 64-QAM to find the frame |
| Shaping | RRC or another explicitly specified waveform; FPGA interpolation, group delay and fixed-point saturation |
| Scaling | Measured transmitter backoff/compression and at least the required distinct QAM levels |
| Playback packing | Exact transport/backend IQ representation; verify I/Q order, sign, gain and clock |

Start at a low measured symbol rate with enough samples per symbol and a burst
that fits the proven buffer. Do not select a target rate solely from CPU clock
or advertised Wi-Fi data rate. Advance BPSK → QPSK → 16-QAM → 64-QAM only after
measuring the preceding mode over RF.

For 64-QAM, test all 64 states in one time-ordered received capture, then changing
random symbols with framing/FEC. Measure gain/phase error, carrier leakage, IQ
imbalance, clipping/compression, RMS EVM and transition settling. An initial
engineering EVM target such as <=5% may guide iteration, but is not a claim of
Wi-Fi standard compliance. Freeze a measured acceptance threshold before tests.

## B5 — FPGA RX chain; host display only

- Raw CI8 capture → anti-alias/matched FIR → acquisition → coarse/fine CFO →
  timing interpolation → phase/pilot tracking → equalizer → 64-QAM max-log
  metrics → Viterbi → descramble/CRC → known-payload comparison.
- Reuse the existing FIR, preamble and symbol/FEC work where their exact formats
  apply. The coarse detector is not a complete synchronizer. Extend payload and
  traceback capacity before choosing longer packets.
- Declare Nios software versus RTL/IP stages. If Nios is used for a first
  on-board prototype, label it and then accelerate measured bottlenecks. Never
  use host NumPy DSP to quietly complete a live result.
- Test modules with fixed-point vectors and Questa, then seeded impairments,
  then same-capture RF checks. Python is an offline independent checker only.
- Match frame IDs and settings across TX reference, received IQ and FPGA outputs.
  Timestamp receipt, trigger and estimated RF start separately. GPIO/GPS pulses
  do not establish shared RF phase or sample clocks.

Exit: fresh, independently received RF produces the known decoded payload inside
FPGA/Nios, with CRC and stage-level evidence. No host-generated received symbols.

## B6 — BER, presentation and final acceptance

- Count pre-FEC errors against the exact known coded stream; count post-FEC
  errors against known payload. Publish denominators, acquisition/header/CRC
  failures, truncations, missing frames, duplicates and TX failures separately.
- Keep failed but identifiable frames in BER. Do not assign zero errors to an
  unacquired frame. Require at least 100,000 unique payload bits per RF operating
  point, using short jobs with enforced cooldowns and verified TX-off state.
- Use measured RF conditions/EVM, not the replay demo's generated-noise labels.
  Treat zero observed errors as a finite measurement with a clearly scoped bound.
- Display clean FPGA TX reference, actual RX samples, equalized symbol decisions
  and decoded results. Any re-encoded/remapped post-FEC graphic is display
  reconstruction and must retain errors; it is not cleaned received IQ.
- Show backend, actual modulation, capture age, CRC/lock, EVM, BER, source/job,
  firmware/SOF hashes, processing location and TX-active indicator. Opening a
  browser, notebook or screenshot export must never start RF.

Completion requires a complete custom 64-QAM frame received over air and decoded
on board, measured EVM/BER and retained evidence. A native Wi-Fi packet, isolated
carrier, replay vector or attractive ideal grid is not completion of this gate.

## Deliverables and first next action

Proposed: `firmware/original_iq_tx_probe/`, an evidence journal,
`fpga_hub/iq_bridge/vds_demo_12_custom_qam_ota/`, bounded controller commands,
module/Questa tests, an educational notebook and a separate OTA display page.
The attenuation-only probe now exists and compiles; it is not installed or RF
qualified. Its [guide](../firmware/original_iq_tx_probe/README.md) documents
software guard limits and the initial calibration budget. The VDS receiver,
custom modulation path, notebook and OTA page remain planned.

First action: review the existing original-chip source/ROM evidence and identify
one new, concrete TX-source or amplitude-control lead. In parallel at the project
level, Plan A can advance native Wi-Fi packet transmission without assuming this
research succeeds. Installing either firmware requires the existing guided PMOD
reset sequence after the build and rollback files are ready.

## References

- [Original-chip investigation and reproducible analysis](ESP32_TX_INVESTIGATION.md).
- [Measured original-chip phase control](ESP32_PHASE_RF_RESULTS.md), [QPSK qualification](QPSK_QUALIFICATION.md).
- [Published S3/S31 arbitrary-IQ TX](https://github.com/whstudio123/esp32-iq-tx): chip-specific SRAM playback and source provenance.
- [ESP-SDR receiver scope and sample rates](https://github.com/ESPARGOS/esp-sdr): RX capability does not imply an equivalent TX injection API.
- [Current FPGA symbol-replay qualification](FPGA_64QAM_BER.md).
