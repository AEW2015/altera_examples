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
    with self.assertRaises(HTTPError) as result:urlopen(Request(url+'/api/run',method='POST'))
    self.assertEqual(result.exception.code,405)
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
