"""Reject corrupted or clipped evidence before an offline amplitude audit."""
import hashlib,json,sys,tempfile,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import analyze_original_iq_amplitude as a
class AmplitudeEvidence(unittest.TestCase):
 def fixture(self,root,data=None):
  data=data or bytes([1,2])*16380;path=root/'cyberether/run/a.ci8';path.parent.mkdir(parents=True);path.write_bytes(data)
  return {'archive':{'path':'cyberether/run/a.ci8','sha256':hashlib.sha256(data).hexdigest()},'snapshot':dict(samples=16380,source=0,rate=40000000,frequency=2447000000,error=0,raw_crc=zlib.crc32(data))}
 def test_uncorrupted_snapshot(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);row=self.fixture(r);z=a.samples(r,row);self.assertEqual(len(z),16380);self.assertEqual(z[0],1+2j)
 def test_corrupted_payload_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);row=self.fixture(r);(r/row['archive']['path']).write_bytes(bytes([3,4])*16380)
   with self.assertRaisesRegex(ValueError,'integrity'):a.samples(r,row)
 def test_clipped_payload_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);row=self.fixture(r,bytes([127,2])*16380)
   with self.assertRaisesRegex(ValueError,'Clipped'):a.samples(r,row)
 def test_hardware_gain_snapshot_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);p=r/'proof.json';p.write_text(json.dumps(dict(kind='original ESP32 attenuation hypothesis',completed=True,register_trial_qualified=True,cleanup_errors=[],gain='GAIN HARDWARE -1 0 81 0')))
   with self.assertRaisesRegex(ValueError,'gain mismatch'):a.analyze(r,[p],r/'unused')
