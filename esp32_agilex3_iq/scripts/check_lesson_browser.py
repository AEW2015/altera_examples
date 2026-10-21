#!/usr/bin/env python3
"""Offline Chromium smoke tests with mocked acquisition. Never uses UART/JTAG.
Optional development setup: pip install playwright; python -m playwright install chromium.
"""
import copy,json,os,sys,tempfile,threading,time,zlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'cyberether'),str(ROOT/'cyberether/tests')]
import numpy as np
import iq_bridge_lab as backend
from iq_bridge import Frame
from iq_lab_samples import load_sample,synthetic_snapshot,tone_measurements
from lesson_evidence import spectrum
from test_lesson_evidence import fir_state
import nios_ddc
from playwright.sync_api import sync_playwright


def fixture(lab,lesson):
    if lesson==3:
        f=fir_state();lab.settings.update(f['settings']);c=f['latest']['hamming']
    elif lesson<=2:
        a,_=load_sample('two-tone');payload=a.tobytes()
        raw=Frame(1,lab.settings['source'],7,len(a),16000000,(2407+5*lab.settings['channel'])*1000000,zlib.crc32(payload),256,0,len(payload),10,20,0,payload)
        c=backend.summarize(raw);c['acquisition']=lab.settings.copy()
    else:
        cfg=lab.settings
        a,spec=load_sample(cfg['ddc_input'])
        raw=synthetic_snapshot(cfg['ddc_input'],dict(source=3,samples=4096,rate=16000000,raw_crc=spec['crc32'],job=7))
        phase=nios_ddc.phase_increment(cfg['tuning_hz'],16000000)
        out=nios_ddc.reference(a,phase,cfg['decimation'],cfg['ddc_bypass'])['result']
        out,meters=nios_ddc.gain_reference(out,cfg['digital_gain_q8'],cfg['digital_gain_bypass'])
        meta=dict(phase=phase,rate=16000000,decimation=cfg['decimation'],bypass_flags=cfg['ddc_bypass'],digital_gain_q8=cfg['digital_gain_q8'],digital_gain_bypass=cfg['digital_gain_bypass'],output_samples=len(out),output_rate=16000000//cfg['decimation'],max_reference_error=0,gain_meters=meters)
        c=backend.summarize(raw)
        c.update(acquisition=cfg.copy(),ddc=meta,ddc_spectrum_db=spectrum(out.astype(float)/128),ddc_wave=(out[:256].astype(float)/128).tolist(),input_kind=cfg['ddc_input'],snapshot_crc_verified=True,transport_crc_verified=False,tone_measurements=tone_measurements(cfg['ddc_input'],a,out,meta))
    c['acquisition']=lab.settings.copy();c['captured_unix']=time.time()
    lab.latest={lab.settings['view']:c}
    lab.state.update(status='LIVE',completed=1,error=None)
    lab.state['telemetry']=dict(seq=3,received_unix=time.time(),r0_uart_Bps=42000,r1_uart_Bps=30000,host_iq_Bps=40000,capture_errors=0,radio_errors=0)
    lab.history.clear()
    for i in range(10):lab.history.append(dict(Bps=40000+i*100,time=time.time(),telemetry=dict(seq=i,r0_uart_Bps=42000+i*200,r1_uart_Bps=30000+i*100,host_iq_Bps=40000+i*180)))
    lab.publish()


def main():
    output=ROOT/'cyberether/run/lesson-browser-checks';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright()as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            for lesson in range(1,6):
                with tempfile.TemporaryDirectory()as directory,patch.object(backend,'LESSON',lesson):
                    lab=backend.Lab(Path(directory))
                    lab.state['fpga']=dict(stage_relative=f'fpga_hub/iq_bridge/vds_demo_0{lesson}_test',fpga_fir=lesson>=3,fpga_ddc=lesson>=4,fpga_gain_meter=lesson==5)
                    fixture(lab,lesson)
                    server=backend.Server(('127.0.0.1',0),backend.handler(lab,'offline-test-token','http://trusted'))
                    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    # Use the real handler and validation; authorize this test page's origin.
                    url=f'http://127.0.0.1:{server.server_port}'
                    server.RequestHandlerClass=backend.handler(lab,'offline-test-token',url)
                    try:
                        page.goto(url+'/#offline-test-token')
                        page.wait_for_function("document.getElementById('badge').textContent==='VERIFIED'")
                        assert page.locator('#evidence tr').count()>=5
                        # Deduplicate repeat polling of the same capture.
                        page.wait_for_timeout(1400)
                        assert page.evaluate('history.length')==1
                        page.get_by_role('button',name='Software preview',exact=True).click()
                        page.wait_for_function("document.getElementById('badge').textContent==='SOFTWARE PREVIEW'")
                        assert 'NOT RUN'in page.locator('#metrics').inner_text()
                        page.get_by_role('button',name='Return to hardware',exact=True).click()
                        page.wait_for_function("document.getElementById('badge').textContent==='VERIFIED'")
                        if lesson==2:
                            page.locator('#radio').select_option('1')
                            page.wait_for_function("document.getElementById('badge').textContent==='APPLYING'")
                            fixture(lab,lesson)
                            page.wait_for_function("document.getElementById('badge').textContent==='VERIFIED'")
                        if lesson>=3:
                            name={3:'FPGA two-tone check',4:'Show alias',5:'Clip 16×'}[lesson]
                            page.get_by_role('button',name=name,exact=True).click()
                            page.wait_for_function("document.getElementById('badge').textContent==='APPLYING'")
                            # No acquisition worker: acknowledge alone must not become a PASS.
                            assert page.locator('#badge').inner_text()=='APPLYING'
                            fixture(lab,lesson)if lesson!=3 else None
                        if lesson==3:
                            # Restore original matching fixture for the screenshot.
                            lab.settings['input_kind']='fpga-impulse';fixture(lab,lesson)
                        page.wait_for_function("document.getElementById('badge').textContent==='VERIFIED'")
                        page.screenshot(path=str(output/f'lesson-{lesson}-desktop.png'),full_page=True)
                        if lesson==5:
                            assert lab.latest['ddc']['ddc']['gain_meters']['gain_clips']>0
                            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.screenshot(path=str(output/'lesson-5-mobile.png'),full_page=True)
                        assert not errors,errors
                        print(f'Lesson {lesson}: verified evidence, preview separation, controls, bounded history and Chromium render PASS')
                    finally:
                        page.close();server.shutdown();server.server_close();thread.join(2)
        finally:browser.close()
    print('Offline screenshots:',output)

if __name__=='__main__':main()
