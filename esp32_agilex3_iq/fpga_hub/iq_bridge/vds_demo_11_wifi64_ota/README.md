# Checkpoint 11 — native Wi-Fi receiver foundation

**Build baseline, not an OTA decoder yet.** This separate native Visual Designer
Studio project copies the tracked checkpoint 06 capture/FIR/DDC/gain/modem design
and expands Nios V on-chip RAM from 64 KiB to **256 KiB**. Radio ports, board pins,
50 MHz SDC and the original monitor behavior remain unchanged. No hardware is
programmed by generation/build/export/simulation.

Changes are consistent across editable `scripts/create_vds.tcl` (`memorySize
262144`), `sw/link.ld` (`LENGTH=256K`, stack top 0x3fff0), HEX range 0..0x3ffff and
firmware build metadata. CPU debug is moved to **0x40000** in both instruction
and data maps; the CPU timer is moved to **0x50000**. Use `sw/platform_map.h`
for future checkpoint 11 software; earlier checkpoints keep their own maps.

A native VDS experiment with 192 KiB showed that the memory's Avalon span rounds
up to 256 KiB (0..0x3ffff), overlapping the old CPU debug region. The 256 KiB
choice and both relocations provide actual headroom for the receiver workspace
and remove that conflict. A 128 KiB prototype was too tight for the projected
complete receiver plus monitor and stack. These are capacity decisions, not
proof of a working OTA receiver.

All custom IP descriptors refer to this project's own RTL. Three inherited reset
descriptors (DDC, gain and modem) now correctly declare synchronous edges BOTH,
matching their clocked RTL. The DDC FIR reset source declares its associated reset
sink. These metadata repairs remove native VDS validation warnings. All other
datapath RTL and the explicit SDC remain byte-identical to checkpoint 06.

The copied symbol modem demapper is internally pipelined in checkpoint 11: mapping
→ subtraction → squared distance → minimum update. This preserves 64-bit
arithmetic, CSR format and values while adding three cycles per candidate point.
The first unpipelined fit missed 50 MHz setup by 0.471 ns; its measured path crossed
all four operations. The pipeline is a real logic change; timing constraints are
not relaxed. This custom symbol modem remains separate from IEEE Wi-Fi decoding.

From the example root, beside the Quartus/Nios/Questa tools:

```bash
.venv-notebooks/bin/python scripts/wifi64_fpga.py generate
.venv-notebooks/bin/python scripts/wifi64_fpga.py simulate
.venv-notebooks/bin/python scripts/wifi64_fpga.py build
.venv-notebooks/bin/python scripts/wifi64_fpga.py check
```

Open `iq_bridge_vds.qpf`, then Tools → Visual Designer Studio and
`src/vds/iq_bridge_system/iq_bridge_system.vds` after generation. Change blocks
through the authored create/connect Tcl; generated files are not source.

The build helper packages a complete portable project in
`results/vds_demo_11_wifi64_ota-quartus-project.zip`, with explicit SDC, generated
system and leaf IP QIPs, source RTL and Nios initialization HEX. It fingerprints
source, helper and SOF separately and rejects a mismatched completed build.

Legacy Lesson/Nios helper stage selections intentionally remain unchanged.
Use this helper for 11; no implicit redirection of 06 or active FPGA image occurs.
The copied symbol-replay modem uses its existing custom mapping/FEC conventions,
not the complete IEEE Wi-Fi receiver. Native OFDM receiver software integration,
contiguous IQ delivery, fresh RF reception, constellation and BER qualification
are separate later gates. Enlarging RAM alone does not implement those stages.

## Qualified build baseline

The pipelined design builds with Quartus Pro 26.1.1 at 50 MHz: setup slack +2.777 ns,
minimum reported slack +0.016 ns; 27,769 ALMs, 242 M20Ks and 32 reported DSP units.
Questa's five symbol-modem cases match independent reference outputs, including
all constellation points and the 64-QAM noisy case. These are build/module tests;
the CPU, radio links and OTA receiver are **not hardware-qualified on 11** yet.

Generated evidence: `BUILD_RESULT.json`, `sw/BUILD_RESULT.json`,
`run/address-map-verification.json`, `run/export-check.json`,
`results/modem-simulation/validation.json` and the complete project ZIP.
The first failed setup path/SOF remain under `run/timing-before-pipeline/` for
comparison. An extracted-project recompile has not been performed.
