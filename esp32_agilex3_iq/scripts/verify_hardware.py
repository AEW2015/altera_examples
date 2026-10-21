import json,time,urllib.request
from pathlib import Path
import argparse,os
from common import ROOT
p=argparse.ArgumentParser(description='Check live RF FIR and FPGA clean-pattern DDC/gain on the running lab');p.add_argument('--host',default='127.0.0.1');a=p.parse_args()
root=ROOT;run=root/'cyberether/run/iq-bridge-lab'
base='http://'+a.host+':'+os.getenv('ATUM_CONTROL_PORT','8768')
end=time.monotonic()+75
while not(run/'control-token.txt').exists():
 if time.monotonic()>end:raise RuntimeError('Control service did not start')
 time.sleep(.2)
token=(run/'control-token.txt').read_text().strip()
def request(body=None):
 req=urllib.request.Request(base+'/api/'+('control'if body else 'state'),data=json.dumps(body).encode()if body else None,headers={'X-Lab-Token':token,'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=5))
def wait(predicate):
 end=time.monotonic()+80
 while time.monotonic()<end:
  s=request()
  if s.get('error'):raise RuntimeError(s['error'])
  if predicate(s):return s
  time.sleep(.3)
 raise RuntimeError('Timed out waiting for physical FPGA result')
before=request()['completed'];started=time.time()
request(dict(view='hamming',source=0,channel=2,rate=16000000,samples=16380,continuous=True))
s=wait(lambda s:s['completed']>=before+2 and s['latest'].get('hamming',{}).get('captured_unix',0)>started);fir=s['latest']['hamming'];assert fir['transport_crc_verified']and fir['max_reference_error']==0
print('PASS physical RF Hamming pair',fir['raw']['samples'],'samples; reference 0 LSB',flush=True)
started=time.time();request(dict(view='ddc',ddc_input='two-tone',continuous=False,once=True,tuning_hz=500000,decimation=4,ddc_bypass=0,digital_gain_q8=512,digital_gain_bypass=False))
s=wait(lambda s:s['latest'].get('ddc',{}).get('captured_unix',0)>started);d=s['latest']['ddc'];assert d['ddc']['max_reference_error']==0 and d['ddc']['digital_gain_q8']==512
print('PASS physical FPGA clean two-tone / DDC / 2x gain and exact meter reference',flush=True)
result=dict(status='PASS_HARDWARE',image_sha256=s['fpga']['sha256'],scope='Fresh source rebuild: live RFS2 RF -> raw/Hamming pair; FPGA two-tone -> DDC / decimation4 / 2x gain; exact output and power-meter reference checks',fir=dict(samples=fir['raw']['samples'],max_reference_error=fir['max_reference_error'],transport_crc_verified=fir['transport_crc_verified']),ddc=d['ddc'])
(run/'branch-hardware-validation.json').write_text(json.dumps(result,indent=2)+'\n')
