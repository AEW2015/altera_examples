"""Integer coarse synchronization tests; generated fixtures are not RF evidence."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from preamble_reference import evaluate,scan,TRAINING


def training_capture(*,sps=160,start=40,cfo_hz=0.,phase=0.,states=TRAINING):
    z=np.zeros(16380,complex)
    for k,state in enumerate(states):z[start+k*sps:start+(k+1)*sps]=70*np.exp(-.5j*np.pi*state)
    z*=np.exp(1j*(phase+2*np.pi*cfo_hz*np.arange(len(z))/16e6))
    return np.rint(np.c_[z.real,z.imag]).astype(np.int8)


class DifferentialPreambleTests(unittest.TestCase):
    def test_exact_reference_all_rotations_and_signed_full_scale(self):
        iq=training_capture();single=evaluate(iq,40)
        self.assertEqual(single['score_q15'],32768)
        self.assertEqual(single['sum_real'],31*70**2)
        self.assertEqual(single['sum_imag'],0)
        expected=31*70**4
        self.assertEqual(single['differential_energy'],expected)
        # +32768 differential corner needs17signed bits before rotation.
        full=np.full((16380,2),-128,np.int8)
        corner=evaluate(full,0,states=np.zeros(32,int))
        self.assertEqual(corner['sum_real'],31*32768)
        self.assertEqual(corner['score_q15'],32768)
        self.assertLess(corner['numerator']<<15,1<<55)

    def test_phase_and_constant_cfo_do_not_require_carrier_search(self):
        baseline=evaluate(training_capture(),40)['score_q15']
        for cfo,phase in [(21000,.8),(-17000,2.1),(53000,-1.7)]:
            result=evaluate(training_capture(cfo_hz=cfo,phase=phase),40)
            self.assertGreater(result['score_q15'],32500)
            self.assertLess(abs(result['score_q15']-baseline),268)

    def test_scan_matches_scalar_integer_arithmetic_and_complete_window_bound(self):
        iq=training_capture();result=scan(iq)
        self.assertEqual(result['best_start'],40)
        self.assertEqual(result['best_score_q15'],32768)
        self.assertEqual(result['starts'][-1],((len(iq)-31*160-16)//4)*4)
        for index in [0,10,200,len(result['starts'])-1]:
            scalar=evaluate(iq,result['starts'][index])
            self.assertEqual(result['scores_q15'][index],scalar['score_q15'])
            self.assertEqual(result['differential_energy'][index],scalar['differential_energy'])

    def test_zeros_cw_noise_and_wrong_training_are_rejected(self):
        rng=np.random.default_rng(8)
        negatives=[np.zeros((16380,2),np.int8),np.full((16380,2),[60,20],np.int8),
            rng.integers(-60,61,(16380,2),dtype=np.int8),training_capture(states=TRAINING[::-1])]
        for iq in negatives:
            self.assertFalse(scan(iq,threshold_q15=26000)['detected'])

    def test_low_energy_floor_and_first_strict_max_metrics(self):
        iq=training_capture();iq=(iq//35).astype(np.int8)
        result=scan(iq,stride=16)
        self.assertEqual(result['best_score_q15'],0)
        self.assertEqual(result['best_start'],0)
        scalar=evaluate(iq,0)
        self.assertEqual(result['best_energy'],scalar['differential_energy'])
        self.assertEqual(result['best_sum_real'],scalar['sum_real'])
        self.assertFalse(result['detected'])
        self.assertTrue(all(score==0 for score in result['scores_q15']))

    def test_zero_energy_cannot_detect_even_zero_threshold_and_floor(self):
        result=scan(np.zeros((5120,2),np.int8),sps=128,min_energy=0,threshold_q15=0)
        self.assertFalse(result['detected'])
        self.assertEqual(result['best_score_q15'],0)
        with self.assertRaises(ValueError):scan(np.zeros((5120,2),np.int8),sps=128,stride=17)

    def test_floor_average_matches_signed_shift_and_invalid_contract_refused(self):
        iq=training_capture();iq[40:56,0]=-1;iq[40,0]=-2
        self.assertEqual(evaluate(iq,40)['averages'][0][0],-2)
        with self.assertRaises(ValueError):scan(iq,sps=0)
        with self.assertRaises(ValueError):scan(iq,window=15)
        with self.assertRaises(ValueError):scan(iq,stride=0)
        with self.assertRaises(ValueError):evaluate(iq,len(iq)-31*160)


if __name__=='__main__':unittest.main()
