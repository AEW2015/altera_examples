#!/usr/bin/env python3
"""Live IQ bridge lab: one UART/JTAG owner, bounded snapshots, authenticated browser controls."""
from __future__ import annotations
import argparse,collections,gzip,hashlib,hmac,json,os,secrets,signal,threading,time,zlib,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
from capture_quality import configure_receiver_gain
import nios_ddc
from iq_lab_samples import PATTERNS,load_sample,synthetic_snapshot,tone_measurements,DIRECTORY
from iq_bridge import Bridge
from nios_fir import NiosFir,PROFILES,ROOT,fixed_reference

PAGES=('raw','boxcar','hamming','ddc','compare')
SOURCES=('RFS2 ESP32','PMOD A ESP32','PMOD B ESP32')
DEFAULT_RUN=ROOT/'cyberether/run/iq-bridge-lab'
LESSON=int(os.getenv('ATUM_LESSON','0'))
DEMO_NIGHT=os.getenv('ATUM_DEMO_NIGHT')=='1'

def atomic_json(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,allow_nan=False)+'\n');temp.replace(path)

def validate_settings(body):
    if not isinstance(body,dict) or set(body)-{'view','source','channel','round','continuous','once','export','rate','samples','gain_mode','gain_code','tuning_hz','decimation','ddc_bypass','ddc_input','new_snapshot','reference','digital_gain_q8','digital_gain_bypass','input_kind'}:raise ValueError('Unknown control')
    result={}
    for key,value in body.items():
        if key=='input_kind':
            if value not in ('live','fpga-impulse','fpga-tones'):raise ValueError('Unknown FIR input')
        elif key=='view':
            if value not in PAGES:raise ValueError('Unknown lesson')
        elif key in ('source','channel'):
            if type(value)is not int or value not in (range(3)if key=='source'else range(1,12)):raise ValueError('Invalid radio/channel')
        elif key=='ddc_input':
            if value not in ('live','frozen')+PATTERNS:raise ValueError('Unknown DDC input')
        elif key=='reference':
            if value not in ('pin','clear'):raise ValueError('Unknown comparison action')
        elif key=='digital_gain_q8':
            if type(value)is not int or value not in range(4097):raise ValueError('Invalid FPGA digital gain')
        elif key=='gain_mode':
            if value not in ('HARDWARE','MANUAL'):raise ValueError('Invalid gain mode')
        elif key in ('tuning_hz','decimation','ddc_bypass'):
            choices={'tuning_hz':range(-40000000,40000000),'decimation':(1,2,4),'ddc_bypass':range(4)}
            if type(value)is not int or value not in choices[key]:raise ValueError('Invalid DDC setting')
        elif key in ('rate','samples','gain_code'):
            choices={'rate':(16000000,40000000,80000000),'samples':(4096,8192,16380),'gain_code':range(82)}
            if type(value)is not int or value not in choices[key]:raise ValueError('Invalid acquisition setting')
        elif type(value)is not bool:raise ValueError('Boolean control required')
        result[key]=value
    return result

def summarize(raw,filtered=None,coeff=None,nearest=False,status=None,elapsed=1.):
    a=raw.iq();b=filtered.iq()if filtered else None
    error=None;clips=None
    if b is not None:
        expected=fixed_reference(a,coeff,nearest)
        error=int(np.max(np.abs(b.astype(np.int16)-expected.astype(np.int16))))
        full=np.column_stack([np.convolve(a[:,i].astype(np.int64),coeff)[:len(a)]for i in (0,1)])
        scaled=(full+(16384 if nearest else 0))>>15
        clips=int(np.count_nonzero(np.any((scaled>127)|(scaled < -128),axis=1)))
        if error or clips!=status['clips']:raise ValueError('FPGA FIR/reference or clipping mismatch')
    # All spectral arithmetic here is explicitly HOST DISPLAY DSP, never FPGA FFT output.
    spectra=[]
    for data in ([a,b]if b is not None else[a]):
        window=np.hanning(len(data));iq=data[:,0].astype(float)+1j*data[:,1]
        db=20*np.log10(np.maximum(np.abs(np.fft.fftshift(np.fft.fft(iq*window)))/max(1,window.sum()),1e-9))
        # Max in contiguous display bins preserves narrow peaks without connecting omitted samples.
        edges=np.linspace(0,len(db),min(1024,len(db))+1,dtype=int)
        spectra.append([float(np.max(db[x:y]))for x,y in zip(edges[:-1],edges[1:])])
    scatter_indices=np.linspace(0,len(a)-1,min(384,len(a)),dtype=int)
    wave=[a[:256].tolist()]+([b[:256].tolist()]if b is not None else[])
    return dict(raw=raw.metadata(),filtered=filtered.metadata()if filtered else None,coefficients=coeff,
        round_nearest=nearest if b is not None else None,clips=clips,max_reference_error=error,
        adc_rail_samples=int(np.count_nonzero(np.any((a==-128)|(a==127),axis=1))),
        adc_rail_percent=float(100*np.mean(np.any((a==-128)|(a==127),axis=1))),
        adc_rail_scope='Host count of CI8 samples with either component at -128 or 127; rail indicator, not calibrated analog clipping',
        nominal_burst_us=len(a)/raw.rate*1e6,
        waveform=wave,scatter=[a[scatter_indices].tolist()]+([b[scatter_indices].tolist()]if b is not None else[]),
        spectra_db=spectra,display_spectrum_backend='host numpy FFT; presentation only',
        elapsed_seconds=elapsed,payload_Bps=(len(raw.payload)+(len(filtered.payload)if filtered else 0))/max(elapsed,1e-9),
        captured_unix=time.time(),transport_crc_verified=True)

class Lab:
    def __init__(self,run):
        self.run=run;run.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.stop=threading.Event();self.latest={};self.buffers={};self.history=collections.deque(maxlen=60)
        self.settings=dict(view='hamming',source=0,channel=2,round=True,continuous=True,rate=16000000,samples=16380,gain_mode='HARDWARE',gain_code=40,tuning_hz=500000,decimation=4,ddc_bypass=0,ddc_input='live',digital_gain_q8=256,digital_gain_bypass=True,input_kind='live')
        if LESSON:
            self.settings.update(source=0,channel=2,rate=16000000,samples=4096,continuous=True)
            if LESSON<=2:self.settings.update(view='raw')
            elif LESSON==3:self.settings.update(view='hamming',input_kind='fpga-impulse')
            elif LESSON==4:self.settings.update(view='ddc',ddc_input='two-tone',tuning_hz=500000,decimation=4,ddc_bypass=0)
            else:self.settings.update(view='ddc',ddc_input='single-tone',tuning_hz=0,decimation=1,ddc_bypass=2,digital_gain_q8=256,digital_gain_bypass=False)
        self.reference=None;self.reference_payload=None;self.reference_requested=None;self.new_snapshot=False;self.revision=0;self.once=False;self.export_requested=False;self.export_count=0
        self.state=dict(schema='iq_bridge_lab_v1',status='STARTING',error=None,latest={},settings=self.settings.copy(),completed=0,radio_acquisitions=0,pattern_generations=0,reference=None,
            fpga=(json.loads((ROOT/'cyberether/run/active-fpga.json').read_text())if (ROOT/'cyberether/run/active-fpga.json').exists()else {}),history=[],exports=[],hardware_state=None)
        self.show=None
        if DEMO_NIGHT:
            from rf_arcade import Showreel
            self.show=Showreel(self)
        self.publish()
    def publish(self):
        with self.lock:
            self.state.update(settings=self.settings.copy(),latest=dict(self.latest),history=list(self.history),updated_unix=time.time())
            if self.show:self.state['demo_night']=self.show.status()
            atomic_json(self.run/'state.json',self.state)
    def update(self,body):
        body=validate_settings(body)
        with self.lock:
            if body.get('input_kind','live')!='live'and (LESSON in (1,2)or not self.state['fpga'].get('fpga_fir')):raise ValueError('FPGA FIR test input requires a FIR checkpoint')
            candidate=self.settings|{k:v for k,v in body.items()if k in self.settings}
            nios_ddc.phase_increment(candidate['tuning_hz'],16000000 if candidate['ddc_input']in PATTERNS else candidate['rate'])
            if body.get('reference')=='pin'and 'ddc'not in self.latest:raise ValueError('Run a DDC result before pinning')
            for key in ('view','source','channel','round','continuous','rate','samples','gain_mode','gain_code','tuning_hz','decimation','ddc_bypass','ddc_input','digital_gain_q8','digital_gain_bypass','input_kind'):
                if key in body:self.settings[key]=body[key]
            if body.get('reference'):
                self.reference_requested=body['reference']
                if body['reference']=='pin':
                    if self.settings['ddc_input']=='live':self.settings['ddc_input']='frozen'
                    self.once=True
            if body.get('new_snapshot'):
                self.new_snapshot=True;self.once=True
            if body.get('once'):self.once=True
            if body.get('export'):self.export_requested=True
            self.revision+=1;self.publish()
            return dict(accepted=True,settings=self.settings.copy(),revision=self.revision)
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.state))
    def export(self):
        with self.lock:
            mode=self.settings['view'];mode=mode if mode!='compare'else self.state.get('acquiring','hamming')
            if mode not in self.buffers:raise ValueError('Capture this lesson before exporting')
            if self.export_count>=20:raise ValueError('20 exports saved; start a new run directory for more')
            a,b,meta=self.buffers[mode];self.export_count+=1
            d=self.run/'captures'/f'{time.time_ns()}-{mode}';d.mkdir(parents=True)
            (d/'raw.ci8').write_bytes(a)
            if b is not None:(d/('ddc.ci16'if meta.get('ddc')else'filtered.ci8')).write_bytes(b)
            if meta.get('reference_compatible')and self.reference_payload is not None:
                (d/'reference.ci16').write_bytes(self.reference_payload);atomic_json(d/'reference-metadata.json',self.reference)
            atomic_json(d/'metadata.json',meta)
            self.state['exports'].append(str(d));self.publish()
    def raw_work(self):
        from contextlib import nullcontext
        from notebook_monitor import PassiveMonitor
        while not self.stop.is_set():
            try:
                with Bridge(background=True)as bridge:
                    prepared=None
                    monitor=PassiveMonitor(self.run)if LESSON==2 else None
                    try:
                        while not self.stop.is_set():
                            with self.lock:
                                config=self.settings.copy();once=self.once;self.once=False
                            if not config['continuous']and not once:
                                bridge.idle_status()
                                with self.lock:
                                    telemetry=dict(monitor.value)if monitor else {}
                                    self.state.update(status='PAUSED',telemetry=telemetry)
                                    previous=self.history[-1].get('telemetry',{})if self.history else {}
                                    if monitor and telemetry.get('seq')is not None and telemetry.get('seq')!=previous.get('seq'):
                                        self.history.append(dict(time=time.time(),Bps=0,mode='raw',paused=True,telemetry=telemetry))
                                self.publish();self.stop.wait(.3);continue
                            if prepared!=(config['source'],config['channel'],config['rate']):
                                bridge.prepare_sdr(config['source'],2407+5*config['channel'],config['rate'])
                                prepared=config['source'],config['channel'],config['rate']
                            started=time.monotonic()
                            raw=next(bridge.captures(1,source=config['source'],samples=config['samples'],rate=config['rate'],pipeline=False))
                            result=summarize(raw,elapsed=time.monotonic()-started)
                            result.update(mode='raw',source_name=SOURCES[raw.source],acquisition=config.copy(),image_sha256=self.state['fpga']['sha256'])
                            with self.lock:
                                self.latest['raw']=result;self.history.append(dict(time=time.time(),Bps=result['payload_Bps'],mode='raw',telemetry=dict(monitor.value)if monitor else {}))
                                self.state.update(status='LIVE',error=None,completed=self.state['completed']+1,radio_acquisitions=self.state['radio_acquisitions']+1,last_mode='raw',hardware_state=bridge.status(),telemetry=dict(monitor.value)if monitor else {})
                            self.publish();self.stop.wait(.25)
                    finally:
                        if monitor:monitor.close()
            except Exception as exc:
                self.state.update(status='OFFLINE',error=str(exc));self.publish();self.stop.wait(3)
        self.state['status']='STOPPED';self.publish()

    def work(self):
        if LESSON in (1,2):return self.raw_work()
        # One persistent owner avoids per-capture JTAG startup and coefficient reload.
        while not self.stop.is_set():
            try:
                active=json.loads((ROOT/'cyberether/run/active-fpga.json').read_text())
                if not active.get('fpga_fir'):raise RuntimeError('Build and load a FIR-capable checkpoint first')
                with Bridge(background=True)as bridge,NiosFir()as nios:
                    nios.gain_supported=active.get('fpga_gain_meter',False)
                    nios.command('PAIR',0);prepared=None;gain_applied=None;configured=None;acquiring='hamming';frozen=None
                    while not self.stop.is_set():
                        with self.lock:
                            config=self.settings.copy();once=self.once;self.once=False;export=self.export_requested;self.export_requested=False;refresh=self.new_snapshot;self.new_snapshot=False;reference_action=self.reference_requested;self.reference_requested=None
                        if refresh:
                            frozen=None;self.reference=None;self.reference_payload=None
                        elif reference_action=='pin':
                            with self.lock:
                                self.reference=json.loads(json.dumps(self.latest['ddc']));self.reference_payload=self.buffers['ddc'][1]
                        elif reference_action=='clear':self.reference=None;self.reference_payload=None
                        with self.lock:self.state['reference']=self.reference
                        if export:
                            try:self.export()
                            except ValueError as exc:
                                with self.lock:self.state['error']=str(exc)
                        if not config['continuous']and not once:
                            bridge.idle_status();self.state.update(status='PAUSED',hardware_state=nios.status());self.publish();self.stop.wait(.3);continue
                        mode=config['view']if config['view']!='compare'else acquiring
                        acquiring=mode
                        with self.lock:self.state.update(status='CONFIGURING',acquiring=mode,error=None)
                        self.publish()
                        fir_test=mode in ('boxcar','hamming')and config['input_kind']!='live'
                        synthetic=(mode=='ddc'and config['ddc_input']in PATTERNS)or fir_test
                        if mode!='ddc':frozen=None
                        if not synthetic and prepared!=(config['source'],config['channel'],config['rate']):
                            if prepared and prepared[0]in(1,2)and prepared[0]!=config['source']:
                                bridge.radio_write(prepared[0],'MODE MONITOR\n');time.sleep(.2);bridge.control(2,prepared[0],115200);time.sleep(.4)
                            bridge.prepare_sdr(config['source'],2407+5*config['channel'],config['rate'])
                            prepared=config['source'],config['channel'],config['rate']
                            gain_applied=None
                        if not synthetic and gain_applied!=(config['source'],config['gain_mode'],config['gain_code']):
                            def gain_command(source,command):
                                prefix='LIMITS 'if command=='LIMITS?'else 'GAIN 'if command=='GAIN?'else 'OK'
                                return bridge.radio_command(source,command,prefix)
                            gain_readback=configure_receiver_gain(config['source'],gain_command,config['gain_mode'],config['gain_code'],config['rate'])
                            gain_applied=config['source'],config['gain_mode'],config['gain_code']
                        wanted=(mode,config['round'])
                        if configured!=wanted:
                            nios.command('PAIR',0)
                            if mode in ('boxcar','hamming'):nios.preset(1 if mode=='boxcar'else 2);nios.command('ROUND',int(config['round']));nios.command('PAIR',1)
                            configured=wanted
                        with self.lock:self.state['status']='ACQUIRING'
                        self.publish();started=time.monotonic()
                        if mode=='ddc':
                            if not active.get('fpga_ddc'):raise RuntimeError('DDC image not qualified/loaded')
                            if config['ddc_input']!='live':bridge.idle_status()
                            key=tuple(config[k]for k in ('source','channel','rate','samples','gain_mode','gain_code'))if not synthetic else config['ddc_input']
                            reused=frozen is not None and frozen['key']==key and config['ddc_input']!='live'
                            if not reused:
                                if synthetic:
                                    if not active.get('fpga_replay_patterns'):raise RuntimeError('Load the long-pattern FPGA image first')
                                    _,spec=load_sample(config['ddc_input']);nios.command('TEST',spec['test_id']);snapshot_status=nios.wait(2)
                                    raw=synthetic_snapshot(config['ddc_input'],snapshot_status);self.state['pattern_generations']+=1
                                else:
                                    nios.command('ARM');raw=next(bridge.captures(1,source=config['source'],samples=config['samples'],rate=config['rate'],pipeline=False));nios.wait(2);self.state['radio_acquisitions']+=1
                                frozen=dict(key=key,raw=raw,id=f'{raw.source}:{raw.job}:{raw.raw_crc:08x}:{time.time_ns()}',created_unix=time.time(),gain=None if synthetic else gain_readback)
                            raw=frozen['raw'];filtered=None
                            current=nios.status()
                            if(current['job'],current['source'],current['samples'],current['raw_crc'])!=(raw.job,raw.source,raw.samples,raw.raw_crc):raise ValueError('Frozen FPGA input changed; acquire a new snapshot')
                            nios_ddc.run(nios,raw.rate,config['tuning_hz'],config['decimation'],config['ddc_bypass'],config['digital_gain_q8'],config['digital_gain_bypass'])
                            ddc_meta,ddc_raw,ddc_out=nios_ddc.dump(nios)
                            if ddc_raw.tobytes()!=raw.payload or (ddc_meta['job'],ddc_meta['source'],ddc_meta['samples'],ddc_meta['rate'],ddc_meta['frequency'],ddc_meta['raw_crc'])!=(raw.job,raw.source,raw.samples,raw.rate,raw.frequency,raw.raw_crc):raise ValueError('DDC raw capture provenance mismatch')
                        elif fir_test:
                            bridge.idle_status()
                            from lesson_evidence import capture_fir_test
                            raw,filtered,fir_test_meta=capture_fir_test(nios,config)
                            self.state['pattern_generations']+=1
                        elif mode=='raw':raw=next(bridge.captures(1,source=config['source'],samples=config['samples'],rate=config['rate'],pipeline=False));filtered=None
                        else:raw,filtered=bridge.paired_capture(config['source'],config['samples'],config['rate'])
                        if mode!='ddc'and not synthetic:self.state['radio_acquisitions']+=1
                        elapsed=time.monotonic()-started;status=nios.status()
                        coeff=PROFILES[1 if mode=='boxcar'else 2]if mode in ('boxcar','hamming')else None
                        if filtered and not fir_test and filtered.aux&0xffffffff!=(0x80010000|(int(config['round'])<<8)|(1 if mode=='boxcar'else 2)):
                            raise ValueError('Applied coefficient/rounding descriptor differs from requested settings')
                        result=summarize(raw,filtered,coeff,config['round'],status,elapsed)
                        if fir_test:
                            result.update(pattern_identity_verified=True,snapshot_crc_verified=True,transport_crc_verified=False,fir_readback=fir_test_meta)
                            configured=None  # TEST disables pairing; restore configuration before the next live capture.
                        if not synthetic and(raw.samples!=config['samples']or raw.rate!=config['rate']):raise ValueError('Capture length/rate metadata mismatch')
                        if mode=='ddc':
                            result.update(input_id=frozen['id'],input_created_unix=frozen['created_unix'],input_kind=config['ddc_input'],snapshot_reused=reused,transport_crc_verified=not synthetic,snapshot_crc_verified=True)
                            result['reference_compatible']=bool(self.reference and self.reference.get('input_id')==frozen['id']and self.reference['ddc']['output_rate']==ddc_meta['output_rate'])
                            if result['reference_compatible']:result['reference_config']=self.reference['ddc']
                            result['tone_measurements']=tone_measurements(config['ddc_input'],ddc_raw,ddc_out,ddc_meta)if synthetic else None
                            v=ddc_out.astype(float)/128.
                            skip=(126+config['decimation']-1)//config['decimation']if config['ddc_input']in ('two-tone','single-tone')and not config['ddc_bypass']&2 else 0
                            steady=v[skip:];w=np.hanning(len(steady));z=steady[:,0]+1j*steady[:,1]
                            db=20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(z*w,n=len(v))))/max(1,w.sum()),1e-9))
                            result['ddc_fft_startup_samples_excluded']=skip
                            edges=np.linspace(0,len(db),min(1024,len(db))+1,dtype=int)
                            result.update(payload_Bps=(2*len(raw.payload)+ddc_out.nbytes)/max(elapsed,1e-9),payload_rate_scope='Raw IQB1 acquisition plus raw/processed JTAG readback; payload bytes only',ddc=ddc_meta,ddc_spectrum_db=[float(np.max(db[x:y]))for x,y in zip(edges[:-1],edges[1:])],ddc_wave=v[:256].tolist())
                        result.update(acquisition=config.copy(),receiver_gain=None if synthetic else frozen['gain']if mode=='ddc'else gain_readback,rate_scope='Nominal CAP16 mode; IQB1 rate is configured metadata, not independent clock measurement',cap16_mode={16000000:6,40000000:1,80000000:0}[config['rate']])
                        result.update(mode=mode,source_name=('FPGA '+(config['input_kind']if fir_test else config['ddc_input'])+' · SYNTHETIC')if synthetic else SOURCES[raw.source],image_sha256=active['sha256'])
                        with self.lock:
                            self.latest[mode]=result;self.buffers[mode]=(raw.payload,filtered.payload if filtered else ddc_out.tobytes()if mode=='ddc'else None,result)
                            self.history.append(dict(time=time.time(),Bps=result['payload_Bps'],mode=mode))
                            self.state.update(status='LIVE',error=None,hardware_state=status,completed=self.state['completed']+1)
                            # Raw view may display the raw half of the same physical filtered pair.
                            self.state['last_mode']=mode
                        if self.show:
                            with self.lock:self.show.on_result(result)
                        self.publish();self.stop.wait(.25)
                    nios.command('PAIR',0);nios.preset(1);nios.command('ROUND',0)
                    if prepared and prepared[0]in(1,2):
                        bridge.radio_write(prepared[0],'MODE MONITOR\n');time.sleep(.2);bridge.control(2,prepared[0],115200)
            except Exception as exc:
                print(time.strftime('%Y-%m-%d %H:%M:%S'),'acquisition:',repr(exc),flush=True)
                with self.lock:self.state.update(status='OFFLINE',error=str(exc))
                self.publish();self.stop.wait(3)
        self.state['status']='STOPPED';self.publish()

class Server(ThreadingHTTPServer):
    daemon_threads=True

def handler(lab,token,public_url):
    client_html=[None]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,code,value,kind='application/json'):
            b=json.dumps(value).encode()if kind=='application/json'else value.encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def authenticated(self):return hmac.compare_digest(self.headers.get('X-Lab-Token',''),token)
        def do_GET(self):
            path=urlsplit(self.path).path
            if path=='/':return self.respond(200,(Path(__file__).with_name('demo_night.html'if DEMO_NIGHT else'notebook_focus.html'if LESSON else 'iq_bridge_lab.html')).read_text(),'text/html; charset=utf-8')
            if path=='/samples/clean-ddc.zip':
                data=(DIRECTORY.parent/'clean-ddc.zip').read_bytes();self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition','attachment; filename=clean-ddc.zip');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if path=='/native':
                # Serve the exact bundled client on this origin. Its documented-in-code
                # signaller URL parameter still connects directly to CyberEther's broker.
                try:
                    if client_html[0]is None:
                        broker=public_url.rsplit(':',1)[0]+':'+os.getenv('ATUM_VIEWER_PORT','8687')+'/remote'
                        with urllib.request.urlopen(broker,timeout=3)as response:body=response.read(2*1024*1024+1)
                        if len(body)>2*1024*1024:raise ValueError('Remote client size limit')
                        if body.startswith(b'\x1f\x8b'):body=gzip.decompress(body)
                        client_html[0]=body.decode('utf-8')
                    return self.respond(200,client_html[0],'text/html; charset=utf-8')
                except Exception:return self.respond(503,dict(error='Native viewer is starting'))
            if not self.authenticated():return self.respond(403,dict(error='Lab token required'))
            if path=='/api/state':return self.respond(200,lab.snapshot())
            if path in ('/api/evidence','/api/preview'):
                from lesson_evidence import evidence,plot_data,preview
                state=lab.snapshot()
                lesson=LESSON or 5
                if path=='/api/preview':return self.respond(200,preview(lesson,state['settings']))
                proof=evidence(state,lesson)
                result=proof.pop('result')
                proof['plots']=plot_data(result)if result else None
                return self.respond(200,proof)
            if path=='/api/viewer':
                p=lab.run/'remote-join.json'
                return self.respond(200,json.loads(p.read_text())if p.exists()else dict(remote_viewer_url=None))
            return self.respond(404,dict(error='Unknown path'))
        def do_POST(self):
            if not self.authenticated():return self.respond(403,dict(error='Lab token required'))
            origin=self.headers.get('Origin')
            if origin and origin!=public_url:return self.respond(403,dict(error='Origin mismatch'))
            route=urlsplit(self.path).path
            if route not in('/api/control','/api/show'):return self.respond(404,dict(error='Unknown path'))
            if route=='/api/show'and not lab.show:return self.respond(404,dict(error='Showcase is not active'))
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=4096:raise ValueError('Control body limit')
                body=json.loads(self.rfile.read(n))
                with lab.lock:
                    if route=='/api/show':
                        result=lab.show.update(body);lab.publish()
                    else:
                        if lab.show:lab.show.auto=False
                        result=lab.update(body)
            except (ValueError,TypeError)as exc:return self.respond(400,dict(error=str(exc)))
            return self.respond(202,result)
    return Handler

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,default=DEFAULT_RUN);p.add_argument('--bind',default=os.getenv('ATUM_HOST','127.0.0.1'));p.add_argument('--port',type=int,default=8768);a=p.parse_args()
    if a.bind in ('0.0.0.0','::'):p.error('Bind to an explicit host address')
    a.run.mkdir(parents=True,exist_ok=True);token_path=a.run/'control-token.txt'
    if not token_path.exists():token_path.write_text(secrets.token_urlsafe(24));token_path.chmod(0o600)
    token=token_path.read_text().strip();lab=Lab(a.run);public=f'http://{a.bind}:{a.port}'
    atomic_json(a.run/'control-invite.json',dict(url=public+'/#'+token));(a.run/'control-invite.json').chmod(0o600)
    server=Server((a.bind,a.port),handler(lab,token,public));worker=threading.Thread(target=lab.work,name='iq-acquisition',daemon=True);worker.start()
    def stop(*_):lab.stop.set();threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:server.serve_forever(.2)
    finally:lab.stop.set();server.server_close();worker.join(25)
if __name__=='__main__':main()
