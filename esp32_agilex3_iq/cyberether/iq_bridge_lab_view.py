"""CyberEther presentation for the IQ bridge lab. Plots are measured snapshots, not generators."""
import json,math,os,tarfile,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
RUN=Path(os.getenv('ATUM_IQLAB_RUN',str(ROOT/'cyberether/run/iq-bridge-lab')))
BG='#0b121e';CARD='#142234';LINE='#2b4058';INK='#e7f0ff';MUTED='#99afc9';CYAN='#52dfdd';GOLD='#ffc56a';GREEN='#75dfa4';RED='#ff9292'
W,H=1800,1000

def font(n):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',n)
def text(d,x,y,s,n=20,color=INK):d.text((x,y),str(s),font=font(n),fill=color)
def card(d,box,title):d.rounded_rectangle(box,12,fill=CARD,outline=LINE,width=2);text(d,box[0]+18,box[1]+13,title,22,CYAN)
def short(s,n=16):return str(s)[:n]
def plot(d,box,series,labels,title,xlabel,ylim=None,scatter=False,primary_on_top=False):
    card(d,box,title);l,t,r,b=box;l+=65;t+=62;r-=24;b-=47
    vals=[float(v)for row in series for v in (np.asarray(row).flatten() if scatter else row)]
    if ylim:lo,hi=ylim
    else:
        lo,hi=min(vals,default=-1),max(vals,default=1)
        pad=max(.5,(hi-lo)*.12);lo-=pad;hi+=pad
    for tick in range(5):
        y=t+(b-t)*tick/4;d.line((l,y,r,y),fill=LINE);text(d,l-60,y-10,f'{hi-(hi-lo)*tick/4:.0f}',14,MUTED)
    traces=list(zip(series,labels,(CYAN,GOLD)))
    if primary_on_top:traces.reverse()
    for row,label,color in traces:
        if scatter:
            for i,q in row:
                x=l+(i-lo)/(hi-lo)*(r-l);y=b-(q-lo)/(hi-lo)*(b-t)
                d.ellipse((x-2,y-2,x+2,y+2),fill=color)
        else:
            pts=[(l+k*(r-l)/max(1,len(row)-1),b-min(1,max(0,(v-lo)/(hi-lo)))*(b-t))for k,v in enumerate(row)]
            if len(pts)>1:d.line(pts,fill=color,width=2)
    text(d,l,box[3]-30,xlabel,16,MUTED)
    text(d,box[2]-310,box[1]+18,' / '.join(labels),16,GOLD)

def pipeline(d,mode):
    nodes=[('ESP32','2.4 GHz RF / ADC'),('UART + CRC','CI8 · 2 Mbaud'),('FPGA RAM','Frozen raw snapshot'),('FIR II DSP',{'raw':'BYPASS','boxcar':'16-tap boxcar','hamming':'16-tap Hamming'}[mode]),('Quantize / clip','Q15 → CI8'),('Host viewer','Plot + reference')]
    for i,(label,sub)in enumerate(nodes):
        x=28+i*294;active=not(mode=='raw'and i in(3,4));c=CYAN if active else MUTED
        d.rounded_rectangle((x,91,x+270,178),10,fill=CARD,outline=c,width=2)
        text(d,x+14,104,label,22,c);text(d,x+14,140,sub,17,MUTED)
        if i<5:d.polygon([(x+276,128),(x+289,135),(x+276,142)],fill=c)

def usage(d,fpga,y=916):
    resources=fpga.get('resources',{})
    for i,(key,total,label)in enumerate((('ALMs',45800,'ALMs'),('M20Ks',353,'RAM blocks'),('DSP_reported',368,'Quartus DSP blocks'))):
        x=32+i*570;used=resources.get(key,0);pct=used/total
        text(d,x,y,f'{label}  {used:,}/{total:,}  ·  {pct:.0%}',18,INK)
        d.rounded_rectangle((x,y+30,x+510,y+41),5,fill=LINE)
        d.rounded_rectangle((x,y+30,x+max(6,510*pct),y+41),5,fill=CYAN)
    text(d,32,973,'Compiled allocation · loaded checkpoint image · these bars are not live DSP activity'if os.getenv('ATUM_LESSON','0')!='0'else'Compiled allocation · same image for every lesson · these bars are not live DSP activity',16,MUTED)

def design_rows():
    rows=[]
    for name,stage in [('Raw bridge','01_raw'),('Nios V monitor','02_nios'),('FIR II','03_fir'),('DDC','04_ddc')]:
        try:
            v=json.loads((ROOT/'fpga_hub/iq_bridge'/('vds_demo_'+stage)/'BUILD_RESULT.json').read_text())
            rows.append((name,v['resources'],v['sha256'],False))
        except (OSError,ValueError,KeyError):pass
    return rows
HISTORY=design_rows()

def render(state,view=None):
    view=view or state.get('settings',{}).get('view','hamming');image=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(image)
    names={'raw':'RAW IQ BRIDGE','boxcar':'BOXCAR FIR','hamming':'HAMMING FIR','ddc':'TUNE / FILTER / DECIMATE','compare':'COMPARE DESIGNS'}
    text(d,28,18,names.get(view,view),32,CYAN)
    status=state.get('status','WAITING');text(d,1160,25,status,23,GREEN if status=='LIVE'else GOLD)
    text(d,1390,27,f"Results  {state.get('completed',0)}",20,MUTED)
    if view=='compare':
        fpga=state.get('fpga',{});rows=HISTORY+[('FIR + DDC + gain'if fpga.get('fpga_gain_meter')else'FIR + DDC + UART'if fpga.get('fpga_ddc')else'FIR + paired UART',fpga.get('resources',{}),fpga.get('sha256',''),True)]
        for i,(name,res,sha,active)in enumerate(rows):
            y=104+i*110;card(d,(28,y,1772,y+96),name+('  ·  LOADED NOW'if active else'  ·  HISTORICAL FIT'))
            for j,(key,total,label)in enumerate((('ALMs',45800,'ALM'),('M20Ks',353,'RAM'),('DSP_reported',368,'DSP'))):
                x=620+j*350;used=res.get(key,0);text(d,x,y+20,f'{label}  {used:,}',24)
                d.rounded_rectangle((x,y+59,x+290,y+74),5,fill=LINE)
                d.rounded_rectangle((x,y+59,x+max(5,290*used/total),y+74),5,fill=CYAN if active else'#55728c')
            text(d,48,y+72,short(sha),17,MUTED)
        card(d,(28,669,1772,868),'One current image · runtime DSP lessons')
        text(d,65,724,'RAW  →  transport only             BOXCAR  →  smoothing             HAMMING  →  frequency rejection',24,GOLD)
        for j,mode in enumerate(('raw','boxcar','hamming')):
            capture=state.get('latest',{}).get(mode);x=65+j*560
            if capture:
                rate=1/max(capture['elapsed_seconds'],1e-9);stamp=time.strftime('%H:%M:%S',time.localtime(capture['captured_unix']))
                text(d,x,768,f'{rate:.2f} cap/s · {capture["payload_Bps"]/1000:.1f} kB/s · {stamp}',19,CYAN)
            else:text(d,x,768,'No measurement yet',19,MUTED)
        text(d,65,808,'Last measured capture · raw bytes for Raw; both buffers for FIR · setup time excluded',19,MUTED)
        text(d,65,841,'Next: magnitude / energy  →  trigger  →  event buffer   [planned]',18,MUTED)
        text(d,32,882,'Historical rows show fit results; selecting a lesson does not load a historical bitfile.',18,MUTED)
        usage(d,fpga);return image
    if view=='ddc':return render_ddc(state,image,d)
    pipeline(d,view)
    latest=state.get('latest',{});capture=latest.get(view)
    if view=='raw'and capture is None and latest:
        capture=max(latest.values(),key=lambda v:v.get('captured_unix',0))
    if capture is None:
        card(d,(28,220,1772,860),'Waiting for a physical capture')
        text(d,70,320,'Select this lesson using the browser tabs. Hardware configuration applies to the next capture.',26,MUTED)
        if state.get('error'):text(d,70,390,state['error'][:110],22,RED)
        usage(d,state.get('fpga',{}));return image
    a=capture['raw'];age=max(0,time.time()-capture['captured_unix']);filtered=view!='raw'and capture.get('filtered')is not None
    settings=state.get('settings',{});current=a['source']==settings.get('source',a['source']) and a['frequency']==(2407+5*settings.get('channel',2))*1000000
    requested=capture.get('acquisition',{})
    current=current and all(requested.get(k)==settings.get(k)for k in ('rate','samples','gain_mode','gain_code'))
    if filtered:current=current and capture['round_nearest']==settings.get('round',True)
    label='LIVE SNAPSHOT'if current and age<5 and state.get('status')not in('OFFLINE','PAUSED')else'HELD SNAPSHOT'
    text(d,30,194,f"{label} · {age:.1f}s old · {capture['source_name']} · job {a['job']} · {a['frequency']/1e6:g} MHz",20,GREEN if label=='LIVE SNAPSHOT'else GOLD)
    text(d,1150,194,f"{a['samples']:,} samples · {a['rate']/1e6:g} MS/s configured",20,MUTED)
    waves=capture['waveform'][:2 if filtered else 1]
    wave_i=[[p[0]for p in row]for row in waves]
    wave_limit=max(4,math.ceil(max((abs(v)for row in wave_i for v in row),default=1)*1.15))
    scatter_rows=capture['scatter'][:2 if filtered else 1]
    scatter_limit=max(4,math.ceil(max((abs(v)for row in scatter_rows for pair in row for v in pair),default=1)*1.1))
    spectra=capture['spectra_db'][:2 if filtered else 1]
    peak=max(max(row)for row in spectra);floor=max(-110,min(float(np.percentile(spectra,10))-8,peak-50))
    plot(d,(28,235,880,505),wave_i,['Raw I','FPGA FIR I']if filtered else['Raw I'],'I waveform · shared scale',f"Time: 0–{len(waves[0])/a['rate']*1e6:.1f} µs · I8 counts",(-wave_limit,wave_limit))
    plot(d,(904,235,1772,505),scatter_rows,['Raw','FPGA FIR']if filtered else['Raw'],'IQ scatter · no demodulation','I8 →   /   Q8 ↑',(-scatter_limit,scatter_limit),True)
    plot(d,(28,529,1152,865),spectra,['Raw','FPGA FIR']if filtered else['Raw'],'Spectrum · HOST display FFT',f"Baseband: −{a['rate']/2e6:g} to +{a['rate']/2e6:g} MHz · dB re 1 CI8 unit",(floor,peak+5))
    card(d,(1176,529,1772,865),'Physical result checks')
    rows=[('IQB1 wire / payload CRC','PASS'),('Capture payload rate',f"{capture['payload_Bps']/1000:.1f} kB/s"),('FIR / reference error',str(capture['max_reference_error'])if filtered else'Not applied'),('FPGA output clips',str(capture['clips'])if filtered else'Not applied'),('Arithmetic',('Nearest · ties +∞'if capture['round_nearest']else'Truncate')if filtered else'Raw CI8'),('ADC rail hits',f"{capture.get('adc_rail_percent',0):.2f}%")]
    for i,(label,value)in enumerate(rows):text(d,1196,582+i*40,label,18,MUTED);text(d,1502,582+i*40,value,18,GREEN if value in('PASS','0')else INK)
    text(d,30,881,f"Burst: {capture.get('nominal_burst_us',0):.1f} µs nominal / {a.get('capture_us',0)} µs firmware · "+('FIR: FPGA · 'if filtered else'')+'FFT/reference/rail counts: host',19,MUTED)
    usage(d,state.get('fpga',{}));return image

class IQBridgeLabSource:
    def __init__(self):self.last_render=0.;self.frame=None
    def compute(self,ctx,skip):
        if time.monotonic()-self.last_render<(.25 if os.getenv('ATUM_DEMO_NIGHT')=='1'else .5):time.sleep(.03);return skip
        try:state=json.loads((RUN/'state.json').read_text())
        except(OSError,ValueError):state=dict(status='WAITING',settings=dict(view='hamming'))
        if os.getenv('ATUM_DEMO_NIGHT')=='1':
            if not hasattr(self,'arcade'):
                from demo_night_view import Arcade
                self.arcade=Arcade()
            frame=self.arcade.render(state)
        else:frame=render_focus(state)
        self.frame=np.asarray(frame,np.float32)/255.;ctx.outputs[0][...]=self.frame
        self.last_render=time.monotonic();return None
    def close(self):pass

def render_ddc(state,image,d):
    c=state.get('latest',{}).get('ddc');flags=c['ddc']['bypass_flags']if c else state['settings'].get('ddc_bypass',0);m=c['ddc']['decimation']if c else state['settings'].get('decimation',4)
    nodes=[('FPGA test generator'if c and c['raw']['source']==3 else'ESP32 RF / ADC','Synthetic CI8 snapshot'if c and c['raw']['source']==3 else'CI8 frozen snapshot'),('NCO + mixer','BYPASS'if flags&1 else'Complex frequency shift'),('I / Q FIR II','BYPASS'if flags&2 else'127 taps · Q15'),('Decimator',f'Keep every {m}'if m!=1 else'BYPASS · keep every 1'),('Gain + meters',('BYPASS · power active'if c['ddc'].get('digital_gain_bypass',True)else f"{c['ddc']['digital_gain_q8']/256:g}× · saturate / measure")if c else'FPGA digital levels'),('CI16 RAM','FPGA result + CRC'),('Host readback','JTAG · plots / reference')]
    if not state.get('fpga',{}).get('fpga_gain_meter',True):
        nodes.pop(4)
    stride=(W-56)//len(nodes)
    for i,(title,sub)in enumerate(nodes):
        color=MUTED if (i==1 and flags&1)or(i==2 and flags&2)or(i==3 and m==1)else CYAN
        x=28+i*stride;d.rounded_rectangle((x,91,x+stride-24,178),10,fill=CARD,outline=color,width=2);text(d,x+14,104,title,19,color);text(d,x+14,140,sub,15,MUTED)
        if i<len(nodes)-1:d.polygon([(x+stride-18,128),(x+stride-5,135),(x+stride-18,142)],fill=CYAN)
    c=state.get('latest',{}).get('ddc')
    if not c:
        card(d,(28,220,1772,865),'Waiting for a measured FPGA DDC result')
        text(d,65,320,'Capture → freeze → tune / filter / decimate → JTAG download → exact reference check',24,MUTED)
        if state.get('error'):text(d,65,390,state['error'][:110],22,RED)
        usage(d,state.get('fpga',{}));return image
    meta=c['ddc'];a=c['raw'];age=max(0,time.time()-c['captured_unix']);cfg=c['acquisition'];req=state['settings']
    current=all(cfg.get(k)==req.get(k)for k in('source','channel','rate','samples','gain_mode','gain_code','tuning_hz','decimation','ddc_bypass','ddc_input','digital_gain_q8','digital_gain_bypass'))
    label='LIVE RESULT'if age<20 and current and state['status']not in('PAUSED','OFFLINE')else'HELD RESULT'
    text(d,30,194,f"{label} · {c['source_name']} · input {c.get('input_id','')[-10:]} · {'REPLAY'if c.get('snapshot_reused')else'NEW INPUT'}",20,GREEN if label=='LIVE RESULT'else GOLD)
    phase=meta['phase'];tune=(phase if phase<2**31 else phase-2**32)*meta['rate']/2**32
    spectra=[c['spectra_db'][0],c['ddc_spectrum_db']];peak=max(max(row)for row in spectra);floor=max(-110,min(float(np.percentile(spectra,10))-8,peak-60));limits=(floor,peak+5)
    ref=state.get('reference');compatible=bool(ref and c.get('input_id')==ref.get('input_id')and meta['output_rate']==ref['ddc']['output_rate'])
    if compatible:
        combined=spectra+[ref['ddc_spectrum_db']];peak=max(max(row)for row in combined);floor=max(-110,min(float(np.percentile(combined,10))-8,peak-60));limits=(floor,peak+5)
    if c.get('input_kind')=='impulse':
        plot(d,(28,235,880,540),[[p[0]for p in c['waveform'][0]]],['FPGA input I'],'Impulse · actual FPGA input','Input sample index 0–255')
        rows=[[p[0]for p in c['ddc_wave']]];labels=['FPGA DDC I / 128']
        if compatible:rows.append([p[0]for p in ref['ddc_wave']]);labels.append('Pinned')
        plot(d,(904,235,1772,540),rows,labels,'Impulse response · actual FPGA output','Output sample index 0–255 · CI8-equivalent counts')
    else:
        plot(d,(28,235,880,540),[spectra[0]],['FPGA test CI8'if a['source']==3 else'Raw CI8'],'Before · HOST display FFT',f"Baseband −{a['rate']/2e6:g} … +{a['rate']/2e6:g} MHz",limits)
        rows=[spectra[1]];labels=['Current']
        if compatible:rows.append(ref['ddc_spectrum_db']);labels.append('Pinned')
        plot(d,(904,235,1772,540),rows,labels,'After / pinned · HOST steady FFT'if c.get('input_kind')in ('two-tone','single-tone')else'After / pinned · HOST display FFT',f"Baseband −{meta['output_rate']/2e6:g} … +{meta['output_rate']/2e6:g} MHz · CI8-equivalent dB",limits,primary_on_top=True)
    card(d,(28,564,880,865),'FPGA digital gain / power meters · uncalibrated')
    def level(v):return '−∞'if v is None else f'{v:+.2f}'
    gm=meta.get('gain_meters',{})
    rows=[('Digital translation','Mixer bypassed'if meta['bypass_flags']&1 else f'{tune/1e6:+.3f} MHz → DC'),
        ('Output / nominal rate',f"{meta['output_samples']} pairs @ {meta['output_rate']/1e6:g} MS/s"),
        ('Digital gain','BYPASS'if meta.get('digital_gain_bypass',True)else f"{meta['digital_gain_q8']/256:g}× · round + saturate"),
        ('Mean dBFS · before → after',f"{level(meta.get('pre_mean_dbfs'))} → {level(meta.get('post_mean_dbfs'))}"),
        ('Peak dBFS · before → after',f"{level(meta.get('pre_peak_dbfs'))} → {level(meta.get('post_peak_dbfs'))}"),
        ('Gain-clipped / measured pairs',f"{gm.get('gain_clips',0)} / {gm.get('meter_samples',0)}"),
        ('Pre-gain CI16 rail pairs',str(gm.get('pre_rails',0))),
        ('FPGA processing time',f"{meta['processing_seconds']*1000:.2f} ms")]
    for i,(label,value)in enumerate(rows):text(d,48,610+i*29,label,18,MUTED);text(d,425,610+i*29,value,18,RED if i==5 and gm.get('gain_clips')else INK)
    card(d,(904,564,1772,865),'Capture / processing checks')
    rows=[('FPGA fixture + JTAG CRCs'if a['source']==3 else'Raw UART + JTAG payload CRCs','PASS'),('Raw byte-for-byte provenance','PASS'),('FPGA samples + meter reference'if meta.get('gain_meter_available',True)else'FPGA sample reference',str(meta['max_reference_error'])+' LSB error'),('Mixer / filter clipped pairs',f"{meta['mixer_clips']} / {meta['filter_clips']}"),('Input identity / age',f"{'SYNTHETIC'if a['source']==3 else'RF snapshot'} · {max(0,time.time()-c.get('input_created_unix',c['captured_unix'])):.0f}s"),('Pinned comparison','Same input / rate'if compatible else'Different input / rate'if ref else'Not pinned')]
    for i,(label,value)in enumerate(rows):text(d,924,614+i*37,label,18,MUTED);text(d,1310,614+i*37,value,18,GREEN if value in('PASS','0 LSB error')else INK)
    meter=c.get('tone_measurements');tones=meter.get('tones',[])if meter else[]
    if len(tones)>1:footer=f"HOST tone meter (startup excluded): desired gain {-tones[0]['attenuation_db']:+.2f} dB · interferer rejection {tones[1]['attenuation_db']:.1f} dB · aliases to {tones[1]['output_hz']/1e6:+.3f} MHz"
    elif tones:footer=f"HOST tone meter (startup excluded): tone at {tones[0]['output_hz']/1e6:+.3f} MHz · gain {-tones[0]['attenuation_db']:+.2f} dB"
    else:footer='DSP: FPGA · FFT / reference: host · '+('Fresh RF burst each result'if c.get('input_kind')=='live'else'Replay input unchanged until New snapshot')+' · JTAG readback'
    text(d,30,881,footer,19,MUTED)
    usage(d,state.get('fpga',{}));return image


def render_focus(state):
    lesson=int(os.getenv('ATUM_LESSON','0'))
    if lesson==2:
        image=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(image)
        text(d,28,20,'2 · NIOS V TRANSFER MONITOR',32,CYAN)
        telemetry=state.get('telemetry',{});age=time.time()-telemetry.get('received_unix',0)
        text(d,1050,25,f"{state.get('status','WAITING')} · counter age {age:.1f}s"if telemetry else'Waiting for JTAG UART counters',20,GREEN if age<3 else GOLD)
        card(d,(28,90,1772,200),'Sample data stays on UART · Nios reads passive FPGA counters')
        text(d,55,142,'ESP32 → FPGA capture RAM → host UART       Counters → Avalon-MM → Nios V → JTAG UART',25)
        keys=[('r0_uart_Bps','Radio UART B/s'),('host_uart_Bps','Host UART B/s'),('host_iq_Bps','IQ payload B/s'),('host_captures','Captures / window')]
        for j,(key,label)in enumerate(keys):
            x=28+j*440;card(d,(x,225,x+420,385),label);text(d,x+25,290,f"{telemetry.get(key,'—'):,}"if isinstance(telemetry.get(key),int)else'—',38)
        windows={}
        for h in state.get('history',[]):
            t=h.get('telemetry',{})
            if 'seq'in t:windows[t['seq']]=t
        rows=list(windows.values())
        limits=(0,max(1,max((max(t.get('r0_uart_Bps',0),t.get('host_iq_Bps',0))for t in rows),default=1))*1.15)
        plot(d,(28,415,1125,865),[[t.get('r0_uart_Bps',0)for t in rows],[t.get('host_iq_Bps',0)for t in rows]],['Radio UART','Host IQ'],'Actual FPGA one-second window counts','Distinct counter windows · bytes/s',limits)
        card(d,(1150,415,1772,865),'Coherent counters · no sample DSP')
        for j,line in enumerate([f"Window sequence: {telemetry.get('seq','—')}",f"Capture errors: {telemetry.get('capture_errors','—')}",f"UART errors: {telemetry.get('radio_errors','—')}",f"Logger drops: {telemetry.get('log_drops','—')}",'50 MHz counter clock','Nios software division: RV32I','FPGA samples are not CPU-filtered']):text(d,1175,480+45*j,line,21,MUTED)
        usage(d,state.get('fpga',{}));return image
    image=render(state)
    d=ImageDraw.Draw(image)
    if lesson==1:
        d.rectangle((0,80,W,183),fill=BG)
        for j,(title,sub)in enumerate([('ESP32 ADC','Sparse CI8 RF bursts'),('FPGA UART + CRC','Framing and validation'),('FPGA capture RAM','Frozen IQ snapshot'),('Host + CyberEther','Display FFT / plots')]):
            x=28+j*440;d.rounded_rectangle((x,91,x+415,178),10,fill=CARD,outline=CYAN,width=2);text(d,x+15,105,title,23,CYAN);text(d,x+15,143,sub,18,MUTED)
    if lesson==4:
        d.rectangle((25,560,883,870),fill=BG);card(d,(28,564,880,865),'Frequency translation → FIR II → decimation')
        c=state.get('latest',{}).get('ddc',{});m=c.get('ddc',{})
        for j,line in enumerate(['FPGA clean two-tone input',f"Decimation: {m.get('decimation','—')}",f"Output nominal rate: {m.get('output_rate',0)/1e6:g} MS/s",f"Output pairs: {m.get('output_samples','—')}",f"Independent integer error: {m.get('max_reference_error','—')} LSB",'Gain/meter hardware is added in lesson 5']):text(d,55,630+33*j,line,23,MUTED)
    return image
