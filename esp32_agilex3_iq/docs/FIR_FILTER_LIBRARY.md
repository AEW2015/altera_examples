# FIR filter library

The FIR lesson has **15 host-stored examples**, a Python loading API and a CyberEther selector/editor. The existing FPGA has **one active set of 16 signed Q15 taps**, shared by I and Q. Changing coefficients does not require a new bitfile or ESP32 flash. The DDC's separate 127-tap filters remain fixed.

| Python name | Example |
|---|---|
| `hamming` | Existing 16-tap Hamming low-pass |
| `boxcar` | 16-sample moving average |
| `identity` | Near-unity pass-through |
| `delay-7` | Seven-sample delay |
| `average-4` | Four-sample moving average |
| `binomial-5` | Binomial smoother |
| `gaussian` | Gaussian smoother |
| `lowpass-narrow` | Low-pass at 0.08 Fs |
| `lowpass-wide` | Low-pass at 0.20 Fs |
| `highpass` | High-pass at 0.20 Fs |
| `bandpass` | Band-pass, 0.22–0.43 Fs |
| `notch-4mhz` | Notch at 0.25 Fs, or 4 MHz at 16 MS/s |
| `notch-6mhz` | Notch at 0.375 Fs, or 6 MHz at 16 MS/s |
| `dc-blocker` | Half-scaled first difference |
| `echo-comb` | Current plus eight-sample-delayed input |

The FIR checkpoint’s short two-tone test contains −0.5 and +4 MHz at 16 MS/s. The DDC’s longer test contains +0.5 and +6 MHz. Use `notch-4mhz` with the FIR test.

Cutoff/zero frequencies scale with the nominal input sample rate. Fifteen-tap designs are padded to 16 taps; short filters have broad transitions. The response preview uses the actual quantized coefficients. Their L1 sum is a worst-case amplification bound: a passband near unity does not prevent arbitrary inputs from clipping. Q15 coefficient `k` represents `k/32768`; +1.0 is outside its representable range, so identity/delay use 32767/32768.

## Notebook

Open [03 FIR](../notebooks/03_fir_filter.ipynb). The library table and response plot are offline. After its programming and CyberEther launch cells:

```python
from fir_controls import FIRControls
from fir_filters import plot_filter, q15

plot_filter('notch-4mhz')  # Host preview only.
fir = FIRControls()
result = fir.apply('notch-4mhz', input_kind='fpga-tones')
print(result)

# Eight-sample average, zero-padded to 16 taps:
custom = [4096] * 8 + [0] * 8
print(fir.apply(coefficients=custom, input_kind='fpga-impulse'))

# Four-sample averaging filter designed with real-valued taps:
custom = q15([0.25] * 4)
# print(fir.apply(coefficients=custom, input_kind='live'))

# Optional same interactive page inside the notebook:
# fir.show_gui()
```

`FIRControls` sends authenticated requests to the already running acquisition service. It does not open a competing UART or JTAG session. The running service must belong to this checkout; stop/relaunch it after updating. Its loader verifies every coefficient and its result must match the independent integer reference before `apply()` returns success. It also works while paused by requesting one result. The selected filter persists across subsequent captures until another filter is selected or the demo restarts.

## CyberEther

1. Select a filter example and click **Apply selected example**.
2. Use **FPGA two-tone check** to compare frequency rejection, or **FPGA impulse check** to see its impulse response.
3. Open **Filter design** for a candidate response and all 16 Q15 integers. Editing/previewing alone does not change hardware. **Apply edited taps as custom** loads them explicitly.
4. Inspect coefficient readback/hash, profile, rounding, CRC and integer-reference error in the evidence table. Requested settings are not treated as applied before a matching result arrives.
5. Choose **Live RF** to retain the selected filter while returning to the radio input.

The library's Hamming/Boxcar entries reuse built-in profiles 2/1; other named examples and user coefficients use profile 0. Only one set is resident. Updates disable pairing at a job boundary, write/verify the set and rounding, then configure pairing for the next capture. The active set is part of the worker's configuration key, so the next capture does not silently restore a built-in preset. Invalid lengths, non-integer coefficients and values outside −32768…32767 are rejected before any reload.

Python's frequency response, plot FFT and integer reference are host computations. Actual filtering and rounding/saturation run in FPGA FIR II. The display distinguishes software previews, FPGA test signals and live RF; IQ scatter is not decoded modulation symbols.
