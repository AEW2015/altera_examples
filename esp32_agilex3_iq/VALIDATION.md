# Clean source validation

All five checkpoint projects were regenerated and fully compiled from this branch in a new checkout directory, using Quartus Prime Pro 26.1.1 Build 130. Generated vendor HDL, cached IP, Nios HEX, reports and bitfiles are excluded from Git. A second export containing only the staged Git tree also regenerated checkpoint 5 successfully, with no preexisting diagrams, IP caches or Nios HEX.

| Checkpoint | ALMs | RAM blocks | Quartus DSP blocks | Minimum reported slack (ns) |
|---|---:|---:|---:|---:|
| vds_demo_01_raw | 5227 | 35 | 0 | +0.089 |
| vds_demo_02_nios | 9325 | 72 | 0 | +0.025 |
| vds_demo_03_fir | 10398 | 104 | 16 | +0.012 |
| vds_demo_04_ddc | 11899 | 140 | 22 | +0.028 |
| vds_demo_05_gain | 12121 | 140 | 26 | +0.007 |

The reported minimum is across the timing checks in each STA summary, not a statement that every external/asynchronous I/O path is fully constrained. Compiled DSP counts use Quartus's reported units (368 total), not 184 physical DSP blocks.

- **23 host tests PASS** in a newly created Python 3.12 venv with the pinned requirements: transport CRC and bounds, FIR/DDC/gain references, HTTP control/authentication, sample fixtures and bind-mount path resolution.
- **Standalone Questa gain RTL lesson PASS:** bypass, half, double, saturation and zero, with exact integer and power-meter assertions. This does not simulate Nios instructions or the full vendor FIR system.
- **Original ESP32 firmware build PASS** against the pinned ESP-IDF/ESP-DSP source revisions, using the existing matching SDK cache. No ESP32 was flashed or reset for this validation.
- **CyberEther v1.15.0 download and SHA-256 verification PASS;** GStreamer shim compiled from source. The native graph started from the new checkout on a separate port without radio acquisition. During the physical test, the browser displayed the native lesson video and all five HTML tabs. During the physical test, the browser displayed the native lesson video and all five HTML tabs.
- **Fresh final bitfile tested on the physical Atum A3 Nano:** real RFS2 RF captures, 16,380 CI8 pairs, paired raw/Hamming transport CRC valid and independent FIR reference error **0 LSB**. The FPGA clean two-tone generator was then processed by the FPGA DDC with decimation 4 and 2× digital gain; CI16 readback and all reported integer power meters matched the independent host reference exactly.

Final hardware-tested image SHA-256: `69b1ca29a00812e28f1fa22506ea108f37f6da64a796c8281fadb2a5c9a6ec2a`.

This is a targeted rebuild and live hardware check, not a long-duration soak or an exhaustive RF receiver qualification. The separate Wi-Fi Receiver Lab is outside this source package and is restored after testing.
