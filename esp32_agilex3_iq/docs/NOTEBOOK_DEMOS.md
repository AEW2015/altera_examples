# See the result, then prove it

Run the notebook's build/program/launch cells and open its private control link. Each checkpoint has a focused experiment page. Diagnostic graphs work directly in the browser; expand **native CyberEther canvas** to view the same acquisition through its video renderer. Reloading the page gets new HTML, but backend changes require stopping/relaunching the notebook-owned demo.

| Notebook | Quick experiment | What should change | Evidence |
|---|---|---|---|
| 01 raw bridge | Software preview → Return to hardware | Known tones in preview; actual RF in hardware view | Fresh job/capture, CRC, radio/length/rate metadata |
| 02 Nios monitor | Capture / pause / resume | UART vs payload rate and advancing counter windows | Counter sequence, age and error counts from JTAG |
| 03 FIR | FPGA impulse → FPGA two-tone; Hamming / Boxcar | Impulse spreads over taps; different frequency rejection | Exact FPGA input pattern, coefficients/rounding, dump CRC, integer-reference error |
| 04 DDC | Verify tone rejection → Show alias → Impulse response | Wanted tone shifts, interferer rejection/alias, filter startup | Latched phase/config, output length/rate, CRC and integer-reference error |
| 05 gain | Clean 1× → Boost 2× → Clip 16× | About +6 dB before clipping; then rails/harmonics | Gain readback, FPGA power/clipping integers, integer-reference error |

The first two images do not contain a test generator. Their **Software preview** is an offline numerical illustration; it cannot validate their FPGA path. Checkpoint 3 opens with its known FPGA impulse input, so its first result can verify the filter without an ESP32 RF signal. It already contains a 128-sample impulse/two-tone generator. Its new quick-check controls use existing Nios TEST/RUN/DUMP commands; no bitfile change is required. Checkpoints 4–5 use the existing 4096-sample FPGA patterns. Synthetic tests do not transmit RF. Selecting live RF restores the paired capture configuration before another radio capture.

## Read the page

- **Cyan input / gold output** share a physical frequency axis and CI8-equivalent amplitude units. DDC output covers only its decimated band; it is not stretched across the input bandwidth.
- Waveforms share time and amplitude scales. IQ plots are samples, not decoded symbols.
- FIR response is calculated on the host from coefficients. It is an explanation of the digital filter, not a measured RF response.
- FPGA gain meters are integer sums/peaks/clips; the host calculates logarithms and reference DSP. The host also calculates display FFTs.
- Waterfall history is bounded to 90 distinct results, reset when input/rate/context changes. It is sparse capture history, not continuous RF time.
- Nios rates come from distinct counter windows, not repeated browser polls. Stale counter age remains visible.

## The badge is evidence, not an acknowledgment

**VERIFIED** requires a fresh result whose acquisition settings match the current request, plus applicable CRC, exact fixture, result metadata/readback and integer-reference checks. Nominal RF center/sample-rate metadata is not an independent RF measurement. Raw transport has no arithmetic reference check.

**APPLYING** means the last result belongs to earlier settings. **MISMATCH** identifies a failed comparison. **HELD** means paused; **STALE** means too old; **ERROR / DISCONNECTED** means acquisition or the API is unavailable. Held graphs remain visible and do not become a fresh pass.

**Software preview** calls only host reference routines. It never opens serial, changes controls or supplies fake counters; it replaces the hardware badge with **SOFTWARE PREVIEW / NOT RUN**. Use **Return to hardware** to inspect measured results again.

Tests: run `.venv-notebooks/bin/python -m unittest discover -s cyberether/tests -q`. Optional browser checks use Playwright (development dependency only): install `playwright`, run `python -m playwright install chromium`, then `.venv-notebooks/bin/python scripts/check_lesson_browser.py`. These browser checks use an in-memory/mock acquisition server, never the board.
