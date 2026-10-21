"""Choose the board UART by USB identity, without probing/opening serial ports."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from common import resolve_uart


class UARTDiscovery(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ,{},clear=True).start()
        self.ports=patch('serial.tools.list_ports.comports',return_value=[]).start()
        self.links=patch('common.Path.glob',return_value=[]).start()
        patch('serial.Serial',side_effect=AssertionError('Discovery must not open a UART')).start()

    def port(self,name='ttyUSB7',**changes):
        path=self.root/name
        path.touch()
        values=dict(device=str(path),vid=0x09fb,pid=0x6022,location='2-3:1.1')
        values.update(changes)
        return SimpleNamespace(**values)

    def test_explicit_argument_and_environment_override_detection(self):
        first=self.port('custom-a').device
        second=self.port('custom-b').device
        os.environ['ATUM_UART']=first
        self.assertEqual(resolve_uart(),first)
        self.assertEqual(resolve_uart(second),second)
        self.ports.assert_not_called()

    def test_invalid_override_is_reported_instead_of_silently_falling_back(self):
        self.ports.return_value=[self.port()]
        for value in ('',str(self.root/'missing')):
            with self.subTest(value=value):
                os.environ['ATUM_UART']=value
                with self.assertRaisesRegex(RuntimeError,'Configured UART.*does not exist'):
                    resolve_uart()
        self.ports.assert_not_called()

    def test_metadata_finds_uart_when_container_has_no_by_id_links(self):
        board=self.port()
        self.ports.return_value=[board]
        self.assertEqual(resolve_uart(),board.device)

    def test_stable_symlink_is_preferred_and_same_device_is_deduplicated(self):
        board=self.port()
        link=self.root/'usb-TERASIC_Atum_A3_Nano_test-if01-port0'
        link.symlink_to(board.device)
        self.links.return_value=[link]
        self.ports.return_value=[board]
        self.assertEqual(resolve_uart(),str(link))

    def test_unrelated_usb_uart_and_jtag_interface_are_not_selected(self):
        self.ports.return_value=[self.port('other',vid=0x0403,pid=0x6011),
                                 self.port('jtag',location='2-3:1.0')]
        with self.assertRaisesRegex(RuntimeError,'No Atum A3 Nano UART detected'):
            resolve_uart()

    def test_multiple_boards_require_explicit_selection(self):
        self.ports.return_value=[self.port('board-a'),self.port('board-b')]
        with self.assertRaisesRegex(RuntimeError,'Multiple Atum A3 Nano UARTs.*ATUM_UART'):
            resolve_uart()

    def test_no_board_reports_how_to_override(self):
        with self.assertRaisesRegex(RuntimeError,'No Atum A3 Nano UART.*ATUM_UART'):
            resolve_uart()

    def test_bridge_honors_environment_set_after_import(self):
        from iq_bridge import Bridge
        os.environ['ATUM_UART']=self.port().device
        with patch('iq_bridge.serial.Serial')as serial:
            with Bridge() as bridge:
                self.assertEqual(bridge.port.port,os.environ['ATUM_UART'])
            serial.return_value.open.assert_called_once()


if __name__=='__main__':
    unittest.main()
