"""Display-only server: no hardware access, distinct saved evidence types."""
import json,sys,tempfile,threading,unittest
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wifi64_native as viewer
class NativeViewer(unittest.TestCase):
 @classmethod
 def setUpClass(cls):viewer.RUN.mkdir(parents=True,exist_ok=True)
 def test_missing_and_wrong_proof_paths(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as t:
   root=Path(t);pointer=root/'pointer.json'
   self.assertEqual(viewer.state(pointer,root/'missing')['status'],'waiting')
   pointer.write_text(json.dumps({'path':'/etc/passwd'}))
   self.assertEqual(viewer.state(pointer,root/'missing')['status'],'telemetry_error')
 def test_proof_and_transmitter_remain_separate(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as t:
   root=Path(t);proof=root/'proof.json';tx=root/'tx.json';pointer=root/'pointer.json'
   proof.write_text(json.dumps({'kind':'independent native Wi-Fi64 OTA packet observation','completed':False}))
   tx.write_text(json.dumps({'kind':'native Wi-Fi 64-QAM transmitter control','tx_success':True}))
   pointer.write_text(json.dumps({'path':str(proof)}));state=viewer.state(pointer,tx)
   self.assertTrue(state['transmitter']['tx_success']);self.assertFalse(state['proof']['completed'])
 def test_http_get_and_post_cannot_run_rf(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as t:
   server=ThreadingHTTPServer(('127.0.0.1',0),viewer.handler(Path(t)/'missing',Path(t)/'missing'))
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
   try:
    with urlopen(url+'/api/state') as response:self.assertEqual(json.load(response)['status'],'waiting')
    with urlopen(url) as response:self.assertIn(b'Native Wi-Fi 64-QAM',response.read())
    with urlopen(url+'/story') as response:self.assertIn(b'Exact remapped constellation needs a new device export',response.read())
    with urlopen(url+'/wifi-phy.svg') as response:
     self.assertEqual(response.headers['Content-Type'],'image/svg+xml');self.assertIn(b'CUSTOM IQ TX',response.read())
    with self.assertRaises(HTTPError) as result:urlopen(Request(url+'/api/run',method='POST'))
    self.assertEqual(result.exception.code,405)
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()

class RawReceiverViewer(unittest.TestCase):
 @classmethod
 def setUpClass(cls):viewer.RUN.mkdir(parents=True,exist_ok=True)
 def fixture(self,qualified=True):
  result=dict(valid=1,status=0 if qualified else 256,stage=5 if qualified else 4,accepted=int(qualified),rate_code=12,mbps=54,packet_status=0 if qualified else 4,source=0,rate=40000000,length=92,points=192,symbols=4,fcs_crc=123,received_crc=123 if qualified else 124,ticks_lo=3220374544,ticks_hi=1,clock_hz=50000000,frequency=2462000000)
  points=[dict(index=i,i=-1264,q=3792,scale=8192) for i in range(192)]
  attempt=dict(host_dsp=False,known_a_identity=True,channel=11,decoder=dict(source='fpga-capture-ram',completed=True,device_decode_accepted=qualified,device_result=result,constellation=points))
  return dict(kind=viewer.RAW_KIND,source=viewer.RAW_SOURCE,host_dsp=False,ota64_confirmed=qualified,channel=11,finished_unix=1700000000,attempts=[attempt])
 def test_qualified_real_source_and_failed_fcs_remain_distinct(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as directory:
   root=Path(directory);pointer=root/'pointer.json';proof=root/'proof.json';pointer.write_text(json.dumps({'path':str(proof)}))
   proof.write_text(json.dumps(self.fixture()));state=viewer.state(root/'missing',root/'missing',pointer)
   self.assertTrue(state['raw_qualified']);self.assertEqual(state['raw_attempt_index'],0);self.assertEqual(state['raw_proof']['attempts'][0]['decoder']['device_result']['points'],192)
   proof.write_text(json.dumps(self.fixture(False)));state=viewer.state(root/'missing',root/'missing',pointer)
   self.assertFalse(state['raw_qualified']);self.assertEqual(state['raw_status'],'not_qualified');self.assertIsNone(state['raw_attempt_index'])
 def test_missing_raw_and_unsafe_paths_preserve_native_panel(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as directory:
   root=Path(directory);native=root/'native.json';np=root/'np.json';raw=root/'rp.json'
   native.write_text(json.dumps({'kind':'independent native Wi-Fi64 OTA packet observation','completed':True}));np.write_text(json.dumps({'path':str(native)}))
   state=viewer.state(np,root/'missing',raw);self.assertEqual(state['status'],'available');self.assertEqual(state['raw_status'],'waiting')
   raw.write_text(json.dumps({'path':'/etc/passwd'}));state=viewer.state(np,root/'missing',raw)
   self.assertEqual(state['status'],'available');self.assertEqual(state['raw_status'],'telemetry_error');self.assertTrue(state['proof']['completed'])
 def test_wrong_source_bad_points_and_false_crc_acceptance_rejected(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as directory:
   root=Path(directory);pointer=root/'pointer.json';proof=root/'proof.json';pointer.write_text(json.dumps({'path':str(proof)}))
   for mutation in ('source','scale','fcs'):
    fixture=self.fixture()
    if mutation=='source':fixture['source']='fpga-test-vector'
    if mutation=='scale':fixture['attempts'][0]['decoder']['constellation'][0]['scale']=128
    if mutation=='fcs':fixture['attempts'][0]['decoder']['device_result']['received_crc']=999
    proof.write_text(json.dumps(fixture));state=viewer.state(root/'missing',root/'missing',pointer)
    self.assertFalse(state['raw_qualified']);self.assertEqual(state['raw_status'],'telemetry_error')
 def test_http_raw_state_get_only_and_large_constellation_present(self):
  with tempfile.TemporaryDirectory(dir=viewer.RUN) as directory:
   root=Path(directory);proof=root/'proof.json';pointer=root/'pointer.json';proof.write_text(json.dumps(self.fixture()));pointer.write_text(json.dumps({'path':str(proof)}))
   server=ThreadingHTTPServer(('127.0.0.1',0),viewer.handler(root/'missing',root/'missing',pointer));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
   try:
    with urlopen(url+'/api/state') as response:self.assertTrue(json.load(response)['raw_qualified'])
    with urlopen(url) as response:
     html=response.read();self.assertIn(b'rawConstellation',html);self.assertIn(b'NIOS SOFTWARE',html);self.assertIn(b'no reconstructed cloud',html)
    with self.assertRaises(HTTPError) as result:urlopen(Request(url+'/api/run',method='POST'))
    self.assertEqual(result.exception.code,405)
   finally:server.shutdown();server.server_close();thread.join()
