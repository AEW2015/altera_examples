# Native Wi-Fi monitor capture notes

PMOD A (`Bridge` radio source 1) runs `firmware/wifi64_tx`; PMOD B (source 2)
runs the passive `firmware/wifi64_monitor`. A native TX callback is local driver
telemetry. It does not establish that a packet reached B or that B decoded
54 Mb/s. The independent claim comes from B's joined `PACKET`, `PHY` and `META`
records, matched to the requested A job.

## Capture sequence

1. Acquire the shared `cyberether/run/rf-link-capture.lock`, connect the bridge,
   and set radio sources 1 and 2 to 2 Mbaud. Query B `INFO` and A `INFO` /
   `CONFIG?`; retain both identities and all returned lines.
2. Configure A with the chosen run ID, seed and packet count, then verify its
   `CONFIG?` readback. Arm A and verify its channel and power readback.
3. Start B listening on the same channel before starting A. For example, send
   B `LISTEN 8 5000` and require `WIFI64_MON,LISTEN,ok=1,ch=8,ms=5000,error=0`.
   Its listening window is bounded to 10 seconds maximum.
4. Write `START` to A, then read and route bridge text envelopes from both
   sources until A reports the matching `WIFI64_TX,DONE,job=...`. While waiting,
   retain every source-2 monitor text chunk. Do not use `Bridge.wait_text(1,...)`
   during this interval: it consumes and discards text frames from other radio
   sources while searching for source 1.
5. Reassemble newline records independently per radio because one logical UART
   line may span several FPGA text envelopes. A source-2 `WIFI64_MON,PACKET`,
   `PHY` or `META` record is usable only after its terminating newline is seen.
   Parse all three types and join by `(run, packet)`; accept any arrival order.
6. Send `STOP` to A and B, query both `STATUS` records, and retain the final
   `busy=0,rf=0,stop_err=0` A state plus B `listening=0`, `matched` and `drops`.
   Missing B records, incomplete joins, duplicate record types and monitor queue
   drops stay visible; do not silently repair or deduplicate them.

The pure text helpers in `cyberether/wifi64_records.py` implement strict record
parsing and order-independent joining. Give `Wifi64MonitorJoiner` an expected
map from `(run, packet)` to seed, such as `expected_packet_map(run, count,
seed)`. This binds received IDs to the commanded job. Its audit separates absent
PACKET records, incomplete triples, duplicates and unexpected IDs.

## Qualification rules

For a matching 54-Mb/s native observation, require all of the following on the
same `(run, packet)` identity:

- A `PACKET` line with the expected run, packet index and seed, and `body_ok=1`.
- A `PHY` line with `rate_code=12` and `sig_mode=0`. Preserve raw RSSI and
  channel fields, and require `rx_state=0` (no reported receive error). These
  values are the installed SDK's legacy 54-Mb/s encoding. Preserve nonzero
  `rx_state` values in evidence, but do not qualify those observations.
- A `META` line with matching run and packet, `native_rx=1`, timestamp and
  length. The timestamp is the monitor's receive timestamp, not shared RF phase
  or sample-clock evidence.
- No duplicate record type for that identity, and no mismatch against the
  expected packet/seed map.

The monitor's `body_ok` checks the deterministic body against the IDs and seed
read from that received body. The host-side expected map is separately needed
to prove that those IDs and seed match the requested transmitter job. Require
distinct expected packet indices; report missing or duplicated indices rather
than counting them as successful observations. `rate_code=12` and
`sig_mode=0` corroborate the PHY rate only when the joined packet identity and
body checks also pass and `rx_state=0`. The current monitor record does not
expose a separate FCS-valid flag; do not infer one from `rx_state`.

These records establish successfully decoded native packet observations and
support a packet-delivery/PER denominator when paired with A's eligible
transmission list. They do not reveal bit errors in packets B rejected, and they
do not establish raw-IQ BER, pre-FEC BER, or FPGA decoding. A callback `rate54`
counter from A must never be substituted for B's independent PHY record.
