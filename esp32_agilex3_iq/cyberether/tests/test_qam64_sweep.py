import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'cyberether'),str(ROOT/'scripts')]
import qam64_sweep as q
from qam64_lab import Manager
from modem_reference import fixedpoint_soft_demapper,viterbi_decode
import check_qam64_sweep as checker

class QAM64SweepTests(unittest.TestCase):
    def test_c_noise_exact_reference_and_command_bounds(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        source=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem/sw/main.c'
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'probe.c';exe=Path(d)/'probe'
            c.write_text('#define IQMON_HOST_TEST\n#define main logger_main\n#include "'+str(source)+'"\n#undef main\n#include <stdio.h>\n#include <assert.h>\n'+r'''
volatile uint32_t test_regs[64],test_jdata,test_jctrl;
int main(void){
 char *version[]={"FIR","1","MSVERSION"};ms_command(1,version,3);reply_save();assert(reply_used>0);
 char *bad[]={"FIR","1","MSRUN","1","918","33"};used=0;ms_command(1,bad,6);reply_save();assert(reply_used>0);
 ms_rng=407;
 for(unsigned n=0;n<256;n++)ms_next();
 for(unsigned n=0;n<176;n++)printf("%d\n",ms_noise(918));
 return 0;
}
''')
            subprocess.run([cc,'-std=c99','-O1',str(c),'-o',str(exe)],check=True,capture_output=True)
            actual=np.asarray([int(x)for x in subprocess.check_output([str(exe)],text=True).splitlines()]).reshape(88,2)
            ref=q.replay_reference(407,918,1)
            np.testing.assert_array_equal(actual,ref['rx'].astype(int)-ref['tx'])

    def test_snapshot_every_field_and_llr_decoding_checked(self):
        r=q.replay_reference(407,918,2);llr=fixedpoint_soft_demapper(r['rx'],'64QAM')[:524]
        a=dict(bits=r['bits'],coded=r['coded'],tx=r['tx'],rx=r['rx'],llr=llr,decoded=viterbi_decode(llr))
        result=q.audit_snapshot(a,407,918,2)
        self.assertTrue(result['all_fields_exact'])
        self.assertEqual(result['plots']['post_fec']['bit_errors'],result['payload_errors'])
        broken={**a,'llr':llr.copy()};broken['llr'][0]+=1
        with self.assertRaises(AssertionError):q.audit_snapshot(broken,407,918,2)
        with self.assertRaises(AssertionError):q.audit_snapshot(a,408,918,2)

    def test_zero_noise_and_prng_bounds(self):
        r=q.replay_reference(1,0,1);np.testing.assert_array_equal(r['tx'],r['rx'])
        for args in ((0,1,1),(1,-1,1),(1,8193,1),(1,1,33)):
            with self.assertRaises(ValueError):q.replay_reference(*args)
        row=dict(raw_errors=0,coded_bits=2048,decoded_errors=0,payload_bits=100096)
        q.summarize([row]);self.assertEqual(row['post_fec_ber'],0);self.assertAlmostEqual(row['zero_error_95_upper_bound'],2.9928159e-5,places=8)

    def test_gui_cannot_change_settings_transmit_or_program(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m=Manager(root)
            for data in ({'tx':True},{'levels':[3]},[],{'program':True}):
                with self.assertRaises(ValueError):m.start(data)
            with patch('qam64_lab.require_modem_checkpoint',return_value={}),patch('qam64_lab.threading.Thread') as thread:
                job=m.start({});self.assertTrue(job['busy'])
                cmd=thread.call_args.kwargs['args'][0]
                self.assertIn('check_qam64_sweep.py',cmd[1]);self.assertNotIn('program',cmd)
                with self.assertRaises(RuntimeError):m.start({})


class SweepAccountingTests(unittest.TestCase):
    class Owner:
        mismatch=False
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def command(self,verb,*args,**kwargs):
            if verb=='MREAD':return dict(bits=0x4d440601 if args[0]==0 else 2)
            if verb=='MSVERSION':return dict(version=1,payload=256)
            _,_,n=args
            return dict(verb=verb,frames=n,payload_bits=n*256,coded_bits=n*524,
                        raw_errors=n,decoded_errors=0,raw_audit=0 if self.mismatch else n,
                        decoded_audit=0,encode_cycles=n*350,decode_cycles=n*40000,clips=0)

    def run_mock(self,root,owner):
        with patch.object(checker,'ROOT',root),patch.object(checker,'require_modem_checkpoint',return_value={'sha256':'test'}),patch.object(checker,'NiosFir',return_value=owner),patch.object(checker,'read_snapshot',return_value={}),patch.object(checker,'audit_snapshot',return_value={'raw_errors':0,'payload_errors':0,'plots':{},'status':'PASS'}),patch('builtins.print'):
            return checker.run(root/'proof',levels=(16,),payload_bits=100000,chunk_frames=32)

    def test_at_least_100k_payload_bits_includes_every_complete_frame(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);proof=self.run_mock(root,self.Owner());r=proof['rows'][0]
            self.assertEqual(proof['status'],'PASS')
            self.assertEqual((r['frames'],r['payload_bits'],r['coded_bits']),(391,100096,204884))
            self.assertEqual(sum(c['frames']for c in r['chunks']),391)
            self.assertEqual(r['raw_errors'],391);self.assertFalse(proof['rf_transmitted'])
            with self.assertRaises(ValueError):self.run_mock(root,self.Owner())

    def test_counter_mismatch_fails_and_preserves_failure_proof(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);owner=self.Owner();owner.mismatch=True
            with self.assertRaises(RuntimeError):self.run_mock(root,owner)
            proof=json.loads((root/'proof/proof.json').read_text())
            self.assertEqual(proof['status'],'FAIL');self.assertIn('audit',proof['error'])
