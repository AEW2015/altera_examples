"""Independent exhaustive, brute-force likelihood and waveform tests (no hardware)."""
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import svg_modem as m


class SvgModemTests(unittest.TestCase):
    def test_bit_order_matches_existing_reference(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from modem_reference import conv_encode
        bits = np.random.default_rng(25).integers(0, 2, 256, dtype=np.uint8)
        pairs = m.encode(bits)['coded_pairs']
        actual = np.column_stack((pairs >> 1, pairs & 1)).reshape(-1)
        np.testing.assert_array_equal(actual, conv_encode(bits))

    def test_exhaustive_short_terminated_frames_and_final_vertices(self):
        points = m.load_graph()
        final_nodes = set()
        for n in range(8):
            for bits in itertools.product((0, 1), repeat=n):
                tx = m.encode(bits)
                rx = m.decode(points[tx['node_path'][1:]])
                np.testing.assert_array_equal(rx['decoded_bits'], bits)
                np.testing.assert_array_equal(rx['node_path'], tx['node_path'])
                self.assertEqual(rx['final_state'] % 64, 0)
                self.assertEqual(tx['final_state'] % 64, 0)
                np.testing.assert_array_equal(rx['stream_bits'][-6:], 0)
                final_nodes.add(tx['final_state'] // 64)
        self.assertEqual(final_nodes, set(range(5)))

    def test_predecessors_forward_inverse_all_640_branches(self):
        for parent in range(320):
            node, memory = divmod(parent, 64)
            for bit in (0, 1):
                next_memory, pair = m.branch(memory, bit)
                destination = ((node + m.DELTAS[pair]) % 5) * 64 + next_memory
                self.assertEqual(list(m.PARENTS[destination]).count(parent), 1)
        self.assertEqual(m.PARENTS.shape, (320, 2))

    def test_viterbi_matches_exhaustive_maximum_likelihood(self):
        rng = np.random.default_rng(71)
        points = m.load_graph()
        for _ in range(6):
            y = rng.standard_normal(11) + 1j * rng.standard_normal(11)
            candidates = []
            for bits in itertools.product((0, 1), repeat=5):
                tx = m.encode(bits)
                score = float(np.sum(abs(y - points[tx['node_path'][1:]]) ** 2))
                candidates.append((score, bits))
            expected_score, expected_bits = min(candidates)
            actual = m.decode(y)
            np.testing.assert_array_equal(actual['decoded_bits'], expected_bits)
            self.assertAlmostEqual(actual['metric'], expected_score, places=11)

    def test_nonzero_start_node_and_unterminated_frame(self):
        points = m.load_graph()
        bits = [1, 0, 1, 1, 0, 0, 1, 1]
        for start in range(5):
            tx = m.encode(bits, start_node=start, terminate=False)
            rx = m.decode(points[tx['node_path'][1:]], start_node=start, terminated=False)
            np.testing.assert_array_equal(rx['decoded_bits'], bits)

    def test_graph_only_has_four_distinct_choices(self):
        for node in range(5):
            destinations = {int(m.graph_encode(pair, node)[-1])
                            for pair in itertools.product((0, 1), repeat=2)}
            self.assertEqual(destinations, set(range(5)) - {node})
        with self.assertRaises(ValueError):
            m.graph_encode([1])

    def test_waveform_endpoints_arc_radius_linear_chord_and_hold(self):
        points = m.load_graph()
        path = [0, 1, 3, 2, 0]
        for mode in ('arc', 'linear', 'hold'):
            wave = m.shape_waveform(path, mode=mode, sps=16)
            np.testing.assert_array_equal(wave[15::16], points[path[1:]])
        arc = m.shape_waveform(path, mode='arc', sps=16)
        np.testing.assert_allclose(abs(arc[:16]), 1, atol=1e-14)
        self.assertLess(abs(arc[16 + 7]), 0.5)  # star transition remains a chord
        linear = m.shape_waveform(path, mode='linear', sps=16)
        self.assertLess(abs(linear[7]), 1)
        hold = m.shape_waveform(path, mode='hold', sps=16)
        np.testing.assert_array_equal(hold[:16], np.full(16, points[1]))

    def test_reproducible_noisy_demo_and_honest_error_counts(self):
        a = m.simulate(seed=7, snr_db=7, payload_bits=256)
        self.assertEqual(a, m.simulate(seed=7, snr_db=7, payload_bits=256))
        self.assertTrue(a['simulation_only'])
        self.assertFalse(a['implemented_in_fpga'])
        self.assertFalse(a['rf_tested'])
        self.assertGreater(a['rx']['hard_symbol_errors'], 0)
        self.assertEqual(a['rx']['decoded_bit_errors'], 0)
        np.testing.assert_array_equal(np.asarray(a['waveform']['rx_samples'])[15::16], a['rx']['symbols'])
        expected = sum(x != y for x, y in zip(a['payload_bits'], a['rx']['decoded_bits']))
        self.assertEqual(a['rx']['decoded_bit_errors'], expected)
        poor = m.simulate(seed=7, snr_db=-6, payload_bits=256)
        self.assertGreater(poor['rx']['decoded_bit_errors'], 0)
        self.assertGreater(poor['rx']['post_fec_ber'], 0)

    def test_ci16_metrics_are_exact_without_complex_sqrt_rounding(self):
        points = np.rint(m.load_graph() * 8192)
        rng = np.random.default_rng(130)
        for _ in range(12):
            iq = rng.integers(-32768, 32768, size=(10, 2), dtype=np.int64)
            actual = m.decode(iq[:, 0] + 1j * iq[:, 1], points=points)
            candidates = []
            for bits in itertools.product((0, 1), repeat=4):
                nodes = m.encode(bits)['node_path'][1:]
                delta = iq - np.column_stack((points[nodes].real, points[nodes].imag)).astype(np.int64)
                candidates.append((int(np.sum(delta * delta)), bits))
            score, bits = min(candidates)
            self.assertEqual(actual['metric'], score)
            np.testing.assert_array_equal(actual['decoded_bits'], bits)

    def test_input_validation(self):
        for bits in ([2], [[0, 1]], [-1]):
            with self.assertRaises(ValueError):
                m.encode(bits)
        with self.assertRaises(ValueError):
            m.decode([1j] * 5)
        with self.assertRaises(ValueError):
            m.decode([np.nan] * 6)
        with self.assertRaises(ValueError):
            m.decode([1j] * 8, payload_bits=3)
        with self.assertRaises(ValueError):
            m.shape_waveform([0, 1], sps=0)


if __name__ == '__main__':
    unittest.main()
