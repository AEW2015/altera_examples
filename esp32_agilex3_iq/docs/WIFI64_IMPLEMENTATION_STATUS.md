# Wi-Fi 64-QAM implementation — 2026-10-21

The two OTA plans are **in progress**. Native 54 Mb/s PHY packet reception has
now been observed over the air on PMOD B, but no raw-IQ decode, BER, or custom
64-QAM transmission has been qualified. Existing port8773 still shows FPGA
symbol replay, labeled **NO RF TX**. No replacement RF results are fabricated.

```mermaid
flowchart LR
  A[PMOD A: native 54Mb/s TX<br/>firmware FLASHED] -->|actual RF| M[PMOD B: native PHY monitor<br/>2/2 payloads matched]
  A -. raw-IQ decode pending .-> B[RFS2: raw IQ40MS/s<br/>3 captures / CRC PASS]
  B --> C[Acquisition / CFO / timing<br/>NOT IMPLEMENTED in new path]
  C --> D[FFT64 / equalizer / soft QAM64]
  D --> E[Deinterleave / depuncture / Viterbi<br/>descramble / CRC]
  E --> F[Host display only<br/>OTA page pending]
```

## Implemented and tested

| Item | Evidence | Remaining limit |
|---|---|---|
| Native TX firmware | Pinned SDK build; deterministic88-byte frames; UART command tests | Normal boot verified; bounded job produced 2/2 native monitor matches at54Mb/s |
| Independent monitor firmware | Flashed and normal boot verified; bounded OTA job matched2/2 payloads | Native PHY monitor evidence only; does not decode RFS2 raw IQ |
| Bounded controller | Shared acquisition lock, explicit `--transmit`, readbacks, STOP/idle proof; fake-bridge tests and one successful native OTA job | Larger packet/error-rate trials remain open |
| Wideband transport | Three16380-sample CI8 captures, nominal40MS/s, CRCs pass; reported capture411us; no hub errors | Passive; sample clock and complete20MHz analog response not measured |
| Receiver primitives | Integer FFT64, two-LTF channel estimate, equalization, all64 QAM labels | Caller must supply acquired/CFO/pilot-corrected symbols |
| Wi-Fi DATA backend | s=3 deinterleave,3/4 depuncture, K7 soft Viterbi, SERVICE seed/descramble, FCS | 256-byte PSDU limit; not connected to live acquisition |
| Actual Nios V test | **5/5 pass on Agilex3**, fixture92-byte PSDU,4 DATA symbols, CRC107563580; corrupt FCS rejected | CPU software on device, not RTL acceleration or received RF |
| Full C receiver prototype | Synthetic40MS/s IQ through FIR, acquisition/CFO, FFT/equalizer/pilots, L-SIG,64-QAM and DATA FCS passes | Not integrated with live capture RAM or hardware-qualified; requires larger Nios RAM |
| L-SIG header backend | All8 legacy rate fixtures pass; 54Mb/s wire code12,48Mb/s code8 | Offline C/RV32I compile only; acquisition remains missing |
| Custom-TX research | Original-chip attenuation field and separate forced-gain ABI identified;1024 bitfield cases pass | Separate attenuation-only firmware compiles; not installed or RF-qualified; no arbitrary-IQ playback proof |

Nios test ELF SHA:
`674d89ee92cfd3cf7f4334359b8ee46bad1388f84a2c72e44c118ebce5772467`.
Tested FPGA image is checkpoint06 SHA `4297a6c946a7bb1381523eccd53ee99864871fb5a66c83edef6c90eb8b2f5441`.
The original monitor ELF was restored and STATUS replied with no errors after that test.
PMOD A was subsequently flashed, verified and booted normally. Its first bounded
two-packet job reported accepted=2, done=2, rate54=2, failed/rejected/other=0.
STOP and STATUS confirmed busy=0, rf=0, stop_err=0. These are transmitter
callbacks, not independent reception or raw-IQ decoding. Programming bridges
temporarily replace the runtime SOF during installation of the other module.

The PMOD B physical4MiB backup SHA-256 is
`780d150511dcd0544e16bda55045d117aab2d995cf05b0aadf7e880e19444d51`. All three
firmware images were hash-verified after flashing, and normal boot was verified
with INFO/STOP/STATUS. The bounded native OTA proof
`cyberether/run/wifi64-native-ota-002.json` completed successfully: 2/2 monitor
packets matched on channel8 at54Mb/s (RATE code12, SIG mode0, RX state0), RSSI
−17dBm, length92, and matching run/seed/body. Transport-error and drop deltas
were zero; A verified RF-off and B stopped. This is actual native PHY packet
reception over RF, not FPGA raw-IQ decoding and not BER.

The selftest uses42,804bytes of64KiB including BSS; workspace25,712bytes.
At50MHz its FFT tone test took453085 timer ticks (~9.06ms), channel/null test
423026 (~8.46ms), 64 repetitions of48-symbol demapping176552903 (~3.53s),
and one92-byte DATA backend20815151 (~416ms). These are slow CPU prototypes:
process finite captured bursts; they cannot sustain40MS/s. Move qualified stages
into streaming RTL/IP after acquisition and conventions are validated.

An initial hardware attempt used optional `mcycle`, timed out, and restored the
monitor. Replacing it with this system's memory-mapped `mtime` passed. The final
runner snapshots the exact ELF before download, avoiding a concurrent build race.

Local ignored evidence:

- `cyberether/run/wifi64-wideband-passive-1792630367872929318/`
- `cyberether/run/wifi64-nios-hardware-final/`
- `cyberether/run/original-iq-research-20261021/`

These paths hold captures/binaries and stay out of Git. No TX was requested during
these tests. PMOD A's existing v6 firmware reported idle with both tones disabled.

## Reproduce without RF

Run locally beside the installed tools, on host or inside the desktop container:

```sh
# SDK/toolchain provisioning follows docs/ESP32_FIRMWARE.md
ATUM_ESP_IDF=/path/to/pinned/esp-idf-sdr bash scripts/build_wifi64_tx.sh
ATUM_ESP_IDF=/path/to/pinned/esp-idf-sdr bash scripts/build_wifi64_monitor.sh
.venv-notebooks/bin/python -m unittest discover -s cyberether/tests -q
.venv-notebooks/bin/python scripts/analyze_original_polar_qam.py --self-test
.venv-notebooks/bin/python scripts/wifi64_nios_selftest.py
.venv-notebooks/bin/python scripts/wifi64_signal_nios_selftest.py
```

Explicit hardware test, only with checkpoint06 already loaded and devices free:

```sh
.venv-notebooks/bin/python scripts/check_wifi64_nios.py --hardware \
  --output cyberether/run/wifi64-nios-test-NEW
```

Add `--signal` to test the separately built L-SIG ELF (native4/4 pass;
hardware execution pending).

This temporarily replaces **CPU software**, restores the original monitor even
on failure, and does not change the SOF or issue radio commands. It tests offline
fixtures on actual hardware. It is not a waveform replay through the RF chain.

## Next gates

1. PMOD A TX and PMOD B native PHY monitor are flashed and normal boot is
   verified; bounded two-packet RF reception matched both payloads and ended
   RF-off. Repeatability and larger packet/error-rate trials remain open.
2. Implement in-device40→20MS/s filtering, acquisition/CFO/timing, pilot correction
   and validated L-SIG. Integrate these primitives with actual capture RAM.
3. Qualify actual raw-IQ FCS/BER and build the separate source-tagged OTA GUI;
   then run100,000 unique known payload bits per RF condition with cooldowns.
4. Separately, build a bounded original-chip attenuation-only probe, qualify
   amplitude settling/AM-PM, then decide whether a polar64-QAM backend is viable.
   Direct arbitrary-IQ TX remains research-gated.

See [native plan](NATIVE_WIFI_64QAM_OTA_PLAN.md),
[custom plan](CUSTOM_IQ_64QAM_OTA_PLAN.md),
[telemetry](WIFI64_OTA_TELEMETRY.md),
[TX firmware](../firmware/wifi64_tx/README.md),
[monitor firmware](../firmware/wifi64_monitor/README.md), and
[original-chip research](ORIGINAL_IQ_TX_RESEARCH_20261021.md), and
[compile-only amplitude probe](../firmware/original_iq_tx_probe/README.md).


## Native monitor viewer

The new display is read-only and starts no RF job:

```sh
.venv-notebooks/bin/python cyberether/wifi64_native.py --port 8774
```

It shows the most recent published native monitor proof. After firmware and
runtime installation are verified, an explicit bounded job may publish one:

```sh
.venv-notebooks/bin/python scripts/wifi64_ota.py --transmit --count 2 \
  --run 2026102102 --seed 1 --publish \
  --output cyberether/run/wifi64-native-ota-002.json
```

Each output path must be new. Publishing atomically updates the latest-proof
pointer after retaining the complete proof, including failed jobs. Opening the
viewer never starts acquisition or RF. Native packet reception is separate from
FPGA raw-IQ decoding; unavailable receiver evidence remains unknown.

## PMOD B ROM no-response check

The physical BOOT-switch test succeeded: with BOOT ON and a manual reset, PMOD B
entered ROM `DOWNLOAD_BOOT` and returned MAC `e0:e2:e6:01:a9:30`, matching the
expected module identity. A full 4 MiB rollback image was read before flashing;
its SHA-256 is `780d150511dcd0544e16bda55045d117aab2d995cf05b0aadf7e880e19444d51`.
All three images passed device hash verification. With the runtime FPGA bridge
restored, normal boot was verified by INFO/STOP/STATUS. The earlier no-response
result was resolved for the ROM diagnostic path; an external boot-drive issue
remains an unverified hypothesis.

For future firmware operations, preserve the rollback image, verify the intended
module identity immediately before writing, and hash-verify every image after
flash. Record both selector positions. Restore the runtime FPGA bridge, set BOOT
OFF, then manually reset B for normal boot; keep the SPI selector OFF for the
monitor UART. Verify normal firmware INFO/STOP/STATUS before starting a bounded
monitor job. If boot or UART identity is unexpected, stop and recheck module
selection, switch positions, reset sequence and UART routing; do not infer that
the external boot drive is faulty without evidence.
