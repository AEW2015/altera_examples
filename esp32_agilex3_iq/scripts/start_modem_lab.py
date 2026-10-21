#!/usr/bin/env python3
"""Start/stop this checkout's Modem Lab page; no radio or FPGA image is changed."""
import argparse,json,os,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
from common import ROOT
from lessons import lan_ip
RUN=ROOT/'cyberether/run';META=RUN/'modem-lab-service.json'
def owned(meta):
    try:
        args=Path('/proc',str(meta['pid']),'cmdline').read_bytes().split(b'\0')
        return str(ROOT/'cyberether/modem_lab.py').encode()in args
    except (OSError,KeyError,ValueError):return False

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','stop','status'],default='start',nargs='?');p.add_argument('--host',default='0.0.0.0');p.add_argument('--port',type=int,default=8769);p.add_argument('--enable-fpga-action',action='store_true',help='Expose explicit symbol test; requires checkpoint06 and no other JTAG owner')
    a=p.parse_args();RUN.mkdir(exist_ok=True)
    try:meta=json.loads(META.read_text())
    except (OSError,ValueError):meta={}
    live=owned(meta)
    if a.action=='status':print(json.dumps(dict(running=live,**meta),indent=2));return
    if a.action=='stop':
        if live:
            os.kill(meta['pid'],signal.SIGTERM)
            for _ in range(100):
                if not owned(meta):break
                time.sleep(.05)
            if owned(meta):raise RuntimeError('Modem page is still stopping; no unrelated process was terminated')
        META.unlink(missing_ok=True);print('Modem page stopped; no FPGA image changed');return
    if live:print('Already running:',meta['url']);return
    with socket.socket()as check:check.bind((a.host,a.port))
    args=[sys.executable,str(ROOT/'cyberether/modem_lab.py'),'--host',a.host,'--port',str(a.port)]
    if a.enable_fpga_action:args.append('--enable-fpga-action')
    with (RUN/'modem-lab-service.log').open('a')as log:
        proc=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+12
    try:
        while time.monotonic()<deadline:
            if proc.poll()is not None:raise RuntimeError('Modem page exited; inspect cyberether/run/modem-lab-service.log')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health',timeout=1)as response:
                    if json.load(response).get('status')=='ready':break
            except (OSError,ValueError):time.sleep(.1)
        else:raise TimeoutError('Modem page did not become ready')
    except BaseException:proc.terminate();proc.wait(timeout=5);raise
    hostname=lan_ip()if a.host=='0.0.0.0'else a.host
    meta=dict(pid=proc.pid,url=f'http://{hostname}:{a.port}/',port=a.port,started_unix=time.time(),fpga_action_enabled=a.enable_fpga_action)
    META.write_text(json.dumps(meta,indent=2)+'\n');print(meta['url']);print('Python waveform simulation; optional FPGA symbol action is '+('enabled'if a.enable_fpga_action else'disabled'))
if __name__=='__main__':main()
