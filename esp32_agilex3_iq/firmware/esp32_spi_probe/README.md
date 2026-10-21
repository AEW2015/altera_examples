# Separate PMOD B SPI transport firmware

See [SPI transport qualification](../../docs/SPI_TRANSPORT.md) for wiring,
protocol, build, FPGA image and host readback commands.

- `bash scripts/build_spi_probe.sh synthetic`: known CI8 byte ramp, no RF.
- `bash scripts/build_spi_probe.sh rf`: combined synthetic/real-RX image, starts synthetic. SPI `R` requests fixed
  channel8/2447MHz, nominal16MS/s,16380 samples; `T` returns to synthetic.
  One firmware flash supports both; no RF transmission.
- Separate build directories and SHA manifests; never flashed by build scripts.
- SPI mode1, MSB first,5MHz initial master rate; CS5/MOSI23/MISO19/SCK18,
  READY2 on the Digilent Pmod SPI selector path.
- `iq_spi_packet.c`: portable bounded header/CRC/CI8 chunk encoder, native-tested
  against Python. Firmware flag distinguishes synthetic data from real RX.
- `iq_spi_slave.c`: ESP-IDF DMA slave with one packet queued, READY callbacks,
  retained DMA ownership across timeout and exact transaction-length checks.
- `iq_spi_publish()` is a single-producer blocking capture hook; this is not
  a continuous real-time SDR stream or an arbitrary-IQ transmitter.

Programming uses the installed J2 UART0/GPIO0 wires and existing ROM bridge
procedure. The SPI images are accepted only for `--module pmod-b` by the guarded
flash utility. Confirm the target MAC, preserve the current image, and guide
manual reset/switch steps; do not replace a running radio just to build this code.
