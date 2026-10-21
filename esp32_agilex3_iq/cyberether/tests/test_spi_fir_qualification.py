"""Software-only references; no hardware access or RF claims."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spi_fir_qualification import verify_fir,display_plots,snapshot,verify_restoration,restoration_plan


class SPIQualificationTests(unittest.TestCase):
    def test_independent_delayed_scaled_impulse_and_wrong_output(self):
        raw=np.zeros((32,2),np.int8);raw[0]=[80,-64]
        taps=[0,16384]+[0]*14
        expected=np.zeros_like(raw);expected[1]=[40,-32]
        proof=verify_fir(raw.tobytes(),expected.tobytes(),taps,nearest=True)
        self.assertTrue(proof['bit_exact'])
        self.assertEqual(proof['clips'],0)
        expected[1,0]+=1
        with self.assertRaises(AssertionError):verify_fir(raw.tobytes(),expected.tobytes(),taps,nearest=True)

    def test_signed_rounding_and_saturation_at_limits(self):
        raw=np.array([[127,-128],[127,-128],[127,-128]],np.int8)
        taps=[32767,32767]+[0]*14
        expected=np.array([[127,-128],[127,-128],[127,-128]],np.int8)
        proof=verify_fir(raw.tobytes(),expected.tobytes(),taps,nearest=True,reported_clips=2)
        self.assertEqual(proof['clips'],2)
        with self.assertRaises(ValueError):verify_fir(raw.tobytes(),expected.tobytes(),taps,nearest=True,reported_clips=1)
        with self.assertRaises(ValueError):verify_fir(raw.tobytes(),expected.tobytes(),taps,nearest=True,raw_crc=0)
        raw=np.array([[-3,3]],np.int8)
        nearest=np.array([[-1,2]],np.int8)
        floor=np.array([[-2,1]],np.int8)
        verify_fir(raw.tobytes(),nearest.tobytes(),[16384]+[0]*15,nearest=True)
        verify_fir(raw.tobytes(),floor.tobytes(),[16384]+[0]*15,nearest=False)

    def test_full_range_fft_and_bound_with_known_complex_tone(self):
        n=16380;k=3000
        z=60*np.exp(2j*np.pi*k*np.arange(n)/n)
        raw=np.rint(np.c_[z.real,z.imag]).astype(np.int8).tobytes()
        plots=display_plots(raw,raw)
        spec=plots['spectrum'];peak=int(np.argmax(spec['raw']))
        self.assertLessEqual(len(spec['x']),1024)
        self.assertLess(abs(spec['x'][peak]-16*k/n),.02)
        self.assertLess(abs(spec['raw'][peak]-20*np.log10(60/128)),.1)
        self.assertLess(spec['x'][0],-7.9);self.assertGreater(spec['x'][-1],7.9)
        self.assertEqual(spec['raw'],spec['filtered'])
        self.assertIn('Host FFT',spec['processing'])
        self.assertEqual(plots['time']['sample'],list(range(384)))
        original=np.frombuffer(raw,np.int8).reshape(-1,2)
        self.assertEqual(plots['time']['raw_i'],original[:384,0].tolist())
        self.assertEqual(plots['time']['raw_q'],original[:384,1].tolist())

    def test_cleanup_requires_matching_setting_and_coefficient_readbacks(self):
        original=dict(configured_round=1,configured_profile=2)
        actual=dict(original,pair=0);taps=[1]*16
        self.assertTrue(verify_restoration(actual,taps,original,taps))
        for key,bad in [('pair',1),('configured_round',0),('configured_profile',1)]:
            changed=dict(actual);changed[key]=bad
            with self.subTest(key=key):
                with self.assertRaises(ValueError):verify_restoration(changed,taps,original,taps)
        with self.assertRaises(ValueError):verify_restoration(actual,[0]*16,original,taps)

    def test_noncanonical_preset_restores_exact_taps_with_honest_custom_label(self):
        original=dict(configured_round=0,configured_profile=1)
        taps=[0]+[2048]*15
        plan=restoration_plan(original,taps)
        self.assertEqual(plan['method'],'coefficients')
        self.assertEqual(plan['profile'],0)
        self.assertEqual(plan['normalized_profile_from'],1)
        self.assertFalse(plan['profile_label_preserved'])
        actual=dict(pair=0,configured_round=0,configured_profile=0)
        self.assertTrue(verify_restoration(actual,taps,original,taps,expected_profile=plan['profile']))
        with self.assertRaises(ValueError):verify_restoration(actual,[2048]*16,original,taps,expected_profile=0)
        canonical=restoration_plan(original,[2048]*16)
        self.assertEqual(canonical['method'],'preset')
        self.assertTrue(canonical['profile_label_preserved'])
        self.assertIsNone(canonical['normalized_profile_from'])

    def test_snapshot_must_identify_software_fixture(self):
        raw=bytes([1,2])*32
        proof=snapshot(raw,raw,kind='synthetic_spi_fir_simulation',requested={},readback={},verification={},timing={},provenance={})
        self.assertEqual(proof['schema'],'spi-pipeline-v1')
        self.assertIn('Not hardware tested',proof['provenance']['fpga_processing'])
        with self.assertRaises(ValueError):snapshot(raw,raw,kind='rf',requested={},readback={},verification={},timing={},provenance={})


if __name__=='__main__':unittest.main()
