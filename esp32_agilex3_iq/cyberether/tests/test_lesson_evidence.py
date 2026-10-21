import copy,json,re,sys,tempfile,threading,time,unittest,urllib.request,urllib.error,zlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lesson_evidence import fir_fixture,capture_fir_test,evidence,preview
from iq_bridge_lab import Lab,Server,handler,summarize
from iq_bridge_lab_view import render_diagnostic
from nios_fir import PROFILES,fixed_reference

class FakeNios:
    def __init__(self,config,corrupt=False):self.config=config;self.calls=[];self.corrupt=corrupt
    def command(self,*args):self.calls.append(args);return {}
    def wait(self,*args):self.calls.append(('WAIT',*args));return {}
    def run(self,*args):self.calls.append(('RUN',*args));return {}
    def dump(self):
        raw=fir_fixture(self.config['input_kind']);coeff=PROFILES[1 if self.config['view']=='boxcar'else 2]
        out=fixed_reference(raw,coeff,self.config['round'])
        if self.corrupt:raw=raw.copy();raw[0,0]^=1
        meta=dict(source=3,samples=128,rate=16000000,frequency=0,mode=1,round=int(self.config['round']),profile=1 if self.config['view']=='boxcar'else 2,
            job=0xffff0001,coefficients_current=coeff,raw_crc=zlib.crc32(raw.tobytes()),filtered_crc=zlib.crc32(out.tobytes()),clips=0)
        return meta,raw,out

def fir_state():
    config=dict(view='hamming',input_kind='fpga-impulse',round=True,source=0,channel=2,rate=16000000,samples=4096,gain_mode='HARDWARE',gain_code=40)
    nios=FakeNios(config);raw,out,meta=capture_fir_test(nios,config)
    c=summarize(raw,out,PROFILES[2],True,meta)
    c.update(acquisition=config.copy(),pattern_identity_verified=True,snapshot_crc_verified=True,transport_crc_verified=False)
    return dict(settings=config,latest={'hamming':c},status='LIVE',completed=1,history=[],fpga=dict(fpga_fir=True,stage_relative='fpga_hub/iq_bridge/vds_demo_03_fir'))

class EvidenceTests(unittest.TestCase):
    def test_fixture_matches_rtl_and_test_sequence(self):
        root=Path(__file__).resolve().parents[2]
        rtl=(root/'fpga_hub/iq_bridge/vds_demo_03_fir/rtl/iq_fir_capture.sv').read_text()
        words=[int(v,16)for v in re.findall(r"5'd\d+:pattern_word=16'h([0-9a-f]+)",rtl)]
        self.assertEqual(fir_fixture('fpga-tones').view('<u2').ravel().tolist(),words*4)
        self.assertEqual(fir_fixture('fpga-impulse')[0].tolist(),[64,32])
        s=fir_state();n=FakeNios(s['settings']);capture_fir_test(n,s['settings'])
        self.assertEqual(n.calls,[('PAIR',0),('TEST',1),('WAIT',2),('RUN',1)])
        with self.assertRaisesRegex(ValueError,'identity'):capture_fir_test(FakeNios(s['settings'],True),s['settings'])

    def test_verified_requires_readback_crc_and_current_settings(self):
        s=fir_state();self.assertEqual(evidence(s,3)['status'],'VERIFIED')
        for change in ('crc','reference','pattern','samples','round'):
            broken=copy.deepcopy(s);c=broken['latest']['hamming']
            if change=='crc':c['snapshot_crc_verified']=False
            elif change=='reference':c['max_reference_error']=1
            elif change=='pattern':c['pattern_identity_verified']=False
            elif change=='samples':c['raw']['samples']=129
            else:c['round_nearest']=False
            self.assertEqual(evidence(broken,3)['status'],'MISMATCH',change)
        s['settings']['round']=False
        self.assertEqual(evidence(s,3)['status'],'APPLYING')
        s=fir_state();s['status']='OFFLINE';s['error']='UART disconnected'
        self.assertEqual(evidence(s,3)['status'],'ERROR')
        self.assertEqual(evidence(fir_state(),3,now=time.time()+60)['status'],'STALE')
        s=fir_state();s['status']='PAUSED';self.assertEqual(evidence(s,3)['status'],'HELD')

    def test_nios_feature_requires_fresh_counter_evidence(self):
        s=fir_state()
        self.assertEqual(evidence(s,2)['status'],'MISMATCH')
        s['telemetry']=dict(seq=0,received_unix=time.time(),capture_errors=0,radio_errors=0)
        self.assertEqual(evidence(s,2)['status'],'VERIFIED')
        s['telemetry']['received_unix']-=6
        self.assertEqual(evidence(s,2)['status'],'MISMATCH')
        s['status']='OFFLINE';s['settings']['round']=False
        self.assertEqual(evidence(s,2)['status'],'ERROR')
        s['latest']={}
        self.assertEqual(evidence(s,2)['status'],'ERROR')

    def test_preview_is_explicit_and_never_opens_hardware(self):
        for lesson in range(1,6):
            with patch('iq_bridge_lab.Bridge',side_effect=AssertionError('Unexpected device')):
                result=preview(lesson,dict(view='hamming',tuning_hz=500000,decimation=4,ddc_bypass=0,digital_gain_q8=256,digital_gain_bypass=True))
            self.assertIn('NOT HARDWARE',result['origin']);json.dumps(result,allow_nan=False)
            self.assertTrue(result['plots']['input_spectrum'])
        self.assertEqual(render_diagnostic(fir_state(),3).size,(1800,1000))

    def test_feature_readbacks_are_not_configuration_echoes(self):
        config=dict(view='ddc',ddc_input='single-tone',tuning_hz=0,decimation=1,ddc_bypass=2,digital_gain_q8=512,digital_gain_bypass=False)
        c=dict(acquisition=config.copy(),raw=dict(source=3,samples=4096,rate=16000000),snapshot_crc_verified=True,captured_unix=time.time(),
          ddc=dict(phase=0,decimation=1,bypass_flags=2,digital_gain_q8=512,digital_gain_bypass=False,output_samples=4096,max_reference_error=0))
        s=dict(settings=config,latest={'ddc':c},status='LIVE')
        self.assertEqual(evidence(s,5)['status'],'VERIFIED')
        for field,value in [('phase',1),('decimation',4),('bypass_flags',0),('digital_gain_q8',256),('digital_gain_bypass',True),('output_samples',0)]:
            b=copy.deepcopy(s);b['latest']['ddc']['ddc'][field]=value
            self.assertEqual(evidence(b,5)['status'],'MISMATCH',field)

    def test_worker_routes_fir_test_without_radio_capture(self):
        import iq_bridge_lab as backend
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory()as directory,patch.object(backend,'LESSON',3):
            root=Path(directory);active=root/'cyberether/run';active.mkdir(parents=True)
            (active/'active-fpga.json').write_text(json.dumps(dict(fpga_fir=True,sha256='mock-image')))
            lab=Lab(root/'lab');lab.settings.update(fir_state()['settings'])
            nios=FakeNios(lab.settings)
            nios.preset=lambda profile: nios.calls.append(('PRESET',profile))
            nios.status=lambda:dict(clips=0)
            original_dump=nios.dump
            def dump():
                result=original_dump();lab.stop.set();return result
            nios.dump=dump
            serial_owner=MagicMock();serial_owner.__enter__.return_value=serial_owner
            serial_owner.captures.side_effect=AssertionError('Synthetic check attempted radio capture')
            jtag_owner=MagicMock();jtag_owner.__enter__.return_value=nios
            with patch.object(backend,'ROOT',root),patch.object(backend,'Bridge',return_value=serial_owner),patch.object(backend,'NiosFir',return_value=jtag_owner):
                lab.work()
            self.assertEqual(lab.state['completed'],1)
            self.assertEqual(lab.state['radio_acquisitions'],0)
            self.assertEqual(lab.state['pattern_generations'],1)
            self.assertTrue(lab.latest['hamming']['pattern_identity_verified'])
            self.assertEqual(lab.latest['hamming']['max_reference_error'],0)
            serial_owner.prepare_sdr.assert_not_called()

    def test_paused_nios_monitor_keeps_counter_windows_fresh(self):
        import iq_bridge_lab as backend
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory()as directory,patch.object(backend,'LESSON',2):
            lab=Lab(Path(directory));lab.settings['continuous']=False
            owner=MagicMock();owner.__enter__.return_value=owner
            owner.idle_status.side_effect=lambda:lab.stop.set()
            monitor=MagicMock();monitor.value=dict(seq=7,received_unix=time.time(),r1_uart_Bps=0,host_iq_Bps=0)
            with patch.object(backend,'Bridge',return_value=owner),patch('notebook_monitor.PassiveMonitor',return_value=monitor):
                lab.raw_work()
            self.assertEqual(lab.state['telemetry']['seq'],7)
            self.assertEqual(lab.history[-1]['telemetry']['seq'],7)
            self.assertTrue(lab.history[-1]['paused'])
            owner.captures.assert_not_called();monitor.close.assert_called_once()

    def test_api_auth_and_fixture_capability(self):
        with tempfile.TemporaryDirectory()as directory,patch('iq_bridge_lab.LESSON',3):
            lab=Lab(Path(directory));s=fir_state();lab.settings.update(s['settings']);lab.latest=s['latest'];lab.state.update(s);lab.state['settings']=lab.settings.copy()
            lab.update({'input_kind':'fpga-tones'})
            self.assertEqual(lab.settings['input_kind'],'fpga-tones')
            server=Server(('127.0.0.1',0),handler(lab,'test-token','http://trusted'))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}'
                for path in ('evidence','preview'):
                    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+'/api/'+path)
                    req=urllib.request.Request(url+'/api/'+path,headers={'X-Lab-Token':'test-token'})
                    response=json.load(urllib.request.urlopen(req))
                    self.assertIn('plots',response)
                with patch('iq_bridge_lab.LESSON',1):
                    with self.assertRaises(ValueError):lab.update({'input_kind':'fpga-impulse'})
            finally:server.shutdown();server.server_close()
