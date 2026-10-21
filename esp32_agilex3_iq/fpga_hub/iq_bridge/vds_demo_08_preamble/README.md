# Checkpoint08 · raw-IQ QPSK preamble detector

This extends checkpoint07 with a buffered differential preamble detector in parallel with FIR II. The two observer conduits carry identical raw writes and CRC-qualified commit metadata; neither stalls capture transport. VDS conduits are point-to-point, so the controller exposes a dedicated preamble observer interface.

```text
ESP32 SPI/UART → CRC-qualified capture RAM ┬→ FIR II → paired output
                                         └→ preamble RAM → means → differentials
                                            → training rotations → Q15 score → peak
Nios V / JTAG UART → configuration, CI8 replay, result and trace readout
```

Run from the example root, beside the installed Quartus/Questa tools:

```bash
.venv-notebooks/bin/python scripts/preamble_pipeline.py generate
.venv-notebooks/bin/python scripts/preamble_pipeline.py simulate
.venv-notebooks/bin/python scripts/preamble_pipeline.py build
.venv-notebooks/bin/python scripts/preamble_pipeline.py program
.venv-notebooks/bin/python scripts/check_preamble.py --synthetic --output cyberether/run/preamble-clean-001
.venv-notebooks/bin/python scripts/start_preamble_lab.py start --saved-iq /path/to/saved.ci8
```

Programming is explicit. Replay uploads raw CI8 and executes the detector on the FPGA; Python computes an independent integer reference afterward. `--passive` captures PMOD B SPI RF directly into both FPGA capture and detector RAM. These actions never start a transmitter. All hardware actions share the acquisition/JTAG leases and clear the detector afterward with readback verification.

The native VDS design has 14 blocks, with `preamble_detector` at Avalon address `0x10070000`. Authored sources are `rtl/`, `ip/`, `sw/` and the create/connect Tcl files. Generated `src/vds/`, `gen/`, ELF/HEX and SOF files remain local. Build exports the complete QPF/QSF/SDC/vendor-IP project ZIP under `results/`. Official BSP/apps: `python scripts/nios_software.py 8`; open them in RiscFree. This does not download an ELF.

See the [lesson notebook](../../../notebooks/10_fpga_preamble.ipynb) and [detector guide](../../../docs/FPGA_PREAMBLE_LAB.md) for the register map, simulation GUI, formats, limitations and qualification. A detected preamble is coarse sample-window alignment; it does not establish carrier lock, decoded payload, CRC or BER.
