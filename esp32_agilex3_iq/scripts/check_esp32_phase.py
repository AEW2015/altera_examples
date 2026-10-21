#!/usr/bin/env python3
"""Capture bounded phase-continuity hypotheses and negative RF controls.

Requires explicitly installed original-ESP32 probe v3/v4. No programming/flashing.
Measured phase clusters are not decoded payload bits or a complete RF modem.
"""
import argparse,json,sys,time
from pathlib import Path
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir
from check_esp32_nco import state
from analyze_esp32_phase import analyze_iq,plot_report

def fields(line):return {k:int(v) for k,v in (x.split('=',1) for x in line.split(',')[1:])}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--repeats',type=int,choices=range(1,6),default=2)
    p.add_argument('--rx-gain',type=int,choices=range(128),metavar='0..127',default=0,help='Manual RX gain code; inspect sample headroom before interpreting phase')
    p.add_argument('--pattern',type=int,choices=range(256),metavar='0..255',default=165,help='Repeated 8-bit pattern, decimal (165 is 0xA5)')
    p.add_argument('--symbol-us',type=int,choices=range(32,257),metavar='32..256',default=64)
    p.add_argument('--fast-step',type=int,choices=[1,2,3],help='Use v4 FASTPHASE with this NCO extension step')
    p.add_argument('--backoff-qdb',type=int,choices=range(80,121),metavar='80..120',default=96,help='TX power backoff in quarter-dB units')
    p.add_argument('--pulse-cycles',type=int,help='Override nominal half-turn width for calibration; never an assumed RF phase')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    proof=dict(kind='physical RF phase-continuity hypothesis with negative controls',completed=False,
        arbitrary_iq_verified=False,decoded_bits=False,fpga_demodulation=False,rows=[])
    try:
        with NiosFir(pause_monitor=False)as n:n.command('PAIR',0)
        with Bridge(a.port)as b:
            b.control(2,1,2000000)
            proof['identity']=b.radio_command(1,'INFO','TX_PROBE,')
            if not proof['identity'].startswith(('TX_PROBE,v=3,','TX_PROBE,v=4,')):raise RuntimeError('Phase probe requires v3/v4')
            if a.fast_step and not proof['identity'].startswith('TX_PROBE,v=4,'):raise RuntimeError('FASTPHASE requires v4')
            proof['receiver']=b.prepare_sdr(0,2447,16000000)
            old=b.radio_command(0,'GAIN?','GAIN ')
            try:
                proof['rx_gain_readback']=b.radio_command(0,f'GAIN MANUAL {a.rx_gain}','OK')
                proof['rx_gain_code']=a.rx_gain
                proof['rx_gain_state']=b.radio_command(0,'GAIN?','GAIN ')
                if proof['rx_gain_state'].split()[1:3]!=['MANUAL',str(a.rx_gain)]:
                    raise RuntimeError('Manual RX gain readback mismatch')
                # Initialize RF explicitly before querying the final CPU clock.
                b.radio_write(1,f'TONE 8 50 {a.backoff_qdb}\n');b.wait_text(1,'TX_ON,',10);time.sleep(.08)
                caps=fields(b.radio_command(1,'PHASECAP','PHASECAP,'));proof['caps']=caps
                full=a.pulse_cycles if a.pulse_cycles is not None else (caps['half_cycles']//a.fast_step if a.fast_step else caps['half_cycles'])
                if not 0<full<=8192:raise ValueError('Pulse width must be 1..8192 cycles')
                if full>caps['cpu']*a.symbol_us//2000000:
                    raise ValueError('Pulse must not exceed half the symbol period')
                for name,pulse in [('zero_pulse_control',0),('half_width_control',full//2),('nominal_half_turn',full)]:
                    for index in range(a.repeats):
                        command=f'PHASE 8 500 {a.backoff_qdb} {a.pattern} {a.symbol_us} {pulse}'
                        if a.fast_step:command=command.replace('PHASE ','FASTPHASE ',1)+f' {a.fast_step}'
                        b.radio_write(1,command+'\n')
                        cfg=fields(b.wait_text(1,'PHASE_CFG,',4))
                        if a.fast_step and cfg.get('step')!=a.fast_step:
                            raise RuntimeError('Fast NCO step readback mismatch')
                        if (cfg['period_us'],cfg['pulse_cycles'],cfg['pattern'])!=(a.symbol_us,pulse,a.pattern):
                            raise RuntimeError('Phase settings readback mismatch')
                        # CFG is emitted after vendor RF setup; do not wait for a
                        # redundant event that can be dropped by the hub text queue.
                        on='Matched configuration emitted after RF setup; TX_ON event not required'
                        start=time.monotonic()
                        try:frame=next(b.captures(1,0,16380,16000000,pipeline=False))
                        finally:b.radio_write(1,'STOP\n')
                        capture_elapsed=time.monotonic()-start
                        if capture_elapsed>.48:raise RuntimeError('Capture transfer exceeded this probe on-window; capture timing needs review')
                        deadline=time.monotonic()+3
                        while True:
                            idle=b.radio_command(1,'INFO','TX_PROBE,')
                            if 'busy=0' in idle:break
                            if time.monotonic()>deadline:raise RuntimeError('Phase job did not stop')
                            time.sleep(.01)
                        quiet=state(b.radio_command(1,'STATE','TONE_STATE,'))
                        if any((quiet[k]>>18)&255 for k in ('tone1','tone2')) or quiet['ext']&3:raise RuntimeError('Phase job did not restore quiet controls')
                        stats=fields(b.radio_command(1,'PHASESTAT','PHASESTAT,'))
                        if stats['job']!=cfg['job']:raise RuntimeError('Phase statistics job mismatch')
                        folder=a.output/f'{name}-{index}';folder.mkdir()
                        (folder/'capture.ci8').write_bytes(frame.payload)
                        report=analyze_iq(frame.iq(),rate=frame.rate,expected_offset_hz=0,expected_pulse_us=(pulse/cfg['cpu']*1e6 if pulse else None))
                        report['capture']=frame.metadata()
                        (folder/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
                        plot_report(report,folder/'phase-analysis.png')
                        row=dict(case=name,index=index,command=command,config=cfg,on=on,stats=stats,quiet=quiet,
                            capture_elapsed_s=capture_elapsed,idle_readback=idle,
                            metrics=report['metrics'],carrier=report['carrier'],transport=frame.metadata(),hub_status=b.status())
                        proof['rows'].append(row);print(name,index,json.dumps(report['metrics']),flush=True)
                controls=[r for r in proof['rows'] if r['case']!='nominal_half_turn'];signal=[r for r in proof['rows'] if r['case']=='nominal_half_turn']
                proof.update(completed=True,controls_reject_two_phase=all(not r['metrics']['two_phase_clusters_observed'] for r in controls),
                    phase_hypothesis_supported=bool(all(r['metrics']['two_phase_clusters_observed'] for r in signal) and all(not r['metrics']['two_phase_clusters_observed'] for r in controls)))
            finally:
                b.radio_write(1,'STOP\n');prior=old.split();b.radio_command(0,'GAIN HARDWARE' if prior[1]=='HARDWARE' else 'GAIN MANUAL '+prior[2],'OK')
    except BaseException as error:
        proof['error']=str(error);raise
    finally:(a.output/'proof.json').write_text(json.dumps(proof,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='rows'},indent=2))
    if not proof['phase_hypothesis_supported']:print('Hypothesis not qualified: retain measured negative evidence; no BPSK or IQ playback claim.')
if __name__=='__main__':main()
