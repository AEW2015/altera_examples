# Native Wi-Fi 64-QAM transmitter

Original ESP32 / Digilent PMOD A, application UART GPIO17 TX / GPIO16 RX,
2,000,000 baud. This uses the ESP32's **native Wi-Fi modem**, not arbitrary IQ.
The host does not generate packet content or a transmit waveform.

Build beside the pinned SDK and its installed toolchain:

```sh
ATUM_ESP_IDF=/path/to/pinned/esp-idf-sdr bash scripts/build_wifi64_tx.sh
```

If SDK tools were installed in a separate directory, export `IDF_TOOLS_PATH` too.
SDK commit: `25fe69f946311abdaf9ad56591f25fedbc20ac98`.
Build creates `build-wifi64-tx/`; it neither flashes nor transmits.
Use the repository's guarded `flash_esp32.py --module pmod-a --build-dir
build-wifi64-tx` workflow after the correct ROM bridge, private backup and manual
reset. Restore the runtime FPGA image, release GPIO0, then reset for normal boot.
No firmware install or hardware result is implied by this source/build.

## Commands

ASCII lines, no envelope; 95 bytes maximum before newline. Replies start
`WIFI64_TX,`. Oversized lines are discarded until newline. Unknown commands fail.

```text
INFO
CONFIG?
CONFIG 8 8 4 2 123 1
ARM
START
STATUS
STOP
```

`CONFIG channel power_qdbm packet_count gap_ms run seed` accepts channels 1–11,
power codes 8–40 (quarter-dBm API units, not calibrated radiated power), 1–16
packets, and 2–5 ms gaps. Default: channel8, power8, four packets, gap2ms,
run1/seed1. Rate is fixed legacy 54 Mb/s, 802.11g, 64-QAM rate3/4.
CONFIG is rejected while armed/busy; ARM expires after5s. START requires ARM.
The independent high-priority task stops the Wi-Fi driver at the100ms job deadline.
Every finished/cancelled job and STOP enforce2s quiet time before ARM. The driver
is uninitialized at boot; no association, scan, credentials or background TX loop
exists. ARM starts the driver without connecting; STOP and job completion stop it.
Do not start frequent jobs from a viewer timer.

STATUS and INFO include separate SUBMITTED and COUNTERS lines. Multi-line replies
pace rows by2ms to accommodate the FPGA text-envelope overhead. `accepted` counts
successful API submissions, not received packets; `done`/`failed` come from the
SDK TX callback. `rate54`/`other` count callback-reported rates, which still need
independent receiver confirmation. No callback count is a receiver FCS/BER.
RF=0 means the driver has been stopped; it is not a calibrated spectrum test.

## Exact packet contract

88 input bytes, no FCS in the supplied buffer. Native PHY supplies FCS and PHY
encoding. Non-QoS data FC=0x0008, no DS, duration0, Addr1 broadcast, Addr2 and
Addr3 station MAC. Sequence control=`(packet_index &4095)<<4`; fragment0.
`en_sys_seq=false`, no association and no ACK requested by the broadcast address.

Body is64bytes:

| Offset | Value |
|---|---|
| 0–3 | ASCII `W64A` |
| 4 | Version1 |
| 5 | Requested PHY Mbps54 |
| 6 | Body length64 |
| 7 | Reserved0 |
| 8–11 | Run ID, little-endian u32 |
| 12–15 | Packet index, little-endian u32, starts0 per job |
| 16–19 | Seed, little-endian u32 |
| 20–63 | Deterministic xorshift bytes |

Initialize u32 `x=seed ^ run ^ (packet_index*0x9e3779b9)` (wrapping arithmetic),
replace zero with1. For each remaining byte: `x^=x<<13; x^=x>>17; x^=x<<5`,
all u32; emit the low byte. `main/protocol.h` is the portable golden implementation.

An88byte input becomes92bytes with FCS. Nominal 54Mb/s OFDM PSDU requires4
symbols (16us) plus20us preamble/SIGNAL =36us per packet; ≤576us for16packets.
This excludes contention/backoff, calibration, driver setup and other RF effects;
the100ms deadline is a job guard, not an airtime measurement.

Hardware acceptance: preserve old image; verify READY idle, INFO/MAC/config,
bounded16packet job, callback counters, independent matching monitor rate54,
STOP/idle, cooldown rejection and raw wideband capture before any decoder claim.
