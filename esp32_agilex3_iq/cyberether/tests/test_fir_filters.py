import copy,json,sys,tempfile,time,unittest,zlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fir_filters import CATALOG,catalog,resolve_filter,q15,coefficient_hash,validate_coefficients
from lesson_evidence import evidence,capture_fir_test,fir_fixture
from iq_bridge_lab import Lab,validate_settings,summarize
from nios_fir import fixed_reference
from fir_controls import FIRControls


class FilterLibraryTests(unittest.TestCase):
    def test_catalog_quantization_and_distinct_filters(self):
        self.assertEqual(len(CATALOG),15)
        self.assertEqual(len({e['sha256']for e in catalog()}),15)
        for spec in catalog():
            self.assertEqual(len(validate_coefficients(spec['coefficients'])),16)
            self.assertEqual(coefficient_hash(spec['coefficients']),spec['sha256'])
        self.assertEqual(q15([.25]*4),[8192]*4+[0]*12)
        for h in ([1.0],[float('nan')],[0]*17):
            with self.assertRaises(ValueError):q15(h)
        for values in ([0]*15,[0]*17,[True]+[0]*15,[.5]+[0]*15,[32768]+[0]*15):
            with self.assertRaises(ValueError):validate_coefficients(values)
        self.assertEqual(validate_coefficients([-32768]+[32767]*15)[0],-32768)

    def test_filters_have_useful_frequency_behavior(self):
        def magnitude(name,f):
            h=np.array(CATALOG[name]['coefficients'])/32768
            return abs(np.sum(h*np.exp(-2j*np.pi*f*np.arange(16))))
        self.assertLess(magnitude('notch-4mhz',.25),1e-9)
        self.assertGreater(magnitude('notch-4mhz',-.03125),.95)
        self.assertLess(magnitude('notch-6mhz',.375),1e-4)
        self.assertGreater(magnitude('notch-6mhz',.03125),.9)
        self.assertLess(magnitude('highpass',.03125),.05)
        self.assertGreater(magnitude('highpass',.375),.8)
        self.assertLess(magnitude('bandpass',.03125),.05)
        self.assertGreater(magnitude('bandpass',.375),.7)
        self.assertEqual(sum(CATALOG['dc-blocker']['coefficients']),0)
        impulse=fir_fixture('fpga-impulse')
        self.assertEqual(np.argmax(abs(fixed_reference(impulse,CATALOG['delay-7']['coefficients'],True)[:,0])),7)

    def test_api_custom_coefficients_persist_and_reject_bad_inputs(self):
        with tempfile.TemporaryDirectory()as directory,patch('iq_bridge_lab.LESSON',3):
            lab=Lab(Path(directory));lab.state['fpga']['fpga_fir']=True
            lab.update(dict(fir_filter='notch-6mhz'))
            self.assertEqual((lab.settings['view'],lab.settings['fir_filter']),('custom','notch-6mhz'))
            lab.update(dict(once=True))
            self.assertEqual(resolve_filter(lab.settings)['id'],'notch-6mhz')
            taps=[4096]*8+[0]*8
            lab.update(dict(fir_coefficients=taps));self.assertEqual(lab.settings['fir_filter'],'custom')
            self.assertEqual(resolve_filter(lab.settings)['coefficients'],taps)
            for bad in (dict(fir_filter='fake'),dict(fir_coefficients=[1]*15),dict(fir_filter='boxcar',fir_coefficients=taps)):
                before=copy.deepcopy(lab.settings)
                with self.assertRaises(ValueError):lab.update(bad)
                self.assertEqual(lab.settings,before)
            with patch('iq_bridge_lab.LESSON',1):
                with self.assertRaises(ValueError):lab.update(dict(fir_filter='identity'))

    def test_custom_readback_and_fixture_are_required(self):
        config=dict(view='custom',fir_filter='notch-6mhz',fir_coefficients=None,input_kind='fpga-tones',round=True)
        spec=resolve_filter(config);raw=fir_fixture(config['input_kind']);out=fixed_reference(raw,spec['coefficients'],True)
        full=np.column_stack([np.convolve(raw[:,i].astype(np.int64),spec['coefficients'])[:len(raw)]for i in (0,1)])
        scaled=(full+16384)>>15;clips=int(np.count_nonzero(np.any((scaled>127)|(scaled < -128),axis=1)))
        meta=dict(source=3,samples=128,rate=16000000,frequency=0,mode=1,round=1,profile=0,job=0xffff0002,
            coefficients_current=spec['coefficients'],raw_crc=zlib.crc32(raw.tobytes()),filtered_crc=zlib.crc32(out.tobytes()),clips=clips)
        class Nios:
            def command(self,*args):pass
            def wait(self,*args):pass
            def run(self,*args):pass
            def dump(self):return meta,raw,out
        a,b,m=capture_fir_test(Nios(),config)
        c=summarize(a,b,spec['coefficients'],True,m)
        c.update(acquisition=config.copy(),pattern_identity_verified=True,snapshot_crc_verified=True,fir_profile=0,
            fir_coefficients_readback=spec['coefficients'].copy())
        state=dict(settings=config,latest={'custom':c},status='LIVE')
        self.assertEqual(evidence(state,3)['status'],'VERIFIED')
        c['fir_coefficients_readback'][0]^=1
        self.assertEqual(evidence(state,3)['status'],'MISMATCH')
        c['fir_coefficients_readback']=spec['coefficients'].copy()
        state['settings']['fir_filter']='identity'
        self.assertEqual(evidence(state,3)['status'],'APPLYING')

    def test_notebook_client_uses_owner_api_and_rejects_wrong_result(self):
        with tempfile.TemporaryDirectory()as directory:
            run=Path(directory);(run/'control-invite.json').write_text(json.dumps(dict(url='http://127.0.0.1:8768/#test-token')))
            client=FIRControls(run)
            spec=CATALOG['identity'];called=[]
            def api(path,body=None):
                called.append((path,body))
                if path=='control':return dict(accepted=True)
                if path=='state':return dict(latest={'custom':dict(captured_unix=time.time()+1,fir_coefficient_sha256=spec['sha256'],
                    fir_coefficients_readback=spec['coefficients'],max_reference_error=0,clips=0)})
                return dict(status='HELD',reason='Fresh verified result, paused',rows=[dict(ok=True)])
            with patch.object(client,'_api',side_effect=api):
                result=client.apply('identity')
            self.assertTrue(result['readback_verified']);self.assertEqual(result['max_reference_error'],0)
            self.assertEqual(called[0][1]['fir_filter'],'identity')
            with self.assertRaises(ValueError):client.apply('identity',coefficients=[0]*16)
