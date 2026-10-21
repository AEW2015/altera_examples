"""Bounds and transaction evidence for optional S3 upload; no hardware access."""
import sys,unittest,zlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from modem_tx import TXLoader,validate_waveform
class TestModemTX(unittest.TestCase):
    def test_waveform_bounds(self):
        valid=np.tile(np.array([1023|(512<<10)],dtype='<u4'),256).tobytes()
        self.assertEqual(validate_waveform(valid)['crc'],f'{zlib.crc32(valid):08x}')
        for data in (b'',b'abc',valid[:-4],valid*64,(np.ones(256,dtype='<u4')<<20).tobytes()):
            with self.assertRaises(ValueError):validate_waveform(data)
    def test_upload_requires_proof_and_never_starts(self):
        c=TXLoader.__new__(TXLoader);data=bytes(256*4);calls=[]
        proof=validate_waveform(data)
        info=[dict(chip='ESP32-S3',initialized='1',running='0',max='16128',alignment='256'),dict(loaded='1',crc=proof['crc'],samples='256')]
        class Port:
            def write(self,value):calls.append(('bytes',len(value)))
            def flush(self):pass
        c.serial=Port();c.info=lambda:info.pop(0)
        c.command=lambda line,prefix:calls.append(line)
        c.response=lambda prefix:calls.append(prefix)
        result=c.upload(data)
        self.assertFalse(result['rf_started']);self.assertFalse(any('START'in str(v)or'INIT'in str(v)for v in calls))
        self.assertEqual(calls[0],f"LOAD 256 {proof['crc']}")
    def test_upload_rejects_wrong_state_or_mismatched_reply(self):
        c=TXLoader.__new__(TXLoader)
        for chip,initialized,running in [('ESP32','1','0'),('ESP32-S3','0','0'),('ESP32-S3','1','1')]:
            c.info=lambda:dict(chip=chip,initialized=initialized,running=running)
            with self.assertRaises(RuntimeError):c.upload(bytes(1024))
