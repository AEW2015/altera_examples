"""RF Arcade scene controls. The showreel advances only after verified hardware results."""
import time
SCENES = {
 'airwaves': dict(title='AIRWAVES', line='Real ESP32 RF. Watch the FPGA shape the spectrum.', family='rf', seconds=16,
  controls=dict(view='hamming',ddc_input='live')),
 'fold': dict(title='THE INTERFERER', line='Two tones enter. Decimation folds the interferer into view.', family='rescue',seconds=10,
  controls=dict(view='ddc',ddc_input='two-tone',tuning_hz=0,decimation=4,ddc_bypass=2)),
 'tune': dict(title='PULL IT TO DC', line='The FPGA mixer moves the wanted tone to the center.',family='rescue',seconds=10,
  controls=dict(view='ddc',ddc_input='two-tone',tuning_hz=500000,decimation=4,ddc_bypass=2)),
 'reject': dict(title='RESCUE THE TONE', line='FIR II rejects the interferer before decimation.',family='rescue',seconds=14,
  controls=dict(view='ddc',ddc_input='two-tone',tuning_hz=500000,decimation=4,ddc_bypass=0)),
 'clean': dict(title='CLEAN SIGNAL',line='A clean FPGA tone draws a circle in the IQ plane.',family='power',seconds=10,
  controls=dict(view='ddc',ddc_input='single-tone',tuning_hz=0,decimation=1,ddc_bypass=2,digital_gain_q8=256)),
 'boost': dict(title='TURN IT UP',line='Twice the amplitude. Four times the power.',family='power',seconds=10,
  controls=dict(view='ddc',ddc_input='single-tone',tuning_hz=0,decimation=1,ddc_bypass=2,digital_gain_q8=512)),
 'overdrive': dict(title='OVERDRIVE',line='The circle hits the rails. Clipping creates new harmonics.',family='power',seconds=10,
  controls=dict(view='ddc',ddc_input='single-tone',tuning_hz=0,decimation=1,ddc_bypass=2,digital_gain_q8=4096)),
}
ORDER=tuple(SCENES)
class Showreel:
 def __init__(self,lab,clock=time.monotonic):
  self.lab=lab;self.clock=clock;self.scene='airwaves';self.auto=False;self.started=None;self.selected_unix=time.time();self.matches=0
  self.radio=0;self.channel=2;self.required=self.controls()
  lab.settings.update(self.required)
 def controls(self):
  controls=dict(source=self.radio,channel=self.channel,rate=16000000,samples=4096,continuous=True,round=True,
   digital_gain_q8=256,digital_gain_bypass=False)
  controls.update(SCENES[self.scene]['controls'])
  return controls
 def select(self,name,automatic=False):
  if name not in SCENES:raise ValueError('Unknown RF Arcade scene')
  self.scene=name;self.auto=automatic;self.started=None;self.matches=0;self.selected_unix=time.time();self.required=self.controls()
  self.lab.update(self.required)
 def update(self,body):
  if not isinstance(body,dict)or set(body)-{'scene','auto','source','channel'}:raise ValueError('Unknown show control')
  if 'scene'in body and body['scene']not in SCENES:raise ValueError('Unknown scene')
  if 'auto'in body and type(body['auto'])is not bool:raise ValueError('Boolean auto required')
  for key,choices in(('source',range(3)),('channel',range(1,12))):
   if key in body and(type(body[key])is not int or body[key]not in choices):raise ValueError('Invalid radio/channel')
  if 'source'in body:self.radio=body['source']
  if 'channel'in body:self.channel=body['channel']
  self.select(body.get('scene',self.scene),body.get('auto',False))
  return self.status()
 def accepts(self,result):
  error=(result.get('ddc')or {}).get('max_reference_error',result.get('max_reference_error'))if result else None
  return bool(result and error==0 and result.get('captured_unix',0)>=self.selected_unix and all(result.get('acquisition',{}).get(k)==v for k,v in self.required.items()))
 def on_result(self,result):
  if not self.accepts(result):return
  self.matches+=1
  if self.started is None:self.started=self.clock()
  if self.auto and self.matches>=2 and self.clock()-self.started>=SCENES[self.scene]['seconds']:
   self.select(ORDER[(ORDER.index(self.scene)+1)%len(ORDER)],automatic=True)
 def status(self):
  s=SCENES[self.scene];elapsed=0 if self.started is None else max(0,self.clock()-self.started)
  return dict(scene=self.scene,title=s['title'],line=s['line'],family=s['family'],auto=self.auto,verified_results=self.matches,
   waiting=self.started is None,elapsed=elapsed,duration=s['seconds'],selected_unix=self.selected_unix,required=self.required.copy(),
   scenes=[dict(id=k,title=v['title'],family=v['family'])for k,v in SCENES.items()])
