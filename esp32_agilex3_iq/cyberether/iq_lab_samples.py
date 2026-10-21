"""Verified downloadable CI8 fixtures; the FPGA emits the same integer patterns."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,zlib
import numpy as np
DIRECTORY=Path(__file__).with_name('samples')/'clean-ddc'
MANIFEST=json.loads((DIRECTORY/'manifest.json').read_text())
PATTERNS=tuple(MANIFEST['patterns'])
def load_sample(name):
    if name not in PATTERNS:raise ValueError('Unknown clean sample')
    payload=(DIRECTORY/(name+'.ci8')).read_bytes();meta=MANIFEST['patterns'][name]
    if len(payload)!=8192 or hashlib.sha256(payload).hexdigest()!=meta['sha256']or zlib.crc32(payload)!=meta['crc32']:raise ValueError('Clean sample hash/CRC mismatch')
    return np.frombuffer(payload,np.int8).reshape(-1,2),meta
@dataclass
class SyntheticSnapshot:
    payload:bytes
    descriptor:dict
    def iq(self):return np.frombuffer(self.payload,np.int8).reshape(-1,2)
    def metadata(self):return self.descriptor.copy()
    def __getattr__(self,name):
        try:return self.descriptor[name]
        except KeyError:raise AttributeError(name)from None

def synthetic_snapshot(name,status):
    a,expected=load_sample(name)
    if(status['source'],status['samples'],status['rate'],status['raw_crc'])!=(3,4096,16000000,expected['crc32']):raise ValueError('FPGA pattern identity mismatch')
    return SyntheticSnapshot(a.tobytes(),dict(source=3,samples=4096,rate=16000000,frequency=0,job=status['job'],raw_crc=expected['crc32'],length=8192,capture_us=0,sample_format='ci8',payload_sha256=expected['sha256'],origin='FPGA deterministic test generator; verified against downloadable CI8 fixture',signal_origin='SYNTHETIC FPGA PATTERN; no RF acquisition',pattern=name,capture_time_synchronized=False,frequency_and_rate_origin='Synthetic nominal sample clock; no RF center',absolute_power_calibrated=False))

def tone_measurements(name,raw,output,meta):
    _,spec=load_sample(name);frequencies=spec['tones_hz']
    if not frequencies:return None
    rate=meta['rate'];m=meta['decimation'];phase=meta['phase'];tune=(phase if phase<2**31 else phase-2**32)*rate/2**32
    if meta['bypass_flags']&1:tune=0.
    skip=0 if meta['bypass_flags']&2 else (126+m-1)//m
    z=output[:,0].astype(float)/128+1j*output[:,1].astype(float)/128
    n=np.arange(len(z))[skip:];fs=rate/m
    aliased=[(f-tune+fs/2)%fs-fs/2 for f in frequencies]
    basis=np.column_stack([np.exp(2j*np.pi*f*n/fs)for f in aliased]);amplitudes=np.abs(np.linalg.lstsq(basis,z[skip:],rcond=None)[0])
    input_z=raw[:,0].astype(float)+1j*raw[:,1].astype(float);n0=np.arange(len(raw));input_basis=np.column_stack([np.exp(2j*np.pi*f*n0/rate)for f in frequencies]);input_amplitudes=np.abs(np.linalg.lstsq(input_basis,input_z,rcond=None)[0])
    tones=[dict(input_hz=f,output_hz=alias,input_amplitude_counts=float(before),output_amplitude_counts=float(after),attenuation_db=float(20*np.log10(max(before,1e-12)/max(after,1e-12))))for f,alias,before,after in zip(frequencies,aliased,input_amplitudes,amplitudes)]
    return dict(backend='Host complex sinusoid fit; measured FPGA output, startup excluded',startup_output_samples_excluded=skip,tones=tones)
