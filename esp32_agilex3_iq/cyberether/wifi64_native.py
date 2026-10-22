"""Read-only native Wi-Fi monitor viewer. No device or RF operations."""
from __future__ import annotations
import argparse,json,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'cyberether/run'

def _json(path):
    if not path.is_file():return None
    if path.stat().st_size>1048576:raise ValueError('Telemetry file exceeds 1 MiB')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('Telemetry must be an object')
    return value

def state(pointer=None,transmitter=None):
    result={'proof':None,'transmitter':None,'age_s':None,'status':'waiting'}
    try:
        latest=_json(Path(pointer or RUN/'wifi64-ota-latest.json'))
        if latest:
            path=Path(latest['path'])
            if not path.is_absolute():path=ROOT/path
            path=path.resolve()
            if not path.is_relative_to(RUN.resolve()) or path.suffix!='.json':raise ValueError('Invalid proof path')
            proof=_json(path)
            if not proof or proof.get('kind')!='independent native Wi-Fi64 OTA packet observation':raise ValueError('Not a native OTA observation')
            result['proof']=proof;result['status']='available'
            end=proof.get('finished_unix')
            if isinstance(end,(int,float)):result['age_s']=max(0,time.time()-end)
        tx=_json(Path(transmitter or RUN/'wifi64-a-first-native-job.json'))
        if tx and tx.get('kind')=='native Wi-Fi 64-QAM transmitter control':result['transmitter']=tx
    except (OSError,ValueError,KeyError,TypeError) as error:
        result['status']='telemetry_error';result['error']=str(error)
    return result

def handler(pointer=None,transmitter=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            route=self.path.split('?',1)[0]
            if route=='/api/state':
                payload=json.dumps(state(pointer,transmitter),allow_nan=False).encode();content_type='application/json'
            elif route in ('/','/index.html'):
                payload=(ROOT/'cyberether/wifi64_native.html').read_bytes();content_type='text/html; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_POST(self):self.send_error(405,'Display only; no RF controls')
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='0.0.0.0');parser.add_argument('--port',type=int,default=8774);parser.add_argument('--pointer',type=Path);parser.add_argument('--transmitter',type=Path);args=parser.parse_args()
    print(f'Native Wi-Fi display on http://{args.host}:{args.port}/ (no RF controls)',flush=True)
    ThreadingHTTPServer((args.host,args.port),handler(args.pointer,args.transmitter)).serve_forever()
