# SPI IQ Pipeline Lab

The SPI IQ Pipeline Lab gives PMOD B its own capture and processing page on
port8771. The page is idle when opened: it does not acquire RF, flash either
device, or program the FPGA. Use **Verify test pattern** or **Capture real RF**
to start one explicit bounded run.

```mermaid
flowchart LR
 B[PMOD B ESP32\nCI8 snapshot] -->|SPI · 5 MHz| F[Agilex FPGA\ncheckpoint07 proxy + capture RAM]
 F -->|raw IQB1| H[Host\nCRC + independent integer check]
 F --> FIR[FIR II\n16-tap profile]
 FIR -->|filtered IQB1| H
 H --> V[Browser\nFFT and plots]
```

In FPGA, CRC/order checks and integer power, peak and clipping measurements run
with the capture controller. Checkpoint07 stages each SPI capture through raw
RAM and FIR II. The host verifies both IQB1 frames, capture identity, CRCs and
FIR output against an independent integer reference, then calculates the
display FFT. The plot is an analysis view of normalized CI8 samples, not a
calibrated power measurement. Final checkpoint07 SOF
`19ff94b02e3670587ada244a3ce6eb41aed2dbd0f21970a0db17c9dc8a06fa2b` passed a
fresh-boot capture. All 16 default taps read back as 2048; an exact Hamming
profile run matched the integer reference for 16,380 complex samples, and
settings restoration passed. The boot-fixed proof is
`cyberether/run/spi-fir-boot-fixed-synthetic-001`.

Checkpoint07 control guards were physically tested: 40 MHz / 2417 MHz returns
error128; a 1024-sample request returns error32 without arming. A valid SPI raw
capture and four passive RFS2 UART0 captures then passed, recorded in
`spi-profile-rejection-recovery-001`. PMOD A UART INFO responds, but its known v5
TX attempt hangs in PHY setup before `FRAME_CFG`; this produced no RF capture and
is not a SPI result. Its separate v6 WDT-recovery/timing build is not flashed or
hardware-qualified.

## Start the page

Run beside the installed FPGA tools, either on the Linux host or in its desktop
container:

```bash
.venv-notebooks/bin/python scripts/start_spi_pipeline_lab.py start
```

Open the URL printed by the launcher (port8771) in a browser that can reach that
host. It binds to `0.0.0.0` by default and reports a reachable address; there is
no fixed host or IP to configure. The existing [RF Link Lab](RF_BPSK_WALKTHROUGH.md)
is a separate page on port8770. Both pages use the same acquisition lock, so
they cannot capture simultaneously. The viewer enables SPI controls only when
the selected image manifest identifies checkpoint07. The checker independently
requires the shared acquisition lock and rejects a run if another owner holds
it. Release the other capture owner before retrying. To inspect or stop the page:

```bash
.venv-notebooks/bin/python scripts/start_spi_pipeline_lab.py status
.venv-notebooks/bin/python scripts/start_spi_pipeline_lab.py stop
```

## Run a bounded capture

Use the known PMOD B setup: combined SPI receiver firmware installed, SPI
selector ON, BOOT selector OFF, and the intended FPGA image already loaded. The
qualified meter image identifies as `SPIQ0002` and captures PMOD B only.
Checkpoint07 is the integrated SPI/FIR image. RFS2 UART0 passed four passive
captures on it. PMOD A UART INFO works, but transmitter RF remains unqualified
after a PHY setup watchdog hang before frame configuration.

In the page, select **SPI power meter** for the installed SPIQ0002 image or
**SPI + FIR pipeline** for integrated checkpoint07. Selecting an image in the
page only selects the requested test: it never loads that image. For the meter,
choose **Verify test pattern** to capture the deterministic CI8 pattern, or
**Capture real RF** for passive PMOD B RF on channel8 (2447 MHz, nominal16 MS/s).
The page labels synthetic and real RF separately and shows requested settings
alongside image, sequence, mode and verification readbacks. RF data is passive;
it does not start a transmitter.

The [SPI IQ and FIR notebook](../notebooks/09_spi_iq_fir.ipynb) walks through
the packet contract, FPGA processing and page. All 23 cells were executed in the
`atum-a3-iq` kernel; all 11 code cells completed without errors, with optional
generation, build, program, capture and viewer actions left at offline defaults.
The executed copy is saved under ignored `cyberether/run/`. It performs no board
capture. The notebook's explicit FPGA build/program and capture actions remain
separate hardware steps.

Checkpoint07 offers two reloadable 16-tap FIR profiles: **1, Boxcar average**,
and **2, Hamming low-pass**. The default is Hamming low-pass. Neither is a
bypass. Choose the requested **Host UART** rate, 2 Mbaud or 4 Mbaud; this controls
FPGA-to-host transport, not the fixed 5 MHz SPI clock. Meter mode stays at
2 Mbaud. The checker restores the host UART to 2 Mbaud after each run and
restores the prior FIR configuration; displayed readbacks describe the saved
capture.

The checkpoint07 **Live test · 12 captures** button runs six alternating pairs
of deterministic synthetic and passive RF snapshots, starting with synthetic.
It shows progress as each pair is checked. They are bounded snapshots, not
continuous sampling, and gaps between them have no inferred RF drop/delivery
rate. Single-capture buttons remain available for one requested source. The
checker verifies that raw and filtered representations belong to the same
capture, validates CRCs and applied coefficients, and compares the result to an
independent integer reference. The final checkpoint07 image passed bounded
hardware checks, including fresh-boot coefficient readback and exact FIR
comparison. The viewer's selected profile is still only a requested setting;
use the captured coefficient readback and independent integer result as proof.
The latest final-image 12-capture GUI batch (`spi-gui-1792618348955853001`)
verified its first synthetic pair, then failed the required PMOD A INFO liveness
check. Cleanup verified the host UART returned to 2 Mbaud and FIR settings were
restored. This is a failed soak, not an SPI/FIR failure; the known v5 PHY setup
watchdog leaves PMOD A UART-unresponsive until manual reset. Repeat the batch
after transmitter recovery; do not weaken its liveness check.

A separate one-shot browser RF capture (`browser-final-single-001`) on the final
SOF passed the actual Hamming profile at 4 Mbaud: raw and FIR payloads matched
bit-for-bit, with no JavaScript errors. This proves that bounded capture path,
not the failed 12-capture liveness soak or PMOD A transmitter. The saved view is
![A verified 4-Mbaud RF capture through the checkpoint07 Hamming FIR](images/spi_pipeline_fir_lab.png)

The integrated checker requires explicit acknowledgement that the correct
checkpoint07 image is already loaded, saves proof/raw results to a new run
directory, and can also save the Lab's snapshot JSON:

```bash
.venv-notebooks/bin/python scripts/check_spi_fir.py \
  --confirm-spi-image --output cyberether/run/spi-fir-boxcar-001 \
  --snapshot cyberether/run/spi-fir-boxcar-001/snapshot.json --profile 1
.venv-notebooks/bin/python scripts/check_spi_fir.py \
  --confirm-spi-image --output cyberether/run/spi-fir-hamming-rf-001 \
  --snapshot cyberether/run/spi-fir-hamming-rf-001/snapshot.json --profile 2 --rf
```

Use a new, unused `--output` directory for every run. `--rf` selects passive
channel8 capture; without it the source is the synthetic pattern. `--profile 1`
selects the 16-tap boxcar average; `--profile 2` selects the Hamming low-pass.
Neither is bypass. The checker does not program the FPGA or flash an ESP32.
Matched profile-2 RF runs over 16,380 complex samples measured 79,164 useful
input B/s at 2 Mbaud and 126,048 B/s at 4 Mbaud. These rates exclude Nios setup
and host verification; CS-active SPI ingress remains about 591,134 B/s.

The final-image one-shot 4-Mbaud RF browser proof passed raw/FIR bit equality
with no JavaScript errors. Its proof is separate from the earlier matched-rate
measurements and does not establish a continuous rate or soak result.

![SPI IQ Pipeline Lab showing a verified FPGA meter capture and host display](images/spi_pipeline_lab.png)

The image is a saved view of the actual meter Lab from a completed capture. It
is historical evidence, not a live capture from the current FPGA image. A page
render or screenshot does not itself prove that a capture was acquired; use the
run proof and readbacks for measurement evidence.
