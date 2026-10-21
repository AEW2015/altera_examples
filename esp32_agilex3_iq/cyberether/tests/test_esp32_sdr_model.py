"""Check teaching-model wire output against the actual firmware C packers."""
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from esp32_sdr_model import ReceiverModel, RATES, bandwidth_code, pack_samples


class FirmwareModelTests(unittest.TestCase):
    def test_capture_bounds_and_sparse_timing(self):
        model=ReceiverModel()
        for code,fs in RATES.items():
            cap=model.command(f'CAP16 8192 {code}')
            self.assertEqual(cap.fs,fs)
            self.assertEqual(len(cap.payload),16384)
            self.assertAlmostEqual(cap.capture_seconds,8192/fs)
            self.assertGreater(cap.uart_seconds,0.08192)
            self.assertEqual(zlib.crc32(cap.payload),int(cap.header.split()[2],16))
        for code in (2,3,4,5):
            self.assertEqual(model.command(f'CAP16 8192 {code}'),'ERR rate')
        for length in (0,255,16381):
            self.assertEqual(model.command(f'CAP16 {length} 6'),'ERR command')

    def test_invalid_controls_leave_state_intact(self):
        model=ReceiverModel(gain_max=60)
        for cmd in ('FREQ 99','FREQ 6001','BANDWIDTH 11','BANDWIDTH 68',
                    'GAIN MANUAL 61','BAUD 4000000','FREQ text'):
            self.assertEqual(model.command(cmd),'ERR command')
        self.assertEqual((model.frequency_mhz,model.bandwidth_mhz,model.baud),(2412,0,2000000))
        self.assertEqual(model.command('BANDWIDTH 0'),'OK')
        self.assertEqual(model.command('GAIN MANUAL 60'),'OK')
        self.assertFalse(model.hardware_agc)
        self.assertEqual(model.command('GAIN HARDWARE'),'OK')
        self.assertTrue(model.hardware_agc)

    def test_signed_packing_and_odd_tail(self):
        iq=np.array([[-512,511],[-1,0],[4,-4]])
        self.assertEqual(pack_samples(iq,16),bytes([128,127,255,0,1,255]))
        payload=pack_samples(iq,20)
        self.assertEqual(len(payload),8)
        decoded=[]
        for j in range(0,len(iq),2):
            bits=int.from_bytes(payload[(j//2)*5:(j//2)*5+5],'little')
            for k in range(min(2,len(iq)-j)):
                decoded.append([((bits>>(20*k+b)&1023)^512)-512 for b in (0,10)])
        self.assertEqual(decoded,iq.tolist())

    @unittest.skipUnless(shutil.which('cc'),'C compiler needed for firmware-source comparison')
    def test_actual_c_packers_and_bandwidth_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'esp_rom_crc.h').write_text('#include <stdint.h>\nstatic uint32_t esp_rom_crc32_le(uint32_t c,const uint8_t*p,unsigned n){return 0;}\n')
            code=r'''
#include <stdbool.h>
#include <stdlib.h>
#include <stdint.h>
static uint32_t words[16384];
#define IQ_BUFFER words
static bool send_bytes(const void *p,unsigned n){return true;}
#include "burst_capture.h"
#define CONFIG_IDF_TARGET_ESP32 1
#include "rx_bandwidth.h"
int main(int argc,char**argv){
 unsigned format=atoi(argv[1]);
 if(format==99){for(unsigned n=0;n<=67;n++)putchar(rx_bandwidth_dcap(n));return 0;}
 unsigned n=fread(words,4,16384,stdin);
 if(format==16)pack_iq8(n);else if(format==20)pack_iq(n);
 return fwrite(words,1,wire_size(n,format),stdout)==wire_size(n,format)?0:1;
}
'''
            (folder/'check.c').write_text(code)
            subprocess.run(['cc','-I',str(folder),'-I',str(ROOT/'unified/main/common'),str(folder/'check.c'),'-o',str(folder/'check')],check=True,capture_output=True)
            rng=np.random.default_rng(2026)
            for n in (1,2,255,256,8191,16380):
                iq=rng.integers(-512,512,(n,2),dtype=np.int16)
                u=iq.astype(np.int64)&1023
                words=(u[:,0]|(u[:,1]<<10)).astype('<u4').tobytes()
                for fmt in (0,16,20):
                    actual=subprocess.run([str(folder/'check'),str(fmt)],input=words,check=True,capture_output=True).stdout
                    self.assertEqual(actual,pack_samples(iq,fmt),(n,fmt))
            curve=subprocess.run([str(folder/'check'),'99'],check=True,capture_output=True).stdout
            for mhz in (0,*range(12,68)):
                self.assertEqual(curve[mhz],bandwidth_code(mhz),mhz)
