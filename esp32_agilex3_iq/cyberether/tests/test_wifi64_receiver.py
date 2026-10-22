"""Full synthetic WLAN54 waveform -> portable Nios C receiver prototype.
No runtime host receiver, RF hardware or certification claim. NumPy creates
independent STF/LTF/OFDM/Gray mapping/pilots; offline encoder fixtures are from
scripts/wifi64_vectors.py, independently anchored to primary WLAN conventions.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from wifi64_vectors import encode,native_frame
from test_wifi64_acquire import Result as AcquireResult
from test_wifi64_signal import Result as SignalResult
from test_wifi64_decode import Result as PacketResult
class IQ(C.Structure):_fields_=[('i',C.c_int32),('q',C.c_int32)]
class Result(C.Structure):
 _fields_=[(name,C.c_uint32) for name in ('status','stage','accepted','candidates_attempted','capture_clipped_components','equalizer_clips','data_points','data_symbols')]+[('candidate_status',C.c_uint32*8),('candidate_ltf',C.c_uint32*8),('pilot_phase_q32',C.c_int32*11),('frontend',AcquireResult),('acquisition',AcquireResult),('signal',SignalResult),('packet',PacketResult),('constellation',IQ*480)]
def mother(bits):
 history=[0]*7;out=[]
 for b in bits:
  history=[b]+history[:6];out.extend(sum(history[i] for i in taps)&1 for taps in ((0,2,3,5,6),(0,1,2,3,6)))
 return out

def waveform(cfo=0,snr=None,channel=(1,),crc_bad=False,parity_bad=False,printed_rate=3,prefix=96):
 expected,coded=encode(native_frame(),crc_bad=crc_bad)
 sig=[printed_rate>>i&1 for i in (3,2,1,0)]+[0]+[len(expected)>>i&1 for i in range(12)]
 sig+=[(sum(sig)&1)^int(parity_bad)]+[0]*6
 coded_signal=mother(sig);interleaved_signal=[coded_signal[row*16+col] for col in range(16) for row in range(3)]
 data_carriers=np.array([k for k in range(-26,27) if k not in (-21,-7,0,7,21)])%64
 pilots=np.array([-21,-7,7,21])%64
 # Independent IEEE axis labels written in left-to-right geometric order.
 labels=('000','001','011','010','110','111','101','100');axis={tuple(map(int,b)):v for b,v in zip(labels,range(-7,8,2))}
 state=127;polarities=[]
 for _ in range(len(coded)//288+1):
  feedback=((state>>6)^(state>>3))&1;polarities.append(1-2*feedback);state=((state<<1)|feedback)&127
 symbols=[];expected_points=[]
 for s in range(len(coded)//288+1):
  f=np.zeros(64,complex)
  if s==0:f[data_carriers]=np.array(interleaved_signal)*2-1
  else:
   block=coded[(s-1)*288:s*288];points=[]
   for k in range(0,288,6):points.append((axis[tuple(block[k:k+3])]+1j*axis[tuple(block[k+3:k+6])])/np.sqrt(42))
   f[data_carriers]=points;expected_points.extend(points)
  f[pilots]=np.array([1,1,1,-1])*polarities[s]
  time=np.fft.ifft(f)*8*np.exp(1j*.12*np.sin(s))
  symbols.extend(np.r_[time[-16:],time])
 signs=[1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,0,1,-1,-1,1,1,-1,1,-1,1,-1,-1,-1,-1,-1,1,1,-1,-1,1,-1,1,-1,1,1,1,1]
 f=np.zeros(64,complex);f[np.arange(-26,27)%64]=signs;long=np.fft.ifft(f)*8
 f=np.zeros(64,complex);f[np.array([-24,-20,-16,-12,-8,-4,4,8,12,16,20,24])%64]=np.array([1,-1,1,-1,-1,1,-1,-1,1,1,1,1])*(1+1j)*np.sqrt(13/6);short=np.fft.ifft(f)*8
 x=np.r_[np.zeros(prefix),np.tile(short[:16],10),long[-32:],long,long,symbols,np.zeros(96)]
 x=np.convolve(x,np.asarray(channel));spectrum=np.fft.fft(x);mid=(len(x)+1)//2;expanded=np.zeros(2*len(x),complex);expanded[:mid]=spectrum[:mid];expanded[-(len(x)-mid):]=spectrum[mid:];x=np.fft.ifft(expanded)*2
 x*=np.exp(2j*np.pi*cfo*np.arange(len(x))/40000000)
 if snr is not None:
  rng=np.random.default_rng(64);sigma=np.sqrt(np.mean(abs(x)**2)*10**(-snr/10)/2);x+=sigma*(rng.normal(size=len(x))+1j*rng.normal(size=len(x)))
 raw=np.clip(np.rint(np.column_stack((x.real,x.imag))*32),-128,127).astype(np.int8).reshape(-1)
 return raw,expected,np.asarray(expected_points)

@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class ReceiverTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
  (p/'test.c').write_text('#include "wifi64_receiver.h"\nstatic w64r_workspace w;\nint decode(const int8_t*x,unsigned n,unsigned rate,w64r_result*r){return w64r_decode(x,n,rate,&w,r);}\nunsigned memory(void){return sizeof(w);}\nunsigned result_size(void){return sizeof(w64r_result);}\n')
  process=subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC','-I',str(ROOT/'sw'),str(p/'test.c'),'-o',str(p/'test.so')],capture_output=True,text=True)
  if process.returncode:raise RuntimeError(process.stderr)
  cls.lib=C.CDLL(str(p/'test.so'));cls.lib.decode.argtypes=[C.POINTER(C.c_int8),C.c_uint,C.c_uint,C.POINTER(Result)]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def decode(self,raw,rate=40000000):
  a=(C.c_int8*len(raw))(*raw);r=Result();rc=self.lib.decode(a,len(raw)//2,rate,C.byref(r));return rc,r
 def test_clean_cfo_multipath_noise_full_packet_and_constellation(self):
  for cfo,snr,ch in ((0,None,(1,)),(120000,30,(1,.18+.07j)),(-210000,27,(1,.1j))):
   with self.subTest(cfo=cfo,snr=snr):
    raw,expected,points=waveform(cfo,snr,ch);rc,r=self.decode(raw)
    self.assertEqual((rc,r.status,r.accepted,r.stage),(0,0,1,5),(r.status,r.stage,r.signal.status,r.packet.status))
    self.assertEqual((r.signal.rate_code,r.signal.rate_mbps,r.signal.psdu_bytes),(12,54,92))
    self.assertEqual(bytes(r.packet.psdu[:92]),expected);self.assertEqual(r.packet.status,0)
    self.assertEqual((r.data_symbols,r.data_points),(4,192));self.assertLessEqual(r.candidates_attempted,8)
    actual=np.array([r.constellation[k].i+1j*r.constellation[k].q for k in range(r.data_points)])/8192
    self.assertLess(np.sqrt(np.mean(abs(actual-points)**2)),.12)
 def test_bad_fcs_retains_decoded_payload_and_points(self):
  raw,expected,_=waveform(crc_bad=True);rc,r=self.decode(raw)
  self.assertEqual((rc,r.accepted,r.status,r.packet.status),(1,0,256,4))
  self.assertEqual(bytes(r.packet.psdu[:92]),expected);self.assertEqual(r.data_points,192)
  self.assertNotEqual(r.packet.crc_received,r.packet.crc_computed)
 def test_bad_header_unsupported_rate_and_truncated_data(self):
  for kwargs,status in (({'parity_bad':True},32),({'printed_rate':1},64),({'printed_rate':13},64)):
   rc,r=self.decode(waveform(**kwargs)[0]);self.assertEqual((rc,r.accepted,r.status),(1,0,status))
  raw,_,_=waveform();rc,r=self.decode(raw[:(96+320+80+40)*4]);self.assertEqual((rc,r.accepted,r.status),(1,0,8));self.assertEqual(r.signal.rate_mbps,54)
 def test_noenergy_rate_bounds_and_workspace_size(self):
  self.assertEqual(self.decode(np.zeros(2000,dtype=np.int8))[1].status,4)
  self.assertEqual(self.decode(np.zeros(2000,dtype=np.int8),16000000)[1].status,64)
  self.assertLess(self.lib.memory()+C.sizeof(Result),128*1024-8192)
  self.assertEqual(self.lib.result_size(),C.sizeof(Result))
 def test_alternate_candidate_retains_rejection_before_valid_packet(self):
  unsupported=waveform(printed_rate=1)[0];valid,expected,_=waveform()
  rc,r=self.decode(np.r_[unsupported,valid])
  self.assertEqual((rc,r.accepted,r.candidates_attempted),(0,1,2))
  self.assertEqual(list(r.candidate_status[:2]),[64,0])
  self.assertEqual(bytes(r.packet.psdu[:92]),expected)
  self.assertGreater(r.candidate_ltf[1],r.candidate_ltf[0])
if __name__=='__main__':unittest.main()
