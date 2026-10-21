#!/usr/bin/env python3
"""Launch the native CyberEther lesson display and its single-owner acquisition service."""
import argparse,json,os,signal,socket,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTROL_PORT=int(os.getenv('ATUM_CONTROL_PORT','8768'));VIEWER_PORT=int(os.getenv('ATUM_VIEWER_PORT','8687'))

def listening(host,port):
    try:
        with socket.create_connection((host,port),.3):return True
    except OSError:return False

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default=os.getenv('ATUM_HOST','127.0.0.1'));p.add_argument('--run',type=Path,default=ROOT/'cyberether/run/iq-bridge-lab');p.add_argument('--replace-viewer',action='store_true');a=p.parse_args()
    a.run.mkdir(parents=True,exist_ok=True)
    if listening(a.host,VIEWER_PORT):
        if not a.replace_viewer:p.error('Viewer already running; use --replace-viewer for the known project viewer')
        candidates=[]
        for path in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                args=path.read_bytes().split(b'\0');exe=Path(os.readlink(path.parent/'exe')).name
            except(OSError,ValueError):continue
            if exe=='cyberether'and b'--remote-broker-port' in args and str(VIEWER_PORT).encode()in args and any(str(ROOT/'cyberether/graphs').encode()in x for x in args):
                candidates.append((int(path.parent.name),args,path.parent))
        if len(candidates)!=1:raise RuntimeError('Existing viewer ownership is ambiguous')
        pid,args,proc=candidates[0]
        env={}
        for entry in (proc/'environ').read_bytes().split(b'\0'):
            if entry.startswith((b'ATUM_',b'LD_PRELOAD=',b'GST_',b'APPIMAGE_')):
                k,_,v=entry.decode(errors='replace').partition('=');env[k]=v
        (a.run/'previous-viewer.json').write_text(json.dumps(dict(pid=pid,argv=[s.decode()for s in args if s],environment=env),indent=2)+'\n')
        (a.run/'previous-viewer.json').chmod(0o600);os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+15
        while listening(a.host,VIEWER_PORT):
            if time.monotonic()>deadline:raise RuntimeError('Previous viewer did not stop')
            time.sleep(.1)
    if listening(a.host,CONTROL_PORT):raise RuntimeError(f'Control port {CONTROL_PORT} is owned by another service')
    (a.run/'remote-join.json').unlink(missing_ok=True)
    worker_log=(a.run/'acquisition.log').open('a')
    worker=subprocess.Popen([str(ROOT/'.venv-notebooks/bin/python'),str(ROOT/'cyberether/iq_bridge_lab.py'),'--run',str(a.run),'--bind',a.host,'--port',str(CONTROL_PORT)],stdout=worker_log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+10
    while not listening(a.host,CONTROL_PORT):
        if worker.poll()is not None:raise RuntimeError('Acquisition service exited; inspect acquisition.log')
        if time.monotonic()>deadline:worker.terminate();raise RuntimeError('Acquisition service startup timeout')
        time.sleep(.1)
    env=dict(os.environ,ATUM_RF_ROOT=str(ROOT),ATUM_IQLAB_RUN=str(a.run),APPIMAGE_EXTRACT_AND_RUN='1',LD_PRELOAD=str(ROOT/'cyberether/runtime/register-bundled-plugins.so'),GST_PLUGIN_PATH_1_0='',GST_PLUGIN_SYSTEM_PATH_1_0='',GST_REGISTRY=str(a.run/'gstreamer-registry.bin'))
    args=[str(ROOT/'cyberether/runtime/CyberEther-linux-x64-v1.15.0.AppImage'),'--headless','--python-runtime','/usr/bin/python3','--dependency-policy','deny','--remote','--remote-auto-approve','on','--remote-broker-address',a.host,'--remote-broker-public-url',f'http://{a.host}:{VIEWER_PORT}','--remote-broker-port',str(VIEWER_PORT),'--remote-media-transport','tcp','--remote-media-port-range',os.getenv('ATUM_MEDIA_RANGE','40100-40103'),'--remote-media-address',a.host,'--remote-codec','vp8',str(ROOT/'cyberether/graphs/iq-bridge-lab.yml')]
    viewer=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
    (a.run/'processes.json').write_text(json.dumps(dict(worker_pid=worker.pid,viewer_pid=viewer.pid,started_unix=time.time(),graph=args[-1],control_url=f'http://{a.host}:{CONTROL_PORT}/',native_url=f'http://{a.host}:{VIEWER_PORT}/remote'),indent=2)+'\n')
    def stop(*_):
        worker.terminate()
        try:os.killpg(viewer.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with (a.run/'runtime.log').open('a')as log:
        for line in viewer.stdout:
            log.write(line);log.flush()
            if line.startswith('Join URL:'):
                f=a.run/'remote-join.json';f.write_text(json.dumps(dict(remote_viewer_url=line.partition('Join URL:')[2].strip()))+'\n');f.chmod(0o600)
    worker.terminate();worker.wait(timeout=30);viewer.wait();sys.exit(viewer.returncode)
if __name__=='__main__':main()
