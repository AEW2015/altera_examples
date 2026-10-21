#!/usr/bin/env python3
"""Idle-by-default preamble demonstration. No TX API or TX commands."""
from __future__ import annotations
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import signal
import sys
import threading
import time
from rf_link_lab import CaptureManager,handler_for
from spi_pipeline_lab import SPIManager
ROOT=Path(__file__).resolve().parents[1]


class PreambleManager(SPIManager):
    def __init__(self,snapshot,root=ROOT,saved_iq=None,port=None):
        super().__init__(snapshot,root=root,port=port)
        self.saved_iq=Path(saved_iq).resolve() if saved_iq else None

    def state(self):
        state=super().state()
        state['preamble_paused']=state['recorded_checkpoint']!=8
        state['saved_available']=bool(self.saved_iq and self.saved_iq.is_file())
        return state

    def capture(self,data,synthetic=False):
        if not isinstance(data,dict) or set(data)-{'source'}:raise ValueError('Choose only a preamble input source')
        source='synthetic' if synthetic else data.get('source','saved')
        if source not in ('synthetic','saved','passive'):raise ValueError('Use synthetic, saved or passive input')
        if synthetic and data:raise ValueError('Synthetic replay takes no parameters')
        if self.state()['preamble_paused']:raise RuntimeError('Load checkpoint08 explicitly first')
        if source=='saved' and not (self.saved_iq and self.saved_iq.is_file()):raise ValueError('Start viewer with --saved-iq PATH to enable saved replay')
        with self.guard:
            if self.closed or self.job['busy']:raise RuntimeError('Another preamble job is active')
            out=self.root/'cyberether/run'/('preamble-gui-'+str(time.time_ns()))
            command=[sys.executable,str(self.root/'scripts/check_preamble.py'),'--output',str(out),'--snapshot',str(self.snapshot),'--symbol-us','10']
            command+=['--synthetic'] if source=='synthetic' else ['--input',str(self.saved_iq)] if source=='saved' else ['--passive']
            if self.port:command+=['--port',self.port]
            self.job=dict(busy=True,status='running',started_at=time.time(),output=str(out),requested=dict(source=source,tx=False))
            threading.Thread(target=self._experiment,args=(command,out,'preamble'),daemon=True).start()
            return dict(self.job)

    def qualify(self,data):raise ValueError('Use a bounded preamble replay or passive capture')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='0.0.0.0');p.add_argument('--port',type=int,default=8772)
    p.add_argument('--input',type=Path,default=ROOT/'cyberether/run/preamble-state.json');p.add_argument('--saved-iq',type=Path);p.add_argument('--uart');a=p.parse_args()
    manager=PreambleManager(a.input,saved_iq=a.saved_iq,port=a.uart);base=handler_for(manager)
    class Handler(base):
        def do_GET(self):
            if self.path.split('?')[0]=='/':self.reply(200,Path(__file__).with_suffix('.html').read_bytes(),'text/html; charset=utf-8')
            else:super().do_GET()
    server=ThreadingHTTPServer((a.host,a.port),Handler)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:manager.close();server.server_close()


if __name__=='__main__':main()
