#!/usr/bin/env python3
"""Build-only checkpoint11 Nios raw-capture receiver app; never download/RF.

Requires stage11's256KiB linker and platform_map.h (mtime0x50000). Generated
ELF replaces the normal Nios monitor only through a separate explicit download.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from common import ROOT,altera_root,tool_env

def build(out=None):
    stage=ROOT/'fpga_hub/iq_bridge/vds_demo_11_wifi64_ota';out=Path(out or ROOT/'simulation/wifi64-capture-app').resolve();out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'sw/wifi64_capture_app.c';platform=stage/'sw/platform_map.h';link=stage/'sw/link.ld'
    if 'LENGTH = 256K' not in link.read_text() or '#define WIFI64_NIOS_MTIME_BASE 0x00050000u' not in platform.read_text():raise RuntimeError('Matching checkpoint11 256KiB linker/platform map required')
    compiler=Path(os.getenv('ATUM_RISCV_GCC',str(altera_root()/'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc')))
    size=Path(os.getenv('ATUM_RISCV_SIZE',str(compiler.parent/'riscv32-unknown-elf-size')))
    elf=out/'wifi64_capture_app.elf'
    command=[str(compiler),'-march=rv32i_zicsr','-mabi=ilp32','-Os','-ffreestanding','-fno-builtin','-mno-relax','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror','-fstack-usage','-I',str(ROOT/'sw'),'-I',str(stage/'sw'),'-Wl,-Map='+str(out/'wifi64_capture_app.map'),'-T',str(link),str(stage/'sw/start.S'),str(source),'-lgcc','-o',str(elf)]
    process=subprocess.run(command,env=tool_env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);(out/'build.log').write_text(process.stdout);process.check_returncode()
    sizes=subprocess.check_output([str(size),str(elf)],env=tool_env(),text=True);print(sizes,end='')
    files=[source,platform,link,stage/'sw/start.S',Path(__file__),*[ROOT/'sw'/name for name in ('wifi64_receiver.h','wifi64_acquire.h','wifi64_ofdm.h','wifi64_signal.h','wifi64_decode.h')]]
    result=dict(status='PASS_BUILD',hardware_tested=False,stage=11,ram_bytes=262144,mtime_base='0x50000',jtag_uart_base='0x10010000',input='FPGA FIR raw mirror; source0;40000000 nominal samples/s',runtime='Nios software receiver, host transport/display only',tx_started=False,elf=str(elf),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),size_output=sizes,build_unix=time.time(),command=command,files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (out/'BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print('ELF:',elf,'\nSHA256:',result['elf_sha256']);print('Build only: no device access, download or RF.');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);args=p.parse_args();build(args.out)
