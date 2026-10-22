from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import wifi64_control as control


class FakeBridge:
    instances = []

    def __init__(self, port=None):
        self.port_arg = port
        self.calls = []
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def control(self, opcode, source, value):
        self.calls.append(("control", opcode, source, value))

    def radio_command(self, source, command, prefix=None, timeout=4):
        self.calls.append(("radio", source, command, prefix))
        if command == "INFO":
            return "WIFI64_TX,INFO,version=1,chip=esp32,phy=native11g,rate=54,uart=2000000"
        if command == "STATUS":
            return "WIFI64_TX,STATUS,job=1,busy=0,armed=0,rf=0,stop_err=0"
        if command == "CONFIG?":
            return "WIFI64_TX,CONFIG,ch=8,power_qdbm=8,count=2,gap_ms=2,run=7,seed=9"
        if command.startswith("CONFIG "):
            return "WIFI64_TX,CONFIG,ok=1"
        if command == "ARM":
            return "WIFI64_TX,ARM,ok=1,ch=8,power_qdbm=8,expires_ms=5000"
        if command == "START":
            return "WIFI64_TX,START,job=1,deadline_ms=100"
        if command == "STOP":
            return "WIFI64_TX,STOP,job=1,busy=0,armed=0,rf=0,stop_err=0"
        raise AssertionError(command)

    def wait_text(self, source, prefix, timeout=4):
        self.calls.append(("wait", source, prefix))
        if prefix == "WIFI64_TX,IDENT,":
            return "WIFI64_TX,IDENT,mac=24:6f:28:01:ab:cd,frame_bytes=88"
        if prefix == "WIFI64_TX,STATUS,":
            return "WIFI64_TX,STATUS,job=0,busy=0,armed=0,rf=0,stop_err=0"
        if prefix == "WIFI64_TX,SUBMITTED,":
            return "WIFI64_TX,SUBMITTED,accepted=2,rejected=0"
        if prefix == "WIFI64_TX,COUNTERS,":
            return "WIFI64_TX,COUNTERS,done=2,failed=0,rate54=2,other=0"
        if prefix == "WIFI64_TX,DONE,":
            return "WIFI64_TX,DONE,job=1,busy=0,armed=0,rf=0,stop_err=0"
        raise AssertionError(prefix)


class Wifi64ControlTests(unittest.TestCase):
    def setUp(self):
        FakeBridge.instances.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lock = Path(self.temp.name) / "capture.lock"
        self.output = Path(self.temp.name) / "proof.json"

    def invoke(self, *args):
        with mock.patch.object(control, "Bridge", FakeBridge), \
             mock.patch.object(control, "LOCK", self.lock), \
             contextlib.redirect_stdout(io.StringIO()):
            return control.main(list(args))

    def test_info_status_config_and_stop_are_explicit_nontransmit_actions(self):
        for action in ("--info", "--status", "--config-query", "--stop"):
            with self.subTest(action=action):
                FakeBridge.instances.clear()
                self.assertEqual(self.invoke(action), 0)
                calls = FakeBridge.instances[-1].calls
                commands = [call[2] for call in calls if call[0] == "radio"]
                self.assertNotIn("ARM", commands)
                self.assertNotIn("START", commands)

    def test_transmit_requires_explicit_flag_and_saves_idle_proof(self):
        self.assertEqual(self.invoke("--transmit", "--count", "2", "--run", "7",
                                     "--seed", "9", "--output", str(self.output)), 0)
        proof = json.loads(self.output.read_text())
        self.assertTrue(proof["completed"])
        self.assertTrue(proof["radio"]["idle_verified"])
        self.assertFalse(proof["rate54_callback_is_receiver_proof"])
        commands = [call[2] for call in FakeBridge.instances[-1].calls if call[0] == "radio"]
        self.assertEqual(commands[:4], ["INFO", "CONFIG?", "CONFIG 8 8 2 2 7 9", "CONFIG?"])
        self.assertIn("ARM", commands)
        self.assertIn("START", commands)
        self.assertIn("STOP", commands)
        with self.assertRaises(FileExistsError):
            control.write_proof(self.output, proof)

    def test_readback_failure_still_stops_without_starting(self):
        args = control.argparse.Namespace(channel=8, power=8, count=2, gap=2, run=7, seed=9)
        bridge = FakeBridge()
        original = bridge.radio_command
        def wrong(source, command, prefix=None, timeout=4):
            answer = original(source, command, prefix, timeout)
            if command == "ARM":
                return answer.replace("ch=8", "ch=9")
            return answer
        bridge.radio_command = wrong
        proof = control.transmit(bridge, args)
        self.assertFalse(proof["completed"])
        self.assertIn("ARM readback mismatch", proof["error"])
        self.assertTrue(proof["radio"]["idle_verified"])
        sent = [c[2] for c in bridge.calls if c[0] == "radio"]
        self.assertNotIn("START", sent)
        self.assertIn("STOP", sent)

    def test_no_implicit_tx_or_unbounded_packet_count(self):
        with self.assertRaises(SystemExit):
            self.invoke("--output", str(self.output))
        with self.assertRaises(SystemExit):
            self.invoke("--transmit", "--count", "17", "--output", str(self.output))
        self.assertEqual(FakeBridge.instances, [])


if __name__ == "__main__":
    unittest.main()
