import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import signal
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spi_pipeline_lab import SPIManager, meter_snapshot, stop_experiment
from spi_meter import integer_reference


class TestSPIPipelineLab(unittest.TestCase):
    def test_saved_measurement_is_verified_before_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = bytes((n * 37 + 11) & 255 for n in range(32760))
            meter = dict(integer_reference(raw), valid=True, reference_match=True,
                         ingress_s=.055, ingress_payload_bytes_s=590000)
            proof = dict(fpga_meter=meter, sha256=hashlib.sha256(raw).hexdigest(),
                kind='synthetic_spi_fpga_meter_hardware', requested_mode='synthetic',
                readback_mode='synthetic', fpga_identity='SPIQ0002', source=2,
                sequence=123, payload_exact=True, crc_all_pass=True,
                elapsed_s=.3, end_to_end_bytes_s=109200)
            (root/'capture.ci8').write_bytes(raw)
            (root/'proof.json').write_text(json.dumps(proof))
            result = meter_snapshot(root)
            self.assertEqual(result['readback']['sequence'], 123)
            self.assertTrue(result['verification']['meter_exact'])
            self.assertEqual(len(result['plots']['spectrum']['x']), 1024)
            self.assertIn('display FFT', result['provenance']['host_processing'])
            proof['fpga_meter']['power_sum'] += 1
            (root/'proof.json').write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                meter_snapshot(root)
            proof['fpga_meter']['power_sum'] -= 1
            proof['crc_all_pass'] = False
            (root/'proof.json').write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                meter_snapshot(root)

    def test_missing_or_programmer_manifest_keeps_browser_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root/'cyberether/run'
            run.mkdir(parents=True)
            manager = SPIManager(run/'state.json', root=root)
            self.assertTrue(manager.state()['spi_capture_paused'])
            (run/'active-fpga.json').write_text(json.dumps({'checkpoint': 7}))
            self.assertFalse(manager.state()['spi_capture_paused'])
            (run/'active-fpga.json').write_text(json.dumps({'checkpoint': -1}))
            self.assertTrue(manager.state()['spi_capture_paused'])

    def test_stop_leaves_jtag_alive_for_checker_restoration(self):
        child = Mock()
        child.poll.return_value = None
        with patch('spi_pipeline_lab.os.killpg') as group:
            stop_experiment(child)
        child.send_signal.assert_called_once_with(signal.SIGINT)
        child.wait.assert_called_once_with(timeout=30)
        group.assert_not_called()

    def test_stuck_checker_has_bounded_group_cleanup(self):
        child = Mock(pid=123)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('checker', 30), 0]
        with patch('spi_pipeline_lab.os.killpg') as group:
            stop_experiment(child)
        group.assert_called_once_with(123, signal.SIGKILL)

    def test_invalid_capture_never_starts_a_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SPIManager(Path(tmp)/'state.json', root=tmp)
            for data in ({'pipeline': 'shell'}, {'profile': 'unknown'}, {'command': 'anything'},
                         {'pipeline': 'meter', 'host_baud': 4000000},
                         {'pipeline': 'fir', 'host_baud': True}):
                with self.assertRaises(ValueError):
                    manager.capture(data)
            self.assertIsNone(manager.child)
            manager.closed = True
            with self.assertRaises(RuntimeError):
                manager.capture({})


if __name__ == '__main__':
    unittest.main()
