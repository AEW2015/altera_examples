"""Independent normalization, fairness, CRC accounting and evidence boundaries."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import math
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ber_qualification import error_metric, noise_sigma, run_sweep, aggregate_rf
from rf_bpsk import frame_bits, int_bits, crc8


class BERQualificationTests(unittest.TestCase):
    def test_zero_count_exact_limit_and_unknown_denominator(self):
        metric = error_metric(0, 100)
        self.assertAlmostEqual((1-metric['zero_error_upper'])**100, .05)
        self.assertIsNone(error_metric(0, 0)['rate'])
        self.assertIsNone(error_metric(1, 100)['zero_error_upper'])
        with self.assertRaises(ValueError):
            error_metric(2, 1)

    def test_ebn0_uses_finite_tail_rate(self):
        self.assertAlmostEqual(noise_sigma(0, 16, 44)**2, 44/32)
        self.assertAlmostEqual(noise_sigma(0, 16, 16)**2, .5)
        self.assertAlmostEqual(noise_sigma(10, 16, 44)**2, 44/320)
        with self.assertRaises(ValueError):
            noise_sigma(float('nan'), 16, 44)

    def test_reproducible_perfect_high_snr_and_real_denominators(self):
        a = run_sweep([40], frames=3, payload_bytes=2, seed=91)
        self.assertEqual(a, run_sweep([40], frames=3, payload_bytes=2, seed=91))
        point = a['points'][0]
        self.assertEqual(a['coded_bits'], 60)
        self.assertEqual(point['coded_channel']['trials'], 180)
        for name in ('hard', 'soft'):
            self.assertEqual(point[name]['payload']['errors'], 0)
            self.assertEqual(point[name]['payload']['trials'], 48)
            self.assertEqual(point[name]['crc_checks'], 3)
            self.assertEqual(point[name]['frames']['trials'], 3)
        self.assertIn('NOT tested', a['synchronization'])

    def test_soft_gain_on_same_samples_and_uncoded_theory(self):
        result = run_sweep([2], frames=160, payload_bytes=8, seed=442)
        point = result['points'][0]
        self.assertLess(point['soft']['payload']['errors'], point['hard']['payload']['errors'])
        p = .5*math.erfc(math.sqrt(10**.2))
        observed = point['uncoded']['rate']
        self.assertLess(abs(observed-p), 5*math.sqrt(p*(1-p)/(160*64)))
        self.assertGreater(point['hard']['crc_failures'], 0)

    def test_saved_rf_dedup_keeps_crc_failed_frames_and_reference_independent(self):
        payload = 165
        coded = frame_bits(payload)[16:60]
        llr = 1.-2.*coded
        llr[0] *= -1
        decoded = np.r_[int_bits(payload,8), int_bits(crc8(bytes([payload])),8)]
        decoded[0] ^= 1
        candidate = dict(sync_errors=0, crc_ok=False, coded_llr=llr.tolist(), decoded_bits=decoded.tolist())
        row = dict(config={'payload': payload}, transport={'source':0, 'payload_sha256':'a'*64},
                   report={'candidates':[candidate]})
        fail = dict(config={'payload':payload}, transport={'source':2,'payload_sha256':'b'*64}, report={'candidates':[]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'rf.json'
            path.write_text(json.dumps({'kind':'physical_rf_bpsk','rows':[row,row,fail]}))
            other = Path(temp)/'synthetic.json'
            other.write_text(json.dumps({'kind':'synthetic_bpsk','rows':[row]}))
            report = aggregate_rf([path, other])
            totals = report['totals']
            self.assertEqual(totals['captures'],2)
            self.assertEqual(totals['acquisition_failures'],1)
            self.assertEqual(totals['crc_failures'],1)
            self.assertEqual(totals['coded_errors'],1)
            self.assertEqual(totals['coded_bits'],44)
            self.assertEqual(totals['payload_errors'],1)
            self.assertEqual(totals['payload_bits'],8)
            self.assertEqual(report['duplicate_captures_excluded'],1)
            self.assertEqual(report['non_rf_proofs_excluded'],1)
            wrong = aggregate_rf([path], reference_payload=0)['totals']
            self.assertEqual(wrong['crc_failures'],totals['crc_failures'])
            self.assertEqual(wrong['acquired_frames'],totals['acquired_frames'])
            self.assertNotEqual(wrong['payload_errors'],totals['payload_errors'])

    def test_hard_soft_decode_exact_same_noisy_symbols(self):
        from unittest.mock import patch
        import ber_qualification as b
        original = b.viterbi_decode
        calls = []
        def recorded(values, **kwargs):
            calls.append((np.asarray(values).copy(), kwargs['soft']))
            return original(values, **kwargs)
        with patch.object(b, 'viterbi_decode', side_effect=recorded):
            b.run_sweep([0], frames=2, payload_bytes=1)
        self.assertEqual(len(calls), 4)
        for index in (0, 2):
            hard, soft = calls[index:index+2]
            self.assertFalse(hard[1])
            self.assertTrue(soft[1])
            np.testing.assert_array_equal(hard[0], soft[0] < 0)

    def test_per_setting_groups_preserve_unknown_settings(self):
        rows = []
        for index, channel in enumerate([2, 8]):
            rows.append(dict(config={'channel':channel, 'period_us':8, 'pulse_cycles':670},
                transport={'source':0,'payload_sha256':str(index)*64}, report={'candidates':[]}))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'rf.json'
            path.write_text(json.dumps({'kind':'physical_rf_bpsk','rows':rows}))
            report = aggregate_rf([path, path])
        self.assertEqual(report['totals']['captures'],2)
        self.assertEqual(report['duplicate_captures_excluded'],2)
        self.assertEqual(len(report['setting_groups']),2)
        self.assertEqual({r['settings']['channel'] for r in report['setting_groups']},{2,8})
        self.assertTrue(all(r['settings']['backoff'] is None for r in report['setting_groups']))

    def test_new_proof_requested_backoff_is_recorded_not_guessed(self):
        row=dict(config={},transport={'payload_sha256':'a'*64},report={'candidates':[]})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'proof.json'
            proof=dict(kind='physical_rf_bpsk',requested={'backoff_qdb':120},rows=[row])
            path.write_text(json.dumps(proof))
            self.assertEqual(aggregate_rf([path])['setting_groups'][0]['settings']['backoff'],120)
            row['config']['backoff']=100
            path.write_text(json.dumps(proof))
            self.assertEqual(aggregate_rf([path])['setting_groups'][0]['settings']['backoff'],100)

    def test_qpsk_crc_failed_candidates_included_and_modulations_separate(self):
        payload=60
        code=frame_bits(payload)[16:60]
        llr=1.-2.*code
        llr[2]*=-1
        decoded=np.r_[int_bits(payload,8),int_bits(crc8(bytes([payload])),8)]
        decoded[0]^=1
        candidate=dict(sync_errors=2,crc_ok=False,coded_llr=llr.tolist(),decoded_bits=decoded.tolist())
        row=dict(config={'payload':payload,'period_us':10,'quarter_cycles':335},
            transport={'source':0,'payload_sha256':'a'*64},report={'candidates':[candidate]})
        failed=dict(config={'payload':payload,'period_us':8},transport={'source':0,'payload_sha256':'b'*64},report={'candidates':[]})
        with tempfile.TemporaryDirectory() as temp:
            qp=Path(temp)/'qpsk.json';bp=Path(temp)/'bpsk.json'
            qp.write_text(json.dumps(dict(kind='physical_rf_qpsk',rows=[row,failed])))
            bp.write_text(json.dumps(dict(kind='physical_rf_bpsk',rows=[row])))
            q=aggregate_rf([qp,bp],modulation='QPSK')
            b=aggregate_rf([qp,bp])
        self.assertEqual(q['totals']['captures'],2)
        self.assertEqual(q['totals']['acquired_frames'],1)
        self.assertEqual(q['totals']['acquisition_failures'],1)
        self.assertEqual(q['totals']['crc_failures'],1)
        self.assertEqual(q['totals']['coded_errors'],1)
        self.assertEqual(q['totals']['coded_bits'],44)
        self.assertEqual(q['totals']['payload_errors'],1)
        self.assertEqual(q['totals']['payload_bits'],8)
        self.assertEqual(b['totals']['captures'],1)
        self.assertEqual(b['totals']['acquired_frames'],0) # BPSK requires sync<=1
        self.assertEqual(q['non_rf_proofs_excluded'],1)
        self.assertTrue(all(g['settings']['modulation']=='QPSK' for g in q['setting_groups']))
        with self.assertRaises(ValueError):aggregate_rf([],modulation='16QAM')

    def test_crc_only_corruption_counts_as_frame_failure_not_payload_ber(self):
        from unittest.mock import patch
        import ber_qualification as b
        original=b.viterbi_decode
        def corrupt_crc(values, **kwargs):
            result=original(values, **kwargs)
            result[-1]^=1
            return result
        with patch.object(b,'viterbi_decode',side_effect=corrupt_crc):
            simulation=b.run_sweep([40],frames=2,payload_bytes=1)
        for name in ('hard','soft'):
            metric=simulation['points'][0][name]
            self.assertEqual(metric['payload']['errors'],0)
            self.assertEqual(metric['frames']['errors'],2)
            self.assertEqual(metric['crc_failures'],2)
            self.assertEqual(metric['undetected_payload_error_frames'],0)
        payload=165
        llr=1.-2.*frame_bits(payload)[16:60]
        decoded=np.r_[int_bits(payload,8),int_bits(crc8(bytes([payload])),8)]
        decoded[-1]^=1
        row=dict(config={'payload':payload},transport={'payload_sha256':'a'*64},
            report={'candidates':[dict(sync_errors=0,crc_ok=False,coded_llr=llr.tolist(),decoded_bits=decoded.tolist())]})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'rf.json'
            path.write_text(json.dumps(dict(kind='physical_rf_bpsk',rows=[row])))
            with patch.object(b,'viterbi_decode',side_effect=corrupt_crc):
                rf=b.aggregate_rf([path])
        for name in ('hard','soft'):
            self.assertEqual(rf['totals'][name]['payload']['errors'],0)
            self.assertEqual(rf['totals'][name]['frames']['errors'],1)
            self.assertEqual(rf['totals'][name]['crc_failures'],1)

    def test_transmitter_versions_and_actual_acknowledgement_never_merge(self):
        row=dict(config={'payload':165,'job':4,'channel':8,'backoff':120,'period_us':8},
            transport={'source':0,'payload_sha256':'a'*64},report={'candidates':[]})
        ack=dict(id=4,channel=8,backoff_qdb=120,limit_ms=500,
            line='TX_ON,id=4,channel=8,backoff_qdb=120,limit_ms=500')
        with tempfile.TemporaryDirectory() as temp:
            paths=[]
            for index,(version,acknowledgement) in enumerate([('v=5',None),('v=6',ack),('v=6',dict(ack,id=99))]):
                r=json.loads(json.dumps(row));r['transport']['payload_sha256']=str(index)*64
                if acknowledgement:r['config']['tx_on_readback']=acknowledgement
                path=Path(temp)/f'{index}.json'
                path.write_text(json.dumps(dict(kind='physical_rf_bpsk',identity='TX_PROBE,'+version+',busy=0',requested={'backoff_qdb':120},rows=[r])))
                paths.append(path)
            groups=aggregate_rf(paths)['setting_groups']
        self.assertEqual(len(groups),3)
        self.assertEqual([(g['settings']['tx_firmware'],g['settings']['tx_ack_verified']) for g in groups],[('v5',False),('v6',True),('v6',False)])
        self.assertTrue(all(g['settings']['backoff']==120 for g in groups))
        from ber_qualification import transmitter_settings
        bad=dict(row['config'],tx_on_readback=dict(ack,line='TX_ON,id=4,channel=8,backoff_qdb=119,limit_ms=500'))
        self.assertFalse(transmitter_settings({},bad)['tx_ack_verified'])
        self.assertEqual(transmitter_settings({},row['config'])['tx_firmware'],'unknown')

    def test_missing_hash_is_excluded_and_missing_reference_not_zero_ber(self):
        row = dict(transport={'payload_sha256':'a'*64},report={'candidates':[dict(sync_errors=0,crc_ok=True)]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'rf.json'
            path.write_text(json.dumps({'kind':'physical_rf_bpsk','rows':[{},row]}))
            report = aggregate_rf([path])
        self.assertEqual(len(report['skipped']),1)
        self.assertEqual(report['totals']['unreferenced_frames'],1)
        self.assertIsNone(report['totals']['payload']['rate'])


if __name__ == '__main__':
    unittest.main()
