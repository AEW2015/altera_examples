"""Offline phase evidence: real measurements, not a forced two-cluster fit."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from analyze_esp32_phase import analyze_iq, synthetic_capture, load_ci8


class PhaseAnalysisTests(unittest.TestCase):
    def test_antipodal_pulses_unknown_carrier_and_phase(self):
        pattern = [1,0,1,0,0,1,0,1]
        for seed, noise in ((1,1.), (3,2.), (7,4.)):
            iq = synthetic_capture(seed=seed, noise_sigma=noise, carrier_hz=17578.125,
                                   n=16380, symbol_bits=pattern)
            result = analyze_iq(iq, expected_offset_hz=0)
            self.assertTrue(result['metrics']['two_phase_clusters_observed'])
            self.assertLess(abs(result['carrier']['carrier_hz']-17578.125), 30)
            self.assertEqual(result['metrics']['near_pi_events'], 12)
            changes = np.array([abs(event['phase_change_deg']) for event in result['events']])
            self.assertLess(abs(np.median(changes)-180), 3)
            self.assertGreater(min(c['fraction'] for c in result['metrics']['clusters']), .3)
            json.dumps(result, allow_nan=False)

    def test_ringing_lobes_form_one_measured_transition(self):
        iq = synthetic_capture('ringing-pulses', n=16380, carrier_hz=17578.125,
                               symbol_bits=[1,0,1,0,0,1,0,1], noise_sigma=2.)
        result = analyze_iq(iq, expected_offset_hz=0)
        self.assertTrue(result['metrics']['two_phase_clusters_observed'])
        self.assertEqual(result['metrics']['detected_events'], 12)
        self.assertEqual(result['metrics']['near_pi_events'], 12)
        self.assertLess(abs(result['carrier']['carrier_hz']-17578.125), 30)
        changes = [abs(e['phase_change_deg']) for e in result['events']]
        self.assertLess(abs(np.median(changes)-180), 3)

    def test_zero_and_half_width_controls_do_not_qualify(self):
        pattern = [1,0,1,0,0,1,0,1]
        zero = analyze_iq(synthetic_capture(carrier_hz=17578.125, n=16380,
                                           pulse_us=0, symbol_bits=pattern), expected_offset_hz=0)
        half = analyze_iq(synthetic_capture(carrier_hz=17578.125, n=16380,
                                           pulse_us=6.4, symbol_bits=pattern), expected_offset_hz=0)
        self.assertFalse(zero['metrics']['two_phase_clusters_observed'])
        self.assertEqual(zero['metrics']['detected_events'], 0)
        self.assertGreater(zero['metrics']['first_circular_moment'], .99)
        self.assertFalse(half['metrics']['two_phase_clusters_observed'])
        self.assertEqual(half['metrics']['near_pi_events'], 0)
        changes = np.array([event['phase_change_deg'] for event in half['events']])
        self.assertLess(abs(np.median(changes)-90), 3)

    def test_negative_controls_are_not_projected_to_bpsk(self):
        for kind in ('cw', 'ook', 'qpsk', 'reset-pulses', 'small-pulses', 'noise'):
            result = analyze_iq(synthetic_capture(kind, seed=14))
            self.assertFalse(result['metrics']['two_phase_clusters_observed'], kind)
        # The corrected scatter remains a continuous measured cloud, not +/-1.
        positive = analyze_iq(synthetic_capture())
        points = np.asarray(positive['plots']['corrected_xy'])
        self.assertGreater(len(np.unique(np.round(points, 3), axis=0)), 1000)

    def test_squaring_branch_resolution_and_global_phase_invariance(self):
        for carrier in (-5.123e6, 5.123e6):
            iq = synthetic_capture(carrier_hz=carrier)
            z = (iq[:,0].astype(float)+1j*iq[:,1].astype(float))*np.exp(1.2j)
            result = analyze_iq(z, expected_offset_hz=np.sign(carrier)*5e6)
            self.assertTrue(result['metrics']['two_phase_clusters_observed'])
            self.assertLess(abs(result['carrier']['carrier_hz']-carrier), 20)

    def test_file_roundtrip_and_input_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'capture.ci8'
            iq = synthetic_capture()
            p.write_bytes(iq.tobytes())
            np.testing.assert_array_equal(load_ci8(p), iq)
            p.write_bytes(b'x')
            with self.assertRaises(ValueError):
                load_ci8(p)
        with self.assertRaises(ValueError):
            analyze_iq(np.zeros((20,2)))
        with self.assertRaises(ValueError):
            analyze_iq(np.full((1024,2), np.nan))
        with self.assertRaises(ValueError):
            analyze_iq(synthetic_capture(), rate=0)


if __name__ == '__main__':
    unittest.main()
