#!/usr/bin/env python3
"""Query or switch PMOD A's combined TX image. Never transmits or programs."""
import argparse,fcntl,json,time
from common import ROOT
from wifi64_ota import MonitorBridge
from wifi64_capture import artifact_guard

def fields(s):
    return dict(p.split('=',1) for p in s.split(',') if '=' in p)

def switch(bridge,mode=None):
    bridge.control(2,1,2000000)
    before=bridge.radio_command(1,'MODE?','TXLAB,MODE,')
    old=fields(before)
    if old.get('mode') not in ('AMP','NATIVE','PHASE'):raise RuntimeError('Unknown combined image')
    if mode is None:return {'before':before,'transmit':False}
    if mode not in ('AMP','NATIVE','PHASE'):raise ValueError('Unknown mode')
    # STOP can emit asynchronous completion lines. Poll common quiet readback.
    bridge.radio_write(1,'STOP\n')
    until=time.monotonic()+5
    while True:
        state=bridge.radio_command(1,'MODE?','TXLAB,MODE,')
        if fields(state).get('quiet')=='1':break
        if time.monotonic()>until:raise TimeoutError('TX mode failed to become quiet')
        time.sleep(.05)
    attempts=[]
    for attempt in range(2):
        bridge.radio_command(1,'MODE '+mode,'TXLAB,SWITCH,')
        prefix={'AMP':'OIQ,READY,','NATIVE':'WIFI64_TX,READY,','PHASE':'TX_PROBE_READY,'}[mode]
        try:
            ready=bridge.wait_text(1,prefix,4)
        except TimeoutError:
            # ROM UART-speed changes can lose the one-time boot announcement.
            ready='announcement missed; checking live mode readback'
        after=bridge.radio_command(1,'MODE?','TXLAB,MODE,')
        attempts.append({'ready':ready,'after':after})
        state=fields(after)
        if state.get('mode')==mode and state.get('quiet')=='1':
            return {'before':before,'ready':ready,'after':after,'attempts':attempts,'transmit':False}
        # The experimental certification PHY can reset into the cold-boot AMP
        # fallback after use. Retry once only from this verified RF-off state.
        if attempt==0 and state.get('mode')=='AMP' and state.get('quiet')=='1':
            continue
        raise RuntimeError('Mode/quiet readback mismatch: '+after)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=('AMP','NATIVE','PHASE'));p.add_argument('--port',default='/dev/ttyUSB0');a=p.parse_args()
    with (ROOT/'cyberether/run/rf-link-capture.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);artifact_guard()
        with MonitorBridge(a.port,background=True) as bridge:print(json.dumps(switch(bridge,a.mode),indent=2))
if __name__=='__main__':main()
