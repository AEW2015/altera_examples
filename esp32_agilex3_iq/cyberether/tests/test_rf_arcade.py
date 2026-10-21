"""A showreel must never advance on old settings or paint invented waterfall rows."""
import copy,sys,time,unittest
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rf_arcade import Showreel,SCENES
from demo_night_view import Arcade
class FakeLab:
 def __init__(self):self.settings={}
 def update(self,body):self.settings.update(body)
class ShowTests(unittest.TestCase):
 def test_auto_waits_for_applied_verified_results_and_full_hold(self):
  now=[0.];show=Showreel(FakeLab(),clock=lambda:now[0]);show.update({'auto':True})
  r=dict(acquisition=show.required.copy(),captured_unix=show.selected_unix+1,max_reference_error=0)
  old=copy.deepcopy(r);old['acquisition']['channel']=11
  now[0]=100;show.on_result(old);self.assertTrue(show.status()['waiting'])
  bad=copy.deepcopy(r);bad['max_reference_error']=1;show.on_result(bad);self.assertTrue(show.status()['waiting'])
  show.on_result(r);self.assertEqual(show.scene,'airwaves')
  now[0]=115;show.on_result(r);self.assertEqual(show.scene,'airwaves')
  now[0]=116;show.on_result(r);self.assertEqual(show.scene,'fold');self.assertTrue(show.status()['waiting'])
  show.on_result(r);self.assertEqual(show.matches,0)
 def test_controls_reject_before_mutating(self):
  show=Showreel(FakeLab());before=show.status()
  for b in ({'auto':1},{'scene':'fake'},{'source':True},{'channel':12},{'scene':'boost','source':4},{'new':1}):
   with self.assertRaises(ValueError):show.update(b)
   self.assertEqual(show.status()['scene'],before['scene']);self.assertEqual(show.radio,0)
  show.update({'source':2,'channel':11});self.assertEqual(show.required['source'],2)
 def test_all_scene_controls_use_valid_lab_schema(self):
  from iq_bridge_lab import validate_settings
  show=Showreel(FakeLab())
  for name in SCENES:
   show.select(name);self.assertEqual(validate_settings(show.required),show.required)
class ViewTests(unittest.TestCase):
 def rescue_state(self,filtered=False,stamp=1.,phase=0x08000000):
  cfg=dict(view='ddc',source=0,channel=2,tuning_hz=500000)
  ddc=dict(phase=phase,output_rate=4000000,output_samples=1024,decimation=4,
   bypass_flags=0 if filtered else 2,digital_gain_q8=256,digital_gain_bypass=False,max_reference_error=0)
  tones=[dict(output_hz=0.,attenuation_db=.0004),dict(output_hz=1500000.,attenuation_db=91. if filtered else 0.)]
  spectrum=[-80.]*16;spectrum[8]=33.;spectrum[14]=-55. if filtered else 36.
  c=dict(captured_unix=stamp,acquisition=cfg,raw=dict(source=3,frequency=0,rate=16000000),
   input_id='same-fpga-input',input_kind='two-tone',ddc=ddc,ddc_spectrum_db=spectrum,
   ddc_wave=[[48.,0.],[48.,.01]],tone_measurements=dict(tones=tones))
  return dict(status='LIVE',completed=2,latest={'ddc':c},demo_night=dict(required=cfg,selected_unix=0.,
   scene='reject'if filtered else'tune',title='OFFLINE TEST · RESCUE'))
 def state(self):
  cfg=dict(view='hamming',source=0,channel=2)
  c=dict(captured_unix=1.,acquisition=cfg,raw=dict(source=0,frequency=2417000000,rate=16000000),
   spectra_db=[[-15.]*16,[-20.]*16],scatter=[[[1,2],[3,-1]]],filtered={'samples':4096},source_name='RFS2 ESP32',
   max_reference_error=0,payload_Bps=10000,clips=0)
  return dict(status='LIVE',completed=1,latest={'hamming':c},demo_night=dict(required=cfg,selected_unix=0.,scene='airwaves',title='AIRWAVES'))
 def test_waterfall_only_adds_distinct_results_is_bounded_and_resets_on_frequency(self):
  v=Arcade();s=self.state();v.ingest(s);v.ingest(s);self.assertEqual(len(v.rows),1)
  for i in range(250):s['latest']['hamming']['captured_unix']+=1;v.ingest(s)
  self.assertEqual(len(v.rows),180)
  s['latest']['hamming']['raw']['frequency']=2422000000;s['latest']['hamming']['captured_unix']+=1;v.ingest(s)
  self.assertEqual(len(v.rows),1)
  s['demo_night']['required']={'view':'ddc'};self.assertFalse(v.ingest(s));self.assertEqual(len(v.rows),1)
 def test_empty_and_real_result_render_without_synthetic_filler(self):
  v=Arcade();self.assertEqual(v.render({}).size,(1800,1000));self.assertFalse(v.rows)
  self.assertEqual(v.render(self.state()).size,(1800,1000));self.assertEqual(len(v.rows),1)
 def test_failed_or_unverified_results_do_not_enter_display_history(self):
  for ddc in (False,True):
   for error in (None,1,-1):
    with self.subTest(ddc=ddc,error=error):
     v=Arcade();s=self.state();c=s['latest']['hamming']
     if ddc:c['ddc']={'max_reference_error':error}
     else:c['max_reference_error']=error
     self.assertFalse(v.ingest(s));self.assertFalse(v.rows);self.assertIsNone(v.last)
 def test_rescue_retains_measured_before_trace_after_peak_memory_expires(self):
  v=Arcade();before=self.rescue_state();v.ingest(before)
  expected=before['latest']['ddc']['ddc_spectrum_db'].copy()
  before['latest']['ddc']['ddc_spectrum_db'][0]=123. # The retained trace is a copy.
  after=self.rescue_state(filtered=True,stamp=2.);v.ingest(after);v.peaks.clear()
  np.testing.assert_array_equal(v.before_spectrum(after['latest']['ddc']),expected)
  self.assertEqual(v.render(after).size,(1800,1000))
 def test_rescue_never_compares_different_input_or_processing_settings(self):
  changes=[('input_id','different-input'),('phase',0),('output_rate',8000000),
   ('output_samples',512),('digital_gain_q8',512),('digital_gain_bypass',True),('bypass_flags',1)]
  for key,value in changes:
   with self.subTest(key=key):
    v=Arcade();v.ingest(self.rescue_state())
    after=self.rescue_state(filtered=True,stamp=2.);c=after['latest']['ddc']
    (c if key=='input_id'else c['ddc'])[key]=value
    v.ingest(after);self.assertIsNone(v.before_spectrum(c))
 def test_fold_trace_cannot_be_presented_as_shift_before_filtering(self):
  v=Arcade();v.ingest(self.rescue_state(phase=0))
  after=self.rescue_state(filtered=True,stamp=2.);v.ingest(after)
  self.assertIsNone(v.before_spectrum(after['latest']['ddc']))
 def test_failed_capture_cannot_become_a_rescue_baseline(self):
  v=Arcade();s=self.rescue_state();s['latest']['ddc']['ddc']['max_reference_error']=1
  self.assertFalse(v.ingest(s));self.assertIsNone(v.rescue_before)
 def test_rescue_without_matching_baseline_and_existing_power_view_render(self):
  v=Arcade();s=self.rescue_state(filtered=True)
  self.assertEqual(v.render(s).size,(1800,1000));self.assertIsNone(v.before_spectrum(s['latest']['ddc']))
  power=self.rescue_state(stamp=2.);power['latest']['ddc']['input_kind']='single-tone'
  power['latest']['ddc']['tone_measurements']['tones']=power['latest']['ddc']['tone_measurements']['tones'][:1]
  self.assertEqual(v.render(power).size,(1800,1000));self.assertIsNone(v.rescue_before)
if __name__=='__main__':unittest.main()
