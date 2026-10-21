import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modem_lab
from modem_reference import conv_encode, fixedpoint_soft_demapper, quantized_mapping


class ModemLabFpgaTests(unittest.TestCase):
    def checkpoint_tree(self, root, stage_relative=modem_lab.MODEM_STAGE):
        stage = root / modem_lab.MODEM_STAGE
        stage.mkdir(parents=True)
        (stage / "iq_bridge_vds.sof").write_bytes(b"qualified test image")
        digest = hashlib.sha256((stage / "iq_bridge_vds.sof").read_bytes()).hexdigest()
        build = dict(status="PASS_BUILD", checkpoint=6, sha256=digest, hardware_verified=False)
        (stage / "BUILD_RESULT.json").write_text(json.dumps(build))
        run = root / "cyberether/run"
        run.mkdir(parents=True)
        (run / "active-fpga.json").write_text(json.dumps(dict(stage_relative=stage_relative, sha256=digest)))
        return dict(stage_relative=modem_lab.MODEM_STAGE, sha256=digest, status="PASS_BUILD")

    def test_checkpoint_guard_checks_stage_and_image_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self.checkpoint_tree(root)
            self.assertEqual(modem_lab.require_modem_checkpoint(root), expected | {"device": None, "hardware_verified": False})
            (root / "cyberether/run/active-fpga.json").write_text(json.dumps(dict(stage_relative="fpga_hub/other", sha256=expected["sha256"])))
            with self.assertRaisesRegex(ValueError, "not the active FPGA image"):
                modem_lab.require_modem_checkpoint(root)

    def test_fpga_action_disabled_or_wrong_checkpoint_never_constructs_modem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = modem_lab.fpga_status(enabled=False, root=root)
            self.assertFalse(status["ready"])
            constructor = Mock()
            owner = object()
            checkpoint = dict(stage_relative="fpga_hub/iq_bridge/vds_demo_05_gain", status="PASS_BUILD", sha256="old")
            with self.assertRaisesRegex(ValueError, "requires active checkpoint 06"):
                modem_lab.run_fpga_symbol_test(owner, {"modulation": "QPSK"}, checkpoint, constructor)
            constructor.assert_not_called()
            with self.assertRaisesRegex(ValueError, "Choose BPSK"):
                modem_lab.validate_fpga_request({"modulation": "OQPSK"})
            with self.assertRaisesRegex(ValueError, "byte-aligned"):
                modem_lab.validate({"payload_bits": 129})

    def test_cross_checkout_jtag_owner_blocks_manual_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.checkpoint_tree(root)
            with patch.object(modem_lab, "_monitor_active", return_value=False), \
                 patch.object(modem_lab, "_jtag_owner_busy", return_value=True), \
                 patch.object(modem_lab, "_viewer_active", return_value=False), \
                 patch.object(modem_lab, "_nios_owner_busy", return_value=False):
                status = modem_lab.fpga_status(enabled=True, root=root)
            self.assertFalse(status["ready"])
            self.assertTrue(status["jtag_client_active"])
            self.assertIn("another checkout", status["reason"])

    def test_manual_owner_loopback_reports_exact_fpga_source_and_counters(self):
        seed = 19
        expected_bits = np.random.default_rng(seed).integers(0, 2, 32, dtype=np.uint8)
        owner = object()

        class FakeModem:
            def __init__(self, supplied_owner):
                self.asserted_owner = supplied_owner

            def encode(self, bits, bps):
                np.testing.assert_array_equal(bits, expected_bits)
                self.asserted_bps = bps
                self.coded = conv_encode(bits)
                padded = np.pad(self.coded, (0, (-len(self.coded)) % bps))
                labels = padded.reshape(-1, bps) @ (1 << np.arange(bps - 1, -1, -1))
                mapping = quantized_mapping("64QAM")
                iq = mapping[labels].copy()
                self.original_iq = iq.copy()
                return dict(iq=iq, coded=self.coded.copy(), cycles=3400)

            def decode(self, iq):
                self.asserted_iq = iq
                self.asserted_symbol_changed = not np.array_equal(iq, self.original_iq)
                llr = fixedpoint_soft_demapper(iq, "64QAM")
                return dict(bits=expected_bits.copy(), llr=llr, raw_errors=1, decoded_errors=0, cycles=18400)

        checkpoint = dict(stage_relative=modem_lab.MODEM_STAGE, status="PASS_BUILD", sha256="a" * 64)
        result = modem_lab.run_fpga_symbol_test(owner, {"modulation": "64QAM", "seed": seed}, checkpoint, FakeModem)
        self.assertEqual(result["source"], "FPGA checkpoint 06 symbol-rate modem")
        self.assertEqual(result["stage_relative"], modem_lab.MODEM_STAGE)
        self.assertEqual(result["evidence"]["encode_cycles"], 3400)
        self.assertEqual(result["evidence"]["decode_cycles"], 18400)
        self.assertEqual(result["evidence"]["fpga_raw_coded_errors"], 1)
        self.assertEqual(result["evidence"]["independent_coded_errors"], 1)
        self.assertEqual(result["evidence"]["fpga_decoded_bit_errors"], 0)
        self.assertTrue(result["evidence"]["encoder_matches_reference"])
        self.assertTrue(result["evidence"]["mapper_matches_reference"])
        self.assertTrue(result["evidence"]["llr_matches_reference"])
        self.assertTrue(result["evidence"]["counters_verified"])
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["hardware_verified"])
        self.assertEqual(result["evidence"]["host_payload_errors"], 0)
        self.assertFalse(result["evidence"]["rf_tx"])
        self.assertFalse(result["evidence"]["python_waveform_sync"])

    def test_wrong_fpga_id_error_is_preserved(self):
        checkpoint = dict(stage_relative=modem_lab.MODEM_STAGE, status="PASS_BUILD", sha256="b" * 64)

        class WrongImage:
            def __init__(self, owner):
                raise RuntimeError("Checkpoint06 modem ID not present")

        with self.assertRaisesRegex(RuntimeError, "modem ID not present"):
            modem_lab.run_fpga_symbol_test(object(), {"modulation": "QPSK"}, checkpoint, WrongImage)

    def test_counter_mismatch_cannot_claim_hardware_verified(self):
        bits = np.random.default_rng(7).integers(0, 2, 32, dtype=np.uint8)
        coded = conv_encode(bits)

        class WrongCounter:
            def __init__(self, owner):
                pass

            def encode(self, payload, bps):
                padded = np.pad(coded, (0, (-len(coded)) % bps))
                labels = padded.reshape(-1, bps) @ (1 << np.arange(bps - 1, -1, -1))
                return dict(iq=quantized_mapping("QPSK")[labels], coded=coded.copy(), cycles=20)

            def decode(self, iq):
                llr = fixedpoint_soft_demapper(iq, "QPSK")
                return dict(bits=bits.copy(), llr=llr, raw_errors=0, decoded_errors=0, cycles=30)

        checkpoint = dict(stage_relative=modem_lab.MODEM_STAGE, status="PASS_BUILD", sha256="c" * 64)
        result = modem_lab.run_fpga_symbol_test(object(), {"modulation": "QPSK"}, checkpoint, WrongCounter)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["evidence"]["counters_verified"])
        self.assertTrue(result["evidence"]["mapper_matches_reference"])
        self.assertTrue(result["evidence"]["llr_matches_reference"])


if __name__ == "__main__":
    unittest.main()
