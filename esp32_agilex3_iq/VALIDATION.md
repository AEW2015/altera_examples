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
