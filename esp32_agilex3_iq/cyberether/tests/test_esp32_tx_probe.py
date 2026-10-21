"""Exercise the actual C job parser before any RF job reaches the worker."""
import ctypes,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Job(ctypes.Structure):
    _fields_=[('channel',ctypes.c_uint32),('duration_ms',ctypes.c_uint32),('backoff_qdb',ctypes.c_uint32)]
@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class ProbeParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        library=Path(cls.temp.name)/'probe.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'firmware/esp32_tx_probe/main/probe_protocol.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library));cls.parse=cls.lib.probe_parse_tone
        cls.parse.argtypes=[ctypes.c_char_p,ctypes.POINTER(Job)];cls.parse.restype=ctypes.c_bool
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_bounded_jobs(self):
        for command,expected in [(b'TONE 3 3000 96',(3,3000,96)),(b'TONE 11 50 120',(11,50,120))]:
            job=Job();self.assertTrue(self.parse(command,ctypes.byref(job)))
            self.assertEqual((job.channel,job.duration_ms,job.backoff_qdb),expected)
    def test_rejects_unbounded_malformed_and_high_power(self):
        for command in [b'TONE 1 0 96',b'TONE 1 3001 96',b'TONE 1 50 0',b'TONE 12 50 96',b'TONE -1 50 96',b'TONE 1 50 -1',b'TONE 1 50 96 START',b'TONE 1 50',b'TONE 1 9999999999999999999999 96',b'TONE 1x 50 96']:
            self.assertFalse(self.parse(command,ctypes.byref(Job())),command)

class ToneMetrics(unittest.TestCase):
    def test_separate_receiver_band_detects_tone_without_assuming_iq_sign(self):
        import sys
        import numpy as np
        sys.path.insert(0,str(ROOT/'scripts'))
        from check_esp32_tone import metrics
        n=np.arange(8192)
        noise=np.random.default_rng(9).normal(0,2,(len(n),2)).astype(np.int8)
        off,_,_=metrics(noise,16000000)
        for sign in (-1,1):
            z=30*np.exp(sign*2j*np.pi*5e6*n/16e6)
            iq=(noise.astype(float)+np.column_stack([z.real,z.imag])).astype(np.int8)
            on,_,_=metrics(iq,16000000)
            self.assertGreater(on['relative_band_db']-off['relative_band_db'],20)
            self.assertAlmostEqual(on['peak_offset_hz'],sign*5e6,delta=2000)
            self.assertEqual(on['rail_percent'],0)

    def test_ook_detector_uses_only_received_levels_and_training_threshold(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        from check_esp32_ook import decide_ook
        self.assertEqual(decide_ook([-16,45,3,15,45,-18],14).astype(int).tolist(),[0,1,0,1,1,0])
