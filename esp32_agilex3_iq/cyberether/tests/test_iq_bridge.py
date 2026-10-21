import sys,struct,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from iq_bridge import HEADER,COMMAND,encode_command,decode_frame,decode_header

def wire(payload=b'\x80\x7f\x00\xff',kind=1,source=0,job=42,error=0):
    h=HEADER.pack(b'IQB1',1,kind,source,0,job,len(payload)//2,16000000,2417000000,zlib.crc32(payload),10,error,len(payload),100,200,0)
    body=h+payload;return body+struct.pack('<I',zlib.crc32(body))
class BridgeProtocolTests(unittest.TestCase):
    def test_layout(self):self.assertEqual(HEADER.size,64);self.assertEqual(COMMAND.size,16)
    def test_command_crc(self):
        b=encode_command(3,2,job=99,value=16380)
        self.assertEqual(len(b),20);self.assertEqual(zlib.crc32(b[:-4]),int.from_bytes(b[-4:],'little'))
        self.assertEqual(COMMAND.unpack(b[:-4]),(b'IQBC',3,2,0,99,16380))
    def test_signed_iq_and_identity(self):
        f=decode_frame(wire());self.assertEqual(f.iq().tolist(),[[-128,127],[0,-1]])
        self.assertEqual((f.job,f.source,f.rate),(42,0,16000000));self.assertFalse(f.metadata()['capture_time_synchronized'])
    def test_every_corrupted_byte_rejected(self):
        good=wire()
        for index in range(len(good)):
            bad=bytearray(good);bad[index]^=1
            with self.assertRaises(ValueError):decode_frame(bytes(bad))
    def test_payload_crc_independent_of_wire_crc(self):
        b=bytearray(wire());b[64]^=1;b[-4:]=struct.pack('<I',zlib.crc32(b[:-4]))
        with self.assertRaisesRegex(ValueError,'payload CRC'):decode_frame(bytes(b))
    def test_bounds(self):
        with self.assertRaises(ValueError):decode_frame(wire(b'\0'*32770))
        with self.assertRaises(ValueError):decode_frame(wire(b'\0'))
        with self.assertRaises(ValueError):decode_frame(wire(source=3))
        with self.assertRaises(ValueError):decode_frame(wire(error=1))
    def test_no_partial_frames(self):
        good=wire()
        for n in range(len(good)):
            with self.assertRaises(ValueError):decode_frame(good[:n])
    def test_embedded_magic_and_newlines_are_payload(self):
        p=(b'IQB1DATA 123\n\rIQBC'*20)
        if len(p)%2:p+=b'\0'
        self.assertEqual(decode_frame(wire(p)).payload,p)
if __name__=='__main__':unittest.main()
