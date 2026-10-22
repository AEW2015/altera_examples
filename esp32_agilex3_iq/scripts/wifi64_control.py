#!/usr/bin/env python3
"""Explicit host control for the native ESP32 Wi-Fi 64-QAM packet transmitter.

This tool only sends commands and records firmware telemetry. It does not
generate packets/DSP results or start RF unless ``--transmit`` is supplied.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from pathlib import Path

from common import ROOT
sys.path.insert(0, str(ROOT / "cyberether"))
from iq_bridge import Bridge

LOCK = ROOT / "cyberether/run/rf-link-capture.lock"
REPLY = "WIFI64_TX,"


def fields(line: str) -> dict[str, str]:
    parts = line.split(",")
    result = {"record": parts[1]} if len(parts) > 1 else {}
    for part in parts[2:]:
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
    return result


def require_ok(line: str, record: str) -> dict[str, str]:
    if not line.startswith(REPLY):
        raise RuntimeError(f"Unexpected firmware reply: {line}")
    parsed = fields(line)
    if parsed.get("record") == "ERR":
        raise RuntimeError(f"Firmware rejected command: {line}")
    if parsed.get("record") != record:
        raise RuntimeError(f"Expected {record} reply, got: {line}")
    return parsed


def query(bridge: Bridge, command: str, expected: str, timeout: float = 4) -> str:
    return bridge.radio_command(1, command, REPLY + expected + ",", timeout=timeout)


def poll_idle(bridge: Bridge, timeout: float = 3) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = query(bridge, "STATUS", "STATUS", timeout=max(.2, deadline - time.monotonic()))
        state = fields(last)
        if state.get("busy") == "0" and state.get("rf") == "0" and state.get("stop_err") == "0":
            return last
        time.sleep(.05)
    raise TimeoutError(f"Transmitter did not reach verified idle state: {last}")


def validate_request(args: argparse.Namespace) -> None:
    if not 1 <= args.channel <= 11:
        raise ValueError("--channel must be 1..11")
    if not 8 <= args.power <= 40:
        raise ValueError("--power must be 8..40 quarter-dBm API units")
    if not 1 <= args.count <= 16:
        raise ValueError("--count must be 1..16")
    if not 2 <= args.gap <= 5:
        raise ValueError("--gap must be 2..5 ms")
    for name in ("run", "seed"):
        if not 0 <= getattr(args, name) <= 0xFFFFFFFF:
            raise ValueError(f"--{name} must fit u32")


def transmit(bridge: Bridge, args: argparse.Namespace) -> dict:
    proof: dict = {
        "kind": "native Wi-Fi 64-QAM transmitter control",
        "source": "ota-native-wifi64",
        "requested": {"channel": args.channel, "power_qdbm": args.power,
                      "count": args.count, "gap_ms": args.gap,
                      "run": args.run, "seed": args.seed},
        "radio": {},
        "completed": False,
        "processing": "FPGA bridge UART transport; firmware native Wi-Fi PHY; no host DSP",
        "rate54_callback_is_receiver_proof": False,
    }

    def run() -> None:
        info_line = query(bridge, "INFO", "INFO")
        proof["radio"]["identity"] = require_ok(info_line, "INFO")
        proof["radio"]["info_line"] = info_line
        proof["radio"]["identity_line"] = bridge.wait_text(1, REPLY + "IDENT,", 1)
        proof["radio"]["initial_status_line"] = bridge.wait_text(1, REPLY + "STATUS,", 1)
        # INFO emits the standard status block as three lines.
        proof["radio"]["initial_submitted_line"] = bridge.wait_text(1, REPLY + "SUBMITTED,", 1)
        proof["radio"]["initial_counters_line"] = bridge.wait_text(1, REPLY + "COUNTERS,", 1)
        config_line = query(bridge, "CONFIG?", "CONFIG")
        proof["radio"]["initial_config_line"] = config_line
        config_command = (f"CONFIG {args.channel} {args.power} {args.count} "
                          f"{args.gap} {args.run} {args.seed}")
        configured = query(bridge, config_command, "CONFIG")
        require_ok(configured, "CONFIG")
        readback = query(bridge, "CONFIG?", "CONFIG")
        proof["radio"]["config_command"] = config_command
        proof["radio"]["config_readback_line"] = readback
        expected = {"ch": str(args.channel), "power_qdbm": str(args.power),
                    "count": str(args.count), "gap_ms": str(args.gap),
                    "run": str(args.run), "seed": str(args.seed)}
        actual = fields(readback)
        if any(actual.get(k) != v for k, v in expected.items()):
            raise RuntimeError(f"CONFIG readback mismatch: expected {expected}, got {actual}")

        arm = query(bridge, "ARM", "ARM")
        arm_fields = require_ok(arm, "ARM")
        if arm_fields.get("ch") != str(args.channel) or arm_fields.get("power_qdbm") != str(args.power):
            raise RuntimeError(f"ARM readback mismatch: {arm}")
        proof["radio"]["arm_line"] = arm
        started = query(bridge, "START", "START")
        proof["radio"]["start_line"] = started
        require_ok(started, "START")
        job = fields(started).get("job")
        deadline = time.monotonic() + 3.0
        done_line = ""
        while time.monotonic() < deadline:
            done_line = bridge.wait_text(1, REPLY + "DONE,", max(.1, deadline - time.monotonic()))
            if fields(done_line).get("job") == job:
                break
        else:
            raise TimeoutError(f"No matching DONE event for job {job}")
        proof["radio"]["done_line"] = done_line
        require_ok(done_line, "DONE")

    try:
        run()
    except Exception as exc:
        proof["error"] = str(exc)
    # Even a command/readback failure after connecting leads to explicit STOP
    # and a separately queried idle state; retain whatever evidence succeeded.
    try:
        proof["radio"]["stop_line"] = query(bridge, "STOP", "STOP")
        require_ok(proof["radio"]["stop_line"], "STOP")
        proof["radio"]["submitted_line"] = bridge.wait_text(1, REPLY + "SUBMITTED,", .5)
        proof["radio"]["counters_line"] = bridge.wait_text(1, REPLY + "COUNTERS,", .5)
        proof["radio"]["idle_status_line"] = poll_idle(bridge)
        idle = fields(proof["radio"]["idle_status_line"])
        proof["radio"]["idle_verified"] = all(
            idle.get(key) == value for key, value in
            (("busy", "0"), ("rf", "0"), ("stop_err", "0")))
    except Exception as exc:
        proof["radio"]["stop_or_idle_error"] = str(exc)
    proof["callback_counters"] = proof["radio"].get("counters_line")
    proof["completed"] = bool(proof["radio"].get("done_line") and
                               proof["radio"].get("idle_verified") and
                               "error" not in proof and
                               "stop_or_idle_error" not in proof["radio"])
    # A completed/idle command job may have submitted no RF successfully.
    # Retain that lifecycle evidence separately from native TX telemetry success.
    proof["job_completed"] = proof["completed"]
    proof["tx_success"] = False
    try:
        submitted = fields(proof["radio"]["submitted_line"])
        callbacks = fields(proof["radio"]["counters_line"])
        names = {"accepted": submitted["accepted"], "rejected": submitted["rejected"],
                 **{key: callbacks[key] for key in ("done", "failed", "rate54", "other")}}
        if any(not value.isdecimal() for value in names.values()):
            raise ValueError("TX counters must be unsigned decimal integers")
        counters = {key: int(value) for key, value in names.items()}
        if any(value > 16 for value in counters.values()):
            raise ValueError("TX job counters exceed bounded job limit")
        proof["tx_counters"] = counters
        expected = {"accepted": args.count, "rejected": 0, "done": args.count,
                    "failed": 0, "rate54": args.count, "other": 0}
        proof["tx_success"] = bool(proof["completed"] and counters == expected)
    except (KeyError, ValueError, AttributeError) as exc:
        proof["counter_validation_error"] = str(exc)
    return proof


def write_proof(path: Path, proof: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--info", action="store_true", help="query INFO")
    actions.add_argument("--status", action="store_true", help="query STATUS")
    actions.add_argument("--config-query", action="store_true", help="query CONFIG?")
    actions.add_argument("--stop", action="store_true", help="send STOP and verify idle")
    actions.add_argument("--transmit", action="store_true", help="explicitly run a bounded RF packet job")
    parser.add_argument("--port", help="FPGA bridge serial port")
    parser.add_argument("--channel", type=int, default=8)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--power", type=int, default=8, help="quarter-dBm Wi-Fi API code")
    parser.add_argument("--gap", type=int, default=2, help="inter-packet gap in ms")
    parser.add_argument("--run", type=lambda x: int(x, 0), default=1)
    parser.add_argument("--seed", type=lambda x: int(x, 0), default=1)
    parser.add_argument("--output", type=Path, help="new JSON proof file; never overwritten")
    args = parser.parse_args(argv)
    if args.transmit and not args.output:
        parser.error("--transmit requires --output for retained proof")
    if args.output and not args.transmit:
        parser.error("--output is supported for --transmit only")
    if args.transmit:
        try:
            validate_request(args)
        except ValueError as exc:
            parser.error(str(exc))

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOCK.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with Bridge(args.port) as bridge:
                bridge.control(2, 1, 2_000_000)
                if args.info:
                    print(query(bridge, "INFO", "INFO"))
                elif args.status:
                    print(query(bridge, "STATUS", "STATUS"))
                elif args.config_query:
                    print(query(bridge, "CONFIG?", "CONFIG"))
                elif args.stop:
                    print(query(bridge, "STOP", "STOP"))
                    print(poll_idle(bridge))
                else:
                    proof = transmit(bridge, args)
                    write_proof(args.output, proof)
                    print(json.dumps(proof, indent=2))
                    if not proof["tx_success"]:
                        return 2
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"wifi64_control: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
