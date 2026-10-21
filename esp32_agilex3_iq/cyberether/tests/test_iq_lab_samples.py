import hashlib,sys,tempfile,unittest,zlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from iq_lab_samples import load_sample,synthetic_snapshot,tone_measurements,PATTERNS
from nios_ddc import reference
from iq_bridge_lab import Lab,validate_settings,summarize
from iq_bridge_lab_view import render
class SampleTests(unittest.TestCase):
    def test_fixtures_are_bounded_coherent_and_verified(self):
        for name in PATTERNS:
            x,m=load_sample(name);self.assertEqual(x.shape,(4096,2));self.assertLess(np.abs(x.astype(np.int16)).max(),128)
            if name!='impulse':np.testing.assert_array_equal(x,np.tile(x[:32],(128,1)))
            snap=synthetic_snapshot(name,dict(source=3,samples=4096,rate=16000000,job=0xffff0000|m['test_id'],raw_crc=m['crc32']))
            self.assertEqual(snap.metadata()['pattern'],name)
            self.assertIn('no RF',snap.metadata()['signal_origin'])
    def test_clean_alias_rejection_measurement(self):
        x,_=load_sample('two-tone');measures=[]
        for flags in(2,0):
            y=reference(x,0x08000000,4,flags)['result'];m=tone_measurements('two-tone',x,y,dict(rate=16000000,phase=0x08000000,decimation=4,bypass_flags=flags));measures.append(m)
            self.assertEqual(m['tones'][1]['output_hz'],1500000.)
        self.assertLess(abs(measures[0]['tones'][1]['attenuation_db']),.1)
        self.assertGreater(measures[1]['tones'][1]['attenuation_db'],60)
    def test_request_validation_and_pattern_renderer(self):
        for body in ({'ddc_input':'unknown'},{'reference':True},{'new_snapshot':1}):
            with self.assertRaises(ValueError):validate_settings(body)
        with tempfile.TemporaryDirectory()as d:
            lab=Lab(Path(d));lab.update({'ddc_input':'two-tone'})
            with self.assertRaises(ValueError):lab.update({'reference':'pin'})
            x,m=load_sample('two-tone');snap=synthetic_snapshot('two-tone',dict(source=3,samples=4096,rate=16000000,job=0xffff0003,raw_crc=m['crc32']));result=summarize(snap)
            self.assertEqual(result['raw']['source'],3)
            self.assertEqual(render(lab.snapshot(),'ddc').size,(1800,1000))
if __name__=='__main__':unittest.main()
