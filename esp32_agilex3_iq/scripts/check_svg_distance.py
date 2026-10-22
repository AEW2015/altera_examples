#!/usr/bin/env python3
"""Bounded paired-path distance search for the SVG graph/K7 modem.

This enumerates diverge/remerge events from the known zero state. It uses the
ideal unit-radius graph points (the fivefold symmetry lets p0 represent every
starting node), so these figures exclude FPGA coordinate quantization. A
finite depth is only a bounded search result, never a full free-distance proof.
No FPGA, RF, or hardware access occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import svg_modem  # noqa: E402


def _transition(state: int, bit: int) -> tuple[int, int]:
    node, memory = divmod(state, 64)
    next_memory, pair = svg_modem.branch(memory, bit)
    next_node = (node + int(svg_modem.DELTAS[pair])) % 5
    return next_node * 64 + next_memory, next_node


def bounded_search(max_depth: int) -> dict:
    if not 2 <= max_depth <= 64:
        raise ValueError("max-depth must be in 2..64")
    points = svg_modem.load_graph()

    # Force opposite first input bits to start a nonzero error event.
    s0, n0 = _transition(0, 0)
    s1, n1 = _transition(0, 1)
    first_cost = float(abs(points[n0] - points[n1]) ** 2)
    active: dict[tuple[int, int], tuple[float, tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = {
        (s0, s1): (first_cost, (0, 1), (n0,), (n1,))
    }
    events: list[dict] = []
    transitions_examined = 0

    # Each active entry is the minimum-cost path to this ordered pair of
    # encoder/graph states at this depth. Reaching equal states closes an
    # event and is never expanded further (first remergence convention).
    for depth in range(2, max_depth + 1):
        following: dict[tuple[int, int], tuple[float, tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = {}
        for (left_state, right_state), (cost, bits, left_nodes, right_nodes) in active.items():
            for left_bit in (0, 1):
                next_left, left_node = _transition(left_state, left_bit)
                for right_bit in (0, 1):
                    next_right, right_node = _transition(right_state, right_bit)
                    transitions_examined += 1
                    next_cost = cost + float(abs(points[left_node] - points[right_node]) ** 2)
                    next_bits = bits + (left_bit, right_bit)
                    next_left_nodes = left_nodes + (left_node,)
                    next_right_nodes = right_nodes + (right_node,)
                    if next_left == next_right:
                        events.append({
                            "length_symbols": depth,
                            "squared_euclidean_distance": next_cost,
                            "left_input_bits": list(next_bits[0::2]),
                            "right_input_bits": list(next_bits[1::2]),
                            "left_nodes": [0, *next_left_nodes],
                            "right_nodes": [0, *next_right_nodes],
                        })
                        continue
                    key = (next_left, next_right)
                    previous = following.get(key)
                    if previous is None or next_cost < previous[0]:
                        following[key] = (next_cost, next_bits,
                                          next_left_nodes, next_right_nodes)
        active = following
        if not active:
            break

    events.sort(key=lambda event: (event["squared_euclidean_distance"], event["length_symbols"]))
    best = events[0] if events else None
    return {
        "schema": "svg-bounded-distance-search-v1",
        "result_type": "bounded software enumeration",
        "simulation_only": True,
        "implemented_in_fpga": False,
        "rf_tested": False,
        "distance_model": "squared Euclidean distance between ideal unit-radius destination-node symbols",
        "coordinate_quantization": "none; ideal float vertices; p0 represents all rotations by graph symmetry",
        "encoder": "K=7 rate-1/2 convolutional, polynomials (171,133) octal, 64 memories, five graph nodes",
        "start_state": {"node": 0, "memory": 0},
        "forced_initial_divergence": "opposite first payload bits 0 and 1",
        "remergence_rule": "first time both complete node-and-memory states match",
        "max_search_depth_symbols": max_depth,
        "transition_pair_expansions": transitions_examined,
        "divergent_state_pairs_at_bound": len(active),
        "events_found": len(events),
        "best_event_within_bound": best,
        "minimum_squared_distance_within_bound": (
            best["squared_euclidean_distance"] if best is not None else None),
        "distance_is_full_free_distance": False,
        "bound_statement": (
            f"Search includes first-remerge events of length at most {max_depth} symbols; "
            "longer events and fixed-point quantization are not covered."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-depth", type=int, default=20,
                        help="maximum symbols in a first-remerge event (default: 20, range 2..64)")
    parser.add_argument("--output", type=Path,
                        help="optional JSON result path (otherwise print JSON)")
    args = parser.parse_args()
    try:
        result = bounded_search(args.max_depth)
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
        print(f"Saved bounded distance search to {args.output}")
        print(f"Best distance: {result['minimum_squared_distance_within_bound']} "
              f"within {args.max_depth} symbols; full free distance not established.")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
