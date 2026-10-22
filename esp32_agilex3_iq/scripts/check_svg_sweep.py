#!/usr/bin/env python3
"""Run a bounded Python-only AWGN sweep for the five-node SVG graph modem."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import svg_modem  # noqa: E402


def _zero_error_upper_95(denominator: int) -> float | None:
    """Exact one-sided 95% binomial upper bound when zero errors were seen."""
    if denominator <= 0:
        return None
    return 1.0 - 0.05 ** (1.0 / denominator)


def run_sweep(*, payload_bits: int, frame_bits: int, esn0_db: list[float],
              seed: int, mode: str, sps: int) -> dict:
    if payload_bits < 1:
        raise ValueError("payload_bits must be positive")
    if not 1 <= frame_bits <= 65536:
        raise ValueError("frame_bits must be in 1..65536")
    if not esn0_db or any(not math.isfinite(x) for x in esn0_db):
        raise ValueError("provide one or more finite Es/N0 values")
    if seed < 0:
        raise ValueError("seed must be nonnegative")
    if sps < 1:
        raise ValueError("sps must be positive")

    points = svg_modem.load_graph()
    graph_path = Path(svg_modem.GRAPH)
    graph_sha256 = hashlib.sha256(graph_path.read_bytes()).hexdigest()
    frame_count = (payload_bits + frame_bits - 1) // frame_bits
    symbol_denominator = payload_bits + 6 * frame_count
    effective_payload_rate = payload_bits / symbol_denominator

    # Reuse each deterministic payload chunk at every noise level. Separate
    # streams make the sweep reproducible without retaining all waveforms.
    payload_rng = np.random.default_rng(seed)
    noise_rngs = [np.random.default_rng(np.random.SeedSequence([seed, 0x535647, i]))
                  for i in range(len(esn0_db))]
    totals = [{
        "esn0_db": float(db),
        "ebn0_db": float(db - 10.0 * math.log10(effective_payload_rate)),
        "payload_bit_errors": 0,
        "payload_bit_denominator": 0,
        "joint_node_errors": 0,
        "joint_node_denominator": 0,
        "nearest_node_errors": 0,
        "nearest_node_denominator": 0,
        "frames_with_payload_errors": 0,
    } for db in esn0_db]

    bits_done = 0
    while bits_done < payload_bits:
        count = min(frame_bits, payload_bits - bits_done)
        bits = payload_rng.integers(0, 2, count, dtype=np.uint8)
        tx = svg_modem.encode(bits)
        tx_nodes = tx["node_path"][1:]
        tx_symbols = points[tx_nodes]
        waveform = svg_modem.shape_waveform(tx["node_path"], mode=mode,
                                             sps=sps, points=points)

        for index, db in enumerate(esn0_db):
            # The graph has unit symbol energy. Noise is circular complex AWGN;
            # Es/N0 = 1/(2*sigma^2). RX uses known ideal symbol boundaries.
            sigma = math.sqrt(0.5 * 10.0 ** (-float(db) / 10.0))
            rng = noise_rngs[index]
            noise = sigma * (rng.standard_normal(len(waveform)) +
                             1j * rng.standard_normal(len(waveform)))
            received_waveform = waveform + noise
            observations = received_waveform[sps - 1::sps]
            if len(observations) != len(tx_symbols):
                raise RuntimeError("waveform endpoint count does not match encoded symbols")

            nearest_nodes = np.argmin(np.abs(observations[:, None] - points[None, :]) ** 2,
                                      axis=1)
            decoded = svg_modem.decode(observations, payload_bits=count,
                                        points=points)
            bit_errors = int(np.count_nonzero(decoded["decoded_bits"] != bits))
            decoded_nodes = decoded["node_path"][1:]
            if len(decoded_nodes) != len(tx_nodes):
                raise RuntimeError("joint decoder node path length does not match frame")
            joint_node_errors = int(np.count_nonzero(decoded_nodes != tx_nodes))
            nearest_errors = int(np.count_nonzero(nearest_nodes != tx_nodes))

            row = totals[index]
            row["payload_bit_errors"] += bit_errors
            row["payload_bit_denominator"] += count
            row["joint_node_errors"] += joint_node_errors
            row["joint_node_denominator"] += len(tx_nodes)
            row["nearest_node_errors"] += nearest_errors
            row["nearest_node_denominator"] += len(tx_nodes)
            row["frames_with_payload_errors"] += int(bit_errors != 0)

        bits_done += count

    for row in totals:
        row["payload_ber"] = row["payload_bit_errors"] / row["payload_bit_denominator"]
        row["joint_node_error_rate"] = row["joint_node_errors"] / row["joint_node_denominator"]
        row["nearest_node_error_rate"] = row["nearest_node_errors"] / row["nearest_node_denominator"]
        row["frame_count"] = frame_count
        row["payload_frame_error_rate"] = row["frames_with_payload_errors"] / frame_count
        row["payload_frame_error_zero_upper_95_iid_frames"] = (
            _zero_error_upper_95(frame_count)
            if row["frames_with_payload_errors"] == 0 else None)
        row["payload_ber_zero_error_upper_95_iid_bits_only"] = (
            _zero_error_upper_95(row["payload_bit_denominator"])
            if row["payload_bit_errors"] == 0 else None)
        row["joint_node_zero_error_upper_95_iid_symbols_only"] = (
            _zero_error_upper_95(row["joint_node_denominator"])
            if row["joint_node_errors"] == 0 else None)
        row["nearest_node_zero_error_upper_95_iid_symbols_only"] = (
            _zero_error_upper_95(row["nearest_node_denominator"])
            if row["nearest_node_errors"] == 0 else None)

    return {
        "schema": "svg-graph-awgn-sweep-v1",
        "provenance": {
            "result_type": "Python simulation",
            "implemented_in_fpga": False,
            "rf_tested": False,
            "graph_sha256": graph_sha256,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
        "configuration": {
            "seed": seed,
            "payload_bits": payload_bits,
            "frame_bits": frame_bits,
            "frame_count": frame_count,
            "tail_bits_per_frame": 6,
            "coded_symbols_including_tails": symbol_denominator,
            "effective_payload_bits_per_symbol": effective_payload_rate,
            "esn0_db": [float(x) for x in esn0_db],
            "waveform_mode": mode,
            "samples_per_symbol": sps,
            "noise_model": "unit-energy symbols; independent circular complex AWGN per oversampled sample",
            "receiver_timing": "ideal known symbol boundaries; timing recovery is not modeled",
            "decoder": "joint 320-state graph/K7 Viterbi with six zero tail bits",
            "nearest_node_decisions": "memoryless Euclidean nearest point on sampled RX symbols",
            "nearest_node_bit_errors_reported": False,
            "error_rate_note": "Payload BER, joint-decoded node error rate, and nearest-node symbol error rate have distinct denominators; nearest-node decisions are not converted to a bit BER.",
            "confidence_note": (
                "Payload-bit and node-symbol zero-error bounds are labeled iid-only because errors can cluster within frames. "
                "The payload-frame zero-error bound uses frames as trials and assumes independent frames under the simulated "
                "independent payload/AWGN model; it is reported only when no frame had a payload error."
            ),
        },
        "results": totals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bits", type=int, default=100_000,
                        help="payload bits per Es/N0 point (default: 100000)")
    parser.add_argument("--frame-bits", type=int, default=256,
                        help="payload bits per terminated frame (default: 256)")
    parser.add_argument("--esn0-db", type=float, nargs="+", default=[0.0, 4.0, 7.0],
                        help="one or more symbol-energy to noise-density points")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--mode", choices=["arc", "linear", "hold"], default="arc")
    parser.add_argument("--sps", type=int, default=8)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "cyberether/run/svg-sweep.json")
    args = parser.parse_args()

    result = run_sweep(payload_bits=args.bits, frame_bits=args.frame_bits,
                       esn0_db=args.esn0_db, seed=args.seed,
                       mode=args.mode, sps=args.sps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Python simulation only; no FPGA or RF was used.")
    for row in result["results"]:
        print(f"Es/N0={row['esn0_db']:g} dB, Eb/N0={row['ebn0_db']:.3f} dB: "
              f"joint payload {row['payload_bit_errors']}/{row['payload_bit_denominator']}, "
              f"payload-error frames {row['frames_with_payload_errors']}/{row['frame_count']}, "
              f"joint node {row['joint_node_errors']}/{row['joint_node_denominator']}, "
              f"nearest node {row['nearest_node_errors']}/{row['nearest_node_denominator']}")
        if row["payload_frame_error_zero_upper_95_iid_frames"] is not None:
            print("  zero-error FER one-sided 95% bound "
                  f"(iid frames): <={row['payload_frame_error_zero_upper_95_iid_frames']:.6g}")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
