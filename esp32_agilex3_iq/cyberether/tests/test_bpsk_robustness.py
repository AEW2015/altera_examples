"""Offline training-only timing audit; no hardware or decoder replacement."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'cyberether'))
from analyze_bpsk_robustness import refine,measure
from rf_bpsk import synthesize,receive

class TrainingTimingAudit(unittest.TestCase):
    def test_payload_reference_only_changes_metrics(self):
        iq=synthesize(60,offset_samples=97,cfo_hz=23000,noise_std=1)
        acquired=receive(iq) # unknown payload
        self.assertGreater(len(acquired['frames']),0)
        for fit in [False,True]:
            frame=refine(iq,acquired['frames'][0],fit_period=fit)
            self.assertIsNotNone(frame);self.assertTrue(frame['crc_ok']);self.assertEqual(frame['payload'],60)
            actual=measure(frame,60);wrong=measure(frame,195)
            self.assertEqual(actual['crc_valid'],wrong['crc_valid']);self.assertEqual(actual['payload_errors'],0);self.assertEqual(wrong['payload_errors'],8)
    def test_no_training_edges_reject(self):
        import numpy as np
        iq=np.c_[np.full(16380,35),np.zeros(16380)]
        self.assertIsNone(refine(iq,dict(start_sample=100,carrier_hz=0)))
