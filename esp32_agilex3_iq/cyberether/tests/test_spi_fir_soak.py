"""Pure snapshot-soak accounting; hardware is never opened."""
from pathlib import Path
import sys
import unittest
import json
import tempfile
import zlib
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from soak_spi_fir import summary
import soak_spi_fir as soak
from iq_bridge import Frame
from nios_fir import PROFILES,fixed_reference


class SoakSummaryTests(unittest.TestCase):
    def test_partial_failed_attempt_preserves_verified_modes_and_rejects(self):
        rows=[dict(mode=mode,verification=dict(samples=16380,spi_reject_counter_change=rejects),
            timing=dict(end_to_end_s=1.)) for mode,rejects in [('synthetic',2),('rf',1)]]
        result=summary(rows,3,'CRC mismatch')
        self.assertEqual(result['attempts'],3)
        self.assertEqual(result['verified_pairs'],2)
        self.assertEqual(result['failed_attempts'],1)
        self.assertEqual(result['observed_spi_reject_counter_advance'],3)
        self.assertEqual(result['samples_verified'],32760)
        self.assertEqual(result['synthetic_pairs'],1);self.assertEqual(result['rf_pairs'],1)
        self.assertIsNone(result['packet_drop_rate'])
        self.assertIn('not continuous',result['unobserved_gaps'])

    def test_known_failed_attempt_rejects_are_not_lost_or_double_counted(self):
        active=dict(index=0,spi_before={'reject_count':5},spi_after={'reject_count':9})
        result=summary([],1,'Bad packet',active)
        self.assertEqual(result['observed_spi_reject_counter_advance'],4)
        self.assertEqual(result['failed_attempt_spi_reject_counter_advance'],4)
        row=dict(index=0,mode='rf',verification=dict(samples=16380,spi_reject_counter_change=4),timing=dict(end_to_end_s=1.))
        result=summary([row],1,'UART liveness failure',active)
        self.assertEqual(result['observed_spi_reject_counter_advance'],4)
        self.assertIsNone(result['failed_attempt_spi_reject_counter_advance'])

    def test_fast_readback_preserves_per_pair_proof_and_finishes_snapshot_after_restore(self):
        class MockBridge:
            current=None
            def __init__(self,port):
                self.count=0;self.synthetic=True;self.raw=None;self.out=None;MockBridge.current=self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def prepare_sdr(self,*args):return 'ESP32SDR SPI_PROXY'
            def control(self,*args):pass
            def status(self):return dict(host_command_errors=0)
            def radio_command(self,source,command,prefix):
                if command.startswith('SPI_MODE '):
                    self.synthetic=command.endswith('SYNTH');return 'OK '+command
                if command=='SPI?':
                    flags=(1 if self.count else 0)|(2 if self.synthetic else 0)
                    return f'SPI 00030001 {int(self.synthetic):08x} {flags:08x} {self.count:08x} {self.count:08x} 00000000 002dc6c0 00000000'
                if command=='INFO':return 'TX_PROBE,v=5,busy=0'
                if command=='MODE?':return 'RF_MODE,SDR,baud=2000000'
                raise AssertionError(command)
            def paired_capture(self,*args,**kwargs):
                self.count+=1
                raw=bytes((n*37+11)&255 for n in range(32760))
                a=np.frombuffer(raw,np.int8).reshape(-1,2);filtered=fixed_reference(a,PROFILES[2],True).tobytes()
                crc=zlib.crc32(raw);common=dict(source=2,job=self.count,samples=16380,rate=16000000,frequency=2447000000,capture_us=0,error=0,length=32760,first_tick=100,last_tick=200)
                self.raw=Frame(kind=1,raw_crc=crc,aux=0,payload=raw,**common)
                self.out=Frame(kind=6,raw_crc=zlib.crc32(filtered),aux=(crc<<32)|0x80010102,payload=filtered,**common)
                return self.raw,self.out
        class MockNios:
            current=None
            interrupt_read=None
            def __init__(self,**kwargs):
                self.profile=1;self.nearest=0;self.pair=0;self.reads=0;MockNios.current=self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def preset(self,profile):self.profile=profile
            def command(self,verb,*args):
                if verb=='READCOEFF':
                    self.reads+=1
                    if self.reads==MockNios.interrupt_read:raise KeyboardInterrupt()
                    return dict(bits=PROFILES[self.profile][args[0]]&65535)
                if verb=='PAIR':self.pair=args[0];return dict(enabled=self.pair)
                if verb=='ROUND':self.nearest=args[0];return dict(nearest=self.nearest)
                raise AssertionError(verb)
            def status(self):
                bridge=MockBridge.current
                return dict(configured_profile=self.profile,configured_round=self.nearest,pair=self.pair,
                    job=bridge.count,samples=16380,source=2,profile=2,round=1,clips=0,cycles=114756,
                    raw_crc=bridge.raw.raw_crc if bridge.raw else 0,filtered_crc=bridge.out.raw_crc if bridge.out else 0)
        reads=[]
        for fast in (False,True):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);out=root/'out';view=root/'view.json'
                argv=['soak_spi_fir.py','--confirm-spi-image','--captures','2','--output',str(out),'--snapshot',str(view)]
                if fast:argv.append('--fast-readback')
                with patch.object(soak,'ROOT',root),patch.object(soak,'Bridge',MockBridge),patch.object(soak,'NiosFir',MockNios),patch.object(sys,'argv',argv),redirect_stdout(io.StringIO()):
                    soak.main()
                proof=json.loads((out/'proof.json').read_text());snapshot=json.loads(view.read_text())
                self.assertTrue(proof['completed']);self.assertEqual(proof['summary']['verified_pairs'],2)
                self.assertEqual(snapshot['status'],'PASS');self.assertTrue(snapshot['batch']['completed'])
                self.assertEqual(snapshot['batch']['index'],1);self.assertEqual(snapshot['readback']['mode'],'rf')
                self.assertTrue(snapshot['readback']['final_coefficient_readback_verified'])
                self.assertEqual((MockNios.current.profile,MockNios.current.nearest,MockNios.current.pair),(1,0,0))
                reads.append(MockNios.current.reads)
        self.assertEqual(reads[0]-reads[1],32) # Two16-register per-pair reads skipped only in opt-in mode.
        # Cancel after all pairs, during final coefficient verification. A blank
        # KeyboardInterrupt must not turn the completed row count into PASS.
        MockNios.interrupt_read=33
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'out';view=root/'view.json'
            argv=['soak_spi_fir.py','--confirm-spi-image','--captures','2','--fast-readback','--output',str(out),'--snapshot',str(view)]
            with patch.object(soak,'ROOT',root),patch.object(soak,'Bridge',MockBridge),patch.object(soak,'NiosFir',MockNios),patch.object(sys,'argv',argv),redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):soak.main()
            proof=json.loads((out/'proof.json').read_text());snapshot=json.loads(view.read_text())
            self.assertFalse(proof['completed']);self.assertEqual(proof['error'],'KeyboardInterrupt')
            self.assertEqual(snapshot['status'],'ERROR')
            self.assertEqual((MockNios.current.profile,MockNios.current.nearest,MockNios.current.pair),(1,0,0))


    def test_no_attempt_is_not_zero_error_hardware_evidence(self):
        result=summary([],0)
        self.assertEqual(result['verified_pairs'],0)
        self.assertIsNone(result['packet_drop_rate'])


if __name__=='__main__':unittest.main()
