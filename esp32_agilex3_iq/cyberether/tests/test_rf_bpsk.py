"""Independent receive tests; every RF-looking input here is synthetic."""
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rf_bpsk as r


class PhaseBPSKTests(unittest.TestCase):
    def test_contract_crc_and_independent_tap_encoder(self):
        self.assertEqual(r.crc8(b'123456789'),0xf4)
        for payload in range(256):
            data=[(payload>>k)&1 for k in range(7,-1,-1)]
            crc=r.crc8(bytes([payload]))
            data += [(crc>>k)&1 for k in range(7,-1,-1)]
            history=[0]*6
            encoded=[]
            for bit in data+[0]*6:
                taps=[bit]+history
                encoded += [taps[0]^taps[3]^taps[4]^taps[5]^taps[6],
                            taps[0]^taps[1]^taps[3]^taps[4]^taps[6]]
                history=taps[:6]
            frame=r.frame_bits(payload)
            self.assertEqual(len(frame),64)
            self.assertEqual(''.join(map(str,frame[:16])),'0000011001010001')
            np.testing.assert_array_equal(frame[16:60],encoded)
            np.testing.assert_array_equal(frame[60:],0)
            np.testing.assert_array_equal(r.decode(1.-2.*frame[16:60]),data)

    def test_acquire_carrier_timing_and_phase_without_payload_oracle(self):
        for seed,(payload,offset,cfo,phase) in enumerate([
                (0,0,17321.,.7),(255,8180,-21234.,-2.9),
                (60,358,85555.,1.7),(165,47,-99234.,.01)]):
            x=r.synthesize(payload,offset_samples=offset,cfo_hz=cfo,phase=phase,
                           noise_std=2.,pulse_error=.025,seed=seed)
            report=r.receive(x)
            self.assertGreaterEqual(report['valid_frames'],1)
            self.assertTrue(all(f['payload']==payload for f in report['frames']))
            self.assertIsNone(report['coded_errors'])
            self.assertIsNone(report['payload_errors'])
            for frame in report['frames']:
                self.assertEqual(len(frame['symbols']),44)
                self.assertLess(abs(frame['carrier_hz']-cfo),10000.)
            # Wrong expected data must never alter sync, payload, CRC or IQ.
            instrumented=r.receive(x,expected_payload=payload^255)
            self.assertEqual(report['frames'][0]['start_sample'],instrumented['frames'][0]['start_sample'])
            self.assertEqual(report['frames'][0]['symbols'],instrumented['frames'][0]['symbols'])
            self.assertEqual(instrumented['frames'][0]['payload'],payload)
            self.assertEqual(instrumented['payload_errors'],8*instrumented['acquired_frames'])
            json.dumps(report,allow_nan=False)

    def test_coded_errors_corrected_and_failed_frames_count_in_ber(self):
        corrected=r.receive(r.synthesize(coded_flips=(5,20)),expected_payload=165)
        self.assertGreater(corrected['coded_errors'],0)
        self.assertEqual(corrected['payload_errors'],0)
        self.assertGreater(corrected['valid_frames'],0)
        failed=r.receive(r.synthesize(coded_flips=(2,5,11,16,25,30,35,40)),expected_payload=165)
        self.assertEqual(failed['valid_frames'],0)
        self.assertGreater(failed['acquired_frames'],0)
        self.assertGreater(failed['crc_failures'],0)
        self.assertGreater(failed['payload_errors'],0)
        self.assertEqual(failed['coded_bits'],44*failed['acquired_frames'])
        # This is an acquired bad frame, not a synchronization failure.
        self.assertFalse(failed['sync_failure'])

    def test_noise_carrier_ook_and_unframed_phase_negatives(self):
        rng=np.random.default_rng(834)
        n=16380
        t=np.arange(n)/16e6
        carrier=30*np.exp(2j*np.pi*17321*t)
        noise=4*(rng.normal(size=n)+1j*rng.normal(size=n))
        ook=carrier*((np.arange(n)//128)%2)
        unframed=r.synthesize()
        # Destroy only the sync marker while preserving the same rate/pulse
        # physics: constant carrier, OOK and noise must never imply a frame.
        for x in (noise,carrier+noise,ook+noise,np.zeros(n,dtype=complex)):
            report=r.receive(x)
            self.assertEqual(report['valid_frames'],0)
            self.assertTrue(report['sync_failure'])
            self.assertIsNone(report['payload_bits'])

    def test_boundaries_and_sparse_gap_reporting(self):
        with self.assertRaises(ValueError):
            r.frame_bits(256)
        with self.assertRaises(ValueError):
            r.receive(np.zeros((12,2),np.int8))
        with self.assertRaises(ValueError):
            r.receive(r.synthesize(),expected_payload=1,known_payload=2)
        report=r.receive(r.synthesize(samples=8192))
        self.assertIn('unobserved',report['unobserved_gaps'])
        self.assertEqual(report['processing'],'host Python')
        self.assertIn('correlation',report['plots'])


if __name__=='__main__':
    unittest.main()
