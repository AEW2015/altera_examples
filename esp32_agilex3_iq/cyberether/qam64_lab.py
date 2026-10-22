#!/usr/bin/env python3
"""Idle FPGA-only 64-QAM viewer. No transmit or auto-programming endpoints."""
import argparse,json,signal,subprocess,sys,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from modem_lab import require_modem_checkpoint

class Manager:
    def __init__(self,root=ROOT):
        self.root=Path(root);self.lock=threading.Lock();self.child=None;self.closed=False
        self.pointer=self.root/'cyberether/run/qam64-latest.json'
        self.job=dict(busy=False,status='idle')
        try:self.output=Path(json.loads(self.pointer.read_text())['output'])
        except (OSError,ValueError,KeyError):self.output=None
    def state(self):
        with self.lock:
            job=dict(self.job);out=self.output
        proof=None
        if out:
            try:proof=json.loads((out/'proof.json').read_text())
            except (OSError,ValueError):pass
        try:cp=require_modem_checkpoint(self.root);ready=True;reason='Checkpoint 06 build manifest matches selected image; actual block ID checked on Run.'
        except RuntimeError as exc:cp=None;ready=False;reason=str(exc)
        return dict(job=job,proof=proof,ready=ready,reason=reason,current_image=cp)
    def start(self,data):
        if data!={}:raise ValueError('This demo uses fixed 12/16/20 dB and at least 100,000 payload bits per point')
        require_modem_checkpoint(self.root)
        with self.lock:
            if self.closed or self.job['busy']:raise RuntimeError('Sweep already running or server closing')
            self.output=self.root/'cyberether/run'/('qam64-gui-'+str(time.time_ns()));self.output.mkdir(parents=True)
            self.pointer.write_text(json.dumps(dict(output=str(self.output))))
            command=[sys.executable,str(self.root/'scripts/check_qam64_sweep.py'),'--output',str(self.output)]
            self.job=dict(busy=True,status='running',started_at=time.time(),output=str(self.output))
            threading.Thread(target=self._run,args=(command,self.output),daemon=True).start()
            return dict(self.job)
    def _run(self,command,out):
        try:
            with (out/'run.log').open('w') as log:
                with self.lock:
                    if self.closed:return
                    self.child=subprocess.Popen(command,cwd=self.root,stdout=log,stderr=subprocess.STDOUT)
                    child=self.child
                code=child.wait(timeout=1800)
            proof=json.loads((out/'proof.json').read_text())
            if code or proof['status']!='PASS':raise RuntimeError(proof.get('error',f'Checker exit {code}'))
            with self.lock:self.job.update(busy=False,status='complete',completed_at=time.time())
        except Exception as exc:
            with self.lock:
                if self.child and self.child.poll() is None:self.child.terminate()
                self.job.update(busy=False,status='failed',error=str(exc))
        finally:
            with self.lock:self.child=None
    def close(self):
        with self.lock:
            self.closed=True;child=self.child
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='0.0.0.0');p.add_argument('--port',type=int,default=8773);a=p.parse_args();manager=Manager()
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,data,kind='application/json'):
            wire=data if isinstance(data,bytes) else json.dumps(data,allow_nan=False).encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(wire)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(wire)
        def do_GET(self):
            route=self.path.split('?')[0]
            if route=='/':self.reply(200,Path(__file__).with_suffix('.html').read_bytes(),'text/html; charset=utf-8')
            elif route=='/poster':self.reply(200,Path(__file__).with_name('qam64_poster.html').read_bytes(),'text/html; charset=utf-8')
            elif route=='/poster.png':
                picture=ROOT/'notebooks/screenshots/08_fpga_64qam_social.png'
                if picture.is_file():self.reply(200,picture.read_bytes(),'image/png')
                else:self.reply(404,dict(error='Example PNG not exported yet'))
            elif route=='/api/state':self.reply(200,manager.state())
            elif route=='/health':self.reply(200,dict(status='ready'))
            else:self.reply(404,dict(error='Not found'))
        def do_POST(self):
            if self.path!='/api/run':self.reply(404,dict(error='Not found'));return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=1024:raise ValueError('Invalid body length')
                self.reply(202,manager.start(json.loads(self.rfile.read(n))))
            except (ValueError,TypeError) as exc:self.reply(400,dict(error=str(exc)))
            except RuntimeError as exc:self.reply(409,dict(error=str(exc)))
        def log_message(self,*_):pass
    server=ThreadingHTTPServer((a.host,a.port),Handler)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:manager.close();server.server_close()
if __name__=='__main__':main()
