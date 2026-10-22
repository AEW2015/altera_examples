import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tx_calibration_view as view
class CalibrationView(unittest.TestCase):
 def test_waiting_has_no_rf_control(self):
  with tempfile.TemporaryDirectory() as t:self.assertEqual(view.read(Path(t)/'missing')[0]['state'],'waiting')
 def test_rejects_outside_run_path(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'pointer';p.write_text(json.dumps({'status':'/etc/passwd'}))
   self.assertEqual(view.read(p)[0]['state'],'telemetry_error')
 def test_summary_is_read_only_and_hides_commands(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);run=root/'run';run.mkdir();status=run/'status.json';status.write_text(json.dumps({'state':'running','observations':[{'qualified':True}],'summary':{'levels':[{'code':24}]},'commands':['private details']}))
   pointer=root/'pointer';pointer.write_text(json.dumps({'status':str(status)}))
   with patch.object(view,'RUN',run):result,image=view.read(pointer)
   self.assertEqual(result['qualified_captures'],1);self.assertNotIn('commands',result);self.assertFalse(result['qam_qualified']);self.assertIsNone(image)
