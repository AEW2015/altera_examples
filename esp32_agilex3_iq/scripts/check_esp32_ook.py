#!/usr/bin/env python3
"""Host-timed OOK diagnostic using the installed original-ESP32 CW probe.

The host coordinates one short RF capture per bit; this does not implement
independent frame acquisition, symbol timing recovery, FEC or arbitrary IQ TX.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from check_esp32_tone import metrics
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'cyberether'))
from iq_bridge import Bridge
from nios_fir import NiosFir

def decide_ook(levels,threshold_db):
    """Decide solely from calibrated receive power, never expected payload."""
    return np.asarray(levels)>threshold_db

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port');p.add_argument('--payload-hex',default='a5c3')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:payload=bytes.fromhex(a.payload_hex)
    except ValueError:p.error('Payload must be hexadecimal bytes')
    if not 1<=len(payload)<=8:p.error('Use 1–8 bytes for the short diagnostic')
    a.output.mkdir(parents=True,exist_ok=False)
    bits=np.unpackbits(np.frombuffer(payload,np.uint8));rows=[]
    proof=dict(kind='physical RF OOK with host-coordinated capture slots',
        independent_symbol_synchronization=False,arbitrary_iq_verified=False,
        fec=False,processing='host power detector; FPGA transport only',
        payload_hex=payload.hex(),tx_source=1,rx_source=0,tx_channel=8,backoff_qdb=96,rows=rows,completed=False)
    try:
        with NiosFir(pause_monitor=False) as n:n.command('PAIR',0)
        with Bridge(a.port) as b:
            b.control(2,1,2000000)
            proof['tx_identity']=b.radio_command(1,'INFO','TX_PROBE,')
            proof['rx_identity']=b.prepare_sdr(0,2442,16000000)
            oldgain=b.radio_command(0,'GAIN?','GAIN ')
            try:
                b.radio_command(0,'GAIN MANUAL 20','OK')
                proof['gain_readback']=b.radio_command(0,'GAIN?','GAIN ')
                if not proof['gain_readback'].startswith('GAIN MANUAL 20 '):raise RuntimeError('Fixed RX gain mismatch')
                def capture(label):
                    frame=next(b.captures(1,0,8192,16000000,pipeline=False))
                    result,_,_=metrics(frame.iq(),frame.rate)
                    (a.output/(label+'.ci8')).write_bytes(frame.payload)
                    result['transport']=frame.metadata()
                    return result
                b.radio_command(1,'STOP','STOP_REQUESTED,');time.sleep(.05)
                off=[capture('cal-off-'+str(i)) for i in range(3)]
                b.radio_write(1,'TONE 8 3000 96\n');b.wait_text(1,'TX_ON,',10)
                try:on=[capture('cal-on-'+str(i)) for i in range(3)]
                finally:
                    b.radio_write(1,'STOP\n');b.wait_text(1,'TX_OFF,',4)
                low=float(np.median([r['relative_band_db'] for r in off]));high=float(np.median([r['relative_band_db'] for r in on]))
                proof.update(calibration=dict(off=off,on=on,low_db=low,high_db=high))
                if high-low<12:raise RuntimeError('Insufficient OOK calibration separation')
                threshold=(low+high)/2;proof['threshold_db']=threshold
                start=time.monotonic()
                for i,bit in enumerate(bits):
                    ack=None;tone_start=None
                    if bit:
                        b.radio_write(1,'TONE 8 1200 96\n');ack=b.wait_text(1,'TX_ON,',4);tone_start=time.monotonic()
                    else:b.radio_command(1,'STOP','STOP_REQUESTED,')
                    try:row=capture(f'bit-{i:02d}')
                    finally:
                        if bit:
                            b.radio_write(1,'STOP\n');off_ack=b.wait_text(1,'TX_OFF,',3)
                    if tone_start is not None and time.monotonic()-tone_start>=1:
                        raise RuntimeError('Capture exceeded the qualified on-window')
                    if row['rail_percent']>=1:raise RuntimeError('Receiver rail hits invalidate bit measurement')
                    # Payload is used only below, to count measured errors.
                    detected=int(decide_ook([row['relative_band_db']],threshold)[0])
                    row.update(index=i,expected=int(bit),detected=detected,host_elapsed_s=time.monotonic()-start,on_ack=ack)
                    rows.append(row);print(f'Bit {i+1}/{len(bits)} TX={bit} RX={detected} power={row["relative_band_db"]:.2f} dB',flush=True)
                decoded=np.packbits(np.asarray([r['detected'] for r in rows],dtype=np.uint8)).tobytes()
                errors=sum(r['expected']!=r['detected'] for r in rows)
                proof.update(completed=True,decoded_hex=decoded.hex(),bit_errors=errors,measured_bits=len(bits),elapsed_s=time.monotonic()-start)
            finally:
                b.radio_write(1,'STOP\n');time.sleep(.03)
                proof['final_tx_state']=b.radio_command(1,'INFO','TX_PROBE,')
                prior=oldgain.split();restore='GAIN HARDWARE' if prior[1]=='HARDWARE' else 'GAIN MANUAL '+prior[2]
                b.radio_command(0,restore,'OK')
    finally:(a.output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    x=np.arange(len(rows));fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=True)
    levels=[r['relative_band_db'] for r in rows]
    axes[0].scatter(x,levels,c=['#ff9800' if r['detected'] else '#2196f3' for r in rows],s=60)
    axes[0].axhline(proof['threshold_db'],color='gray',ls='--',label='Calibration threshold')
    axes[0].set(ylabel='Relative receive band power (dB)',title='Original ESP32 → RF → RFS2 · host-timed OOK');axes[0].legend()
    axes[1].step(x,[r['expected'] for r in rows],where='mid',lw=4,alpha=.4,label='Transmitted bits')
    axes[1].scatter(x,[r['detected'] for r in rows],marker='x',color='black',s=70,label='Detected from RF power')
    axes[1].set(ylim=(-.3,1.3),yticks=[0,1],xlabel='Host-coordinated bit/capture index',ylabel='Bit',title=f'{payload.hex().upper()} → {proof["decoded_hex"].upper()} · {proof["bit_errors"]}/{len(bits)} observed errors')
    axes[1].legend();fig.tight_layout();fig.savefig(a.output/'ook-evidence.png',dpi=150)
    print(json.dumps({k:v for k,v in proof.items() if k not in ('rows','calibration')},indent=2))
    if proof['bit_errors']:raise SystemExit('OOK diagnostic recorded bit errors')
if __name__=='__main__':main()
