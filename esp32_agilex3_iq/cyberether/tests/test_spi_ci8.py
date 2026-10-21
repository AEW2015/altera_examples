import sys
from pathlib import Path
import unittest
import ctypes,shutil,subprocess,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spi_ci8 import *
class SPITransport(unittest.TestCase):
 def test_native_encoder_matches_wire(self):
  compiler=shutil.which('cc')
  if compiler is None:self.skipTest('native C compiler unavailable')
  source=Path(__file__).resolve().parents[2]/'firmware/esp32_spi_probe/main/iq_spi_packet.c'
  with tempfile.TemporaryDirectory() as folder:
   library=Path(folder)/'packet.so'
   subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',str(source),'-o',str(library)],check=True)
   native=ctypes.CDLL(str(library))
   command=native.iq_spi_packet_command;command.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
   self.assertEqual(command(ctypes.create_string_buffer(b'T'+bytes(PACKET-1)),PACKET),1)
   self.assertEqual(command(ctypes.create_string_buffer(b'R'+bytes(PACKET-1)),PACKET),2)
   for raw in (bytes(PACKET),b'Q'+bytes(PACKET-1),b'R!'+bytes(PACKET-2)):
    self.assertEqual(command(ctypes.create_string_buffer(raw),PACKET),0)
   self.assertEqual(command(ctypes.create_string_buffer(b'R'+bytes(PACKET-1)),PACKET-1),0)
   build=native.iq_spi_packet_build
   build.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint8,ctypes.c_uint32,ctypes.c_size_t,ctypes.c_uint8]
   for total in (2,1024,1026,32760):
    data=bytes((n*37+11)&255 for n in range(total));capture=ctypes.create_string_buffer(data)
    for source_id in (0,1,2):
     for offset in range(0,total,CHUNK):
      out=ctypes.create_string_buffer(PACKET)
      self.assertEqual(build(out,capture,total,source_id,0xffffffff,offset,0),0)
      self.assertEqual(out.raw,encode(source_id,0xffffffff,offset,total,data[offset:offset+CHUNK]))
      self.assertEqual(build(out,capture,total,source_id,0xffffffff,offset,1),0)
      self.assertEqual(out.raw,encode(source_id,0xffffffff,offset,total,data[offset:offset+CHUNK],synthetic=True))
   self.assertEqual(build(out,capture,3,2,1,0,0),-1)
 def test_synthetic_identity_is_not_rf(self):
  self.assertTrue(decode(encode(2,1,0,2,b'IQ',synthetic=True)).synthetic)
  self.assertFalse(decode(encode(2,1,0,2,b'IQ')).synthetic)
  c=Capture();c.append(encode(2,1,0,2048,b'x'*1024,synthetic=True))
  with self.assertRaises(ValueError):c.append(encode(2,1,1024,2048,b'y'*1024,synthetic=False))
 def test_capture(self):
  data=bytes((n*37+11)&255 for n in range(32760));c=Capture()
  for offset in range(0,len(data),CHUNK):
   packet=encode(2,0xffffffff,offset,len(data),data[offset:offset+CHUNK])
   self.assertEqual(len(packet),PACKET);c.append(packet)
  self.assertTrue(c.complete);self.assertEqual(c.data,data)
 def test_corruption(self):
  packet=encode(0,4,0,1024,bytes(range(256))*4)
  for position in (0,4,8,24,28,32,1055):
   bad=bytearray(packet);bad[position]^=1
   with self.assertRaises(ValueError):decode(bad)
 def test_padding_and_truncation(self):
  packet=encode(1,0,0,2,b'IQ')
  with self.assertRaises(ValueError):decode(packet[:-1])
  with self.assertRaises(ValueError):decode(packet[:-1]+b'!')
 def test_loss_duplicate_restart(self):
  a=encode(2,1,0,2048,b'a'*1024);b=encode(2,1,1024,2048,b'b'*1024)
  with self.assertRaises(ValueError):Capture().append(b)
  c=Capture();c.append(a)
  with self.assertRaises(ValueError):c.append(a)
  with self.assertRaises(ValueError):c.append(encode(2,2,1024,2048,b'b'*1024))
  self.assertTrue(c.append(b))
  with self.assertRaises(ValueError):c.append(b)
 def test_bounds(self):
  for args in ((3,0,0,2,b'ab'),(2,0,0,3,b'abc'),(2,0,2,4,b'ab'),(0,0,0,32762,b'x'*1024)):
   with self.assertRaises(ValueError):encode(*args)
if __name__=='__main__':unittest.main()
