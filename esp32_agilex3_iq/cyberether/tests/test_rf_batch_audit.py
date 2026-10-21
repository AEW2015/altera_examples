"""Offline raw integrity/batch boundary tests; fixtures never represent RF tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rf_batch_audit import discover_proofs,audit_raw,validate_audit_snapshot


class RFBatchAuditTests(unittest.TestCase):
    def fixture(self,root):
        raw=np.array([[1,-2],[3,4]],np.int8).tobytes()
        outcome=dict(payload=165,crc_received=114,crc_ok=True,sync_errors=0)
        report=dict(valid_frames=1,acquired_frames=1,acquisition_failures=0,crc_failures=0,candidates=[outcome])
        row=dict(config={'period_us':8},transport=dict(samples=2,length=4,rate=16000000,
            raw_crc=zlib.crc32(raw),payload_sha256=hashlib.sha256(raw).hexdigest()),report=report)
        path=root/'batch'/'proof.json';path.parent.mkdir()
        path.write_text(json.dumps(dict(kind='physical_rf_bpsk',completed=True,rows=[row])))
        (path.parent/'capture-000.ci8').write_bytes(raw)
        return path,row,report

    def test_explicit_recursive_paths_dedup_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,_,_=self.fixture(root)
            proofs=discover_proofs([path],[root])
            self.assertEqual(proofs,[path.resolve()])
            result=audit_raw(proofs,require_complete=True)
            self.assertEqual(result['captures_checked'],1)
            self.assertTrue(result['raw_crc_sha_length_verified'])
            raw=path.parent/'capture-000.ci8';raw.write_bytes(b'abcd')
            with self.assertRaises(ValueError):audit_raw(proofs)

    def test_partial_proof_explicit_and_refused_when_complete_required(self):
        with tempfile.TemporaryDirectory() as temp:
            path,row,_=self.fixture(Path(temp))
            path.write_text(json.dumps(dict(kind='physical_rf_bpsk',completed=False,error='interrupted',rows=[row])))
            result=audit_raw([path])
            self.assertFalse(result['proofs'][0]['completed'])
            self.assertEqual(result['proofs'][0]['error'],'interrupted')
            with self.assertRaises(ValueError):audit_raw([path],require_complete=True)

    def test_independent_redecode_has_no_known_payload_and_detects_disagreement(self):
        with tempfile.TemporaryDirectory() as temp:
            path,_,report=self.fixture(Path(temp))
            with patch('rf_bpsk.receive',return_value=report) as receive:
                result=audit_raw([path],redecode=True)
            self.assertTrue(result['independently_redecoded_without_known_payload'])
            self.assertNotIn('known_payload',receive.call_args.kwargs)
            self.assertNotIn('expected_payload',receive.call_args.kwargs)
            report=dict(report,valid_frames=0)
            with patch('rf_bpsk.receive',return_value=report):
                with self.assertRaises(ValueError):audit_raw([path],redecode=True)

    def test_changed_live_proof_cannot_reuse_byte_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            path,_,_=self.fixture(Path(temp))
            result=audit_raw([path])
            validate_audit_snapshot(result)
            path.write_text(path.read_text()+'\n')
            with self.assertRaises(ValueError):validate_audit_snapshot(result)

    def test_synthetic_excluded_even_if_files_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'proof.json';path.write_text(json.dumps(dict(kind='synthetic_bpsk',rows=[{}])))
            result=audit_raw([path])
            self.assertEqual(result['non_rf_proofs_excluded'],1)
            self.assertEqual(result['captures_checked'],0)


if __name__=='__main__':unittest.main()
