#!/usr/bin/env python3
"""Generate the authored lessons and RF Arcade setup notebook; outputs are produced by local execution."""
import ast
import textwrap
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
tries=[
 'Start with **Software preview** to see a known two-tone input without hardware. Return to hardware and look for **VERIFIED**, fresh CRC/metadata, and advancing capture counts. This raw bridge has no internal test generator; the preview does not verify the FPGA.',
 'Use **Software preview** for a known IQ input, then return to hardware and watch distinct Nios counter windows, UART/payload rates and error counts. A new counter sequence and fresh counter age provide evidence independently of the IQ graph. This bitfile has no internal test generator.',
 'Press **FPGA impulse check**: the first sample should spread into the filter impulse response. Then try **FPGA two-tone check**, toggle Hamming/Boxcar, and compare the common-axis input/output spectrum. The page checks the actual pattern, coefficients, rounding, payload CRC and integer error. **Live RF** returns to the radio.',
 'Press **Verify tone rejection** for a known FPGA two-tone input. Compare with **Show alias**, then **Impulse response**. The requested/applied ledger checks phase, bypass flags, decimation, sample counts, CRC and zero integer-reference error. Input and output FFTs share the same physical frequency axis.',
 'Try **Clean 1× → Boost 2× → Clip 16×**. Check amplitude, harmonics, measured FPGA power change and clipped samples. Gain readback and zero integer-reference error must match the current request before the badge says VERIFIED.',
]
def cyberether_examples(number):
 captions = {
  1: 'Live RFS2 ESP32 RF capture through the raw bridge: spectrum, IQ samples, payload rate and CRC/metadata evidence.',
  2: 'Live RFS2 ESP32 RF capture with Nios V transfer counters, counter freshness and error checks.',
  3: 'FPGA-generated two-tone input with the 4 MHz notch applied. Compare the cyan input with the gold filtered output and inspect the coefficient readback evidence.',
  4: 'FPGA-generated two-tone input: the mixer shifts the wanted tone to DC, FIR II rejects the interferer, and decimation reduces the output sample rate.',
  5: 'FPGA-generated single-tone input at 16× gain. Saturation creates harmonics; the FPGA reports 4096 clipped samples and the output matches the integer reference.',
  6: 'RF Arcade’s Power rush scene at 16× gain, using an FPGA-generated test signal. The display shows saturation, harmonics, clipping and zero integer-reference error.',
 }
 cells = [nb.v4.new_markdown_cell(
  '### CyberEther · example screenshot\n\n'
  'Saved browser screenshot from a physical Atum A3 Nano / Agilex 3 hardware test. '
  'This is a static example; run the launch cell above for current data.\n\n'
  + captions[number] + f'\n\n![CyberEther example — lesson {number:02d}](screenshots/{number:02d}_cyberether.png)\n\n'
  f'[Open full-resolution screenshot](screenshots/{number:02d}_cyberether.png).',
  metadata={'tags':['cyberether-example']})]
 if number == 3:
  cells.append(nb.v4.new_markdown_cell(
   '#### Custom FIR editor example\n\n'
   'Eight-tap averaging coefficients loaded through the browser editor. The candidate response, '
   'actual before/after samples and VERIFIED coefficient readback are shown together. '
   'The input is an FPGA-generated test signal.\n\n'
   '![CyberEther custom FIR coefficient editor](screenshots/03_fir_custom_editor.png)\n\n'
   '[Open full-resolution editor screenshot](screenshots/03_fir_custom_editor.png).',
   metadata={'tags':['cyberether-example']}))
 return cells

def write_notebook(notebook, path):
 for cell in notebook.cells:
  if cell.cell_type=='code' and 'theory' in cell.metadata.get('tags',[]) and not cell.source.startswith('from notebook_progress import progress'):
   last_summary=cell.source.rstrip().endswith('\nsummary')
   cell.source='from notebook_progress import progress\nwith progress("Run Python example / render graphs"):\n'+textwrap.indent(cell.source,'    ')+('\nsummary'if last_summary else '')
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
 nb.v4.new_markdown_cell('## Setup\n\nOnce, from this example folder: `bash scripts/install_local.sh --system` (Linux system packages need sudo), then select **Atum A3 IQ Demos** as the notebook kernel. Quartus/Questa/Nios tools must already be installed. Set the optional paths below if they are not on PATH. No Docker commands are needed. Long-running cells show an animated activity bar, elapsed time and the active step/log; a full bar means successful completion, not an estimated compile percentage.'),
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
 nb.v4.new_markdown_cell('## 6 · Focused CyberEther demo\n\n'+tries[i-1]+'\n\nThe page uses the bitfile just programmed. Diagnostic plots work without WebRTC; the native CyberEther canvas is expandable below them. **VERIFIED** requires a fresh matching result; **APPLYING**, **HELD**, **STALE** or **ERROR** keeps old data visibly separate from successful application. **Software preview** is host-only and never counts as a hardware pass. See [demo guide](../docs/NOTEBOOK_DEMOS.md). One board and one acquisition owner are shared across all notebooks.'),
 nb.v4.new_code_cell('live = lesson.start_demo(host=HOST)\nprint(live)',metadata={'tags':['hardware','live']}),
 nb.v4.new_markdown_cell('Leave the page running while presenting. The next notebook stops it before programming. To stop it manually, run `stop_demo()` in the cell below. Live invites and captures stay in ignored runtime folders; do not publish their tokens.'),
 nb.v4.new_code_cell('# stop_demo()',metadata={'tags':['cleanup']})]
 if i>=2:
  at=next(j for j,c in enumerate(cells)if c.cell_type=='markdown'and c.source.startswith('## 3 ·'))
  cells[at:at]=[
   nb.v4.new_markdown_cell('### Official Nios V BSP and applications\n\nGenerate a HAL BSP from this actual VDS system, plus editable **Hello World** and **IQ monitor** CMake applications. This builds software only; it does not download or replace the running firmware. Open both BSP and app with **RiscFree → File → Import Nios V CMake Project**, then build with Ctrl+B. See [Nios V IDE guide](../software/README.md) for BSP Editor, JTAG download and restore steps.'),
   nb.v4.new_code_cell('software_dir = lesson.software()\nprint("BSP:", software_dir / "bsp")\nprint("Hello World:", software_dir / "hello_world")\nprint("IQ monitor:", software_dir / "iq_monitor")',metadata={'tags':['software']}),
  ]
 if i==3:
  at=next(j for j,c in enumerate(cells)if c.cell_type=='markdown'and c.source.startswith('## 2 ·'))
  cells[at:at]=[
   nb.v4.new_markdown_cell("""### Filter library · preview without hardware

There are **15 examples** stored in Python and one active 16-tap coefficient set in the FPGA. The same real coefficients filter I and Q. Selecting another example reloads the coefficients through Nios V; it does not rebuild the bitfile.

Try **narrow low-pass**, **high-pass**, **band-pass**, or the **4 MHz notch** with the FPGA two-tone input. The short filters have broad transition regions. Frequencies scale with sample rate: the matching FIR test notch is at 0.25 Fs, so it is 4 MHz only at 16 MS/s.

Q15 represents each coefficient divided by 32768. All examples contain exactly 16 integers; shorter designs have trailing zeros. The example's L1 gain bounds worst-case amplification, so some arbitrary inputs can clip even when a sinusoidal passband is near unity. [Filter guide](../docs/FIR_FILTER_LIBRARY.md)."""),
   nb.v4.new_code_cell('from IPython.display import Markdown, display\nfrom fir_filters import catalog, plot_filter, q15\nrows = ["| Python name | Example | What to observe |", "|---|---|---|"]\nrows += [f"| `{f[\'id\']}` | {f[\'title\']} | {f[\'description\']} |" for f in catalog()]\ndisplay(Markdown("\\n".join(rows)))',metadata={'tags':['theory','filter-library']}),
   nb.v4.new_code_cell('from fir_filters import plot_catalog\nplot_catalog(rate=16_000_000)',metadata={'tags':['theory','filter-gallery']}),
   nb.v4.new_code_cell('FILTER = "notch-4mhz"  # Change to any Python name in the table.\npreview = plot_filter(FILTER, rate=16_000_000)\nprint(preview)',metadata={'tags':['theory','filter-preview']}),
  ]
  at=next(j for j,c in enumerate(cells)if c.cell_type=='markdown'and c.source.startswith('Leave the page running'))
  cells[at:at]=[
   nb.v4.new_markdown_cell("""### Load a filter through Python · keep CyberEther running

Run this after the launch cell. Python sends a request to the **existing acquisition owner**; it does not open a second UART/JTAG client. The call waits for a fresh FPGA result, verifies all coefficients, CRC/readback and zero integer-reference error, and reports clipping. The selected filter remains active across captures until you choose another filter or restart the demo. The shared progress row shows application/verification feedback.

In the browser choose an example, then **Apply selected example**. Open **Filter design** to preview the candidate or edit all 16 Q15 integers. Previewing or editing alone never changes the FPGA. Optional: embed the same page below; its output contains a private invite, just like the launch cell."""),
   nb.v4.new_code_cell('from fir_controls import FIRControls\nfir = FIRControls()\nresult = fir.apply(FILTER, input_kind="fpga-tones")\nprint(result)',metadata={'tags':['hardware','filter-apply']}),
   nb.v4.new_markdown_cell("""#### Your own coefficients

Edit the 16 integers below, then run the cell. This eight-sample average uses eight Q15 taps of 4096 and eight zeros. To design using real-valued taps, call `q15([0.25] * 4)`; the helper pads shorter filters and rejects overflow. Positive 1.0 is not representable in signed Q15; use 32767/32768 for a near-unity tap. `plot_filter(coefficients=CUSTOM_Q15)` previews your actual quantized design without changing hardware.

Change `input_kind` to `fpga-impulse` to inspect its impulse response, or `live` for real RF. Real RF uses the notebook's current radio/channel/rate. These reloads affect the 16-tap FIR, not the separate fixed 127-tap DDC filters."""),
   nb.v4.new_code_cell('CUSTOM_Q15 = [4096] * 8 + [0] * 8\nprint(fir.apply(coefficients=CUSTOM_Q15, input_kind="fpga-impulse"))',metadata={'tags':['hardware','filter-custom']}),
   nb.v4.new_code_cell('# Interactive GUI: the same acquisition owner and filter settings as the browser.\nfir.show_gui(height=1050)',metadata={'tags':['hardware','filter-gui']}),
  ]
 for cell in cells:
  if cell.cell_type=='markdown'and cell.source.startswith('## 2 ·'):
   sdc=stages()[i-1].relative_to(ROOT)/'iq_bridge_vds.sdc'
   cell.source+=f'\n\nTiming constraints: [iq_bridge_vds.sdc](../{sdc.as_posix()}).'
 cells.extend(cyberether_examples(i))
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

Select **Atum A3 IQ Demos**, or `.venv-notebooks/bin/python` in VS Code. Keep the desktop's `DISPLAY`. Set UART and JTAG overrides below for your board; the current container uses `/dev/ttyUSB0`. No Docker-specific commands are required. Long-running cells show an activity bar, elapsed time and the current step/log. The bar fills on successful completion; it does not guess a tool percentage. These configuration checks do not open the serial device."""),
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
arcade_cells.extend(cyberether_examples(6))
arcade = nb.v4.new_notebook(cells=arcade_cells, metadata=notebook.metadata)
write_notebook(arcade, ROOT/'notebooks/06_rf_arcade.ipynb')

# Offline firmware lesson: intentionally no serial, FPGA programming or GUI launch.
firmware_cells = [
 nb.v4.new_markdown_cell("""# ESP32 SDR firmware · from airwaves to bytes

**What is added:** an explanation of the original ESP32 receiver firmware, plus an editable Python model of its controls and binary samples.

**Why it is useful:** understand what reaches the FPGA, what each radio setting changes, and why fast sampling still produces sparse captures over UART.

**How it works:** the ESP32 RF/PHY capture hardware fills reserved SRAM; firmware checks the capture, packs I/Q, computes a CRC and sends bytes. Agilex 3 receives those bytes before applying the lesson's DSP.

**Everything in this notebook is offline.** Run All is safe: no serial access, firmware build/flash, FPGA programming or live viewer. Simulated tones are not RF transmissions. The model follows selected command/packing rules, but its RF filter, gain curve and AGC are teaching approximations, not an ESP32 hardware emulator."""),
 nb.v4.new_markdown_cell("""## 1 · Setup

Use **Atum A3 IQ Demos** or `.venv-notebooks/bin/python`. If needed, run `bash scripts/install_local.sh` from the example root first; see [installation](README.md#install-once). This notebook needs NumPy/Matplotlib, not Quartus or connected hardware. Python examples show an activity bar and elapsed time while computing and rendering plots.

Source of truth: [mode dispatch](../unified/main/rf_mode.c), [ESP32 receiver](../unified/main/targets/esp32/receiver.c), [capture packing](../unified/main/common/burst_capture.h), [shared commands](../unified/main/common/burst_commands.h), [UART transport](../unified/main/common/burst_serial.c). Python model: [esp32_sdr_model.py](../scripts/esp32_sdr_model.py)."""),
 nb.v4.new_code_cell('''from pathlib import Path
import sys
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "scripts/esp32_sdr_model.py").exists())
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
import matplotlib.pyplot as plt
from esp32_sdr_model import ReceiverModel, Capture, RATES, bandwidth_code, pack_samples
print("Python:", sys.executable)
print("OFFLINE — no hardware connection")
''',metadata={'tags':['setup']}),
 nb.v4.new_markdown_cell("""## 2 · One firmware, three different measurements

```text
Boot → read mode from NVS
           ├─ MONITOR → Wi-Fi packet metadata / SSID inventory       · 115200 baud
           ├─ CSI     → associated AP → channel-state measurements  · 115200 baud
           └─ SDR     → RF capture SRAM → raw I/Q bursts             · 2000000 baud
```

`MODE?` reports the current mode. `MODE SDR` saves the selection in NVS, replies `RF_MODE_ACK,SDR,rebooting` and restarts the ESP32. It is not an instantaneous concurrent mode switch. A fresh NVS defaults to MONITOR. SDR baud changes are session-only; the next SDR boot returns to the configured 2 Mbaud default.

SSID/decoded header information comes from the built-in Wi-Fi receiver in monitoring mode. SDR gives samples, not SSIDs; these notebooks' FPGA DSP does not decode Wi-Fi packets. CSI is channel-state information, not the same data as an IQ recording.

### SDR capture lifecycle

The receiver reserves a 64 KiB SRAM aperture (16,384 32-bit words), permitting **256–16,380 samples** per burst. The extra four words remain outside the requested capture. Before capture it fills the whole aperture with sentinel `0xa55aa55a`; after capture it verifies the written region and untouched tail. A hardware completion/status check has a 20 ms timeout. It restores the memory ownership and filter state before transferring bytes.

The next diagram is a schematic of the source sequence, not a Quartus VDS export."""),
 nb.v4.new_code_cell('''fig, ax = plt.subplots(figsize=(12, 3))
labels = ["Tune / calibrate\\napply gain", "Fill SRAM sentinel\\ntrigger RF dump", "Check done / count\\ncheck SRAM bounds", "Pack I/Q\\nCRC + DATA header", "UART → FPGA\\nCRC / RAM / DSP"]
for j, label in enumerate(labels):
    ax.text(j*2.5, 0.5, label, ha="center", va="center", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#dff3ff", edgecolor="#13799a"))
    if j < len(labels)-1:
        ax.annotate("", xy=(j*2.5+1.5,0.5), xytext=(j*2.5+1,0.5), arrowprops=dict(arrowstyle="->", lw=2))
ax.set(xlim=(-1.4,11.5), ylim=(0,1)); ax.axis("off")
fig.tight_layout(); plt.show()
''',metadata={'tags':['theory','diagram']}),
 nb.v4.new_markdown_cell("""## 3 · Controls and their meaning

| Firmware command | Effect | Important distinction |
|---|---|---|
| `INFO`, `CAPS`, `LIMITS?` | Discover identity, features and bounds | Read the actual device; gain maximum is read from a register at boot |
| `FREQ 2417` | Retune LO to channel-2 center | MHz, not channel number; retuning can require calibration |
| `RANGE?` | Reports accepted software range 100–6000 MHz | Acceptance is not proof of PLL lock, useful sensitivity or 5 GHz reception on these original ESP32 boards; use the demonstrated 2.4 GHz region |
| `GAIN HARDWARE` | Let RF hardware AGC control gain | Default; relative amplitude can change across bursts |
| `GAIN MANUAL 40` | Force a gain code | Code is not calibrated dB; different from downstream FPGA digital gain |
| `BANDWIDTH 20` | Approximate analog full-width selection | Original ESP32 accepts 0 or 12–67 MHz; 0 selects code 0; actual response is approximate |
| `LPF AUTO`, `LPF 64`, `LPF?` | Restore calibrated filter / select raw capacitor code / query | `AUTO` is distinct from `BANDWIDTH 0`; the model only simulates BANDWIDTH |
| `CAP16 8192 6` | One burst, signed CI8 output | 8-bit I + 8-bit Q, 16 bits per complex sample |
| `CAP20 8192 6` | One burst, packed IQ10 | 10-bit I + 10-bit Q, not 20 bits per component |
| `CAP 8192 6` | One burst, raw 32-bit words | Includes bits outside the low-20-bit IQ fields |
| `RXRUN 8192 6 10 16` | Ten independent CI8 captures, then `END` | RF gaps during transfers; not continuous streaming |
| `BAUD?`, `BAUD 1000000` | Query/change UART baud | ACK at old baud; host and FPGA receiver must then agree on new baud |
| `SYNC 123`, `RELEASE` | Echo marker / release transport ownership | SYNC does not synchronize RF sample phase between radios |

**Valid capture rate codes for this target:** 0 → 80 MS/s, 1 → 40 MS/s, 6 → 16 MS/s. Codes 2–5 are rejected by the original ESP32 capture backend even though the shared parser allows codes up to 6. These are hardware sampling clocks, inferred in the firmware from capture-duration slopes, not a software decimation setting.

The shared transport parser bounds command lines to 127 characters and holds a five-second ownership lease after a transaction. The original ESP32 modules here use UART; native USB handling in shared source serves other chips. Additional on-device spectrum commands exist, but the current FPGA IQ bridge requests **CAP16**; it does not use compressed spectrum output.

The model below implements only the listed examples for tuning, gain, bandwidth, baud, queries and single captures. It deliberately omits mode restarts, LPF, RXRUN, leases and calibration."""),
 nb.v4.new_code_cell('''radio = ReceiverModel(gain_max=72)  # Example limit, not a device measurement.
for command in ["MODE?", "INFO", "RANGE?", "FREQ 2417", "GAIN MANUAL 40", "BANDWIDTH 20", "BAUD?", "CAP16 8192 2"]:
    print(f"> {command}\\n{radio.command(command)}")
print("BANDWIDTH 20 maps to capacitor code:", bandwidth_code(20))
''',metadata={'tags':['theory','controls']}),
 nb.v4.new_markdown_cell("""## 4 · Try the controls: tune, narrow, amplify, sample

Edit the parameters, then rerun this cell. Synthetic fixed RF tones sit at **2416 and 2426 MHz**. Changing center frequency changes their baseband offsets. At 16 MS/s the displayed complex band is −8 to +8 MHz: out-of-band content can alias if analog rejection is insufficient.

Try `(center, bandwidth, gain, rate)` values `(2417, 0, 40, 6)`, `(2417, 12, 40, 6)`, `(2422, 20, 40, 1)`, and `(2417, 20, 72, 6)`. Compare movement, interferer attenuation and clipping. Set hardware AGC to see a simplified RMS-level controller.

**Model assumptions:** smooth illustrative analog low-pass response before sampling; gain doubles every 16 codes solely for this illustration; AGC targets a fixed RMS; additive noise is synthetic. These are not measured ESP32 transfer curves. The firmware's numeric bandwidth-to-capacitor interpolation and IQ packing are reproduced separately."""),
 nb.v4.new_code_cell('''CENTER_MHZ = 2417
BANDWIDTH_MHZ = 20       # 0 or 12..67
GAIN_CODE = 40          # 0..72 in this illustrative instance
HARDWARE_AGC = False
RATE_CODE = 6           # 0=80, 1=40, 6=16 MS/s
SAMPLES = 8192           # 256..16380
FORMAT = 16             # 0=raw32, 16=CI8, 20=IQ10
radio = ReceiverModel(gain_max=72)
for command in [f"FREQ {CENTER_MHZ}", f"BANDWIDTH {BANDWIDTH_MHZ}",
                "GAIN HARDWARE" if HARDWARE_AGC else f"GAIN MANUAL {GAIN_CODE}"]:
    answer=radio.command(command)
    if answer != "OK": raise ValueError(f"{command}: {answer}")
cap = radio.capture(SAMPLES, RATE_CODE, FORMAT)
if FORMAT == 16:
    pair = np.frombuffer(cap.payload, dtype=np.int8).reshape(-1,2).astype(float)/128
else:
    pair = cap.iq10.astype(float)/512
x = pair[:,0] + 1j*pair[:,1]
f = np.fft.fftshift(np.fft.fftfreq(len(x),1/cap.fs))/1e6
power = 20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(x*np.hanning(len(x)))))/len(x),1e-9))
fig, axes = plt.subplots(1,3,figsize=(14,3.8))
axes[0].plot(np.arange(160)/cap.fs*1e6,pair[:160,0],label="I")
axes[0].plot(np.arange(160)/cap.fs*1e6,pair[:160,1],label="Q",alpha=.7)
axes[0].set(xlabel="Time (µs)",ylabel="Normalized amplitude",ylim=(-1.1,1.1)); axes[0].legend()
axes[1].plot(f,power,color="#168eab"); axes[1].set(xlabel="Offset from LO (MHz)",ylabel="Relative FFT magnitude (dB)",ylim=(-100,0))
axes[2].scatter(pair[:2000,0],pair[:2000,1],s=2,alpha=.3)
axes[2].set(xlabel="I",ylabel="Q",xlim=(-1.1,1.1),ylim=(-1.1,1.1)); axes[2].set_aspect("equal")
fig.suptitle("SIMULATED receiver output — sample scatter, not decoded symbols")
fig.tight_layout(); plt.show()
print(cap.header.strip(), "← simulated elapsed time excludes firmware overhead")
print("Payload bytes:",len(cap.payload),"Clipped I/Q components:",cap.clipped_components)
''',metadata={'tags':['theory','controls']}),
 nb.v4.new_markdown_cell("""## 5 · The byte contract: ESP32 → FPGA → Python

```text
ESP32 radio UART:
  ASCII DATA <sample_count> <payload_crc_hex> <capture_us> + newline
  followed immediately by binary payload (no newline terminator)
                         ↓
Agilex 3: parse / length / CRC → capture RAM → optional DSP
                         ↓
Host UART: IQB1 binary envelope + payload + envelope CRC
```

These are **two different protocols**. The host also sends binary `IQBC` commands to the FPGA; firmware commands are ASCII forwarded to a selected radio. See [host bridge implementation](../cyberether/iq_bridge.py). FPGA host UART supports qualified 2/4 Mbaud profiles; ESP32 SDR UART supports 1/2 Mbaud. A host UART speed change does not automatically change the ESP32 link.

The FPGA bridge currently uses **CAP16**: signed I then Q, keeping the upper eight bits of each signed ten-bit field (discard two low bits). IQ10 packs two complex samples into five bytes; an odd tail uses three. CAP uses four bytes per word. The model's raw32 format sets unused upper bits to zero; actual raw register words need not.

The firmware CRC covers the packed payload, not the ASCII header. Capture microseconds measure the firmware trigger-to-completion interval, not UART transfer time or a shared multi-radio RF timestamp."""),
 nb.v4.new_code_cell('''import zlib
example = np.array([[-512,511],[-1,0],[4,-4]],dtype=np.int16)
for fmt in (0,20,16):
    payload=pack_samples(example,fmt)
    print(f"Format {fmt:2}: {len(payload):2} bytes  {payload.hex(' ')}")
print("CAP16 decoded:",np.frombuffer(pack_samples(example,16),np.int8).reshape(-1,2).tolist())
fields=cap.header.split()
assert fields[0]=="DATA" and int(fields[1])==SAMPLES
assert zlib.crc32(cap.payload)==int(fields[2],16)
bad=bytearray(cap.payload); bad[0]^=1
print("Good CRC:",f"{zlib.crc32(cap.payload):08x}")
print("Corrupted payload rejected:",zlib.crc32(bad)!=int(fields[2],16))
''',metadata={'tags':['theory','protocol']}),
 nb.v4.new_markdown_cell("""## 6 · Why the UART limits live acquisition

For 8N1 UART, one byte costs **10 wire bits**. CI8 costs two bytes per sample, so 2 Mbaud carries at most **100,000 complex samples/s**, before headers and overhead. An 8192-sample burst at 16 MS/s spans just **512 µs** of RF; its CI8 payload alone takes **81.92 ms** over 2 Mbaud.

The graph shows ideal capture-plus-transfer timing only. Calibration, sentinel writes/checks, task scheduling, FPGA→host transfer and display work add more gaps. RXRUN repeats this sparse sequence. A faster RF sample clock makes each capture shorter, not the UART faster. Separate FPGA and host links add constraints; do not add the three radios' RF sample clocks and call that host throughput."""),
 nb.v4.new_code_cell('''n=8192
fig, axes=plt.subplots(1,2,figsize=(12,3.5))
for fmt,label in [(16,"CI8"),(20,"IQ10"),(0,"raw32")]:
    byte_count=len(pack_samples(np.zeros((n,2),np.int16),fmt))
    wire_ms=byte_count*10/2_000_000*1000
    axes[0].bar(label,wire_ms)
    axes[0].text(label,wire_ms,f"{wire_ms:.2f} ms",ha="center",va="bottom")
axes[0].set(ylabel="Payload-only UART time (ms)",title="8192 samples at 2 Mbaud",ylim=(0,190))
for j,code in enumerate((6,1,0)):
    sample_ms=n/RATES[code]*1000
    wire_ms=n*2*10/2_000_000*1000
    axes[1].barh(j,sample_ms,color="#24b6a8",label="RF capture" if j==0 else None)
    axes[1].barh(j,wire_ms,left=sample_ms,color="#f5ab49",label="CI8 transfer" if j==0 else None)
    print(f"{RATES[code]/1e6:2.0f} MS/s: RF {sample_ms*1000:.1f} µs, transfer {wire_ms:.2f} ms, ideal RF duty {100*sample_ms/(sample_ms+wire_ms):.3f}%")
axes[1].set(yticks=range(3),yticklabels=["16 MS/s","40 MS/s","80 MS/s"],xlabel="Ideal elapsed time (ms)",title="Capture → transfer → gap before next burst")
axes[1].legend(); fig.tight_layout(); plt.show()
''',metadata={'tags':['theory','bandwidth']}),
 nb.v4.new_markdown_cell("""## 7 · Firmware, FPGA and host responsibilities

| Stage | Runs where | How to test it independently |
|---|---|---|
| LO/PHY setup, calibration, dump clocks, capture completion | ESP32 RF hardware + firmware | Physical known RF source and timed captures; the Python model cannot validate registers or sensitivity |
| SRAM bounds, packing, DATA framing | ESP32 firmware | Known signed sample vectors / byte comparison; timeout/bounds checks in receiver source |
| UART framing, CRC, burst RAM | Agilex 3 FPGA | [Lesson 01](01_raw_iq_bridge.ipynb): UART module simulation, then hardware capture |
| FIR / DDC / gain / meters | Agilex 3 FPGA | [Lessons 03–05](README.md): generated IP/RTL assertions and clean FPGA test patterns |
| Independent reference / display FFT / plots | Host Python + CyberEther | Host unit tests and synthetic references; [RF Arcade](06_rf_arcade.ipynb) for presentation |

To build the **real** firmware later, follow [firmware build/program instructions](../docs/ESP32_FIRMWARE.md). RFS2 application TX/RX uses GPIO1/3; Digilent Pmod application TX/RX uses GPIO17/16. Pmod ROM flashing instead uses J2 GPIO1/3; it is a different route. No build or flash is performed here.

Python examples above model **this checkout's original ESP32 backend**. Other ESP32 families have different rate codes, analog paths and capabilities; shared source listings are not proof that these three modules implement every target's features."""),
]
firmware_notebook=nb.v4.new_notebook(cells=firmware_cells,metadata=notebook.metadata)
write_notebook(firmware_notebook,ROOT/'notebooks/07_esp32_sdr_firmware.ipynb')

# Offline modem education lesson. Keep this separate from FPGA lessons 01–05 and
# RF Arcade: its Python synchronization path is a reference, not FPGA evidence.
modem_cells = [
 nb.v4.new_markdown_cell("""# 08 · Modem Lab · BPSK to 64-QAM

**Local software lesson · no board access or radio capture**

**What is added:** a Python reference chain and interactive browser lab for BPSK, QPSK, 16-QAM and 64-QAM.

**Why it is useful:** adjust noise, carrier offset, timing and multipath, then see what synchronization, hard/soft decisions and FEC do to the same known frame.

**How it works:** the seeded Python model creates a framed waveform, adds channel impairments, acquires the burst and compares decoded bits with the known payload. The local browser page displays raw and recovered samples, EVM, CRC/lock state and error counts.

```text
Python TX reference → seeded software channel → Python RX reference → measured BER / EVM
```

Every result is explicitly **Python simulation**. RF TX qualification is blocked: only original ESP32 modules are installed, and arbitrary-IQ playback is not qualified. The Python carrier/timing recovery and equalizer do not imply that matching FPGA blocks exist. The separate checkpoint 06 currently targets the symbol-level FEC/QAM path; waveform shaping and synchronization remain future RTL work. No hardware is touched by the cells in this notebook."""),
 nb.v4.new_markdown_cell("## 1 · Set up the offline model\n\nRun from the repository's Atum A3 IQ Demos environment. This lesson needs the existing NumPy and Matplotlib packages. It does not need Quartus, Questa, a board, ESP32 firmware or a network connection."),
 nb.v4.new_code_cell('''from pathlib import Path
import sys
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "cyberether/modem_lab.py").exists())
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "cyberether"))
from lessons import lan_ip
from modem_reference import run_experiment
print("Example root:", ROOT)
print("Backend: Python reference simulation; no hardware source")''',metadata={'tags':['setup','offline']}),
 nb.v4.new_markdown_cell("## 2 · Compare the modulation ladder\n\nAll four runs use the same SNR, seed and payload length. Higher-order modes carry more coded bits per symbol, while their ideal points sit closer together at the same average symbol energy. The following plots are synthetic simulation results."),
 nb.v4.new_code_cell('''import matplotlib.pyplot as plt
from notebook_progress import progress
MODES = ("BPSK", "QPSK", "16QAM", "64QAM")
ladder = {}
with progress("Simulate modulation ladder"):
    for mode in MODES:
        ladder[mode] = run_experiment(modulation=mode, snr_db=18, cfo_hz=1500,
            timing_offset=.25, multipath=False, seed=7, payload_bits=2048,
            decode_mode="soft", coded=True, sample_rate=4_000_000, sps=4)
fig, axes = plt.subplots(1, 4, figsize=(13, 3.5))
for ax, mode in zip(axes, MODES):
    plot = ladder[mode]["plots"]
    ideal = plot["ideal_xy"]
    received = plot["recovered_xy"]
    ax.scatter([p[0] for p in ideal], [p[1] for p in ideal], s=9, c="#71869d", marker="s", label="ideal")
    ax.scatter([p[0] for p in received], [p[1] for p in received], s=7, c="#18aeb2", alpha=.45, label="recovered")
    ax.set(title=mode, xlabel="I", ylabel="Q", aspect="equal")
    ax.grid(alpha=.2)
axes[0].legend(loc="lower left", fontsize=8)
fig.suptitle("Python simulation · recovered symbols and ideal reference")
fig.tight_layout()
plt.show()
for mode, result in ladder.items():
    m = result["metrics"]
    print(f"{mode:6} EVM={m['evm_percent']:.2f}%  pre-FEC={m['pre_fec_errors']}/{m['pre_fec_bits']}  soft payload errors={m['soft_fec_errors']}/{m['post_fec_bits']}")''',metadata={'tags':['theory','offline']}),
 nb.v4.new_markdown_cell("## 3 · Change one impairment at a time\n\nThis sweep keeps modulation, seed and payload fixed while changing carrier offset. Each result is a separate seeded simulation. Acquisition failure, a bad header or CRC failure is a real model outcome and stays visible in the metrics."),
 nb.v4.new_code_cell('''carrier_sweep = []
with progress("Measure carrier-offset sweep"):
    for offset in (0, 1500, 5000, 10000):
        result = run_experiment(modulation="64QAM", snr_db=18, cfo_hz=offset,
            timing_offset=.25, multipath=False, seed=21, payload_bits=4096,
            decode_mode="soft", coded=True, sample_rate=4_000_000, sps=4)
        carrier_sweep.append((offset, result["metrics"]))
for offset, m in carrier_sweep:
    print(f"CFO {offset:5} Hz · lock={m['locked']} · EVM={m['evm_percent']:.2f}% · hard errors={m['hard_fec_errors']}/{m['post_fec_bits']} · soft errors={m['soft_fec_errors']}/{m['post_fec_bits']} · CRC={m['crc_ok']}")''',metadata={'tags':['theory','offline']}),
 nb.v4.new_markdown_cell("## 4 · Accumulate a 64-QAM BER curve\n\nThis longer run aggregates 49 independent, seeded 2048-bit payloads at each Es/N0 point. It compares hard and soft Viterbi input over the same software channel and reports actual error counts and tested-bit denominators. The reference BER helper excludes frames that fail acquisition/header decoding and reports those separately. It labels every row as **Python simulation**. This takes longer than the single-frame controls, so the cell shows elapsed progress and the current SNR; reduce `BER_SEEDS` for a quick preview. A zero-error observation is shown as a separate annotated marker and count, not as BER=0 on the logarithmic axis."),
 nb.v4.new_code_cell('''from modem_reference import ber_sweep

BER_SNR_DB = (12, 16, 18, 22)
BER_SEEDS = tuple(range(49))
BER_PAYLOAD_BITS = 2048
ber_rows = []
with progress("Accumulate 64-QAM BER curve") as activity:
    for snr in BER_SNR_DB:
        activity.message(f"{len(BER_SEEDS)} independent frames · {BER_PAYLOAD_BITS} payload bits/frame · Es/N0 {snr} dB")
        result = ber_sweep(modulation="64QAM", snr_values=(snr,), seeds=BER_SEEDS,
            payload_bits=BER_PAYLOAD_BITS, cfo_hz=1500, timing_offset=.25,
            multipath=False, coded=True, decode_mode="soft",
            sample_rate=4_000_000, sps=4)
        ber_rows.extend(result["rows"])

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 4.8))
for key, label, color, marker in (
    ("hard_fec_ber", "Hard-decision Viterbi", "#d38b2c", "o"),
    ("soft_fec_ber", "Soft-decision Viterbi", "#168f9b", "s"),
):
    measured = [row for row in ber_rows if row[key] is not None and row[key] > 0]
    ax.plot([r["snr_db"] for r in measured], [r[key] for r in measured],
            color=color, marker=marker, linewidth=2, label=label)
    zeros = [row for row in ber_rows if row[key] == 0]
    if zeros:
        # The marker lives in the bottom annotation strip, not at an invented BER value.
        ax.scatter([r["snr_db"] for r in zeros], [.055] * len(zeros),
                   transform=ax.get_xaxis_transform(), marker="v", s=50,
                   facecolors="none", edgecolors=color, linewidths=1.5,
                   label=f"{label}: zero observed (annotation only)")
        for row in zeros:
            ax.annotate(f"0/{row['post_fec_bits']}",
                        xy=(row["snr_db"], .055), xycoords=ax.get_xaxis_transform(),
                        xytext=(0, 8), textcoords="offset points", ha="center",
                        color=color, fontsize=8, rotation=90)
ax.set_yscale("log")
ax.set_xlabel("Es/N0 (dB)")
ax.set_ylabel("Observed payload BER (nonzero counts)")
ax.set_title("Python simulation · 64-QAM hard vs soft decoding")
ax.grid(True, which="both", alpha=.25)
ax.legend(fontsize=8)
ax.text(.01, .015, "Hollow triangles and 0/N labels mark zero observed errors; they are not BER coordinates.",
        transform=ax.transAxes, fontsize=8, color="#555")
fig.tight_layout()
plt.show()
print("Source: Python simulation · Es/N0 sweep · same seeded frames for hard/soft decoding")
for row in ber_rows:
    total = row["post_fec_bits"]
    def count(key):
        errors = row[key]
        return f"{errors}/{total} = {errors/total:.6g}" if errors else f"0/{total} observed; BER not plotted"
    print(f"{row['snr_db']:>2.0f} dB · frames {row['frames']} · failures {row['frame_failures']} · hard {count('hard_fec_errors')} · soft {count('soft_fec_errors')}")''',metadata={'tags':['theory','offline','ber-sweep']}),
 nb.v4.new_markdown_cell("## 5 · Open the interactive browser lab\n\nThis starts a Python server bound to `0.0.0.0` so a browser on your LAN can reach the notebook host. The printed URL uses `lan_ip()`; replace `HOST` below with an address reachable from your browser if route discovery chooses the wrong interface. The optional FPGA action remains off unless you explicitly set `ENABLE_FPGA_ACTION=True`; even then its separate button requires a click, a matching checkpoint 06 manifest/image and a free Nios/JTAG owner. Stop the process by interrupting this cell or use the cleanup cell. Python plots remain labeled simulation; FPGA results use a separate badge and evidence."),
 nb.v4.new_code_cell('''import subprocess
LAB_LOG = ROOT / "cyberether/run/modem-lab.log"
LAB_LOG.parent.mkdir(parents=True, exist_ok=True)
LAB_PORT = 8769
HOST = lan_ip()  # Set to a reachable host/container LAN address if needed.
ENABLE_FPGA_ACTION = False  # Opt in explicitly; still requires a manual click and checkpoint guard.
lab_log = LAB_LOG.open("ab")
args = [sys.executable, str(ROOT / "cyberether/modem_lab.py"), "--host", "0.0.0.0", "--port", str(LAB_PORT)]
if ENABLE_FPGA_ACTION:
    args.append("--enable-fpga-action")
lab_process = subprocess.Popen(args, stdout=lab_log, stderr=subprocess.STDOUT, cwd=ROOT)
LAB_URL = f"http://{HOST}:{LAB_PORT}/"
print("Modem Lab:", LAB_URL)
print("Server PID:", lab_process.pid, "· bind: 0.0.0.0 · source: Python simulation")''',metadata={'tags':['offline','browser']}),
 nb.v4.new_markdown_cell("### Saved browser example\n\nThis static screenshot was captured from the working local page. Values are one seeded Python simulation run; the RF TX qualification banner records the current original-ESP32 hardware gate.\n\n![Modem Lab browser example](screenshots/08_modem_lab.png)\n\n[Open the full-resolution screenshot](screenshots/08_modem_lab.png)."),
 nb.v4.new_markdown_cell("## 6 · FPGA path and its current boundary\n\nCheckpoint 06 implements symbol-rate encoding/mapping, max-log soft demapping and Viterbi FEC. Run the actual Questa assertions, then optionally generate the native VDS project and build a SOF using the executable cells below. Each action is controlled by a default-false switch so **Run All** stays offline. Generation/build use the project progress helper and log output. They do not program a board or flash a radio. The saved PNG is an actual Quartus VDS GUI export from checkpoint 06. Python waveform shaping, burst acquisition, carrier/timing recovery and equalization are not implemented in this RTL."),
 nb.v4.new_markdown_cell("### Saved native Quartus VDS GUI export\n\n![Checkpoint 06 modem block design exported from the actual VDS GUI](diagrams/08_vds_gui.png)\n\nThis is the native design GUI export, not a Python topology drawing. The executable generate cell can recreate the project and export a fresh diagram locally."),
 nb.v4.new_code_cell('''from IPython.display import Image, display
from pathlib import Path
from simulate_modem import simulate
from modem_fpga import build as build_modem

# Enable only the action you intend to run. Simulation/build/generation never program hardware.
RUN_QUESTA_SIMULATION = False
GENERATE_NATIVE_VDS = False
BUILD_MODEM_SOF = False

if RUN_QUESTA_SIMULATION:
    rtl_result = simulate(gui=False)  # Actual RTL assertions; no FPGA/JTAG/serial access.
    print("RTL simulation:", rtl_result["status"])
if GENERATE_NATIVE_VDS:
    modem_qpf = build_modem(generate_only=True)  # Tool invocation shows progress and writes a log.
    print("Generated project:", modem_qpf)
if BUILD_MODEM_SOF:
    modem_qpf = build_modem(generate_only=False)  # Quartus compile only; no board programming.
    print("Built SOF:", modem_qpf.with_suffix(".sof"))

saved_diagram = ROOT / "notebooks/diagrams/08_vds_gui.png"
display(Image(filename=str(saved_diagram)))
print("Saved actual VDS export:", saved_diagram)''',metadata={'tags':['rtl','offline','optional-tools']}),
 nb.v4.new_markdown_cell("### Optional · program checkpoint 06\n\nThis replaces the currently loaded FPGA image with the modem checkpoint. It checks the build fingerprint and SOF SHA, stops only this checkout's notebook-owned demo, refuses remaining serial/JTAG owners and uses the explicit Atum JTAG cable setting. Do not run this while another acquisition service or design owner is active. The cell is separate from generation/simulation and defaults off; it does not flash or reset an ESP32. Review the compiled image and its resource/timing reports before explicitly running this cell."),
 nb.v4.new_code_cell('''from modem_fpga import program

RUN_PROGRAM_MODEM = False  # Explicitly set True and run this cell to load checkpoint 06.
if RUN_PROGRAM_MODEM:
    active_modem = program()  # Hash/source guard + device-owner guard + progress.
    print("Loaded:", active_modem["stage_relative"], "· hardware qualification remains separate.")
else:
    print("Programming skipped. Set RUN_PROGRAM_MODEM=True only for the explicit checkpoint 06 load.")''',metadata={'tags':['hardware','program','modem-checkpoint']}),
 nb.v4.new_markdown_cell("## Cleanup\n\nStop the local page and release its port when finished. The process is separate from FPGA acquisition services."),
 nb.v4.new_code_cell('''if "lab_process" in globals() and lab_process.poll() is None:
    lab_process.terminate()
    lab_process.wait(timeout=5)
    lab_log.close()
    print("Modem Lab stopped.")
else:
    print("No Modem Lab server is running from this kernel.")''',metadata={'tags':['cleanup']})
]
modem_notebook = nb.v4.new_notebook(cells=modem_cells,metadata={'kernelspec':{'name':'atum-a3-iq','display_name':'Atum A3 IQ Demos','language':'python'},'language_info':{'name':'python','version':'3.12'}})
write_notebook(modem_notebook, ROOT/'notebooks/08_modem_lab.ipynb')
