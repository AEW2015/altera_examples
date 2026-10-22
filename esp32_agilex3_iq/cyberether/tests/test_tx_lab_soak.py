import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from tx_lab_soak import schedule
class SoakSchedule(unittest.TestCase):
 def test_bounded_schedule(self):
  self.assertEqual(schedule(3,20),[n*1200 for n in range(9)])
  self.assertEqual(schedule(.01,20),[0])
 def test_invalid_schedule(self):
  for hours,minutes in [(0,20),(7,20),(3,0),(3,61)]:
   with self.assertRaises(ValueError):schedule(hours,minutes)
