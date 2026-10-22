#!/usr/bin/env python3
"""Simulate checkpoint11's actual UART text controller in Questa; no hardware."""
import hashlib,json,subprocess
from common import ROOT,tool_exe,tool_env,tool_path
STAGE=ROOT/'fpga_hub/iq_bridge/vds_demo_11_wifi64_ota'
def main():
    out=ROOT/'simulation/wifi64-text';out.mkdir(parents=True,exist_ok=True)
    sources=[STAGE/'rtl/iq_bridge_controller.sv',STAGE/'rtl/sync_fifo.sv',STAGE/'sim/tb_iq_controller_text.sv']
    commands=['onerror {quit -force -code 1}','vlib work','vmap work work','vlog -sv '+' '.join('{'+tool_path(s)+'}' for s in sources),'vsim -voptargs=+acc work.tb_iq_controller_text','log -r /*','run -all','quit -force -code 0']
    script=out/'run.do';script.write_text('\n'.join(commands)+'\n')
    with (out/'questa.log').open('w') as log:
        subprocess.run([str(tool_exe('vsim')),'-c','-do',str(script)],cwd=out,env=tool_env(),stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    if 'PASS controller text' not in (out/'questa.log').read_text():raise RuntimeError('Missing RTL assertions pass')
    proof={'passed':True,'checkpoint':11,'hardware_access':False,'actual_rtl':True,'tests':['127/128/255-byte lines','256-byte reject and drop count','2 Mbaud back-to-back configuration / TX_ON','four-line FIFO order/full/drop','atomic full pop and push'],
           'source_sha256':{str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}}
    (out/'validation.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
