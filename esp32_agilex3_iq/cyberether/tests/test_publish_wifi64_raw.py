"""Offline publisher integrity/scope tests; all fixtures synthetic, no devices."""
import copy,hashlib,json,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import publish_wifi64_raw as pub
from wifi64_vectors import native_frame

class PublishRawTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.run=self.root/'cyberether/run';self.run.mkdir(parents=True)
  self.patches=[patch.object(pub,'ROOT',self.root),patch.object(pub,'RUN_DIR',self.run),patch.object(pub,'LATEST',self.run/'wifi64-raw-latest.json')]
  for p in self.patches:p.start()
  self.path=self.run/'proof.json';self.proof=self.fixture();self.write()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def write(self):self.path.write_text(json.dumps(self.proof))
 def fixture(self):
  payload=bytes(16384);archive=self.run/'raw.ci8';archive.write_bytes(payload);sha=hashlib.sha256(payload).hexdigest();crc=zlib.crc32(payload)
  frame=native_frame(run=9,packet=0,seed=1);frame+=zlib.crc32(frame).to_bytes(4,'little');fcs=int.from_bytes(frame[-4:],'little')
  clean=dict(tx_idle_verified=True,monitor_stop_verified=True,mirror_cancel_verified=True)
  raw=dict(kind=1,source=0,job=7,rate=40000000,frequency=2462000000,samples=8192,length=16384,error=0,raw_crc=crc,payload_sha256=sha)
  identity={k:raw[k] for k in ('job','source','rate','frequency','raw_crc')};identity['conjugate_q']=1
  device=dict(identity,valid=1,status=0,stage=5,accepted=1,rate_code=12,mbps=54,length=92,points=192,symbols=4,packet_status=0,signal_status=0,acquisition_status=0,received_crc=fcs,fcs_crc=fcs)
  decoder=dict(source='fpga-capture-ram',completed=True,decode_requested=True,device_decode_accepted=True,capture_ram_changed_after_copy=False,ber_measured=False,raw_iq_transferred_to_host=False,initial_status=identity,final_status=identity,device_result=device,decoded_psdu_hex=frame.hex(),decoded_bytes=[dict(index=i,value=v,packet_status=0) for i,v in enumerate(frame)],constellation=[dict(index=i,i=1,q=-1,scale=8192) for i in range(192)])
  lines=[{'source':2,'line':line} for line in ('WIFI64_MON,PACKET,run=9,packet=0,seed=1,body_ok=1','WIFI64_MON,PHY,run=9,packet=0,rate_code=12,sig_mode=0,rx_state=0,rssi=-42,ch=11','WIFI64_MON,META,run=9,packet=0,timestamp_us=1,length=92,native_rx=1')]
  attempt=dict(completed=True,ota64_confirmed=True,tx_start_requested=True,tx_success=True,known_a_identity=True,device_decode_accepted=True,raw_known_a_decode_confirmed=True,raw_transferred_for_transport_only=True,host_dsp=False,ber_measured=False,tx_job_cancelled=False,tx_start='WIFI64_TX,START,job=1',tx_terminal='WIFI64_TX,DONE,job=1',cleanup=clean,run=9,channel=11,requested_frequency=2462000000,conjugate_q=1,configuration='WIFI64_TX,CONFIG,ch=11,count=1,seed=1,run=9',submitted=dict(accepted='1',rejected='0'),counters=dict(done='1',failed='0',rate54='1',other='0'),raw_transport=raw,decoder=decoder,transmitter=dict(mac='78:21:84:d4:4f:98'),saved_raw=dict(path='cyberether/run/raw.ci8',bytes=16384,sha256=sha,host_dsp=False,sample_format='ci8'),observed_radio_lines=lines)
  return dict(kind=pub.KIND,source=pub.SOURCE,completed=True,ota64_confirmed=True,tx_start_requested=True,transport_clean=True,host_dsp=False,ber_measured=False,finished_unix=1,final_cleanup=clean,transport_error_deltas=dict(capture_errors=0,text_drops=0),attempts=[attempt],artifact_provenance={k:'a'*64 for k in ('fpga_sof_sha256','fpga_source_fingerprint','expected_capture_elf_sha256')})
 def test_read_only_and_monitor_audit(self):
  report=pub.validate_proof(self.path)
  self.assertFalse(report['published']);self.assertFalse(pub.LATEST.exists())
  self.assertEqual(report['attempts'][0]['monitor']['qualified_packets'],1)
  self.assertFalse(report['attempts'][0]['monitor']['native_proof_created'])
 def test_explicit_publish_atomic_pointer_shape(self):
  report=pub.publish(self.path);self.assertTrue(report['published'])
  self.assertEqual(json.loads(pub.LATEST.read_text()),{'path':'cyberether/run/proof.json'})
  self.assertFalse(list(self.run.glob('.wifi64-raw-latest.*')))
 def test_wrong_kind_source_unclosed_or_failed_rejected(self):
  for key,value in (('kind','independent native Wi-Fi64 OTA packet observation'),('source','ota-native-wifi64'),('completed',False),('finished_unix',None),('ota64_confirmed',False),('host_dsp',True)):
   original=self.proof[key];self.proof[key]=value;self.write()
   with self.subTest(key=key),self.assertRaises(ValueError):pub.validate_proof(self.path)
   self.proof[key]=original
 def test_cancelled_wrong_capture_and_bad_fcs_rejected(self):
  original=copy.deepcopy(self.proof)
  for change in ('cancelled','frequency','fcs','point','bytes','cleanup'):
   self.proof=copy.deepcopy(original);r=self.proof['attempts'][0]
   if change=='cancelled':r['tx_job_cancelled']=True
   if change=='frequency':r['decoder']['device_result']['frequency']=2447000000
   if change=='fcs':r['decoder']['device_result']['fcs_crc']^=1
   if change=='point':r['decoder']['constellation'][0]['scale']=1
   if change=='bytes':r['decoder']['decoded_bytes'][0]['value']^=1
   if change=='cleanup':r['cleanup']['tx_idle_verified']=False
   self.write()
   with self.subTest(change=change),self.assertRaises(ValueError):pub.validate_proof(self.path)
 def test_modified_raw_archive_rejected(self):
  (self.run/'raw.ci8').write_bytes(b'x'*16384)
  with self.assertRaises(ValueError):pub.publish(self.path)
  self.assertFalse(pub.LATEST.exists())
 def test_external_path_and_symlink_escape_rejected(self):
  outside=self.root/'outside.json';outside.write_text(json.dumps(self.proof))
  with self.assertRaises(ValueError):pub.validate_proof(outside)
  alias=self.run/'alias.json';alias.symlink_to(outside)
  with self.assertRaises(ValueError):pub.validate_proof(alias)
 def test_latest_symlink_cannot_overwrite_another_file(self):
  victim=self.run/'victim';victim.write_text('keep');pub.LATEST.symlink_to(victim)
  with self.assertRaises(ValueError):pub.publish(self.path)
  self.assertEqual(victim.read_text(),'keep')
 def test_duplicate_monitor_packet_not_identity_qualified(self):
  a=self.proof['attempts'][0];a['observed_radio_lines'].append(a['observed_radio_lines'][0]);self.write()
  report=pub.validate_proof(self.path)
  self.assertEqual(report['attempts'][0]['monitor']['qualified_packets'],0)
  self.assertTrue(report['attempts'][0]['monitor']['audit']['duplicates'])
 def test_failure_leaves_old_pointer_untouched(self):
  pub.LATEST.write_text('{"path":"old"}');self.proof['completed']=False;self.write()
  with self.assertRaises(ValueError):pub.publish(self.path)
  self.assertEqual(json.loads(pub.LATEST.read_text()),{'path':'old'})

if __name__=='__main__':unittest.main()
