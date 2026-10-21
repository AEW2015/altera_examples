import json,sys,tempfile,threading,unittest,urllib.request,urllib.error,zlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from iq_bridge_lab import Lab,Server,handler,validate_settings,summarize
from iq_bridge_lab_view import render
from iq_bridge import Frame
from nios_fir import fixed_reference,PROFILES

def frame(a,kind=1,aux=0):
    payload=a.tobytes();return Frame(kind,0,7,len(a),16000000,2417000000,zlib.crc32(payload),10,0,len(payload),10,20,aux,payload)

class LabTests(unittest.TestCase):
    def test_control_validation(self):
        for body in ({'source':True},{'channel':12},{'view':'fake'},{'continuous':1},{'file':'/tmp/x'},[],{'round':'yes'},{'rate':20000000},{'samples':16384},{'gain_mode':'AUTO'},{'gain_code':82},{'rate':True},{'digital_gain_q8':True},{'digital_gain_q8':4097},{'digital_gain_q8':-1},{'digital_gain_bypass':1}):
            with self.assertRaises(ValueError):validate_settings(body)
        self.assertEqual(validate_settings({'digital_gain_q8':4096,'digital_gain_bypass':False}),{'digital_gain_q8':4096,'digital_gain_bypass':False})
        self.assertEqual(validate_settings({'view':'raw','source':2,'channel':11,'continuous':False}),{'view':'raw','source':2,'channel':11,'continuous':False})
    def test_reference_check_rejects_wrong_fpga_and_clips(self):
        a=np.array([[127,-128]]*64,np.int8);b=fixed_reference(a,PROFILES[2],True)
        full=np.column_stack([np.convolve(a[:,i].astype(np.int64),PROFILES[2])[:len(a)]for i in(0,1)]);v=(full+16384)>>15
        clips=int(np.count_nonzero(np.any((v>127)|(v < -128),axis=1)))
        r=summarize(frame(a),frame(b,6),PROFILES[2],True,{'clips':clips})
        self.assertEqual(r['max_reference_error'],0)
        with self.assertRaises(ValueError):summarize(frame(a),frame(b,6),PROFILES[2],True,{'clips':clips+1})
        bad=b.copy();bad[-1,0]^=1
        with self.assertRaises(ValueError):summarize(frame(a),frame(bad,6),PROFILES[2],True,{'clips':clips})
        self.assertEqual(summarize(frame(a))['max_reference_error'],None)
    def test_adc_rail_count_is_complex_samples_not_components(self):
        a=np.array([[-128,127],[0,0],[127,0],[0,-127]],np.int8)
        result=summarize(frame(a))
        self.assertEqual(result['adc_rail_samples'],2)
        self.assertEqual(result['adc_rail_percent'],50.)
        self.assertEqual(result['nominal_burst_us'],.25)
        self.assertIsNone(result['clips'])
    def test_four_pages_render_and_historical_fits_are_distinct(self):
        with tempfile.TemporaryDirectory()as d:
            lab=Lab(Path(d));state=lab.snapshot()
            for page in('raw','boxcar','hamming','ddc','compare'):
                with self.subTest(page=page):self.assertEqual(render(state,page).size,(1800,1000))
            for i in range(100):lab.history.append(i)
            self.assertEqual(len(lab.history),60)
    def test_auth_origin_schema_and_async_control(self):
        with tempfile.TemporaryDirectory()as d:
            lab=Lab(Path(d));server=Server(('127.0.0.1',0),handler(lab,'private','http://trusted'))
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            url=f'http://127.0.0.1:{server.server_port}'
            def req(path,body=None,token='private',origin='http://trusted'):
                return urllib.request.urlopen(urllib.request.Request(url+path,data=json.dumps(body).encode()if body is not None else None,headers={'X-Lab-Token':token,'Content-Type':'application/json','Origin':origin}))
            for token in('','wrong'):
                with self.assertRaises(urllib.error.HTTPError)as error:req('/api/state',token=token)
                self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError):req('/api/control',{'once':True},origin='http://foreign')
            self.assertEqual(req('/api/control',{'view':'boxcar'}).status,202)
            self.assertEqual(json.load(req('/api/state'))['settings']['view'],'boxcar')
            with self.assertRaises(urllib.error.HTTPError):req('/api/control',{'source':4})
if __name__=='__main__':unittest.main()
