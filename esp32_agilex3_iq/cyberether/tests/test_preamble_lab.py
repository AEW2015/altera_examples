"""Preamble demo dispatch/control guards without Quartus, JTAG or radios."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'cyberether'))
from preamble_lab import PreambleManager


class PreambleDispatchTests(unittest.TestCase):
    def test_incompatible_image_missing_capture_and_extra_controls_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'cyberether/run';run.mkdir(parents=True)
            manager=PreambleManager(run/'snapshot.json',root)
            with self.assertRaises(RuntimeError):manager.capture({},synthetic=True)
            (run/'active-fpga.json').write_text(json.dumps({'checkpoint':8}))
            with self.assertRaises(ValueError):manager.capture({'source':'saved'})
            with self.assertRaises(ValueError):manager.capture({'source':'tx'})
            with self.assertRaises(ValueError):manager.capture({'source':'passive','duration':999})

    def test_synthetic_dispatch_is_replay_and_passive_is_single_bounded_capture(self):
        for data,synthetic,flag in [({},True,'--synthetic'),({'source':'passive'},False,'--passive')]:
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as d:
                root=Path(d);run=root/'cyberether/run';run.mkdir(parents=True)
                (run/'active-fpga.json').write_text(json.dumps({'checkpoint':8}))
                manager=PreambleManager(run/'snapshot.json',root)
                with patch('preamble_lab.threading.Thread') as thread:
                    job=manager.capture(data,synthetic)
                    command=thread.call_args.kwargs['args'][0]
                    self.assertIn(flag,command)
                    self.assertEqual(command[1],str(root/'scripts/check_preamble.py'))
                    self.assertFalse(job['requested']['tx'])
                    self.assertTrue(job['busy'])


class NativePreambleControlTests(unittest.TestCase):
    def test_bad_load_config_bounds_busy_guard_and_ci8_byte_order(self):
        compiler=shutil.which('cc')
        if not compiler:self.skipTest('Native C compiler unavailable')
        source=ROOT/'fpga_hub/iq_bridge/vds_demo_08_preamble/sw/main.c'
        with tempfile.TemporaryDirectory() as d:
            harness=Path(d)/'test.c';binary=Path(d)/'test'
            harness.write_text('#define IQMON_HOST_TEST\n#define main monitor_main\n#include "'+str(source)+'"\n#undef main\n#include <assert.h>\n'+r'''
volatile uint32_t test_regs[64],test_jdata,test_jctrl;
static void command(const char *s){unsigned n=0;while(s[n]){input_line[n]=s[n];n++;}input_line[n]=0;fir_command();}
int main(void){
 PRE(2)=10;PRE(27)=0;PRE(8)=0x7777;PRE(1)=0;
 command("FIR 1 PLOAD 0 01zz");assert(PRE(8)==0x7777);
 command("FIR 2 PLOAD 1 01ff");assert(PRE(8)==0x7777);
 command("FIR 3 PCONFIG 16385 160 24576");assert(PRE(2)==10);
 command("FIR 4 PCONFIG 16380 127 24576");assert(PRE(2)==10);
 command("FIR 5 PCONFIG 16380 160 32769");assert(PRE(2)==10);
 PRE(1)=1;command("FIR 6 PCONFIG 16380 160 24576");assert(PRE(2)==10);
 command("FIR 7 PCLEAR");assert(PRE(1)==1);
 PRE(1)=0;command("FIR 8 PCONFIG 16380 160 24576");
 assert(PRE(2)==16380 && PRE(3)==160 && PRE(4)==4 && PRE(5)==24576 && PRE(6)==7936);
 command("FIR 9 PLOAD 0 01ff02fe");assert(PRE(8)==0xfe02);
 command("FIR 10 PAIR 1");assert(FIR(18)==1);
 command("FIR 11 PRESET 2");assert((int16_t)COEFF(0)==-42 && FIR(20)==2);
 command("FIR 12 PAIR 0");assert(FIR(18)==0);
 return 0;
}
''')
            subprocess.run([compiler,'-std=c11','-O2',str(harness),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)


if __name__=='__main__':unittest.main()
