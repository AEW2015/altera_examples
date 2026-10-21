# Original ESP32 raw-IQ TX investigation

Status: **offline investigation, not a hardware-qualified arbitrary-IQ transmitter**. The
installed RFS2 and Pmod receivers use the original ESP32. We have not established
arbitrary-IQ playback on that chip, but the absence of an upstream backend is
not proof that the silicon cannot do it. Keep the original modules as the first
investigation target; the existing S3 wrapper is a separately documented option.

## What was actually inspected

The repeatable experiment compares locally installed ESP-IDF PHY archives for
**ESP32 and ESP32-S3**, the SDK ROM linker maps, and the working S3 source from
`whstudio123/esp32-iq-tx`. It opens files and runs Xtensa binutils only. It does
not open serial/JTAG, boot or flash a board, read live registers or transmit RF.

| Input | Inspected revision / SHA-256 |
|---|---|
| ESP-IDF source tree | `25fe69f946311abdaf9ad56591f25fedbc20ac98` |
| IQ-TX upstream | `cf88cb6ab367c9db44d5af81d85923cfc883751e` |
| Original ESP32 `librftest.a` | `17cdfede65d13d9061605eb4efafb93a4932fcd4f35b2fbefc6302b3cc00f4d7` |
| ESP32-S3 `librftest.a` | `d3e3b808dd21f62c94841c4fffc0e33b6a04a0c0e5357b9a6e8675a1cd107324` |

The report fingerprints **all four original-chip and five S3 archives** in that
SDK, because replacing proprietary binary libraries can change results even at
an unchanged source revision. Full disassembly remains ignored local evidence;
this repository adds the investigation script and these observations, not copies
of vendor binaries.

## Facts versus hypotheses

| Observation from local source/disassembly | What it establishes | What it does not establish |
|---|---|---|
| S3 `librftest.a:mac_common.o` defines `dactrig`; its literals include `0x60033d64`, `0x3fcd0000`, count masks and a start bit | A concrete S3 SRAM-to-DAC diagnostic control path, consistent with the upstream backend | An equivalent original-chip register or mode |
| No `dactrig` definition appears in the four inspected original-chip PHY archives | That named helper is absent from this SDK's archive symbol tables | No playback capability anywhere in ROM or silicon |
| Original `adctrig` uses control `0x60033d90`, status `0x60033d94` and SRAM `0x3ffe8000` | The RX capture path underlying our existing receiver | That setting a guessed adjacent register reverses its direction |
| Original `get_txdumpaddr` reports `0x3ffe8000` and writes a second output of `12`; `clear_txdumpmem` fills diagnostic memory with `0x5aa55aa5` | TX diagnostics and RX capture reuse that SRAM address | The meaning of `12`, a TX IQ sample format, or playback direction |
| Original `crypto_encap` writes `0x60033dc0` then calls `tx_a_frame` | A TX diagnostic path associated with MAC/crypto processing | An arbitrary waveform DAC source; dumping transmitted packet data is different |
| Original SDK contains `ram_start_tx_tone`, `ram_set_txclk_en`, `set_tx_dig_gain`, `force_txon_en`; ROM maps expose tone, clock, PBUS and loopback helpers | There are concrete original-chip TX bring-up / tone-generation leads | A complete arbitrary-IQ modem or a supported function ABI |

The original-chip `ram_start_tx_tone` reads `0x3ff460b8`, transforms parameters
and calls through `g_phyFuns` at offset 68. The ROM follow-up below resolves that
indirect implementation to a concrete NCO control function. The corresponding SDK ROM map names
`rom_start_tx_tone` at `0x400036b4` and `rom_start_tx_tone_step` at `0x400035d0`.
Addresses identify the inspected original-chip map; **they are not portable
entry points to call without determining signatures and chip/ROM revision**.

### Why copying the S3 sequence is insufficient

```text
S3:      reserved SRAM → ownership switch → PLAY register → DAC → RF
              proven in upstream S3 implementation

ESP32:   reserved SRAM ← ADC dump engine
              proven in our RX implementation

ESP32 TX: SRAM → [source selection / sample packing / clock / trigger?] → DAC
                         still being investigated
```

S3 `ADC=0x60033d5c` and `PLAY=0x60033d64` do not justify applying their eight-byte
spacing to original `ADC=0x60033d90`. The script scans the local MAC register
window for literal references, rather than proposing register writes. In this
SDK, original-chip matches in `0x60033d50..0x60033dcc` are `0x60033d90`,
`0x60033d94`, `0x60033dc0`, and `0x60033dc4`; the S3 scan also finds its documented
playback literal. A literal scan is incomplete evidence: indirect/base-plus-offset
access and ROM code can hide a register reference.

## Wider Wi-Fi library scan

The optional `--wifi-archives` scan extends beyond `esp_phy` to **all seven
original-chip Wi-Fi archives, 109 archive members** in the same SDK. It saves
symbol lists, hashes, selected disassembly and literal matches under
`wifi-esp32/` in the ignored evidence directory.

| Wi-Fi archive | Members | SHA-256 |
|---|---:|---|
| `libcore.a` | 1 | `6372b6318a375dd60558471bf51521bb9aaec89a4f674f98c1e572bb5ee57df7` |
| `libespnow.a` | 2 | `8c897c9f1167a236bc8a55aa7691e2554e2d4f28302ad6250e2b7a3d7e376ca9` |
| `libmesh.a` | 15 | `9fc682d862b0ee9ed68a080d21d3e09a518a3f6cadc357cd475fdbbb7aa8ba12` |
| `libnet80211.a` | 50 | `45df5a69485d68ede6f9f17163dbccae0206ab1bfd1c5c89752f9a778386aa88` |
| `libpp.a` | 30 | `1436fa95f5d4ca77bbab2e72e8628679e5c0efac878600390a6ef312625ea6c3` |
| `libsmartconfig.a` | 8 | `f7097b3cd6f23b29c44d186a8b9431bf75f74d8013a10e6e3042792473281768` |
| `libwapi.a` | 3 | `e6e403379b40abc9ff626b6dc23492071a5f2a59acdd279e34fbe5469d09f882` |

Concrete outcomes:

- **The normal TX entry is a packet path.** `ic_tx_pkt` references `ppTxPkt`.
  `hal_mac_tx_set_ppdu` calls the PLCP, duration and HT-SIG configuration helpers.
  `mac_tx_set_plcp1/2` use registers `0x3ff74258/5c` and
  `mac_tx_set_htsig` uses `0x3ff74260/64`. The inspected code reads packet
  descriptors and writes PHY header fields; it does not walk an IQ sample buffer.
- **The word “bank” does not mean RF waveform RAM.** `wdev_bank_load/store` are
  bounded word-copy helpers used by `wdev_mac_reg_load/store` to restore/save
  banks at `0x3ff73000`, `0x3ff73400`, `0x3ff73800`, `0x3ff73c00`,
  `0x3ff74000` and `0x3ff74400`. The inspected callers supply register banks and
  saved-state offsets, not the RX sample aperture at `0x3ffe8000`.
- **Nearby register numbers can be misleading.** A raw scan finds
  `0x3ff73d58..0x3ff73d70`, including a `...3d64` address. The containing
  `dbg_lmac_hw_statis_dump` code loads those values and calls `wifi_log`; this
  is statistics inspection, not evidence that the S3 PLAY offset applies here.
  Other hits occur in MAC, RX-descriptor and sniffer control code.
- **CSI control is distinct from IQ TX.** `hal_mac_set_csi` updates a field at
  `0x3ff7309c`; the inspected helpers do not provide complex-sample playback.
- No definitions named `adctrig`, `dactrig`, `force_iq_set`, or `dac_out` were
  found in these seven Wi-Fi archives. The scan also checked little-endian
  literal values in both inspected MAC address windows and the known sample-RAM
  and NCO addresses. No new SRAM-to-DAC source selector was identified.

That last result narrows these **specific SDK archives**; it does not prove that
an unnamed, indirect, ROM-only or undocumented silicon mechanism is absent.
The next worthwhile evidence would be a register description, another original-
chip SDK/test build exposing such a path, or a disassembly trace of the actual
TX sample-source multiplexer. The packet-header and register-save routines are
not suitable substitutes for it.

## ROM follow-up: the indirect tone path is now resolved

The official local `esp-rom-elfs/20241011` package contains executable code and
initial PHY data for original-chip **rev0 and rev300**, not symbol-only stubs.
Both were inspected offline using the script's optional `--rom-elf` argument.

| File | SHA-256 |
|---|---|
| `esp32_rev0_rom.elf` | `bef39889393de40d7ae8dcf1cfe0bba32435a96a0b6ec35839724a9fddd6049f` |
| `esp32_rev300_rom.elf` | `920b70635440517866aab2230964a570d2cf2b676658d93c52fbac108c1cca31` |

The initial table and the executable chain agree in both images:

```text
phy_get_romfuncs @ 0x40004100
    load pointer stored at 0x3ffae0c0
              ↓
initial pointer value = 0x3ffae0c4
              ↓
table + 68 bytes = 0x3ffae108 → 0x400035d0
              ↓
rom_start_tx_tone_step
    scalar parameter fields → NCO control registers
    0x600060b8 / 0x600060bc, with a branch using 0x600050a8
```

`ram_start_tx_tone` and `rom_start_tx_tone` both transform scalar parameters and
call that table entry. The examined `rom_start_tx_tone_step` implementation
writes register fields; it does **not** load waveform samples from RF SRAM or
configure a demonstrated SRAM playback engine. That resolves the tone path,
while leaving arbitrary-IQ source selection unresolved. SDK RAM routines and ROM
code use different register access windows; their addresses are not instructions
to copy between chips.

These are **initial ELF table values**, not a live device readback. The SDK's
`phy_get_romfunc_addr` calls `phy_get_romfuncs`, stores the result in `g_phyFuns`,
and patches many entries. In the inspected function, the replacement
`ram_start_tx_tone` is written at byte offset **72**, whereas its nested call uses
**68**. The script retains that initialization function as evidence. A different
SDK or later initialization hook could change a running table.

The precise remaining information needed for an arbitrary-IQ TX probe is:

- An original-chip TX sample-source multiplexer or static-IQ injection mechanism.
- Its actual SRAM playback enable/count/status mechanism, if one exists.
- Sample packing, SRAM/alias ownership, clock selection and stop/restore sequence.
- The exact target chip revision and current SDK initialization/patch state.

A matching ROM image is no longer the blocker for tracing this tone function;
the missing evidence concerns the **arbitrary waveform input path**. No hardware
reads, writes or RF activity were used to reach this conclusion.

## Reproduce locally beside the SDK tools

The comparison needs the pinned upstream source as well as the SDK. For a fresh
missing dependency directory, prepare it with:

```bash
git clone https://github.com/whstudio123/esp32-iq-tx.git vendor/esp32-iq-tx
git -C vendor/esp32-iq-tx checkout --detach cf88cb6ab367c9db44d5af81d85923cfc883751e
```

Reuse an existing clean checkout at that revision; do not overwrite a modified
dependency. Source inspection does not initialize or transmit from any radio.


Run from the example root, on a host or inside a container with the same source
and SDK visible. Use the SDK actually used for the current receiver, not an
unidentified installation.

```bash
.venv-notebooks/bin/python scripts/investigate_esp32_tx.py --self-test

.venv-notebooks/bin/python scripts/investigate_esp32_tx.py \
  --idf-root "$IDF_PATH" \
  --tools-dir "$IDF_TOOLS_PATH/tools" \
  --upstream-root vendor/esp32-iq-tx \
  --wifi-archives

# Optional: inspect official ROM ELFs already installed with ESP-IDF tools.
# Set ROM_ELF_DIR to your local esp-rom-elfs/<version> directory.
.venv-notebooks/bin/python scripts/investigate_esp32_tx.py \
  --idf-root "$IDF_PATH" \
  --rom-elf "$ROM_ELF_DIR/esp32_rev0_rom.elf" \
  --rom-elf "$ROM_ELF_DIR/esp32_rev300_rom.elf"
```

`--tools-dir` is optional when Xtensa binutils are on PATH or in the conventional
local ESP-IDF tools directory. The script requires both chip tool prefixes.
Default output: `cyberether/run/esp32-tx-investigation/`.

| Evidence file | Use |
|---|---|
| `report.json` | Exact revisions/hashes, symbol definitions, per-function literal/call references, raw literal scan |
| `esp32/interesting-symbols.txt` | Review original-chip TX, DAC, dump, clock and loopback symbol leads |
| `esp32/adctrig.disasm.txt` | Cross-check the already working RX direction |
| `esp32/crypto_encap.disasm.txt` | Distinguish MAC crypto/TX dump from waveform replay |
| `esp32/ram_start_tx_tone.disasm.txt` | Trace the indirect original-chip tone path |
| `esp32s3/dactrig.disasm.txt` | Compare a positive SRAM playback example |
| `*/rom-symbols.json` | Named ROM entry points from SDK linker maps |
| `wifi-esp32/hal_mac_tx_set_ppdu.disasm.txt` | Distinguish packet/PLCP configuration from IQ playback |
| `wifi-esp32/wdev_mac_reg_load.disasm.txt` | Check the saved register-bank addresses and word counts |
| `wifi-esp32/dbg_lmac_hw_statis_dump.disasm.txt` | Check that nearby register hits feed statistics logging |

No positive playback result is inferred simply because the script exits cleanly.
It completes an offline comparison and explicitly reports the unresolved path.

## Next probes, in order

1. **Trace the remaining waveform source selection offline.** The ROM tone-table
   entry has been resolved above; verify argument units and current SDK patches,
   then look for a source multiplexer, static-IQ test mode or sample-memory DAC
   input. Trace DAC clock and dump/memory direction. Do not guess them from
   another chip's offsets.
2. **Build a separate original-chip diagnostic profile before replacing a working
   receiver.** Preserve the current image and pin profile. Reserve both dump
   banks/aliases as the RX backend does; add ELF/map overlap checks. Include
   explicit identity, firmware version, job limits, STOP and watchdog behavior.
   The ordinary IQ receiver backend remains RX-only until this gate passes.
3. **Qualify tone generation first with a documented SDK test entry point.** On an
   explicitly selected test module, run one bounded low-power tone job, capture
   it on the independent monitor, then stop and verify return to RX. Record
   frequency, gain, durations, RX clipping and on/off evidence. This proves only
   TX/clock bring-up. This gate has now passed on the separate bounded CW probe
   described below; arbitrary waveform playback has not.
4. **Test one evidenced IQ source hypothesis at a time.** Only after a source
   selector and packing/trigger path have been reconstructed, try a short
   low-amplitude known vector with automatic stop. Compare two distinct patterns
   on a separate receiver, their repeat period, frequency and constellation.
   A tone or MAC packet is not a pass for arbitrary IQ.
5. **Qualify modem playback.** Decode a full preamble/header/CRC frame over RF,
   repeat at different frequencies/amplitudes/rates, and measure EVM, failures
   and BER. Start BPSK, then QPSK; 16/64-QAM need measured linearity and phase
   quality. Keep each result tied to the exact module and firmware image.

If only a programmable tone path becomes available, low-rate on/off or frequency
keying may still be an interesting experiment. It must be labeled **tone-based
OOK/FSK**, with measured switching latency/jitter; it is not evidence of RRC-shaped
BPSK/QAM waveform playback. A conventional Wi-Fi packet TX function likewise
cannot transmit our custom modem IQ buffer.

Current outcome: **an actionable original-ESP32 investigation, with positive S3
comparison and specific original-chip leads; arbitrary-IQ TX remains unverified.**
No hardware or serial ownership was changed by this investigation.

## Bounded carrier diagnostic implementation

The separate [original-chip TX probe](../firmware/esp32_tx_probe/README.md)
implements the first on-board gate using the SDK's supported certification API.
It builds as `atum_esp32_tx_probe`, uses the existing Pmod UART pin profile and
starts without RF initialization. Explicit tone commands have bounded durations
and reduced-power backoff. `scripts/check_esp32_tone.py` records independent RX
captures before/during/after the job and reports the result without claiming IQ
playback or FPGA demodulation. See the probe README for build, flash and restore.

The ROM follow-up also shows that `rom_txiq_set_reg` clamps a signed scalar and
updates one of two small fields (5 or 6 bits) at `0x600050dc`. This is evidence of
TX IQ adjustment fields, not a sample-buffer reader. Merely calling an entry
with “IQ” in its name does not establish arbitrary complex-sample injection.


### Separate on-air CW gate now passed

The root operator tested the original-chip probe on PMOD A with independent
RFS2 captures. Existing local `tone-test-001/002/proof.json` evidence records
2422 and 2447 MHz jobs, with observed band-power rises of approximately
**39.8 and 62.3 dB**, respectively. These are relative capture measurements,
not calibrated radiated power or coding gain. Explicit STOP was observed, and a
separate 500 ms deadline job stopped after 500,803 µs with busy/invalid-command
rejection checked. This establishes bounded original-ESP32 **CW transmission**.
It does not establish a transmitted custom constellation or arbitrary-IQ replay.
The offline Wi-Fi/ROM scans above did not acquire hardware ownership.

See [original-chip TX bring-up results](ESP32_TX_BRINGUP_RESULTS.md) for the
separate live CW/OOK tests and their stated timing/processing boundaries.
