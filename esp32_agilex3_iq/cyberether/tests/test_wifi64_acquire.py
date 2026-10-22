"""Offline independent WLAN preamble + fixedpoint C qualification, no RF.
Acquisition kernel is intended for Nios; Python only synthesizes/verifies fixtures.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
class IQ(C.Structure):_fields_=[('i',C.c_int16),('q',C.c_int16)]
class Candidate(C.Structure):_fields_=[('ltf_index',C.c_uint32),('score_q15',C.c_uint32),('coarse_q32',C.c_int32)]
class Result(C.Structure):
 _fields_=[(x,C.c_uint32) for x in ('status','output_samples','input_offset','decimation','frontend_clips','ltf_index','signal_index','score_q15','stf_score_q15','candidates','rotation_clips')]+[(x,C.c_int32) for x in ('coarse_q32','fine_q32','cfo_q32')]+[('candidate',Candidate*8)]
def preamble(fs=20000000,cfo=0,snr=None,channel=(1,),prefix=96):
 signs=[1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,0,1,-1,-1,1,1,-1,1,-1,1,-1,-1,-1,-1,-1,1,1,-1,-1,1,-1,1,-1,1,1,1,1]
 f=np.zeros(64,complex);f[np.arange(-26,27)%64]=signs;long=np.fft.ifft(f)*8
 f=np.zeros(64,complex)
 f[np.array([-24,-20,-16,-12,-8,-4,4,8,12,16,20,24])%64]=np.array([1,-1,1,-1,-1,1,-1,-1,1,1,1,1])*(1+1j)*np.sqrt(13/6)
 short=np.fft.ifft(f)*8
 rng=np.random.default_rng(801)
 # The tested stage does not decode DATA; random valid OFDM occupies its span.
 data=[]
 for _ in range(5):
  f=np.zeros(64,complex);f[np.r_[1:27,38:64]]=rng.choice([-1,1],52)
  symbol=np.fft.ifft(f)*8;data.extend(np.r_[symbol[-16:],symbol])
 wave=np.r_[np.zeros(prefix),np.tile(short[:16],10),long[-32:],long,long,data,np.zeros(96)]
 wave=np.convolve(wave,np.asarray(channel))
 if fs==40000000:
  spectrum=np.fft.fft(wave);mid=(len(wave)+1)//2;expanded=np.zeros(len(wave)*2,complex)
  expanded[:mid]=spectrum[:mid];expanded[-(len(wave)-mid):]=spectrum[mid:];wave=np.fft.ifft(expanded)*2
 wave*=np.exp(2j*np.pi*cfo*np.arange(len(wave))/fs)
 if snr is not None:
  sigma=np.sqrt(np.mean(np.abs(wave)**2)*10**(-snr/10)/2);wave+=sigma*(rng.normal(size=len(wave))+1j*rng.normal(size=len(wave)))
 return wave
@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class AcquireTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
  (p/'test.c').write_text('#include "wifi64_acquire.h"\nint frontend(const int8_t*x,unsigned n,unsigned rate,w64a_complex*y,unsigned c,w64a_result*r){return w64a_frontend(x,n,rate,y,c,r);}\nint frontend_ex(const int8_t*x,unsigned n,unsigned rate,w64a_complex*y,unsigned c,w64a_result*r,unsigned conjugate){return w64a_frontend_ex(x,n,rate,y,c,r,conjugate);}\nint acquire(w64a_complex*x,unsigned n,w64a_complex*w,unsigned c,w64a_result*r){return w64a_acquire(x,n,w,c,r);}\nint angle(int x,int y){return w64a_angle(x,y);}\nvoid sine(int p,int*c,int*s){w64a_sincos(p,c,s);}\nvoid rotate(const w64a_complex*x,w64a_complex*y,unsigned n,int inc,unsigned*c){w64a_rotate(x,y,n,inc,c);}\n')
  subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC','-I',str(ROOT/'sw'),str(p/'test.c'),'-o',str(p/'test.so')],check=True,capture_output=True)
  cls.lib=C.CDLL(str(p/'test.so'));cls.lib.frontend.argtypes=[C.POINTER(C.c_int8),C.c_uint,C.c_uint,C.POINTER(IQ),C.c_uint,C.POINTER(Result)];cls.lib.frontend_ex.argtypes=cls.lib.frontend.argtypes+[C.c_uint];cls.lib.acquire.argtypes=[C.POINTER(IQ),C.c_uint,C.POINTER(IQ),C.c_uint,C.POINTER(Result)]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def raw(self,z,scale=40):
  xy=np.column_stack((np.asarray(z).real,np.asarray(z).imag))*scale
  return np.clip(np.rint(xy),-128,127).astype(np.int8).reshape(-1)
 def front(self,raw,fs=40000000,capacity=None):
  n=len(raw)//2;out=(IQ*n)();r=Result();arr=(C.c_int8*len(raw))(*raw)
  rc=self.lib.frontend(arr,n,fs,out,n if capacity is None else capacity,C.byref(r));return rc,out,r
 def values(self,a,n):return np.array([a[k].i+1j*a[k].q for k in range(n)])
 def test_frontend_exact_independent_q15_and_alias_rejection(self):
  rng=np.random.default_rng(100);raw=rng.integers(-128,128,4000,dtype=np.int16).astype(np.int8)
  rc,out,r=self.front(raw);self.assertEqual(rc,0);self.assertEqual((r.output_samples,r.input_offset,r.decimation),(936,64,2))
  n=np.arange(-64,65);h=.45*np.sinc(.45*n)*np.kaiser(129,8.6);h/=h.sum();q=np.rint(h*32768).astype(np.int64);q[64]+=32768-q.sum()
  def ref(a):
   x=np.convolve(a.astype(np.int64),q,'valid')[::2]
   return np.clip(np.sign(x)*((np.abs(x)+128)//256),-32768,32767)
  expected=ref(raw[::2])+1j*ref(raw[1::2]);self.assertTrue(np.array_equal(self.values(out,r.output_samples),expected))
  magnitudes=[]
  for hz in (4000000,13000000):
   raw=self.raw(np.exp(2j*np.pi*hz*np.arange(4096)/40000000),80)
   _,out,r=self.front(raw);magnitudes.append(np.sqrt(np.mean(abs(self.values(out,r.output_samples))**2)))
  self.assertGreater(20*np.log10(magnitudes[0]/magnitudes[1]),35)
 def test_cordic_quadrants_and_rotation(self):
  for phase in np.linspace(-.499,.499,101):
   p=round(phase*2**32);c=C.c_int();s=C.c_int();self.lib.sine(p,C.byref(c),C.byref(s))
   self.assertLess(abs((c.value+1j*s.value)/32768-np.exp(2j*np.pi*phase)),.001)
   x=round(np.cos(2*np.pi*phase)*1000000);y=round(np.sin(2*np.pi*phase)*1000000)
   angle=self.lib.angle(x,y)/2**32;self.assertLess(abs(angle-phase),.00001)
 def test_wlan20_40_cfo_noise_multipath_and_corrected_ltf(self):
  for fs,cfo,noise,ch in ((20000000,0,None,(1,)),(20000000,180000,24,(1,.25j)),(40000000,-310000,26,(1,.2,.1j)),(40000000,45000,18,(1,))):
   with self.subTest(fs=fs,cfo=cfo):
    wave=preamble(fs,cfo,noise,ch);rc,out,front=self.front(self.raw(wave),fs);self.assertEqual(rc,0)
    n=front.output_samples;before=self.values(out,n);scratch=(IQ*n)();r=Result()
    rc=self.lib.acquire(out,n,scratch,n,C.byref(r));self.assertEqual(rc,0,(r.status,r.score_q15,r.candidates))
    expected=96+192-(32 if fs==40000000 else 0)
    self.assertLessEqual(abs(r.ltf_index-expected),1);self.assertGreaterEqual(r.score_q15,14745)
    measured=r.cfo_q32*20000000/2**32;self.assertLess(abs(measured-cfo),2500)
    corrected=self.values(out,n);residual=np.angle(np.vdot(corrected[r.ltf_index:r.ltf_index+64],corrected[r.ltf_index+64:r.ltf_index+128]))*20000000/(2*np.pi*64)
    self.assertLess(abs(residual),1500);self.assertLessEqual(r.candidates,8)
 def test_no_frame_truncated_and_failures_preserve_input(self):
  rng=np.random.default_rng(8)
  for z in (np.zeros(700),np.exp(2j*np.pi*.07*np.arange(700)),rng.normal(size=700)+1j*rng.normal(size=700)):
   _,out,front=self.front(self.raw(z),20000000);n=front.output_samples;before=bytes(out);r=Result();scratch=(IQ*n)()
   self.assertNotEqual(self.lib.acquire(out,n,scratch,n,C.byref(r)),0);self.assertEqual(bytes(out),before)
  _,out,front=self.front(self.raw(preamble()[:400]),20000000);n=front.output_samples;r=Result();scratch=(IQ*n)();before=bytes(out)
  self.assertNotEqual(self.lib.acquire(out,n,scratch,n,C.byref(r)),0);self.assertEqual(bytes(out),before)
  self.assertEqual(self.front(np.zeros(400,dtype=np.int8),16000000)[2].status,2)
  self.assertEqual(self.front(np.zeros(100,dtype=np.int8))[2].status,4)
  self.assertEqual(self.front(np.zeros(400,dtype=np.int8),capacity=1)[2].status,1)
 def test_saturation_maximum_count_and_nonoverlap_guards(self):
  n=np.arange(-64,65);h=.45*np.sinc(.45*n)*np.kaiser(129,8.6);h/=h.sum()
  raw=np.column_stack((np.where(h>=0,127,-128),np.zeros(129))).astype(np.int8).reshape(-1)
  rc,out,r=self.front(raw);self.assertEqual(rc,0);self.assertEqual(out[0].i,32767);self.assertGreater(r.frontend_clips,0)
  rc,out,r=self.front(np.zeros(16380*2,dtype=np.int8));self.assertEqual((rc,r.output_samples),(0,8126))
  self.assertEqual(self.front(np.zeros(16381*2,dtype=np.int8))[2].status,1)
  data=(IQ*701)();r=Result();before=bytes(data)
  overlap=C.cast(C.byref(data,C.sizeof(IQ)),C.POINTER(IQ))
  self.assertEqual(self.lib.acquire(data,700,overlap,700,C.byref(r)),-1)
  self.assertEqual(bytes(data),before)
  large=(IQ*2)(IQ(32767,32767),IQ(32767,32767));rot=(IQ*2)();clips=C.c_uint()
  self.lib.rotate(large,rot,2,2**29,C.byref(clips))
  self.assertEqual(rot[1].i,32767);self.assertGreater(clips.value,0)
 def test_conjugation_preclip_preserves_negative128_and_filter_sign(self):
  for fs,n in ((20000000,2),(40000000,200)):
   raw=np.zeros(2*n,dtype=np.int8);raw[1::2]=-128;arr=(C.c_int8*len(raw))(*raw);out=(IQ*n)();r=Result()
   self.assertEqual(self.lib.frontend_ex(arr,n,fs,out,n,C.byref(r),1),0)
   self.assertTrue(all(out[k].q==16384 for k in range(r.output_samples)));self.assertEqual(r.frontend_clips,0)
   self.assertEqual(self.lib.frontend_ex(arr,n,fs,out,n,C.byref(r),2),-1)
  rng=np.random.default_rng(19);raw=rng.integers(-128,128,2000,dtype=np.int16).astype(np.int8)
  _,normal,r=self.front(raw);arr=(C.c_int8*len(raw))(*raw);out=(IQ*1000)();conj=Result()
  self.lib.frontend_ex(arr,1000,40000000,out,1000,C.byref(conj),1)
  self.assertTrue(np.array_equal(self.values(out,conj.output_samples),np.conj(self.values(normal,r.output_samples))))
if __name__=='__main__':unittest.main()
