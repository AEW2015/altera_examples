"""Explicit RF gating and cleanup under simulated device responses; no hardware."""
import argparse,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import original_iq_control as c

class OriginalControl(unittest.TestCase):
 def test_bounds(self):
  self.assertEqual(c.job_command(None,50),'CONTROL 50')
  self.assertEqual(c.job_command(127,3),'ATTEN 127 3')
  for code,ms in [(119,50),(128,50),(True,50),(120,2),(120,51),(120,True)]:
   with self.assertRaises(ValueError):c.job_command(code,ms)
 def exercise(self,case='ok'):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);run=root/'cyberether/run';run.mkdir(parents=True)
   args=argparse.Namespace(transmit=case!='not_explicit',atten=None,milliseconds=50,capture_delay_ms=0,expect_mac='78:21:84:d4:4f:98',port='/dev/fixture',output=run/'proof.json')
   b=MagicMock();b.__enter__.return_value=b;b.observed_radio_lines=[]
   b.prepare_sdr.return_value='ESP32SDR fixture';b.capture.return_value.metadata.return_value={'source':0,'samples':16380}
   def radio(source,command,*a,**kw):
    if command=='INFO':return 'OIQ,INFO,chip=esp32,iq=unverified,busy=0'
    if command=='GAIN?':return 'GAIN HARDWARE -1 0 81 0'
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
   with patch.object(c,'ROOT',root),patch.object(c,'CaptureMonitorBridge',return_value=b) as opened,patch.object(c,'NiosFir'),patch.object(c,'checked'),patch.object(c,'artifact_guard'),patch.object(c,'arm_bridge',return_value=7),patch.object(c,'save_raw',return_value={'transport_only':True}):
    if case=='ok':
     proof=c.run(args);self.assertTrue(proof['completed']);self.assertFalse(proof['qam_verified']);self.assertFalse(proof['host_dsp']);self.assertTrue(proof['register_trial_qualified'])
    else:
     with self.assertRaises(Exception):c.run(args)
    if case in ('not_explicit','exists'):opened.assert_not_called()
    elif case=='wrong_mac':self.assertFalse(any(call.args[1].startswith('CONTROL') for call in b.radio_write.call_args_list))
    if case not in ('not_explicit','exists'):
     self.assertTrue(any(call.args[1]=='STOP' for call in b.radio_command.call_args_list))
     self.assertIn('mirror_cancel',json.loads(args.output.read_text()))
 def test_complete_control_and_transport_only(self):self.exercise()
 def test_explicit_flag_required(self):self.exercise('not_explicit')
 def test_no_overwrite(self):self.exercise('exists')
 def test_identity_failure_never_starts_rf(self):self.exercise('wrong_mac')
 def test_wrong_terminal_job_still_stops(self):self.exercise('wrong_job')
 def test_capture_timeout_still_stops(self):self.exercise('capture_failure')
