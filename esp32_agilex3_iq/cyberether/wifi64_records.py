"""Strict parser and joiner for WIFI64_MON observation text records."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

PREFIX = "WIFI64_MON,"
REQUIRED = {
    "PACKET": {"run", "packet", "seed", "body_ok"},
    "PHY": {"run", "packet", "rate_code", "sig_mode", "rx_state", "rssi", "ch"},
    "META": {"run", "packet", "timestamp_us", "length", "native_rx"},
}
IGNORED = {"READY", "INFO", "STATUS", "LISTEN", "STOP"}
U32_FIELDS = {"run", "packet", "seed", "timestamp_us", "length"}


@dataclass(frozen=True)
class MonitorRecord:
    kind: str
    run: int
    packet: int
    values: Mapping[str, int]

    @property
    def key(self) -> tuple[int, int]:
        return self.run, self.packet


def parse_monitor_record(line: str) -> MonitorRecord | None:
    """Parse one complete line; return None for monitor control records."""
    line = line.strip()
    if not line.startswith(PREFIX):
        raise ValueError("not a WIFI64_MON record")
    parts = line.split(",")
    kind = parts[1] if len(parts) > 1 else ""
    if kind in IGNORED:
        return None
    if kind not in REQUIRED:
        raise ValueError(f"unknown monitor record type {kind!r}")
    values: dict[str, int] = {}
    for part in parts[2:]:
        if part.count("=") != 1:
            raise ValueError(f"malformed field {part!r}")
        name, raw = part.split("=", 1)
        if name in values:
            raise ValueError(f"duplicate field {name!r}")
        if not raw or (raw[0] == "-" and not raw[1:].isdigit()) or (raw[0] != "-" and not raw.isdigit()):
            raise ValueError(f"non-decimal value for {name!r}")
        values[name] = int(raw, 10)
    expected = REQUIRED[kind]
    if set(values) != expected:
        raise ValueError(f"{kind} fields must be exactly {sorted(expected)}")
    for name in U32_FIELDS & expected:
        if not 0 <= values[name] <= 0xFFFFFFFF:
            raise ValueError(f"{name} outside u32 range")
    for name in expected - U32_FIELDS - {"rssi"}:
        if values[name] < 0:
            raise ValueError(f"{name} must be nonnegative")
    if kind == "PACKET" and values["body_ok"] not in (0, 1):
        raise ValueError("body_ok must be 0 or 1")
    if kind == "PHY" and not 1 <= values["ch"] <= 11:
        raise ValueError("monitor channel must be 1..11")
    if kind == "PHY" and not 0 <= values["rx_state"] <= 0xFF:
        raise ValueError("rx_state must be an unsigned byte")
    if kind == "META" and values["native_rx"] != 1:
        raise ValueError("native_rx must be 1")
    if kind == "META" and values["length"] < 92:
        raise ValueError("monitor frame length must include W64A and FCS (>=92)")
    return MonitorRecord(kind, values["run"], values["packet"], values)


@dataclass
class LineAssembler:
    """Reconstruct newline records from arbitrary per-radio UART text chunks."""
    max_line_bytes: int = 512
    _pending: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> list[str]:
        records: list[str] = []
        for byte in chunk:
            if byte == 10:
                line = bytes(self._pending).rstrip(b"\r")
                self._pending.clear()
                if line:
                    records.append(line.decode("ascii", errors="strict"))
            else:
                self._pending.append(byte)
                if len(self._pending) > self.max_line_bytes:
                    self._pending.clear()
                    raise ValueError("monitor text line exceeds configured limit")
        return records


@dataclass
class Wifi64MonitorJoiner:
    """Join PACKET/PHY/META in any order and audit expected packet identities.

    ``expected`` maps (run, packet) to the expected deterministic payload seed.
    Without this transmitter-side identity map, joined monitor reports are not
    marked as identity-qualified.
    """
    expected: Mapping[tuple[int, int], int] | None = None
    records: dict[tuple[int, int], dict[str, MonitorRecord]] = field(default_factory=dict)
    duplicates: dict[tuple[int, int], set[str]] = field(default_factory=dict)

    def feed(self, line: str) -> MonitorRecord | None:
        record = parse_monitor_record(line)
        if record is None:
            return None
        bucket = self.records.setdefault(record.key, {})
        if record.kind in bucket:
            self.duplicates.setdefault(record.key, set()).add(record.kind)
        else:
            bucket[record.kind] = record
        return record

    def missing_packets(self) -> set[tuple[int, int]]:
        if self.expected is None:
            return set()
        return {key for key in self.expected if "PACKET" not in self.records.get(key, {})}

    def incomplete(self) -> set[tuple[int, int]]:
        return {key for key, bucket in self.records.items() if set(bucket) != set(REQUIRED)}

    def joined(self, key: tuple[int, int]) -> dict | None:
        bucket = self.records.get(key, {})
        if set(bucket) != set(REQUIRED):
            return None
        packet, phy, meta = (bucket[k] for k in ("PACKET", "PHY", "META"))
        expected_seed = None if self.expected is None else self.expected.get(key)
        identity_match = expected_seed is not None and packet.values["seed"] == expected_seed
        duplicate_types = sorted(self.duplicates.get(key, set()))
        return {
            "run": key[0], "packet": key[1], "seed": packet.values["seed"],
            "identity_match": identity_match,
            "body_valid": packet.values["body_ok"] == 1,
            "rate_code": phy.values["rate_code"], "sig_mode": phy.values["sig_mode"],
            "rx_state": phy.values["rx_state"],
            "rssi": phy.values["rssi"], "channel": phy.values["ch"],
            "timestamp_us": meta.values["timestamp_us"], "length": meta.values["length"],
            "rate54_monitor_match": phy.values["rate_code"] == 12 and phy.values["sig_mode"] == 0,
            "qualified": bool(identity_match and packet.values["body_ok"] == 1 and
                               phy.values["rate_code"] == 12 and phy.values["sig_mode"] == 0 and
                               phy.values["rx_state"] == 0 and
                               not duplicate_types),
            "duplicates": duplicate_types,
        }

    def audit(self) -> dict:
        keys = set(self.records)
        complete = {key: row for key in keys if (row := self.joined(key)) is not None}
        expected = set(self.expected) if self.expected is not None else None
        return {
            "expected": sorted(expected) if expected is not None else None,
            "missing_packets": sorted(self.missing_packets()),
            "incomplete": sorted(self.incomplete()),
            "duplicates": {key: sorted(kinds) for key, kinds in sorted(self.duplicates.items())},
            "unexpected": sorted(keys - expected) if expected is not None else [],
            "joined": {key: row for key, row in sorted(complete.items())},
        }


def expected_packet_ids(run: int, count: int) -> Iterable[tuple[int, int]]:
    """Build the transmitter's per-job packet IDs (indices start at zero)."""
    if not 0 <= run <= 0xFFFFFFFF or not 1 <= count <= 16:
        raise ValueError("run must be u32 and count must be 1..16")
    return ((run, packet) for packet in range(count))


def expected_packet_map(run: int, count: int, seed: int) -> dict[tuple[int, int], int]:
    """Return expected (run, packet) to seed identities for a TX job."""
    if not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be u32")
    return {key: seed for key in expected_packet_ids(run, count)}
