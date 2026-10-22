"""Combined image selection and host switching. No hardware or RF."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import tx_lab_control as c
class TxLab(unittest.TestCase):
 @unittest.skipUnless(shutil.which('cc'),'C compiler required')
 def test_selector_defaults_and_strict_parser(self):
  text='''#include <assert.h>
#include "mode_protocol.h"
int main(void){
 assert(txlab_parse_mode("MODE AMP")==0);
 assert(txlab_parse_mode("MODE NATIVE")==1);
 assert(txlab_parse_mode("MODE PHASE")==2);
 assert(txlab_parse_mode("MODE PHASE ")==-1);
 assert(txlab_parse_mode("MODE QAM")==-1);
 for(unsigned mode=0;mode<3;mode++){
  assert(txlab_selection(1,0x544c4142u,mode,~mode)==(int)mode);
  assert(txlab_selection(0,0x544c4142u,mode,~mode)==0);
  assert(txlab_selection(1,0,mode,~mode)==0);
  assert(txlab_selection(1,0x544c4142u,mode,mode)==0);
 }
 assert(txlab_selection(1,0x544c4142u,3,~3u)==0);
 return 0;
}'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.c').write_text(text)
   subprocess.run(['cc','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/tx_lab/main'),str(p/'test.c'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
 def bridge(self):
  b=MagicMock();b.radio_command.side_effect=['TXLAB,MODE,mode=AMP,quiet=1','TXLAB,MODE,mode=AMP,quiet=1','TXLAB,SWITCH,mode=NATIVE','TXLAB,MODE,mode=NATIVE,quiet=1'];b.wait_text.return_value='WIFI64_TX,READY,rf=0';return b
 def test_switch_never_transmits(self):
  b=self.bridge();self.assertFalse(c.switch(b,'NATIVE')['transmit'])
  commands=[x.args[1] for x in b.radio_command.call_args_list]+[x.args[1] for x in b.radio_write.call_args_list]
  self.assertEqual(commands,['MODE?','MODE?','MODE NATIVE','MODE?','STOP\n'])
 def test_mismatched_readback_rejected(self):
  b=self.bridge();b.radio_command.side_effect=['TXLAB,MODE,mode=AMP,quiet=1','TXLAB,MODE,mode=AMP,quiet=1','TXLAB,SWITCH,mode=NATIVE','TXLAB,MODE,mode=PHASE,quiet=1']
  with self.assertRaisesRegex(RuntimeError,'readback'):c.switch(b,'NATIVE')
 def test_unknown_image_not_touched(self):
  b=self.bridge();b.radio_command.side_effect=['TXLAB,MODE,mode=UNKNOWN,quiet=1']
  with self.assertRaises(RuntimeError):c.switch(b,'NATIVE')
  b.radio_write.assert_not_called()
