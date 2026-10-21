"""Independent contract and impairment tests for host-only modem reference."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modem_reference as m


class ModemReferenceTests(unittest.TestCase):
    def test_exhaustive_gray_maps_and_soft_metric_sign(self):
        for mode in m.MODES:
            p, labels = m.constellation(mode)
            self.assertAlmostEqual(float(np.mean(abs(p)**2)), 1.)
            np.testing.assert_allclose(m.map_bits(labels.reshape(-1), mode), p)
            np.testing.assert_array_equal(m.hard_demapper(p, mode), labels.reshape(-1))
            np.testing.assert_array_equal(m.soft_demapper(p, mode) < 0, labels.reshape(-1))
            self.assertEqual(m.quantized_mapping(mode).shape, (len(p), 2))
            if mode != 'BPSK':
                level_count = int(np.sqrt(len(p)))
                axis_gray = [k ^ (k >> 1) for k in range(level_count)]
                for a, b in zip(axis_gray, axis_gray[1:]):
                    self.assertEqual((a ^ b).bit_count(), 1)
        np.testing.assert_array_equal(m.map_bits([0, 1], 'BPSK'), [1, -1])
        np.testing.assert_allclose(m.map_bits([0, 0], 'QPSK'), [(-1-1j)/np.sqrt(2)])

    def test_fixedpoint_demapper_exact_distances_and_saturation(self):
        for mode in m.MODES:
            points = m.quantized_mapping(mode)
            labels = m.constellation(mode)[1]
            metrics = m.fixedpoint_soft_demapper(points, mode)
            np.testing.assert_array_equal(metrics < 0, labels.reshape(-1))
            for sample in ([1234, -4321], [32767, -32768]):
                expected = []
                distances = [sum((int(a)-int(b))**2 for a, b in zip(sample, point)) for point in points]
                for bit in range(labels.shape[1]):
                    d0 = min(d for d, label in zip(distances, labels) if label[bit] == 0)
                    d1 = min(d for d, label in zip(distances, labels) if label[bit] == 1)
                    expected.append(max(-127, min(127, (d1-d0) >> 18)))
                np.testing.assert_array_equal(m.fixedpoint_soft_demapper([sample], mode), expected)
        with self.assertRaises(ValueError):
            m.fixedpoint_soft_demapper([[0, 32768]])

    def test_independent_encoder_golden_and_termination(self):
        bits = np.array([1, 0, 1, 1, 0, 0, 1], dtype=np.uint8)
        # Direct seven-bit shift-register tap equation, separate from table.
        history = [0]*6
        expected = []
        for bit in list(bits)+[0]*6:
            reg = [int(bit)] + history
            expected.extend([reg[0]^reg[3]^reg[4]^reg[5]^reg[6],
                             reg[0]^reg[1]^reg[3]^reg[4]^reg[6]])
            history = reg[:6]
        np.testing.assert_array_equal(m.conv_encode(bits), expected)
        encoded = m.conv_encode(bits)
        np.testing.assert_array_equal(m.viterbi_decode(encoded, soft=False), bits)
        np.testing.assert_array_equal(m.viterbi_decode(1.-2.*encoded), bits)
        encoded[6] ^= 1
        encoded[13] ^= 1
        np.testing.assert_array_equal(m.viterbi_decode(encoded, soft=False), bits)
        with self.assertRaises(ValueError):
            m.viterbi_decode([1, 2, 3])

    def test_soft_decoder_noise_gain_same_received_codeword(self):
        rng = np.random.default_rng(31)
        bits = rng.integers(0, 2, 4096, dtype=np.uint8)
        encoded = m.conv_encode(bits)
        samples = 1.-2.*encoded + rng.normal(0, .8, len(encoded))
        hard = m.viterbi_decode(samples < 0, soft=False)
        soft = m.viterbi_decode(samples)
        hard_errors = np.count_nonzero(hard != bits)
        soft_errors = np.count_nonzero(soft != bits)
        self.assertGreater(hard_errors, 0)
        self.assertLess(soft_errors, hard_errors)

    def test_rrc_finite_energy_and_scrambler_roundtrip(self):
        for sps in (4, 8, 40):
            h = m.rrc_taps(sps)
            self.assertAlmostEqual(float(h@h), 1.)
            np.testing.assert_allclose(h, h[::-1])
        bits = np.random.default_rng(3).integers(0, 2, 512)
        np.testing.assert_array_equal(m.scramble(m.scramble(bits)), bits)
        np.testing.assert_array_equal(m.bytes_to_bits(m.bits_to_bytes(bits)), bits)

    def test_noiseless_decode_all_modes_and_uncoded(self):
        payload = bytes(range(32))
        for mode in m.MODES:
            for coded in (False, True):
                tx = m.build_frame(payload, mode, coded)
                rx = m.receive_frame(tx['waveform'])
                self.assertTrue(rx['crc_ok'], (mode, coded, rx['reason']))
                self.assertEqual(rx['payload'], payload)
                self.assertEqual(rx['modulation'], mode)
                self.assertEqual(rx['coded'], coded)

    def test_cfo_fractional_timing_and_unknown_start(self):
        for mode in m.MODES:
            tx = m.build_frame(b'Acquire without payload oracle', mode)
            for cfo, delay in ((-8000, -.3), (6000, .45)):
                x = m.impair(tx['waveform'], snr_db=35, cfo_hz=cfo,
                             timing_offset=delay, seed=11)
                # No transmitted frame / known mode supplied to receiver.
                rx = m.receive_frame(np.r_[np.zeros(73), x])
                self.assertTrue(rx['crc_ok'], (mode, cfo, rx['reason']))
                self.assertEqual(rx['payload'], tx['payload'])
                self.assertLess(abs(rx['estimated_cfo_hz']-cfo), 100)

    def test_multipath_training_and_failure_accounting(self):
        r = m.run_experiment('16QAM', snr_db=32, multipath=True, payload_bits=1024)
        self.assertTrue(r['metrics']['crc_ok'])
        noise = np.random.default_rng(82).normal(size=2400)+1j*np.random.default_rng(83).normal(size=2400)
        rx = m.receive_frame(noise)
        self.assertFalse(rx['header_ok'])
        self.assertFalse(rx['crc_ok'])
        empty = m.receive_frame(np.zeros(20))
        self.assertFalse(empty['locked'])
        # Truncation is not a CRC pass, even if the preamble/header survive.
        tx = m.build_frame(bytes(128), 'QPSK')
        self.assertFalse(m.receive_frame(tx['waveform'][:len(tx['waveform'])//2])['crc_ok'])

    def test_json_counts_fec_benefit_and_sweep(self):
        r = m.run_experiment('64QAM', snr_db=18, payload_bits=2048)
        json.dumps(r, allow_nan=False)
        a = r['metrics']
        self.assertGreater(a['pre_fec_errors'], 0)
        self.assertEqual(a['soft_fec_errors'], 0)
        self.assertEqual(a['post_fec_bits'], 2048)
        self.assertEqual(a['pre_fec_bits'], 2*(2048+32+6))
        self.assertAlmostEqual(a['pre_fec_ber'], a['pre_fec_errors']/a['pre_fec_bits'])
        sweep = m.ber_sweep('QPSK', snr_values=[8, 20], seeds=[2, 3], payload_bits=256)
        self.assertEqual(sweep['rows'][1]['frames'], 2)
        self.assertEqual(sweep['rows'][1]['post_fec_bits'], 512)

    def test_tx_sram_iq10_capacity_and_independent_decode(self):
        for mode in m.MODES:
            tx = m.tx_waveform(b'A', mode)
            self.assertLessEqual(tx['sample_count'], 16128)
            self.assertEqual(tx['sample_count'] % 256, 0)
            words = np.frombuffer(tx['iq10_bytes'], dtype='<u4')
            self.assertTrue(np.all(words >> 20 == 0))
            i = (words & 1023).astype(int)
            q = ((words >> 10) & 1023).astype(int)
            i = np.where(i >= 512, i-1024, i)
            q = np.where(q >= 512, q-1024, q)
            self.assertEqual(max(abs(i).max(), abs(q).max()), 420)
            rx = m.receive_frame(i+1j*q, sps=40, sample_rate=40e6)
            self.assertTrue(rx['crc_ok'], (mode, rx['reason']))
            self.assertEqual(rx['payload'], b'A')
        with self.assertRaisesRegex(ValueError, 'capacity'):
            m.tx_waveform(bytes(256), 'BPSK')
        with self.assertRaises(ValueError):
            m.tx_waveform(amplitude=512)


if __name__ == '__main__':
    unittest.main()
