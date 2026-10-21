#!/usr/bin/env python3
"""Local educational modem simulation UI; every result is explicitly software-generated."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
MODULATIONS = {"BPSK", "QPSK", "16QAM", "64QAM"}
MODULATION_BITS = {"BPSK": 1, "QPSK": 2, "16QAM": 4, "64QAM": 6}
MODEM_STAGE = "fpga_hub/iq_bridge/vds_demo_06_modem"


def require_modem_checkpoint(root=ROOT):
    """Verify loaded manifest, checkpoint build, and SOF identity without touching hardware."""
    active_path = root / "cyberether/run/active-fpga.json"
    stage = root / MODEM_STAGE
    build_path = stage / "BUILD_RESULT.json"
    image = stage / "iq_bridge_vds.sof"
    try:
        active = json.loads(active_path.read_text())
        build = json.loads(build_path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("Checkpoint 06 must be built and loaded before FPGA symbol tests") from exc
    if active.get("stage_relative") != MODEM_STAGE:
        raise ValueError("Checkpoint 06 is not the active FPGA image")
    if build.get("status") != "PASS_BUILD" or build.get("checkpoint") != 6:
        raise ValueError("Checkpoint 06 build result is missing or unsuccessful")
    expected = build.get("sha256")
    if not expected or active.get("sha256") != expected or not image.is_file():
        raise ValueError("Active image does not match the checkpoint 06 build")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError("Checkpoint 06 SOF no longer matches its build result")
    return dict(stage_relative=MODEM_STAGE, sha256=digest, device=build.get("device"),
                status=build["status"], hardware_verified=bool(build.get("hardware_verified", False)))


def _nios_owner_busy(root=ROOT):
    lock_path = root / "cyberether/run/nios-fir.lock"
    if not lock_path.exists():
        return False
    try:
        with lock_path.open("r") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(stream, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        return True


def _jtag_owner_busy(proc_root=Path("/proc")):
    """Avoid a competing JTAG client even when it belongs to another checkout."""
    for cmdline in proc_root.glob("[0-9]*/cmdline"):
        try:
            args = cmdline.read_bytes().split(b"\0")
            executable = Path(os.readlink(cmdline.parent / "exe")).name
        except (OSError, ValueError):
            continue
        if executable in {"juart-terminal", "quartus_pgm"}:
            return True
        if args and Path(args[0].decode(errors="replace")).name in {"juart-terminal", "quartus_pgm"}:
            return True
    return False


def _viewer_active(root=ROOT, proc_root=Path("/proc")):
    graph_path = str(root / "cyberether/graphs").encode()
    for cmdline in proc_root.glob("[0-9]*/cmdline"):
        try:
            args = cmdline.read_bytes().split(b"\0")
            exe = Path(os.readlink(cmdline.parent / "exe")).name
        except (OSError, ValueError):
            continue
        if exe == "cyberether" and b"--remote-broker-port" in args and any(graph_path in arg for arg in args):
            return True
    return False


def _monitor_active(root=ROOT):
    try:
        active = json.loads((root / "cyberether/run/active-fpga.json").read_text())
        stage = root / active["stage_relative"]
        metadata = json.loads((stage / "run/live-monitor-process.json").read_text())
        pid = int(metadata["pid"])
        cmdline = Path(f"/proc/{pid}/cmdline")
        return cmdline.exists() and str(stage / "monitor_log.py").encode() in cmdline.read_bytes().split(b"\0")
    except (OSError, ValueError, KeyError, TypeError):
        return False


def fpga_status(enabled=False, root=ROOT, check_processes=True):
    status = dict(enabled=bool(enabled), ready=False, source="FPGA checkpoint 06 symbol-rate modem",
                  stage_relative=MODEM_STAGE, reason=None, owner_busy=False, viewer_active=False,
                  monitor_active=False, jtag_client_active=False, image_file_sha256=None)
    if not enabled:
        status["reason"] = "Optional FPGA action is disabled; restart with --enable-fpga-action to expose the manual control."
        return status
    try:
        checkpoint = require_modem_checkpoint(root)
    except ValueError as exc:
        status["reason"] = str(exc)
        return status
    status["image_file_sha256"] = checkpoint["sha256"]
    if check_processes:
        status["monitor_active"] = _monitor_active(root)
        if status["monitor_active"]:
            status["reason"] = "The active FPGA rate monitor is running; this action will not stop it."
            return status
        status["jtag_client_active"] = _jtag_owner_busy()
        if status["jtag_client_active"]:
            status["reason"] = "A JTAG client is active in this or another checkout; this action will not open a competing owner."
            return status
        status["owner_busy"] = _nios_owner_busy(root)
        status["viewer_active"] = _viewer_active(root)
        if status["viewer_active"]:
            status["reason"] = "A CyberEther viewer is already active; this action will not interrupt or replace it."
            return status
        if status["owner_busy"]:
            status["reason"] = "The existing Nios/JTAG owner is busy; this action will not open a second owner."
            return status
    status.update(ready=True, reason="Checkpoint 06 build and active-image manifest match. The board ID will be checked after the manual action.")
    return status


def validate_fpga_request(body):
    if not isinstance(body, dict) or set(body) - {"modulation", "seed"}:
        raise ValueError("FPGA test accepts only modulation and seed")
    mode = body.get("modulation", "QPSK")
    seed = body.get("seed", 7)
    if mode not in MODULATIONS:
        raise ValueError("Choose BPSK, QPSK, 16QAM or 64QAM")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("Seed must be a nonnegative 32-bit integer")
    # JTAG register transactions dominate interactive latency. This frame size
    # is qualified on all four modes by check_modem_hardware.py.
    return dict(modulation=mode, bps=MODULATION_BITS[mode], seed=seed, payload_bits=32)


def run_fpga_symbol_test(owner, body, checkpoint, modem_factory=None):
    """Run an RTL symbol/FEC recovery test through a caller-owned Nios instance.

    The owner lifetime belongs to the caller. This function never opens or
    closes JTAG and never feeds the Python waveform synchronizer.
    """
    import numpy as np
    settings = validate_fpga_request(body)
    if not isinstance(checkpoint, dict) or checkpoint.get("stage_relative") != MODEM_STAGE:
        raise ValueError("FPGA symbol test requires active checkpoint 06")
    if checkpoint.get("status") != "PASS_BUILD" or not checkpoint.get("sha256"):
        raise ValueError("FPGA symbol test requires a matching successful checkpoint 06 build")
    if modem_factory is None:
        from modem_fpga import ModemFPGA
        modem_factory = ModemFPGA
    from modem_reference import conv_encode, fixedpoint_soft_demapper, quantized_mapping

    modem = modem_factory(owner)
    bits = np.random.default_rng(settings["seed"]).integers(0, 2, settings["payload_bits"], dtype=np.uint8)
    tx = modem.encode(bits, bps=settings["bps"])
    coded_reference = conv_encode(bits)
    coded_matches = np.array_equal(np.asarray(tx["coded"], dtype=np.uint8), coded_reference)
    mapping = quantized_mapping(settings["modulation"])
    padded = np.pad(coded_reference, (0, (-len(coded_reference)) % settings["bps"]))
    labels = padded.reshape(-1, settings["bps"]) @ (1 << np.arange(settings["bps"] - 1, -1, -1))
    expected_iq = mapping[labels]
    mapping_matches = np.array_equal(np.asarray(tx["iq"], dtype=np.int16), expected_iq)
    symbol_index = min(10, len(labels) - 1)
    tx_iq = np.asarray(tx["iq"], dtype=np.int16).copy()
    tx_iq[symbol_index] = mapping[int(labels[symbol_index]) ^ 1]
    rx = modem.decode(tx_iq)
    host_errors = int(np.count_nonzero(np.asarray(rx["bits"], dtype=np.uint8) != bits))
    raw_errors = int(rx["raw_errors"])
    decoded_errors = int(rx["decoded_errors"])
    independent_llr = fixedpoint_soft_demapper(tx_iq, settings["modulation"])[:len(coded_reference)]
    fpga_llr = np.asarray(rx["llr"], dtype=np.int32)[:len(coded_reference)]
    llr_matches_reference = np.array_equal(fpga_llr, independent_llr)
    measured_raw_errors = int(np.count_nonzero((independent_llr < 0) != coded_reference))
    raw_counter_matches = measured_raw_errors == raw_errors
    passed = (coded_matches and mapping_matches and llr_matches_reference and raw_counter_matches
              and raw_errors == 1 and decoded_errors == host_errors == 0)
    return dict(status="PASS" if passed else "FAIL",
                source="FPGA checkpoint 06 symbol-rate modem",
                source_tag="fpga:checkpoint06:symbol-rate-fec",
                stage_relative=MODEM_STAGE, image_file_sha256=checkpoint["sha256"],
                fpga_id="0x4d440601", hardware_verified=passed,
                settings=settings, evidence=dict(input_origin="FPGA encoder/mapper symbol buffer",
                    output_origin="FPGA max-log demapper + soft Viterbi",
                    perturbation="one nearest-neighbor symbol error injected at the host before FPGA demapping",
                    rf_capture_id=None, rf_tx=False, python_waveform_sync=False,
                    information_bits=len(bits), coded_bits=len(coded_reference), symbols=int(len(tx["iq"])),
                    encode_cycles=int(tx["cycles"]), decode_cycles=int(rx["cycles"]),
                    fpga_raw_coded_errors=raw_errors, fpga_decoded_bit_errors=decoded_errors,
                    independent_coded_errors=measured_raw_errors, encoder_matches_reference=coded_matches,
                    mapper_matches_reference=mapping_matches, llr_matches_reference=llr_matches_reference,
                    host_payload_errors=host_errors,
                    counters_verified=(raw_counter_matches and host_errors == decoded_errors)))


def validate(body):
    if not isinstance(body, dict):
        raise ValueError("Expected a JSON object")
    allowed = {"modulation", "snr_db", "cfo_hz", "timing_offset", "multipath", "seed", "payload_bits"}
    if set(body) - allowed:
        raise ValueError("Unknown simulation control")
    modulation = body.get("modulation", "64QAM")
    snr = body.get("snr_db", 18)
    cfo = body.get("cfo_hz", 1500)
    timing = body.get("timing_offset", .25)
    multipath = body.get("multipath", False)
    seed = body.get("seed", 7)
    bits = body.get("payload_bits", 2048)
    if modulation not in MODULATIONS:
        raise ValueError("Choose BPSK, QPSK, 16QAM or 64QAM")
    if type(snr) not in (float, int) or not 0 <= snr <= 40:
        raise ValueError("SNR must be from 0 to 40 dB")
    if type(cfo) not in (float, int) or not -12000 <= cfo <= 12000:
        raise ValueError("Carrier offset must be from -12000 to 12000 Hz")
    if type(timing) not in (float, int) or not 0 <= timing <= .9:
        raise ValueError("Timing offset must be from 0 to 0.9 samples")
    if type(multipath) is not bool:
        raise ValueError("Multipath must be true or false")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("Seed must be a nonnegative 32-bit integer")
    if type(bits) is not int or not 128 <= bits <= 20000:
        raise ValueError("Payload length must be from 128 to 20000 bits")
    if bits % 8:
        raise ValueError("Payload length must be byte-aligned (a multiple of 8 bits)")
    return dict(modulation=modulation, snr_db=float(snr), cfo_hz=float(cfo), timing_offset=float(timing),
                multipath=multipath, seed=seed, payload_bits=bits)


def simulate(body):
    settings = validate(body)
    from modem_reference import run_experiment

    result = run_experiment(**settings, decode_mode="soft", coded=True, sample_rate=4_000_000, sps=4)
    if not isinstance(result, dict) or not isinstance(result.get("metrics"), dict) or not isinstance(result.get("plots"), dict):
        raise RuntimeError("The modem reference returned an incomplete result")
    result["settings"] = settings | {"sample_rate": 4_000_000, "sps": 4, "coded": True}
    result["run_id"] = f"sim-{time.time_ns()}"
    result["frame_id"] = result.get("frame_id", settings["seed"])
    result["source"] = "Python simulation"
    result["evidence"] = "This run used a seeded software channel and known reference payload. It contains no FPGA image, radio capture or RF timestamp."
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "ModemLab/1.0"

    def send(self, code, content, kind):
        data = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlsplit(self.path).path == "/":
            self.send(200, (HERE / "modem_lab.html").read_text(), "text/html; charset=utf-8")
        elif urlsplit(self.path).path == "/api/fpga-status":
            self.send(200, json.dumps(fpga_status(getattr(self.server, "fpga_enabled", False))), "application/json")
        elif urlsplit(self.path).path == "/health":
            self.send(200, json.dumps({"status": "ready", "source": "Python simulation"}), "application/json")
        else:
            self.send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ("/api/run", "/api/fpga-test"):
            self.send(404, "Not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16_384:
                raise ValueError("Request body must be between 1 and 16384 bytes")
            body = json.loads(self.rfile.read(length))
            if route == "/api/run":
                result = simulate(body)
            else:
                if not getattr(self.server, "fpga_enabled", False):
                    self.send(403, json.dumps({"error": "Optional FPGA action is disabled; restart with --enable-fpga-action."}), "application/json")
                    return
                validate_fpga_request(body)
                with self.server.fpga_lock:
                    status = fpga_status(True)
                    if not status["ready"]:
                        self.send(409, json.dumps({"error": status["reason"], "status": status}), "application/json")
                        return
                    checkpoint = require_modem_checkpoint()
                    from nios_fir import NiosFir
                    with NiosFir(pause_monitor=False) as owner:
                        result = run_fpga_symbol_test(owner, body, checkpoint)
            self.send(200, json.dumps(result, allow_nan=False), "application/json")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send(400, json.dumps({"error": str(exc)}), "application/json")
        except RuntimeError as exc:
            self.send(409, json.dumps({"error": str(exc)}), "application/json")
        except Exception as exc:
            self.send(500, json.dumps({"error": f"Simulation failed: {exc}"}), "application/json")

    def log_message(self, fmt, *args):
        print("[modem-lab] " + fmt % args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address; use 0.0.0.0 to share on a reachable host")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--open", action="store_true", help="open the local page in a browser")
    parser.add_argument("--enable-fpga-action", action="store_true", help="expose a manual checkpoint-06 JTAG symbol loopback action; it still does not program or transmit RF")
    args = parser.parse_args()
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.fpga_enabled = args.enable_fpga_action
    server.fpga_lock = threading.Lock()
    url_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{url_host}:{args.port}/"
    print(f"Modem Lab: {url} · Python simulation is the default; FPGA action {'enabled for manual use' if args.enable_fpga_action else 'disabled'}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
