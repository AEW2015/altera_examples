"""Mock JTAG transaction tests, not hardware qualification."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'cyberether'))
import check_rf_bpsk_fpga as checker
from modem_reference import conv_encode,fixedpoint_soft_demapper,viterbi_decode
import rf_bpsk


class MockModem:
    received=[]
    def __init__(self,owner):
        self.owner=owner
    def read(self,address):
        return 0x4d440601
    def encode(self,bits,bps):
        self.bps=bps
        self.expected=np.array(bits)
        self.code=conv_encode(bits)
        return dict(coded=self.code,iq=np.column_stack((8192*(1.-2.*self.code),np.zeros(44))),cycles=44)
    def decode(self,iq):
        self.received.append(iq.copy())
        llr=fixedpoint_soft_demapper(iq,'QPSK' if self.bps==2 else 'BPSK')
        bits=viterbi_decode(llr)
        return dict(llr=llr,bits=bits,raw_errors=int(np.count_nonzero((llr<0)!=self.code)),
                    decoded_errors=int(np.count_nonzero(bits!=self.expected)),cycles=2222)


class RFReplayTests(unittest.TestCase):
    def proof(self,crc_ok=True,flips=()):
        code=rf_bpsk.frame_bits(165)[16:60].copy()
        for bit in flips:code[bit]^=1
        symbols=np.column_stack((.9*(1.-2.*code),np.full(44,.17)))
        return dict(kind='physical_rf_bpsk',rows=[dict(config=dict(payload=165),
                    transport=dict(payload_sha256='a'*64),
                    report=dict(candidates=[dict(sync_errors=0,crc_ok=crc_ok,sync_score=.99,
                        start_sample=42,symbols=symbols.tolist())]))])

    def test_measured_iq_used_and_independent_coded_errors_corrected(self):
        MockModem.received=[]
        with patch.object(checker,'ModemFPGA',MockModem):
            report=checker.check(object(),self.proof(flips=(5,20)))
        self.assertEqual(report['coded_errors'],2)
        self.assertEqual(report['payload_errors'],0)
        self.assertTrue(report['results'][0]['crc_ok'])
        self.assertTrue(np.all(MockModem.received[0][:,1]!=0))
        self.assertEqual(report['results'][0]['symbols_ci16'],MockModem.received[0].tolist())
        self.assertEqual(report['hardware_block_id'],'4d440601')
        self.assertFalse(report['waveform_synchronization_in_fpga'])

    def test_crc_failure_is_selected_and_counted(self):
        proof=self.proof(crc_ok=False,flips=(2,5,11,16,25,30,35,40))
        self.assertEqual(len(checker.select_frames(proof)),1)
        with patch.object(checker,'ModemFPGA',MockModem):
            report=checker.check(object(),proof)
        self.assertEqual(report['frames_checked'],1)
        self.assertGreater(report['payload_errors'],0)
        self.assertEqual(report['crc_failures'],1)
        self.assertEqual(report['coded_bits'],44)

    def test_input_guard_before_hardware(self):
        proof=self.proof()
        proof['kind']='synthetic'
        with self.assertRaises(ValueError):checker.select_frames(proof)
        proof=self.proof();proof['rows'][0]['transport']['payload_sha256']='bad'
        with self.assertRaises(ValueError):checker.select_frames(proof)
        proof=self.proof();proof['rows'][0]['report']['candidates'][0]['sync_errors']=2
        with self.assertRaises(ValueError):checker.select_frames(proof)

    def test_qpsk_measured_symbols_rotate_exact_lut_convention(self):
        from modem_reference import map_bits
        proof=self.proof()
        proof['kind']='physical_rf_qpsk'
        frame=proof['rows'][0]['report']['candidates'][0]
        # Independently enumerate cardinal Gray pairs. Distort magnitude and
        # phase slightly so replacing received points with ideal symbols fails.
        code=rf_bpsk.frame_bits(165)[16:60]
        cardinal=np.array([1.,-1j,1j,-1.],dtype=complex)
        indices=2*code[::2]+code[1::2]
        measured=cardinal[indices]*np.linspace(.72,1.08,22)*np.exp(.06j)
        frame['symbols']=np.c_[measured.real,measured.imag].tolist()
        frame['sync_errors']=2 # QPSK32-symbol training permits2, BPSK16 permits1.
        MockModem.received=[]
        with patch.object(checker,'ModemFPGA',MockModem):
            report=checker.check(object(),proof)
        self.assertEqual(report['kind'],'physical_rf_qpsk_fpga')
        self.assertEqual(report['modulation'],'QPSK')
        self.assertEqual(report['coded_errors'],0)
        self.assertEqual(report['payload_errors'],0)
        self.assertTrue(report['results'][0]['crc_ok'])
        rotated=measured*np.exp(-3j*np.pi/4)
        expected=np.rint(np.c_[rotated.real,rotated.imag]*8192).astype(np.int16)
        np.testing.assert_array_equal(MockModem.received[0],expected)
        self.assertEqual(report['results'][0]['measured_symbols_before_rotation'],frame['symbols'])
        self.assertEqual(report['results'][0]['measured_symbol_count'],22)
        self.assertAlmostEqual(report['frontend_rotation_degrees'],-135)
        ideal=np.c_[map_bits(code,'QPSK').real,map_bits(code,'QPSK').imag]*8192
        self.assertFalse(np.allclose(expected,ideal))
        # Check all four Gray labels, independently of this payload pattern.
        points=cardinal*np.exp(-3j*np.pi/4)
        llr=fixedpoint_soft_demapper(np.rint(np.c_[points.real,points.imag]*8192).astype(np.int16),'QPSK')
        np.testing.assert_array_equal(llr<0,[0,0,0,1,1,0,1,1])

    def test_qpsk_shape_and_physical_kind_guards(self):
        proof=self.proof();proof['kind']='physical_rf_qpsk'
        with self.assertRaises(ValueError):checker.select_frames(proof)
        for kind in ('synthetic_qpsk','physical_rf_qpsk_fpga','physical_rf_bpsk_fir'):
            proof['kind']=kind
            with self.assertRaises(ValueError):checker.select_frames(proof)

    def test_bad_llr_readback_fails_independent_check(self):
        class WrongModem(MockModem):
            def decode(self,iq):
                result=super().decode(iq);result['llr'][0]+=1;return result
        with patch.object(checker,'ModemFPGA',WrongModem):
            with self.assertRaises(AssertionError):checker.check(object(),self.proof())


if __name__=='__main__':unittest.main()
