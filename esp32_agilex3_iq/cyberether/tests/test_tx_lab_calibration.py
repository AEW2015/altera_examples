import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from tx_lab_calibration import assess,summarize
class CalibrationGates(unittest.TestCase):
 def candidate(self):return dict(two_levels_detected=True,high_amplitude_adc=97,low_amplitude_adc=70,fit_residual_rms_adc=2,amplitude_ratio=70/97,low_relative_phase_deg=-3)
 def test_control_and_headroom(self):
  self.assertIsNone(assess(dict(amplitude_adc=97,phase_rms_deg=2,fit_residual_rms_adc=2),control=True))
  self.assertEqual(assess(dict(amplitude_adc=120,phase_rms_deg=2,fit_residual_rms_adc=2),control=True),'control_headroom_or_signal')
 def test_missed_capture_never_qualified(self):self.assertEqual(assess({},reference=97),'sparse_capture_missed_transitions')
 def test_candidate_requires_good_reference_signal_and_fit(self):
  r=self.candidate();self.assertIsNone(assess(r,reference=97))
  for field,value,reason in [('high_amplitude_adc',120,'reference_amplitude_changed'),('low_amplitude_adc',3,'weak_level_not_qualified'),('fit_residual_rms_adc',20,'fit_residual')]:
   r=self.candidate();r[field]=value;self.assertEqual(assess(r,reference=97),reason)
 def test_rejected_measurements_not_in_summary(self):
  summary=summarize([dict(code=24,qualified=True,measurement=self.candidate()),dict(code=32,qualified=False,measurement=self.candidate())])
  self.assertEqual([r['code'] for r in summary['levels']],[24]);self.assertFalse(summary['custom_qam_qualified'])

 def test_nonfinite_metrics_rejected(self):
  r=self.candidate();r['fit_residual_rms_adc']=float('nan');self.assertEqual(assess(r,reference=97),'nonfinite_or_missing_measurement')
