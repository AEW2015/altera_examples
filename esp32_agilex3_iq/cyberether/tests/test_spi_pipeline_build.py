"""Programming helper safety without serial, JTAG, or Quartus access."""
import fcntl,hashlib,json,subprocess,sys,tempfile,unittest,shutil
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import spi_pipeline

class ProgrammingLeaseTest(unittest.TestCase):
 def test_failing_programmer_releases_global_lease_even_if_traceback_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);stage=root/'stage';(stage/'run').mkdir(parents=True)
   image=stage/'iq_bridge_vds.sof';image.write_bytes(b'offline-test-image')
   (stage/'BUILD_RESULT.json').write_text(json.dumps(dict(checkpoint=7,status='PASS_BUILD',sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_fingerprint='source',build_inputs_sha256={})))
   attempted=[]
   def run(args,**kwargs):
    if '-o' in args:
     attempted.append(args)
     raise subprocess.CalledProcessError(1,args)
    if '-c' in args:compile(args[2],'<owner-scan>','exec')
    return subprocess.CompletedProcess(args,0)
   with mock.patch.multiple(spi_pipeline,ROOT=root,STAGE=stage),mock.patch.object(spi_pipeline,'fingerprint',return_value='source'),mock.patch.object(spi_pipeline,'build_inputs',return_value={}),mock.patch.object(spi_pipeline,'stop_demo'),mock.patch.object(spi_pipeline,'local_tools',return_value=True),mock.patch.object(spi_pipeline,'tool_path',side_effect=str),mock.patch.object(spi_pipeline,'tool_command',side_effect=lambda args,**kwargs:args),mock.patch.object(spi_pipeline.subprocess,'run',side_effect=run):
    retained=None
    try:spi_pipeline.program('offline-cable')
    except subprocess.CalledProcessError as error:retained=error
    self.assertTrue(attempted)
    self.assertIsNotNone(retained)
    self.assertIsNotNone(retained.__traceback__)
    with (root/'cyberether/run/rf-link-capture.lock').open('a') as lease:
     fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    self.assertFalse((root/'cyberether/run/active-fpga.json').exists())

class BootFirPresetTest(unittest.TestCase):
 def test_boot_replaces_noncanonical_reload_ram_and_matches_presets(self):
  compiler=shutil.which('cc')
  if not compiler:self.skipTest('Native C compiler unavailable')
  source=spi_pipeline.STAGE/'sw/main.c'
  with tempfile.TemporaryDirectory() as tmp:
   harness=Path(tmp)/'boot.c';binary=Path(tmp)/'boot'
   harness.write_text('#define IQMON_HOST_TEST\n#define main monitor_main\n#include "'+str(source)+'"\n#undef main\n#include <assert.h>\n'+r'''
volatile uint32_t test_regs[64],test_jdata,test_jctrl;
int main(void){
 for(unsigned i=0;i<16;i++)fir_test_coeff[i]=(i==0?0:2048);
 fir_test_regs[18]=1;fir_test_regs[19]=1;fir_test_regs[20]=99;
 fir_boot_init();
 for(unsigned i=0;i<16;i++)assert(fir_test_coeff[i]==2048);
 assert(FIR(18)==0 && FIR(19)==0 && FIR(20)==1);
 fir_preset(2);assert((int16_t)COEFF(0)==-42 && COEFF(7)==7885 && FIR(20)==2);
 fir_preset(1);for(unsigned i=0;i<16;i++)assert(COEFF(i)==2048);
 assert(FIR(20)==1);
 return 0;
}
''')
   subprocess.run([compiler,'-std=c11','-O2',str(harness),'-o',str(binary)],check=True,capture_output=True)
   subprocess.run([str(binary)],check=True)

if __name__=='__main__':unittest.main()
