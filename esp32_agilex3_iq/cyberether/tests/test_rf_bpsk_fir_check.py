"""Same-buffer FIR verification and bounded RF timing tests; mock transport only."""
from collections import deque
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'cyberether'))
import check_rf_bpsk_fir as check
from iq_bridge import Frame
from nios_fir import PROFILES,fixed_reference


def make_pair(samples=16380):
    a=np.zeros((samples,2),np.int8);a[:4]=[[30,-20],[20,50],[-30,60],[60,-40]]
    b=fixed_reference(a,PROFILES[2],True)
    rawcrc=zlib.crc32(a.tobytes());filteredcrc=zlib.crc32(b.tobytes())
    common=dict(source=0,job=9,samples=samples,rate=16000000,frequency=2447000000,
                capture_us=1,error=0,length=2*samples,first_tick=100,last_tick=200)
    raw=Frame(kind=1,raw_crc=rawcrc,aux=0,payload=a.tobytes(),**common)
    out=Frame(kind=6,raw_crc=filteredcrc,aux=(rawcrc<<32)|0x80010102,payload=b.tobytes(),**common)
    status=dict(job=9,samples=samples,source=0,raw_crc=rawcrc,filtered_crc=filteredcrc,
                round=1,profile=2,clips=0,cycles=123456)
    return raw,out,status


class FIRProofTests(unittest.TestCase):
    def test_same_capture_bitexact_and_rounding_descriptor(self):
        raw,out,status=make_pair(32)
        proof=check.verify_pair(raw,out,PROFILES[2],status)
        self.assertEqual(proof['max_reference_error'],0)
        self.assertTrue(proof['bit_exact'])
        self.assertTrue(proof['round_nearest'])
        out.payload=bytes([out.payload[0]^1])+out.payload[1:]
        with self.assertRaises(AssertionError):check.verify_pair(raw,out,PROFILES[2],status)

    def test_wrong_association_or_original_crc_rejected(self):
        raw,out,status=make_pair(32)
        out.last_tick+=1
        with self.assertRaises(ValueError):check.verify_pair(raw,out,PROFILES[2],status)
        out.last_tick-=1;out.aux^=1<<32
        with self.assertRaises(ValueError):check.verify_pair(raw,out,PROFILES[2],status)
        out.aux^=1<<32;out.aux^=256
        with self.assertRaises(ValueError):check.verify_pair(raw,out,PROFILES[2],status)

    def test_raw_header_stops_tx_and_late_filtered_transfer_is_allowed(self):
        raw,out,_=make_pair()
        clock=[100.]
        class MockBridge:
            responses=deque()
            stopped=[]
            def submit(self,*args):clock[0]=100.1;return 9
            def radio_write(self,source,text):self.stopped.append((clock[0],source,text))
            def read_frame(self,timeout,on_capture_header):
                if not self.stopped:
                    on_capture_header(raw)
                    return raw
                clock[0]=101.
                return out
        b=MockBridge()
        with patch.object(check.time,'monotonic',lambda:clock[0]):
            a,f,timing=check.capture_pair(b,0,100.)
        self.assertIs(a,raw);self.assertIs(f,out)
        self.assertAlmostEqual(timing['raw_header_elapsed_seconds'],.1)
        self.assertEqual(timing['full_pair_elapsed_seconds'],1.)
        self.assertEqual(b.stopped[0],(100.1,1,'STOP\n'))

    def test_late_raw_header_fails_even_when_pair_is_valid(self):
        raw,out,_=make_pair()
        class MockBridge:
            responses=deque([raw,out])
            def submit(self,*args):return 9
            def radio_write(self,*args):pass
        with self.assertRaises(RuntimeError):check.capture_pair(MockBridge(),0,time.monotonic()-.5)


if __name__=='__main__':unittest.main()
