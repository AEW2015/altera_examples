"""IQS1 fixed-size SPI CI8 transport. No hardware is opened on import."""
import struct
import zlib
from dataclasses import dataclass
CHUNK=1024
PACKET=1056
MAX_CAPTURE=32760
@dataclass(frozen=True)
class Chunk:
    source:int
    sequence:int
    offset:int
    total:int
    final:bool
    payload:bytes
    synthetic:bool=False

def encode(source,sequence,offset,total,payload,synthetic=False):
    payload=bytes(payload)
    _fields(source,offset,total,len(payload),offset+len(payload)==total)
    header=struct.pack('<4sBBBBIIIII',b'IQS1',1,source,int(offset+len(payload)==total)|(int(bool(synthetic))<<1),32,
                       sequence,offset,total,len(payload),zlib.crc32(payload))
    return header+struct.pack('<I',zlib.crc32(header))+payload+bytes(CHUNK-len(payload))

def _fields(source,offset,total,length,final):
    if source not in (0,1,2) or not (0<total<=MAX_CAPTURE) or total%2:
        raise ValueError('source/total invalid')
    if offset%CHUNK or not (0<=offset<total) or length!=min(CHUNK,total-offset) or length%2:
        raise ValueError('CI8 chunk bounds invalid')
    if bool(final)!=(offset+length==total):raise ValueError('final flag mismatch')

def decode(packet):
    if len(packet)!=PACKET:raise ValueError('wrong SPI transaction size')
    magic,version,source,flags,hsize,seq,offset,total,length,crc=struct.unpack('<4sBBBBIIIII',packet[:28])
    if magic!=b'IQS1' or version!=1 or hsize!=32 or flags&~3:
        raise ValueError('unsupported SPI header')
    if zlib.crc32(packet[:28])!=struct.unpack('<I',packet[28:32])[0]:raise ValueError('header CRC')
    _fields(source,offset,total,length,flags&1)
    data=packet[32:32+length]
    if zlib.crc32(data)!=crc:raise ValueError('payload CRC')
    if any(packet[32+length:]):raise ValueError('nonzero padding')
    return Chunk(source,seq,offset,total,bool(flags&1),data,bool(flags&2))

class Capture:
    """One capture, strict in-order chunks; a loss/restart never yields silent IQ."""
    def __init__(self):self.identity=None;self.data=bytearray();self.complete=False
    def append(self,packet):
        c=decode(packet)
        if self.complete:raise ValueError('capture already complete')
        identity=(c.source,c.sequence,c.total,c.synthetic)
        if self.identity is None:
            if c.offset:raise ValueError('first chunk missing')
            self.identity=identity
        if identity!=self.identity or c.offset!=len(self.data):raise ValueError('sequence/source/offset mismatch')
        self.data.extend(c.payload);self.complete=c.final
        return self.complete
