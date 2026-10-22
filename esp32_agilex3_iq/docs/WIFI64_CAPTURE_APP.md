# Wi-Fi64 capture receiver on Nios V

The dedicated checkpoint11 application reads one frozen RFS2 IQ capture from
FPGA RAM and processes it on Nios V. The host sends commands and displays the
returned measurements. No runtime host synchronization, FFT, demapping, FEC or
CRC is used to produce the receiver result.

```text
RFS2 ESP32 raw CI8, nominal40MS/s
                │
       Agilex3 capture/FIR RAM
                │ stable metadata + whole-buffer CRC
          Nios V receiver
  FIR /2 → acquisition+CFO → FFT64 → channel/equalizer
          → pilots → L-SIG → 64QAM soft demap
          → deinterleave/depuncture → Viterbi
          → descramble → packet FCS
                │
       Host: points, bytes, status
```

These receiver stages are **Nios software**, separate from the existing RTL FIR,
DDC and modem blocks. The new receiver is a functional prototype; acceleration
and continuous reception remain later work. Installed original ESP32 TX uses its
native Wi-Fi PHY for54Mb/s64QAM, not FPGA-generated arbitrary TX IQ.

The first hardware passive16380-sample run verified the RAM copy/CRC and executed
the receiver, but found no preamble/header. Its device processing time was about
147seconds. That is **not a decoded OTA64QAM result**. A valid native packet/rate
observation on the independent ESP32 monitor is a separate milestone. Require a
fresh real-RF capture with decoded54Mb/s L-SIG and valid packet FCS before claiming
this raw-IQ chain decoded native64QAM over the air.

## Build and load

Run from the project directory beside installed Quartus/Nios tools, either on a
host or in its desktop container. Use the local project venv; do not forward
programming through another environment.

```sh
.venv-notebooks/bin/python scripts/wifi64_fpga.py build
.venv-notebooks/bin/python scripts/build_wifi64_capture_app.py
.venv-notebooks/bin/python scripts/program_wifi64.py fpga
.venv-notebooks/bin/python scripts/program_wifi64.py capture-app
.venv-notebooks/bin/python scripts/wifi64_capture.py \
  --output cyberether/run/wifi64-status-001.json
```

The first command builds checkpoint11's VDS foundation and SOF. The second builds
`simulation/wifi64-capture-app/wifi64_capture_app.elf`. The last command reads
`WVERSION`/`WSTATUS`; it does not arm a capture, decode or transmit.

Checkpoint11 has256KiB CPU RAM and its Nios timer at`0x50000`. Do not download
this ELF into checkpoint06/07/08. Programming the FPGA/CPU does not require an
ESP32 button press and does not install radio firmware. The correct RFS2 raw-IQ
firmware must already be present.

The programmer verifies the frozen FPGA helper/source/SOF hashes and the
application source/ELF hashes. It takes the RF and Nios leases, stops only this
checkout's recorded notebook demo and refuses other serial/JTAG owners. A failed
SOF attempt invalidates the old active-FPGA record; a failed ELF attempt leaves
no successful app marker. Successful records are **host programming records**,
not hashes read from the device. `WVERSION` checks the actual app/platform.

## Make a passive capture separately

Receiver inspection does not implicitly arm hardware. This Python example takes
one passive snapshot and leaves its raw RAM ready for a later `--decode`. It
never starts the transmitter.

```python
import fcntl
import sys
from pathlib import Path
sys.path[:0] = ["scripts", "cyberether"]
from common import ROOT
from iq_bridge import Bridge
from nios_fir import NiosFir

lease_path = ROOT / "cyberether/run/rf-link-capture.lock"
with lease_path.open("a") as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with NiosFir(pause_monitor=False) as cpu, Bridge() as bridge:
        version = cpu.command("WVERSION")
        assert version["cancel_supported"] == 1
        ready = False
        try:
            bridge.prepare_sdr(source=0, frequency_mhz=2447, rate=40_000_000)
            cpu.command("WCANCEL")
            # Optional calibrated IQ-polarity correction: cpu.command("WCONJ", 1)
            cpu.command("WARM")
            job = bridge.submit(source=0, samples=16380, rate=40_000_000)
            while True:
                frame = (bridge.responses.popleft() if bridge.responses
                         else bridge.read_frame(timeout=15))
                if frame.kind == 5:
                    raise RuntimeError("FPGA capture error")
                if frame.kind == 1 and frame.job == job:
                    break
            state = cpu.command("WSTATUS")
            ready = (state["state"] & 0x8B) == 2
            assert ready and state["source"] == 0 and state["rate"] == 40_000_000
            print("Frozen capture:", state)
        finally:
            if not ready:
                try:
                    bridge.control(6, source=0)
                finally:
                    cpu.command("WCANCEL")
```

The bridge's framed UART output is drained for transport integrity; it is not a
host receiver. At40MS/s this capture covers409.5µs and is a sparse snapshot.
`CAP16` starts acquisition in software; it is not an energy/packet trigger. A
short native packet can fall outside the window. Do not replace missing RF data
with a synthetic waveform or infer a raw-IQ decode from the native monitor.

The example channel must match the intended transmission. Changing the FPGA's
rate metadata alone does not qualify the analog sampling rate; the installed
RFS2 firmware's capture profile selects the ADC mode.

## Decode and inspect

```sh
.venv-notebooks/bin/python scripts/wifi64_capture.py --decode --timeout 600 \
  --output cyberether/run/wifi64-decode-001.json
```

Only this explicit action invokes `WRUN`. The CPU validates ready/idle status,
source0, nominal40MS/s, the sample bound and a stable capture identity. It reads
raw RAM with the synchronous-read ordering, computes the copy CRC and compares
it with the frozen FPGA CRC. It then runs the full receiver. The host retrieves
the actual equalized Q13 DATA points and decoded packet bytes in ID-tagged batches.
A decode may take minutes; the command allows600seconds by default.

Look at these distinct JSON fields:

| Field | Meaning |
|---|---|
| `completed` | The requested transport/decode/readout operation completed |
| `device_decode_accepted` | Device reported a complete54Mb/s packet with valid FCS |
| `device_result.status`, `stage` | Exact receiver outcome and furthest processing stage |
| `device_result.packet_status` | DATA/SERVICE/tail/FCS backend flags |
| `device_result.raw_crc`, `job` | Identity of the CPU's validated raw copy |
| `constellation` | Actual equalized DATA points: signed`i`,`q`, scale8192 |
| `decoded_psdu_hex` | Device-decoded bytes, including failed-FCS results |
| `ber_measured` | False: this app does not yet calculate reference-bit BER |

A completed operation can contain a rejected frame. Failed FCS bytes and points
remain in the proof; they are not silently filtered from the results. No BER is
invented for captures without acquired/decoded frames. Receiver acceptance alone
does not identify a particular transmitter without packet identity/monitor evidence.

Read individual cached measurements without rerunning the receiver:

```sh
.venv-notebooks/bin/python scripts/wifi64_capture.py --point 0 --byte 0 \
  --output cyberether/run/wifi64-cached-001.json
```

Cached inspection is labeled separately because `WSTATUS` shows the live capture
metadata, which need not identify an older cached decode. All proof paths must
be new; files are never overwritten. No command in this host reader programs
hardware, arms reception or starts TX.

## CPU command interface

Commands use the existing NiosFir envelope: `FIR <unsigned-ID> <verb> [index]`.
Only one UART/JTAG owner may hold the device at a time.

| Verb | Operation |
|---|---|
| `WVERSION` | Version1, RAM/timer/component IDs, host-DSP0, cancel/conjugation capabilities |
| `WSTATUS` | Live frozen-capture state and cached-result validity |
| `WARM` | Disable PAIR and arm the manual raw mirror; does not start ESP32 RX/TX |
| `WCANCEL` | Clear manual FIR arm/ready/done and invalidate cached results |
| `WCONJ 0` / `WCONJ 1` | Preserve or negate input Q on device; invalidates cached results |
| `WRUN` | Validate/copy the ready source0 capture and run the receiver |
| `WPOINT n` | Actual equalized DATA point at index`n` |
| `WBYTE n` | Decoded PSDU byte at index`n`, including failed FCS |

`WCANCEL` refuses FIR busy, UART-owned or DDC-busy state; successful cancellation
checks the state is clear. Bridge opcode6 alone does not clear a manual FIR arm.
Always require the cancel capability before an orchestration script arms the
mirror. Cancel after an abandoned capture or after reading its results.
**Do not cancel between a successful capture and `WRUN`: it clears ready RAM
validity.** A software-only cancel does not interrupt a running blocking decode;
wait for its result before issuing another command.

## Optional IQ polarity correction

`WVERSION` reports `conjugate_supported=1` on the new app. `WCONJ 1` negates Q
inside the Nios frontend **before rounding and clipping**; even rawQ=-128 is
handled without8-bit overflow. `WCONJ 0` preserves the original behavior and is
the boot default. `WSTATUS` and `WRUN` report the applied `conjugate_q` value.

Configure only after `WCANCEL` and before `WARM`; armed/busy/owned RAM rejects a
mode change. Read the setting back, and restore the original mode after a test.
The spectral-polarity calibration motivated this option, but conjugation alone
is not evidence that a real Wi-Fi packet decoded. Require the same L-SIG, packet
identity and FCS evidence as for the unmodified mode.

## Restore the normal monitor

Release any reader's JTAG handle, then explicitly restore the checkpoint11 monitor:

```sh
.venv-notebooks/bin/python scripts/program_wifi64.py monitor
```

This downloads the matching source-checked baseline monitor ELF; it does not
change the FPGA image. To return to another lesson, explicitly load that lesson's
matching SOF and monitor. The checkpoint11 capture application is separate from
the older checkpoint06 replay/BER demonstration.

Development checks:

```sh
.venv-notebooks/bin/python -m unittest discover -s cyberether/tests \
  -p 'test_wifi64_capture*.py' -v
.venv-notebooks/bin/python -m unittest discover -s cyberether/tests \
  -p 'test_program_wifi64.py' -v
```

These native MMIO/mock tests qualify guards and receiver arithmetic offline.
Hardware and genuine RF acceptance remain separately recorded evidence.
