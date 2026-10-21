#!/usr/bin/env python3
"""ID-tagged Nios V commands over JTAG UART; IQ stays inside FPGA processing."""
from __future__ import annotations
import argparse,fcntl,json,os,queue,signal,subprocess,threading,time,zlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from common import tool_command,tool_path,tool_exe
HAMMING=[-42,-177,-406,-352,669,2961,5846,7885,7885,5846,2961,669,-352,-406,-177,-42]
PROFILES={1:[2048]*16,2:HAMMING}
CABLE=os.getenv('ATUM_JTAG_CABLE','Atum A3 Nano [1-4.3-iface0]')
class NiosFir:
    def __init__(self,log:Path|None=None,pause_monitor=True):
        run=ROOT/'cyberether/run';run.mkdir(exist_ok=True)
        self.lock=(run/'nios-fir.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise RuntimeError('Another Nios FIR control client is active') from None
        self.paused=None
        if pause_monitor:self.pause_monitor()
        self.messages=queue.Queue();self.request=int(time.monotonic_ns()%1000000000);self.log=log.open('x') if log else None
        run=ROOT/'cyberether/run';run.mkdir(exist_ok=True)
        self.pidfile=run/f'nios-fir-{os.getpid()}.pid'
        shared=tool_path(self.pidfile)
        self.process=subprocess.Popen(tool_command(['stdbuf','-oL','-eL',str(tool_exe('juart-terminal')),'-q','-c',CABLE,'-d','1','-i','0','--no-quit-on-ctrl-d','--write-pid',shared]),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        def reader():
            for line in self.process.stdout:
                if self.log:self.log.write(line);self.log.flush()
                self.messages.put(line.strip())
            self.messages.put(None)
        self.thread=threading.Thread(target=reader,daemon=True);self.thread.start()
    def pause_monitor(self):
        manifest=ROOT/'cyberether/run/active-fpga.json'
        if not manifest.exists():return
        active=json.loads(manifest.read_text())
        if not active.get('fpga_fir'):return
        stage=ROOT/active['stage_relative'];metadata=stage/'run/live-monitor-process.json'
        if not metadata.exists():return
        meta=json.loads(metadata.read_text());pid=meta['pid'];cmdline=Path(f'/proc/{pid}/cmdline')
        script=str(stage/'monitor_log.py').encode()
        if not cmdline.exists() or script not in cmdline.read_bytes().split(b'\0'):return
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+8
        while cmdline.exists() and cmdline.read_bytes():
            if time.monotonic()>deadline:raise RuntimeError('Rate logger did not release JTAG')
            time.sleep(.05)
        self.paused=(stage,active['sha256'])
    def resume_monitor(self):
        if self.paused is None:return
        stage,digest=self.paused;manifest=ROOT/'cyberether/run/active-fpga.json'
        active=json.loads(manifest.read_text())
        if active['sha256']!=digest:return
        output=stage/'run'/('live-rate-log-auto-'+str(time.time_ns()))
        with (stage/'run/live-monitor-driver.log').open('a') as log:
            p=subprocess.Popen([str(ROOT/'.venv-notebooks/bin/python'),str(stage/'monitor_log.py'),'--seconds','0','--output',str(output)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (stage/'run/live-monitor-process.json').write_text(json.dumps(dict(pid=p.pid,output=str(output),started_unix=time.time(),stop_command=f'kill -TERM {p.pid}'),indent=2)+'\n')
        active['live_monitor_log']=str(output.relative_to(ROOT));manifest.write_text(json.dumps(active,indent=2)+'\n')
    def close(self):
        if self.pidfile.exists():
            shared=tool_path(self.pidfile)
            cleanup="""import os,signal,sys
from pathlib import Path
p=Path(sys.argv[1])
if p.exists():
 pid=int(p.read_text());q=Path('/proc')/str(pid)/'cmdline'
 if q.exists() and b'juart-terminal' in q.read_bytes() and sys.argv[2].encode() in q.read_bytes():os.kill(pid,signal.SIGTERM)
"""
            subprocess.run(tool_command(['python3','-c',cleanup,shared,CABLE]),capture_output=True)
        if self.process.stdin:self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.thread.join(timeout=2)
        if self.log:self.log.close()
        self.resume_monitor()
        fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def line(self,deadline):
        try:item=self.messages.get(timeout=max(.01,deadline-time.monotonic()))
        except queue.Empty:raise TimeoutError('Nios JTAG response timeout') from None
        if item is None:raise RuntimeError('JTAG terminal exited')
        return item
    def command(self,verb,*args,timeout=12):
        self.request+=1;ident=self.request
        self.process.stdin.write(f'FIR {ident} {verb}'+''.join(' '+str(a) for a in args)+'\n');self.process.stdin.flush()
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            parts=self.line(deadline).split(',')
            if len(parts)<4 or parts[:2]!=['FIR',str(ident)]:continue
            if parts[2]!='OK':raise RuntimeError('Nios: '+','.join(parts))
            values={key:int(value,16 if key.endswith('crc') or key=='bits' else 10) for key,value in (v.split('=',1) for v in parts[4:] if '=' in v)}
            return dict(id=ident,verb=parts[3],**values)
        raise TimeoutError(f'Nios did not acknowledge {verb}')
    def status(self):return self.command('STATUS')
    def commands(self,calls,timeout=12):
        """Bounded pipelined control writes; match every reply by request ID.

        This removes a JTAG polling round trip per small replay block. The
        existing command() API remains synchronous for ordinary controls.
        """
        calls=list(calls)
        if not 1<=len(calls)<=16:raise ValueError('Batch requires1..16commands')
        pending={};lines=[]
        for call in calls:
            verb,*args=call
            if not isinstance(verb,str) or not verb.isalnum() or any('\n' in str(a) or '\r' in str(a) for a in args):
                raise ValueError('One verb and single-line arguments required')
            self.request+=1;ident=self.request;pending[ident]=verb
            lines.append(f'FIR {ident} {verb}'+''.join(' '+str(a) for a in args)+'\n')
        self.process.stdin.write(''.join(lines));self.process.stdin.flush()
        deadline=time.monotonic()+timeout;results={}
        while len(results)<len(pending):
            if time.monotonic()>=deadline:raise TimeoutError('Batched Nios reply deadline exceeded')
            parts=self.line(deadline).split(',')
            if len(parts)<4 or parts[0]!='FIR':continue
            try:ident=int(parts[1])
            except ValueError:continue
            if ident not in pending:continue
            if ident in results or parts[2]!='OK' or parts[3]!=pending[ident]:
                raise RuntimeError('Invalid/failed/duplicate batched Nios reply: '+','.join(parts))
            values={key:int(value,16 if key.endswith('crc') or key=='bits' else 10) for key,value in (v.split('=',1) for v in parts[4:] if '=' in v)}
            results[ident]=dict(id=ident,verb=parts[3],**values)
        return [results[ident] for ident in pending]
    def wait(self,mask,timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            state=self.status()
            if state['state']&mask and not state['state']&8:return state
            time.sleep(.02)
        raise TimeoutError(('FPGA FIR state did not complete',state))
    def coefficients(self,values):
        values=list(values)
        if len(values)!=16 or any(not -32768<=v<=32767 for v in values):raise ValueError('Sixteen signed Q15 coefficients required')
        for i,value in enumerate(values):
            self.command('COEFF',i,value)
            actual=self.command('READCOEFF',i)['bits']
            if actual!=(value&65535):raise RuntimeError(('Coefficient readback',i,actual,value))
    def preset(self,profile=2):
        if profile not in PROFILES:raise ValueError('Profile must be 1 (boxcar) or 2 (Hamming)')
        result=self.command('PRESET',profile)
        for i,value in enumerate(PROFILES[profile]):
            if self.command('READCOEFF',i)['bits']!=(value&65535):raise RuntimeError('Preset readback mismatch')
        return result
    def run(self,mode=1):
        self.command('RUN',mode);return self.wait(4)
    def dump(self):
        meta=self.command('DUMP');raw=bytearray();filtered=bytearray();offset=0;deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            line=self.line(deadline);parts=line.split(',')
            if parts==['FIRDONE',str(meta['id'])]:break
            if len(parts)!=6 or parts[:2]!=['FIRDATA',str(meta['id'])]:continue
            start,n=int(parts[2]),int(parts[3]);a,b=bytes.fromhex(parts[4]),bytes.fromhex(parts[5])
            if start!=offset or not 1<=n<=32 or len(a)!=2*n or len(b)!=2*n:raise ValueError('FIR dump sequence/length')
            raw.extend(a);filtered.extend(b);offset+=n
        else:raise TimeoutError('FIR dump incomplete')
        if offset!=meta['samples'] or zlib.crc32(raw)!=meta['raw_crc'] or zlib.crc32(filtered)!=meta['filtered_crc']:raise ValueError('FIR paired-buffer CRC/length failure')
        meta.update(sample_format='ci8',output_origin='FPGA FIR II' if meta['mode'] else 'FPGA bypass copy',input_origin='FPGA test pattern' if meta['source']==3 else 'CRC-qualified physical ESP32 capture',processing_seconds=meta['cycles']/50000000,arithmetic='round nearest, ties toward positive infinity' if meta.get('round') else 'truncate toward negative infinity',coefficients_current=[self.command('READCOEFF',i)['bits'] for i in range(16)])
        meta['coefficients_current']=[v if v<32768 else v-65536 for v in meta['coefficients_current']]
        return meta,np.frombuffer(raw,np.int8).reshape(-1,2),np.frombuffer(filtered,np.int8).reshape(-1,2)

def fixed_reference(iq,coefficients,round_nearest=False):
    iq=np.asarray(iq,dtype=np.int64);coefficients=np.asarray(coefficients,dtype=np.int64)
    result=np.column_stack([np.convolve(iq[:,lane],coefficients)[:len(iq)] for lane in range(2)])
    return np.clip((result+(16384 if round_nearest else 0))>>15,-128,127).astype(np.int8)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['status','arm','run','lowpass','hamming','round','pair','test-impulse','test-tones','dump'])
    p.add_argument('--mode',type=int,choices=[0,1],default=1)
    p.add_argument('--output',type=Path)
    p.add_argument('--enable',type=int,choices=[0,1],default=1)
    a=p.parse_args()
    with NiosFir() as nios:
        if a.command=='status':print(json.dumps(nios.status(),indent=2))
        elif a.command=='arm':print(nios.command('ARM'))
        elif a.command=='run':print(nios.run(a.mode))
        elif a.command in ('lowpass','hamming'):print(nios.preset(1 if a.command=='lowpass' else 2))
        elif a.command=='round':print(nios.command('ROUND',a.enable))
        elif a.command=='pair':print(nios.command('PAIR',a.enable))
        elif a.command.startswith('test-'):
            print(nios.command('TEST',1 if a.command=='test-impulse' else 2));print(nios.wait(2))
        elif a.command=='dump':
            if a.output is None:p.error('--output required for dump')
            a.output.mkdir(parents=True,exist_ok=False);meta,raw,filtered=nios.dump()
            (a.output/'raw.ci8').write_bytes(raw.tobytes());(a.output/'filtered.ci8').write_bytes(filtered.tobytes());(a.output/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
