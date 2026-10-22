"""No hardware: interleaved radio text retention and independent RX proof gates."""
import argparse
import collections
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import wifi64_ota as ota
from wifi64_records import LineAssembler

def rows(rate=12,channel=8):
    return ['WIFI64_MON,PACKET,run=7,packet=0,seed=9,body_ok=1',
            f'WIFI64_MON,PHY,run=7,packet=0,rate_code={rate},sig_mode=0,rx_state=0,rssi=-35,ch={channel}',
            'WIFI64_MON,META,run=7,packet=0,timestamp_us=12,length=92,native_rx=1']

class RetentionTests(unittest.TestCase):
    def bridge(self):
        b=object.__new__(ota.MonitorBridge);b.responses=collections.deque()
        b.text_queues={n:collections.deque() for n in range(3)}
        b.assemblers={n:LineAssembler() for n in range(3)};b.monitor_lines=[]
        return b
    def test_all_monitor_rows_retained_during_tx_reply_wait(self):
        b=self.bridge()
        frames=[SimpleNamespace(kind=3,source=2,payload=line.encode()) for line in rows()]
        frames.insert(1,SimpleNamespace(kind=3,source=1,payload=b'WIFI64_TX,INFO,version=1'))
        frames.append(SimpleNamespace(kind=3,source=1,payload=b'WIFI64_TX,DONE,job=1'))
        with patch.object(ota.Bridge,'read_frame',side_effect=frames):
            self.assertIn('INFO',b.wait_text(1,'WIFI64_TX,INFO,'))
            self.assertIn('DONE',b.wait_text(1,'WIFI64_TX,DONE,'))
        self.assertEqual(b.monitor_lines,rows())
    def test_control_queued_frame_is_not_ingested_twice(self):
        b=self.bridge();f=SimpleNamespace(kind=3,source=2,payload=rows()[0].encode())
        b._ingest(f);b.responses.append(f)
        self.assertEqual(b.wait_text(2,'WIFI64_MON,PACKET,'),rows()[0])
        self.assertEqual(b.monitor_lines,[rows()[0]])

class FakeJobBridge:
    def __init__(self,rate=12,channel=8):self.monitor_lines=[];self.commands=[];self.rate=rate;self.channel=channel
    def control(self,*args):self.commands.append(('control',args))
    def radio_command(self,source,command,prefix=None,timeout=4):
        self.commands.append((source,command))
        if source==1:
            if command=='STOP':return 'WIFI64_TX,STOP,busy=0,rf=0,stop_err=0'
            if command=='STATUS':return 'WIFI64_TX,STATUS,busy=0,rf=0,stop_err=0'
        if command=='INFO':return 'WIFI64_MON,INFO,v=1'
        if command=='STOP':return 'WIFI64_MON,STOP,listening=0,error=0'
        if command=='STATUS':return 'WIFI64_MON,STATUS,listening=0,ch=8,matched=0,drops=0'
        if command=='LISTEN 8 10000':return 'WIFI64_MON,LISTEN,ok=1,ch=8,ms=10000,error=0'
        raise AssertionError((source,command))
    def collect(self,seconds):self.monitor_lines.extend(rows(self.rate,self.channel))
    def status(self):return dict(host_command_errors=0,radio_framing_errors=0,capture_errors=0,text_drops=0)

class JobTests(unittest.TestCase):
    def args(self):return argparse.Namespace(channel=8,power=8,count=1,gap=2,run=7,seed=9)
    def test_listen_precedes_tx_and_complete_proof_serializes(self):
        b=FakeJobBridge()
        def tx(bridge,args):
            self.assertIn((2,'LISTEN 8 10000'),bridge.commands)
            return {'completed':True,'tx_success':True}
        with patch.object(ota,'transmit',side_effect=tx):proof=ota.run_job(b,self.args())
        self.assertTrue(proof['completed']);self.assertTrue(proof['native_rate54_observed_over_air'])
        self.assertTrue(proof['final_tx_idle_verified']);json.dumps(proof)
    def test_wrong_rate_or_channel_does_not_qualify(self):
        for rate,ch in ((11,8),(12,7)):
            with self.subTest(rate=rate,ch=ch),patch.object(ota,'transmit',return_value={'completed':True,'tx_success':True}):
                proof=ota.run_job(FakeJobBridge(rate,ch),self.args())
                self.assertFalse(proof['completed']);self.assertFalse(proof['native_rate54_observed_over_air'])
    def test_existing_output_never_opens_device(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'proof.json';output.write_text('{}')
            with patch.object(ota,'MonitorBridge') as bridge,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ota.main(['--transmit','--output',str(output)]),2)
                bridge.assert_not_called()

if __name__=='__main__':unittest.main()

class TxCounterGates(unittest.TestCase):
    def test_rejected_packet_job_completes_but_is_not_tx_success(self):
        from test_wifi64_control import FakeBridge
        from wifi64_control import transmit
        bridge=FakeBridge();original=bridge.wait_text
        def wait(source,prefix,timeout=4):
            if prefix=='WIFI64_TX,SUBMITTED,':return 'WIFI64_TX,SUBMITTED,accepted=1,rejected=1'
            if prefix=='WIFI64_TX,COUNTERS,':return 'WIFI64_TX,COUNTERS,done=1,failed=0,rate54=1,other=0'
            return original(source,prefix,timeout)
        bridge.wait_text=wait
        proof=transmit(bridge,argparse.Namespace(channel=8,power=8,count=2,gap=2,run=7,seed=9))
        self.assertTrue(proof['completed']);self.assertTrue(proof['job_completed'])
        self.assertFalse(proof['tx_success'])
        self.assertEqual(proof['tx_counters']['rejected'],1)
