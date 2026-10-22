"""Publication tests use fake bridges only; they never open hardware."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import wifi64_ota as ota


class FakeBridge:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Wifi64OtaPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.root / "cyberether" / "run"
        self.run_dir.mkdir(parents=True)
        self.output = self.run_dir / "proof.json"
        self.pointer = self.run_dir / "wifi64-ota-latest.json"

    def invoke(self, *args, bridge=None, job=None, publish=True):
        cli = ["--transmit", "--output", str(self.output)]
        if publish:
            cli.append("--publish")
        cli.extend(args)
        with patch.object(ota, "ROOT", self.root), \
             patch.object(ota, "RUN_DIR", self.run_dir), \
             patch.object(ota, "LATEST_POINTER", self.pointer), \
             patch.object(ota, "LOCK", self.run_dir / "rf-link-capture.lock"), \
             patch.object(ota, "MonitorBridge", return_value=bridge or FakeBridge()) as open_bridge, \
             patch.object(ota, "run_job", return_value=job or {"completed": True, "source": "ota-native-wifi64"}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = ota.main(cli)
        return result, open_bridge

    def test_publish_updates_atomic_pointer_after_complete_proof_write(self):
        real_publish = ota.publish_proof
        def publish_after_close(output):
            saved = json.loads(Path(output).read_text())
            self.assertEqual(saved["completed"], True)
            return real_publish(output)

        with patch.object(ota, "publish_proof", side_effect=publish_after_close) as publish:
            result, bridge = self.invoke()
        self.assertEqual(result, 0)
        bridge.assert_called_once()
        publish.assert_called_once_with(self.output)
        self.assertEqual(json.loads(self.pointer.read_text()), {"path": "cyberether/run/proof.json"})

    def test_publish_rejects_paths_outside_run_dir_before_device_access(self):
        outside = self.root / "elsewhere.json"
        with patch.object(ota, "ROOT", self.root), \
             patch.object(ota, "RUN_DIR", self.run_dir), \
             patch.object(ota, "LATEST_POINTER", self.pointer), \
             patch.object(ota, "LOCK", self.run_dir / "rf-link-capture.lock"), \
             patch.object(ota, "MonitorBridge") as bridge, \
             contextlib.redirect_stderr(io.StringIO()):
            result = ota.main(["--transmit", "--output", str(outside), "--publish"])
        self.assertEqual(result, 2)
        bridge.assert_not_called()
        self.assertFalse(outside.exists())
        self.assertFalse(self.pointer.exists())

    def test_bridge_setup_failure_writes_complete_failure_proof_then_publishes(self):
        with patch.object(ota, "ROOT", self.root), \
             patch.object(ota, "RUN_DIR", self.run_dir), \
             patch.object(ota, "LATEST_POINTER", self.pointer), \
             patch.object(ota, "LOCK", self.run_dir / "rf-link-capture.lock"), \
             patch.object(ota, "MonitorBridge", side_effect=RuntimeError("fake setup failure")), \
             contextlib.redirect_stdout(io.StringIO()):
            result = ota.main(["--transmit", "--output", str(self.output), "--publish"])
        self.assertEqual(result, 2)
        proof = json.loads(self.output.read_text())
        self.assertEqual(proof["kind"], "independent native Wi-Fi64 OTA packet observation")
        self.assertEqual(proof["source"], "ota-native-wifi64")
        self.assertEqual(proof["error"], "fake setup failure")
        self.assertFalse(proof["completed"])
        self.assertIn("finished_unix", proof)
        self.assertEqual(json.loads(self.pointer.read_text()), {"path": "cyberether/run/proof.json"})

    def test_default_transmit_does_not_publish_pointer(self):
        result, bridge = self.invoke(publish=False)
        self.assertEqual(result, 0)
        bridge.assert_called_once()
        self.assertTrue(self.output.exists())
        self.assertFalse(self.pointer.exists())

    def test_existing_output_never_opens_device_or_changes_pointer(self):
        self.output.write_text('{"previous":true}')
        self.pointer.write_text('{"path":"old.json"}')
        with patch.object(ota, "ROOT", self.root), \
             patch.object(ota, "RUN_DIR", self.run_dir), \
             patch.object(ota, "LATEST_POINTER", self.pointer), \
             patch.object(ota, "LOCK", self.run_dir / "rf-link-capture.lock"), \
             patch.object(ota, "MonitorBridge") as bridge, \
             contextlib.redirect_stderr(io.StringIO()):
            result = ota.main(["--transmit", "--output", str(self.output), "--publish"])
        self.assertEqual(result, 2)
        bridge.assert_not_called()
        self.assertEqual(json.loads(self.pointer.read_text()), {"path": "old.json"})


if __name__ == "__main__":
    unittest.main()
