import collections,sys,unittest,zlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nios_ddc import phase_increment,reference,dump,gain_reference
class FakeNios:
    def __init__(self,wrong=False):
        a=np.array([[-128,127],[23,-47],[0,0],[12,31],[43,91]],np.int8)
        b=reference(a,0xf8000000,4,0)['result'];r=a.tobytes();q=b.tobytes()
        _,meters=gain_reference(b)
        self.levels=dict(gain=65792,samples=len(b),pre_sum_lo=meters['pre_power']&0xffffffff,pre_sum_hi=meters['pre_power']>>32,pre_peak=meters['pre_peak'],pre_rails=meters['pre_rails'],post_sum_lo=meters['post_power']&0xffffffff,post_sum_hi=meters['post_power']>>32,post_peak=meters['post_peak'],clips=0,capability=0x474e0101,epoch=7)
        self.meta=dict(id=19,epoch=7,samples=len(a),output_samples=len(b),raw_crc=zlib.crc32(r),output_crc=zlib.crc32(q)^(1 if wrong else 0),phase=0xf8000000,config=0x10400,rate=16000000,cycles=1000,mixer_clips=0,filter_clips=0)
        self.rows=iter([f'DDCRAW,19,0,{len(a)},{r.hex()}',f'DDCIQ,19,0,{len(b)},{q.hex()}','DDCDONE,19'])
    def command(self,*args):return (self.levels if args[0]=='DDCLEVELS'else self.meta).copy()
    def line(self,*args):return next(self.rows)
class DdcTests(unittest.TestCase):
    def test_gain_meter_corruption_is_rejected(self):
        fake=FakeNios();fake.levels['pre_sum_lo']+=1
        with self.assertRaisesRegex(ValueError,'meter'):dump(fake)
        fake=FakeNios();fake.levels['epoch']+=1
        with self.assertRaisesRegex(ValueError,'stale'):dump(fake)
    def test_gain_rounding_saturation_and_complex_power(self):
        x=np.array([[-1,1],[-3,3],[-32768,32767]])
        y,m=gain_reference(x,128,False)
        np.testing.assert_array_equal(y,np.array([[0,1],[-1,2],[-16384,16384]]))
        self.assertEqual(m['pre_rails'],1)
        y,m=gain_reference(x,4096,False);self.assertEqual(m['gain_clips'],1)
        self.assertEqual(m['pre_power'],int(np.sum(x.astype(np.int64)**2)))
    def test_tuning_bounds_and_signed_phase(self):
        self.assertEqual(phase_increment(-500000,16000000),0xf8000000)
        self.assertEqual(phase_increment(500000,16000000),0x08000000)
        for v in(8000000,-8000001,True):
            with self.assertRaises(ValueError):phase_increment(v,16000000)
    def test_bypass_decimates_without_changing_integer_scale(self):
        x=np.array([[-128,127],[23,-47],[0,0],[12,31],[43,91]],np.int8)
        np.testing.assert_array_equal(reference(x,0xffffffff,4,3)['result'],x.astype(np.int16)[::4]*128)
    def test_readback_crc_sequence_and_integer_reference(self):
        meta,a,b=dump(FakeNios());self.assertEqual(meta['max_reference_error'],0);self.assertEqual(meta['output_rate'],4000000)
        with self.assertRaisesRegex(ValueError,'CRC'):dump(FakeNios(True))
        fake=FakeNios();fake.rows=iter(['DDCRAW,19,1,1,0000'])
        with self.assertRaisesRegex(ValueError,'sequence'):dump(fake)
if __name__=='__main__':unittest.main()
