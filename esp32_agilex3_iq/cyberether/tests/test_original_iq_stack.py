"""Regression for the V2 worker's oversized compiler frame; no device access."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_original_iq_stack import inspect
class StackEvidence(unittest.TestCase):
 def report(self,text):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'main.c.su';p.write_text(text);return inspect(p)
 def test_static_frame_budget(self):self.assertTrue(self.report('main.c:63:13:worker\t384\tstatic\n')['passed'])
 def test_original_896_byte_frame_rejected(self):
  with self.assertRaisesRegex(ValueError,'<=512'):self.report('main.c:63:13:worker\t896\tstatic\n')
 def test_missing_or_dynamic_frame_rejected(self):
  for text in ('','main.c:63:13:worker\t384\tdynamic\n'):
   with self.assertRaises(ValueError):self.report(text)
