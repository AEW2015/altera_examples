"""Protect the hardware target and running demo when loading optional CPU apps."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import nios_download


class DownloadTarget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage_by_checkpoint = {
            2: self.root / 'fpga_hub/iq_bridge/vds_demo_02_nios',
            6: self.root / 'fpga_hub/iq_bridge/vds_demo_06_modem',
            7: self.root / 'fpga_hub/iq_bridge/vds_demo_07_spi_fir',
        }
        self.stage = self.stage_by_checkpoint[2]
        state = self.root / 'cyberether/run/active-fpga.json'
        state.parent.mkdir(parents=True)
        self.state = state
        state.write_text(json.dumps({'stage_relative': self.stage.relative_to(self.root).as_posix()}))
        elf = self.root / 'software/checkpoint_02/hello_world/build/hello_world.elf'
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b'fake ELF; subprocess execution is mocked')

    def invoke(self, listing, checkpoint=2):
        with patch.object(nios_download, 'ROOT', self.root), \
             patch.object(nios_download, 'software_stage', side_effect=self.stage_by_checkpoint.__getitem__), \
             patch.object(nios_download, 'local_tools', return_value=True), \
             patch.object(nios_download, 'software_env', return_value={}), \
             patch.object(nios_download, 'stop_demo') as stop, \
             patch.object(nios_download.subprocess, 'check_output', return_value=listing), \
             patch.object(nios_download.subprocess, 'run') as run, \
             patch.object(sys, 'argv', ['nios_download.py', str(checkpoint), 'hello_world']), \
             patch.dict('os.environ', {'ATUM_JTAG_CABLE': 'Atum A3 Nano [usb]'}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                nios_download.main()
                return None, stop, run
            except SystemExit as error:
                return error.code, stop, run

    def test_selects_atum_when_another_board_is_first(self):
        code, stop, run = self.invoke('1) Other development board [usb]\n  1234 Device\n2) Atum A3 Nano [usb]\n  5678 Device\n')
        self.assertIsNone(code)
        stop.assert_called_once()
        self.assertEqual(run.call_args.args[0][:9], ['niosv-download', '-c', '2', '-d', '0', '-i', '0', '-r', '-g'])

    def test_wrong_checkpoint_never_stops_demo_or_downloads(self):
        self.state.write_text(json.dumps({'stage_relative': 'fpga_hub/checkpoint5'}))
        code, stop, run = self.invoke('2) Atum A3 Nano [usb]\n')
        self.assertEqual(code, 2)
        stop.assert_not_called()
        run.assert_not_called()

    def test_missing_atum_never_stops_demo_or_downloads(self):
        code, stop, run = self.invoke('1) Other development board [usb]\n')
        self.assertEqual(code, 2)
        stop.assert_not_called()
        run.assert_not_called()

    def test_modem_checkpoint_selects_its_own_software(self):
        stage = self.stage_by_checkpoint[6]
        self.state.write_text(json.dumps({'stage_relative': stage.relative_to(self.root).as_posix()}))
        elf = self.root / 'software/checkpoint_06/hello_world/build/hello_world.elf'
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b'fake ELF; subprocess execution is mocked')
        code, stop, run = self.invoke('2) Atum A3 Nano [usb]\n', checkpoint=6)
        self.assertIsNone(code)
        self.assertEqual(run.call_args.args[0][-1], str(elf))
        stop.assert_called_once()

    def test_spi_fir_checkpoint_selects_its_own_software(self):
        stage = self.stage_by_checkpoint[7]
        self.state.write_text(json.dumps({'stage_relative': stage.relative_to(self.root).as_posix()}))
        elf = self.root / 'software/checkpoint_07/hello_world/build/hello_world.elf'
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b'fake ELF; subprocess execution is mocked')

        code, stop, run = self.invoke('2) Atum A3 Nano [usb]\n', checkpoint=7)

        self.assertIsNone(code)
        self.assertEqual(run.call_args.args[0][-1], str(elf))
        stop.assert_called_once()

    def test_wrong_spi_fir_image_never_stops_demo_or_downloads(self):
        stage = self.stage_by_checkpoint[6]
        self.state.write_text(json.dumps({'stage_relative': stage.relative_to(self.root).as_posix()}))

        code, stop, run = self.invoke('2) Atum A3 Nano [usb]\n', checkpoint=7)

        self.assertEqual(code, 2)
        stop.assert_not_called()
        run.assert_not_called()
