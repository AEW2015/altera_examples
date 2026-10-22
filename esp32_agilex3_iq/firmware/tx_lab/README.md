# Combined PMOD A transmitter lab

One ESP32 image contains three software-selected modes: amplitude research,
native Wi-Fi54Mb/s transmission, and carrier/phase/BPSK/QPSK research.

See [the build, switching and experiment guide](../../docs/TX_LAB_FIRMWARE.md).
`bash scripts/build_tx_lab.sh` builds only. Mode switching restarts the ESP32,
requires RF off, and never starts a transmission. Cold boot defaults to AMP.

The project reuses the existing firmware source modules through separate
translation units; their standalone builds remain available. Its own CMake target
enables the common UART mode dispatcher and bounded PHASE profile.
