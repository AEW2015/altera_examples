"""Read-only native Wi-Fi monitor viewer. No device or RF operations."""
from __future__ import annotations
import argparse,json,time,math
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'cyberether/run'

def _json(path):
    if not path.is_file():return None
    if path.stat().st_size>1048576:raise ValueError('Telemetry file exceeds 1 MiB')
    value=json.loads(path.read_text(),parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    if not isinstance(value,dict):raise ValueError('Telemetry must be an object')
    return value

RAW_KIND='bounded native Wi-Fi -> raw RFS2 -> Nios receiver'
RAW_SOURCE='ota-native-wifi64-raw-iq'

def _proof_path(pointer):
    latest=_json(Path(pointer))
    if not latest:return None
    path=Path(latest['path'])
    if not path.is_absolute():path=ROOT/path
    path=path.resolve()
    if not path.is_relative_to(RUN.resolve()) or path.suffix!='.json':raise ValueError('Invalid proof path')
    return path

def _integer(value):return isinstance(value,int) and not isinstance(value,bool)

def _raw_attempt(proof):
    if proof.get('kind')!=RAW_KIND or proof.get('source')!=RAW_SOURCE or proof.get('host_dsp') is not False:raise ValueError('Not an on-device native raw-IQ receiver proof')
    attempts=proof.get('attempts')
    if not isinstance(attempts,list) or len(attempts)>32:raise ValueError('Invalid raw receiver attempt list')
    if proof.get('ota64_confirmed') is not True:return None
    for index in range(len(attempts)-1,-1,-1):
        attempt=attempts[index]
        if not isinstance(attempt,dict):raise ValueError('Invalid raw receiver attempt')
        decoder=attempt.get('decoder',{})
        if not isinstance(decoder,dict):continue
        if decoder.get('device_decode_accepted') is not True or attempt.get('known_a_identity') is not True:continue
        if attempt.get('host_dsp') is not False:raise ValueError('Raw attempt reports host DSP')
        if decoder.get('source')!='fpga-capture-ram' or decoder.get('completed') is not True:raise ValueError('Invalid raw decoder source')
        result=decoder.get('device_result',{})
        expected={'valid':1,'status':0,'stage':5,'accepted':1,'rate_code':12,'mbps':54,'packet_status':0,'source':0,'rate':40000000}
        if not isinstance(result,dict) or any(not _integer(result.get(k)) or result[k]!=v for k,v in expected.items()):raise ValueError('Raw decoder acceptance/header mismatch')
        if not _integer(result.get('length')) or not 4<=result['length']<=256:raise ValueError('Invalid raw decoded length')
        if not _integer(result.get('fcs_crc')) or not _integer(result.get('received_crc')) or result['fcs_crc']!=result['received_crc']:raise ValueError('Raw decoder FCS mismatch')
        points=decoder.get('constellation')
        if not isinstance(points,list) or not _integer(result.get('points')) or not 1<=len(points)<=480 or len(points)!=result['points']:raise ValueError('Invalid raw constellation length')
        for n,point in enumerate(points):
            if not isinstance(point,dict) or not _integer(point.get('index')) or point['index']!=n or not _integer(point.get('scale')) or point['scale']!=8192 or any(not _integer(point.get(k)) or not -32768<=point[k]<=32767 for k in ('i','q')):raise ValueError('Invalid device Q13 point')
        if not _integer(result.get('symbols')) or not 1<=result['symbols']<=10 or result['points']!=48*result['symbols'] or result['symbols']!=(22+8*result['length']+215)//216:raise ValueError('Raw DATA symbol/count mismatch')
        for key in ('ticks_lo','ticks_hi','clock_hz','frequency'):
            if not _integer(result.get(key)) or result[key]<0:raise ValueError('Invalid raw device timing/frequency')
        if not result['clock_hz'] or result['ticks_lo']>0xffffffff or result['ticks_hi']>0xffffffff:raise ValueError('Invalid raw device clock')
        return index
    return None

def state(pointer=None,transmitter=None,raw_pointer=None):
    result={'proof':None,'transmitter':None,'age_s':None,'status':'waiting','raw_proof':None,'raw_attempt_index':None,'raw_qualified':False,'raw_status':'waiting','raw_age_s':None}
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
    # Raw-IQ evidence is independent of the native packet-monitor panel: an
    # unsafe/missing raw pointer must not hide a valid native monitor proof.
    try:
        path=_proof_path(raw_pointer or RUN/'wifi64-raw-latest.json')
        if path is not None:
            proof=_json(path)
            if not proof:raise ValueError('Missing raw receiver proof')
            index=_raw_attempt(proof)
            result.update(raw_proof=proof,raw_attempt_index=index,raw_qualified=index is not None,raw_status='qualified' if index is not None else 'not_qualified')
            end=proof.get('finished_unix')
            if isinstance(end,(int,float)) and math.isfinite(end):result['raw_age_s']=max(0,time.time()-end)
    except (OSError,ValueError,KeyError,TypeError) as error:
        result['raw_status']='telemetry_error';result['raw_error']=str(error)
    return result

def handler(pointer=None,transmitter=None,raw_pointer=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            route=self.path.split('?',1)[0]
            if route=='/api/state':
                payload=json.dumps(state(pointer,transmitter,raw_pointer),allow_nan=False).encode();content_type='application/json'
            elif route in ('/','/index.html'):
                payload=(ROOT/'cyberether/wifi64_native.html').read_bytes();content_type='text/html; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_POST(self):self.send_error(405,'Display only; no RF controls')
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='0.0.0.0');parser.add_argument('--port',type=int,default=8774);parser.add_argument('--pointer',type=Path);parser.add_argument('--transmitter',type=Path);parser.add_argument('--raw-pointer',type=Path);args=parser.parse_args()
    print(f'Native Wi-Fi display on http://{args.host}:{args.port}/ (no RF controls)',flush=True)
    ThreadingHTTPServer((args.host,args.port),handler(args.pointer,args.transmitter,args.raw_pointer)).serve_forever()
