#!/usr/bin/env python3
"""Build (never download) a standalone RV32I Wi-Fi64 primitive selftest.

Output ELF uses checkpoint06's 64-KiB RAM, startup and JTAG UART at0x10010000.
Loading it replaces that monitor until its ELF/SOF is restored. Only root's
explicit hardware workflow may download; this utility has no device access.
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
from wifi64_vectors import header


def build(out=None,native=True):
    out=Path(out or ROOT/'simulation/wifi64-nios-selftest').resolve()
    out.mkdir(parents=True,exist_ok=True)
    fixture=out/'wifi64_fixture.h';fixture.write_text(header())
    source=ROOT/'sw/wifi64_selftest.c'
    stage=ROOT/'fpga_hub/iq_bridge/vds_demo_06_modem'
    compiler=Path(os.getenv('ATUM_RISCV_GCC',str(altera_root()/'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc')))
    size=Path(os.getenv('ATUM_RISCV_SIZE',str(compiler.parent/'riscv32-unknown-elf-size')))
    env=tool_env();native_report=None
    if native and shutil.which('cc'):
        executable=out/'wifi64-native-selftest'
        subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-DW64_SELFTEST_NATIVE','-I',str(ROOT/'sw'),'-I',str(out),str(source),'-o',str(executable)],check=True)
        native_report=subprocess.check_output([str(executable)],text=True,timeout=30)
        (out/'native-selftest.log').write_text(native_report)
        if 'SUMMARY,passed=5,total=5' not in native_report:raise RuntimeError('Native selftest did not pass')
        print(native_report,end='')
    elf=out/'wifi64_selftest.elf'
    cmd=[str(compiler),'-march=rv32i_zicsr','-mabi=ilp32','-Os','-ffreestanding','-fno-builtin','-mno-relax','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror',
         '-I',str(ROOT/'sw'),'-I',str(out),'-Wl,-Map='+str(out/'wifi64_selftest.map'),'-T',str(stage/'sw/link.ld'),str(stage/'sw/start.S'),str(source),'-lgcc','-o',str(elf)]
    log=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (out/'build.log').write_text(log.stdout);log.check_returncode()
    sizes=subprocess.check_output([str(size),str(elf)],env=env,text=True)
    print(sizes,end='')
    paths=[source,ROOT/'sw/wifi64_ofdm.h',ROOT/'sw/wifi64_decode.h',stage/'sw/start.S',stage/'sw/link.ld',fixture,Path(__file__),ROOT/'scripts/wifi64_vectors.py']
    result=dict(status='PASS_BUILD',hardware_tested=False,source='offline-fixture',runtime='Nios V software; no RTL/RF claim',architecture='rv32i_zicsr/ilp32',ram_bytes=65536,jtag_uart_base='0x10010000',trigger='T',tx_started=False,
                native_selftest='PASS_5' if native_report else 'NOT_RUN',elf=str(elf),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),size_output=sizes,build_unix=time.time(),command=cmd,
                files={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out/'BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print('ELF:',elf,'\nSHA256:',result['elf_sha256'])
    print('Build only: no download, serial, JTAG, or RF access.')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);p.add_argument('--skip-native',action='store_true');a=p.parse_args();build(a.out,not a.skip_native)
