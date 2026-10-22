"""Golden-vector checks for the portable native Wi-Fi packet contract."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "firmware/wifi64_tx/main/protocol.h"
PLAN = ROOT / "docs/NATIVE_WIFI_64QAM_OTA_PLAN.md"


def expected_frame(mac: bytes, run_id: int, packet_id: int, seed: int) -> bytes:
    """Encode the documented wire format independently of the C helper."""
    frame = bytearray(88)
    frame[0] = 0x08  # non-QoS data, no DS bits
    frame[4:10] = b"\xff" * 6
    frame[10:16] = mac
    frame[16:22] = mac
    sequence = packet_id & 0xFFF
    frame[22] = (sequence & 0xF) << 4
    frame[23] = sequence >> 4

    frame[24:28] = b"W64A"
    frame[28:32] = bytes((1, 54, 64, 0))
    frame[32:36] = run_id.to_bytes(4, "little")
    frame[36:40] = packet_id.to_bytes(4, "little")
    frame[40:44] = seed.to_bytes(4, "little")

    state = (seed ^ run_id ^ ((packet_id * 0x9E3779B9) & 0xFFFFFFFF)) & 0xFFFFFFFF
    if state == 0:
        state = 1
    for offset in range(44, 88):
        state ^= (state << 13) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        frame[offset] = state & 0xFF
    return bytes(frame)


HARNESS = r"""
#include <stdio.h>
#include "protocol.h"
int main(void) {
    const uint8_t mac[6] = {0x24, 0x6f, 0x28, 0x01, 0xab, 0xcd};
    const uint32_t cases[][3] = {
        {1, 0, 1}, {0x10203040u, 0x12345678u, 0x89abcdefu},
        {0xffffffffu, 0x1001u, 0u}
    };
    uint8_t frame[W64_FRAME];
    for (unsigned c = 0; c < sizeof(cases) / sizeof(cases[0]); ++c) {
        w64_frame(frame, mac, cases[c][0], cases[c][1], cases[c][2]);
        for (unsigned i = 0; i < sizeof(frame); ++i) printf("%02x", frame[i]);
        putchar('\n');
    }
    const unsigned configs[][4] = {
        {1, 8, 1, 2}, {11, 40, 16, 5}, {0, 8, 1, 2},
        {12, 8, 1, 2}, {1, 7, 1, 2}, {1, 41, 1, 2},
        {1, 8, 0, 2}, {1, 8, 17, 2}, {1, 8, 1, 1}, {1, 8, 1, 6}
    };
    for (unsigned c = 0; c < sizeof(configs) / sizeof(configs[0]); ++c)
        printf("%u", w64_valid_config(configs[c][0], configs[c][1],
                                     configs[c][2], configs[c][3]));
    putchar('\n');
}
"""


@unittest.skipUnless(shutil.which("cc"), "a C compiler is required for the C fixture")
class Wifi64PacketContractTests(unittest.TestCase):
    def test_c_frames_match_independent_golden_vectors_and_bounds(self) -> None:
        mac = bytes((0x24, 0x6F, 0x28, 0x01, 0xAB, 0xCD))
        cases = ((1, 0, 1), (0x10203040, 0x12345678, 0x89ABCDEF), (0xFFFFFFFF, 0x1001, 0))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "fixture.c"
            binary = temp / "fixture"
            source.write_text(HARNESS)
            subprocess.run(
                ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(HEADER.parent), str(source), "-o", str(binary)],
                check=True,
                capture_output=True,
                text=True,
            )
            output = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout.splitlines()

        frames = [bytes.fromhex(row) for row in output[:3]]
        self.assertEqual(frames, [expected_frame(mac, *case) for case in cases])
        self.assertEqual(len(frames[0]), 88)
        self.assertEqual(output[3], "1100000000")

    def test_maximum_config_fits_uart_line_and_matches_plan_bounds(self) -> None:
        command = "CONFIG 11 40 16 5 4294967295 4294967295"
        # Firmware accepts at most 95 command bytes before the NUL terminator.
        self.assertLessEqual(len(command), 95)
        source = HEADER.read_text()
        self.assertIn("#define W64_PAYLOAD 64", source)
        self.assertIn("#define W64_FRAME 88", source)
        main = (ROOT / "firmware/wifi64_tx/main/main.c").read_text()
        self.assertIn("char line[96]", main)
        self.assertRegex(main, r"deadline\s*=\s*esp_timer_get_time\(\)\s*\+\s*100000")
        self.assertRegex(main, r"arm_until\s*=\s*esp_timer_get_time\(\)\s*\+\s*5000000")
        self.assertRegex(main, r"next_start\s*=\s*esp_timer_get_time\(\)\s*\+\s*2000000")
        plan = PLAN.read_text()
        self.assertRegex(plan, r"at most 16 short packets per job, at least 2 ms between packets, a 100 ms")
        self.assertRegex(plan, r"at least 2 seconds between jobs")


if __name__ == "__main__":
    unittest.main()
