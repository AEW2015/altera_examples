#!/usr/bin/env python3
"""Generate the five authored notebooks; outputs are produced by local execution."""
import ast
from pathlib import Path
import nbformat as nb
from common import ROOT
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
levels=['Real UART TX/RX module loopback, binary bytes and 8N1 framing.','Real counter RTL with scaled 10-cycle windows, snapshot and reset checks.','Actual generated FIR II VHDL plus capture controller; impulse, custom coefficients, rounding and saturation.','Actual generated I/Q FIR II plus DDC/snapshot RTL, four mixer/filter/decimation cases.','Real gain/meter RTL: bypass, half, double, saturation and zero; all integer outputs and meters checked.']
tries=['Compare I/Q waveform, scatter and display spectrum. The points are raw IQ, not decoded modulation symbols.','Watch actual one-second radio/host byte counts. Pause acquisition and observe the counter age; these are rates, not calibrated RF bandwidth.','Toggle Hamming and Boxcar. Each displayed filtered result is independently checked against the configured integer coefficients.','Select Shift + filter + decimate, then no filter. The interferer folds into the output band when anti-alias filtering is bypassed.','Try 0.5×, 1×, 2×, then 4× or 16×. Watch actual power meters and clipping.']
for i,name in enumerate(NAMES,1):
 cells=[nb.v4.new_markdown_cell(f'# {i} · {name}\n\n**Local Quartus workflow · host or container · one active FPGA design at a time**\n\n`{introductions[i-1][0]}`\n\n{introductions[i-1][1]}\n\nPython model → native VDS diagram → real RTL/IP simulation → SOF → board → focused CyberEther page.'),
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
 nb.v4.new_markdown_cell('## 2 · Generate the actual FPGA block design\n\nRebuild the Nios initialization memory where present, recreate the native VDS system, validate and generate vendor IP. The cell opens **Quartus Visual Designer Studio itself**, fits the diagram and uses **File → Export**. Its native PDF is rendered to a high-resolution PNG and displayed inline. The original PDF and a full GUI screenshot are saved beside it. A private X display keeps capture separate from your desktop.'),
 nb.v4.new_code_cell('from IPython.display import Image, display\ndiagram_png = lesson.generate()\ndisplay(Image(filename=str(diagram_png)))\nprint("Exported:", diagram_png)',metadata={'tags':['generate']}),
 nb.v4.new_markdown_cell(f'### Saved native VDS GUI diagram\n\n![Checkpoint {i} — actual VDS GUI export](diagrams/{i:02d}_vds_gui.png)\n\nThe cell above refreshes this diagram from your local design.'),
 nb.v4.new_markdown_cell(f'## 3 · RTL/IP simulation\n\n{levels[i-1]}\n\nThe plots below read the actual simulator output files. Assertions must pass before the result is plotted.'),
 nb.v4.new_code_cell('simulation_result = lesson.simulate()\nprint("Simulation:", simulation_result["status"])\nlesson.simulation_plot()',metadata={'tags':['rtl']}),
 nb.v4.new_markdown_cell('### Open the Questa GUI\n\nUse a desktop terminal **on the machine running Quartus** (or its container desktop). Execute the printed commands. `wave.wlf` opens the saved real simulation; `view.do` adds its signals. To rerun interactively, start `vsim -gui` in the same directory and type `do gui.do` in the Transcript. This reruns the same assertions and leaves the waveform window open.'),
 nb.v4.new_code_cell('lesson.questa_gui()',metadata={'tags':['instructions']}),
 nb.v4.new_markdown_cell('## 4 · Build the SOF\n\nA source-matched, hash-verified cached bitfile can be reused for a quick presentation. Set `FORCE_REBUILD=True` to demonstrate a full Quartus compilation. A fresh checkout always requires a build.'),
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
 notebook=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'atum-a3-iq','display_name':'Atum A3 IQ Demos','language':'python'},'language_info':{'name':'python','version':'3.12'}})
 name=f'{i:02d}_'+['raw_iq_bridge','nios_transfer_monitor','fir_filter','ddc_frequency_translation','gain_power_meters'][i-1]+'.ipynb';nb.write(notebook,ROOT/'notebooks'/name)
