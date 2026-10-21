# Native VDS GUI diagrams

These PNGs were exported through **Quartus Visual Designer Studio → File → Export**, then rasterized from the native PDF at 4,000 pixels. They show the actual blocks, ports and wiring.

| Checkpoint | PNG | Blocks |
|---|---|---:|
| 01 · Raw IQ bridge | [Open diagram](01_vds_gui.png) | 6 |
| 02 · Nios V transfer monitor | [Open diagram](02_vds_gui.png) | 11 |
| 03 · FIR II filtering | [Open diagram](03_vds_gui.png) | 13 |
| 04 · Frequency translation and decimation | [Open diagram](04_vds_gui.png) | 16 |
| 05 · Digital gain and power meters | [Open diagram](05_vds_gui.png) | 17 |

Every notebook includes its saved preview. Running its generation cell refreshes the local export and displays the PNG inline:

```python
from IPython.display import Image, display
diagram_png = lesson.generate()
display(Image(filename=str(diagram_png)))
print("Exported:", diagram_png)
```

Export files are saved under `fpga_hub/iq_bridge/vds_demo_*/results/notebook/`: `vds_diagram.png`, the original `vds_diagram.pdf`, `vds_gui_window.png` (full GUI screenshot), and `vds_gui_export.json` (verified cell names and provenance). Export uses a private X display and a separate project copy. The GUI automation is tested with Quartus Prime Pro 26.1.1.
