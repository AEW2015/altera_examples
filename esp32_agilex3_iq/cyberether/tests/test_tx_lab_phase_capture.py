import sys,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import tx_lab_phase_capture as c
class PhaseCapture(unittest.TestCase):
 def test_explicit_transmit_required_before_any_device(self):
  with patch.object(sys,'argv',['phase','--output','unused.json']),patch.object(c,'CaptureMonitorBridge') as bridge:
   with self.assertRaises(SystemExit):c.main()
   bridge.assert_not_called()
 def test_both_tone_enables_and_mode_checked(self):
  b=MagicMock();b.radio_command.side_effect=['TXLAB,MODE,mode=PHASE,quiet=1','TONE_STATE,tone1=20000000,tone2=00000000,ext=00000000']
  self.assertIn('state',c.quiet(b))
  b.radio_command.side_effect=['TXLAB,MODE,mode=PHASE,quiet=1','TONE_STATE,tone1=20000000,tone2=00040000,ext=00000000']
  with self.assertRaises(RuntimeError):c.quiet(b)
  b.radio_command.side_effect=['TXLAB,MODE,mode=AMP,quiet=1']
  with self.assertRaises(RuntimeError):c.quiet(b)

 def test_capture_rate_matches_firmware_profile_code(self):
  self.assertEqual(c.capture_wire(16000000),'CAP16 16380 6\n')
  self.assertEqual(c.capture_wire(40000000),'CAP16 16380 1\n')
  with self.assertRaises(ValueError):c.capture_wire(32000000)
