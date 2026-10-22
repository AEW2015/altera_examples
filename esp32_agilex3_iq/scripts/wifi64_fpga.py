#!/usr/bin/env python3
"""Build checkpoint11's native VDS foundation with 256KiB Nios RAM.

No programming, JTAG, serial, RF or live host DSP. The initial monitor and
capture/FIR/DDC/modem datapath match checkpoint06; OTA receiver integration is a
separate source change. Legacy helper stage selections remain untouched.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,subprocess,sys
from common import ROOT,tool_command,tool_env
from lessons import fingerprint
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_11_wifi64_ota'

def build_inputs():
    files=[Path(__file__).resolve(),*sorted((STAGE/'scripts').glob('*.py'))]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def command(commands):
    display=os.getenv('DISPLAY',':0')
    try:
        available=subprocess.run(tool_command(['xdpyinfo','-display',display],display=display),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0
    except (FileNotFoundError,subprocess.TimeoutExpired):available=False
    args=['bash','-c',' && '.join(commands)]
    if available:return tool_command(args,cwd=STAGE,display=display)
    return tool_command(['xvfb-run','-a','-s','-screen 0 1600x1000x24 -nolisten tcp',*args],cwd=STAGE)

def check():
    image=STAGE/'iq_bridge_vds.sof'
    meta=json.loads((STAGE/'BUILD_RESULT.json').read_text())
    if meta.get('checkpoint')!=11 or meta.get('status')!='PASS_BUILD' or meta.get('source_fingerprint')!=fingerprint(STAGE) or meta.get('build_inputs_sha256')!=build_inputs() or meta.get('sha256')!=hashlib.sha256(image.read_bytes()).hexdigest():
        raise RuntimeError('Checkpoint11 source/helper/image mismatch; rebuild')
    return meta

def export():
    from quartus_project import export_project
    return export_project(STAGE)

def build(generate_only=False):
    (STAGE/'run').mkdir(exist_ok=True)
    with (STAGE/'run/build.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=fingerprint(STAGE);helpers=build_inputs()
        commands=['bash scripts/build_firmware.sh','quartus_sh -t scripts/create_vds.tcl','quartus_sh -t scripts/connect_vds.tcl']
        if not generate_only:commands.append('quartus_sh --flow compile iq_bridge_vds')
        with (STAGE/'run/build.log').open('w') as log:
            subprocess.run(command(commands),cwd=STAGE,env=tool_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
        if before!=fingerprint(STAGE) or helpers!=build_inputs():
            raise RuntimeError('Authored source/helper changed while building; rebuild')
        if not generate_only:
            fit=(STAGE/'iq_bridge_vds.fit.summary').read_text()
            sta=(STAGE/'iq_bridge_vds.sta.summary').read_text()
            slacks=[float(x) for x in re.findall(r'Slack : (-?[\d.]+)',sta)]
            if 'Successful' not in fit or not slacks or min(slacks)<0:
                raise RuntimeError('Checkpoint11 fit/timing failed; inspect reports')
            def count(pattern):
                found=re.search(pattern,fit)
                return int(found[1].replace(',','')) if found else None
            meta=dict(status='PASS_BUILD',checkpoint=11,source_fingerprint=before,
                      build_inputs_sha256=helpers,sha256=hashlib.sha256((STAGE/'iq_bridge_vds.sof').read_bytes()).hexdigest(),
                      device='A3CZ135BB18AE7S',clock_hz=50000000,nios_ram_bytes=262144,
                      minimum_reported_slack_ns=min(slacks),hardware_verified=False,
                      iq_bridge=True,fpga_fir=True,fpga_ddc=True,fpga_gain_meter=True,
                      fpga_modem=True,modem_symbol_rate=True,native_wifi_receiver=False,
                      role='256KiB Nios foundation; checkpoint06 baseline monitor, no OTA decoder yet',
                      radio_transports={'0':'UART','1':'UART','2':'UART'},
                      resources=dict(ALMs=count(r'Logic utilization \(in ALMs\) : ([\d,]+)'),M20Ks=count(r'Total RAM Blocks : ([\d,]+)'),DSP_reported=count(r'Total DSP Blocks : ([\d,]+)')))
            (STAGE/'BUILD_RESULT.json').write_text(json.dumps(meta,indent=2)+'\n')
        export()
    return STAGE/'iq_bridge_vds.qpf'

def simulate(gui=False):
    # Exercise the copied checkpoint11 RTL, not the original checkpoint06 path.
    import simulate_modem
    simulate_modem.STAGE=STAGE
    return simulate_modem.simulate(gui)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['generate','build','simulate','check','export'])
    p.add_argument('--gui',action='store_true');a=p.parse_args()
    if a.action in ('generate','build'):print(build(a.action=='generate'))
    elif a.action=='simulate':simulate(a.gui)
    elif a.action=='check':print(json.dumps(check(),indent=2))
    else:print(export())
