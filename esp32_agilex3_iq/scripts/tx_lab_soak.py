#!/usr/bin/env python3
"""Bounded three-mode endurance test. --transmit permits brief AMP/native jobs.

Never flashes/programs hardware. Stops on the first failed check; RF remains off
between rounds. PHASE is queried only: received phase/QAM quality is not claimed.
"""
import argparse,json,subprocess,sys,time
from pathlib import Path
from common import ROOT

def schedule(hours,interval_minutes):
    if not 0<hours<=6 or not 1<=interval_minutes<=60:raise ValueError('Use hours >0..6, interval 1..60 minutes')
    return [n*interval_minutes*60 for n in range(int((hours*3600-1)//(interval_minutes*60))+1)]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hours',type=float,default=3);p.add_argument('--interval-minutes',type=float,default=20)
    p.add_argument('--transmit',action='store_true');p.add_argument('--port',default='/dev/ttyUSB0')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    times=schedule(a.hours,a.interval_minutes)
    output=a.output.resolve();output.relative_to((ROOT/'cyberether/run').resolve());output.mkdir(mode=0o700,parents=True,exist_ok=False)
    report={'started_unix':time.time(),'hours':a.hours,'interval_minutes':a.interval_minutes,'transmit':a.transmit,'rounds':[],'state':'running',
            'scope':'Mode/endurance, sparse raw amplitude captures and native packet reception; no custom QAM or RF BER qualification'}
    def save():
        temp=output/'status.tmp';temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(output/'status.json')
    def command(row,name,script,*args):
        log=output/(name+'.log');start=time.time()
        with log.open('x') as stream:
            result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
        row.append({'name':name,'returncode':result.returncode,'started_unix':start,'elapsed_seconds':time.time()-start,'log':log.name});save()
        if result.returncode:raise RuntimeError(name+' failed; inspect '+log.name)
    def mode(row,name,selected):command(row,name,'tx_lab_control.py','--port',a.port,'--mode',selected)
    started=time.monotonic();save()
    try:
        for index,offset in enumerate(times):
            # Firmware TX is already off throughout these idle intervals.
            while time.monotonic()<started+offset:time.sleep(min(30,started+offset-time.monotonic()))
            steps=[];round_={'index':index,'started_unix':time.time(),'steps':steps};report['rounds'].append(round_);save()
            prefix=f'round-{index:03d}'
            mode(steps,prefix+'-phase','PHASE')
            mode(steps,prefix+'-amp','AMP')
            if a.transmit:
                base=['--transmit','--port',a.port,'--rx-gain',0,'--expect-mac','78:21:84:d4:4f:98']
                command(steps,prefix+'-amp-init','original_iq_control.py',*base,'--milliseconds',50,'--output',output/(prefix+'-amp-init.json'))
                time.sleep(3)
                target=output/(prefix+'-amp-train.json')
                command(steps,prefix+'-amp-train','original_iq_control.py',*base,'--milliseconds',30,'--level',24,'--train-period-us',64,'--output',target)
                proof=json.loads(target.read_text())
                if not proof.get('completed') or not proof.get('register_trial_qualified') or proof.get('cleanup_errors'):raise RuntimeError('AMP readback/cleanup failed')
            mode(steps,prefix+'-native','NATIVE')
            if a.transmit:
                command(steps,prefix+'-native-ota','wifi64_ota.py','--transmit','--port',a.port,'--channel',11,'--count',2,'--power',8,'--gap',2,'--run',(int(report['started_unix'])+index)&0xffffffff,'--output',output/(prefix+'-native.json'))
            mode(steps,prefix+'-off','AMP');round_['passed']=True;round_['finished_unix']=time.time();save()
        while time.monotonic()<started+a.hours*3600:
            time.sleep(min(30,started+a.hours*3600-time.monotonic()))
        report['state']='passed'
    except BaseException as error:
        report.update(state='stopped',error=str(error));save()
    finally:
        cleanup=[];report['cleanup']=cleanup
        try:mode(cleanup,'final-off','AMP')
        except BaseException as error:report['cleanup_error']=str(error);report['state']='stopped'
        report['finished_unix']=time.time();save()
    print(json.dumps(report,indent=2));return 0 if report['state']=='passed' else 2
if __name__=='__main__':raise SystemExit(main())
