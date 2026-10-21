"""Mock real checker transactions: capture/replay provenance and CRC barriers."""
from contextlib import redirect_stdout
import argparse
import fcntl
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'cyberether'))
import check_preamble as check
from preamble_reference import scan,TRAINING


class MockPreamble:
    instances=[]
    identity=0x50520801
    corrupt_crc=False
    def __init__(self,**kwargs):
        self.calls=[];self.raw=bytearray();self.n=0;self.sps=160;self.stage='empty';self.result=None
        self.closed=False;type(self).instances.append(self)
    def commands(self,calls,timeout=12):return [self.command(*call) for call in calls]
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def command(self,verb,*args):
        self.calls.append((verb,*args))
        if verb=='PCLEAR':self.stage='empty';return {}
        if verb=='PCONFIG':
            self.n,self.sps,self.threshold=args
            return dict(samples=self.n,sps=self.sps,step=4,threshold=self.threshold,min_energy=7936)
        if verb=='PBEGIN':self.raw=bytearray();return dict(written=0)
        if verb=='PLOAD':
            assert args[0]==len(self.raw)//2
            self.raw.extend(bytes.fromhex(args[1]));return dict(written=len(self.raw)//2)
        if verb=='PFINISH':self.stage='frozen';return {}
        if verb=='PRUN':
            self.result=scan(np.frombuffer(self.raw,np.int8).reshape(-1,2),sps=self.sps,threshold_q15=self.threshold)
            self.stage='done';return {}
        if verb=='PSTATUS':
            result=dict(identity=type(self).identity,state=2 if self.stage=='frozen' else 0,errors=0,samples=self.n,
                raw_crc=zlib.crc32(self.raw)^int(type(self).corrupt_crc),source=3,job=0,rate=16000000,frequency=0,
                written=len(self.raw)//2 if self.stage in ('frozen','done') else 0,candidates=0)
            if self.stage=='done':
                r=self.result
                result.update(state=4|(32 if r['detected'] else 0),cycles=10000,candidates=len(r['starts']),
                    best_start=r['best_start'],best_score=r['best_score_q15'],
                    best_r=r['best_sum_real'],best_i=r['best_sum_imag'],best_energy=r['best_energy'])
            return result
        if verb=='PTRACES':
            offset,count=args
            return dict(index=offset,count=count,**{'v'+str(k):self.result['scores_q15'][offset+k] for k in range(count)})
        raise AssertionError(verb)


class PreambleCheckerTests(unittest.TestCase):
    def fixture(self,root):
        n=5120;sps=160;iq=np.zeros((n,2),np.int8)
        for k,state in enumerate(TRAINING):
            z=60*np.exp(-.5j*np.pi*state);iq[k*sps:(k+1)*sps]=np.rint([z.real,z.imag])
        path=root/'capture.ci8';path.write_bytes(iq.tobytes())
        run=root/'cyberether/run';run.mkdir(parents=True)
        (run/'active-fpga.json').write_text(json.dumps(dict(checkpoint=8,fpga_preamble=True,sha256='a'*64,source_fingerprint='b'*64)))
        return argparse.Namespace(output=root/'out',snapshot=root/'snapshot.json',symbol_us=10,
            threshold=24576,input=path,synthetic=False,passive=False,port=None)

    def run_checker(self,root,args):
        with patch.object(check,'ROOT',root),patch.object(check,'NiosFir',MockPreamble),redirect_stdout(io.StringIO()):
            return check.run(args)

    def test_replay_uses_received_bytes_source3_and_complete_trace_without_tx(self):
        MockPreamble.instances=[];MockPreamble.identity=0x50520801;MockPreamble.corrupt_crc=False
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);args=self.fixture(root);result=self.run_checker(root,args)
            instance=MockPreamble.instances[-1]
            self.assertTrue(result['completed']);self.assertEqual(result['provenance']['kind'],'saved_iq_replay')
            self.assertFalse(result['tx_started']);self.assertEqual(result['frozen']['source'],3)
            self.assertEqual(bytes(instance.raw),args.input.read_bytes())
            self.assertTrue(result['verification']['full_trace_bit_exact'])
            self.assertEqual(result['plots']['correlation']['fpga'],result['plots']['correlation']['reference'])
            self.assertTrue(instance.closed);self.assertEqual(sum(c[0]=='PCLEAR' for c in instance.calls),2)
            self.assertTrue(all(c[0].startswith('P') for c in instance.calls))
            with (root/'cyberether/run/rf-link-capture.lock').open('a') as lease:
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB) # Ownership released evenafterallJTAGwork.

    def test_actual_identity_blocks_upload_and_manifest_is_only_hint(self):
        MockPreamble.identity=0xdeadbeef;MockPreamble.corrupt_crc=False
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);args=self.fixture(root)
            with self.assertRaisesRegex(RuntimeError,'Actual FPGA preamble identity'):self.run_checker(root,args)
            self.assertEqual([c[0] for c in MockPreamble.instances[-1].calls],['PSTATUS'])
            result=json.loads((args.output/'proof.json').read_text())
            self.assertEqual(result['status'],'ERROR');self.assertFalse(result['completed'])
        MockPreamble.identity=0x50520801

    def test_frozen_input_crc_mismatch_blocks_run_and_still_clears_detector(self):
        MockPreamble.identity=0x50520801;MockPreamble.corrupt_crc=True
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);args=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'Frozen buffer'):self.run_checker(root,args)
            instance=MockPreamble.instances[-1]
            self.assertFalse(any(c[0]=='PRUN' for c in instance.calls))
            self.assertEqual(sum(c[0]=='PCLEAR' for c in instance.calls),2);self.assertTrue(instance.closed)
            result=json.loads((args.output/'proof.json').read_text())
            self.assertEqual(result['status'],'ERROR')
        MockPreamble.corrupt_crc=False


if __name__=='__main__':unittest.main()
