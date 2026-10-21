"""Offline teaching model of the original ESP32 burst receiver; never opens hardware.

Protocol/packing follows unified/main/{targets/esp32/receiver.c,common/burst_capture.h}.
RF response, gain and AGC below are illustrative, not silicon/register simulation.
"""
from dataclasses import dataclass
import math
import zlib
import numpy as np

RATES = {0: 80_000_000, 1: 40_000_000, 6: 16_000_000}
BANDWIDTH_POINTS = [(8,67),(12,55),(16,48),(24,38),(32,32),(48,25),
                    (64,20),(80,17),(96,15),(112,14),(127,12)]


def bandwidth_code(mhz):
    """Original-ESP32 integer interpolation from rx_bandwidth.h."""
    if mhz == 0:
        return 0
    if not 12 <= mhz <= 67:
        raise ValueError('Bandwidth must be 0 or 12..67 MHz')
    for (ca, a), (cb, b) in zip(BANDWIDTH_POINTS, BANDWIDTH_POINTS[1:]):
        if mhz >= b:
            return ca + ((cb-ca)*(a-mhz)+(a-b)//2)//(a-b)
    return 127


def pack_samples(iq10, fmt=16):
    """Input: signed ten-bit [I,Q]; exact low-20-bit wire packing."""
    iq = np.asarray(iq10)
    if iq.ndim != 2 or iq.shape[1] != 2 or np.any(iq < -512) or np.any(iq > 511):
        raise ValueError('Expected N x 2 signed ten-bit samples')
    if not np.all(iq == np.floor(iq)):
        raise ValueError('Integer samples required')
    u = iq.astype(np.int64) & 1023
    words = u[:,0] | (u[:,1] << 10)
    if fmt == 16:
        return (iq.astype(np.int64) >> 2).astype(np.int8).tobytes()
    if fmt == 20:
        # Pairs form 40 little-endian bits; an odd final sample uses three bytes.
        return b''.join(int(words[j] | ((words[j+1] if j+1<len(words) else 0)<<20))
                        .to_bytes(5 if j+1<len(words) else 3,'little')
                        for j in range(0,len(words),2))
    if fmt == 0:
        # Synthetic raw words: upper 12 bits are zero; hardware may contain other bits.
        return words.astype('<u4').tobytes()
    raise ValueError('Format must be 0 (raw), 16 (CI8), or 20 (IQ10)')


@dataclass
class Capture:
    iq10: np.ndarray
    payload: bytes
    header: str
    fs: int
    format: int
    capture_seconds: float
    uart_seconds: float
    clipped_components: int


class ReceiverModel:
    """Selected SDR commands only. INFO/LIMITS describe this simulated instance."""
    def __init__(self, gain_max=72):
        self.frequency_mhz = 2412
        self.hardware_agc = True
        self.gain_code = 40
        self.gain_max = gain_max  # illustrative; real firmware reads RX_GAIN at boot
        self.bandwidth_mhz = 0
        self.baud = 2_000_000

    def command(self, line):
        parts = line.strip().split()
        if parts == ['INFO']:
            return 'ESP32SDR 6 burst 16380'
        if parts == ['RANGE?']:
            return 'RANGE 100 6000 1'
        if parts == ['MODE?']:
            return f'RF_MODE,SDR,baud={self.baud}'
        if parts == ['BAUD?']:
            return f'BAUD {self.baud}'
        if parts == ['GAIN?']:
            return f'GAIN {"HARDWARE" if self.hardware_agc else "MANUAL"} {(-1 if self.hardware_agc else self.gain_code)} 0 {self.gain_max} {int(not self.hardware_agc)}'
        if parts == ['GAIN','HARDWARE']:
            self.hardware_agc = True
            return 'OK'
        try:
            if len(parts)==2 and parts[0]=='FREQ' and 100<=int(parts[1])<=6000:
                self.frequency_mhz=int(parts[1]); return 'OK'
            if len(parts)==2 and parts[0]=='BANDWIDTH':
                mhz=int(parts[1]); bandwidth_code(mhz)
                self.bandwidth_mhz=mhz; return 'OK'
            if len(parts)==3 and parts[:2]==['GAIN','MANUAL'] and 0<=int(parts[2])<=self.gain_max:
                self.hardware_agc=False; self.gain_code=int(parts[2]); return 'OK'
            if len(parts)==2 and parts[0]=='BAUD' and int(parts[1]) in (1_000_000,2_000_000):
                self.baud=int(parts[1]); return f'OK BAUD {self.baud}'
            if len(parts)==3 and parts[0] in ('CAP','CAP16','CAP20'):
                n,code=map(int,parts[1:])
                if not 256<=n<=16380 or not 0<=code<=6:
                    return 'ERR command'
                if code not in RATES:
                    return 'ERR rate'
                return self.capture(n,code,{'CAP':0,'CAP16':16,'CAP20':20}[parts[0]])
        except ValueError:
            pass
        return 'ERR command'

    def capture(self, n=8192, rate_code=6, fmt=16, seed=7):
        if not 256<=n<=16380 or rate_code not in RATES:
            raise ValueError('Unsupported length/rate')
        fs=RATES[rate_code]; t=np.arange(n)/fs
        rng=np.random.default_rng(seed)
        x=0.025*(rng.normal(size=n)+1j*rng.normal(size=n))
        # Fixed RF tones; LO changes their baseband offsets before sampling.
        for rf_mhz, amp in ((2416.,0.35),(2426.,0.22)):
            offset=(rf_mhz-self.frequency_mhz)*1e6
            # Smooth illustrative analog filter, evaluated BEFORE sampling/aliasing.
            response=1. if self.bandwidth_mhz==0 else 1/np.sqrt(1+(2*offset/(self.bandwidth_mhz*1e6))**8)
            x+=amp*response*np.exp(2j*np.pi*offset*t)
        if self.hardware_agc:
            x*=0.65/max(np.sqrt(np.mean(abs(x)**2)),1e-12)
        else:
            x*=2**((self.gain_code-40)/16)  # teaching scale, NOT a measured gain-code law
        components=np.column_stack((x.real,x.imag))*511
        clipped=int(np.count_nonzero((components>511)|(components<-512)))
        iq=np.clip(np.rint(components),-512,511).astype(np.int16)
        payload=pack_samples(iq,fmt)
        duration=n/fs
        header=f'DATA {n} {zlib.crc32(payload):08x} {math.ceil(duration*1e6)}\n'
        # Ideal minimum wire time: ignores scheduler/calibration/FPGA/host overhead.
        wire_seconds=10*(len(header.encode())+len(payload))/self.baud
        return Capture(iq,payload,header,fs,fmt,duration,wire_seconds,clipped)
