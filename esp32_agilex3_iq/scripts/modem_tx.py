#!/usr/bin/env python3
"""Build/validate the optional S3 TX application, or explicitly control its loader.

Imports never open a serial device. Upload never initializes RF or starts playback.
"""
import argparse,hashlib,json,os,subprocess,sys,time,zlib
from pathlib import Path
import struct
from common import ROOT
TX_COMMIT='cf88cb6ab367c9db44d5af81d85923cfc883751e'
SDK_COMMIT='0c45a102a96e82000f145b786a20de229b9f8557'
PHY_SHA='29dcc18a035801bd41486d5d59f3caeb62f8ed153533c488828bffef1abb99fd'

def fetch():
    target=ROOT/'vendor/esp32-iq-tx'
    if not target.exists():
        subprocess.run(['git','clone','https://github.com/whstudio123/esp32-iq-tx.git',str(target)],check=True)
        subprocess.run(['git','-C',str(target),'checkout','--detach',TX_COMMIT],check=True)
    actual=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip()
    if actual!=TX_COMMIT:raise RuntimeError('TX dependency must be at pinned commit '+TX_COMMIT+'; use a clean dependency checkout')
    if subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True).strip():raise RuntimeError('TX dependency has local changes')
    print('Pinned TX component:',TX_COMMIT)

def validate_waveform(data,max_samples=16128,alignment=256):
    if not data or len(data)%4:raise ValueError('Waveform must contain complete little-endian IQ10 words')
    n=len(data)//4
    if n>max_samples or n%alignment:raise ValueError('Waveform exceeds capacity or loop alignment')
    if any(word[0] & 0xfff00000 for word in struct.iter_unpack('<I',data)):raise ValueError('Reserved IQ10 upper bits must be zero')
    return dict(samples=n,bytes=len(data),crc=f'{zlib.crc32(data)&0xffffffff:08x}',sha256=hashlib.sha256(data).hexdigest())

def check_elf(path):
    from elftools.elf.elffile import ELFFile
    with Path(path).open('rb')as f:
        for seg in ELFFile(f).iter_segments():
            if seg['p_type']!='PT_LOAD' or not seg['p_memsz']:continue
            start=seg['p_paddr']
            if 0x40370000<=start<0x403e0000:start-=0x6e8000
            if max(start,0x3fcd0000)<min(start+seg['p_memsz'],0x3fce0000):raise RuntimeError('ELF overlaps reserved RF SRAM')

def build():
    fetch();sdk=Path(os.environ.get('IDF_PATH',''))
    if not sdk.is_dir() or not (sdk/'tools/idf.py').is_file():raise RuntimeError('Export ESP-IDF v5.3.5 first')
    commit=subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD'],text=True).strip()
    if commit!=SDK_COMMIT:raise RuntimeError('Expected ESP-IDF v5.3.5 commit '+SDK_COMMIT)
    phy=sdk/'components/esp_phy/lib/esp32s3/libphy.a'
    digest=hashlib.sha256(phy.read_bytes()).hexdigest()
    if digest!=PHY_SHA:raise RuntimeError('Unexpected PHY library; IQ playback sequence is not qualified against it')
    out=ROOT/'build-modem-tx-s3';out.mkdir(exist_ok=True)
    report=out/'modem-tx-build.json';report.write_text(json.dumps(dict(success=False,chip='esp32s3'))+'\n')
    subprocess.run([sys.executable,str(sdk/'tools/idf.py'),'-C',str(ROOT/'firmware/modem_tx'),'-B',str(out),'-DIDF_TARGET=esp32s3','-DSDKCONFIG='+str(out/'sdkconfig'),'build'],check=True)
    check_elf(out/'atum_modem_tx.elf')
    result=dict(success=True,chip='esp32s3',tx_commit=TX_COMMIT,sdk_commit=commit,phy_sha256=digest,elf_sram_overlap=False,bin_sha256=hashlib.sha256((out/'atum_modem_tx.bin').read_bytes()).hexdigest(),hardware_qualified=False)
    report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

class TXLoader:
    def __init__(self,port,baud=2000000):
        import serial
        self.serial=serial.Serial(port,baudrate=baud,timeout=.2,write_timeout=5,exclusive=True)
    def close(self):self.serial.close()
    def command(self,line,prefix,timeout=12):
        self.serial.write((line+'\n').encode());return self.response(prefix,timeout)
    def response(self,prefix,timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            line=self.serial.readline().decode(errors='replace').strip()
            if line.startswith('ERROR'):raise RuntimeError(line)
            if line.startswith(prefix):return line
        raise TimeoutError('No '+prefix+' acknowledgment from TX firmware')
    def info(self):
        line=self.command('INFO','MODEM_TX chip=')
        return dict(field.split('=',1)for field in line.split()[1:]if '='in field)
    def upload(self,data):
        proof=validate_waveform(data);state=self.info()
        if state.get('chip')!='ESP32-S3' or state.get('initialized')!='1' or state.get('running')!='0':raise RuntimeError('Require initialized, stopped ESP32-S3 TX')
        validate_waveform(data,int(state['max']),int(state['alignment']))
        self.command(f"LOAD {proof['samples']} {proof['crc']}",f"READY {len(data)}")
        self.serial.write(data);self.serial.flush();self.response('OK LOAD '+proof['crc'])
        applied=self.info()
        if applied.get('loaded')!='1' or applied.get('crc')!=proof['crc'] or int(applied['samples'])!=proof['samples']:raise RuntimeError('TX buffer readback mismatch')
        return dict(proof,applied=applied,rf_started=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['fetch','build','check','info','init','upload','start','stop','rate']);p.add_argument('--port');p.add_argument('--file',type=Path);p.add_argument('--channel',type=int,default=1);p.add_argument('--backoff-qdb',type=int,default=100);p.add_argument('--sample-rate',type=int,default=40000000);a=p.parse_args()
    if a.action=='fetch':return fetch()
    if a.action=='build':return build()
    if a.action in ('check','upload'):
        if not a.file:p.error('--file required')
        data=a.file.read_bytes();proof=validate_waveform(data)
        if a.action=='check':print(json.dumps(proof,indent=2));return
    if not a.port:p.error('--port required for hardware commands')
    if a.action=='init'and not(1<=a.channel<=13 and 0<=a.backoff_qdb<=120):p.error('Invalid channel/backoff')
    if a.action=='rate'and a.sample_rate not in (40000000,80000000):p.error('S3 rate must be40M or80M')
    client=TXLoader(a.port)
    try:
        if a.action=='info':result=client.info()
        elif a.action=='init':result=client.command(f'INIT {a.channel} {a.backoff_qdb}','OK INIT')
        elif a.action=='upload':result=client.upload(data)
        elif a.action=='rate':result=client.command(f'RATE {a.sample_rate}','OK RATE')
        else:result=client.command(a.action.upper(),'OK '+a.action.upper())
        print(json.dumps(result,indent=2))
    finally:client.close()
if __name__=='__main__':main()
