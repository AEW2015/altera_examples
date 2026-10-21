import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'cyberether'))
from rf_qpsk import frame_states,synthesize,receive,TRAINING
from test_rf_bpsk_protocol import Job

class QpskReference(unittest.TestCase):
    def test_gray_encoder_all_payloads(self):
        from rf_bpsk import frame_bits
        for payload in range(256):
            states=frame_states(payload);self.assertEqual(len(states),64)
            # Inverse Gray labels independent of encoder vector expression.
            labels={0:(0,0),1:(0,1),2:(1,1),3:(1,0)}
            bits=[b for st in states[32:54] for b in labels[int(st)]]
            self.assertEqual(bits,frame_bits(payload)[16:60].tolist())
    def test_timing_cfo_and_unknown_payload(self):
        for payload,offset,cfo,phase in [(0,17,-38000,2.1),(165,113,17321,.7),(255,602,39000,-1.2),(60,176,0,0)]:
            iq=synthesize(payload,offset_samples=offset,cfo_hz=cfo,phase=phase,noise_std=2)
            result=receive(iq,known_payload=payload);blind=receive(iq)
            self.assertGreater(result['valid_frames'],0);self.assertEqual(result['payload_errors'],0)
            self.assertEqual([x['payload'] for x in result['frames']],[x['payload'] for x in blind['frames']])
            wrong=receive(iq,known_payload=payload^255)
            self.assertEqual([x['payload'] for x in result['frames']],[x['payload'] for x in wrong['frames']]);self.assertGreater(wrong['payload_errors'],0)
    def test_guard_suffix_not_required(self):
        iq=synthesize(165,offset_samples=0,samples=54*128)
        result=receive(iq,known_payload=165)
        self.assertGreater(result['valid_frames'],0)
        self.assertEqual(result['payload_errors'],0)
        with self.assertRaises(ValueError):
            receive(iq[:53*128],known_payload=165)

    def test_controls_rejected(self):
        self.assertEqual(receive(np.c_[np.full(16380,30),np.zeros(16380)])['valid_frames'],0)
        rng=np.random.default_rng(12);self.assertEqual(receive(rng.normal(size=(16380,2)))['valid_frames'],0)
    @unittest.skipUnless(shutil.which('cc'),'native compiler required')
    def test_firmware_encoder_and_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            lib=Path(temp)/'probe.so';subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'firmware/esp32_tx_probe/main/probe_protocol.c'),'-o',str(lib)],check=True);native=ctypes.CDLL(str(lib));native.probe_qframe_states.argtypes=[ctypes.c_uint16,ctypes.POINTER(ctypes.c_uint8)];native.probe_parse_tone.argtypes=[ctypes.c_char_p,ctypes.POINTER(Job)];native.probe_parse_tone.restype=ctypes.c_bool
            for payload in range(256):
                output=(ctypes.c_uint8*64)();native.probe_qframe_states(payload,output);self.assertEqual(list(output),frame_states(payload).tolist())
            for command in ['QFRAME 8 500 120 165 8 335 670 1005','QFRAME 1 50 80 0 8 100 200 300']:
                job=Job();self.assertTrue(native.probe_parse_tone(command.encode(),ctypes.byref(job)));self.assertEqual(job.nco_step,0x203)
            for command in ['QFRAME 8 501 120 165 8 335 670 1005','QFRAME 8 500 120 165 8 335 670','QFRAME 8 500 120 165 8 335 0 1005','QFRAME 8 500 120 165 8 335 670 1005 junk']:
                self.assertFalse(native.probe_parse_tone(command.encode(),ctypes.byref(Job())))
