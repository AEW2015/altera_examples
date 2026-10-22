"""Native C parser and exact bitfield tests; no firmware/device access."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
@unittest.skipUnless(shutil.which('cc'),'C compiler required')
class OriginalIqProbeTests(unittest.TestCase):
 def test_parser_limits_and_only_attenuation_changes(self):
  source=r'''
#include <assert.h>
#include "protocol.h"
int main(void){
 const char*good[]={"CONTROL 3","CONTROL 50","ATTEN 120 3","ATTEN 127 50","LEVEL 0 3","LEVEL 127 50","TRAIN 0 3 32","TRAIN 127 50 128"};
 const char*bad[]={"CONTROL 0","CONTROL 2","CONTROL 51","CONTROL -1","CONTROL 3 x","CONTROL 3 ","ATTEN 119 5","ATTEN 128 5","ATTEN 120 51","ATTEN 120","ATTEN -4294967176 5","ATTEN 4294967416 5","ATTEN 120 +5","ATTEN  120 5","ATTEN 120 5x","LEVEL 128 50","LEVEL -1 50","TRAIN 120 50 31","TRAIN 120 50 129","TRAIN 120 50","TRAIN 120 50 32 ","TRAIN 120 51 32","TRAIN 120 50 4294967328"};
 oiq_job j;
 for(unsigned i=0;i<sizeof(good)/sizeof(good[0]);i++)assert(oiq_parse(good[i],&j));
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)assert(!oiq_parse(bad[i],&j));
 assert(oiq_parse("TRAIN 120 50 64",&j)&&j.code==120&&j.ms==50&&j.period_us==64&&!j.control);
 assert(oiq_parse("CONTROL 50",&j)&&j.period_us==0&&j.control);
 const uint32_t words[]={0,0xffffffff,0x20040000,0xa5a5a5a5};
 for(unsigned i=0;i<4;i++)for(unsigned code=0;code<256;code++){
  uint32_t w=oiq_atten_word(words[i],code);
  assert(((w^words[i])&~OIQ_ATTEN_MASK)==0);
  assert(oiq_atten_code(w)==code);
 }
 return 0;
}
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'test.c').write_text(source)
   subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/original_iq_tx_probe/main'),str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True)
if __name__=='__main__':unittest.main()
