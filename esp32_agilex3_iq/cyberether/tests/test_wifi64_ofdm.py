"""Offline integer Nios primitives against independent NumPy transforms.
No device access; these tests are not OTA or a synchronization proof.
"""
import ctypes as C
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
class IQ(C.Structure):
    _fields_=[('i',C.c_int32),('q',C.c_int32)]
class Wifi64OFDM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'): raise unittest.SkipTest('C compiler required')
        cls.tmp=tempfile.TemporaryDirectory(); p=Path(cls.tmp.name)
        (p/'test.c').write_text('#include "wifi64_ofdm.h"\nint fft(const w64_complex*x,w64_complex*y){return w64_fft64(x,y);}\nvoid channel(const w64_complex*a,const w64_complex*b,w64_complex*h){w64_channel(a,b,h);}\nint eq(const w64_complex*x,const w64_complex*h,w64_complex*y){return w64_equalize(x,h,y);}\nint demap(const w64_complex*x,int16_t*y){return w64_demap(x,y);}\n')
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC','-O2','-I',str(ROOT/'sw'),str(p/'test.c'),'-o',str(p/'test.so')],check=True,capture_output=True)
        cls.lib=C.CDLL(str(p/'test.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def arr(self,z):return (IQ*64)(*[IQ(round(v.real),round(v.imag)) for v in z])
    def values(self,a):return np.array([v.i+1j*v.q for v in a])
    def test_fft_impulse_tone_random_and_range(self):
        rng=np.random.default_rng(24)
        for x in [np.eye(1,64,0)[0]*8192,np.exp(2j*np.pi*7*np.arange(64)/64)*8192,rng.integers(-16000,16000,64)+1j*rng.integers(-16000,16000,64)]:
            a=self.arr(x);out=(IQ*64)();self.assertEqual(self.lib.fft(a,out),0)
            expected=np.fft.fft(self.values(a))/64
            self.assertLess(np.max(abs(self.values(out)-expected)),7)
        a=self.arr(np.ones(64)*1048577);self.assertEqual(self.lib.fft(a,(IQ*64)()),-1)
    def test_equalizer_rotated_frequency_selective_channel(self):
        # Channel from two independent LTFs, then remove it from 48 data bins.
        signs=np.array([1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,0,1,-1,-1,1,1,-1,1,-1,1,-1,-1,-1,-1,-1,1,1,-1,-1,1,-1,1,-1,1,1,1,1])
        bins=np.arange(-26,27)%64;active=bins[bins!=0]
        h=(.8+.15*np.cos(np.arange(64)))*np.exp(1j*(.4+.1*np.sin(np.arange(64))))
        ltf=np.zeros(64,complex);ltf[bins]=signs*h[bins]*8192
        channel=(IQ*64)();self.lib.channel(self.arr(ltf),self.arr(ltf),channel)
        symbols=np.zeros(64,complex);symbols[active]=(3-5j)*1264
        out=(IQ*64)();self.assertEqual(self.lib.eq(self.arr(symbols*h),channel,out),0)
        self.assertLess(np.max(abs(self.values(out)[active]-symbols[active])),5)
        channel[1]=IQ(0,0);self.assertEqual(self.lib.eq(self.arr(symbols*h),channel,out),-2)
    def test_all_64_constellation_labels_and_carrier_order(self):
        # IEEE WLAN axis left-to-right labels: 000,001,011,010,110,111,101,100
        axis={tuple(map(int,b)):v for b,v in zip(['000','001','011','010','110','111','101','100'],range(-7,8,2))}
        carriers=[k%64 for k in range(-26,27) if k not in (-21,-7,0,7,21)]
        for start in (0,16):
            bins=np.zeros(64,complex);expected=[]
            for n,k in enumerate(carriers):
                label=tuple((int(n+start)>>j)&1 for j in range(6))
                bins[k]=1264*(axis[label[:3]]+1j*axis[label[3:]])
                expected.extend(label)
            llr=(C.c_int16*288)();self.assertEqual(self.lib.demap(self.arr(bins),llr),0)
            self.assertEqual([int(x>0) for x in llr],expected)
            self.assertTrue(all(llr))
    def test_demap_out_of_range(self):
        bins=self.arr(np.zeros(64));bins[38]=IQ(40000,0)
        self.assertEqual(self.lib.demap(bins,(C.c_int16*288)()),-1)
if __name__=='__main__':unittest.main()
