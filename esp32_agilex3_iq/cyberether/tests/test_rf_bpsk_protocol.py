"""Compile the actual bounded TX parser/encoder and compare with modem FEC."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cyberether'))


class Job(ctypes.Structure):
    _fields_ = [('channel', ctypes.c_uint32), ('duration_ms', ctypes.c_uint32),
                ('backoff_qdb', ctypes.c_uint32), ('nco_step', ctypes.c_uint32),
                ('nco', ctypes.c_bool), ('phase', ctypes.c_bool),
                ('pattern', ctypes.c_uint32), ('symbol_us', ctypes.c_uint32),
                ('pulse_cycles', ctypes.c_uint32)]


@unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
class FramedProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / 'probe.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'firmware/esp32_tx_probe/main/probe_protocol.c'),
                        '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.parse = cls.lib.probe_parse_tone
        cls.parse.argtypes = [ctypes.c_char_p, ctypes.POINTER(Job)]
        cls.parse.restype = ctypes.c_bool
        cls.frame = cls.lib.probe_frame_bits
        cls.frame.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_uint8)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_fast_and_framed_limits(self):
        for command, expected in [
                ('FASTPHASE 8 500 96 165 8 683 3', (3, 165)),
                ('FRAME 8 500 96 165 8 683', (0x103, 165)),
                ('FRAME 1 50 120 0 256 0', (0x103, 0))]:
            job = Job()
            self.assertTrue(self.parse(command.encode(), ctypes.byref(job)))
            self.assertTrue(job.phase)
            self.assertFalse(job.nco)
            self.assertEqual((job.nco_step, job.pattern), expected)
        for command in ['FASTPHASE 8 500 96 165 8 683 4',
                        'FASTPHASE 8 500 96 165 8 683 0',
                        'FRAME 8 501 96 165 8 683', 'FRAME 8 500 96 256 8 683',
                        'FRAME 8 500 96 165 7 683', 'FRAME 8 500 96 165 8 8193',
                        'FRAME 8 500 96 -1 8 683', 'FRAME 8 500 96 165 8 683 junk']:
            self.assertFalse(self.parse(command.encode(), ctypes.byref(Job())), command)

    def test_every_payload_matches_existing_k7_encoder(self):
        import numpy as np
        from modem_reference import conv_encode, viterbi_decode
        for payload in range(256):
            # Byte-wise CRC reference independent from firmware bitwise loop.
            crc = payload
            for _ in range(8):
                crc = ((crc << 1) ^ (0x07 if crc & 0x80 else 0)) & 255
            uncoded = np.unpackbits(np.array([payload, crc], dtype=np.uint8))
            coded = conv_encode(uncoded)
            result = (ctypes.c_uint8 * 64)()
            self.frame(payload, result)
            expected = [int(x) for x in f'{0x0651:016b}'] + coded.tolist() + [0]*4
            self.assertEqual(list(result), expected, f'payload={payload}')
            if payload in (0, 1, 165, 255):
                self.assertEqual(viterbi_decode(coded, soft=False).tolist(), uncoded.tolist())
