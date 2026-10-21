"""Mock SPI→IQB1 paired-buffer checks; no hardware accessed."""
from pathlib import Path
import sys
import unittest
import json
import io
from contextlib import redirect_stdout
import tempfile
from unittest.mock import patch
import zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Frame
from nios_fir import PROFILES,fixed_reference
import check_spi_fir as check


def fixture(synthetic=True):
    a=np.array([[60,-20],[30,40],[-30,80],[0,20]]+[[0,0]]*16376,np.int8)
    b=fixed_reference(a,PROFILES[2],True)
    rawcrc=zlib.crc32(a.tobytes());outcrc=zlib.crc32(b.tobytes())
    common=dict(source=2,job=22,samples=16380,rate=16000000,frequency=2447000000,capture_us=0,
        error=0,length=32760,first_tick=100,last_tick=200)
    raw=Frame(kind=1,raw_crc=rawcrc,aux=0,payload=a.tobytes(),**common)
    out=Frame(kind=6,raw_crc=outcrc,aux=(rawcrc<<32)|0x80010102,payload=b.tobytes(),**common)
    before=dict(commit_count=10,reject_count=0,valid=True,sequence=39)
    after=dict(commit_count=11,reject_count=1,valid=True,sequence=40,synthetic=synthetic,
        requested_synthetic=synthetic,ingress_cycles=3000000)
    status=dict(job=22,samples=16380,source=2,raw_crc=rawcrc,filtered_crc=outcrc,
        profile=2,round=1,clips=0,cycles=114756)
    return raw,out,before,after,status


class SPIIntegratedCheckTests(unittest.TestCase):
    def test_fixed_contract_status_parse_and_rejects(self):
        status=check.spi_status('SPI 00030001 00000001 00000003 00000027 0000000b 00000002 00000300 00000001')
        self.assertEqual(status['sequence'],39)
        self.assertEqual(status['ingress_cycles'],2**32+768)
        self.assertTrue(status['synthetic']);self.assertTrue(status['valid'])
        for text in ('SPI 00030002 1 3 1 1 0 1 0','SPI 00030001 1 7 1 1 0 1 0','SPIQ0002'):
            with self.assertRaises(ValueError):check.spi_status(text)

    def test_actual_raw_filtered_association_and_integer_reference(self):
        raw,out,before,after,status=fixture()
        result=check.verify_association(raw,out,before,after,PROFILES[2],status,
            synthetic=True,profile=2,nearest=True)
        self.assertTrue(result['bit_exact'])
        self.assertEqual(result['spi_reject_counter_change'],1) # Boundary recovery may abandon stalechunks.
        self.assertEqual(result['spi_commits_advanced'],1)
        self.assertTrue(result['same_capture_association'])

    def test_cli_control_readbacks_snapshot_and_final_restore(self):
        raw,out,_,_,status=fixture(False)
        class MockBridge:
            queries=0
            baud_calls=[]
            def status(self):return dict(host_command_errors=0)
            def set_host_baud(self,baud):self.baud_calls.append(baud);return self.status()
            def __init__(self,port):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def prepare_sdr(self,*args):return 'ESP32SDR SPI_PROXY fixedfreq2447'
            def radio_command(self,source,command,prefix):
                if command=='SPI_MODE RF':return 'OK SPI_MODE RF'
                self.queries+=1
                return ('SPI 00030001 00000000 00000001 00000027 0000000a 00000000 00001000 00000000'
                    if self.queries==1 else 'SPI 00030001 00000000 00000001 00000028 0000000b 00000000 002dc6c0 00000000')
            def paired_capture(self,*args,**kwargs):return raw,out
        class MockNios:
            last=None
            def __init__(self,**kwargs):
                self.profile=1;self.nearest=0;self.pair=0;self.calls=[];MockNios.last=self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def status(self):return dict(status,configured_profile=self.profile,configured_round=self.nearest,pair=self.pair)
            def command(self,verb,*args):
                self.calls.append((verb,*args))
                if verb=='READCOEFF':return dict(bits=PROFILES[self.profile][args[0]]&65535)
                if verb=='ROUND':self.nearest=args[0];return dict(nearest=self.nearest)
                if verb=='PAIR':self.pair=args[0];return dict(enabled=self.pair)
                raise AssertionError(verb)
            def preset(self,profile):self.profile=profile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'capture';view=root/'view.json'
            MockBridge.baud_calls=[]
            argv=['check_spi_fir.py','--confirm-spi-image','--host-baud','4000000','--rf','--output',str(output),'--snapshot',str(view)]
            with patch.object(check,'ROOT',root),patch.object(check,'Bridge',MockBridge),patch.object(check,'NiosFir',MockNios),patch.object(sys,'argv',argv),redirect_stdout(io.StringIO()):
                check.main()
            proof=json.loads((output/'proof.json').read_text());snapshot=json.loads(view.read_text())
            self.assertTrue(proof['completed'])
            self.assertEqual(snapshot['status'],'PASS')
            self.assertEqual(snapshot['readback']['mode'],'rf')
            self.assertEqual(MockBridge.baud_calls,[4000000,2000000])
            self.assertEqual(snapshot['requested']['host_baud'],4000000)
            self.assertEqual(snapshot['readback']['host_baud_restored'],2000000)
            self.assertTrue(snapshot['verification']['raw_crc_valid'])
            self.assertGreater(snapshot['timing']['ingress_payload_bytes_s'],0)
            self.assertEqual(len(snapshot['provenance']['raw_sha256']),64)
            self.assertEqual((MockNios.last.profile,MockNios.last.nearest,MockNios.last.pair),(1,0,0))

    def test_stale_wrong_mode_wrong_origin_or_wrong_fir_rejected(self):
        for failure in ('stale','sequence','mode','crc','job','coeff','status','samples'):
            raw,out,before,after,status=fixture()
            taps=PROFILES[2].copy()
            if failure=='stale':after['commit_count']=10
            if failure=='sequence':after['sequence']=39
            if failure=='mode':after['synthetic']=False
            if failure=='crc':out.aux^=1<<32
            if failure=='job':out.job+=1
            if failure=='coeff':taps[0]+=1
            if failure=='status':status['raw_crc']^=1
            if failure=='samples':raw.source=0
            with self.subTest(failure=failure):
                with self.assertRaises(ValueError):check.verify_association(raw,out,before,after,taps,status,
                    synthetic=True,profile=2,nearest=True)


if __name__=='__main__':unittest.main()
