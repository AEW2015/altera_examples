# Notebook and hardware validation

All five checkpoint projects were regenerated and fully compiled with Quartus Prime Pro 26.1.1 Build 130, then programmed on the physical Terasic Atum A3 Nano (A3CZ135BB18AE7S). All five authored notebooks were executed with the **Atum A3 IQ Demos** kernel, including their programming and live-viewer cells.

Commands ran directly beside the installed tools in the existing Linux desktop environment. For this test that environment was inside `agilex-xrdp`; the notebooks used no Docker commands. Host execution uses the same code with local tool paths. A separate physical host Quartus installation was not tested.

| Checkpoint | ALMs | RAM blocks | Quartus DSP blocks | Minimum reported slack (ns) |
|---|---:|---:|---:|---:|
| vds_demo_01_raw | 5227 | 35 | 0 | +0.089 |
| vds_demo_02_nios | 9311 | 72 | 0 | +0.027 |
| vds_demo_03_fir | 10391 | 104 | 16 | +0.019 |
| vds_demo_04_ddc | 11884 | 140 | 22 | +0.017 |
| vds_demo_05_gain | 12091 | 140 | 26 | +0.006 |

The minimum is across reported STA checks; it does not establish complete external/asynchronous I/O constraints. Quartus reports 368 DSP units for this part, corresponding to 184 physical DSP blocks. These figures are compiled allocation, not live activity.

## Per-notebook results

| Notebook | Actual simulation | Physical test and focused browser page |
|---|---|---|
| 01 Raw IQ | Real UART TX/RX, eight binary bytes, 8N1 framing | RFS2 4,096-pair RF bursts; transport CRC verified; Pause / Capture once / Run tested |
| 02 Nios monitor | All 16 event counters, scaled window boundaries, totals and coherent CSR snapshot; bus reset independence | Advancing Nios/JTAG one-second counters, nonzero UART/payload rates, zero observed UART/capture errors |
| 03 FIR | Actual generated FIR II VHDL and snapshot controller; eight numerical/transport cases | Real RF Boxcar and Hamming outputs both matched independent integer references at 0 LSB error; filter selector tested |
| 04 DDC | Actual generated I/Q FIR II and DDC RTL; four mixer/filter/decimation cases | FPGA-generated two-tone, decimation 4; filter/alias controls tested; CI16 output matched reference at 0 LSB error |
| 05 Gain | Actual gain/meter RTL; bypass, half, double, saturation and zero, including integer meters | FPGA-generated single-tone; 2× output and meters matched exactly; 16× clipping verified; gain control restored to 1× |

Every focused page rendered native CyberEther video in a host browser and accepted its HTML controls without JavaScript exceptions. The final focused gain page remains running. Executed notebooks, generated diagrams, WLF databases, screenshots and runtime invitations are saved locally in ignored output directories. Published notebooks contain no live tokens or RF captures.

Questa 2025.3 GUI successfully opened the saved UART waveform. Every notebook writes `wave.wlf`, `view.do` and `gui.do`; the latter reruns the real simulation and leaves its GUI open. These tests cover the named RTL/IP, not Nios instruction execution or a complete Wi-Fi demodulator.

## Supporting checks

- **27 host tests PASS**, including CRC/bounds, integer DSP references, HTTP controls/authentication, fixtures, local tool discovery, optional bind-mount discovery and source-cache normalization.
- All five Python theory cells and simulator-output plots executed successfully. Native exported diagram counts were **6 / 11 / 13 / 16 / 17** blocks.
- Source-matched, SHA-verified SOF reuse passed after VDS regeneration. `FORCE_REBUILD=True` performs a full compile. Quartus's equivalent top-level entity annotations do not force a rebuild.
- The counter snapshot assignments use constant register indices to avoid a Questa 2025.3 indexed-loop simulation issue; the complete 16-counter assertions now pass. All affected FPGA images were rebuilt and tested afterwards.
- The installer creates the venv, installs notebook/viewer dependencies, registers both user and venv-local kernels, downloads/checks CyberEther v1.15.0 and builds the GStreamer shim. Python shared-library discovery uses the active interpreter's sysconfig; `python3-dev` supplies that library on Debian/Ubuntu.
- The original ESP32 firmware had already built against the pinned SDK revisions during source-package validation. No ESP32 was flashed or reset for the notebook tests.

This is targeted build, simulation and live hardware validation, not a long-duration soak or calibrated RF qualification. The five pages use different FPGA images. The earlier Wi-Fi packet/header receiver is outside this source package.

## Tested image SHA-256

- `vds_demo_01_raw`: `2616590068fd5e8651a79ee5ebb2898b7a4d96a966380ad2c38facc8bea8a12b`
- `vds_demo_02_nios`: `22a15763085faac40aa079aa8ad051ab9e97bf49b52344f1f4e3a75a308947f1`
- `vds_demo_03_fir`: `3c1631a335072090dbd212e39ef6b8586c43aba5c5f8e98a2f73c0cd51bb0150`
- `vds_demo_04_ddc`: `15737b5a6a7584f7b06d161f752732ec6e3720d5335c3b87b826371cc4f23c0b`
- `vds_demo_05_gain`: `4b259073fdffd9bed07a8f56cb9bc6170de0deefbd4001da56cceba9f1e2478a`

## RF Arcade addition

The demo-night page uses the same checkpoint-5 image listed above. Hardware/browser tests passed for real SDR captures from **RFS2 ESP32, PMOD A ESP32 and PMOD B ESP32**, each with valid CRC and 0 LSB FIR-reference error. Acquisition is one selected radio at a time.

Browser controls passed the fold / shift / reject sequence, exact 2× gain and power-meter checks, and 16× saturation (4,096 clipped pairs in the tested fixture). The native CyberEther view rendered throughout with no JavaScript errors. The automatic seven-scene cycle completed and returned to received RF in about **122 seconds**, with 0 LSB reference error in every scene. The page fitted a 1920×1080 browser viewport without document scrolling.

**32 host tests pass**, including scene validation, waiting for applied/verified hardware settings, bounded waterfall history, duplicate-result suppression and history reset when frequency changes. Existing notebook-mode tests still pass. Screenshots and machine-readable hardware/browser proofs remain in the ignored run directory. See [RF Arcade](docs/RF_ARCADE.md) for the presentation sequence and signal provenance.

## Native VDS GUI PNG exports

All five native systems were opened in Quartus Visual Designer Studio 26.1.1 through isolated GUI project copies. **File → Export** produced native Nlview PDFs; rasterization produced 3,091 × 4,000 PNGs. Each PDF was checked for every expected cell name: **6 / 11 / 13 / 16 / 17** blocks. Raw IQ and DDC images were visually inspected. All five PNGs are included under `notebooks/diagrams/` and linked inline in their notebooks.

Every generation cell now displays `Image(filename=str(diagram_png))`; `lesson.generate()` returns the native GUI PNG. The full GUI screenshot, original PDF and cell-name manifest are retained in each ignored results directory. The raw-IQ `lesson.generate()` path was rerun end to end, including native regeneration and GUI PNG export. GUI export does not program the FPGA. The local tool preflight and **32 host tests** pass.

## Official Nios V BSP/application projects

The official `niosv-bsp` tool generated HAL BSPs directly from all four CPU-equipped native VDS systems; `niosv-app` generated Hello World and IQ monitor CMake applications for each. All **four BSPs and eight Debug ELFs** built successfully. BSPs use the polled JTAG UART driver so the HAL interrupt handler cannot consume command bytes owned by `fir_control.h`. Sources and required headers are copied into each editable application directory; repeat generation preserves these edits.

The installed Ashling RiscFree GUI imported checkpoint-2 and checkpoint-5 BSP/Hello World projects and built their `build/Default` ELFs. The checkpoint-5 generated External Tools run configuration invoked the official downloader from the IDE and ran its IDE-built ELF on the physical Atum A3 Nano. JTAG UART printed the Hello World banner, 50 MHz CPU frequency and repeating one-second heartbeat counter. The HAL monitor printed advancing IQMON records and passed `STATUS` / `DDCSTATUS` command exchanges with the polled driver. The matching original boot-monitor ELF was restored afterwards and RF Arcade resumed live acquisition. No FPGA recompilation, SOF change or ESP32 reflash was required.

Downloader discovery in this installation identified the Atum as cable 2 / device 0 / CPU 0; `juart-terminal` uses device 1. The download helper resolves the cable by its exact name and requires the matching recorded FPGA checkpoint before stopping the notebook-owned viewer. **35 host tests pass**, including refusal of mismatched checkpoints and selection of the Atum when another development board is first. All notebook schemas/code cells and local software/tool checks pass. Generated BSP sources, ELF hashes, GUI workspace, download logs and hardware-output proofs remain under ignored `software/` paths. See [the Nios V IDE guide](software/README.md).

## ESP32 firmware/programmer and lesson introductions

Both original-ESP32 unified firmware profiles compile against pinned ESP-IDF `25fe69f946311abdaf9ad56591f25fedbc20ac98`: RFS2 application UART GPIO1/3 and Pmod application/console UART GPIO17/16. Each build records SDK/interpreter information and SHA-256 hashes for its bootloader, partition table and application. The manual-reset programming commands were validated with esptool 5.6.0 in dry-run mode for both profiles; no serial port was opened by those checks. SDK setup is locked and reuses a healthy environment.

The temporary FPGA bridge passed Questa assertions for **six target/mode combinations × 64 input combinations**, including inactive-UART isolation and GPIO0 low/high-Z behavior with pull-ups. RFS2 ROM, Pmod A ROM and Pmod B runtime variants compiled with Quartus 26.1.1 for A3CZ135BB18AE7S (14 I/O pins, no RAM/DSP). These builds were not loaded and no connected ESP32 was reset or reflashed for this addition.

**41 host tests pass**, including wrong application/console pins, out-of-build images, flash bounds, corrupted recorded images and esptool 4/5 manual-reset command generation. All five notebooks validate and their introductions now explain the addition, its use and its FPGA implementation with a short flow diagram. The root project `SKILL.md` passes skill validation and is referenced by `AGENTS.md`. Live acquisition and its JTAG reader were stopped at the user's request; the serial device was confirmed free and was not reopened for this work.

## Complete linked Quartus projects and SDC packaging

All five tracked source SDCs were present; the GUI-export wrapper omitted its referenced SDC. The wrapper now uses the complete project exporter, copying constraints, RTL, generated IP and memory initialization with no source-directory symlinks. Every generation/build (including notebook SOF cache reuse) prints the prepared QPF and full ZIP, and notebook output displays clickable links. Each notebook also links its tracked SDC.

The generated-HDL snapshot QSF explicitly assigns the top SDC, system QIP **and every leaf-IP QIP**. The latter are separate registrations in VDS and are not automatically included by the system QIP. `PROJECT_FILES.json` lists/hashes the inputs; export rejects missing/external QIP inputs and missing constraints. Native diagrams/Tcl definitions remain included.

Each ZIP was extracted to a new temporary directory and compiled using only `quartus_sh --flow compile iq_bridge_vds`, with no Nios/ESP32 software build or original-checkout source references in compile HDL/QIP/SDC files. All five full builds passed, targeted A3CZ135BB18AE7S, read `iq_bridge_vds.sdc`, and reported positive minimum slack:

| Checkpoint | Minimum reported slack (ns) |
|---|---:|
| vds_demo_01_raw | +0.089 |
| vds_demo_02_nios | +0.027 |
| vds_demo_03_fir | +0.023 |
| vds_demo_04_ddc | +0.014 |
| vds_demo_05_gain | +0.008 |

Native VDS GUI export also passed for the six-block raw project and 17-block gain project after the packaging change. **45 host tests pass**, including missing SDC/leaf-HDL rejection, complete extracted ZIP inputs and replacement of old GUI-wrapper symlinks. All notebook schemas/code cells validate. The serial device was not reopened and hardware was not programmed. Prepared project ZIPs, their file hashes and extracted-build logs/proofs remain generated local artifacts. Minimum reported slack does not establish complete external/asynchronous I/O constraints.

## RF Arcade setup notebook

Added `notebooks/06_rf_arcade.ipynb`, a presentation launcher using checkpoint 5 (not a sixth FPGA checkpoint). It covers local installation/kernel selection, tool and device configuration, saved/native GUI diagrams, complete project links, verified cached/full builds, explicit programming, private browser launch, scene walkthrough and explicit hardware cleanup. The generator now preserves unchanged cell IDs; regeneration leaves all six notebooks byte-for-byte unchanged.

All six notebooks pass schema, Python syntax, clean-output and local-link checks. The new notebook's actual setup/preflight and checkpoint-5 cached-SOF verification/project export passed in the local tool environment. Program/launch/cleanup cells were exercised with mocked hardware methods and checked for checkpoint 5 and `demo_night=True`; no live acquisition, programming or serial access was performed. **45 host tests pass.** Existing hardware validation above remains the evidence for the underlying RF Arcade pipeline.

## Offline ESP32 SDR firmware notebook

Added `07_esp32_sdr_firmware.ipynb`: source-linked mode/capture diagrams, control reference, editable synthetic tuning/gain/bandwidth/rate examples, CI8/IQ10/raw packing and CRC demonstration, and UART duty-cycle graphs. It distinguishes the accepted 100–6000 MHz software tuning range from demonstrated useful 2.4 GHz reception on the original ESP32 boards. RF response, gain-code scaling, AGC and capture timing in the teaching model are explicitly approximate; hardware register/calibration behavior is not emulated.

All notebook cells executed successfully in the project venv without hardware, producing three inline figures. All seven notebooks pass schema, Python syntax, clean-output and local-link checks and regenerate byte-for-byte. **49 host tests pass.** New tests compile the actual `burst_capture.h` C packers and compare Python output for six odd/even lengths (including 16,380 samples) in all three formats; they also compare the actual original-ESP32 bandwidth interpolation for every accepted nonzero bandwidth and zero. Bounds/rate rejection, CRC and sparse-capture timing are checked. No serial device was opened, radio reset/flashed or FPGA programmed. The executed synthetic notebook remains in ignored runtime output.

## Visual notebook experiments and applied-setting evidence

The five focused browser pages now show common-frequency before/after FFTs, shared-scale waveforms, equal-aspect IQ samples, coefficient response or FPGA power bars, bounded distinct-result waterfall history, and a requested/applied evidence ledger. The diagnostic graphs do not depend on native WebRTC; the native CyberEther canvas remains expandable and now includes the same readback/reference proof for DSP lessons. Nios plots use distinct counter windows, track the selected radio, and continue receiving counter updates while capture is paused.

Checkpoint 3 starts with its existing 128-sample FPGA impulse and exposes impulse/two-tone/live-RF controls through TEST/RUN/DUMP. The worker verifies exact pattern bytes, CRCs, coefficients, rounding/profile and integer output, and restores pairing configuration before returning to live RF. Checkpoints 4–5 expose existing FPGA tone/impulse and gain/clipping experiments. No FPGA RTL/SOF or ESP32 firmware changes are needed. A separate authenticated software-preview endpoint uses host references only, never reports hardware verification or creates counters.

**57 host tests pass**, including a mocked full FIR worker transaction with no radio acquisition, actual RTL literal-pattern identity, readback/CRC/reference failure cases, unavailable/stale Nios counters, paused counter updates, and rejection of unsupported test inputs. Offline Chromium tests passed for all five pages: controls produce APPLYING until a matching result is supplied, software previews stay separate, repeated polls do not add waterfall rows, and desktop/mobile renders have no JavaScript errors or mobile horizontal overflow. All five native canvas renders passed with offline fixtures; all seven notebooks passed schema/code/local-link checks and stable regeneration. Browser screenshots and test fixtures are in ignored runtime directories and are **mocked UI evidence, not hardware measurements**. Playwright/Chromium were installed only as local validation tools, not runtime dependencies.

The physical UART/JTAG devices were not opened and no board image was programmed. The new FIR worker route was exercised with mocks; its physical TEST/RUN/DUMP integration remains to be checked on the loaded checkpoint when the user next launches that lesson. Earlier hardware qualification of the underlying IP does not establish a new live test of these UI/control changes.

## Notebook activity / elapsed-time feedback

All seven notebooks now show live activity feedback for their numerical/plot examples and long-running lesson operations. Plain HTML progress bars require no widget package; they remain indeterminate while a task runs and fill only after success. The row shows elapsed time, nested phase, and a fresh bounded log tail/path where available. VDS GUI export, Nios BSP/apps, simulation, bitstream verification/compilation, project packaging, programming, demo startup and cleanup are covered. Viewer startup reports acquisition state while waiting for fresh matching data. CLI calls receive periodic text status instead. Failures and KeyboardInterrupt retain their exceptions and mark FAILED/CANCELLED; nested tasks share a row and stop their heartbeat thread on exit.

**62 host tests pass**, including real subprocess success/failure, live heartbeat/thread cleanup, nested row reuse, cancellation, fresh bounded log tails/HTML escaping and disconnected-frontend fallback. Safe cells from all seven notebooks executed successfully in actual Jupyter kernels. This included the real checkpoint-3 generated FIR II/RTL simulation and checkpoint-5 cached SOF verification/project export. A dedicated actual-kernel test observed multiple `update_display_data` messages during a running task and a final completed bar. Chromium rendered the running/completed HTML bars successfully. All seven notebooks validate, regenerate byte-for-byte and retain every original cell ID. Numerical summaries and plots remain displayed. No physical UART/JTAG was opened; programming, live viewer startup and hardware cleanup were not run for validation. Executed notebooks and the visual preview remain ignored local artifacts.

## Physical notebook retest — 2026-10-21

Ran the actual authored build/cache-verification, programming and launch cells in Jupyter kernels against the Atum A3 Nano (Agilex 3). All five source-matched SOFs programmed successfully; the RF Arcade notebook also programmed/reused checkpoint 5. No ESP32 firmware was reflashed. An older notebook-owned instance from `/home/altera_examples` was stopped through its own cleanup helper before testing this checkout.

**28 hardware feature checks passed across notebooks 01–06.** All six flows produced live progress updates during both physical programming and fresh-acquisition startup, with completed indicators. The record contains 98 progress display/update messages. The new reusable `scripts/check_notebook_hardware.py` saves executed notebooks, CRC/readback evidence and progress records under ignored `cyberether/run/notebook-hardware-retest/`; its optional Chromium check saves real hardware screenshots and waits for the native RF Arcade frame rather than photographing the initial flowgraph editor.

| Notebook | Physical checks | SOF SHA-256 prefix |
|---|---|---|
| 01 raw IQ | Fresh CI8/CRC from RFS2, PMOD A and PMOD B; 8192 samples in nominal 40 MS/s mode | `2616590068fd5e86` |
| 02 Nios | Nonzero UART/payload rates, fresh coherent windows while paused, resumed capture, zero UART/capture errors | `22a15763085faac4` |
| 03 FIR | FPGA impulse/two-tone, Hamming and Boxcar, nearest/truncate, live RF pairing and transition back to test input | `3c1631a335072090` |
| 04 DDC | Known two-tone rejection, filter-bypass alias, impulse and restoration; exact integer output | `15737b5a6a7584f7` |
| 05 gain | 0.5×, 1×, 2× and 16×; gain/power/clip readbacks and exact integer output | `4b259073fdffd9be` |
| 06 RF Arcade | Live RF scene, FPGA overdrive scene and rendered native browser frame | checkpoint 5 |

Every checked FIR/DDC/gain result matched the independent integer reference at **0 LSB**. The 2× gain case measured **+6.0206 dB** versus 1×; 16× clipped **4096/4096 samples**, while 1× had no clips. One Nios window measured **16,506 radio UART B/s and 16,384 host IQ payload B/s**, with zero capture/UART errors; these are observed window rates, not peak throughput. DDC filter rejection exceeded 20 dB on the deterministic digital fixture and bypass was approximately 0 dB; this is not an RF sensitivity/calibration result. These are bounded functional tests, not a long-duration soak test.

Checkpoint 5 remains loaded, matching the starting image. All test-owned viewers/acquisition processes were stopped; UART and JTAG-UART readers were checked free after the final run. No buttons, ESP32 resets/reflashes or wiring changes were needed. Earlier offline-only qualifications above are superseded for these tested physical paths by this retest.


## FIR example library, Python reloads and browser controls

Added 15 quantized filter examples, custom 16-tap Q15 reloads, an offline response gallery and a focused selector/editor in the FIR notebook/page. Python requests use the running acquisition owner; no second hardware client is opened. Candidate previews remain separate from applied settings. Reloaded coefficients persist across captures and are verified by full readback, payload CRC and an independent integer reference. One active coefficient set is resident; the separate DDC filters remain fixed. No RTL/SOF or ESP32 firmware changes were needed.

**67 host tests pass.** The offline library/table/15-response gallery executed in a Jupyter kernel; all seven authored notebooks pass schema, Python syntax and clean-output checks. Existing offline browser checks passed for all five focused pages. Physical checkpoint-3 tests covered the original 14 library examples with zero integer-reference error, custom-tap persistence, reload while paused, live RF, and the notebook’s actual Python loading cells. The added 15th example, `notch-4mhz`, passed full coefficient readback and zero-error checks on hardware: the +4 MHz unwanted tone was attenuated **54.51 dB**, while the −0.5 MHz wanted tone lost **0.174 dB**. These are host sinusoid fits on actual FPGA raw/filtered samples, excluding the first 16 startup samples, not calibrated RF measurements.

Actual Chromium controls passed selection/preview isolation, named and custom reloads, invalid-tap rejection, fresh matching coefficient-hash/proof waits and final VERIFIED display. Checkpoint-5 hardware regression also passed 1×/0.5×/2×/16× gain cases, +6.0206 dB at 2× and 4096 clipped samples at 16×. Test captures, executed notebooks and screenshots remain ignored local evidence. The loaded design was restored to checkpoint 5 after testing, and acquisition/UART/JTAG terminal handles were released.


## Saved CyberEther examples in notebooks

Notebooks 01–06 now end with static browser screenshots from the previously recorded physical hardware tests, including the FIR notch and custom coefficient editor. Captions distinguish live ESP32 RF from FPGA-generated test inputs. The offline firmware notebook has no CyberEther section and remains unchanged. Seven PNG assets are checked in beside the notebooks; links resolve relative to each notebook for local and GitHub rendering.

All seven notebooks pass schema, Python syntax and clean-output checks. HTML export includes the expected screenshot links, all seven PNG assets decode successfully, unchanged cell IDs are retained, and regeneration is byte-for-byte stable. This documentation update did not open hardware devices or rerun acquisition.

## Local native GUI export lock regression — 2026-10-21

A failed checkpoint-1 diagram export left Quartus blocked by its “project already open in another instance” dialog. The saved error screenshot showed this modal warning while the helper waited for the loaded-project window title. The VDS/IP generation step had succeeded.

The export helper now prepares a uniquely named `gui_project-*` copy for each run, avoiding reuse of the locked project directory. Two consecutive checkpoint-1 exports passed with six native VDS cells and validated PDF/PNG output; all 73 host tests passed. This check did not program the FPGA, download CPU/ESP32 firmware or start hardware acquisition.

## Portable UART selection and acquisition startup errors — 2026-10-21

RF Arcade failed to capture because its default UART pointed to the original rig's unavailable by-id link. UART selection now honors explicit arguments and `ATUM_UART`, otherwise resolves the Atum's interface-1 by-id link or USB identity. Multiple boards require an explicit selection; unrelated USB serial devices and interface 0 are excluded. Overrides set after Python imports are respected. Demo startup resolves and passes the UART before stopping an existing demo or launching a new process. Timeouts include the current launch's acquisition error and log path, excluding stale errors.

All 77 host tests passed against an isolated export of the staged source, including ten new UART/startup regression tests. Read-only USB enumeration selected `/dev/ttyUSB0` in the current container without a by-id mapping; detection was checked with serial opening disabled. This validates discovery and error reporting, not RF acquisition or FPGA arithmetic. No FPGA/CPU/ESP32 programming or hardware acquisition was performed for this change.

## Local Rescue display comparison — 2026-10-21

Added wanted/interferer frequency labels, a persistent measured before-FIR trace alongside the current filtered spectrum, a 100 dB tone-rescue display range, wanted-tone level change and an explanation of the stationary DC IQ point. Comparisons require matching verified input identity, mixer phase, output rate/length and gain; unmatched, failed and stale captures do not supply a baseline. Power-scene IQ scaling is unchanged.

All 83 host tests passed against an isolated export of the staged source (88 with additional local launcher tests), including comparison persistence, mismatched-input/configuration rejection, Fold-versus-Shift isolation, failed-reference rejection and rendering with/without a baseline. Offline test fixtures were rendered and visually inspected. These display tests did not change the running demo's settings, restart its processes, program hardware or acquire new hardware results.

## Original ESP32 bounded TX bring-up — 2026-10-21

Built `firmware/esp32_tx_probe` against pinned original-chip SDK
`25fe69f946311abdaf9ad56591f25fedbc20ac98`. Preserved the supported 2 MiB PMOD A
flash layout privately before writing; verified target MAC, then all written
image hashes. Application SHA-256:
`191dbff1bbcfcdb2ace58aca1256fa3ced18bda0555833c481ffbddc0f1849ad`.
Restored the exact prior checkpoint-3 FPGA image
`3c1631a335072090dbd212e39ef6b8586c43aba5c5f8e98a2f73c0cd51bb0150`.

Actual PMOD A → RF → RFS2 measurements passed carrier on/off on channels 3 and 8.
Channel 8 measured 62.33 dB relative power rise and 62.32 dB fall using fixed RX
gain. STOP, busy rejection and invalid-job checks passed. Automatic 500 ms job
reported off at 500,803 µs; a separate 750 ms job stopped at 754,928 µs with a
62.12 dB independently observed RF power drop. The repeatable `--automatic-stop`
checker also passed a three-second job (3,004,956 µs, 62.34 dB measured fall).
All 36 captures in the three full tone tests passed transport checks, without
exact CI8 rail hits; absence of those codes does not establish analog headroom.

Host-coordinated OOK recovered `A5C3` and `A55A0123456789FF` exactly: zero observed
errors over 16 + 64 bits. Decision threshold comes from separate off/on training
captures. Expected bits are used only for error counting. This does not establish
an independently synchronized modem, calibrated RF BER or arbitrary-IQ playback.
DSP/detection/FFT in these checks is host Python; the FPGA transports snapshots.
[Results and saved plots](docs/ESP32_TX_BRINGUP_RESULTS.md).

Focused TX/flash tests: 12 passed (actual native-C parser, detector metrics,
image/profile checks and a regression for MAC-probe/reconnect baud handling).
Full local working-tree suite: 109 passed. Offline SDK/ROM scan including seven
Wi-Fi archives / 109 members found no established original-chip waveform
playback/source selector; this is not a proof of silicon impossibility.

Final hardware state: PMOD A runs the bounded TX probe, RF idle; RFS2 and PMOD B
retain their receiver firmware; checkpoint 3 hub restored; RFS2 gain restored to
hardware AGC. The prior viewer is paused and no test UART/JTAG owner remains.
Private backup, capture logs and proof JSON remain ignored locally.

## Original ESP32 NCO and phase control — 2026-10-21

PMOD A's bounded v3 probe was built against pinned SDK
`25fe69f946311abdaf9ad56591f25fedbc20ac98`, flashed with hash verification,
and identified on its normal application UART after the requested physical
resets. Application SHA-256:
`9ba48ecbba51984375e055cb1c781c82239bd5fa8ce21fdbfa2eb3ebe874d170`.
The normal checkpoint-3 FPGA hub was restored before boot:
`3c1631a335072090dbd212e39ef6b8586c43aba5c5f8e98a2f73c0cd51bb0150`.

Independent RFS2 IQ captures verified relative scalar-tone frequency increments
0/1/2/4/8/16/32 on the nominal 39.0625 kHz grid. Both the v2 sweep and v3
regression passed 21/21 payload CRCs with the same peak-bin displacements at
1.953125 kHz FFT resolution. In v3 all seven stop events were observed, the
existing text-drop counter stayed at 11, and command/framing/capture errors
remained zero. This does not calibrate either radio clock or RF power.
[Frequency measurements](docs/ESP32_NCO_RF_RESULTS.md).

The v3 phase-continuity experiment acquired **30 physical captures** across five
runs. All 10 full-width captures showed coherent near-antipodal plateaus and
persistent approximately 180° events; all 10 zero-width carrier controls and
all 10 half-width controls rejected the two-state criterion. Symbol-period and
pattern controls changed the observed spacing. All 30 frames passed transport
checks with zero command/framing/capture errors and no exact CI8 rail hits.
Manual RX gain 0 avoided the extreme-code concentration found in earlier
gain-20 CW data; absence of exact rail hits alone does not prove analog headroom.

The offline event detector was corrected to group ringing lobes with 6 µs quiet
resolution, then applied to every saved capture and independent synthetic
controls. Original proofs remain local. CPU timing and received phase vary:
the optional pulse-width calibration did not establish a unique RF timing
calibration. These are host-analyzed RF phase measurements with FPGA capture
transport, not decoded bits, BER, FPGA synchronization/FEC or arbitrary-IQ TX.
[Phase measurements, controls, PNG and reproduction](docs/ESP32_PHASE_RF_RESULTS.md).

Full working-tree host suite: **118 tests passed**, including actual native-C
command parsing and six offline phase-analysis test groups. Final radio
readback is idle with both tone generators disabled and extension cleared;
RFS2 hardware AGC is restored. No test UART/JTAG owner remains.

## Checkpoint 06 modem — physical FPGA qualification, 2026-10-21

Programmed the source-matched checkpoint-6 image on the Atum A3 Nano and read
modem block ID `0x4d440601` from hardware. SOF SHA-256:
`f5c6f0f2010d1c08a5e7f2bb6dd4ef01ad5d78b53f72ea49dca28157aa9ebeb7`.
Fit: 28,058/45,800 ALMs (61%), 146/353 M20Ks (41%), 32 reported DSP units;
setup slack +1.194 ns and hold +0.026 ns at 50 MHz. These are compilation
allocations, not measured live utilization.

`scripts/check_modem_hardware.py` passed all four modes on **32-bit payloads**:
BPSK, QPSK, 16-QAM and 64-QAM. Actual FPGA coded bits, quantized symbols, signed
soft metrics and decoded payloads matched independent Python results. A seeded
64-QAM symbol-noise case produced **6/76 coded-bit errors → 0/32 payload errors**.
The 64-QAM decoder reported 5,938 cycles (118.76 µs at the configured clock);
JTAG upload/readback is much slower and is excluded from this kernel time.

These are physical FPGA **symbol-level** transactions with host-generated bits
and symbol noise. They are not an RF synchronization or over-air QAM test.
The full 256-bit capacity/noise case remains covered by actual Questa simulation
(27/524 coded errors → 0/256 payload errors); the optional full-capacity hardware
run is slower and was not completed. Reproduce with:

```bash
.venv-notebooks/bin/python scripts/modem_fpga.py program
.venv-notebooks/bin/python scripts/check_modem_hardware.py
# Optional slower maximum-frame case:
.venv-notebooks/bin/python scripts/check_modem_hardware.py --payload-bits 256
```

The guarded programmer checks the source fingerprint/SOF hash; the tested block
ID is hardware readback. Saved bitstream SHA is local programming provenance,
not a SHA read back from the silicon. After testing, checkpoint 3 was restored
for the ongoing radio TX probe. No ESP32 firmware change was required for these
FPGA tests. Detailed local proof: `cyberether/run/modem-hardware-proof.json`.

## Compact framed BPSK — physical RF and FPGA qualification, 2026-10-21

Probe **v4** now boots and runs on PMOD A. The first image failed startup because
its worker was pinned to core 1 in a UNICORE SDK profile. Replacing that with the
original scheduler-selected `xTaskCreate()` fixed the defect. The corrected
image flashed with hash verification and normal boot reported READY and INFO v4.
Application SHA-256:
`3e0816fe1656a1704cce3fed7ec01dd70a9ff78c7fc8b358e49c917ca9708ed2`.

The frame contains marker `0x0651`, 44 terminated K7(171,133) coded bits covering
payload8 + CRC8, then four guard zeros. Native C encoding agrees with independent
Python equations for all 256 payloads. Measured phase calibration selected 670
requested pulse cycles at CPU 160 MHz: approximately −180.22° full-width and
−90.01° half-width, with the zero-width carrier control rejecting two-state
behavior. The earlier nominal 682-cycle setting failed the strict phase test.

Actual PMOD A → RFS2 RF capture results, 8 µs nominal symbols:

| Run | Captures | CRC-valid frames | Coded errors/bits | Payload errors/bits |
| --- | ---: | ---: | ---: | ---: |
| Initial A5 / 3C / 00 / FF runs | 28 | 28 | 20/1232 | 0/224 |
| Browser live batch, payload 3C | 64 | 65 | 55/2860 | 0/520 |
| Combined direct captures | 92 | 93 | 75/4092 | 0/744 |

The browser batch completed in 50.68 seconds. All these captures acquired a
frame; no acquired frame failed CRC. One batch capture contained two adjacent
frames. A separate PMOD B receiver test passed four captures/four frames,
4/176 coded errors → 0/32 payload errors. This is another receiver observation,
not additional unique delivered packets. Saved CI8 hashes and independent
recovery without the known payload confirmed all 97 frame observations.
These are sparse windows, not a packet-delivery or continuous-stream BER test.
Known payloads enter error counting only, not acquisition or CRC decisions.

**Actual FPGA symbol/FEC replay:** checkpoint06 block ID `0x4d440601` decoded
measured RF symbols from the first A5 capture. Soft metrics and decoded bits
matched independent integer/Viterbi references: **1/44 coded errors → 0/8 payload
errors**, CRC valid, no symbol quantization clips. Decode took **3144 cycles /
62.88 µs at 50 MHz**; JTAG upload/readback took **86.402 seconds** overall.
Host carrier/timing/frame acquisition precedes this separate FPGA transaction.
The source-matched SOF SHA is the checkpoint06 hash recorded above.

**Actual same-capture FPGA FIR II:** two raw/FIR pairs, 16,380 complex samples
per capture, passed all 32,760 sample comparisons with maximum integer-reference
error zero. Hamming16 Q15 taps, nearest rounding and descriptor `0x80010102`
matched readback; clips were zero. Both raw and filtered representations decoded
two valid frames, each 0/88 coded and 0/16 payload errors. This demonstrates
correct filtering, not a measured BER improvement. FIR processing took 114,756
cycles / 2.29512 ms per burst. Paired UART transfer took about 0.585 seconds;
RF was stopped after raw capture at about 0.247 seconds. Matching job/timestamps
and origin CRC establish that both outputs came from the same raw capture.

Receiver tests cover CFO, capture phase, phase ramps, corrected errors, retained
CRC failures, independent BER references, and CW/OOK/noise negative controls.
Synthetic controls are explicitly labelled and never counted as RF evidence.
The browser rendered the four plots, FIR overlay and separate FPGA replay panel;
Clean/FEC controls and the 64-capture RF batch were tested end to end. Starting
the page opens no UART/JTAG connection and does not transmit. Notebook08 includes
the Python example and saved screenshots. Full host suite: **133 tests passed**.

Checkpoint03 is restored. TX readback is idle with both tones disabled; receiver
hardware AGC and prior FIR settings are restored, PAIR is off. No test UART/JTAG
owner remains. Raw-waveform synchronization is still on the host; SPI, continuous
streaming and over-air higher-order QAM remain future work.

Local evidence: `cyberether/run/rf-bpsk-001` through `rf-bpsk-004`,
`rf-link-20261021-184620-1792608380457260133`, `rf-bpsk-monitor-001`,
`rf-bpsk-001/fpga-proof.json`, `rf-bpsk-fir-001/proof.json`, and
`rf-bpsk-independent-review.json`. Runtime captures remain private/ignored.
[Walkthrough and reproduction commands](docs/RF_BPSK_WALKTHROUGH.md).

## BER qualification and physical QPSK — 2026-10-21

The roadmap now sequences measured BER qualification, SPI transport, then
increased modulation complexity. Parallel agents implemented independent BER,
SPI and QPSK paths; Luna handled documentation. The qualified v5 transmitter
source is preserved in Git commit `ba208dc`, separately from the subsequent v6
cycle-deadline optimization (built, not yet RF-qualified).

### BER evidence

The offline BPSK AWGN experiment uses 1,000 independent random 16-byte frames per
point, 128,000 payload bits at each −2/0/2/4/6 dB encoder-information Eb/N0.
Finite termination cost enters the effective code rate; CRC information bits
are included, preamble and guards excluded. Hard/soft Viterbi see identical
received samples. At 4 dB, hard decoding produced 704 payload errors versus 8
with soft metrics. At 6 dB both observed zero; the 95% one-sided zero-event bit
bound is 2.3404e-5 under an independent-bit assumption. Decoder errors correlate,
so separately returned independent-frame bounds are more appropriate for frame
reliability. Perfect synchronization is assumed; these are not RF measurements.

Saved RF proofs are audited with raw-SHA deduplication, separate receiver and
setting groups, and missing historical settings left unknown. The earlier
96 captures/97 frame observations give 79/4268 coded errors → 0/776 payload
errors with both hard and soft decoding. The separate v5 BPSK regression adds
four captures/four valid frames, 1/176 → 0/32. Neither establishes a hard/soft RF
advantage because both decoders succeed. A training-only offline timing audit
reduced errors on the same older RFS2 data from 75/4092 to 69/4092 without
changing CRC or payload results; its modest gain was not installed in the live
receiver. Replays add no independent RF observations.

### QPSK qualification

A phase-state gate measured three quarter-turn captures with four coherent
plateaus (335 requested cycles, step3, 32 µs symbols). Fourth circular moments
were 0.9702/0.9789/0.9885; all carrier-only and BPSK controls rejected the
four-state criterion. This gate itself does not decode bits.

PMOD A was then explicitly flashed with v5, hashes verified, and normal startup
reported INFO v5. Application SHA-256:
`057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`.
The 64-symbol QFRAME contains 32 fixed training states, 22 Gray-coded payload/
CRC/FEC symbols and ten guards. All 256 native encoder payloads match the
independent reference. Quarter/half/three-quarter requests are independently
configurable; these RF trials used 335/670/1005 at the measured 160 MHz CPU.

| Physical run | Symbol period | Captures | Acquired frames | CRC pass/fail | Acquisition failures | Coded errors/bits | Payload errors/bits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| QPSK001, original receiver | 8 µs | 8 | 0 | 0/0 | 8 | 0/0 | 0/0 |
| QPSK002, original receiver | 12 µs | 8 | 4 | 4/0 | 4 | 0/176 | 0/32 |
| QPSK003 | 10 µs | 16 | 12 | 6/6 | 4 | 112/528 | 19/96 |
| QPSK004, payload3C | 12 µs | 32 | 21 | 21/0 | 11 | 0/924 | 0/168 |

At 8 µs, transmitter counters reported **zero completed frames**, about 5,080
missed deadlines per job; this is a failed operating point, not BER zero.
At 10 µs, some correctly acquired training precedes damaged bodies; CRC failures
and payload errors remain included. At 12 µs, counters show completed frames and
far fewer timing misses. Use 12 µs as the default; sparse capture windows still
may miss a complete training/body sequence.

The receiver now requires the actual 54 training/body symbols, rather than ten
unused guards too. Blind reprocessing QPSK002 recovered five valid frames from
the same eight captures (0/220 → 0/40), while leaving QPSK001 unacquired. This is
an offline improvement on existing data, not five new RF frames. Tests accept
omitted guards but reject a truncated body, CW and noise. Known payload changes
only BER measurement; blind and referenced acquisition return identical frames.

Checkpoint06 was physically programmed and decoded 22 measured symbols from
QPSK004, after an explicit host −135° rotation to match its different Gray-map
convention. Received noise/amplitude were retained. Hardware block ID was
`0x4d440601`; integer soft metrics and Viterbi bits matched independent references:
0/44 coded errors → 0/8 payload errors, CRC valid. Decode took **3,100 cycles /
62 µs at 50 MHz**; the JTAG transaction took **68.328 seconds**. The source-matched
SOF hash is recorded in the earlier checkpoint06 section. Checkpoint03 was
restored after the replay. Raw carrier/timing acquisition remains on the host.

### Presentation and reproducibility

RF Link Lab port8770 now offers BPSK/QPSK, defaults QPSK requests to 12 µs,
labels expected Gray points separately from received dots, and retains the most
recent CRC-valid plot within a batch while counting every attempt. The plot age
refers to the displayed capture. Historical FPGA FIR/replay panels preserve
source hashes and remain separate operations. Synthetic pages hide those panels.
The BER button runs a bounded offline experiment and leaves the RF snapshot
unchanged. During ROM programming, RF capture was verified to refuse the missing
runtime manifest. Actual browser tests verified the BER action, QPSK reference,
mode defaults and page rendering without JavaScript errors.

Notebook08 includes progress feedback, editable BER/QPSK simulations and saved
physical screenshots. Its QPSK software record contains two full frame periods;
actual RF retains 16,380 samples. The clean model has no firmware timing jitter.
Local proofs: `rf-qpsk-001` through `rf-qpsk-004`, their independent reviews,
`rf-qpsk-004/fpga-proof.json`, `phase-qpsk-gate-001/four-state-proof.json`,
`ber-qualification/qualification.json`, and `bpsk-robustness-audit-001.json` under
ignored `cyberether/run/`. The 100,000-payload-bit RF target, continuous capture,
full FPGA synchronization and amplitude-linear QAM remain open.

### SPI build and subsequent hardware qualification

Separate SPIQ0001 qualification firmware and FPGA sources compile and simulate.
The original ESP32 DMA slave starts with synthetic data and accepts explicit
T/R requests for synthetic/fixed-channel8 CI8 snapshots; packet flags identify
the applied mode. Python/C wire encoders agree; all four SPI modes, CS, READY,
backpressure, bounds, reset and full packet-to-UART paths pass Questa checks.
SPIQ0001 fit: 323 ALMs, 405 registers, one RAM, zero DSP; 50 MHz setup/hold
+13.699/+0.084 ns and nominal 5 MHz SPI +88.747/+18.415 ns. All eight physical
pins use explicitly fitted 3.3 V I/O. The separate meter variant adds FPGA
CRC/header/order checking and atomic whole-capture power/peak/clipping results.
It is independently simulated and compiled before hardware use.

Combined SPI application SHA:
`51412513067d942e1d476bb861df9731ed18972a79f510bcd06f1dd031c7c499`.
SPIQ0001 SOF SHA:
`b424cc647e767ce6a83b5a11482fc63ad49aea6be60fae430fe370b9c50f312c`.
PMOD B was subsequently backed up privately (2 MiB), MAC-checked, flashed with
the combined SPI image and hash-verified. With SPI ON and BOOT OFF, the basic
image received exact synthetic bytes and a fresh passive channel-8 RF capture.
All packet CRCs passed; each capture contained 16,380 CI8 samples.
Current working-tree host suite: **205 tests passed**.

The SPIQ0002 meter image also completed a no-edit consistency rebuild, with
1,237 ALMs, 1,940 registers, one RAM and one reported DSP block. Setup/hold
slacks are +12.698/+0.088 ns (50 MHz) and +88.334/+18.626 ns (nominal 5 MHz
SPI), with zero unconstrained clocks/ports. SOF SHA:
`7385b167454d9e6e297f463e5376bf4ac47b81113da56cefea13e632aa58c540`.
Twelve host/native SPI tests and two meter Questa testbenches pass, including
backwards/replayed sequence rejection, wrap, signed rails and separate clipped
sample/component counts. Compiled allocation is not live utilization.

Physical SPIQ0002 tests then passed synthetic and RF integer-reference checks,
20 alternating captures (327,600 complex samples; 20 unique sequences), and a
separate idle-recovery synthetic/RF pair. All accepted packets passed CRC and
all FPGA power sums, peaks and clip counts matched independent Python. Synthetic
sum/peak/clipped samples/components were 178,923,972 / 24,665 / 256 / 256.
Every full capture used 32 chunks and 2,770,944 active ingress cycles at nominal
50 MHz: 55.419 ms, about 591,134 payload bytes/s. This excludes inter-transaction,
READY and UART gaps. Complete host captures measured about 106–113 kB/s and
remain UART-limited; no sustained streaming speedup is claimed. Mode transitions
intentionally discarded partial old captures and increased reject counters.
Proofs are in ignored `cyberether/run/spi-{synthetic,rf}-001`,
`spi-meter-{synthetic,rf}-001`, `spi-meter-repeat-001/summary.json`, and
`spi-meter-idle-recovery-{synthetic,rf}-001`. The standalone SPI image currently
serves B only; A/RFS2 and the older live RF GUI require the normal hub. Integrated
hub/FIR ingress, continuous operation and higher-clock board margin remain open.

The subsequent v6 TX build replaces per-symbol wall-clock calls with a checked,
wrap-safe CPU-cycle deadline. Returned setup elapsed time is checked against the
original 500 ms phase-work budget after blocking PHY setup; ROM/PHY setup itself
is not bounded by that limit. Dynamic frequency scaling is rejected; short pulse
interrupt masking, STOP and restoration remain. Native deadline tests passed for this earlier candidate:
`6da0772f01bc853e20424aa2b1ed681929163b68389225d7d600dd659cff3b78`. It was
superseded by the later v6 app recorded below; neither build establishes faster
QPSK or improved RF BER without qualified RF measurements.

## Final checkpoint07 boot, FIR and recovery qualification — 2026-10-21

The final integrated checkpoint07 build has source fingerprint
`463977275485c8dd9412f351dfef365ca6c96b7a2ab4d4cfc8dea51d94951898` and SOF
SHA-256 `19ff94b02e3670587ada244a3ce6eb41aed2dbd0f21970a0db17c9dc8a06fa2b`.
Quartus reports 16,799 ALMs (37%), 120 M20Ks (34%) and 16 reported DSP units
(4%); setup/hold slack is +7.264/+0.007 ns at 50 MHz, with zero unconstrained
paths. The independent audit matches all 164 compiled local input files. The
actual VDS GUI export contains 13 blocks. Earlier image `6b980718…` completed
12 alternating SPI/FIR pairs (196,560 complex samples), all matching the FIR
reference exactly.

On the final image, a fresh boot read back all sixteen default FIR coefficients
as 2048. The exact Hamming test passed for 16,380 complex samples, and settings
restoration was verified. Proof is in ignored
`cyberether/run/spi-fir-boot-fixed-synthetic-001`. A profile guard test rejected
40 MHz / 2417 MHz with error128 and a 1,024-sample request with error32 without
arming; the following valid SPI raw capture and four passive RFS2 UART0 captures
passed. See `spi-profile-rejection-recovery-001` under ignored
`cyberether/run/`.

Matched profile-2 RF captures on the earlier integrated image used 16,380
complex samples: useful host input measured 79,164 B/s at 2 Mbaud and 126,048
B/s at 4 Mbaud. These exclude Nios setup and host verification; CS-active SPI
ingress stayed about 591,134 B/s. Do not compare the earlier 4-Mbaud synthetic
result with RF throughput.

Before v6 programming, PMOD A UART INFO responded, but the known v5 TX attempt
failed before `FRAME_CFG`: a task-watchdog backtrace hung in
`chip_sleep_prot_en` → `esp_phy_wifi_tx_tone`, before any RF samples. This is a
transmitter setup failure, not an SPI failure; A then became UART-unresponsive.
An earlier GUI batch verified one synthetic SPI/FIR pair, then timed out on the
required A INFO liveness check; retain it as a historical failure. After v6
normal boot, the later 12-capture GUI batch passed all progress steps, both UART
liveness checks (TX_PROBE v6 `busy=0`, RFS2 SDR), six synthetic and six passive
RF captures, and cleanup. Raw/FIR matched exactly over 196,560 complex samples;
FIR settings and host UART 2-Mbaud state were restored, with no JavaScript
errors. Proof is `cyberether/run/spi-gui-1792619816548480098/proof.json` and
`cyberether/run/spi-fir-browser-v6-live-001.json`; the updated 12-row screenshot
is `docs/images/spi_pipeline_fir_lab.png`. This is bounded GUI evidence, not
continuous coverage or BER qualification.

A separate A→B v6 BPSK SPI/FIR attempt acquired one frame but raw and filtered
CRC both failed: 10/44 coded errors, 0/8 payload errors, and 725 clipped FIR
samples. TX stopped at 90 ms after 119 completed frames and 64 misses, then
verified idle quiet. This does not negate transport/FIR arithmetic evidence and does not qualify a
modem frame. Later v6 RFS2 results are recorded below.

PMOD A was then backed up privately (2 MiB) and verified against MAC
`78:21:84:d4:4f:98`; the backup application's SHA matches preserved v5
`057dda48dcd6621d9bfd09d06eb565767265ee50b661535e45d22746bca315ef`. The v6
WDT-recovery/timing application
`baac3d3881539cb4321c09bda7245b7a3823762d2b3639e6e21c7d9579fc1dbb` was flashed
successfully; separate verify-flash passed for all images. Install evidence is
`cyberether/run/tx-probe-private/v6-watchdog-install/install-record.json` and
its logs. After the separate manual reset, normal boot passed as
`TX_PROBE,v=6,rev=300,mac=78:21:84:d4:4f:98`, with `busy=0` and CPU 160 MHz;
proof is `cyberether/run/pmod-a-v6-watchdog-boot.json`. The boot record has
`iq=unverified` and explicitly covers startup/identity only. Do not claim RF
output or watchdog recovery from flash verification or normal boot. Automatic
reboot recovery is not hardware-proven. The 500 ms phase-work budget starts
after blocking PHY setup and does not include setup.

Notebook09 passed all 23 offline/default cells; the actual VDS GUI export passed
with 13 blocks. Official checkpoint07 BSP/apps and the portable Quartus ZIP were
rebuilt; the archive has 290 entries and all nine leaf QIPs plus SDC. The full
host suite passes: **201 tests**. No FPGA programming or radio flash was part of
these software/package checks. Continuous capture, the final-image soak result,
PMOD A TX recovery, 100,000-bit RF BER, raw-IQ FPGA synchronization and QAM RF
qualification remain open.


## Current checkpoint07 status FIFO and v6 RF evidence — 2026-10-21

The current checkpoint07 SOF `91a0b547a3c5b0ae8b780c89c31a19940dbf20e660f2ceea5ad602845e9e7881` has source fingerprint `e35b970c093464de6fab3a149e8a603938435d3ca05215e551a16925f1e93db7`. Its four-line whole-line status FIFO fixes the dropped `TX_ON` response. Hardware proof `cyberether/run/tx-status-fifo-hardware-001.json` records the actual acknowledgement for job 4, channel 8, attenuation code 120 and 50 ms, with zero text drops, command/framing/capture errors. Attenuation code is not calibrated RF output power. Quartus reports 27,988/45,800 ALMs (61%), 120 M20Ks and 16 DSP units; the added logic is status queue/control, not RF DSP.

The current-image GUI regression passed 12 alternating pairs (six synthetic, six RF; 196,560 complex samples), exact Hamming integer-reference checks, settings restoration, both UART liveness checks and no JavaScript errors. Proofs: `cyberether/run/spi-gui-1792621578444678407/proof.json` and `cyberether/run/spi-fir-browser-fifo-final.json`. Screenshot: `docs/images/spi_pipeline_fir_lab.png`. The separate RF Link Lab 10 µs QPSK browser run completed four captures and acquired five frames: three CRC passed and two failed, with 35/220 coded errors → 6/40 soft payload errors. Combined with the 32-capture CLI batch, the observed 10 µs group is 36 captures, 35 acquired, 33 CRC pass / 2 fail, 2 no-acquisition, 35/1540 coded → 6/280 soft payload errors.

The independent saved-raw audit passed integrity checks and blind re-decode for all 172 unique v6 captures. BPSK: eight captures, nine acquired frames, eight CRC passes / one fail, 16/396 coded errors → 0/72 soft payload errors (hard decoder 1/72). QPSK: at 12 µs, 34 CRC-valid frames from 64 captures, 30 no-acquisition and 0/1496 coded → 0/272 payload errors; at 10 µs CLI, 30 valid from 32, two no-acquisition and 0/1320 → 0/240; at 9 µs, 23 CRC-valid from 32, seven failures, two no-acquisition, 171/1320 → 27/240 soft payload errors (hard 21/240); at 8 µs, 32 captures produced zero acquired frames because TX completed zero frames. BER is undefined at 8 µs. The 9 µs sample does not show a soft-FEC benefit.

Proofs and grouped denominators are under `cyberether/run/rf-v6-independent-audit/qualification.json`, `rf-v6-bpsk-rfs2-002/proof.json`, `rf-v6-qpsk-{8us,9us,10us,12us}-001/proof.json`, `rf-link-browser-v6-final.json` and `rf-link-20261021-222650-1792621610926103009/proof.json`. The 100,000-payload-bit target, continuous coverage and automatic watchdog recovery remain open. No 16/64-QAM RF or arbitrary-IQ claim follows from these measurements.


## Checkpoint08 preamble observer — current cf2eea09

Checkpoint08's 14-block native VDS export, Quartus build and official Nios V
BSP/Hello World/IQ monitor builds passed. The compiled/routed FPGA implementation
reported 29,472/45,800 ALMs, 152/353 M20Ks and 24/368 DSPs, with 50 MHz setup
slack +6.591 ns and minimum hold slack +0.019 ns. The final current SOF is
`cf2eea090cd7825d23087b2e0dbacc2e5b08c3aa898e98aff5b43ef64205145d`, source
fingerprint `dd6bf7276d85b1a1f73619a69e9aaab6a786184e86ade61af66b6ab414b1f439`.
After a monitor-only `PAIR`/`PRESET` command reservation fix, the Nios boot
memory was refreshed with Quartus's MIF-update/assembler flow. This did not
change RTL or routed logic; the prior timing/resource report applies. The
official BSP and applications were rebuilt but no ELF was downloaded.

Nine RTL fixtures and seven model tests passed. The full host suite passed 228
tests. A regression exposed that the original 8ae98339 image's preamble command
parser intercepted the existing FIR `PAIR`/`PRESET` controls; the corrected
current image passed the FIR regression with 16,380 complex samples, exact
Hamming integer-reference output, valid CRC, restored coefficients, disabled
pairing and host UART back at 2 Mbaud (`preamble-fir-regression-fixed-001`).

The current-image browser checks passed clean synthetic replay, replay of a
saved RFS2 QPSK capture, and one passive PMOD B SPI snapshot. All three proofs
reported `tx_started: false`, valid input CRC, exact full FPGA/reference score
traces, cleanup readbacks and no browser JavaScript errors. Synthetic replay
(10,000 samples) checked 1,257 exact candidates; best start 60, score 32,739,
and 2,091,649 FPGA cycles (41.83298 ms). Saved replay checked 2,852 exact
candidates from the prior `rf-v6-qpsk-10us-001` source-0/job-7 sample; best
start 924, score 32,696, and 4,745,729 cycles (94.91458 ms). Replay adds no new
RF observation. The passive 16,380-sample source-2/job-5 capture checked 2,852
candidates, best start 6,040 and score 4,141, below the 24,576 threshold, so no
preamble was detected. Its SPI sequence/bank/length/CRC, mode restoration and
detector clear checks passed; it took 4,610,049 FPGA cycles (92.20098 ms).

Final PMOD A idle proof `cyberether/run/preamble-tx-idle-after.json` reports v6
`busy=0`, raw tone1 register `0x20000000`, tone2 `0`, extension tone `0`, and
zero amplitude fields for both tones (both disabled); RFS2 host UART is at 2 Mbaud. No test sent a TX command. These results qualify the coarse detector
against this bounded synthetic, saved and passive data; they do not prove exact
TX boundary recovery, payload decode, BER, continuous reception or a full QPSK
FPGA receiver.


## FPGA 64-QAM 100k-bit-per-point symbol replay

Full checkpoint06 Quartus build and programming passed for SOF
`4297a6c946a7bb1381523eccd53ee99864871fb5a66c83edef6c90eb8b2f5441`,
source fingerprint `791fe8cb6fecc0d967d78960f6960e92009f6d3d6e5fdf4db69b2ae772006d68`.
Resources: 28,058 ALMs, 146 M20Ks, 32/368 reported DSP units; clk50 setup
+1.194 ns, hold +0.026 ns. RTL modem structure is unchanged; the new Nios
monitor adds bounded `MSRUN` replay and packed `MSGET` snapshot controls.
The native VDS checkpoint06 diagram still describes this design.

The real-browser sweep processed 391 complete 256-payload-bit frames per point:

| Es/N0 | Pre-FEC errors / coded bits | Post-FEC errors / payload bits |
|---|---:|---:|
| 12dB | 23,559 / 204,884 | 176 / 100,096 |
| 16dB | 10,121 / 204,884 | 0 / 100,096 |
| 20dB | 1,679 / 204,884 | 0 / 100,096 |

Every frame's raw/decoded FPGA counters matched independent Nios comparisons.
All three final-frame snapshots passed exact host checks of payload, coded
bits, mapper IQ, noisy IQ, LLRs and Viterbi output. Noise is the explicitly
labeled sum of twelve uniform PRNG bytes, an approximate Gaussian generated
on Nios; it is not exact AWGN or a real RF signal. No frame failures are
dropped from BER. The run took 36.2337 seconds; FPGA encode/decode work per
level totaled 136,850 / 15,818,296 cycles at 50MHz, excluding Nios/JTAG/audits.
The source tag and actual block ID `0x4d440601` are recorded separately from
the host image hash. No RF acquisition, waveform synchronization or TX occurs.

Run/selectors/browser plotting pass with no JavaScript errors. All 237 host
tests, actual Questa modem tests and notebook08 offline execution passed.
Official checkpoint06 BSP/Hello World/IQ monitor apps rebuilt successfully;
no separate ELF download occurred. The full project ZIP passes CRC integrity
checks and contains the new monitor header (no extracted-project recompile).
TX idle is verified before/after with both tone amplitudes zero and `busy=0`.

The first short run failed because the host parsed hexadecimal `next_bits`
as decimal. It is retained as `qam64-hw-short-001`; the parser regression fix,
`qam64-hw-short-002` and full `qam64-gui-1792626056550406835` proof pass on the
same FPGA image. `qam64-browser-hardware.json` records actual button/selector
checks. See [the guide](docs/FPGA_64QAM_BER.md) for formats, plots and limits.
The 95% zero-error bit bound assumes independent trials and is educational;
convolutional decoder errors may be bursty. No RF BER claim follows.


The presentation view now overlays actual noisy input with coded symbols
reconstructed from the actual FPGA-decoded payload (host display re-encoding/
remapping). All 88 positions are paired. Existing saved NPZ snapshots are
re-audited before enriching older JSON proofs. This does not replace measured
IQ with ideal points or claim that the received waveform was cleaned.

All 238 tests pass, including a deliberate decoded-bit error that must leave
wrong reconstructed symbols visible. Browser checks verify all three frame
error counts, six plots, path toggling, 1080/1500-pixel layouts and absence of
JavaScript errors or POST/hardware requests. No firmware/FPGA changes or new
RF/replay jobs were needed; the saved physical sweep supplies the evidence.

## 2026-10-21 — native Wi-Fi OTA groundwork and actual Nios primitives

Both native original-ESP32 firmware projects compile with SDK commit
`25fe69f946311abdaf9ad56591f25fedbc20ac98`. Neither has been flashed.
Role/pin guards and protocol/control tests reject incorrect targets and
unbounded requests before hardware access. Firmware binaries/build databases
remain ignored. Manual programming-reset availability is pending.

Three passive RFS2 captures at nominal40MS/s and2447MHz passed transport CRC:
16380CI8 samples each, reported411us capture, zero hub command/framing/capture
errors. Actual sample clock/full analog bandwidth are not qualified by this.
No RF transmit was requested. Existing PMOD A v6 reported busy0 and both tone
amplitudes disabled. Capture proof: `cyberether/run/wifi64-wideband-passive-1792630367872929318/`.

New portable integer FFT64/channel/equalizer/64-QAM soft demapper and Wi-Fi54
DATA backend pass independent C/Python fixtures. Register orientation and Gray
bit grouping were checked against the earlier externally anchored receiver and
IEEE/GNU Radio references; end-to-end C demapper→C backend passes payload FCS.
The backend uses 3/4 puncturing, s=3 deinterleave, unforced DATA final state,
SERVICE seed recovery/descramble and CRC. No runtime host decoding was added.

Actual Agilex3 Nios V execution passes5/5: FFT tone, equalizer/null rejection,
all64 constellation labels,92-byte PSDU/4-symbol valid FCS, bad FCS rejection.
ELF SHA `674d89ee92cfd3cf7f4334359b8ee46bad1388f84a2c72e44c118ebce5772467`;
proof `cyberether/run/wifi64-nios-hardware-final/`. Checkpoint06 SOF is unchanged;
original monitor restored and JTAG STATUS confirms no errors. First attempt
using optional mcycle timed out; final version uses memory-mapped mtime and
immutable ELF snapshots. These are finite-burst CPU prototypes, not RTL
acceleration or an integrated live RF decoder. Measured92-byte DATA decode
~416ms at50MHz; continuous wideband processing requires acceleration.

Original-chip TX review identified a specific attenuation-only polar probe;
o new RF amplitude qualification or arbitrary-IQ playback was performed.
See docs/WIFI64_IMPLEMENTATION_STATUS.md for reproducible commands and open gates.


### PMOD A native transmitter installation

PMOD A identity matched before any flash write. The initial configured-layout
backup covered2MiB; JEDEC ID0x164020 identifies4MiB physical storage. The upper
2MiB was retained unchanged by all three programmed images and backed up too.
The first upper read at460800baud lost its serial stream; reconnecting to the
stub at that baud, selecting4MiB flash parameters and reading bounded chunks at
115200baud succeeded. The full physical rollback image is private and hashed.

The native TX app SHA
`36ad44901f58cbf150f162d91ca9cdd59059f3ea2c6448154a49a6d88ad77a16`
was installed. Bootloader, partition table and app all passed device hash
verification. Checkpoint06 SOF restored, GPIO0 released; the normal-boot reset
is pending. No native RF job has run. Evidence: ignored
`cyberether/run/wifi64-install-a.json`, `wifi64-flash-a.log`, and private backups.


### PMOD A normal boot and first bounded native TX job

INFO/IDENT verified the new native11g firmware on the expected module. Initial
busy/armed/rf/stop_err were all0. A two-packet channel8/power-code8 job completed
with accepted2, rejected0, done2, failed0, rate54=2 and other0. Explicit STOP
and STATUS confirmed busy0/rf0/stop_err0. This is transmitter-side callback
evidence only; independent RX confirmation and raw-IQ FCS/BER remain pending.
The expired boot listener was recovered with INFO/STATUS queries, requiring
no additional reset. Proofs: `wifi64-a-boot-query.json` and
`wifi64-a-first-native-job.json` in the ignored run directory.


### Standalone L-SIG decoder

New portable C header decodes48 equalized BPSK soft values through inverse
interleaving and terminated K7 Viterbi, validates reserved/parity/tail/RATE/length,
and reports all8 legacy rate metadata. First-transmitted-bit-as-LSB codes are
54Mb/s=12 and48Mb/s=8, independently anchored to the existing6Mb/s RF reference
and primary GNU Radio generator/parser. Five native test groups pass. A separate
RV32I ELF builds and native4/4 fixtures pass; it has not been downloaded yet.
Use `wifi64_signal_nios_selftest.py` then `check_wifi64_nios.py --hardware --signal`
with a new proof directory and checkpoint06 restored. No new synchronization or
raw-IQ receiver integration is implied. Total host suite276 tests passes.


### Compile-only original-chip amplitude probe

Separate `firmware/original_iq_tx_probe` builds against the pinned original-chip
SDK. ATTEN/CONTROL commands are bounded to3–50ms with2s cooldown. Register
masking and strict parser tests pass1024 cases. RF-window snapshots are buffered
and all job telemetry is emitted after stopping, paced2ms per row. Direct tone
enable clearing does not wait for a vendor API mutex; vendor initialization and
interrupts still prevent claiming a proven physical50ms cutoff. First setup may
consume the whole budget and must not be reported as a successful RF trial.
App SHA `e5f5e28787d5990505712573eff7b2a7fc59b5f06055ec808cb64d4f2bac49ad`.
No installation, programmer whitelist, amplitude calibration or RF measurement
was performed for this probe. Native PMOD A firmware is unchanged.


### Fixed-point acquisition and display-only native viewer

Portable C frontend accepts20/40MS/s vectors and rejects16MS/s;40MS/s uses
129 Q15 taps with valid filtering/2 decimation. Independent exact FIR and
13MHz alias rejection (>35dB), STF/LTF timing, CORDIC quadrants, CFO, noise,
multipath, clipping and failure/input-preservation tests pass in5 groups.
RV32I compilation succeeds. This finite-burst CPU prototype is now integrated
into Stage11 Nios for one successful captured-packet decode (documented below),
but it is not a streaming RTL accelerator or BER qualification.

Display-only `cyberether/wifi64_native.py` and HTML show saved native packet
observations separately from FPGA raw-IQ decoder output. At the time of these
initial UI checks no successful raw-IQ decode proof had been published; the
later packet decode is documented below. Three server tests pass. Actual
Chromium checks in the desktop container pass without JavaScript
errors: GET-only requests, waiting state, per-run transmitter precedence, chart
rendering and mobile width. Chart checks used clearly separate synthetic UI
fixtures, not radio evidence; waiting-RX screenshot uses actual saved A callback
evidence with independent RX explicitly unknown. No service was left running
and no RF was started by these browser checks.


### Complete portable C receiver prototype and finite hardware integration

`sw/wifi64_receiver.h` integrates40→20MS/s FIR, STF/LTF acquisition/CFO,
FFT64, channel equalization, pilot phase tracking, L-SIG,64-QAM soft demapping
and the Wi-Fi DATA decoder. Five independent synthetic waveform test groups
pass, including exact92-byte FCS, CFO/multipath/noise, failed-FCS retention,
unsupported headers, truncation and a capture with two candidates (first
unsupported, second valid). Equalized EVM across three synthetic cases is
2.21–3.97%; these are generated fixtures, not RF measurements.

Caller workspace/result total107840bytes. A freestanding RV32I link needs
126980bytes before its4KiB stack allowance, so128KiB fails the linker guard;
256KiB passes. The Stage11 larger-memory-map build passes timing (setup +2.777ns,
hold +0.016ns) with27,769/45,800 ALMs,242/353 M20Ks and32/368 DSP units
reported. Bounded hardware integration and one successful real-packet decode
are recorded below. Continuous raw-capture RAM operation and BER qualification
remain pending. Earlier offline checks did not change the existing hardware/runtime or
selftest ELFs.

`wifi64_ota.py --publish` is opt-in, validates a new proof path under the run
directory before device access and atomically updates the display pointer only
after the proof file closes. Five new publication tests pass; default behavior
remains nonpublishing. No extra radio job was run for these tests.

### Wi-Fi 64-QAM native OTA and Stage 11 build update

PMOD B's physical4MiB rollback image was captured before flashing; SHA-256:
`780d150511dcd0544e16bda55045d117aab2d995cf05b0aadf7e880e19444d51`. All three
installed images passed device hash verification. With the runtime bridge
restored, normal boot was verified through INFO/STOP/STATUS.

The bounded native OTA proof `cyberether/run/wifi64-native-ota-002.json`
completed: both expected packets were received and matched on channel8 at
54Mb/s (RATE code12, SIG mode0, RX state0), RSSI −17dBm, length92, with matching
run, seed and body. Transport-error and drop deltas were zero; transmitter A
verified RF-off and receiver B was stopped at completion. This demonstrates
actual native PHY packet reception over RF. It does not demonstrate FPGA raw-IQ
decoding, constellation/EVM, or BER; those remain unqualified.

Stage11 FPGA build timing passed with setup slack +2.777ns and hold slack
+0.016ns. Reported resource use was27,769/45,800 ALMs,242/353 M20K blocks and
32/368 DSP units. These are build results, separate from receiver qualification.

### Stage 11 first passive real-capture attempt (historical failure)

Stage11 was programmed, and baseline bridge identity, NIOSSTATUS and MSVERSION
checks passed. The capture ELF ran on the real RFS2 source0 capture at nominal
40MS/s: 16,380 CI8 samples, reported duration411us. Nios verified the capture
copy was exact and stable. The full C decoder ran for 7,369,960,022 timer ticks
(147.39920044s at50MHz) and returned status4 (acquisition failed), zero
candidates, no decoded header, and no payload FCS or BER result. It reported134
clipped raw components. Proof:
`cyberether/run/wifi64-stage11-passive-first-decode.json`. No TX was requested
during this passive check.

This first attempt passed bounded hardware integration and capture-copy checks,
but failed decoding this particular capture. It produced no acquisition
candidate, so L-SIG/payload/FCS validation and BER were not reached. This is
historical per-capture failure evidence; a separate later run successfully
decoded one raw-IQ packet (see below). At the time of this run,314 host tests
passed, including eight tests for the new `program_wifi64.py` helper.

### Stage 11 FPGA modem replay and capture-app controls

Checkpoint11 FPGA modem replay passed four fixed64-bit payload fixtures: BPSK,
QPSK, 16-QAM and64-QAM all decoded exactly, with raw and decoded error counts
both zero. Each waveform's symbols were generated and decoded in FPGA RAM;
the host issued batched CSR controls and assertions. Encode/decode cycles were
210/10,704 (BPSK), 140/10,564 (QPSK), 105/11,614 (16-QAM) and94/15,496
(64-QAM). Proof: `cyberether/run/wifi64-stage11-modem-replay-hardware.json`.
This is FPGA modem replay validation, with **no RF** and no IEEE Wi-Fi packet
qualification.

The capture-app ELF `e7525f3a67f8cb63a221177cb4ec90ce05f3f2b1fdd2eced89a56cfa54589c26`
adds and passes hardware WCANCEL validation (ready→idle with cache invalidation)
and reports `WVERSION cancel_supported=1`. The previously reported147.399-second
real-capture decoder run is a separate proof and ELF identity (`99e9…`); these
modem replay results do not change its acquisition-failure result. The capture
app was restored after this test. The host suite had315 passing tests before the
new RF-controller tests were added.

### Stage 11 raw-IQ native OTA packet decode

The later proof `cyberether/run/wifi64-raw-native-ota-007.json` records a
successful finite-burst decode with Stage11 SOF SHA-256
`0d164d03ca627e9d3007070631cab273043e268eb806b077815ad78c61f25efa` and Nios app SHA-256
`a720cb729a318e9c9d98e66a8fa7c0236c9258d37d4eca63e1007e1171eb128c`. A bounded
PMOD A channel11 burst accepted/completed8/8 packets at54Mb/s, all completed
normally, and STOP/idle checks passed with zero counter deltas. PMOD B
independently matched8/8 packets with RATE12, SIG mode0, RX state0, RSSI −17dBm
and matching bodies.

RFS2 source0 captured nominal40MS/s, 16,380 CI8 samples at 2462MHz; conjugation
was enabled. The Nios C receiver decoded L-SIG RATE12 (54Mb/s), length92, then
four DATA symbols (192 real Q13 points, zero clipped points). Its exact 92-byte
payload matched run2026102111, packet0, seed1; computed and received FCS were
2497505256 (`0x94dce7e8`). The run took 7,515,341,840 timer ticks
(150.3068368s at50MHz). This confirms one raw-IQ packet decode using Nios CPU
software, not parallel RTL acceleration. No raw BER or 100,000-bit measurement
was made; continuous capture-RAM operation and raw-IQ BER remain open. This
proof is separate from the earlier147.399-second acquisition-failure run and
does not replace its historical record. The host suite had341 passing tests
before the GUI work.

The final host suite passes **354 tests**, including the raw-proof publisher,
bounded capture controller and viewer. Desktop and 390-pixel mobile browser
checks show the actual 192-point constellation, channel11, 54Mb/s, passing FCS,
92 bytes and 150.3 seconds. The older channel8 native-monitor proof is explicitly
labeled as a separate saved run. Browser requests were GET-only, with no
JavaScript exceptions or mobile horizontal overflow. The read-only page is on
port8774; it does not transmit. Screenshot and browser evidence are retained in
`cyberether/run/wifi64-native-real-raw-007{,-mobile}.png` and
`cyberether/run/wifi64-native-real-raw-007-browserproof.json`. A portable picture
of the real decoded points is included at
`docs/images/wifi64_real_ota_constellation.png`.

### Narrow native-RF presentation

The read-only `/story` page on port8774 presents an ideal TX alphabet reference,
the actual192 received points, and actual decoded packet bits (not a fabricated
post-FEC IQ cloud). An SVG diagram distinguishes the native Wi-Fi PHY from
Agilex3/Nios reception and marks original-chip custom IQ injection as unproven.
Desktop1200px and mobile390px browser checks passed: correct channel11/54Mb/s,
92bytes/FCS/150.3seconds, loaded diagram, GET-only requests, no JavaScript
exceptions or horizontal overflow. All354 host tests pass. No radio or FPGA
programming was performed for this display change. See
[presentation scope](docs/WIFI64_PRESENTATION.md).

### Original-chip custom-QAM execution preparation

The separate amplitude diagnostic builds against pinned SDK25fe69f9; application
SHA-256 remains `e5f5e28787d5990505712573eff7b2a7fc59b5f06055ec808cb64d4f2bac49ad`.
A Kconfig identity flag now enables explicit PMOD-A-only programmer validation,
including original ESP32 target, certification/unicore options, UART17/16,
manifest offsets and image hashes. Flash dry-run passed without device access.
Bridge Questa simulation passes all6routes×64combinations with GPIO0 low/Z.
All362 host tests pass, including simulated capture timeout, wrong target,
wrong job and cleanup paths for the new one-job raw-snapshot controller.

Before programming preparation, actual native-A STOP and STATUS both reported
busy0/armed0/rf0/stop_err0. Existing stage11 SOF and capture-app hashes and source
guards pass. Fresh native-A full-flash backup must be taken after the manual
bootloader reset and before any write. This is preparation, not measured RF
amplitude/phase or arbitrary-IQ qualification. See the
[execution plan](docs/CUSTOM_QAM_EXECUTION_PLAN.md).

### Original ESP32 RF amplitude gate measured

DiagnosticV1 `e5f5e287…` was actually installed on MAC78:21:84:d4:4f:98 after a
fresh4MiB native-TX backup (SHA88a517b5…) matched the original app bytes. Flash
and independent digest verification passed; stage11 SOF0d164d03… and Nios app
a720cb72… were restored. The manual normal-boot reset yielded READY, correct
identity, busy0 and RF-uninitialized before RF experiments.

One initialization-only CONTROL and one clipped AGC CONTROL are excluded. Two
manual-gain0 CONTROL captures measure RMS96.9639/96.0927; two ATTEN120 captures
measure4.2458/4.2010; one ATTEN121 capture measures4.3695. All five have zero exact
rail hits. Three later TX-off snapshots measure1.0479/1.1183/1.0908. Every accepted
job restores attenuation/protected fields and reports STOP/busy0/registers-off.
The measured register windows are about50.5–50.6ms for requested50ms jobs, not a
proven hard RF cutoff. The carrier is near17.094kHz in the same FFT search for
all five active snapshots. Offline host audit gives27.1799dB median total ADC
power difference for CONTROL/code120; no calibrated attenuation, phase
continuity, linearity, EVM, arbitrary-IQ or QAM claim follows.

V2 `9c2330db…` builds with explicit LEVEL0..127 and TRAIN32..128us, first16 register
edge traces and scheduling-lateness counts. It is not yet installed or RF-tested.
The controller refuses these commands on V1 before TX, supports checked manual
RX gain and restores settings. All370 host tests pass, including corruption,
clipping, gain-readback and firmware-capability rejection. Full saved proof
names and the aggregate plot are in
[the amplitude results](docs/ORIGINAL_IQ_AMPLITUDE_RESULTS.md).

### V2 stack fault and V3 correction

V2 `9c2330db…` passed flash/digest verification and normal RF-uninitialized boot,
but CONTROL and TRAIN0 attempts crashed during PHY initialization with an
`oiq_probe` stack overflow. No transition qualification follows. Proofs
`original-iq-v2-init-001.json` and `original-iq-v2-train0-001.json` retain the
fault/reboot; both cleanup sequences reached STOP/busy0, and a later STATE
reports RF-uninitialized. The controller now refuses V2 before RF.

V2's16-record stack trace made the compiler worker frame896bytes. V3 moves it
to static RAM, reduces the frame to384bytes and increases the task stack from
4096 to8192bytes. Compiler stack usage is generated and checked before accepting
the build; runtime INFO/STACK report the measured minimum remaining stack.
Local compiler frames do not include the vendor call tree, so hardware margin
still requires qualification. V3 app SHA-256:
`b112c38a155d66dceaa5a860ab850051280714a0e764c53fc2f7d43750de62a0`.
It is built, not yet installed or hardware-qualified. The host watcher detects
panic/reboot immediately while keeping STOP/cleanup usable. Tests cover the
original896-byte-frame regression, panic/reboot detection and V2 refusal.
All376 host tests pass; V3 flash dry-run and compiler stack checks pass.

### V3 on-device stack and same-capture RF transition tests

V3 b112c38a… passed actual flash/digest, normal boot and initialization. The
initialization-only CONTROL opened no tone-register window; its177191us setup
exceeded the50ms budget and is excluded from RF success. Runtime minimum stack
free is4000bytes for the8192-byte worker and2664 for the guard. No V3 panic/reboot
was observed in the recorded tests.

TRAIN0 controls captured one stable level. TRAIN120/32us captured11 amplitude
transitions; TRAIN24 captured3 at32us and3 at64us, all with zero exact rail hits,
matched job IDs, field/gain restoration, STOP and busy0. A5MHz RX-offset control
and two TRAIN24 attempts are retained: first captured only one level, second
captured6 transitions. Offset did not remove phase disturbance. Estimated
low/high phase offsets are−2.42° (24/32us nearDC),−5.24° (24/64us nearDC) and−3.84°
(24/32us offset); these are end-to-end offline model estimates, not calibrated
TX phase or EVM. Weak code120 has a poor model fit. Later passive snapshots and
quiet register checks passed. No custom-QAM payload/FEC/BER qualification.

Source adds an offline NumPy audit, explicit receiver-offset profiles and a
read-only `/tx-research` page displaying the aggregate plot. Raw SHA/CRC/profile,
gain and clipping checks precede fitting. Synthetic tests cover known AM/PM/DC,
unchanged-code rejection and negative IQ orientation. See
[full results](docs/ORIGINAL_IQ_TRANSITION_RESULTS.md) for proof names and limits.
All383 host tests pass. `/tx-research` desktop1200px/mobile390px browser checks
passed with loaded plots, explicit offline-analysis / unqualified-QAM labels,
GET-only requests, no JavaScript errors and no horizontal overflow. All UART/JTAG
owners were released after the final passive check.

### Combined PMOD A TX lab (2026-10-21)

- `firmware/tx_lab` links the existing AMP, native Wi-Fi and PHASE engines into one
  original-ESP32 image, selected by an idle-only UART command and software reboot.
- Pinned SDK build and compiler stack checks pass (AMP worker frame384B, PHASE
  worker frame128B; both task stacks8192B). Image fits the1MiB app partition.
- Host suite:388 tests pass, including strict RTC selector, mode/readback and
  PMOD-A-only flash-profile checks. These tests do not establish RF behavior.
- Installed image SHA256 `2c563abc99eb31a8fa595bbdc2db19c713e0fb90d678f725e47c2d51c976940a`
  (651,936 bytes) passed flash/digest checks. Runtime checkpoint11 SOF and capture
  app were restored; normal boot verified PMOD A MAC78:21:84:d4:4f:98 and RF off.
- Six software mode transitions passed without another physical reset. Startup
  text can be missed; live mode/quiet readback is required. A transition after
  certification PHY use returned to RF-off AMP; one software retry recovered it.
  The reset cause remains unisolated. Repeated fallback is a hard test failure.
- Native channel11 test: PMOD B independently qualified both requested54Mb/s
  packets, clean FPGA transport, final TX off. AMP initialization consumed its
  first50ms budget; the next30ms TRAIN24/64us passed register and cleanup checks
  with a saved independent RFS2 raw snapshot. This is not a received-QAM proof.
- Short PHASE telemetry observed bounded TX_OFF, but missed startup/INFO/TX_ON
  lines prevent accepting its attempt as a complete RF frame qualification.
  No new custom-IQ or custom64-QAM RF claim is made.
- Final host suite:393 tests pass. A full preflight round of mode changes, AMP
  initialization/training, native two-packet reception and final AMP/RF-off passed.
  The optional three-hour runner uses20-minute intervals, stops on first failure,
  and excludes PHASE transmission. Its status/logs remain private under run/.


### Checkpoint11 text transport and incremental calibration (2026-10-21)

- Root intentionally stopped the initial endurance run after its first passing
  round and RF-off cleanup to repair a reproducible transport loss. A later
  native check received2/2 packets but failed on one dropped telemetry line;
  this failure is retained, not reclassified as a pass.
- Stage11 now ports checkpoint07's four-slot255-byte text FIFO, preserving the
  three UART profiles. Questa checks line bounds,2Mbaud back-to-back CFG/TX_ON,
  queue order/full/drop and simultaneous full pop/push against actual stage11 RTL.
- SOF `e856a75c37c7cefe2a016449cfbf320bdd5191f4c788e25b16ce5f52ac1697cf`
  passes fit/timing and is loaded with the unchanged capture app `a720cb72…`.
  Resource report:42,025/45,800 ALMs(92%),242/353 M20Ks,32/368 reported DSPs.
  Setup+2.244ns, hold+0.001ns. The small hold margin and high logic allocation
  remain material limits; a RAM-backed text FIFO is the next area optimization.
- Six hardware software-mode transitions pass. Long READY/INFO plus complete
  QFRAME_CFG/TX_ON/TX_OFF/PHASESTAT are now received. Tone and phase jobs request
 50ms; measured reported elapsed windows include50,172us and48,516us. These
  are software/telemetry windows, not independent hard RF cutoff measurements.
- The first new phase-capture script accidentally sent receive code1 while
  declaring16MS/s. Its source and capture are retained privately with explicit
  profile rejection. The corrected script uses code6 and records that command;
  its new raw snapshot passes CRC/profile/job checks and RF-off cleanup.
- Corrected phase raw audit acquires one frame but fails CRC:16/44 coded and3/8
  soft payload errors. Analysis is offline host Python, not FPGA demodulation.
  Eight payload bits do not qualify BER. No custom64-QAM or arbitrary IQ claim.
- Incremental preflight passes:2/2 independent native packets, no job-local
  transport errors, two accepted code24 fits (ratios0.7419/0.7459, mean model
  phase−4.29°), final RF-off AMP. A new three-hour process runs gated amplitude
  candidates and independent native checks; it excludes PHASE transmission.
- Final host suite:405 tests pass. Calibration viewer GET-only desktop/mobile checks pass with no JS errors or
  horizontal overflow. The page distinguishes measured ADC ratios from
  theoretical QAM radii and identifies the offline host fitting backend.
