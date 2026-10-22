#!/usr/bin/env python3
"""Explicit JTAG/Avalon captures from the standalone SVG modem FPGA image.

This command never builds or programs the FPGA and never opens an RF/serial port.
Hardware is accessed only when the explicit ``capture`` or ``sweep`` subcommand
is run; ``--help`` and argument validation are offline.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import altera_root, tool_command, tool_env, tool_path  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import svg_modem  # noqa: E402

STAGE = ROOT / "fpga_hub/iq_bridge/svg_modem"
TCL_SCRIPT = ROOT / "scripts/svg_fpga_capture.tcl"
RUN = ROOT / "cyberether/run"
FPGA_ID = 0x53564701
MAX_FRAME_BITS = 256
TAIL_BITS = 6
SAMPLES_PER_EDGE = 16


def _int(text: str) -> int:
    return int(text, 0)


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _unpack_iq(word: int) -> tuple[int, int]:
    return _signed16(word), _signed16(word >> 16)


def _xy(words: list[int]) -> list[list[float]]:
    return [[i / 8192.0, q / 8192.0] for i, q in (_unpack_iq(x) for x in words)]


def _acquire_owners():
    """Hold both shared acquisition leases across the SystemConsole process."""
    RUN.mkdir(parents=True, exist_ok=True)
    stack = ExitStack()
    for name in ("rf-link-capture.lock", "nios-fir.lock"):
        path = RUN / name
        lease = stack.enter_context(path.open("a"))
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            stack.close()
            raise RuntimeError(f"Hardware owner is busy ({name}); stop the active capture/monitor first") from exc
    return stack


def _parse_transcript(text: str) -> dict:
    frames: list[dict] = []
    configurations: dict[int, dict] = {}
    vectors: dict[int, dict] = {}
    device = None
    cable = None
    active_vector: int | None = None
    for line in text.splitlines():
        if not line.startswith(("CABLE\t", "IDENTITY\t", "CONFIG\t", "FRAME\t",
                                "VECTOR_BEGIN\t", "SYMBOL\t", "WAVE\t", "VECTOR_END\t")):
            if line.startswith("SVG_ERROR\t"):
                raise RuntimeError(line.partition("\t")[2])
            continue
        fields = line.split("\t")
        kind = fields[0]
        if kind == "CABLE" and len(fields) == 2:
            cable = fields[1]
        elif kind == "IDENTITY" and len(fields) == 4:
            device = {"id": _int(fields[1]), "decoder_states": _int(fields[2]),
                      "samples_per_edge": _int(fields[3])}
        elif kind == "CONFIG" and len(fields) == 6:
            index = _int(fields[1])
            configurations[index] = {"payload_count": _int(fields[2]),
                                     "noise_amplitude": _int(fields[3]),
                                     "seed": _int(fields[4]), "arc_mode": _int(fields[5])}
        elif kind == "FRAME" and len(fields) == 14:
            frames.append({"frame_index": _int(fields[1]), "payload_count": _int(fields[2]),
                           "seed": _int(fields[3]), "noise_amplitude": _int(fields[4]),
                           "arc_mode": _int(fields[5]), "status": _int(fields[6]),
                           "cycles": _int(fields[7]), "symbol_errors": _int(fields[8]),
                           "payload_errors": _int(fields[9]), "symbol_count": _int(fields[10]),
                           "wave_count": _int(fields[11]),
                           "final_metric": ((_int(fields[12]) & 0xFFFF) << 32) |
                                            (_int(fields[13]) & 0xFFFFFFFF)})
        elif kind == "VECTOR_BEGIN" and len(fields) == 2:
            active_vector = _int(fields[1])
            vectors[active_vector] = {"symbols": [], "wave": []}
        elif kind == "SYMBOL" and len(fields) == 8 and active_vector is not None:
            vectors[active_vector]["symbols"].append({
                "index": _int(fields[1]), "tx_word": _int(fields[2]),
                "rx_word": _int(fields[3]),
                "source_bit": None if fields[4] == "-" else _int(fields[4]),
                "decoded_bit": None if fields[5] == "-" else _int(fields[5]),
                "tx_node": _int(fields[6]), "rx_node": _int(fields[7]),
            })
        elif kind == "WAVE" and len(fields) == 4 and active_vector is not None:
            vectors[active_vector]["wave"].append({
                "index": _int(fields[1]), "tx_word": _int(fields[2]),
                "rx_word": _int(fields[3]),
            })
        elif kind == "VECTOR_END" and len(fields) == 2:
            active_vector = None

    if device is None or device["id"] != FPGA_ID:
        raise RuntimeError("SystemConsole transcript lacks the expected FPGA design identity")
    if not frames or len(configurations) != len(frames):
        raise RuntimeError("SystemConsole transcript is missing frame configuration/status rows")
    for row in frames:
        expected = configurations.get(row["frame_index"])
        if expected is None:
            raise RuntimeError("missing configuration readback for frame")
        for key in ("payload_count", "noise_amplitude", "seed", "arc_mode"):
            if row[key] != expected[key]:
                raise RuntimeError(f"configuration readback did not match frame {row['frame_index']} ({key})")
        if not (row["status"] & 2) or (row["status"] & 5):
            raise RuntimeError(f"FPGA status did not finish cleanly for frame {row['frame_index']}")
        if row["symbol_count"] != row["payload_count"] + TAIL_BITS:
            raise RuntimeError("FPGA symbol count does not include exactly six tail symbols")
        if row["wave_count"] != row["symbol_count"] * SAMPLES_PER_EDGE:
            raise RuntimeError("FPGA waveform count does not match 16 samples per edge")
    if active_vector is not None:
        raise RuntimeError("truncated vector section in SystemConsole transcript")
    return {"device": device, "cable": cable, "frames": frames,
            "configurations": configurations, "vectors": vectors}


def _node_pairs(nodes: list[int]) -> list[int]:
    delta_to_pair = {1: 0, 2: 1, 4: 2, 3: 3}
    return [delta_to_pair[(b - a) % 5] for a, b in zip(nodes[:-1], nodes[1:])]


def _frame_json(frame: dict, raw: dict, points) -> dict:
    expected_symbols = frame["symbol_count"]
    if len(raw["symbols"]) != expected_symbols or len(raw["wave"]) != frame["wave_count"]:
        raise RuntimeError(f"incomplete vector readback for frame {frame['frame_index']}")
    symbol_rows = raw["symbols"]
    wave_rows = raw["wave"]
    if any(row["index"] != index for index, row in enumerate(symbol_rows)) or \
       any(row["index"] != index for index, row in enumerate(wave_rows)):
        raise RuntimeError("FPGA vector readback contains missing, duplicated, or reordered indices")
    payload_bits = [int(row["source_bit"]) for row in symbol_rows[:frame["payload_count"]]]
    decoded_bits = [int(row["decoded_bit"]) for row in symbol_rows[:frame["payload_count"]]]
    if any(bit not in (0, 1) for bit in payload_bits + decoded_bits):
        raise RuntimeError("payload bit register returned an invalid value")
    if sum(a != b for a, b in zip(payload_bits, decoded_bits)) != frame["payload_errors"]:
        raise RuntimeError("FPGA payload error counter differs from source/decoded bit readback")

    tx_nodes = [int(row["tx_node"]) for row in symbol_rows]
    rx_nodes = [int(row["rx_node"]) for row in symbol_rows]
    tx_words = [int(row["tx_word"]) for row in symbol_rows]
    rx_words = [int(row["rx_word"]) for row in symbol_rows]
    tx_symbols = _xy(tx_words)
    rx_symbols = _xy(rx_words)
    tx_wave = _xy([int(row["tx_word"]) for row in wave_rows])
    rx_wave = _xy([int(row["rx_word"]) for row in wave_rows])

    complex_points = points
    rx_complex = [complex(x, y) for x, y in rx_symbols]
    nearest_nodes = [int(min(range(5), key=lambda n: abs(y - complex_points[n]) ** 2))
                     for y in rx_complex]
    nearest_errors = sum(a != b for a, b in zip(nearest_nodes, tx_nodes))
    if nearest_errors != frame["symbol_errors"]:
        raise RuntimeError("FPGA nearest-node error counter differs from readback symbol audit")
    decoded_node_errors = sum(a != b for a, b in zip(rx_nodes, tx_nodes))
    payload_count = frame["payload_count"]
    effective_rate = payload_count / expected_symbols
    decoded_path = [0] + rx_nodes
    tx_path = [0] + tx_nodes

    return {
        "schema": "svg-modem-simulation-v1",
        "simulation_only": False,
        "implemented_in_fpga": True,
        "rf_tested": False,
        "receiver_timing": "FPGA edge-end strobe; no recovered unknown timing",
        "noise_model": "FPGA seeded bounded-uniform signed I/Q noise per oversample, with CI16 saturation; not AWGN",
        "decoder_input": "FPGA waveform samples at each edge-end strobe",
        "seed": frame["seed"],
        "noise_amplitude": frame["noise_amplitude"],
        "noise_type": "seeded bounded-uniform hardware noise",
        "mode": "arc" if frame["arc_mode"] else "linear",
        "snr_db": None,
        "es_n0_db": None,
        "eb_n0_db": None,
        "effective_payload_bits_per_symbol": effective_rate,
        "payload_bits": payload_bits,
        "constellation": [[float(p.real), float(p.imag)] for p in complex_points],
        "graph_sha256": hashlib.sha256(svg_modem.GRAPH.read_bytes()).hexdigest(),
        "hardware": {"fpga_id": frame.get("fpga_id", FPGA_ID),
                     "cable_path": frame.get("cable_path"),
                     "cycles": frame["cycles"], "decoder_states": 320,
                     "payload_count_readback": payload_count,
                     "noise_amplitude_readback": frame["noise_amplitude"],
                     "seed_readback": frame["seed"],
                     "mode_readback": frame["arc_mode"],
                     "final_metric": frame["final_metric"]},
        "code": {"polynomials_octal": ["171", "133"], "states": 320,
                 "start_node": 0, "start_memory": 0, "tail_bits": TAIL_BITS,
                 "branch_metric": "integer squared Euclidean distance; 48-bit accumulated metric"},
        "tx": {"node_path": tx_path, "coded_pairs": _node_pairs(tx_path),
               "symbols": tx_symbols, "origin": "FPGA endpoint buffer readback",
               "coded_pairs_origin": "derived from FPGA node transitions"},
        "rx": {"symbols": rx_symbols, "nearest_nodes": nearest_nodes,
               "decoded_bits": decoded_bits,
               "decoded_node_path": decoded_path,
               "hard_symbol_errors": frame["symbol_errors"],
               "symbol_count": expected_symbols,
               "hard_symbol_error_rate": frame["symbol_errors"] / expected_symbols,
               "decoded_bit_errors": frame["payload_errors"],
               "payload_bit_count": payload_count,
               "post_fec_ber": frame["payload_errors"] / payload_count,
               "decoded_symbol_errors": decoded_node_errors,
               "nearest_node_bit_errors_reported": False,
               "note": "FPGA counters report nearest-node symbol errors and joint-decoder payload bit errors with different denominators; nearest-node decisions are not converted into a pre-FEC bit BER."},
        "waveform": {"sps": SAMPLES_PER_EDGE,
                     "mode": "arc" if frame["arc_mode"] else "linear",
                     "tx_samples": tx_wave, "rx_samples": rx_wave,
                     "sample_symbol_indices": [i for i in range(expected_symbols)
                                               for _ in range(SAMPLES_PER_EDGE)],
                     "origin": "FPGA waveform RAM readback"},
    }


def _run_system_console(*, payload_counts: list[int], seed: int,
                        noise_amplitude: int, mode: str, timeout: int,
                        summary_only: bool, capture_all_vectors: bool,
                        cable_regex: str) -> dict:
    exe = altera_root() / "syscon/bin/system-console"
    if not exe.is_file():
        raise RuntimeError(f"SystemConsole was not found at {exe}; select the installed Quartus tools environment")
    # --cli takes precedence over --script in Quartus 26.1 and skips the script.
    args = [str(exe), "--script=" + tool_path(TCL_SCRIPT),
            ",".join(str(x) for x in payload_counts), str(seed),
            str(noise_amplitude), "1" if mode == "arc" else "0", str(timeout),
            "1" if summary_only else "0", cable_regex,
            "1" if capture_all_vectors else "0"]
    run = _acquire_owners()
    try:
        with run:
            max_wait = max(180, (timeout + 15) * len(payload_counts) + 120)
            process = subprocess.run(tool_command(args, cwd=ROOT), cwd=ROOT,
                                     env=tool_env(), text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=max_wait, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("SystemConsole process exceeded its bounded timeout") from exc
    if process.returncode:
        detail = process.stdout[-5000:]
        raise RuntimeError(f"SystemConsole capture failed (exit {process.returncode}):\n{detail}")
    return _parse_transcript(process.stdout)


def _payload_counts(total: int, frame_bits: int) -> list[int]:
    if total < 1:
        raise ValueError("payload bits must be positive")
    if not 1 <= frame_bits <= MAX_FRAME_BITS:
        raise ValueError("frame bits must be in 1..256")
    counts = []
    remaining = total
    while remaining:
        count = min(frame_bits, remaining)
        counts.append(count)
        remaining -= count
    return counts


def capture(*, payload_counts: list[int], seed: int, noise_amplitude: int,
            mode: str, timeout: int, summary_only: bool,
            capture_all_vectors: bool, cable_regex: str) -> dict:
    if not payload_counts or any(not 1 <= n <= MAX_FRAME_BITS for n in payload_counts):
        raise ValueError("one or more payload counts in 1..256 are required")
    if not 1 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be in 1..0xffffffff")
    if not 0 <= noise_amplitude <= 30000:
        raise ValueError("noise amplitude must be in 0..30000")
    if mode not in ("arc", "linear"):
        raise ValueError("mode must be arc or linear")
    if timeout < 1:
        raise ValueError("timeout must be positive")

    parsed = _run_system_console(payload_counts=payload_counts, seed=seed,
                                 noise_amplitude=noise_amplitude, mode=mode,
                                 timeout=timeout, summary_only=summary_only,
                                 capture_all_vectors=capture_all_vectors,
                                 cable_regex=cable_regex)
    expected_frames = len(payload_counts)
    if len(parsed["frames"]) != expected_frames:
        raise RuntimeError("FPGA returned a different number of frames than requested")
    for index, row in enumerate(parsed["frames"]):
        row["fpga_id"] = parsed["device"]["id"]
        row["cable_path"] = parsed["cable"]
        expected_seed = (seed + index) & 0xFFFFFFFF
        if expected_seed == 0:
            expected_seed = 1
        if row["payload_count"] != payload_counts[index] or row["seed"] != expected_seed:
            raise RuntimeError(f"FPGA configuration did not match requested frame {index}")

    ideal = svg_modem.load_graph()
    points = (np.rint(ideal.real * 8192) + 1j * np.rint(ideal.imag * 8192)) / 8192
    final_frame = parsed["frames"][-1]
    final_vectors = parsed["vectors"].get(final_frame["frame_index"])
    if final_vectors is None:
        raise RuntimeError("FPGA did not return the requested final frame vectors")
    result = _frame_json(final_frame, final_vectors, points)
    result["cable_path"] = parsed["cable"]
    result["hardware"]["fpga_id"] = parsed["device"]["id"]
    result["hardware"]["decoder_states"] = parsed["device"]["decoder_states"]
    result["hardware"]["samples_per_edge"] = parsed["device"]["samples_per_edge"]
    result["capture"] = {"frame_count": len(parsed["frames"]),
                         "payload_bit_count_total": sum(x["payload_count"] for x in parsed["frames"]),
                         "summary_only": summary_only,
                         "vectors_read_for_final_frame": True,
                         "vectors_read_for_every_frame": capture_all_vectors and not summary_only}
    result["sweep_frames"] = [{k: row[k] for k in (
        "frame_index", "payload_count", "seed", "noise_amplitude", "arc_mode",
        "status", "cycles", "symbol_errors", "payload_errors", "symbol_count",
        "wave_count", "final_metric")} for row in parsed["frames"]]
    total_payload = sum(row["payload_count"] for row in parsed["frames"])
    total_symbols = sum(row["symbol_count"] for row in parsed["frames"])
    total_payload_errors = sum(row["payload_errors"] for row in parsed["frames"])
    total_symbol_errors = sum(row["symbol_errors"] for row in parsed["frames"])
    result["sweep_summary"] = {
        "origin": "aggregated host-side from per-frame FPGA counters",
        "payload_bit_errors": total_payload_errors,
        "payload_bit_denominator": total_payload,
        "post_fec_ber": total_payload_errors / total_payload,
        "effective_payload_bits_per_symbol": total_payload / total_symbols,
        "nearest_node_symbol_errors": total_symbol_errors,
        "nearest_node_symbol_denominator": total_symbols,
        "nearest_node_symbol_error_rate": total_symbol_errors / total_symbols,
        "frames_with_payload_errors": sum(row["payload_errors"] != 0 for row in parsed["frames"]),
        "nearest_node_bit_errors_reported": False,
    }
    if capture_all_vectors and not summary_only:
        extra = []
        for frame in parsed["frames"][:-1]:
            raw = parsed["vectors"].get(frame["frame_index"])
            if raw is None:
                raise RuntimeError(f"missing vector readback for frame {frame['frame_index']}")
            extra.append(_frame_json(frame, raw, points))
        result["intermediate_frame_captures"] = extra
    result["provenance"] = {"result_type": "FPGA internal capture",
                            "simulation_only": False, "implemented_in_fpga": True,
                            "rf_tested": False, "design_id": parsed["device"]["id"],
                            "cable_path": parsed["cable"],
                            "graph_sha256": result["graph_sha256"],
                            "noise_distribution": "seeded bounded-uniform",
                            "rf": "not used"}
    result["captured_unix"] = time.time()
    active = RUN / "active-fpga.json"
    if active.exists():
        record = json.loads(active.read_text())
        if record.get("stage_relative") == str(STAGE.relative_to(ROOT)):
            result["hardware"]["image_sha256"] = record.get("sha256")
            result["hardware"]["source_fingerprint"] = record.get("source_fingerprint")
            result["hardware"]["image_identity_origin"] = "host programming record; not a device hash readback"
    return result


def _add_common_capture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=_int, default=7,
                        help="nonzero 32-bit FPGA payload/noise seed (default: 7)")
    parser.add_argument("--noise-amplitude", "--noise", type=int, default=6000,
                        help="bounded uniform signed I/Q noise amplitude, 0..30000 (default: 6000)")
    parser.add_argument("--mode", choices=("arc", "linear"), default="arc",
                        help="arc mode phase-sweeps adjacent ring edges; star edges remain linear")
    parser.add_argument("--timeout", type=int, default=30,
                        help="per-frame FPGA completion timeout in seconds")
    parser.add_argument("--cable-regex", default=None,
                        help="exactly one SystemConsole master path must match; default Atum A3 Nano or SVG_FPGA_CABLE_REGEX")
    parser.add_argument("--output", type=Path, default=RUN / "svg-constellation-result.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    one = subparsers.add_parser("capture", help="run one explicitly requested FPGA frame")
    one.add_argument("--bits", type=int, default=256,
                     help="payload bits, 1..256 (default: 256)")
    _add_common_capture_options(one)
    sweep = subparsers.add_parser("sweep", help="run bounded independent FPGA frames for a larger payload count")
    sweep.add_argument("--bits", type=int, default=100_000,
                       help="total payload bits across frames (default: 100000)")
    sweep.add_argument("--frame-bits", type=int, default=256,
                       help="payload bits per terminated FPGA frame, 1..256")
    sweep_modes = sweep.add_mutually_exclusive_group()
    sweep_modes.add_argument("--summary-only", dest="summary_only", action="store_true",
                             help="read counters for every frame and vectors only for the final frame (default)")
    sweep_modes.add_argument("--all-vectors", dest="summary_only", action="store_false",
                             help="also read all vectors from every frame; very large and slow for long sweeps")
    sweep.set_defaults(summary_only=True)
    _add_common_capture_options(sweep)
    args = parser.parse_args()

    if args.cable_regex is None:
        args.cable_regex = os.environ.get("SVG_FPGA_CABLE_REGEX", "Atum A3 Nano")
    if args.command == "capture":
        if not 1 <= args.bits <= MAX_FRAME_BITS:
            parser.error("capture --bits must be in 1..256")
        counts = [args.bits]
        summary_only = False
        capture_all = False
    else:
        try:
            counts = _payload_counts(args.bits, args.frame_bits)
        except ValueError as exc:
            parser.error(str(exc))
        summary_only = args.summary_only
        capture_all = not summary_only

    result = capture(payload_counts=counts, seed=args.seed,
                     noise_amplitude=args.noise_amplitude, mode=args.mode,
                     timeout=args.timeout, summary_only=summary_only,
                     capture_all_vectors=capture_all,
                     cable_regex=args.cable_regex)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(args.output)
    final = result["rx"]
    print("FPGA internal capture; no RF used. Noise is bounded uniform, not AWGN.")
    print(f"Final frame: {final['hard_symbol_errors']}/{final['symbol_count']} nearest-node symbol errors; "
          f"{final['decoded_bit_errors']}/{final['payload_bit_count']} joint-decoder payload errors.")
    print(f"Captured FPGA ID 0x{result['hardware']['fpga_id']:08x}; saved {args.output}")


if __name__ == "__main__":
    main()
