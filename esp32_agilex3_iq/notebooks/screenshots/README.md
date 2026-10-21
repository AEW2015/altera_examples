# CyberEther example screenshots

These PNGs are saved browser views from physical Atum A3 Nano / Agilex 3 hardware tests. They appear at the end of notebooks 01–06 and render without launching a server or running a cell. Click a full-resolution link for detail. They contain page content only, without private invitation URLs.

| Image | Signal and example |
|---|---|
| `01_cyberether.png` | Live RFS2 ESP32 RF through the raw bridge |
| `02_cyberether.png` | Live RFS2 ESP32 RF and Nios V transfer counters |
| `03_cyberether.png` | FPGA two-tone test, 4 MHz FIR notch |
| `03_fir_custom_editor.png` | FPGA two-tone test, custom eight-sample average and coefficient editor |
| `04_cyberether.png` | FPGA two-tone test, frequency shift/filter/decimation |
| `05_cyberether.png` | FPGA single-tone test, 16× gain and clipping |
| `06_cyberether.png` | RF Arcade Power rush, FPGA test signal at 16× gain |

The source captures were produced by `scripts/check_notebook_hardware.py --browser` in its ignored runtime output directory. These are static examples of verified captures, not current acquisition status. Display FFTs and plots are host computations; filtering, mixing, decimation and gain/meters run in the FPGA. Notebook 07 is an offline firmware lesson with no CyberEther demo section.
