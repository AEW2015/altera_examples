"""Transport-only capture-app controller checks; no device or runtime host DSP."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import wifi64_capture as capture

class FakeNios:
 def __init__(self,accepted=True):self.calls=[];self.accepted=accepted
 def command(self,verb,*args,timeout=12):
  self.calls.append((verb,args,timeout));r={'id':1,'verb':verb}
  if verb=='WVERSION':return dict(r,version=1,ram_bytes=262144,timer_base=0x50000,fir_id=0x46495231,host_dsp=0)
  if verb=='WSTATUS':return dict(r,state=2,samples=2000,job=7,source=0,rate=40000000,frequency=2447000000,raw_crc=0x1234,ddc_busy=0,valid=1,status=0 if self.accepted else 256)
  if verb=='WRUN':return dict(r,valid=1,status=0 if self.accepted else 256,stage=5 if self.accepted else 4,accepted=int(self.accepted),rate_code=12,mbps=54,length=4,points=2,symbols=1,packet_status=0 if self.accepted else 4,fcs_crc=0x9876,received_crc=0x9876 if self.accepted else 0x9877,job=7,source=0,rate=40000000,frequency=2447000000,raw_crc=0x1234,ticks_lo=1000,ticks_hi=0,clock_hz=50000000)
  if verb=='WPOINT':return dict(r,index=args[0],i=-1264,q=3792,scale=8192)
  if verb=='WBYTE':return dict(r,index=args[0],value=args[0]+5,packet_status=0 if self.accepted else 4)
  raise AssertionError(verb)
 def commands(self,calls,timeout=12):return [self.command(call[0],*call[1:],timeout=timeout) for call in calls]

class ControlTests(unittest.TestCase):
 def test_default_read_only_has_no_decode_arm_program_or_tx(self):
  owner=FakeNios();proof=capture.run(owner)
  self.assertTrue(proof['completed']);self.assertFalse(proof['decode_requested'])
  self.assertEqual([call[0] for call in owner.calls],['WVERSION','WSTATUS'])
  self.assertFalse(proof['tx_started']);self.assertFalse(proof['capture_armed'])
 def test_decode_collects_actual_points_and_bytes_on_device_success(self):
  owner=FakeNios()
  with contextlib.redirect_stderr(io.StringIO()):proof=capture.run(owner,decode=True,timeout=600)
  self.assertTrue(proof['device_decode_accepted']);self.assertEqual(proof['decoded_psdu_hex'],'05060708')
  self.assertEqual(len(proof['constellation']),2);self.assertEqual(proof['constellation'][0]['i'],-1264)
  self.assertIn(('WRUN',(),600),owner.calls);self.assertFalse(proof['ber_measured'])
 def test_failed_fcs_keeps_measurements_and_is_not_accepted(self):
  with contextlib.redirect_stderr(io.StringIO()):proof=capture.run(FakeNios(False),decode=True)
  self.assertTrue(proof['completed']);self.assertFalse(proof['device_decode_accepted'])
  self.assertEqual(len(proof['constellation']),2);self.assertEqual(len(proof['decoded_bytes']),4)
  self.assertFalse(proof['rf_reception_independently_verified'])
 def test_wrong_echo_and_no_ready_capture_reject_before_decode(self):
  owner=FakeNios();original=owner.command
  def bad_echo(verb,*args,**kwargs):
   r=original(verb,*args,**kwargs);r['verb']='OTHER';return r
  owner.command=bad_echo
  with self.assertRaises(RuntimeError):capture.run(owner,decode=True)
  owner=FakeNios();original=owner.command
  def busy(verb,*args,**kwargs):
   r=original(verb,*args,**kwargs)
   if verb=='WSTATUS':r['ddc_busy']=1
   return r
  owner.command=busy
  with self.assertRaises(RuntimeError):capture.run(owner,decode=True)
  self.assertNotIn('WRUN',[call[0] for call in owner.calls])
 def test_torn_capture_identity_and_wrong_index_are_rejected(self):
  owner=FakeNios();original=owner.command
  def torn(verb,*args,**kwargs):
   r=original(verb,*args,**kwargs)
   if verb=='WRUN':r['job']=8
   return r
  owner.command=torn
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):capture.run(owner,decode=True)
  owner=FakeNios();original=owner.commands
  def wrong(calls,timeout=12):
   rows=original(calls,timeout);rows[0]['index']=99;return rows
  owner.commands=wrong
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):capture.run(owner,decode=True)
 def test_existing_output_never_opens_jtag_or_runs_guard(self):
  with tempfile.TemporaryDirectory() as directory:
   output=Path(directory)/'proof.json';output.write_text('{}')
   with patch.object(capture,'NiosFir') as owner,patch.object(capture,'artifact_guard') as guard,contextlib.redirect_stderr(io.StringIO()):
    self.assertEqual(capture.main(['--decode','--output',str(output)]),2);owner.assert_not_called();guard.assert_not_called()
 def test_stale_stage_guard_saves_failure_without_opening_device(self):
  with tempfile.TemporaryDirectory() as directory:
   output=Path(directory)/'proof.json'
   with patch.object(capture,'NiosFir') as owner,patch.object(capture,'artifact_guard',side_effect=RuntimeError('stale source')),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(capture.main(['--decode','--output',str(output)]),2);owner.assert_not_called()
   self.assertIn('stale source',json.loads(output.read_text())['error'])
if __name__=='__main__':unittest.main()

class ArtifactGuardTests(unittest.TestCase):
 def test_source_image_and_app_hash_guards(self):
  import hashlib
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);stage=root/'stage11';stage.mkdir();app=root/'app';app.mkdir();active=root/'active.json'
   source=root/'sw/wifi64_capture_app.c';source.parent.mkdir();source.write_text('original')
   sof=stage/'iq_bridge_vds.sof';sof.write_bytes(b'fpga-image');elf=app/'wifi64_capture_app.elf';elf.write_bytes(b'cpu-app')
   sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
   (stage/'BUILD_RESULT.json').write_text(json.dumps(dict(status='PASS_BUILD',sha256=sha(sof),source_fingerprint='fingerprint')))
   active.write_text(json.dumps(dict(stage_relative='stage11',sha256=sha(sof))))
   (app/'BUILD_RESULT.json').write_text(json.dumps(dict(status='PASS_BUILD',stage=11,ram_bytes=262144,elf_sha256=sha(elf),files={'sw/wifi64_capture_app.c':sha(source)})))
   with patch.object(capture,'ROOT',root),patch.object(capture,'STAGE',stage),patch.object(capture,'ACTIVE',active),patch.object(capture,'APP_DIR',app),patch.object(capture,'fingerprint',return_value='fingerprint'):
    hint=capture.artifact_guard();self.assertFalse(hint['device_elf_hash_verified'])
    source.write_text('modified')
    with self.assertRaisesRegex(RuntimeError,'source fingerprint'):capture.artifact_guard()
    source.write_text('original');sof.write_bytes(b'wrong-image')
    with self.assertRaisesRegex(RuntimeError,'hash mismatch'):capture.artifact_guard()
