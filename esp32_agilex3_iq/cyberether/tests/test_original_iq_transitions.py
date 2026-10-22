"""Offline synthetic calibration of the engineering fitter, never RF evidence."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from analyze_original_iq_transitions import evaluate
class TransitionFit(unittest.TestCase):
 def waveform(self,phase=0,flat=False,carrier=17000):
  t=np.arange(16380)/40000000;high=(np.arange(len(t))//1280)%2==0
  envelope=np.ones(len(t))*100 if flat else np.where(high,100,70)
  rotation=0 if flat else np.where(high,0,np.deg2rad(phase))
  return envelope*np.exp(1j*(2*np.pi*carrier*t+rotation))+(1+.5j)
 def test_known_am_pm_and_dc(self):
  result,_,_=evaluate(self.waveform(8))
  self.assertTrue(result['two_levels_detected']);self.assertAlmostEqual(result['amplitude_ratio'],.7,places=3)
  self.assertAlmostEqual(result['low_relative_phase_deg'],8,places=2)
  self.assertLess(abs(result['carrier_fit_hz']-17000),2)
  self.assertFalse(result['phase_continuity_qualified']);self.assertFalse(result['qam_qualified'])
 def test_pure_amplitude_step_has_no_artificial_phase_offset(self):
  result,_,_=evaluate(self.waveform())
  self.assertLess(abs(result['low_relative_phase_deg']),.02)
 def test_unchanged_code_control_rejects_two_levels(self):
  result,_,_=evaluate(self.waveform(flat=True))
  self.assertFalse(result['two_levels_detected']);self.assertLess(result['phase_rms_deg'],.02)
 def test_nonfinite_input_rejected(self):
  with self.assertRaises(ValueError):evaluate(np.full(16380,np.nan))
 def test_offset_receiver_with_negative_iq_orientation(self):
  result,_,_=evaluate(self.waveform(8,carrier=-4983000),expected_abs_offset_hz=5000000)
  self.assertAlmostEqual(result['low_relative_phase_deg'],8,places=2)
  self.assertLess(abs(result['carrier_fit_hz']+4983000),2)
