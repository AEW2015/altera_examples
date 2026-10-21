import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase_states import qualify_states


class PhaseGateTests(unittest.TestCase):
    def samples(self, states):
        phase = np.repeat(np.asarray(states)*np.pi/2, 256)+.39
        z = 30*np.exp(1j*(phase+2*np.pi*17321*np.arange(len(phase))/16e6))
        return np.column_stack((z.real, z.imag))

    def test_four_states_with_carrier_rotation(self):
        a = self.samples([0, 1, 2, 3]*8)
        events = [dict(start_sample=i*256, end_sample=i*256, phase_change_deg=90) for i in range(1, 32)]
        r = qualify_states(a, carrier_hz=17321, events=events)
        self.assertTrue(r['four_states_qualified'])
        self.assertGreater(r['circular_moments']['fourth'], .999)
        self.assertEqual(r['coherent_quarter_events'], 31)

    def test_carrier_bpsk_and_noise_reject(self):
        rng = np.random.default_rng(81)
        for a in [self.samples([0]*32), self.samples([0, 2]*16), rng.normal(0, 10, (8192, 2))]:
            self.assertFalse(qualify_states(a, carrier_hz=17321)['four_states_qualified'])

    def test_four_points_without_transition_evidence_reject(self):
        self.assertFalse(qualify_states(self.samples([0, 1, 2, 3]*8), carrier_hz=17321)['four_states_qualified'])

    def test_invalid_event_reject(self):
        with self.assertRaises(ValueError):
            qualify_states(self.samples([0]*32), carrier_hz=0, events=[dict(start_sample=-5, end_sample=10)])
