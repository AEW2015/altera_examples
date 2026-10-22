"""Mocked programming guards/state transitions. Never accesses hardware."""
import contextlib
import fcntl
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import program_wifi64 as program

class ProgrammingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.stage=self.root/'stage11';(self.stage/'sw').mkdir(parents=True);self.run=self.root/'run';self.run.mkdir();self.app=self.root/'app';self.app.mkdir()
  self.active=self.run/'active-fpga.json';self.marker=self.run/'wifi64-capture-app-active.json'
  self.active.write_text(json.dumps(dict(stage_relative='stage11',sha256='image')));self.marker.write_text('{"app":"old"}')
  (self.stage/'iq_bridge_vds.sof').write_bytes(b'image');(self.stage/'sw/monitor.elf').write_bytes(b'monitor')
  sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
  (self.stage/'sw/BUILD_RESULT.json').write_text(json.dumps(dict(status='PASS',ram_bytes=262144,files={'monitor.elf':sha(self.stage/'sw/monitor.elf')})))
  source=self.root/'app_source.c';source.write_text('source');elf=self.app/'wifi64_capture_app.elf';elf.write_bytes(b'capture')
  (self.app/'BUILD_RESULT.json').write_text(json.dumps(dict(status='PASS_BUILD',stage=11,ram_bytes=262144,elf_sha256=sha(elf),files={'app_source.c':sha(source)})))
  self.patches=contextlib.ExitStack();self.addCleanup(self.patches.close)
  for name,value in (('ROOT',self.root),('STAGE',self.stage),('RUN',self.run),('ACTIVE',self.active),('APP_MARKER',self.marker),('APP_DIR',self.app)):
   self.patches.enter_context(patch.object(program,name,value))
  self.check=self.patches.enter_context(patch.object(program.wifi64_fpga,'check',return_value=dict(sha256='image',checkpoint=11,status='PASS_BUILD')))
  self.local=self.patches.enter_context(patch.object(program,'local_tools',return_value=True))
  self.stop=self.patches.enter_context(patch.object(program,'stop_demo'))
  self.owners=self.patches.enter_context(patch.object(program,'owners',return_value=[]))
  self.environment=self.patches.enter_context(patch.object(program,'software_env',return_value={}))
  self.listing=self.patches.enter_context(patch.object(program.subprocess,'check_output',return_value='1) Atum A3 Nano [1-4.3-iface0]\n  036110DD FPGA\n'))
  self.write=self.patches.enter_context(patch.object(program.subprocess,'run'))
 def invoke(self,action):
  with contextlib.redirect_stdout(io.StringIO()):return program.program(action)
 def test_mandatory_fpga_check_failure_precedes_all_actions(self):
  self.check.side_effect=RuntimeError('stale helper')
  with self.assertRaisesRegex(RuntimeError,'stale helper'):self.invoke('fpga')
  self.local.assert_not_called();self.stop.assert_not_called();self.write.assert_not_called();self.assertTrue(self.active.exists())
 def test_fpga_failure_invalidates_previous_records_before_write(self):
  def fail(command,**kwargs):
   self.assertFalse(self.active.exists());self.assertFalse(self.marker.exists())
   raise subprocess.CalledProcessError(1,command)
  self.write.side_effect=fail
  with self.assertRaises(subprocess.CalledProcessError):self.invoke('fpga')
  self.assertFalse(self.active.exists());self.assertFalse(self.marker.exists())
  records=list(self.run.glob('wifi64-program-*.json'));self.assertEqual(len(records),1);self.assertFalse(json.loads(records[0].read_text())['completed'])
 def test_success_writes_only_target_record_and_resolves_exact_cable(self):
  proof=self.invoke('fpga');self.assertTrue(proof['completed']);self.assertFalse(proof['tx_started'])
  active=json.loads(self.active.read_text());self.assertEqual(active['stage_relative'],'stage11');self.assertFalse(active['hardware_verified']);self.assertFalse(self.marker.exists())
  command=self.write.call_args.args[0];self.assertEqual(command[command.index('-c')+1],'1');self.assertIn('quartus_pgm',command[0])
 def test_capture_download_failure_removes_marker_preserves_fpga_record(self):
  old=self.active.read_text()
  def fail(command,**kwargs):
   self.assertFalse(self.marker.exists());self.assertEqual(command[0],'niosv-download')
   raise subprocess.CalledProcessError(1,command)
  self.write.side_effect=fail
  with self.assertRaises(subprocess.CalledProcessError):self.invoke('capture-app')
  self.assertEqual(self.active.read_text(),old);self.assertFalse(self.marker.exists())
 def test_capture_and_monitor_success_records_are_host_hints(self):
  for action in ('capture-app','monitor'):
   proof=self.invoke(action);self.assertTrue(proof['completed']);marker=json.loads(self.marker.read_text())
   self.assertEqual(marker['app'],action);self.assertFalse(marker['device_hash_verified'])
   command=self.write.call_args.args[0];self.assertEqual(command[:3],['niosv-download','-c','1'])
 def test_stale_app_owner_and_wrong_stage_all_prevent_programming(self):
  (self.root/'app_source.c').write_text('changed')
  with self.assertRaisesRegex(RuntimeError,'hash mismatch'):self.invoke('capture-app')
  self.stop.assert_not_called();self.write.assert_not_called()
  (self.root/'app_source.c').write_text('source');self.owners.return_value=['serial owner PID123']
  with self.assertRaisesRegex(RuntimeError,'Release devices'):self.invoke('capture-app')
  self.write.assert_not_called();self.listing.assert_not_called()
  self.owners.return_value=[];self.active.write_text('{"stage_relative":"other","sha256":"image"}')
  with self.assertRaisesRegex(RuntimeError,'Matching checkpoint11'):self.invoke('capture-app')
 def test_global_leases_prevent_racing_programmer(self):
  for filename in ('rf-link-capture.lock','nios-fir.lock'):
   with (self.run/filename).open('a') as held:
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.assertRaises(BlockingIOError):self.invoke('fpga')
   self.write.assert_not_called()
 def test_local_tools_and_explicit_action_required(self):
  self.local.return_value=False
  with self.assertRaisesRegex(RuntimeError,'locally'):self.invoke('fpga')
  self.write.assert_not_called()
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):program.main([])
if __name__=='__main__':unittest.main()
