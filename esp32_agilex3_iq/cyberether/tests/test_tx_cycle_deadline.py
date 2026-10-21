"""Native tests for bounded wrap-safe TX cycle timing (no RF hardware)."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('cc'),'native compiler needed')
class CycleDeadline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();temp=Path(cls.temp.name);source=temp/'wrap.c';source.write_text('#include "probe_protocol.h"\nbool before(uint32_t now,uint32_t deadline){return probe_cycle_before(now,deadline);}\n');lib=temp/'probe.so';subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/esp32_tx_probe/main'),str(source),str(ROOT/'firmware/esp32_tx_probe/main/probe_protocol.c'),'-o',str(lib)],check=True);cls.lib=ctypes.CDLL(str(lib));cls.before=cls.lib.before;cls.before.argtypes=[ctypes.c_uint32,ctypes.c_uint32];cls.before.restype=ctypes.c_bool;cls.budget=cls.lib.probe_cycle_budget;cls.budget.argtypes=[ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(ctypes.c_uint32)];cls.budget.restype=ctypes.c_bool
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_wrap_and_exact_deadline(self):
        for now,deadline,want in [(100,200,True),(200,200,False),(201,200,False),(0xfffffff0,16,True),(15,16,True),(16,16,False),(32,0xfffffff0,False)]:self.assertEqual(self.before(now,deadline),want)
        # A complete 500ms job crossing the32bit counter wrap.
        start=0xffff0000;deadline=(start+80000000)&0xffffffff
        for elapsed in [0,1,40000000,79999999]:self.assertTrue(self.before((start+elapsed)&0xffffffff,deadline))
        self.assertFalse(self.before((start+80000000)&0xffffffff,deadline))
    def test_remaining_wall_budget_limits(self):
        value=ctypes.c_uint32();self.assertTrue(self.budget(160000000,499000,ctypes.byref(value)));self.assertEqual(value.value,79840000)
        for cpu,remaining in [(0,1),(160000000,0),(160000000,-1),(160000000,500001),(1,1)]:self.assertFalse(self.budget(cpu,remaining,ctypes.byref(value)))
        self.assertTrue(self.budget(160000000,500000,ctypes.byref(value)));self.assertEqual(value.value,80000000)
        self.assertTrue(self.budget(0xffffffff,500000,ctypes.byref(value)));self.assertEqual(value.value,0x7fffffff)
    def test_no_per_symbol_wall_clock(self):
        text=(ROOT/'firmware/esp32_tx_probe/main/main.c').read_text();function=text.split('static void phase_run(',1)[1].split('static void worker(',1)[0];loop=function.split('while (!cancel',1)[1]
        self.assertEqual(function.count('esp_timer_get_time()'),1);self.assertNotIn('esp_timer_get_time',loop);self.assertIn('CONFIG_PM_ENABLE',text);self.assertIn('probe_cycle_before(next,deadline)',loop)
