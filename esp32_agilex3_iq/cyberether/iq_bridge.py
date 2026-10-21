#!/usr/bin/env python3
"""Direct IQB1 FPGA bridge. No host-to-FPGA IQ upload; exclusive serial owner.
Default hardware access is explicit via CLI. Importing this module performs no I/O.
"""
from __future__ import annotations
import argparse,collections,dataclasses,hashlib,json,struct,time,zlib,threading
from pathlib import Path
import numpy as np
import serial,os
COMMAND=struct.Struct('<4sBBHII')
HEADER=struct.Struct('<4sBBBB8IQQQ')
MAX_SAMPLES=16384
DEFAULT_PORT=os.getenv('ATUM_UART','/dev/serial/by-id/usb-TERASIC_Atum_A3_Nano_TRWJB3QN-if01-port0')
@dataclasses.dataclass
class Frame:
    kind:int; source:int; job:int; samples:int; rate:int; frequency:int; raw_crc:int
    capture_us:int; error:int; length:int; first_tick:int; last_tick:int; aux:int
    payload:bytes=b''
    def iq(self):
        if self.kind not in (1,6):raise ValueError('Capture frame required')
        return np.frombuffer(self.payload,np.int8).reshape(-1,2)
    def metadata(self):
        d=dataclasses.asdict(self);d.pop('payload');d.update(sample_format='ci8',payload_sha256=hashlib.sha256(self.payload).hexdigest(),
          origin='physical FPGA FIR output RAM' if self.kind==6 else 'physical FPGA direct capture RAM',capture_time_synchronized=False,
          frequency_and_rate_origin='host-configured; not RF-measured',ticks_origin='50MHz FPGA UART receipt clock',absolute_power_calibrated=False)
        if self.kind==6:
            descriptor=self.aux&0xffffffff
            d.update(original_raw_crc=self.aux>>32,fir_descriptor=descriptor,
                     fir_profile=descriptor&255 if descriptor!=1 else 1,
                     round_nearest=bool(descriptor&256) if descriptor!=1 else True,
                     fir_profile_namespace='legacy fixed Hamming' if descriptor==1 else 'reloadable-v1')
        return d

def encode_command(opcode,source=0,arg=0,job=0,value=0):
    if not 0<=source<=2:raise ValueError('Source must be0,1,2')
    if not 0<=opcode<=7:raise ValueError('Unknown command')
    body=COMMAND.pack(b'IQBC',opcode,source,arg,job,value)
    return body+struct.pack('<I',zlib.crc32(body))

def decode_header(header):
    if len(header)!=HEADER.size:raise ValueError('Header length')
    magic,version,kind,source,flags,*fields=HEADER.unpack(header)
    if magic!=b'IQB1' or version!=1 or flags or source>2 or kind not in(1,2,3,4,5,6):raise ValueError('Invalid IQB1 envelope')
    frame=Frame(kind,source,*fields)
    if kind in (1,6):
        if not 1<=frame.samples<=MAX_SAMPLES or frame.length!=2*frame.samples or frame.rate not in(16000000,40000000,80000000) or frame.error or frame.last_tick<frame.first_tick:
            raise ValueError('Invalid capture descriptor')
    elif kind==3:
        if not 0<frame.length<=127:raise ValueError('Invalid text packet')
    elif frame.length:raise ValueError('Control frame carries a payload')
    if kind==6:
        descriptor=frame.aux&0xffffffff
        if descriptor!=1 and ((descriptor&0xfffffe00)!=0x80010000 or (descriptor&255)>2):
            raise ValueError('Unknown FIR descriptor')
    return frame

def decode_frame(wire):
    if len(wire)<68:raise ValueError('Truncated IQB1 frame')
    f=decode_header(wire[:64])
    if len(wire)!=68+f.length or zlib.crc32(wire[:-4])!=int.from_bytes(wire[-4:],'little'):raise ValueError('IQB1 frame CRC/length failure')
    f.payload=wire[64:-4]
    if f.kind in (1,6) and zlib.crc32(f.payload)!=f.raw_crc:raise ValueError('Capture payload CRC failure')
    return f

class Bridge:
    def __init__(self,port=DEFAULT_PORT,baud=2000000,background=False):
        self.port=serial.Serial(port=None,baudrate=baud,timeout=.15,write_timeout=5,exclusive=True)
        self.port.dtr=False;self.port.rts=False;self.port.port=port;self.port.open()
        self.job=0;self.responses=collections.deque();self.resync_bytes=0;self.last_status=None
        self.port.reset_input_buffer()
        self._rx_background=background
        if background:
            self._rx_chunks=collections.deque();self._rx_size=0;self._rx_error=None;self._rx_cv=threading.Condition();self._rx_stop=threading.Event()
            self._rx_thread=threading.Thread(target=self._receive_bytes,daemon=True,name='iqb1-uart-receiver');self._rx_thread.start()
    def _receive_bytes(self):
        # Drain FTDI even while Nios/JTAG work is in progress. Parsing and CRC
        # checks remain on the caller; bounded buffering never drops bytes silently.
        while not self._rx_stop.is_set():
            try:
                data=self.port.read(min(65536,max(1,self.port.in_waiting)))
                if not data:continue
                with self._rx_cv:
                    if self._rx_size+len(data)>4*1024*1024:raise BufferError('IQB1 background RX exceeds 4 MiB; reconnect required')
                    self._rx_chunks.append(data);self._rx_size+=len(data);self._rx_cv.notify_all()
            except Exception as exc:
                if self._rx_stop.is_set():return
                with self._rx_cv:self._rx_error=exc;self._rx_cv.notify_all()
                return
    def close(self):
        if getattr(self,'_rx_background',False):
            self._rx_stop.set();self.port.cancel_read();self._rx_thread.join(timeout=1)
        self.port.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def next_job(self):self.job=(self.job+1)&0xffffffff;return self.job
    def exact(self,n,deadline):
        out=bytearray()
        if getattr(self,'_rx_background',False):
            with self._rx_cv:
                while len(out)<n:
                    if self._rx_error:raise self._rx_error
                    if self._rx_chunks:
                        chunk=self._rx_chunks.popleft();take=min(n-len(out),len(chunk));out.extend(chunk[:take]);self._rx_size-=take
                        if take<len(chunk):self._rx_chunks.appendleft(chunk[take:])
                    else:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise TimeoutError(f'IQB1 serial timeout: {len(out)}/{n} bytes')
                        self._rx_cv.wait(remaining)
            return bytes(out)
        while len(out)<n:
            if time.monotonic()>deadline:raise TimeoutError(f'IQB1 serial timeout: {len(out)}/{n} bytes')
            out.extend(self.port.read(n-len(out)))
        return bytes(out)
    def read_frame(self,timeout=8,on_capture_header=None):
        deadline=time.monotonic()+timeout;prefix=bytearray()
        while True:
            prefix.extend(self.exact(1,deadline))
            if prefix[-4:]==b'IQB1':break
            if len(prefix)>4:self.resync_bytes+=1;del prefix[0]
        header=b'IQB1'+self.exact(60,deadline);f=decode_header(header)
        if f.kind==1 and on_capture_header:on_capture_header(f)
        return decode_frame(header+self.exact(f.length+4,deadline))
    def send(self,op,source=0,arg=0,job=0,value=0):self.port.write(encode_command(op,source,arg,job,value))
    def control(self,op,source=0,value=0,timeout=5):
        job=self.next_job();self.send(op,source,job=job,value=value);deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            f=self.read_frame(timeout=max(.1,deadline-time.monotonic()))
            if f.kind==5:raise RuntimeError(f'FPGA error {f.error:#x}, job{f.job}')
            if f.job==job and f.kind in(2,4):self.last_status=f;return f
            self.responses.append(f)
        raise TimeoutError('FPGA control reply timeout')
    def status(self):
        f=self.control(0)
        return dict(host_command_errors=f.raw_crc,radio_framing_errors=f.capture_us,
          capture_errors=f.last_tick,text_drops=f.aux>>32,bank_ready=f.aux&3,armed=bool(f.aux&4),receiving=bool(f.aux&8),max_samples=f.samples)
    def idle_status(self):
        """Drain unsolicited text at an idle job boundary, retaining CRC validation."""
        state=self.status()
        if any(f.kind in (1,6)for f in self.responses):raise RuntimeError('Pending capture at idle drain; refusing to discard IQ')
        self.responses.clear()
        return state
    def set_host_baud(self,baud):
        if baud not in(2000000,4000000):raise ValueError('Qualified profiles are2M/4M')
        f=self.control(7,value=baud);assert f.kind==4
        self.port.baudrate=baud;time.sleep(.03)
        return self.status()
    def radio_write(self,source,text):
        data=text.encode('ascii') if isinstance(text,str) else bytes(text)
        if len(data)>96:raise ValueError('Radio command limit96bytes')
        self.port.write(b''.join(encode_command(1,source,arg=b)for b in data));self.port.flush()
    def wait_text(self,source,prefix,timeout=4):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            f=self.responses.popleft() if self.responses else self.read_frame(max(.1,deadline-time.monotonic()))
            if f.kind==5:raise RuntimeError(f'FPGA capture error {f.error:#x}')
            if f.kind==3 and f.source==source:
                text=f.payload.decode('ascii',errors='replace').strip()
                if text.startswith(prefix):return text
        raise TimeoutError(f'No radio response {prefix!r}')
    def radio_command(self,source,text,prefix=None,timeout=4):
        self.radio_write(source,text+'\n')
        return self.wait_text(source,prefix if prefix is not None else text.split()[0],timeout)
    def prepare_sdr(self,source=0,frequency_mhz=2417,rate=16000000):
        # Discover actual runtime mode at both supported radio UART rates.
        mode=None
        for baud in (115200,2000000):
            self.control(2,source,baud);self.responses.clear()
            for attempt in range(3):
                self.radio_write(source,'\nMODE?\n')
                try:mode=self.wait_text(source,'RF_MODE,',1.2);break
                except TimeoutError:continue
            if mode is not None:break
        if mode is None:raise RuntimeError('Radio mode not found; no reset/flash attempted')
        if not mode.startswith('RF_MODE,SDR,'):
            self.radio_write(source,'MODE SDR\n');time.sleep(.2)
            self.control(2,source,2000000);time.sleep(2)
        else:self.control(2,source,2000000)
        self.responses.clear()
        marker=f'SYNC {time.monotonic_ns()}'
        self.radio_write(source,'\nRELEASE\n'+marker+'\n');self.wait_text(source,marker,5)
        info=self.radio_command(source,'INFO','ESP32SDR ')
        self.radio_command(source,f'FREQ {frequency_mhz}','OK')
        self.control(4,source,rate);self.control(5,source,frequency_mhz*1000000)
        return info
    def submit(self,source,samples,rate,wait_ack=True):
        if not 1<=samples<=MAX_SAMPLES:raise ValueError('Unsupported sample count')
        if rate not in(16000000,40000000,80000000):raise ValueError('Unsupported rate')
        job=self.next_job();self.send(3,source,job=job,value=samples)
        if wait_ack:
            while True:
                f=self.read_frame()
                if f.kind==5:raise RuntimeError(f'FPGA arm error {f.error:#x}')
                if f.kind==2 and f.job==job:break
                self.responses.append(f)
        self.radio_write(source,f'CAP16 {samples} '+str({16000000:6,40000000:1,80000000:0}[rate])+'\n')
        return job
    def paired_capture(self,source=0,samples=16380,rate=16000000,timeout=12):
        """PAIR 1 must be selected through Nios first; one job owns both buffers."""
        job=self.submit(source,samples,rate);frames={};deadline=time.monotonic()+timeout
        while set(frames)!={1,6}:
            if time.monotonic()>=deadline:raise TimeoutError('Raw/filtered pair incomplete')
            f=self.responses.popleft() if self.responses else self.read_frame(max(.01,deadline-time.monotonic()))
            if f.kind==5:raise RuntimeError(f'FPGA paired capture error {f.error:#x}, job{f.job}')
            if f.kind not in (1,6):continue
            if (f.job,f.source,f.samples,f.rate)!=(job,source,samples,rate):raise ValueError('Pair capture association mismatch')
            if f.kind in frames:raise ValueError('Duplicate pair representation')
            frames[f.kind]=f
        raw,filtered=frames[1],frames[6]
        if (raw.frequency,raw.first_tick,raw.last_tick)!=(filtered.frequency,filtered.first_tick,filtered.last_tick):raise ValueError('Pair capture metadata mismatch')
        if filtered.aux>>32!=raw.raw_crc:raise ValueError('Pair raw provenance CRC mismatch')
        return raw,filtered
    def captures(self,count=10,source=0,samples=16380,rate=16000000,pipeline=True):
        if count<1:raise ValueError('Positive count required')
        expected=collections.deque([self.submit(source,samples,rate)])
        submitted=1;received=0
        while received<count:
            def next_capture(header):
                nonlocal submitted
                if pipeline and submitted<count:
                    expected.append(self.submit(source,samples,rate,wait_ack=False));submitted+=1
            if self.responses:
                f=self.responses.popleft()
                if f.kind==1:next_capture(f)
            else:f=self.read_frame(timeout=10,on_capture_header=next_capture)
            if f.kind==5:raise RuntimeError(f'FPGA capture error {f.error:#x}, job{f.job}')
            if f.kind!=1:continue
            if not expected or (f.job,f.source,f.samples,f.rate)!=(expected.popleft(),source,samples,rate):raise ValueError('Capture association mismatch')
            received+=1
            if not pipeline and submitted<count:
                expected.append(self.submit(source,samples,rate));submitted+=1
            yield f

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default=DEFAULT_PORT);p.add_argument('--host-baud',type=int,choices=[2000000,4000000],default=2000000);p.add_argument('--initial-host-baud',type=int,choices=[2000000,4000000],default=2000000);p.add_argument('--source',type=int,choices=[0,1,2],default=0);p.add_argument('--frequency',type=int,default=2417);p.add_argument('--rate',type=int,choices=[16,40,80],default=16);p.add_argument('--samples',type=int,default=16380);p.add_argument('--frames',type=int,default=20);p.add_argument('--sequential',action='store_true');p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    with Bridge(a.port,a.initial_host_baud)as b:
        if a.host_baud!=a.initial_host_baud:b.set_host_baud(a.host_baud)
        identity=b.prepare_sdr(a.source,a.frequency,a.rate*1000000);initial=b.status();rows=[];start=time.monotonic();last=start
        with(a.output/'captures.ci8').open('xb')as raw:
            for f in b.captures(a.frames,a.source,a.samples,a.rate*1000000,not a.sequential):
                raw.write(f.payload);now=time.monotonic();row=f.metadata();row.update(host_elapsed_s=now-start,host_interval_s=now-last);rows.append(row);last=now;print(f'Capture {len(rows)}/{a.frames}: {f.samples} IQ pairs, CRC PASS',flush=True)
        elapsed=time.monotonic()-start;final=b.status()
        for key in('host_command_errors','radio_framing_errors','capture_errors'):
            if final[key]!=initial[key]:raise RuntimeError(f'New FPGA error counter: {key}')
        report=dict(status='PASS',identity=identity,frames=len(rows),elapsed_s=elapsed,host_baud=a.host_baud,pipeline=not a.sequential,payload_bytes=a.frames*a.samples*2,payload_bytes_per_second=a.frames*a.samples*2/elapsed,initial=initial,final=final,resync_bytes=b.resync_bytes,captures=rows,scope='Real RF snapshots through direct physical FPGA RAM; no host IQ upload')
        (a.output/'metadata.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items()if k!='captures'},indent=2))
if __name__=='__main__':main()
