"""A showreel must never advance on old settings or paint invented waterfall rows."""
import copy,sys,time,unittest
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
if __name__=='__main__':unittest.main()
