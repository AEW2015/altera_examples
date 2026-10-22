#!/usr/bin/env python3
"""Build-only standalone Nios L-SIG test, with native execution first.

Offline fixture origin; no hardware download, UART/JTAG access or RF activity.
Uses checkpoint06 startup/linker64KiB, JTAGUART0x10010000, mtime0x30000.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from common import ROOT,altera_root,tool_env


def fixture(printed_rate,parity_bad=False):
    # Primary TX order: RATE MSB-first, LENGTH LSB-first. K7 taps expressed as
    # delay lines independently of the C decoder's register-mask implementation.
    bits=[printed_rate>>i&1 for i in (3,2,1,0)]+[0]+[92>>i&1 for i in range(12)]
    bits+=[(sum(bits)&1)^int(parity_bad)]+[0]*6
    history=[0]*7;coded=[]
    for bit in bits:
        history=[bit]+history[:6]
        coded.extend(sum(history[i] for i in taps)&1 for taps in ((0,2,3,5,6),(0,1,2,3,6)))
    return [1000 if coded[row*16+col] else -1000 for col in range(16) for row in range(3)]


def build(out=None):
    out=Path(out or ROOT/'simulation/wifi64-signal-nios-selftest').resolve();out.mkdir(parents=True,exist_ok=True)
    generated=out/'wifi64_signal_fixture.h'
    vectors=[fixture(13),fixture(1),fixture(3),fixture(3,True)]
    generated.write_text('/* Offline generated L-SIG fixtures, not RF. */\nstatic const int16_t signal_fixtures[4][48]={\n'+',\n'.join('{'+','.join(map(str,v))+'}' for v in vectors)+'\n};\n')
    source=ROOT/'sw/wifi64_signal_selftest.c';stage=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem'
    compiler=Path(os.getenv('ATUM_RISCV_GCC',str(altera_root()/'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc')))
    size=Path(os.getenv('ATUM_RISCV_SIZE',str(compiler.parent/'riscv32-unknown-elf-size')))
    if not shutil.which('cc'):raise RuntimeError('Native cc required for this build selftest')
    executable=out/'wifi64-signal-native'
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-DW64_SELFTEST_NATIVE','-I',str(ROOT/'sw'),'-I',str(out),str(source),'-o',str(executable)],check=True)
    native=subprocess.check_output([str(executable)],text=True,timeout=30);(out/'native-selftest.log').write_text(native);print(native,end='')
    if 'SUMMARY,passed=4,total=4' not in native:raise RuntimeError('Native L-SIG selftest failed')
    elf=out/'wifi64_signal_selftest.elf'
    cmd=[str(compiler),'-march=rv32i_zicsr','-mabi=ilp32','-Os','-ffreestanding','-fno-builtin','-mno-relax','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror','-I',str(ROOT/'sw'),'-I',str(out),'-Wl,-Map='+str(out/'wifi64_signal_selftest.map'),'-T',str(stage/'sw/link.ld'),str(stage/'sw/start.S'),str(source),'-lgcc','-o',str(elf)]
    process=subprocess.run(cmd,env=tool_env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);(out/'build.log').write_text(process.stdout);process.check_returncode()
    sizes=subprocess.check_output([str(size),str(elf)],env=tool_env(),text=True);print(sizes,end='')
    paths=[source,ROOT/'sw/wifi64_signal.h',generated,stage/'sw/start.S',stage/'sw/link.ld',Path(__file__)]
    result=dict(status='PASS_BUILD',native_selftest='PASS_4',hardware_tested=False,source='offline-fixture',runtime='Nios V software L-SIG, not RTL/acquisition/RF',ram_bytes=65536,jtag_uart_base='0x10010000',mtime_base='0x30000',trigger='T',tx_started=False,elf=str(elf),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),size_output=sizes,build_unix=time.time(),command=cmd,files={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out/'BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print('ELF:',elf,'\nSHA256:',result['elf_sha256']);print('Build only; no hardware access.');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path);args=parser.parse_args();build(args.out)
