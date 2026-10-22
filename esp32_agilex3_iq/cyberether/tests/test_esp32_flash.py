"""Reject firmware/target mismatches before a programmer can open hardware."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import flash_esp32 as flash


class FirmwareImages(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name)
        (self.build / 'config').mkdir()
        (self.build / 'project_description.json').write_text(json.dumps(dict(target='esp32', project_name='atum_rf_suite')))
        self.config = dict(ESP_SDR_UART_TX_PIN=17, ESP_SDR_UART_RX_PIN=16,
                           ESP_CONSOLE_UART_TX_GPIO=17, ESP_CONSOLE_UART_RX_GPIO=16)
        self.save_config()
        self.spec = dict(write_flash_args=['--flash-mode', 'dio', '--flash-size', '2MB', '--flash-freq', '40m'],
                         flash_files={'0x10000': 'app.bin', '0x1000': 'boot.bin', '0x8000': 'partition.bin'})
        for name in self.spec['flash_files'].values():
            (self.build / name).write_bytes(b'fixture' * 10)
        self.save_spec()

    def save_spec(self):
        (self.build / 'flasher_args.json').write_text(json.dumps(self.spec))

    def save_config(self):
        (self.build / 'config/sdkconfig.json').write_text(json.dumps(self.config))

    def test_rom_offsets_are_sorted_and_application_profile_checked(self):
        spec, pairs = flash.images(self.build, 'pmod-a')
        self.assertEqual([int(offset, 0) for offset, _ in pairs], [0x1000, 0x8000, 0x10000])
        with self.assertRaisesRegex(ValueError, 'needs application UART'):
            flash.images(self.build, 'rfs2')

    def test_wifi64_roles_require_matching_module_and_console(self):
        for project, target in [('wifi64_tx', 'pmod-a'), ('wifi64_monitor', 'pmod-b')]:
            (self.build / 'project_description.json').write_text(json.dumps(
                dict(target='esp32', project_name=project)))
            flash.images(self.build, target)
            for other in ('rfs2', 'pmod', 'pmod-a', 'pmod-b'):
                if other != target:
                    with self.assertRaisesRegex(ValueError, 'only'):
                        flash.images(self.build, other)
            self.config['ESP_CONSOLE_UART_TX_GPIO'] = 1
            self.save_config()
            with self.assertRaisesRegex(ValueError, 'needs application UART'):
                flash.images(self.build, target)
            self.config['ESP_CONSOLE_UART_TX_GPIO'] = 17
            self.save_config()

    def test_pmod_console_cannot_use_rfs2_pins(self):
        self.config['ESP_CONSOLE_UART_TX_GPIO'] = 1
        self.save_config()
        with self.assertRaisesRegex(ValueError, 'Pmod console'):
            flash.images(self.build, 'pmod-b')

    def test_image_cannot_escape_build_directory(self):
        with tempfile.TemporaryDirectory() as outside:
            image = Path(outside) / 'boot.bin'
            image.write_bytes(b'other image')
            (self.build / 'boot.bin').unlink()
            (self.build / 'boot.bin').symlink_to(image)
            with self.assertRaisesRegex(ValueError, 'out-of-build'):
                flash.images(self.build, 'pmod-a')

    def test_rejects_oversized_flash_layout(self):
        with (self.build / 'app.bin').open('wb') as image:
            image.truncate(2 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, 'outside'):
            flash.images(self.build, 'pmod-a')

    def test_manual_reset_and_manifest_addresses_for_both_esptool_versions(self):
        spec, pairs = flash.images(self.build, 'pmod-a')
        for major, reset, action in [(4, 'no_reset', 'write_flash'), (5, 'no-reset', 'write-flash')]:
            command = flash.tool_command('python', '/dev/target', 115200, 'manual', major, 'flash', spec, pairs)
            self.assertEqual(command[command.index('--before') + 1], reset)
            self.assertEqual(command[command.index('--after') + 1], reset)
            self.assertIn(action, command)
            self.assertIn('--flash-mode' if major == 5 else '--flash_mode', command)
            self.assertEqual(command[-6::2], ['0x1000', '0x8000', '0x10000'])

    def test_changed_recorded_image_is_rejected_before_tool_or_serial_access(self):
        manifest = dict(esptool_python='python', flash_files={offset: dict(sha256='changed') for offset in self.spec['flash_files']})
        (self.build / 'FIRMWARE_BUILD.json').write_text(json.dumps(manifest))
        with patch.object(sys, 'argv', ['flash_esp32.py', '--module', 'pmod-a', '--port', '/dev/target', '--build-dir', str(self.build)]), \
             patch.object(flash.subprocess, 'check_output') as tool, \
             patch.object(flash, 'serial_owners') as owners, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                flash.main()
            self.assertEqual(error.exception.code, 1)
            tool.assert_not_called()
            owners.assert_not_called()

    def test_probe_requires_explicit_identity_and_pmod_pins(self):
        (self.build / 'project_description.json').write_text(json.dumps(dict(target='esp32',project_name='atum_esp32_tx_probe')))
        with self.assertRaisesRegex(ValueError,'explicitly configured'):
            flash.images(self.build,'pmod-a')
        self.config['ATUM_TX_PROBE']=True
        self.save_config()
        flash.images(self.build,'pmod-a')
        with self.assertRaisesRegex(ValueError,'Pmod only'):
            flash.images(self.build,'rfs2')

    def test_original_iq_probe_role_and_build_flags(self):
        (self.build / 'project_description.json').write_text(json.dumps(dict(target='esp32',project_name='atum_original_iq_tx_probe')))
        required=('ATUM_ORIGINAL_IQ_TX_PROBE','ESP_PHY_ENABLE_CERT_TEST','FREERTOS_UNICORE')
        for key in required:self.config[key]=True
        self.save_config()
        flash.images(self.build,'pmod-a')
        for other in ('pmod-b','rfs2','pmod'):
            with self.assertRaisesRegex(ValueError,'pmod-a only'):flash.images(self.build,other)
        for key in required:
            self.config[key]=False;self.save_config()
            with self.assertRaisesRegex(ValueError,'build profile'):flash.images(self.build,'pmod-a')
            self.config[key]=True
        self.config['ESP_CONSOLE_UART_TX_GPIO']=1;self.save_config()
        with self.assertRaisesRegex(ValueError,'needs application UART'):flash.images(self.build,'pmod-a')

    def test_mac_probe_leaves_manual_loader_at_initial_baud(self):
        with patch.object(sys,'argv',['flash_esp32.py','--module','pmod-a','--port','/dev/fixture','--build-dir',str(self.build),'--baud','460800','--expect-mac','78:21:84:d4:4f:98']), \
             patch.object(flash.subprocess,'check_output',side_effect=['esptool v5.6.0','MAC: 78:21:84:d4:4f:98']) as output, \
             patch.object(flash.subprocess,'run') as write, \
             patch.object(flash,'serial_owners',return_value=[]), \
             patch('serial.Serial'),contextlib.redirect_stdout(io.StringIO()):
            flash.main()
            probe=output.call_args_list[1].args[0]
            self.assertEqual(probe[probe.index('--baud')+1],'115200')
            command=write.call_args.args[0]
            self.assertEqual(command[command.index('--baud')+1],'460800')
