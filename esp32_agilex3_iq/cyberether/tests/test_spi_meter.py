import unittest,struct,zlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spi_meter import *
class SPIMeter(unittest.TestCase):
 def fixture(self,valid=True,commits=9):
  raw=bytes([128,128,127,127,128,127,127,128])+bytes(32752)
  ref=integer_reference(raw)
  body=struct.pack('<4sBBBBIIIIQIIIQII',b'SPM1',1,2|int(valid),0,0,42,commits,3,ref['samples'],ref['power_sum'],ref['peak_power'],ref['clip_samples'],ref['clip_components'],2_771_000,len(raw),32)
  return raw,body+struct.pack('<I',zlib.crc32(body))
 def test_rails_and_valid_meter(self):
  raw,wire=self.fixture();m=decode_summary(wire);v=verify(m,raw,42,True,8)
  self.assertEqual(v['power_sum'],130052);self.assertEqual(v['peak_power'],32768)
  self.assertEqual(v['clip_samples'],4);self.assertEqual(v['clip_components'],8)
  self.assertTrue(v['reference_match']);self.assertGreater(v['ingress_payload_bytes_s'],500000)
 def test_summary_corruption(self):
  _,wire=self.fixture()
  for at in (0,4,8,24,44,60,63):
   bad=bytearray(wire);bad[at]^=1
   with self.assertRaises(ValueError):decode_summary(bad)
  with self.assertRaises(ValueError):decode_summary(wire[:-1])
 def test_stale_and_invalid_never_pass(self):
  raw,wire=self.fixture();m=decode_summary(wire)
  for change in [dict(valid=False),dict(last_error=4),dict(sequence=41),dict(synthetic=False),dict(power_sum=0),dict(chunks=31),dict(ingress_cycles=0)]:
   with self.assertRaises(ValueError):verify(dict(m,**change),raw,42,True,8)
  with self.assertRaises(ValueError):verify(m,raw,42,True,9)
  with self.assertRaises(ValueError):verify(m,raw,42,True,10)
 def test_commit_wrap_and_zero(self):
  raw,wire=self.fixture(commits=0);m=decode_summary(wire)
  self.assertTrue(verify(m,raw,42,True,0xffffffff)['reference_match'])
  self.assertEqual(integer_reference(bytes(8))['power_sum'],0)
  with self.assertRaises(ValueError):integer_reference(b'x')
if __name__=='__main__':unittest.main()
