#!/usr/bin/env python3
"""Explicit physical-board retest of notebook program/start/progress and feature checks.

Run beside tools: python scripts/check_notebook_hardware.py 3 --host <LAN-IP>
Programs the selected checkpoint, runs its demo, saves ignored evidence, then
stops this checkout's demo to release UART/JTAG. Does not flash ESP32 firmware.
"""
import argparse,copy,json,os,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'cyberether')]
from lessons import lan_ip,stop_demo
from common import resolve_uart


def check_features(number,host):
    run=ROOT/'cyberether/run/iq-bridge-lab'
    token=(run/'control-token.txt').read_text().strip()
    base=f'http://{host}:'+os.getenv('ATUM_CONTROL_PORT','8768')
    def api(path,body=None):
        request=urllib.request.Request(base+'/api/'+path,data=json.dumps(body).encode()if body is not None else None,
            headers={'X-Lab-Token':token,'Content-Type':'application/json'})
        return json.load(urllib.request.urlopen(request,timeout=8))
    cases=[]
    def wait_result(name,body=None,route='control'):
        started=time.time() if body else 0
        if body:api(route,body)
        end=time.monotonic()+95;last={}
        while time.monotonic()<end:
            last=api('state');mode=last['settings']['view'];capture=last.get('latest',{}).get(mode,{})
            proof=api('evidence')
            if last.get('error'):raise RuntimeError(name+': '+last['error'])
            if capture.get('captured_unix',0)>started and proof['status']=='VERIFIED':
                result=dict(name=name,proof=proof,capture=capture,telemetry=last.get('telemetry'),image_sha256=last['fpga']['sha256'])
                cases.append(result);print('PASS physical hardware:',name,flush=True);return result
            time.sleep(.3)
        raise TimeoutError(name+': '+str(last.get('status'))+' / '+str(api('evidence').get('reason')))
    initial=wait_result('notebook initial acquisition')
    if number==1:
        for source in range(3):wait_result(f'radio {source} raw CI8 / CRC',dict(source=source,rate=16000000,samples=4096))
        wait_result('40 MS/s mode / 8192 sample frame',dict(source=0,rate=40000000,samples=8192))
    elif number==2:
        end=time.monotonic()+12
        while time.monotonic()<end:
            t=api('state').get('telemetry',{})
            if t.get('r0_uart_Bps',0)>0 and t.get('host_iq_Bps',0)>0 and time.time()-t.get('received_unix',0)<3:break
            time.sleep(.3)
        else:raise TimeoutError('Nios counters did not measure the active IQ transfers')
        cases.append(dict(name='active Nios UART / IQ payload rates',telemetry=t))
        print('PASS physical hardware: nonzero Nios UART and payload rates',flush=True)
        before=api('state').get('telemetry',{}).get('seq',0)
        api('control',dict(continuous=False));end=time.monotonic()+12
        while time.monotonic()<end:
            s=api('state');t=s.get('telemetry',{})
            if s['status']=='PAUSED'and t.get('seq',0)>=before+2 and time.time()-t.get('received_unix',0)<3:break
            time.sleep(.3)
        else:raise TimeoutError('Nios counter windows did not advance while paused')
        cases.append(dict(name='paused acquisition / advancing Nios counters',telemetry=t))
        print('PASS physical hardware: paused Nios counters advance',flush=True)
        wait_result('resume acquisition',dict(continuous=True))
    elif number==3:
        wait_result('FPGA two-tone / Hamming',dict(input_kind='fpga-tones',view='hamming'))
        wait_result('FPGA two-tone / Boxcar',dict(view='boxcar'))
        wait_result('FPGA impulse / truncate',dict(input_kind='fpga-impulse',round=False))
        wait_result('FPGA impulse / nearest',dict(round=True))
        wait_result('return to live RF / paired CRC',dict(input_kind='live',view='hamming',source=0))
        wait_result('live RF back to FPGA impulse',dict(input_kind='fpga-impulse'))
    elif number==4:
        reject=wait_result('two-tone FPGA DDC rejection',dict(ddc_input='two-tone',tuning_hz=500000,decimation=4,ddc_bypass=0))
        alias=wait_result('two-tone FPGA alias / filter bypass',dict(ddc_bypass=2))
        rejection=reject['capture']['tone_measurements']['tones'][1]['attenuation_db']
        assert rejection>20,rejection
        assert abs(alias['capture']['tone_measurements']['tones'][1]['attenuation_db'])<2
        wait_result('FPGA impulse / DDC FIR',dict(ddc_input='impulse',tuning_hz=0,decimation=1,ddc_bypass=1))
        wait_result('restore two-tone rejection',dict(ddc_input='two-tone',tuning_hz=500000,decimation=4,ddc_bypass=0))
    elif number==5:
        values={}
        for gain in (256,128,512,4096):
            r=wait_result(f'FPGA digital gain {gain/256:g}x',dict(digital_gain_q8=gain,digital_gain_bypass=False))
            values[gain]=r['capture']['ddc']['gain_meters']
        import math
        change=10*math.log10(values[512]['post_power']/values[256]['post_power'])
        assert abs(change-6.0206)<.05,change
        assert values[256]['gain_clips']==0 and values[4096]['gain_clips']>0
        print(f'PASS measured 2x gain: {change:.4f} dB; 16x clipped samples: {values[4096]["gain_clips"]}',flush=True)
    elif number==6:
        wait_result('RF Arcade overdrive scene',dict(scene='overdrive'),route='show')
    output=ROOT/'cyberether/run/notebook-hardware-retest';output.mkdir(parents=True,exist_ok=True)
    (output/f'checkpoint-{number}-evidence.json').write_text(json.dumps(dict(status='PASS_HARDWARE',checkpoint=number,tested_unix=time.time(),cases=cases),indent=2)+'\n')
    return len(cases)


def check_fir_notch():
    from fir_controls import FIRControls
    import numpy as np
    client=FIRControls();result=client.apply('notch-4mhz',input_kind='fpga-tones')
    capture=client.state()['latest']['custom'];raw,filtered=map(np.asarray,capture['waveform'])
    frequencies=np.array([-500000,4000000]);n=np.arange(len(raw))[16:]
    basis=np.exp(2j*np.pi*n[:,None]*frequencies/16000000)
    amplitudes=[]
    for a in (raw,filtered):
        amplitudes.append(abs(np.linalg.lstsq(basis,(a[:,0]+1j*a[:,1])[16:],rcond=None)[0]))
    attenuation=20*np.log10(np.maximum(amplitudes[0],1e-12)/np.maximum(amplitudes[1],1e-12))
    assert attenuation[1]>30,attenuation
    assert abs(attenuation[0])<1,attenuation
    output=ROOT/'cyberether/run/notebook-hardware-retest'
    (output/'fir-notch-evidence.json').write_text(json.dumps(dict(status='PASS_HARDWARE',result=result,
        tone_frequencies_hz=frequencies.tolist(),attenuation_db=attenuation.tolist(),measurement='Host sinusoid fit on FPGA raw/filtered data; first 16 startup samples excluded'),indent=2)+'\n')
    print('PASS physical FIR notch: +4 MHz attenuation',round(attenuation[1],2),'dB; wanted −0.5 MHz loss',round(attenuation[0],3),'dB',flush=True)


def check_filter_library():
    from fir_controls import FIRControls
    from fir_filters import CATALOG
    client=FIRControls();results=[]
    for name in CATALOG:
        result=client.apply(name,input_kind='fpga-tones')
        assert result['readback_verified']and result['max_reference_error']==0,result
        results.append(result);print('PASS physical coefficient reload:',name,flush=True)
    custom=[4096]*8+[0]*8
    results.append(client.apply(coefficients=custom,input_kind='fpga-impulse'))
    # Confirm the worker does not restore its old preset on the following capture.
    before=client.state()['completed'];end=time.monotonic()+25
    while time.monotonic()<end:
        state=client.state()
        if state['completed']>before:
            c=state['latest']['custom'];assert c['fir_coefficients_readback']==custom and c['max_reference_error']==0
            print('PASS custom coefficients persist across subsequent captures',flush=True);break
        time.sleep(.3)
    else:raise TimeoutError('No subsequent custom-filter capture')
    client._api('control',dict(continuous=False))
    results.append(client.apply('identity',input_kind='fpga-impulse'))
    client._api('control',dict(continuous=True))
    results.append(client.apply('notch-4mhz',input_kind='live'))
    output=ROOT/'cyberether/run/notebook-hardware-retest'
    (output/'filter-library-evidence.json').write_text(json.dumps(dict(status='PASS_HARDWARE',tested_unix=time.time(),results=results),indent=2)+'\n')
    return len(results)


def browser_capture(number,host,output):
    from playwright.sync_api import sync_playwright
    invite=json.loads((ROOT/'cyberether/run/iq-bridge-lab/control-invite.json').read_text())['url']
    with sync_playwright()as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(invite)
            if number<=5:
                page.wait_for_function("document.getElementById('badge').textContent==='VERIFIED'",timeout=45000)
                if number==3:
                    from fir_filters import CATALOG,coefficient_hash
                    def wait_filter(name,coefficients):
                        digest=coefficient_hash(coefficients)
                        page.wait_for_function("expected => state.settings.fir_filter===expected.name && state.latest.custom?.fir_coefficient_sha256===expected.hash && document.getElementById('badge').textContent==='VERIFIED' && proof.rows.some(r=>r.label==='Coefficient readback' && r.requested===expected.hash.slice(0,12) && r.applied===r.requested && r.ok)",arg=dict(name=name,hash=digest),timeout=45000)
                    previous=page.evaluate('state.settings.fir_filter')
                    page.locator('#choice').select_option('highpass')
                    assert page.evaluate('state.settings.fir_filter')==previous,'Preview changed the hardware'
                    page.locator('#apply-filter').click()
                    wait_filter('highpass',CATALOG['highpass']['coefficients'])
                    page.locator('#filter-editor summary').click()
                    page.locator('#filter-coefficients').fill('[1,2]')
                    page.locator('#preview-coefficients').click()
                    assert '16 signed Q15' in page.locator('#filter-pending').inner_text()
                    page.locator('#filter-coefficients').fill(json.dumps([4096]*8+[0]*8))
                    page.locator('#apply-coefficients').click()
                    wait_filter('custom',[4096]*8+[0]*8)
                    page.screenshot(path=str(output/'custom-filter-gui-live.png'),full_page=True)
                    page.locator('#choice').select_option('notch-4mhz');page.locator('#apply-filter').click()
                    wait_filter('notch-4mhz',CATALOG['notch-4mhz']['coefficients'])
                    print('PASS physical browser: preview separation, named/custom reload, validation and readback',flush=True)
            else:page.wait_for_function("document.getElementById('viewer').dataset.lessonReady==='true'",timeout=65000)
            page.screenshot(path=str(output/f'checkpoint-{number}-live.png'),full_page=True)
            assert not errors,errors
        finally:browser.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',type=int,choices=range(1,7));p.add_argument('--host',default=lan_ip());p.add_argument('--browser',action='store_true');p.add_argument('--filter-library',action='store_true',help='Also test every FIR example (checkpoint 3 only)');a=p.parse_args()
    if a.filter_library and a.checkpoint!=3:p.error('--filter-library requires checkpoint 3')
    import nbformat
    from nbclient import NotebookClient
    paths=sorted((ROOT/'notebooks').glob(f'{a.checkpoint:02d}_*.ipynb'))
    book=nbformat.read(paths[0],as_version=4)
    selected=[copy.deepcopy(c)for c in book.cells if c.cell_type=='code'and set(c.metadata.get('tags',[]))&({'setup','build','program','live'}|({'filter-library','filter-preview','filter-apply','filter-custom'}if a.checkpoint==3 else set()))]
    selected.append(nbformat.v4.new_code_cell(f'from check_notebook_hardware import check_features\nchecked_cases = check_features({a.checkpoint}, HOST)\nprint("Physical checks:", checked_cases)'))
    if a.checkpoint==3:selected.append(nbformat.v4.new_code_cell('from check_notebook_hardware import check_fir_notch\ncheck_fir_notch()'))
    if a.filter_library:selected.append(nbformat.v4.new_code_cell('from check_notebook_hardware import check_filter_library\nprint("Physical library checks:", check_filter_library())'))
    # Explicit host override after the authored configuration cell.
    selected.insert(1,nbformat.v4.new_code_cell(f'HOST = {a.host!r}'))
    test=nbformat.v4.new_notebook(cells=selected,metadata=book.metadata)
    class Observed(NotebookClient):
        messages=[]
        def process_message(self,msg,cell,cell_index):
            if msg['msg_type']in ('display_data','update_display_data'):
                text=msg['content'].get('data',{}).get('text/html','')
                if '<progress'in text:self.messages.append(dict(kind=msg['msg_type'],cell=cell_index,html=text))
            if msg['msg_type']=='stream':print(msg['content']['text'],end='',flush=True)
            return super().process_message(msg,cell,cell_index)
    output=ROOT/'cyberether/run/notebook-hardware-retest';output.mkdir(parents=True,exist_ok=True)
    client=Observed(test,timeout=240,kernel_name='atum-a3-iq',resources={'metadata':{'path':str(ROOT)}})
    try:
        client.execute(env=dict(os.environ,ATUM_UART=resolve_uart()))
        for tag in ('program','live'):
            index=next(i for i,c in enumerate(test.cells)if tag in c.metadata.get('tags',[]))
            updates=[m for m in client.messages if m['cell']==index]
            assert any(m['kind']=='update_display_data'for m in updates),'No live progress updates for '+tag
            assert 'DONE'in updates[-1]['html'],'No successful completion indicator for '+tag
        if a.browser:browser_capture(a.checkpoint,a.host,output)
        print('PASS checkpoint',a.checkpoint,'physical notebook flow; progress updates:',len(client.messages),flush=True)
    finally:
        nbformat.write(test,output/f'checkpoint-{a.checkpoint}-executed.ipynb')
        (output/f'checkpoint-{a.checkpoint}-progress.json').write_text(json.dumps(client.messages,indent=2)+'\n')
        stop_demo()

if __name__=='__main__':main()
