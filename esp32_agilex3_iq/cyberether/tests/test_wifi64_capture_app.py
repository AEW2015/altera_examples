"""Native MMIO model exercises dedicated Nios capture app; no hardware access."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zlib
from test_wifi64_receiver import waveform
ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_11_wifi64_ota'
@unittest.skipUnless(shutil.which('cc'),'native C compiler required')
class CaptureAppTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
  (p/'test.c').write_text(r'''
#define WIFI64_CAPTURE_HOST_TEST 1
#include "wifi64_capture_app.c"
static uint32_t fir[64],ddc[64],cursor,previous,timer,reads,torn,raw_words;
static uint16_t memory[W64A_MAX_SAMPLES];
static char log_buffer[16384];static unsigned log_used;
uint32_t wifi64_test_read(unsigned block,unsigned index){
 if(block==2)return ++timer;
 if(block==1)return ddc[index];
 if(index==7){uint32_t value=previous;previous=memory[cursor];reads++;if(torn&&reads>=2*raw_words)fir[4]++;return value;}
 return fir[index];
}
void wifi64_test_write(unsigned block,unsigned index,uint32_t value){
 if(block==1){ddc[index]=value;return;}
 if(index==1){if(value==1)fir[1]=1;else if(value==4)fir[1]&=~7u;return;}
 fir[index]=value;if(index==6)cursor=value;
}
void wifi64_test_emit(char c){if(log_used+1<sizeof(log_buffer))log_buffer[log_used++]=c;log_buffer[log_used]=0;}
void setup(const int8_t*data,unsigned n,unsigned crc,unsigned rate,unsigned source,unsigned state,unsigned busy){
 memset(fir,0,sizeof(fir));memset(ddc,0,sizeof(ddc));cursor=previous=timer=reads=torn=0;raw_words=n;
 for(unsigned k=0;k<n&&k<W64A_MAX_SAMPLES;k++)memory[k]=(uint8_t)data[2*k]|((unsigned)(uint8_t)data[2*k+1]<<8);
 fir[0]=0x46495231;fir[1]=state;fir[3]=n;fir[4]=17;fir[5]=source;fir[11]=crc;fir[13]=rate;fir[14]=2447000000u;ddc[0]=0x44444331;ddc[1]=busy;
 result_valid=command_used=overflow=conjugate_q=0;
}
const char*send_command(const char*s){log_used=0;log_buffer[0]=0;while(*s)input((uint8_t)*s++);input('\n');return log_buffer;}
void make_torn(void){torn=1;}
void bad_id(void){fir[0]=0;}
''')
  # The harness sends numeric LF through the actual command-byte parser.
  subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared','-I',str(ROOT/'sw'),'-I',str(STAGE/'sw'),str(p/'test.c'),'-o',str(p/'test.so')],check=True)
  cls.lib=C.CDLL(str(p/'test.so'));cls.lib.setup.argtypes=[C.POINTER(C.c_int8)]+[C.c_uint]*6;cls.lib.send_command.argtypes=[C.c_char_p];cls.lib.send_command.restype=C.c_char_p
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setup(self,raw=None,rate=40000000,source=0,state=2,busy=0,corrupt=False):
  if raw is None:raw=waveform()[0]
  crc=zlib.crc32(bytes(raw));raw=raw.copy()
  if corrupt:raw[10]^=1
  a=(C.c_int8*len(raw))(*raw);self.lib.setup(a,len(raw)//2,crc,rate,source,state,busy)
 def send(self,s):return self.lib.send_command(s.encode()).decode().strip()
 def fields(self,s):return {k:v for k,v in (p.split('=',1) for p in s.split(',')[4:] if '=' in p)}
 def test_version_arm_and_strict_commands(self):
  self.setup();s=self.send('FIR 42 WVERSION');self.assertTrue(s.startswith('FIR,42,OK,WVERSION,'));self.assertEqual(self.fields(s)['timer_base'],'327680');self.assertEqual(self.fields(s)['cancel_supported'],'1');self.assertEqual(self.fields(s)['conjugate_supported'],'1')
  self.assertIn('FIR,43,OK,WARM,state=1,pair=0',self.send('FIR 43 WARM'))
  self.assertIn('ERR,WRUN,error=2',self.send('FIR 44 WRUN'))
  self.assertIn('ERR,WPOINT,error=9',self.send('FIR 45 WPOINT 0'))
  for command in ('FIR 46 WHAT','FIR 46 WPOINT -1','FIR 46 WPOINT 4294967296','FIR 46 WSTATUS extra'):
   self.assertIn('FIR,46,ERR,',self.send(command))
  self.assertIn('ERR,PARSE,error=10',self.send('x'*96))
 def test_full_fresh_capture_copy_and_receiver_results(self):
  self.setup();s=self.send('FIR 50 WRUN');self.assertTrue(s.startswith('FIR,50,OK,WRUN,'),s);f=self.fields(s)
  self.assertEqual((f['accepted'],f['stage'],f['mbps'],f['length'],f['points']),('1','5','54','92','192'))
  self.assertEqual(f['fcs_crc'],f['received_crc']);self.assertEqual(f['source'],'0')
  self.assertEqual(self.fields(self.send('FIR 51 WBYTE 0'))['value'],'8')
  point=self.fields(self.send('FIR 52 WPOINT 191'));self.assertEqual(point['scale'],'8192');int(point['i']);int(point['q'])
  self.assertIn('ERR,WPOINT,error=9',self.send('FIR 53 WPOINT 192'))
  self.assertEqual(self.fields(self.send('FIR 54 WSTATUS'))['valid'],'1')
 def test_crc_mismatch_torn_and_profile_not_ready_guards(self):
  self.setup(corrupt=True);self.assertIn('ERR,WRUN,error=5',self.send('FIR 60 WRUN'))
  self.setup();self.lib.make_torn();self.assertIn('ERR,WRUN,error=4',self.send('FIR 61 WRUN'))
  for kwargs,error in (({'state':1},2),({'busy':1},2),({'rate':16000000},3),({'source':2},3)):
   self.setup(**kwargs);self.assertIn(f'ERR,WRUN,error={error}',self.send('FIR 62 WRUN'))
  self.setup();self.lib.bad_id();self.assertIn('ERR,WARM,error=6',self.send('FIR 63 WARM'))
 def test_fcs_failure_preserves_bytes_and_points_without_acceptance(self):
  self.setup(raw=waveform(crc_bad=True)[0]);f=self.fields(self.send('FIR 70 WRUN'))
  self.assertEqual((f['accepted'],f['status'],f['packet_status'],f['points']),('0','256','4','192'))
  self.assertEqual(self.fields(self.send('FIR 71 WBYTE 0'))['value'],'8')
  self.assertIn('OK,WPOINT',self.send('FIR 72 WPOINT 0'))
 def test_cancel_idle_armed_and_cached_result_with_busy_refusal(self):
  for state in (0,1,2):
   self.setup(state=state);line=self.send('FIR 80 WCANCEL')
   self.assertIn('FIR,80,OK,WCANCEL,state=0,valid=0',line)
   self.assertIn('OK,WARM,state=1',self.send('FIR 81 WARM'))
  self.setup();self.send('FIR 82 WRUN');self.assertEqual(self.fields(self.send('FIR 83 WSTATUS'))['valid'],'1')
  self.send('FIR 84 WCANCEL');self.assertEqual(self.fields(self.send('FIR 85 WSTATUS'))['valid'],'0')
  self.assertIn('ERR,WPOINT,error=9',self.send('FIR 86 WPOINT 0'))
  for state,busy in ((8,0),(128,0),(0,1)):
   self.setup(state=state,busy=busy);self.assertIn('ERR,WCANCEL,error=2',self.send('FIR 87 WCANCEL'))
   self.assertEqual(int(self.fields(self.send('FIR 88 WSTATUS'))['state']),state)
 def test_conjugation_configuration_and_cached_result_guards(self):
  self.setup();line=self.send('FIR 90 WCONJ 1');self.assertIn('OK,WCONJ,conjugate_q=1',line)
  self.assertEqual(self.fields(self.send('FIR 91 WSTATUS'))['conjugate_q'],'1')
  for value in ('2','-1','4294967296'):
   self.assertIn('FIR,92,ERR,WCONJ,error=1',self.send('FIR 92 WCONJ '+value))
  self.setup();self.send('FIR 93 WRUN');self.assertEqual(self.fields(self.send('FIR 94 WSTATUS'))['valid'],'1')
  self.send('FIR 95 WCONJ 0');self.assertEqual(self.fields(self.send('FIR 96 WSTATUS'))['valid'],'0')
  for state,busy in ((1,0),(8,0),(128,0),(0,1)):
   self.setup(state=state,busy=busy);self.assertIn('ERR,WCONJ,error=2',self.send('FIR 97 WCONJ 1'))
  raw=waveform()[0];raw=raw.copy();raw[1::2]=(-raw[1::2].astype('int16')).astype('int8')
  self.setup(raw=raw);self.send('FIR 98 WCONJ 1');fields=self.fields(self.send('FIR 99 WRUN'))
  self.assertEqual((fields['accepted'],fields['conjugate_q']),('1','1'))
if __name__=='__main__':unittest.main()
