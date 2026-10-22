#!/usr/bin/env python3
"""Offline WLAN54 test fixtures; never runtime radio synthesis or DSP.

Newest-bit-first taps match IEEE reversed 133/171 (0155/0117), independently
anchored to gr-ieee802-11 lib/utils.cc. Positive LLR favors one.
"""
import zlib

def encode(payload,seed=93,crc_bad=False):
    if not 1<=seed<128:raise ValueError('seven-bit nonzero scrambler seed required')
    psdu=bytes(payload)+(zlib.crc32(payload)^int(crc_bad)).to_bytes(4,'little')
    bits=[0]*16+[byte>>b&1 for byte in psdu for b in range(8)]+[0]*6
    symbols=(len(bits)+215)//216
    bits += [0]*(symbols*216-len(bits))
    lfsr=[seed>>i&1 for i in range(6,-1,-1)]
    scrambled=[]
    for bit in bits:
        feedback=lfsr[0]^lfsr[3]
        scrambled.append(bit^feedback)
        lfsr=lfsr[1:]+[feedback]
    tail=16+len(psdu)*8;scrambled[tail:tail+6]=[0]*6
    history=[0]*7;mother=[]
    for bit in scrambled:
        history=[bit]+history[:6]
        mother.extend(sum(history[i] for i in tap)%2 for tap in ((0,2,3,5,6),(0,1,2,3,6)))
    punctured=[mother[i+j] for i in range(0,len(mother),6) for j in (0,1,2,5)]
    output=[]
    for symbol in range(symbols):
        block=punctured[symbol*288:(symbol+1)*288]
        first=[block[row*16+col] for col in range(16) for row in range(18)]
        second=[0]*288
        for i,bit in enumerate(first):second[(i//3)*3+(i-i//18)%3]=bit
        output.extend(second)
    return psdu,output

def native_frame(run=123,packet=0,seed=1,mac=bytes.fromhex('782184d44f98')):
    """Exact fixture mirror of wifi64_tx/main/protocol.h, excluding native FCS."""
    if len(mac)!=6:raise ValueError('MAC must contain six bytes')
    body=bytearray(b'W64A'+bytes((1,54,64,0)))
    body+=int(run).to_bytes(4,'little')+int(packet).to_bytes(4,'little')+int(seed).to_bytes(4,'little')
    x=(seed^run^(packet*0x9e3779b9))&0xffffffff
    if not x:x=1
    for _ in range(44):
        x^=(x<<13)&0xffffffff;x^=x>>17;x^=(x<<5)&0xffffffff;body.append(x&255)
    return bytes((8,0,0,0))+bytes([255])*6+mac+mac+((packet&4095)<<4).to_bytes(2,'little')+body

def header():
    import math
    frame=native_frame();psdu,bits=encode(frame);_,bad=encode(frame,crc_bad=True)
    tone=[(round(8192*math.cos(2*math.pi*7*n/64)),round(8192*math.sin(2*math.pi*7*n/64))) for n in range(64)]
    def array(name,ctype,values):return 'static const '+ctype+' '+name+'['+str(len(values))+']={'+','.join(map(str,values))+'};\n'
    out='/* Offline generated fixture, not captured RF. */\n'
    out+=array('fixture_psdu','uint8_t',psdu)
    out+=array('fixture_llr','int16_t',[(1000 if b else -1000) for b in bits])
    out+=array('fixture_bad_llr','int16_t',[(1000 if b else -1000) for b in bad])
    out+='static const w64_complex fixture_tone[64]={'+','.join('{%d,%d}'%v for v in tone)+'};\n'
    out+='#define FIXTURE_PSDU_BYTES '+str(len(psdu))+'u\n#define FIXTURE_LLR_COUNT '+str(len(bits))+'u\n'
    return out
