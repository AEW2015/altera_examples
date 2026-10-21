"""RF Arcade's native CyberEther frame. Every trace/row comes from verified capture data."""
from collections import deque
import math,time
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
from iq_bridge_lab_view import font
W,H=1800,1000
BG='#070c19';PANEL='#0d182b';LINE='#22354f';INK='#edf6ff';MUTED='#94a9c4';CYAN='#52f4ed';GOLD='#ffd16b';PINK='#ff598d';GREEN='#72f7aa'
def text(d,xy,value,size=20,fill=INK):d.text(xy,str(value),font=font(size),fill=fill)
def panel(d,box):d.rounded_rectangle(box,18,fill=PANEL,outline=LINE,width=2)
def palette(v):
 anchors=np.array([[5,10,25],[15,34,77],[27,71,149],[43,133,185],[46,219,219],[140,238,167],[255,209,107],[255,85,141]],float)
 z=np.clip(v,0,1)*(len(anchors)-1);i=np.minimum(z.astype(int),len(anchors)-2);f=(z-i)[...,None]
 return (anchors[i]*(1-f)+anchors[i+1]*f).astype(np.uint8)
def curve(d,box,values,limits,color,width=2):
 l,t,r,b=box;lo,hi=limits
 if len(values)<2:return
 y=np.clip((np.asarray(values)-lo)/max(hi-lo,1e-9),0,1)
 d.line([(l+i*(r-l)/(len(y)-1),b-v*(b-t))for i,v in enumerate(y)],fill=color,width=width)
class Arcade:
 def __init__(self):
  self.rows=deque(maxlen=180);self.peaks=deque(maxlen=40);self.key=None;self.stamp=None;self.last=None;self.last_scene=None;self.marks=deque(maxlen=180)
  self.rescue_before=None
 def rescue_key(self,c):
  ddc=c.get('ddc')or{}
  if c.get('input_kind')!='two-tone' or not c.get('input_id'):return None
  return (c['input_id'],ddc.get('phase'),ddc.get('output_rate'),ddc.get('output_samples'),
   ddc.get('bypass_flags',0)&~2,ddc.get('digital_gain_q8'),ddc.get('digital_gain_bypass'),len(c.get('ddc_spectrum_db',[])))
 def before_spectrum(self,c):
  if not c or (c.get('ddc')or{}).get('bypass_flags',0)&2:return None
  if self.rescue_before and self.rescue_before['key']==self.rescue_key(c):return self.rescue_before['spectrum']
  return None
 def ingest(self,state):
  show=state.get('demo_night',{});required=show.get('required',{});c=state.get('latest',{}).get(required.get('view'))
  ready=bool(c and c.get('captured_unix',0)>=show.get('selected_unix',0)and all(c.get('acquisition',{}).get(k)==v for k,v in required.items()))
  if ready:
   error=(c.get('ddc')or {}).get('max_reference_error',c.get('max_reference_error'))
   ready=error==0
  if not ready:return False
  if c['captured_unix']==self.stamp:return True
  self.stamp=c['captured_unix'];ddc=c.get('ddc');raw=c['raw'];cfg=c['acquisition']
  key=('generated'if raw['source']==3 else'RF',raw['source'],raw['frequency'],ddc['output_rate']if ddc else raw['rate'],c.get('input_kind','rf'))
  if key!=self.key:self.rows.clear();self.peaks.clear();self.marks.clear();self.key=key;self.last_scene=None
  values=np.asarray(c['ddc_spectrum_db']if ddc else c['spectra_db'][-1],float)
  comparison=self.rescue_key(c)
  if comparison is None:self.rescue_before=None
  elif ddc['bypass_flags']&2:self.rescue_before=dict(key=comparison,spectrum=values.copy())
  elif self.rescue_before and self.rescue_before['key']!=comparison:self.rescue_before=None
  row=np.interp(np.linspace(0,len(values)-1,600),np.arange(len(values)),values)
  self.rows.appendleft(row);self.marks.appendleft(show.get('title')if self.last_scene!=show.get('scene')else None)
  self.peaks.append((time.monotonic(),values));self.last=c;self.last_scene=show.get('scene');return True
 def render(self,state):
  ready=self.ingest(state);c=self.last;show=state.get('demo_night',{});now=time.monotonic();requested=show.get('title','RF ARCADE')
  image=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(image)
  for x in range(0,W,60):d.line((x,0,x,H),fill='#0c1425')
  for y in range(0,H,60):d.line((0,y,W,y),fill='#0c1425')
  text(d,(28,14),'RF / ARCADE',40,CYAN);text(d,(365,29),'ESP32  ×  AGILEX 3 FPGA  ×  CYBERETHER',22,MUTED)
  status=state.get('status','WAITING');live=ready and status not in('PAUSED','OFFLINE','STOPPED')and c and time.time()-c['captured_unix']<10
  badge='LIVE RF'if live and c['raw']['source']!=3 else'FPGA TEST SIGNAL'if live else'HELD / '+status
  d.rounded_rectangle((1395,19,1772,63),12,fill='#112a30'if live else'#302738',outline=CYAN if live else GOLD)
  text(d,(1412,29),badge,21,CYAN if live else GOLD)
  text(d,(30,77),requested,29,INK);text(d,(470,86),show.get('line','Waiting for hardware'),20,MUTED)
  if not ready:text(d,(31,118),'APPLYING SETTINGS · plots hold the last verified result',17,GOLD)
  elif c:text(d,(31,118),('RECEIVED RF · '+c['source_name'] if c['raw']['source']!=3 else'GENERATED IN FPGA · no RF transmission')+f"  /  {state.get('completed',0):,} verified passes",17,GREEN)
  self.flow(d,c,now)
  panel(d,(28,226,1228,685));text(d,(48,241),'SPECTRAL MEMORY',23,CYAN)
  text(d,(650,246),'NEWEST ↑  ·  one row per verified result',17,MUTED)
  self.waterfall(image,d,c)
  panel(d,(28,704,1228,971));text(d,(48,719),'BEFORE / AFTER FILTER'if self.before_spectrum(c)is not None else'SPECTRUM  /  PEAK MEMORY',22,CYAN)
  self.spectrum(image,d,c,now)
  panel(d,(1250,226,1772,614));text(d,(1272,242),'IQ ORBIT',23,CYAN)
  tones=(c.get('tone_measurements')or{}).get('tones',[])if c else[]
  at_dc=bool(len(tones)>1 and abs(tones[0]['output_hz'])<1e-6 and not c['ddc']['bypass_flags']&2)
  text(d,(1272,274),'Wanted at DC → a stationary point'if at_dc else'Sample plane · not recovered symbols',17,MUTED)
  self.orbit(image,d,c)
  self.metrics(d,state,c,ready)
  text(d,(30,979),'Sparse RF bursts / frozen FPGA tests · FIR, mixer, decimation, gain + meters: FPGA · FFT + graphics: host',15,MUTED)
  return image
 def flow(self,d,c,now):
  cfg=c.get('acquisition',{})if c else{};ddc=c.get('ddc',{})if c else{};flags=ddc.get('bypass_flags',0)
  synthetic=bool(c and c['raw']['source']==3)
  labels=[('FPGA PATTERN'if synthetic else'ESP32 RF','CI8 snapshot'if synthetic else'2.4 GHz burst',True),
   ('BRIDGE + RAM','CRC / provenance',True),('NCO / MIXER',f"{cfg.get('tuning_hz',0)/1e6:+g} MHz"if ddc else'bypass',bool(ddc and not flags&1)),
   ('FIR II','127 taps'if ddc else'16-tap Hamming',not bool(flags&2)if ddc else bool(c and c.get('filtered'))),
   ('DECIMATE',f"÷ {ddc.get('decimation',1)}",bool(ddc and ddc.get('decimation',1)>1)),
   ('GAIN + METERS',f"{ddc.get('digital_gain_q8',256)/256:g}×"if ddc else'bypass',bool(ddc)),('CYBERETHER','live visual engine',True)]
  for i,(title,sub,active)in enumerate(labels):
   x=28+251*i;color=CYAN if active else'#506179';d.rounded_rectangle((x,152,x+228,210),10,fill=PANEL,outline=color,width=2)
   text(d,(x+12,158),title,17,color);text(d,(x+12,183),sub,15,MUTED)
   if i<6:
    d.line((x+230,181,x+249,181),fill=LINE,width=3)
    if c:
     pos=(now*.8+i*.17)%1;px=x+231+pos*16;d.ellipse((px-3,178,px+3,184),fill=CYAN)
 def axis(self,c):
  if not c:return 'Waiting for a verified FPGA result',(-8,8)
  ddc=c.get('ddc');rate=(ddc['output_rate']if ddc else c['raw']['rate'])/1e6
  center=0 if ddc else c['raw']['frequency']/1e6
  return ('FPGA output baseband / MHz'if ddc else f"RF / MHz · channel {c['acquisition']['channel']}"),(center-rate/2,center+rate/2)
 def waterfall(self,image,d,c):
  l,t,r,b=48,281,1207,641
  if self.rows:
   values=np.asarray(self.rows);ceiling=max(float(np.percentile(values,99.5)),float(values.max())-8)+3;floor=ceiling-55
   rgb=palette((values-floor)/(ceiling-floor));tile=Image.fromarray(rgb).resize((r-l,b-t),Image.Resampling.NEAREST);image.paste(tile,(l,t));d=ImageDraw.Draw(image)
   for i,mark in enumerate(self.marks):
    if mark:
     y=t+i*(b-t)/len(self.rows);d.line((l,y,r,y),fill=GOLD);text(d,(l+8,max(t+1,y-16)),mark,12,GOLD)
   text(d,(650,265),f'{len(self.rows)} measured rows · {ceiling-55:.0f} … {ceiling:.0f} relative dB',13,MUTED)
  else:text(d,(220,420),'WAITING FOR THE FIRST VERIFIED CAPTURE',23,MUTED)
  label,(lo,hi)=self.axis(c)
  for j in range(5):
   x=l+j*(r-l)/4;text(d,(x-20,647),f'{lo+(hi-lo)*j/4:g}',15,MUTED)
  text(d,(r-410,666),label+' · host FFT',14,MUTED)
 def spectrum(self,image,d,c,now):
  if not c:return
  ddc=c.get('ddc');values=np.asarray(c['ddc_spectrum_db']if ddc else c['spectra_db'][-1]);raw=None if ddc else c['spectra_db'][0]
  self.peaks=deque([(t,v)for t,v in self.peaks if now-t<3],maxlen=40)
  peak=np.maximum.reduce([v for _,v in self.peaks])if self.peaks else values
  before=self.before_spectrum(c)
  tones=(c.get('tone_measurements')or{}).get('tones',[])
  rescue=c.get('input_kind')=='two-tone'and len(tones)>1
  hi=max(float(values.max()),float(peak.max()),float(before.max())if before is not None else -math.inf)+5
  lo=hi-(100 if rescue else 65);l,t,r,b=90,790 if rescue else 763,1207,921
  for j in range(4):
   y=t+(b-t)*j/3;d.line((l,y,r,y),fill=LINE);text(d,(39,y-8),f'{hi-(hi-lo)*j/3:.0f}',13,MUTED)
  glow=Image.new('RGB',image.size);gd=ImageDraw.Draw(glow);curve(gd,(l,t,r,b),values,(lo,hi),CYAN,5);image.paste(Image.blend(image,Image.fromarray(np.minimum(np.asarray(image,dtype=np.uint16)+np.asarray(glow.filter(ImageFilter.GaussianBlur(7))),255).astype(np.uint8)),.6));d=ImageDraw.Draw(image)
  if raw is not None:curve(d,(l,t,r,b),raw,(lo,hi),'#58677e',1)
  if before is not None:curve(d,(l,t,r,b),before,(lo,hi),PINK,3)
  else:curve(d,(l,t,r,b),peak,(lo,hi),GOLD,1)
  curve(d,(l,t,r,b),values,(lo,hi),CYAN,2)
  label,(low,high)=self.axis(c)
  if rescue:
   for tone,name,color in zip(tones,('WANTED','INTERFERER'),(GOLD,PINK)):
    frequency=tone['output_hz']/1e6;x=l+(frequency-low)/(high-low)*(r-l)
    if not l<=x<=r:continue
    title=name+(' · DC'if abs(frequency)<1e-9 else f' {frequency:+g} MHz')
    text(d,(min(r-190,max(l+4,x-75)),763),title,15,color)
    d.polygon([(x-5,t-8),(x+5,t-8),(x,t-1)],fill=color)
   if before is not None:text(d,(430,724),'PINK before FIR  /  CYAN after FIR',17,PINK)
   elif not ddc['bypass_flags']&2:text(d,(430,724),'Select Shift first to retain a matching before trace',15,MUTED)
  for j in range(5):text(d,(l+j*(r-l)/4-14,928),f'{low+(high-low)*j/4:g}',14,MUTED)
  legend='Same FPGA input, tuning, rate and gain · measured host FFT'if before is not None else'CYAN current  /  GOLD last 3 s  /  relative dB · '+label
  text(d,(52,950),legend,14,MUTED)
 def orbit(self,image,d,c):
  cx,cy,radius=1510,446,135
  for f in(.5,1):d.ellipse((cx-radius*f,cy-radius*f,cx+radius*f,cy+radius*f),outline=LINE,width=1)
  d.line((cx-radius,cy,cx+radius,cy),fill=LINE);d.line((cx,cy-radius,cx,cy+radius),fill=LINE)
  if not c:return
  ddc=c.get('ddc');points=np.asarray(c['ddc_wave']if ddc else c['scatter'][-1],float)
  limit=280 if ddc else max(16,float(np.max(np.abs(points)))*1.15)
  clips=ddc.get('gain_meters',{}).get('gain_clips',0)if ddc else c.get('clips',0)
  color=PINK if clips else CYAN
  # The fixed CI16-equivalent scale makes expansion and rail flattening visible.
  layer=Image.new('RGB',image.size);ld=ImageDraw.Draw(layer)
  xy=[(cx+np.clip(i/limit,-1,1)*radius,cy-np.clip(q/limit,-1,1)*radius)for i,q in points]
  if ddc and len(xy)>1:ld.line(xy,fill='#99405d'if clips else'#1b7d85',width=1)
  for x,y in xy:
   ld.ellipse((x-3,y-3,x+3,y+3),fill=color)
  a=np.asarray(image,dtype=np.uint16)+np.asarray(layer.filter(ImageFilter.GaussianBlur(5)))+np.asarray(layer)
  image.paste(Image.fromarray(np.minimum(a,255).astype(np.uint8)));d=ImageDraw.Draw(image)
  text(d,(1275,580),'SATURATION / HARMONICS'if clips else'FPGA CI16 / 128'if ddc else'RECEIVED CI8 SAMPLES',16,PINK if clips else MUTED)
 def metrics(self,d,state,c,ready):
  ddc=c.get('ddc',{})if c else{};meters=ddc.get('gain_meters',{});error=ddc.get('max_reference_error',c.get('max_reference_error')if c else None)
  clipping=100*meters.get('gain_clips',0)/max(1,meters.get('meter_samples',1));tones=c.get('tone_measurements',{}).get('tones',[])if c and c.get('tone_measurements')else[]
  if len(tones)>1:label,value='INTERFERER REJECTION',f"{tones[1]['attenuation_db']:.1f} dB"
  elif ddc:label,value='FPGA DIGITAL GAIN',f"{ddc.get('digital_gain_q8',256)/256:g}×"
  else:label,value='CAPTURE PAYLOAD',f"{c['payload_Bps']/1000:.1f} kB/s"if c else'—'
  rows=[(label,value,GOLD),('CLIPPED SAMPLES',f'{clipping:.1f}%'if ddc else'—',PINK if clipping else CYAN),('HARDWARE / INTEGER MATCH',f'{error} LSB'if error is not None else'—',GREEN if error==0 and ready else MUTED)]
  if len(tones)>1:
   change=-tones[0]['attenuation_db'];change=0. if abs(change)<.005 else change
   rows[1]=('WANTED TONE LEVEL CHANGE',f'{change:+.2f} dB',CYAN)
  for i,(label,value,color)in enumerate(rows):
   y=631+i*112;panel(d,(1250,y,1772,y+99));text(d,(1272,y+12),label,16,MUTED);text(d,(1272,y+36),value,39,color)
  if state.get('error'):text(d,(1265,970),'ACQUISITION ERROR · see status above',15,PINK)
