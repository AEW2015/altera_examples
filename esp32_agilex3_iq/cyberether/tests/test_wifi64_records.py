from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cyberether"))
from wifi64_records import LineAssembler, Wifi64MonitorJoiner, expected_packet_map, parse_monitor_record


def line(kind: str, packet: int = 0, **overrides: int) -> str:
    records = {
        "PACKET": {"run": 17, "packet": packet, "seed": 99, "body_ok": 1},
        "PHY": {"run": 17, "packet": packet, "rate_code": 12,
                "sig_mode": 0, "rx_state": 0, "rssi": -41, "ch": 8},
        "META": {"run": 17, "packet": packet, "timestamp_us": 1234,
                 "length": 92, "native_rx": 1},
    }
    values = records[kind] | overrides
    return "WIFI64_MON," + kind + "," + ",".join(f"{key}={value}" for key, value in values.items())


class Wifi64MonitorRecordTests(unittest.TestCase):
    def test_strict_parsing_rejects_missing_duplicate_unknown_and_bad_values(self):
        self.assertEqual(parse_monitor_record(line("PHY")).values["rssi"], -41)
        malformed = (
            "WIFI64_MON,PACKET,run=17,packet=0,seed=99",
            line("PHY") + ",ch=8",
            "WIFI64_MON,OTHER,run=17,packet=0",
            line("PACKET", body_ok=2),
            line("META", native_rx=0),
            line("PACKET", run=0x1_0000_0000),
        )
        for record in malformed:
            with self.subTest(record=record), self.assertRaises(ValueError):
                parse_monitor_record(record)

    def test_reassembles_newline_split_across_envelopes(self):
        assembler = LineAssembler()
        encoded = (line("PACKET") + "\r\n" + line("PHY") + "\n").encode("ascii")
        cut = encoded.index(b"body_ok") + 3
        self.assertEqual(assembler.feed(encoded[:cut]), [])
        result = assembler.feed(encoded[cut:])
        self.assertEqual(result, [line("PACKET"), line("PHY")])

    def test_out_of_order_join_requires_expected_identity_body_and_monitor_rate(self):
        joiner = Wifi64MonitorJoiner(expected_packet_map(17, 2, 99))
        for record in (line("META"), line("PHY"), line("PACKET")):
            joiner.feed(record)
        row = joiner.joined((17, 0))
        self.assertTrue(row["qualified"])
        self.assertTrue(row["rate54_monitor_match"])
        self.assertTrue(row["identity_match"])
        self.assertEqual(joiner.missing_packets(), {(17, 1)})
        # A TX callback count is deliberately absent from this monitor-only
        # interface and cannot qualify a packet without the independent PHY line.
        incomplete = Wifi64MonitorJoiner(expected_packet_map(17, 1, 99))
        incomplete.feed(line("PACKET"))
        self.assertIsNone(incomplete.joined((17, 0)))

    def test_duplicate_inconsistent_and_unexpected_observations_are_reported(self):
        joiner = Wifi64MonitorJoiner(expected_packet_map(17, 1, 99))
        for record in (line("PACKET"), line("PHY"), line("META"), line("PHY")):
            joiner.feed(record)
        row = joiner.joined((17, 0))
        self.assertFalse(row["qualified"])
        self.assertEqual(row["duplicates"], ["PHY"])

        wrong = Wifi64MonitorJoiner(expected_packet_map(17, 1, 98))
        for kind in ("PACKET", "PHY", "META"):
            wrong.feed(line(kind))
        self.assertFalse(wrong.joined((17, 0))["identity_match"])
        self.assertFalse(wrong.joined((17, 0))["qualified"])

        wrong_rate = Wifi64MonitorJoiner(expected_packet_map(17, 1, 99))
        for kind in ("PACKET", "PHY", "META"):
            wrong_rate.feed(line(kind, rate_code=11) if kind == "PHY" else line(kind))
        self.assertFalse(wrong_rate.joined((17, 0))["qualified"])

        rx_error = Wifi64MonitorJoiner(expected_packet_map(17, 1, 99))
        for kind in ("PACKET", "PHY", "META"):
            rx_error.feed(line(kind, rx_state=1) if kind == "PHY" else line(kind))
        self.assertEqual(rx_error.joined((17, 0))["rx_state"], 1)
        self.assertFalse(rx_error.joined((17, 0))["qualified"])

    def test_expected_indices_start_at_zero_and_are_bounded(self):
        self.assertEqual(list(expected_packet_map(17, 3, 99)), [(17, 0), (17, 1), (17, 2)])
        with self.assertRaises(ValueError):
            expected_packet_map(17, 17, 99)


if __name__ == "__main__":
    unittest.main()
