"""Independent WLAN54 encoder -> portable on-board DATA backend, no RF.

Puncture111001 in A0 B0 A1 B1 A2 B2 order follows MathWorks' IEEE802.11
Convolutional Encode and Puncture Streaming Samples example:
https://www.mathworks.com/help/wireless-hdl/ug/convencpunc.html
LLR convention here is positive=1 (opposite wlanBCCDecode's public API).
"""
import ctypes as C
import random
import shutil
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class Result(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('status','symbols','decoded_bits','psdu_bytes','crc_computed','crc_received','service_errors','tail_errors')]+[('seed',C.c_uint8),('final_state',C.c_uint8),('psdu',C.c_uint8*256)]

def convolutional_bits(bits):
    # Shift-register taps anchored against GNU Radio IEEE802.11 utils.cc:
    # left shift with newest bit0, octal155/117, A before B. A list of input
    # delays gives an implementation independent of the C trellis indexing.
    history=[0]*7
    out=[]
    for bit in bits:
        history=[bit]+history[:6]
        out += [sum(history[i] for i in (0,2,3,5,6))%2,
                sum(history[i] for i in (0,1,2,3,6))%2]
    return out

def encode(payload, seed=93, crc_bad=False, service_bad=False, tail_bad=False):
    """Independent list-register encoder; deliberately no imports of C model."""
    fcs=zlib.crc32(payload) ^ (1 if crc_bad else 0)
    psdu=payload+fcs.to_bytes(4,'little')
    bits=[0]*16+[byte>>b&1 for byte in psdu for b in range(8)]+[0]*6
    symbols=(len(bits)+215)//216
    bits += [0]*(symbols*216-len(bits))
    if service_bad: bits[12]=1
    lfsr=[seed>>i&1 for i in range(6,-1,-1)]
    scrambled=[]
    for bit in bits:
        feedback=lfsr[0]^lfsr[3]
        scrambled.append(bit^feedback)
        lfsr=lfsr[1:]+[feedback]
    tail=16+len(psdu)*8
    scrambled[tail:tail+6]=[0]*6
    if tail_bad: scrambled[tail]=1
    mother=convolutional_bits(scrambled)
    # Per three data bits: retain A0,B0,A1,B2. Erased B1/A2 never sent.
    punctured=[]
    for i in range(0,len(mother),6):
        punctured.extend(mother[i+j] for j in (0,1,2,5))
    output=[]
    for symbol in range(symbols):
        block=punctured[symbol*288:(symbol+1)*288]
        # First permutation:18x16 transpose. Second: groups of3 rotate.
        first=[block[row*16+col] for col in range(16) for row in range(18)]
        second=[0]*288
        for i,bit in enumerate(first):
            column=i//18
            second[(i//3)*3+(i-column)%3]=bit
        output.extend(second)
    return psdu,output

@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class Wifi64DecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        tmp=Path(cls.tmp.name)
        source=tmp/'harness.c'
        source.write_text('#include "wifi64_decode.h"\n#include "wifi64_ofdm.h"\nstatic w64d_workspace w;\nint decode(const int16_t *x,unsigned n,unsigned b,w64d_result *r){return w64d_decode(x,n,b,&w,r);}\nunsigned memory(void){return sizeof(w);}\nint demap(const w64_complex *x,int16_t *v){return w64_demap(x,v);}\nvoid link_other_ofdm_primitives(void){w64_complex x[64]={{0}},y[64],h[64];(void)w64_fft64(x,y);w64_channel(x,y,h);(void)w64_equalize(x,h,y);}\n')
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-fPIC','-shared','-I',str(ROOT/'sw'),str(source),'-o',str(tmp/'backend.so')],check=True,capture_output=True)
        cls.lib=C.CDLL(str(tmp/'backend.so'))
        cls.lib.decode.argtypes=[C.POINTER(C.c_int16),C.c_uint,C.c_uint,C.POINTER(Result)]
        cls.lib.decode.restype=C.c_int
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def run_decode(self,bits,psdu_len,noise=0,erasures=(),invert=False):
        rng=random.Random(314159)
        llrs=[round((1 if b else -1)*1000+rng.gauss(0,noise)) for b in bits]
        if invert: llrs=[-v for v in llrs]
        for i in erasures: llrs[i]=0
        llrs=[max(-32768,min(32767,x)) for x in llrs]
        arr=(C.c_int16*len(llrs))(*llrs)
        result=Result()
        rc=self.lib.decode(arr,len(llrs),psdu_len,C.byref(result))
        return rc,result
    def test_external_encoder_impulse_anchor(self):
        # Explicit impulse output from the primary GNU Radio code's
        # state=((state<<1)&0x7e)|bit; parity155 then parity117.
        # https://github.com/bastibl/gr-ieee802-11/blob/master/lib/utils.cc
        self.assertEqual(convolutional_bits([1,0,0,0,0,0,0]),
                         [1,1,0,1,1,1,1,1,0,0,1,0,1,1])

    def test_c_ofdm_demapper_to_c_decoder(self):
        class Complex(C.Structure):
            _fields_=[('i',C.c_int32),('q',C.c_int32)]
        self.lib.demap.argtypes=[C.POINTER(Complex),C.POINTER(C.c_int16)]
        expected,bits=encode(bytes((i*31+7)&255 for i in range(88)))
        # IEEE WLAN table with b0..2 on I and b3..5 on Q, sign0 negative.
        pam=(-7,7,-1,1,-5,5,-3,3)
        carriers=[k for k in range(-26,27) if k not in (-21,-7,0,7,21)]
        all_llrs=[]
        for start in range(0,len(bits),288):
            bins=(Complex*64)()
            for n,k in enumerate(carriers):
                offset=start+n*6
                label=sum(bits[offset+j]<<j for j in range(6))
                bins[k%64]=Complex(pam[label&7]*1264,pam[label>>3]*1264)
            llrs=(C.c_int16*288)()
            self.assertEqual(self.lib.demap(bins,llrs),0)
            self.assertEqual([int(v>0) for v in llrs],bits[start:start+288])
            all_llrs.extend(llrs)
        arr=(C.c_int16*len(all_llrs))(*all_llrs)
        r=Result()
        self.assertEqual(self.lib.decode(arr,len(all_llrs),len(expected),C.byref(r)),0)
        self.assertEqual(bytes(r.psdu[:len(expected)]),expected)

    def test_all_scrambler_seeds_and_native_length(self):
        payload=bytes((i*73+11)&255 for i in range(88))
        for seed in range(1,128):
            expected,bits=encode(payload,seed)
            rc,r=self.run_decode(bits,len(expected))
            self.assertEqual((rc,r.status,r.seed),(0,0,seed))
            self.assertEqual(bytes(r.psdu[:r.psdu_bytes]),expected)
            self.assertEqual((r.symbols,r.decoded_bits),(4,864))
    def test_unforced_final_state_scrambled_pad(self):
        states=set()
        for seed in (1,37,93,127):
            expected,bits=encode(b'pad is scrambled after the zero tail',seed)
            rc,r=self.run_decode(bits,len(expected))
            self.assertEqual(rc,0)
            states.add(r.final_state)
        self.assertTrue(any(states))
        self.assertGreater(len(states),1)
    def test_noise_and_erasure_correction(self):
        expected,bits=encode(bytes(range(120)))
        rc,r=self.run_decode(bits,len(expected),noise=450,erasures=range(13,len(bits),53))
        self.assertEqual((rc,r.status),(0,0))
        self.assertEqual(bytes(r.psdu[:len(expected)]),expected)
    def test_independent_64qam_mapping_and_soft_metrics(self):
        expected,bits=encode(bytes((i*19+31)&255 for i in range(88)))
        def point(label):
            b=[label>>i&1 for i in range(6)]
            # IEEE WLAN: three contiguous I bits followed by three Q bits;
            # bit0 is sign (0 negative), bit1 selects inner vs outer pair,
            # bit2 the adjacent Gray level. Table independently anchored to
            # IEEE802.11-99/074 and gr-ieee802-11 constellation_64qam_impl.
            pam=(-7,7,-1,1,-5,5,-3,3)
            return complex(pam[label&7],pam[label>>3])
        alphabet=[point(n) for n in range(64)]
        self.assertEqual(len(set(alphabet)),64)
        rng=random.Random(20261021)
        llrs=[]
        for start in range(0,len(bits),6):
            label=sum(bits[start+j]<<j for j in range(6))
            received=alphabet[label]+complex(rng.gauss(0,.18),rng.gauss(0,.18))
            distances=[abs(received-p)**2 for p in alphabet]
            for j in range(6):
                d0=min(d for n,d in enumerate(distances) if not (n>>j&1))
                d1=min(d for n,d in enumerate(distances) if n>>j&1)
                llrs.append(max(-32768,min(32767,round(500*(d0-d1)))))
        arr=(C.c_int16*len(llrs))(*llrs)
        r=Result()
        self.assertEqual(self.lib.decode(arr,len(llrs),len(expected),C.byref(r)),0)
        self.assertEqual(bytes(r.psdu[:len(expected)]),expected)

    def test_crc_service_and_tail_failures_reported(self):
        for flags,bit in (({'crc_bad':True},4),({'service_bad':True},2),({'tail_bad':True},8)):
            expected,bits=encode(bytes(range(88)),**flags)
            rc,r=self.run_decode(bits,len(expected))
            self.assertEqual(rc,1)
            self.assertTrue(r.status&bit)
    def test_bounds_min_max_and_workspace(self):
        for length in (0,1,252):
            expected,bits=encode(bytes(i%256 for i in range(length)))
            rc,r=self.run_decode(bits,len(expected))
            self.assertEqual(rc,0)
            self.assertEqual(bytes(r.psdu[:len(expected)]),expected)
        expected,bits=encode(b'abc')
        self.assertEqual(self.run_decode(bits[:-1],len(expected))[1].status,1)
        self.assertEqual(self.run_decode(bits,257)[1].status,1)
        self.assertLess(self.lib.memory(),30000)
    def test_int16_fullscale_metrics_do_not_overflow(self):
        expected,bits=encode(bytes(i&255 for i in range(252)))
        arr=(C.c_int16*len(bits))(*(32767 if b else -32768 for b in bits))
        r=Result()
        self.assertEqual(self.lib.decode(arr,len(bits),len(expected),C.byref(r)),0)
        self.assertEqual(bytes(r.psdu[:len(expected)]),expected)

    def test_wrong_polarity_and_all_erasure_fail(self):
        expected,bits=encode(bytes(range(88)))
        self.assertNotEqual(self.run_decode(bits,len(expected),invert=True)[1].status,0)
        self.assertNotEqual(self.run_decode(bits,len(expected),erasures=range(len(bits)))[1].status,0)

if __name__=='__main__': unittest.main()
