"""Actual acknowledgement evidence must match all requested TX job settings."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tx_job_readback import validate_tx_on


class TXReadbackTests(unittest.TestCase):
    def test_correct_received_job_and_actual_attenuation_recorded(self):
        line='TX_ON,id=123,channel=8,backoff_qdb=120,limit_ms=500'
        result=validate_tx_on(line,dict(job=123),channel=8,backoff_qdb=120)
        self.assertEqual(result['line'],line)
        self.assertEqual(result['backoff_qdb'],120)
        self.assertIn('not calibrated',result['scope'])

    def test_wrong_job_channel_power_limit_or_missing_ack_refused(self):
        actual=dict(id=123,channel=8,backoff_qdb=120,limit_ms=500)
        for name in actual:
            bad=dict(actual);bad[name]+=1
            text='TX_ON,'+','.join(f'{k}={v}' for k,v in bad.items())
            with self.subTest(name=name):
                with self.assertRaises(ValueError):validate_tx_on(text,dict(job=123),channel=8,backoff_qdb=120)
        for text in ('FRAME_CFG,job=123','TX_ON,id=123','TX_ON,id=123,id=123,channel=8,backoff_qdb=120,limit_ms=500'):
            with self.assertRaises(ValueError):validate_tx_on(text,dict(job=123),channel=8,backoff_qdb=120)


if __name__=='__main__':unittest.main()
