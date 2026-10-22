"""Offline transport/orchestration tests. No devices, RF or host DSP."""
import collections,ctypes,json,struct,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import wifi64_capture_ota as ota
from iq_bridge import Frame


def arguments():
    return SimpleNamespace(attempts=1,count=16,power=8,samples=8192,run=99,seed=7,
                           decode_timeout=600,monitor=False,hardware_gain=False,lpf64=False)

class Wifi64CaptureOtaTests(unittest.TestCase):
    def test_trigger_is_atomic_start_then_valid_padded_cap(self):
        for samples in (8192,16380):
            for pad in (0,7,14):
                wire=ota.trigger_wire(samples,pad);chars={0:bytearray(),1:bytearray()}
                self.assertEqual(len(wire)%20,0)
                for start in range(0,len(wire),20):
                    magic,op,source,byte,job,value=struct.unpack('<4sBBHII',wire[start:start+16])
                    self.assertEqual((magic,op,job,value),(b'IQBC',1,0,0))
                    chars[source].append(byte)
                self.assertEqual(chars[1],b'START\n')
                self.assertEqual(chars[0],f'CAP16 {samples} 1'.encode()+b' '*pad+b'\n')
                self.assertEqual(wire[:120],ota.trigger_wire(samples,0)[:120])
        for samples,pad in ((4096,0),(8192,15),(8192,-1)):
            with self.assertRaises(ValueError):ota.trigger_wire(samples,pad)
    def test_trailing_spaces_preserve_receiver_sscanf_contract(self):
        parser=(ROOT/'unified/main/common/burst_commands.h').read_text()
        self.assertIn('CAP20 %u %u %c',parser)
        sscanf=ctypes.CDLL(None).sscanf
        for pad in (0,7,14):
            n=ctypes.c_uint();rate=ctypes.c_uint();extra=ctypes.c_char()
            line=b'CAP20 8192 1'+b' '*pad
            count=sscanf(line,b'CAP20 %u %u %c',ctypes.byref(n),ctypes.byref(rate),ctypes.byref(extra))
            self.assertEqual((count,n.value,rate.value),(2,8192,1))

    def test_attempt_bounds_and_unique_run_limit(self):
        args=arguments();ota.validate_args(args)
        for key,value in (('attempts',0),('attempts',4),('count',17),('samples',4096),('decode_timeout',0),('power',41),('run',0xffffffff+1)):
            a=arguments();setattr(a,key,value)
            with self.assertRaises(ValueError):ota.validate_args(a)
        a=arguments();a.attempts=3;a.run=0xffffffff
        with self.assertRaises(ValueError):ota.validate_args(a)
    def test_iq_is_retained_while_waiting_for_text(self):
        bridge=ota.CaptureMonitorBridge.__new__(ota.CaptureMonitorBridge)
        raw=Frame(1,0,4,8192,ota.RATE,ota.FREQ,123,205,0,16384,1,2,0,b'x'*16384)
        bridge.responses=collections.deque([raw]);bridge.capture_frames=collections.deque();bridge._ingest=Mock()
        self.assertIs(bridge._next(1),raw)
        self.assertIs(bridge.capture(4,8192),raw)
    def test_bounded_trace_keeps_source1_lines_and_frame_kinds_once(self):
        bridge=ota.CaptureMonitorBridge.__new__(ota.CaptureMonitorBridge)
        bridge.observed_frames=collections.deque(maxlen=256)
        bridge.observed_tx_lines=collections.deque(maxlen=256)
        bridge.observed_radio_lines=collections.deque(maxlen=256)
        bridge.text_queues={n:collections.deque() for n in range(3)}
        from wifi64_records import LineAssembler
        bridge.assemblers={n:LineAssembler() for n in range(3)};bridge.monitor_lines=[]
        for index in range(260):
            frame=Frame(3,1,index,0,0,0,0,0,0,0,0,0,0,f'WIFI64_TX,TRACE,index={index}'.encode())
            bridge._ingest(frame);bridge._ingest(frame)
        self.assertEqual(len(bridge.observed_frames),256)
        self.assertEqual(len(bridge.observed_tx_lines),256)
        self.assertEqual(bridge.observed_frames[0]['job'],4)
        self.assertEqual(bridge.observed_tx_lines[-1]['line'],'WIFI64_TX,TRACE,index=259')
        self.assertEqual(len(bridge.text_queues[1]),260)
        receiver=Frame(3,0,300,0,0,0,0,0,0,0,0,0,0,b'ERR ADC timeout')
        bridge._ingest(receiver)
        self.assertEqual(bridge.observed_radio_lines[-1]['source'],0)
        self.assertEqual(bridge.observed_radio_lines[-1]['line'],'ERR ADC timeout')
        self.assertEqual(len(bridge.observed_tx_lines),256)

    def test_packet_identity_is_separate_from_fec_acceptance(self):
        p=bytearray(92);p[10:16]=bytes.fromhex('782184d44f98');p[24:32]=b'W64A\x01\x36\x40\x00'
        p[32:36]=(99).to_bytes(4,'little');p[36:40]=(3).to_bytes(4,'little');p[40:44]=(7).to_bytes(4,'little')
        self.assertTrue(ota.packet_identity({'decoded_psdu_hex':p.hex()},'78:21:84:d4:4f:98',99,16,7))
        self.assertFalse(ota.packet_identity({'decoded_psdu_hex':p.hex()},'78:21:84:d4:4f:98',100,16,7))
        self.assertFalse(ota.packet_identity({'decoded_psdu_hex':p.hex()},'00:00:00:00:00:00',99,16,7))
    def make_attempt(self,cancel_supported=1,decode_accepted=True):
        events=[];args=arguments();owner=object();bridge=Mock();bridge.observed_tx_lines=[];bridge.observed_radio_lines=[];bridge.observed_frames=[];bridge.capture_frames=[];bridge.text_queues={1:collections.deque(['stale'])}
        bridge.next_job.return_value=66
        bridge._next.return_value=SimpleNamespace(kind=2,job=66,source=0)
        bridge.send.side_effect=lambda *a,**k:events.append('bridge_arm')
        bridge.port.write.side_effect=lambda wire:events.append('atomic_wire')
        def wait(source,prefix,timeout=4):
            if 'IDENT' in prefix:return 'WIFI64_TX,IDENT,mac=78:21:84:d4:4f:98'
            if 'STATUS' in prefix:return 'WIFI64_TX,STATUS,busy=0,rf=0,stop_err=0,armed=0'
            if 'SUBMITTED' in prefix:return 'WIFI64_TX,SUBMITTED,accepted=16,rejected=0'
            if 'COUNTERS' in prefix:return 'WIFI64_TX,COUNTERS,done=16,failed=0,rate54=16,other=0'
            if 'START' in prefix:return 'WIFI64_TX,START,job=7'
            if 'DONE' in prefix or prefix=='WIFI64_TX,':return 'WIFI64_TX,DONE,job=7'
            raise AssertionError(prefix)
        bridge.wait_text.side_effect=wait
        raw=SimpleNamespace(raw_crc=123,metadata=lambda:{'raw_crc':123})
        bridge.capture.return_value=raw
        def query(b,command,verb):
            if command=='INFO':return 'WIFI64_TX,INFO,version=1'
            if command=='CONFIG?':return 'WIFI64_TX,CONFIG,ch=8,power_qdbm=8,count=16,gap_ms=2,run=99,seed=7'
            if command.startswith('CONFIG '):return 'WIFI64_TX,CONFIG,ok=1'
            if command=='ARM':events.append('tx_arm');return 'WIFI64_TX,ARM,ok=1,ch=8'
            raise AssertionError(command)
        def checked(o,verb,*a,**k):
            events.append(verb)
            if verb=='WVERSION':return dict(version=1,ram_bytes=262144,timer_base=0x50000,cancel_supported=cancel_supported,host_dsp=0)
            if verb=='WARM':return dict(state=1,pair=0)
            if verb=='WSTATUS':return dict(state=2,ddc_busy=0,samples=8192,job=66,source=0,rate=ota.RATE,frequency=ota.FREQ,raw_crc=123)
            raise AssertionError(verb)
        def cleanup(b,o,cancel_mirror=True):
            events.append('cancel' if cancel_mirror else 'stop_radios')
            return {'tx_idle_verified':True,'mirror_cancel_verified':cancel_mirror,'monitor_stop_verified':True}
        def decode(*a,**k):events.append('decode');return {'device_decode_accepted':decode_accepted,'decoded_psdu_hex':''}
        return events,args,owner,bridge,query,checked,cleanup,decode
    def test_prearm_order_and_cleanup_preserve_ready_until_decode(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt()
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d):
            proof=ota.attempt(bridge,owner,args,99,7)
        self.assertTrue(proof['completed'])
        self.assertEqual(events,['WVERSION','WARM','tx_arm','bridge_arm','atomic_wire','WSTATUS','stop_radios','decode','cancel'])
        self.assertTrue(proof['raw_transferred_for_transport_only'])
        self.assertFalse(proof['ota64_confirmed']) # No known decoded A body supplied.
        self.assertEqual(list(bridge.text_queues[1]),[])
    def test_old_uncancellable_app_never_arms_or_starts(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt(cancel_supported=0)
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d):
            proof=ota.attempt(bridge,owner,args,99,0)
        self.assertFalse(proof['tx_start_requested']);bridge.port.write.assert_not_called()
        self.assertNotIn('WARM',events);self.assertFalse(proof['completed'])
    def test_missing_start_ack_still_runs_all_cleanup(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt()
        original=bridge.wait_text.side_effect
        bridge.wait_text.side_effect=lambda source,prefix,timeout=4: (_ for _ in ()).throw(TimeoutError('ack')) if 'START' in prefix else original(source,prefix,timeout)
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d):
            proof=ota.attempt(bridge,owner,args,99,0)
        self.assertTrue(proof['tx_start_requested']);self.assertIn('cancel',events)
        self.assertNotIn('decode',events);self.assertFalse(proof['completed'])
    def test_start_retained_when_done_missing_and_raw_preserved(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt()
        original=bridge.wait_text.side_effect
        bridge.wait_text.side_effect=lambda source,prefix,timeout=4: (_ for _ in ()).throw(TimeoutError('missing DONE')) if prefix=='WIFI64_TX,' else original(source,prefix,timeout)
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d):
            proof=ota.attempt(bridge,owner,args,99,0)
        self.assertEqual(proof['tx_start'],'WIFI64_TX,START,job=7')
        self.assertNotIn('tx_done',proof)
        self.assertEqual(proof['raw_transport']['raw_crc'],123)
        self.assertEqual(proof['failure_mirror_status']['job'],66)
        self.assertTrue(proof['raw_transferred_for_transport_only'])
        self.assertFalse(proof['ota64_confirmed']);self.assertFalse(proof['completed'])
        self.assertNotIn('decode',events)
        self.assertLess(events.index('stop_radios'),events.index('WSTATUS'))

    def test_cancelled_terminal_still_decodes_raw_without_tx_success(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt()
        original=bridge.wait_text.side_effect
        bridge.wait_text.side_effect=lambda source,prefix,timeout=4: 'WIFI64_TX,CANCELLED,job=7,busy=0,armed=0,rf=0,stop_err=0' if prefix=='WIFI64_TX,' else original(source,prefix,timeout)
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d),patch.object(ota,'packet_identity',return_value=True):
            proof=ota.attempt(bridge,owner,args,99,0)
        self.assertTrue(proof['completed']);self.assertTrue(proof['tx_job_cancelled'])
        self.assertFalse(proof['tx_success']);self.assertFalse(proof['ota64_confirmed'])
        self.assertTrue(proof['raw_known_a_decode_confirmed'])
        self.assertIn('decode',events);self.assertNotIn('tx_done',proof)
        self.assertLess(events.index('stop_radios'),events.index('decode'))

    def test_terminal_wait_preserves_interleaved_counters(self):
        bridge=Mock();bridge.text_queues={1:collections.deque()}
        bridge.wait_text.side_effect=['WIFI64_TX,SUBMITTED,accepted=4','WIFI64_TX,COUNTERS,done=4','WIFI64_TX,CANCELLED,job=4']
        self.assertEqual(ota.wait_terminal(bridge),'WIFI64_TX,CANCELLED,job=4')
        self.assertEqual(list(bridge.text_queues[1]),['WIFI64_TX,SUBMITTED,accepted=4','WIFI64_TX,COUNTERS,done=4'])

    def test_cleanup_attempts_independent_stops_after_one_failure(self):
        bridge=Mock();owner=object()
        def tx(b,command,verb):
            if command=='STOP':raise TimeoutError('tx stop ack')
            return {'line':'WIFI64_TX,STATUS,busy=0,rf=0,stop_err=0,armed=0'}
        with patch.object(ota,'tx_block',side_effect=tx),patch.object(ota,'monitor_command',return_value='WIFI64_MON,STOP,listening=0,error=0') as monitor,patch.object(ota.reader,'checked',return_value={'state':0,'valid':0}) as cancel:
            result=ota.cleanup(bridge,owner)
        self.assertIn('tx_stop_error',result);self.assertTrue(result['tx_idle_verified'])
        self.assertTrue(result['mirror_cancel_verified']);self.assertTrue(result['monitor_stop_verified'])
        monitor.assert_called_once();cancel.assert_called_once();bridge.control.assert_called_once_with(6,0)

    def test_explicit_phase_requires_single_attempt_and_bounded_pad(self):
        for pad in (0,7,14):
            args=arguments();args.phase_pad=pad;ota.validate_args(args)
        for pad,count in ((-1,1),(15,1),(7,2),(0,3)):
            args=arguments();args.phase_pad=pad;args.attempts=count
            with self.assertRaises(ValueError):ota.validate_args(args)

    def test_raw_archive_exact_bytes_private_exclusive_and_no_iq_processing(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(ota,'ROOT',Path(temporary)):
            folder=Path(temporary)/'cyberether/run';folder.mkdir(parents=True)
            directory=ota.reserve_raw_directory(folder/'proof.json')
            self.assertEqual(directory.stat().st_mode&0o777,0o700)
            payload=b'\x80\x7f\x00\xff'
            frame=SimpleNamespace(payload=payload,samples=2,job=4,iq=Mock(side_effect=AssertionError('host DSP forbidden')))
            archive=ota.save_raw(frame,directory,123)
            target=Path(temporary)/archive['path']
            self.assertEqual(target.read_bytes(),payload)
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertEqual(archive['sha256'],ota.hashlib.sha256(payload).hexdigest())
            self.assertFalse(archive['host_dsp']);self.assertFalse(archive['rf_content_verified'])
            frame.iq.assert_not_called()
            with self.assertRaises(FileExistsError):ota.save_raw(frame,directory,123)
            with self.assertRaises(FileExistsError):ota.reserve_raw_directory(folder/'proof.json')
            with self.assertRaises(ValueError):ota.reserve_raw_directory(Path(temporary)/'outside.json')

    def test_raw_archive_is_saved_before_nios_decode(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt();args.raw_dir=Path('/unused')
        def archive(*a):events.append('save_raw');return {'host_dsp':False}
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d),patch.object(ota,'save_raw',side_effect=archive):
            proof=ota.attempt(bridge,owner,args,99,7)
        self.assertTrue(proof['completed']);self.assertLess(events.index('save_raw'),events.index('decode'))

    def test_existing_private_directory_refused_before_device_access(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(ota,'ROOT',Path(temporary)):
            folder=Path(temporary)/'cyberether/run';folder.mkdir(parents=True)
            output=folder/'proof.json';(folder/'proof.private').mkdir()
            with patch.object(ota.reader,'artifact_guard') as guard,patch.object(ota,'NiosFir') as owner,patch.object(ota,'CaptureMonitorBridge') as bridge:
                self.assertEqual(ota.main(['--transmit','--save-raw','--output',str(output)]),2)
            guard.assert_not_called();owner.assert_not_called();bridge.assert_not_called()

    def test_channel_bounds_and_non8_capture_frequency(self):
        self.assertEqual(ota.channel_frequency(1),2412000000)
        self.assertEqual(ota.channel_frequency(11),2462000000)
        for channel in (0,12):
            args=arguments();args.channel=channel
            with self.assertRaises(ValueError):ota.validate_args(args)
        args=arguments();args.conjugate_q=2
        with self.assertRaises(ValueError):ota.validate_args(args)
        bridge=ota.CaptureMonitorBridge.__new__(ota.CaptureMonitorBridge)
        raw=Frame(1,0,4,8192,ota.RATE,2462000000,123,205,0,16384,1,2,0,b'x'*16384)
        bridge.capture_frames=collections.deque([raw])
        self.assertIs(bridge.capture(4,8192,expected_frequency=2462000000),raw)
        bridge.capture_frames.append(raw)
        with self.assertRaises(RuntimeError):bridge.capture(4,8192)

    def test_channel11_controls_and_frozen_frequency_association(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt();args.channel=11
        def query(*a):return q(*a).replace('ch=8','ch=11')
        def checked(*a,**k):
            value=c(*a,**k)
            if a[1]=='WSTATUS':value['frequency']=2462000000
            return value
        with patch.object(ota,'query',side_effect=query),patch.object(ota.reader,'checked',side_effect=checked),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=d):
            proof=ota.attempt(bridge,owner,args,99,14)
        self.assertTrue(proof['completed']);self.assertEqual(proof['requested_frequency'],2462000000)
        bridge.capture.assert_called_once_with(66,8192,expected_frequency=2462000000)

    def test_wrong_channel_readback_never_arms(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt();args.channel=11
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl):
            proof=ota.attempt(bridge,owner,args,99,14)
        self.assertFalse(proof['tx_start_requested']);self.assertNotIn('WARM',events)
        self.assertIn('configuration mismatch',proof['error'])

    def test_conjugation_capability_missing_never_arms(self):
        events,args,owner,bridge,q,c,cl,d=self.make_attempt();args.conjugate_q=1
        with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=c),patch.object(ota,'cleanup',side_effect=cl):
            proof=ota.attempt(bridge,owner,args,99,14)
        self.assertFalse(proof['tx_start_requested']);self.assertNotIn('WARM',events)
        self.assertIn('conjugation capability',proof['error'])

    def test_on_device_conjugation_set_verify_decode_cancel_restore(self):
        for mismatch in (False,True):
            events,args,owner,bridge,q,c,cl,d=self.make_attempt();args.conjugate_q=1
            current=[0];armed=[False]
            def checked(o,verb,*values,**kwargs):
                if verb=='WCONJ':
                    events.append('WCONJ'+str(values[0]));current[0]=values[0]
                    return {'conjugate_q':0 if mismatch and values[0]==1 else current[0]}
                if verb=='WCANCEL':events.append('WCANCEL');return {'state':0,'valid':0}
                if verb=='WSTATUS' and not armed[0]:return {'conjugate_q':current[0]}
                if verb=='WARM':armed[0]=True
                value=c(o,verb,*values,**kwargs)
                if verb=='WVERSION':value['conjugate_supported']=1
                if verb=='WSTATUS':value['conjugate_q']=current[0]
                return value
            def decode(*a,**k):
                result=d(*a,**k);result['device_result']={'conjugate_q':1};return result
            with patch.object(ota,'query',side_effect=q),patch.object(ota.reader,'checked',side_effect=checked),patch.object(ota,'cleanup',side_effect=cl),patch.object(ota.reader,'run',side_effect=decode):
                proof=ota.attempt(bridge,owner,args,99,14)
            self.assertEqual(proof['conjugation_restored']['conjugate_q'],0)
            self.assertLess(events.index('WCANCEL'),events.index('WCONJ1'))
            self.assertLess(events.index('cancel'),events.index('WCONJ0'))
            if mismatch:
                self.assertFalse(proof['tx_start_requested']);self.assertNotIn('WARM',events)
                self.assertFalse(proof['completed'])
            else:
                self.assertTrue(proof['completed']);self.assertIn('decode',events)
                self.assertLess(events.index('WCONJ1'),events.index('WARM'))

    def test_existing_output_rejected_before_artifact_or_device_access(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'proof.json';output.write_text('preserve')
            with patch.object(ota.reader,'artifact_guard') as guard,patch.object(ota,'NiosFir') as owner,patch.object(ota,'CaptureMonitorBridge') as bridge:
                self.assertEqual(ota.main(['--transmit','--output',str(output)]),2)
            guard.assert_not_called();owner.assert_not_called();bridge.assert_not_called()
            self.assertEqual(output.read_text(),'preserve')

if __name__=='__main__':unittest.main()
