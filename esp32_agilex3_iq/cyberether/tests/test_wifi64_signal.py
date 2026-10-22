"""Offline L-SIG kernel fixtures; no runtime host DSP or OTA qualification.

Primary reference: gr-ieee802-11 signal_field_impl.cc emits RATE MSB first,
LENGTH LSB first, parity over17bits, sixzero tail; utils.cc 133/171 reversed.
frame_equalizer_impl.cc parses first wirebit as bit0:54->12,48->8,6->11.
https://github.com/bastibl/gr-ieee802-11/blob/maint-3.10/lib/signal_field_impl.cc
https://github.com/bastibl/gr-ieee802-11/blob/maint-3.10/lib/frame_equalizer_impl.cc
"""
import ctypes as C
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
class Result(C.Structure):
 _fields_=[(n,C.c_uint32) for n in ('status','rate_code','rate_mbps','psdu_bytes','data_symbols','n_bpsc','n_cbps','n_dbps','code_numerator','code_denominator','qam64','backend54_supported','unforced_state','tail_metric_gap')]+[('bits',C.c_uint8*24)]
RATES=[(0xD,6,24),(0xF,9,36),(0x5,12,48),(0x7,18,72),(0x9,24,96),(0xB,36,144),(0x1,48,192),(0x3,54,216)]
def fixture(printed_rate=3,length=92,reserved=False,parity_bad=False,tail_bad=False):
 # Primary TX implementation sends MSB-first RATE; LENGTH remains LSB-first.
 bits=[printed_rate>>i&1 for i in (3,2,1,0)]+[int(reserved)]+[length>>i&1 for i in range(12)]
 bits+=[(sum(bits)&1)^int(parity_bad)]+[0]*6
 if tail_bad:bits[-1]=1
 # Independent delay-line tap form, not an import of the decoder/model.
 history=[0]*7;coded=[]
 for bit in bits:
  history=[bit]+history[:6]
  coded.extend(sum(history[k] for k in taps)&1 for taps in ((0,2,3,5,6),(0,1,2,3,6)))
 # BPSK has only the16-column transpose; no second QAM permutation.
 interleaved=[coded[row*16+col] for col in range(16) for row in range(3)]
 return bits,[(1000 if bit else -1000) for bit in interleaved]
@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class SignalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
  (p/'test.c').write_text('#include "wifi64_signal.h"\nint decode(const int16_t*x,unsigned n,w64s_result*r){return w64s_decode(x,n,r);}\n')
  subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC','-I',str(ROOT/'sw'),str(p/'test.c'),'-o',str(p/'test.so')],check=True,capture_output=True)
  cls.lib=C.CDLL(str(p/'test.so'));cls.lib.decode.argtypes=[C.POINTER(C.c_int16),C.c_uint,C.POINTER(Result)];cls.lib.decode.restype=C.c_int
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def decode(self,values,count=48):
  a=(C.c_int16*len(values))(*values);r=Result();rc=self.lib.decode(a,count,C.byref(r));return rc,r
 def test_all_eight_rates_lengths_and_wire_rate_convention(self):
  for printed,rate,dbps in RATES:
   for length in (4,92,255,4095):
    with self.subTest(rate=rate,length=length):
     bits,llr=fixture(printed,length);rc,r=self.decode(llr)
     self.assertEqual((rc,r.status,r.rate_mbps,r.psdu_bytes),(0,0,rate,length))
     self.assertEqual(list(r.bits),bits);self.assertEqual(r.data_symbols,(22+8*length+dbps-1)//dbps)
     self.assertEqual(r.qam64,int(rate>=48));self.assertEqual(r.backend54_supported,int(rate==54))
     self.assertEqual(r.rate_code,sum(bits[i]<<i for i in range(4)))
  self.assertEqual(self.decode(fixture(3)[1])[1].rate_code,12)
  self.assertEqual(self.decode(fixture(1)[1])[1].rate_code,8)
  self.assertEqual(self.decode(fixture(13)[1])[1].rate_code,11)
 def test_bad_reserved_parity_tail_and_rate(self):
  for kwargs,flag in (({'reserved':True},4),({'parity_bad':True},8),({'tail_bad':True},16),({'printed_rate':0},32)):
   rc,r=self.decode(fixture(**kwargs)[1]);self.assertEqual(rc,1);self.assertTrue(r.status&flag,(kwargs,r.status))
 def test_short_length_and_input_bounds(self):
  for n in (0,1,3):self.assertTrue(self.decode(fixture(length=n)[1])[1].status&64)
  rc,r=self.decode([0]*48);self.assertEqual((rc,r.status),(1,2))
  for n in (0,47,49):self.assertEqual(self.decode([1000]*48,n)[1].status,1)
 def test_partial_erasure_noise_and_fullscale(self):
  bits,llr=fixture();rng=random.Random(123)
  values=[max(-32768,min(32767,round(v+rng.gauss(0,180)))) for v in llr]
  for n in (2,12,27,41):values[n]=0
  self.assertEqual(self.decode(values)[0],0)
  self.assertEqual(list(self.decode(values)[1].bits),bits)
  self.assertEqual(self.decode([32767 if x>0 else -32768 for x in llr])[0],0)
 def test_legacy6_external_reference_anchor(self):
  # Immutable fixture crosschecked against the older RF-qualified project's
  # wifi_phy_reference.convolutional_encode and terminated Viterbi, LENGTH92.
  wire='101100110000100011111111101001010100111000011011'
  llr=[1000 if bit=='1' else -1000 for bit in wire]
  rc,r=self.decode(llr)
  self.assertEqual((rc,r.rate_code,r.rate_mbps,r.psdu_bytes),(0,11,6,92))
  bits,generated=fixture(13,92)
  self.assertEqual(generated,llr);self.assertEqual(list(r.bits),bits)
  self.assertEqual(self.lib.decode(None,48,C.byref(Result())),-1)
if __name__=='__main__':unittest.main()
