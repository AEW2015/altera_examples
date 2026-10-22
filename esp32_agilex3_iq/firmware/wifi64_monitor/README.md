# Independent native Wi-Fi monitor

Original ESP32 / PMOD B, GPIO17 TX / GPIO16 RX at2Mbaud. Firmware is passive:
no association, credentials or TX API. It only reports matching W64A DATA frames.
This is native PHY monitoring, not an FPGA raw-IQ decoder and not pre-FEC BER.

```sh
ATUM_ESP_IDF=/path/to/pinned/esp-idf-sdr bash scripts/build_wifi64_monitor.sh
```

Export `IDF_TOOLS_PATH` if needed. Uses the same pinned SDK as wifi64_tx.
The build never installs firmware. Guarded programmer accepts this image only
for `pmod-b`, with application pins17/16. Preserve a private full-flash backup;
use the established ROM bridge/J2 reset workflow. After programming, restore the
runtime FPGA image, release GPIO0, set B's SPI selector **OFF** (UART), leave BOOT
OFF, then reset normally. Installing this replaces the current SPI receiver;
restore its saved image and switch setting to return to the SPI lesson.

```text
INFO
LISTEN 8 5000
STATUS
STOP
```

LISTEN accepts channels1–11 and10–10000ms, rejects changes while listening and
stops promiscuous reception at expiry. Boot initializes the passive NULL-mode
radio but does not begin listening. Queue depth16; reports `matched` and `drops`.
Only DATA frames at least92bytes long with W64A at body offset0 are queued.
`PACKET` reports run/packet/seed, native `rate_code`, `sig_mode`, channel, RSSI
and independently checked deterministic body. `PHY` reports native rate,
mode, RSSI, channel and `rx_state` (require zero). Rows are paced by2ms to
avoid overrunning the FPGA text queue. `META` joins those IDs with native
RX timestamp and frame length. Timestamp is not a shared RF phase clock.

Legacy sig_mode0/rate_code12 denotes54Mb/s in this SDK. Preserve the raw fields;
require matching identity/body and independently decoded L-SIG before claiming
FPGA 64-QAM reception. Native reception normally exposes successfully decoded
packets; unmatched/missed packets and callback queue drops remain separate from
bit-error counts. UART reports may span multiple FPGA text envelopes: reconstruct
complete newline-terminated records, never treat an envelope as a complete line.
