#!/usr/bin/env python3
"""Generate the authored lessons and RF Arcade setup notebook; outputs are produced by local execution."""
import ast
from pathlib import Path
import nbformat as nb
from common import ROOT,stages
from lessons import NAMES
source=ast.parse((ROOT/'scripts/notebook_plots.py').read_text());function=next(x for x in source.body if isinstance(x,ast.FunctionDef)and x.name=='theory')
chain=next(x for x in function.body if isinstance(x,ast.If));cases=[]
while True:
 cases.append(chain.body)
 if len(chain.orelse)==1 and isinstance(chain.orelse[0],ast.If):chain=chain.orelse[0]
 else:cases.append(chain.orelse);break
introductions=[
 ('x[n]=I[n]+jQ[n]','CI8 is two signed bytes per complex sample. A short RF burst is stored in FPGA RAM, protected by CRC, then read over UART. The host FFT is a display operation.'),
 ('rate=event_count / window_seconds','FPGA counters collect events without CPU involvement. Nios V reads one coherent snapshot and reports it through JTAG UART. This notebook does not simulate Nios instructions.'),
 ('y[n]=Σ h[k]x[n−k]','A 16-tap FIR performs convolution. Quantized Q15 coefficients, nearest rounding and saturation are part of the hardware contract.'),
 ('z[n]=x[n]·exp(−j2πf₀n/fₛ),  y[m]=(h*z)[mM]','Translate frequency, reject the interferer, then decimate. The physical experiment uses a clean FPGA-generated two-tone snapshot; it does not transmit RF.'),
 ('y=saturate(round(g·x)),  P=Σ(I²+Q²)/N','Gain runs in FPGA logic/DSP alongside integer power and clipping meters. Twice the amplitude gives about +6.02 dB power until saturation.')]
lesson_intros=[
 ('A raw-IQ bridge between three ESP32 UARTs and host Python.', 'See the received samples and establish a trustworthy input before adding DSP.', 'FPGA UART parsers accept signed CI8 I/Q pairs, check framing/CRC and freeze a burst in RAM. The host reads an IQB1 frame and draws its FFT.', 'ESP32 → UART / CRC → FPGA RAM → Python'),
 ('A Nios V/m processor, JTAG UART and transfer counters.', 'Measure where the data rate is limited and spot transport errors independently of the display.', 'FPGA logic counts events in one-second windows. Nios reads a coherent register snapshot and prints rates/status over JTAG; the official HAL BSP and Hello World are included.', 'FPGA events → counters → Nios V → JTAG console'),
 ('A selectable, reloadable 16-tap FIR II filter.', 'Compare noise/interference reduction with the original capture and see what filtering removes.', 'Vendor FIR II multiplies samples by Q15 coefficients and sums the taps. FPGA snapshot logic returns paired raw/filtered data with defined rounding and saturation.', 'Captured IQ → FIR II → raw / filtered comparison'),
 ('Frequency translation and decimation: a digital downconverter.', 'Move a wanted signal to the center, reject a neighbor and reduce the output rate without aliasing.', 'An FPGA phase accumulator and complex mixer shift frequency; separate I/Q FIR II filters remove unwanted energy before keeping every Mth sample. A clean FPGA two-tone pattern makes the effect easy to see.', 'IQ → NCO / mixer → I/Q filters → decimator'),
 ('Digital gain, saturation and power/peak/clipping meters.', 'Show why doubling amplitude adds about 6 dB, and how too much gain creates clipping and harmonics.', 'FPGA fixed-point multipliers scale CI16 samples, saturators enforce the output range, and integer accumulators measure power/peak/clips. CyberEther displays the samples and reported meters.', 'DDC output → gain → saturate / meter → CyberEther'),
]
levels=['Real UART TX/RX module loopback, binary bytes and 8N1 framing.','Real counter RTL with scaled 10-cycle windows, snapshot and reset checks.','Actual generated FIR II VHDL plus capture controller; impulse, custom coefficients, rounding and saturation.','Actual generated I/Q FIR II plus DDC/snapshot RTL, four mixer/filter/decimation cases.','Real gain/meter RTL: bypass, half, double, saturation and zero; all integer outputs and meters checked.']
tries=['Compare I/Q waveform, scatter and display spectrum. The points are raw IQ, not decoded modulation symbols.','Watch actual one-second radio/host byte counts. Pause acquisition and observe the counter age; these are rates, not calibrated RF bandwidth.','Toggle Hamming and Boxcar. Each displayed filtered result is independently checked against the configured integer coefficients.','Select Shift + filter + decimate, then no filter. The interferer folds into the output band when anti-alias filtering is bypassed.','Try 0.5×, 1×, 2×, then 4× or 16×. Watch actual power meters and clipping.']
def write_notebook(notebook, path):
 # Keep authored cell IDs stable when regenerating unchanged content.
 if path.exists():
  previous = nb.read(path, as_version=4)
  ids = {(c.cell_type, c.source): c.id for c in previous.cells}
  for cell in notebook.cells:
   if (cell.cell_type, cell.source) in ids:
    cell.id = ids[(cell.cell_type, cell.source)]
 nb.write(notebook, path)

for i,name in enumerate(NAMES,1):
 cells=[nb.v4.new_markdown_cell(f'# {i} · {name}\n\n**Local Quartus workflow · host or container · one active FPGA design at a time**\n\n`{introductions[i-1][0]}`\n\n**What is added:** {lesson_intros[i-1][0]}\n\n**Why it is useful:** {lesson_intros[i-1][1]}\n\n**How it works:** {lesson_intros[i-1][2]}\n\n```text\n{lesson_intros[i-1][3]}\n```\n\nPython model → native VDS diagram → real RTL/IP simulation → SOF → board → focused CyberEther page.'),
 nb.v4.new_markdown_cell('## Setup\n\nOnce, from this example folder: `bash scripts/install_local.sh --system` (Linux system packages need sudo), then select **Atum A3 IQ Demos** as the notebook kernel. Quartus/Questa/Nios tools must already be installed. Set the optional paths below if they are not on PATH. No Docker commands are needed.'),
 nb.v4.new_code_cell(f'''from pathlib import Path
import os, sys
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "scripts/lessons.py").exists())
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "cyberether"))
# Optional overrides, set before tool discovery:
# os.environ["QUARTUS_ROOTDIR"] = "/your/install/quartus"
# os.environ["QUESTA_ROOT"] = "/your/install/questa_fse"
# os.environ["ATUM_ALTERA_ROOT"] = "/your/install"
# os.environ["ATUM_UART"] = "/dev/serial/by-id/your-board"
# os.environ["ATUM_JTAG_CABLE"] = "your cable from jtagconfig"
from lessons import Lesson, lan_ip, stop_demo
from common import tool_exe
CHECKPOINT = {i}
FORCE_REBUILD = False   # Fresh checkout builds; source-matched SOFs are reused afterwards.
lesson = Lesson(CHECKPOINT)
HOST = lan_ip()
print("Python:", sys.executable)
print("Quartus:", tool_exe("quartus_sh"))
print("Questa:", tool_exe("vsim"))
print("Browser host:", HOST)
''',metadata={'tags':['setup']}),
 nb.v4.new_markdown_cell('## 1 · Python simulation\n\nThe code below is the editable numerical model. Its plots are synthetic/theory, separate from the RTL results and live hardware below.')]
 code='''import numpy as np
import matplotlib.pyplot as plt
from notebook_plots import spectrum
from nios_fir import PROFILES, fixed_reference
from nios_ddc import reference, gain_reference
from iq_lab_samples import load_sample
raw, _ = load_sample("two-tone")
fs = 16e6
n = CHECKPOINT
'''+ '\n'.join(ast.unparse(s)for s in cases[i-1])+'''
fig.suptitle(f"{CHECKPOINT} · Python simulation / integer reference")
fig.tight_layout()
plt.show()
summary
'''
 cells += [nb.v4.new_code_cell(code,metadata={'tags':['theory']}),
 nb.v4.new_markdown_cell('## 2 · Generate the actual FPGA block design\n\nRebuild the Nios initialization memory where present, recreate the native VDS system, validate and generate vendor IP. The cell opens **Quartus Visual Designer Studio itself**, fits the diagram and uses **File → Export**. Its native PDF is rendered to a high-resolution PNG and displayed inline. The original PDF and a full GUI screenshot are saved beside it. A private X display keeps capture separate from your desktop. The output also provides **Quartus project** and **complete project ZIP** links. The ZIP contains the SDC, RTL, generated IP and Nios memory initialization. Extract it before opening the QPF in Quartus.'),
 nb.v4.new_code_cell('from IPython.display import Image, display\ndiagram_png = lesson.generate()\ndisplay(Image(filename=str(diagram_png)))\nprint("Exported:", diagram_png)',metadata={'tags':['generate']}),
 nb.v4.new_markdown_cell(f'### Saved native VDS GUI diagram\n\n![Checkpoint {i} — actual VDS GUI export](diagrams/{i:02d}_vds_gui.png)\n\nThe cell above refreshes this diagram from your local design.'),
 nb.v4.new_markdown_cell(f'## 3 · RTL/IP simulation\n\n{levels[i-1]}\n\nThe plots below read the actual simulator output files. Assertions must pass before the result is plotted.'),
 nb.v4.new_code_cell('simulation_result = lesson.simulate()\nprint("Simulation:", simulation_result["status"])\nlesson.simulation_plot()',metadata={'tags':['rtl']}),
 nb.v4.new_markdown_cell('### Open the Questa GUI\n\nUse a desktop terminal **on the machine running Quartus** (or its container desktop). Execute the printed commands. `wave.wlf` opens the saved real simulation; `view.do` adds its signals. To rerun interactively, start `vsim -gui` in the same directory and type `do gui.do` in the Transcript. This reruns the same assertions and leaves the waveform window open.'),
 nb.v4.new_code_cell('lesson.questa_gui()',metadata={'tags':['instructions']}),
 nb.v4.new_markdown_cell('## 4 · Build the SOF\n\nA source-matched, hash-verified cached bitfile can be reused for a quick presentation. Set `FORCE_REBUILD=True` to demonstrate a full Quartus compilation. A fresh checkout always requires a build. Both a new build and cached reuse display links to the complete Quartus project and its ZIP. Open the linked QPF (or extract the ZIP first), then use **Processing → Start Compilation** to build in the GUI.'),
 nb.v4.new_code_cell('build = lesson.build(force=FORCE_REBUILD)\nprint("SOF:", lesson.stage / "iq_bridge_vds.sof")\nprint("SHA256:", build["sha256"])\nprint("Compiled resources:", build["resources"])',metadata={'tags':['build']}),
 nb.v4.new_markdown_cell('## 5 · Program the physical board\n\nThis cell **programs the selected checkpoint**. It first stops a previous notebook-owned demo and releases UART/JTAG. Stop any unrelated acquisition service before running it; an unknown serial owner is refused. No ESP32 flashing or reset-button presses are needed with the installed suite.'),
 nb.v4.new_code_cell('lesson.program()',metadata={'tags':['hardware','program']}),
 nb.v4.new_markdown_cell('## 6 · Focused CyberEther demo\n\n'+tries[i-1]+'\n\nThe page uses the bitfile just programmed. One board and one acquisition owner are shared across all notebooks.'),
 nb.v4.new_code_cell('live = lesson.start_demo(host=HOST)\nprint(live)',metadata={'tags':['hardware','live']}),
 nb.v4.new_markdown_cell('Leave the page running while presenting. The next notebook stops it before programming. To stop it manually, run `stop_demo()` in the cell below. Live invites and captures stay in ignored runtime folders; do not publish their tokens.'),
 nb.v4.new_code_cell('# stop_demo()',metadata={'tags':['cleanup']})]
 if i>=2:
  at=next(j for j,c in enumerate(cells)if c.cell_type=='markdown'and c.source.startswith('## 3 ·'))
  cells[at:at]=[
   nb.v4.new_markdown_cell('### Official Nios V BSP and applications\n\nGenerate a HAL BSP from this actual VDS system, plus editable **Hello World** and **IQ monitor** CMake applications. This builds software only; it does not download or replace the running firmware. Open both BSP and app with **RiscFree → File → Import Nios V CMake Project**, then build with Ctrl+B. See [Nios V IDE guide](../software/README.md) for BSP Editor, JTAG download and restore steps.'),
   nb.v4.new_code_cell('software_dir = lesson.software()\nprint("BSP:", software_dir / "bsp")\nprint("Hello World:", software_dir / "hello_world")\nprint("IQ monitor:", software_dir / "iq_monitor")',metadata={'tags':['software']}),
  ]
 for cell in cells:
  if cell.cell_type=='markdown'and cell.source.startswith('## 2 ·'):
   sdc=stages()[i-1].relative_to(ROOT)/'iq_bridge_vds.sdc'
   cell.source+=f'\n\nTiming constraints: [iq_bridge_vds.sdc](../{sdc.as_posix()}).'
 notebook=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'atum-a3-iq','display_name':'Atum A3 IQ Demos','language':'python'},'language_info':{'name':'python','version':'3.12'}})
 name=f'{i:02d}_'+['raw_iq_bridge','nios_transfer_monitor','fir_filter','ddc_frequency_translation','gain_power_meters'][i-1]+'.ipynb';write_notebook(notebook,ROOT/'notebooks'/name)

# Presentation notebook: uses checkpoint 5; it is not a sixth FPGA checkpoint.
arcade_setup = cells[2].source  # Reuse the final lesson's checkpoint-5 configuration.
arcade_setup += '\n# Override HOST with the address reachable from your browser when necessary.\n# HOST = "192.168.x.x"\nfrom check_tools import check\nchecks = check()\n'
arcade_cells = [
 nb.v4.new_markdown_cell("""# RF Arcade · demo-night setup

**ESP32 SDR → Agilex 3 FPGA → CyberEther**

**What is added:** a fullscreen presentation and automatic seven-scene showreel using checkpoint 5.

**Why it is useful:** move from real airwaves to clean tone rescue and visible clipping with a few buttons.

**How it works:** ESP32 bursts or an FPGA test generator feed capture RAM, frequency translation, FIR II, decimation and gain/meters. Nios V applies settings; the host verifies results and renders the display FFT and CyberEther graphics.

```text
ESP32 RF ───────┐
               ├→ FPGA RAM → NCO → FIR II → decimate → gain / meters → CyberEther
FPGA test IQ ──┘                       ↑ Nios V / JTAG control
```

This is a presentation of **checkpoint 5**, not another FPGA design. No ESP32 reflashing is needed with the compatible firmware already installed. Run cells in order through **Launch**, then stop there while presenting. Run the final **Stop** cell when finished; do not use Run All for a live presentation."""),
 nb.v4.new_markdown_cell("""## 1 · Install once and select the kernel

In a terminal, from `esp32_agilex3_iq`, on the Linux host or container desktop **where Quartus is installed**:

```bash
# Optional: set QUARTUS_ROOTDIR, QUESTA_ROOT and ATUM_ALTERA_ROOT for your installation.
bash scripts/install_local.sh --system
.venv-notebooks/bin/jupyter lab notebooks --no-browser
```

Omit `--system` if system prerequisites are already installed. That option needs sudo. The installer creates the venv/kernel and downloads the pinned CyberEther runtime; install/license Quartus, device support, Questa and Nios separately. See [installation details](README.md#install-once).

Select **Atum A3 IQ Demos**, or `.venv-notebooks/bin/python` in VS Code. Keep the desktop's `DISPLAY`. Set UART and JTAG overrides below for your board; the current container uses `/dev/ttyUSB0`. No Docker-specific commands are required. These configuration checks do not open the serial device."""),
 nb.v4.new_code_cell(arcade_setup, metadata={'tags':['setup']}),
 nb.v4.new_markdown_cell("""## 2 · See the FPGA design

![Checkpoint 5 · native Quartus VDS diagram](diagrams/05_vds_gui.png)

The saved PNG above comes from the actual VDS GUI. Optionally run the next cell to regenerate the IP/design and export a fresh native diagram locally. It also prints complete Quartus project and ZIP links, including SDC and generated sources. This step needs the GUI prerequisites and can take a few minutes; skip it for a quick launch from an existing build.

Timing constraints: [checkpoint-5 SDC](../fpga_hub/iq_bridge/vds_demo_05_gain/iq_bridge_vds.sdc)."""),
 nb.v4.new_code_cell('from IPython.display import Image, display\ndiagram_png = lesson.generate()\ndisplay(Image(filename=str(diagram_png)))\nprint("Exported:", diagram_png)',metadata={'tags':['generate','optional']}),
 nb.v4.new_markdown_cell("""## 3 · Build or verify the checkpoint-5 SOF

A fresh checkout compiles the design. Later runs reuse only a source-matched, hash-verified SOF; set `FORCE_REBUILD=True` above for a full compile. This does not program the board. Use the printed QPF/project ZIP links to inspect or compile in Quartus; extract ZIPs first. The checkpoint includes the Nios boot monitor already. Generating a separate Hello World project is optional: [Nios IDE guide](../software/README.md).

For the Python model, module simulation and Questa GUI walkthrough, use [lesson 05](05_gain_power_meters.ipynb)."""),
 nb.v4.new_code_cell('build = lesson.build(force=FORCE_REBUILD)\nprint("SOF:", lesson.stage / "iq_bridge_vds.sof")\nprint("SHA256:", build["sha256"])\nprint("Compiled resources:", build["resources"])',metadata={'tags':['build']}),
 nb.v4.new_markdown_cell("""## 4 · Program the physical Atum A3 Nano

Connect board power, JTAG and UART; keep the three compatible ESP32 modules connected. Stop unrelated acquisition owners first. This cell stops the previous notebook-owned demo and **programs checkpoint 5**, replacing the current FPGA image. No ESP32 reset-button presses are required with installed compatible firmware."""),
 nb.v4.new_code_cell('lesson.program()',metadata={'tags':['hardware','program']}),
 nb.v4.new_markdown_cell("""## 5 · Launch RF Arcade

The next cell starts actual acquisition and waits for a verified live result. Open its **private control-invite link**, then choose fullscreen. Use that link rather than opening port 8687 directly: it includes the controls and access token. Keep tokens private.

`HOST` must be reachable from the viewing browser. Default ports are **8768** (controls), **8687** (native viewer), and **TCP 40100–40103** (media). If using a container or firewall, expose those ports and set `HOST` to a reachable address. A launch failure is an error to investigate, not evidence of live samples.

**Stop executing cells here once the link opens.** Leave the notebook kernel running while presenting."""),
 nb.v4.new_code_cell('live = lesson.start_demo(host=HOST, demo_night=True)\nprint(live)',metadata={'tags':['hardware','live']}),
 nb.v4.new_markdown_cell("""## Try this two-minute demo

| Scene | Try | Point out |
|---|---|---|
| **Airwaves** | Select radio and Wi-Fi channel | Real received 2.4 GHz bursts, waterfall and IQ samples |
| **Rescue the tone** | Fold → Shift to DC → Reject interferer | FPGA mixing, anti-alias filtering and decimation |
| **Power rush** | 1× → 2× → 16× | Amplitude growth, clipping, harmonics and FPGA meters |
| **Showreel** | Start, then fullscreen | Seven scenes, each waiting for verified hardware settings |

**Freeze / Resume** pauses/restarts acquisition. Manual scene, radio or channel changes stop the showreel. Stop showreel leaves the selected scene active.

Live Airwaves uses RF; tone rescue and power rush use clean **FPGA-generated test signals**, with no RF transmission. The IQ orbit shows sample scatter, not recovered Wi-Fi/QPSK symbols. Power is relative, not calibrated dBm. Each waterfall row is a distinct sparse capture, not a gap-free recording. Radio selection uses one ESP32 at a time, without phase coherence. Host transport, integer reference checks and display FFT remain host computations.

More detail: [RF Arcade guide](../docs/RF_ARCADE.md)."""),
 nb.v4.new_markdown_cell("""## 6 · Stop and release the hardware

Run this cell **when finished presenting**. It stops this checkout's notebook-owned demo and its acquisition/JTAG children, releasing their device handles. It does not stop unrelated user processes or erase the FPGA image. To present again, rerun Launch; to switch designs, open another lesson and run its programming cell."""),
 nb.v4.new_code_cell('stop_demo()\nprint("Notebook-owned RF Arcade stopped; its UART/JTAG handles are released.")',metadata={'tags':['hardware','cleanup']}),
]
arcade = nb.v4.new_notebook(cells=arcade_cells, metadata=notebook.metadata)
write_notebook(arcade, ROOT/'notebooks/06_rf_arcade.ipynb')
