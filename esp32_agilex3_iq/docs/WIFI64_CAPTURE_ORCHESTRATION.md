# Bounded native Wi-Fi → raw IQ → Nios receiver

`scripts/wifi64_capture_ota.py` is a **transport/controller**, not a host decoder.
This helper has offline tests; its RF overlap and end-to-end reception still need
hardware qualification. It never programs the board or flashes a radio.

Prerequisites: qualified checkpoint 11 SOF, the separately installed dedicated
Nios receiver app advertising `cancel_supported=1`, native Wi-Fi TX firmware on
PMOD A, raw SDR firmware on RFS2, and passive native monitor firmware on PMOD B.
The normal checkpoint 06 monitor or older receiver app is refused.

## What CAP16 actually does

The current original-chip receiver `acquire_iq()` clears the sample buffer,
applies its selected filter and pulses DUMP control bit 19. It takes an **immediate
ADC snapshot**, not a Wi-Fi preamble/energy-triggered recording. `CAP16` specifies
signed CI8 packing, not a 16 MS/s rate. `CAP16 8192 1` selects 40 MS/s and captures
204.8 µs; 16380 samples capture 409.5 µs. Rate/frequency metadata are requested settings,
not independent RF clock measurements.

Native packets are separated by at least 2 ms. A snapshot can therefore miss every
packet, even though the independent monitor sees all of them. Waiting for TX
DONE and then capturing will normally record the quiet interval.

## Command ordering

```text
RFS2: SDR / selected channel frequency / 40 MS/s; gain/filter readbacks
Nios: WVERSION verifies cancellation/conjugation capabilities
      WSTATUS mode → WCANCEL → WCONJ requested mode → verify readback
PMOD A: INFO, CONFIG (<=16 packets, 2 ms gap)
Nios: WARM → manual raw mirror armed, PAIR 0
PMOD A: ARM → PHY prepared, awaiting explicit START
Bridge: opcode 3 arm → ACK, without CAP yet
Host: one write [PMOD A START][RFS2 CAP16 + padding + newline]
       collect START/DONE + raw IQ + optional PMOD B text
Nios: WSTATUS verifies job/source/rate/frequency/raw CRC
PMOD A: STOP / idle verification; PMOD B: STOP
Nios: WRUN → synchronization / OFDM / decoding / FCS on board
Host: read recovered points and decoded bytes; parse known A identity
Finally: STOP both radios, cancel bridge, WCANCEL mirror/result
         restore original WCONJ mode and verify readback
```

The helper preserves IQ envelopes while waiting for text. Generic packet-only
`MonitorBridge` deliberately rejects IQ; generic `Bridge.wait_text()` can discard
unrelated captures. This adapter retains them and uses the existing envelope and
payload CRC checks. Raw IQ traverses the current host output transport, but no
host FFT, synchronization, demapping, FEC or BER computation occurs.

All long DSP work happens after TX is explicitly stopped. The app's WRUN can be
slow: a previous passive 16380-sample measurement took 147.399 seconds on Nios and
found no acquisition. The default is 8192 samples to reduce initial iteration time;
it does not guarantee half the latency or successful reception.

## Short phase search

Each forwarded radio ASCII byte occupies 20 bytes on the host IQBC link. At 2 Mbaud
8N1, an extra byte adds nominal 100 µs wire time. Zero/seven/fourteen trailing spaces
before the CAP newline vary request phase without changing CAP arguments or
creating extra replies. The actual C `sscanf` contract accepts these spaces.

This is **not RF synchronization**: USB scheduling, firmware buffer clearing,
calibration and native CSMA backoff all add uncertainty. Up to three explicitly
requested attempts use padding 0/7/14, unique run IDs, and at least 2.05 s host quiet
between jobs. Firmware also enforces its own two-second cooldown and 100 ms deadline.
The helper stops early after a qualified known-A decode. Default: one attempt.

## Explicit example

Run beside the tools with no other UART/JTAG owner, using a new output filename:

```bash
.venv-notebooks/bin/python scripts/wifi64_capture_ota.py \
  --transmit --attempts 1 --samples 8192 --run 20261021 --seed 7 \
  --hardware-gain --lpf64 --monitor \
  --output cyberether/run/wifi64-raw-ota-first.json
```

`--hardware-gain` and `--lpf64` are opt-in; original gain/filter preferences are
recorded and restored. LPF64 is an uncalibrated code, not a measured bandwidth.
`--samples 16380` and `--attempts 3` are explicit alternatives. There is no loop
that transmits indefinitely and no RF action on import or browser opening.

A new proof file is reserved before accessing devices; an existing file is
refused. Artifact hashes are host/build/programming records, not device-read
ELF/SOF hashes. WVERSION checks the installed command interface separately.

## What counts as a result

Keep these separate:

- Native TX callback counters: submitted/completed 54M packets; not received bits.
- Raw bridge/FIR identity and CRC: transport of the same actual snapshot.
- Nios acceptance: valid 54 Mb/s SIGNAL and payload FCS, with device constellation.
- Known A identity: device-decoded source MAC, `W64A`, run/packet/seed fields match.

`ota64_confirmed` requires both device acceptance and known-A identity, plus
successful TX telemetry and clean bridge transport. Failed captures/results remain
in the proof. A native monitor observation alone does not establish that the raw
snapshot contains A. No BER is inferred from CRC success or a missed acquisition.

Failure diagnostics preserve each START/DONE independently, the last 256 frame
identities and all-radio lines (including source0 ADC errors), and any received raw-capture metadata. If a TX
acknowledgement is missing, radios are stopped before frozen mirror status is
read; WCANCEL follows diagnostics. This path does not decode or qualify an OTA
result. The top-level TX-request flag aggregates all attempts.

An explicit CANCELLED terminal is retained as a firmware-deadline cancellation.
Matching frozen raw IQ can still be decoded on Nios after verified TX stop,
including device header/FCS and known-A identity results for investigation.
`raw_known_a_decode_confirmed` reports that narrower result independently; a
cancelled job always has `tx_success=false` and `ota64_confirmed=false`, even
when all packet callbacks or a device decode succeeded. No deadline is extended.

The default is two packets; counts up to 16 require an explicit `--count`.

For a single phase-7 engineering trial, add `--phase-pad 7 --attempts 1`.
Explicit phases accept 0..14 and prohibit multiple attempts. `--save-raw` saves
exact interleaved signed CI8 transport bytes before Nios decoding, including
recovered failure captures. The proof must reside under `cyberether/run`; a new
`<proof-stem>.private/` directory (0700) is reserved before device access. Raw
files (0600) use exclusive creation and include a SHA256/path in the proof. No
archive is overwritten and this archival path performs no host DSP. Saved raw
bytes do not prove that the intended transmitter was inside the capture.

`--channel 1..11` selects both native TX/optional monitor and raw receiver,
using `2412 + 5*(channel-1)` MHz; the default remains channel 8. Frozen raw
metadata must match that frequency. `--conjugate-q 1` requests **Nios software**
input conjugation, requires `conjugate_supported=1`, and verifies its mode before
arming and in the returned decode result. Saved/transported raw bytes remain
unchanged. The original mode is restored only after verified WCANCEL; failures
in mode configuration, readback or restoration invalidate completion. The
new app also allows explicit mode 0 (default); older apps are accepted only
for mode 0. Channel 11 plus conjugation is an engineering trial, not a claim
that this receiver has decoded an over-the-air Wi-Fi packet.
