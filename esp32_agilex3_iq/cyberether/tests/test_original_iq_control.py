"""Explicit RF gating and cleanup under simulated device responses; no hardware."""
import argparse,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import original_iq_control as c

class OriginalControl(unittest.TestCase):
 def test_bounds(self):
  self.assertEqual(c.job_command(None,50),'CONTROL 50')
  self.assertEqual(c.job_command(127,3),'ATTEN 127 3')
  self.assertEqual(c.job_command(None,50,level=0),'LEVEL 0 50')
  self.assertEqual(c.job_command(None,50,level=24,period=64),'TRAIN 24 50 64')
  for code,ms in [(119,50),(128,50),(True,50),(120,2),(120,51),(120,True)]:
   with self.assertRaises(ValueError):c.job_command(code,ms)
  for kw in [dict(level=128),dict(level=True),dict(level=0,period=31),dict(level=0,period=129),dict(period=64)]:
   with self.assertRaises(ValueError):c.job_command(None,50,**kw)
 def exercise(self,case='ok'):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);run=root/'cyberether/run';run.mkdir(parents=True)
   args=argparse.Namespace(transmit=case!='not_explicit',atten=None,milliseconds=50,capture_delay_ms=0,expect_mac='78:21:84:d4:4f:98',port='/dev/fixture',output=run/'proof.json')
   args.rx_gain=0 if case in ('manual','wrong_gain') else None
   args.level=24 if case in ('train','wrong_version','faulty_v2') else None
   args.train_period_us=64 if args.level is not None else None
   b=MagicMock();b.__enter__.return_value=b;b.observed_radio_lines=[]
   b.prepare_sdr.return_value='ESP32SDR fixture';b.capture.return_value.metadata.return_value={'source':0,'samples':16380}
   gain=['GAIN HARDWARE -1 0 81 0']
   def radio(source,command,*a,**kw):
    if command=='INFO':return 'OIQ,INFO,v='+('3,amp_train=1' if case=='train' else '2,amp_train=1' if case=='faulty_v2' else '1')+',chip=esp32,iq=unverified,busy=0'
    if command=='GAIN?':return gain[0]
    if command=='GAIN MANUAL 0' and case!='wrong_gain':gain[0]='GAIN MANUAL 0 0 81 1'
    if command=='GAIN HARDWARE':gain[0]='GAIN HARDWARE -1 0 81 0'
    if command=='STOP':return 'OIQ,STOP,requested=1'
    return 'OK'
   b.radio_command.side_effect=radio
   def wait(source,prefix,*a):
    if prefix=='OIQ,IDENT,':return 'OIQ,IDENT,mac='+('00:00:00:00:00:00' if case=='wrong_mac' else args.expect_mac)
    if prefix=='OIQ,START,':return 'OIQ,START,job=1'
    if prefix=='OIQ,DONE,':return 'OIQ,DONE,job='+('2' if case=='wrong_job' else '1')+',gain_restored=1,fields_ok=1,rf_off=1'
    raise AssertionError(prefix)
   b.wait_text.side_effect=wait
   if case=='capture_failure':b.capture.side_effect=TimeoutError('capture missed')
   if case=='exists':args.output.write_text('keep')
   with patch.object(c,'ROOT',root),patch.object(c,'OriginalIqBridge',return_value=b) as opened,patch.object(c,'NiosFir'),patch.object(c,'checked'),patch.object(c,'artifact_guard'),patch.object(c,'arm_bridge',return_value=7),patch.object(c,'save_raw',return_value={'transport_only':True}):
    if case in ('ok','manual','train'):
     proof=c.run(args);self.assertTrue(proof['completed']);self.assertFalse(proof['qam_verified']);self.assertFalse(proof['host_dsp']);self.assertTrue(proof['register_trial_qualified'])
    else:
     with self.assertRaises(Exception):c.run(args)
    if case in ('not_explicit','exists'):opened.assert_not_called()
    elif case in ('wrong_mac','wrong_gain','wrong_version','faulty_v2'):self.assertFalse(any(call.args[1].startswith(('CONTROL','TRAIN','LEVEL')) for call in b.radio_write.call_args_list))
    if case not in ('not_explicit','exists'):
     self.assertTrue(any(call.args[1]=='STOP' for call in b.radio_command.call_args_list))
     self.assertIn('mirror_cancel',json.loads(args.output.read_text()))
 def test_complete_control_and_transport_only(self):self.exercise()
 def test_explicit_flag_required(self):self.exercise('not_explicit')
 def test_no_overwrite(self):self.exercise('exists')
 def test_identity_failure_never_starts_rf(self):self.exercise('wrong_mac')
 def test_wrong_terminal_job_still_stops(self):self.exercise('wrong_job')
 def test_capture_timeout_still_stops(self):self.exercise('capture_failure')
 def test_manual_gain_applied_and_restored(self):self.exercise('manual')
 def test_gain_readback_failure_never_starts_rf(self):self.exercise('wrong_gain')
 def test_training_v2_capability(self):self.exercise('train')
 def test_training_refuses_v1_before_rf(self):self.exercise('wrong_version')
 def test_known_faulty_v2_refused_before_rf(self):self.exercise('faulty_v2')
 def test_panic_detection_disarms_watcher_for_cleanup(self):
  bridge=c.OriginalIqBridge.__new__(c.OriginalIqBridge);bridge.watch_faults=True
  frame=SimpleNamespace(kind=3,source=1,payload=b'***ERROR*** A stack overflow in task oiq_probe has been detected.')
  with patch.object(c.CaptureMonitorBridge,'_ingest'):
   with self.assertRaisesRegex(RuntimeError,'fault/reboot'):bridge._ingest(frame)
   self.assertFalse(bridge.watch_faults);bridge._ingest(frame)
 def test_reboot_during_job_rejected_but_other_radio_ignored(self):
  bridge=c.OriginalIqBridge.__new__(c.OriginalIqBridge);bridge.watch_faults=True
  with patch.object(c.CaptureMonitorBridge,'_ingest'):
   bridge._ingest(SimpleNamespace(kind=3,source=0,payload=b'OIQ,READY,'))
   with self.assertRaisesRegex(RuntimeError,'fault/reboot'):bridge._ingest(SimpleNamespace(kind=3,source=1,payload=b'OIQ,READY,rf_initialized=0'))
