#!/usr/bin/env python3
"""Report the tools used directly in this terminal/kernel's environment."""
import os, shutil, sys, sysconfig
from pathlib import Path
from common import ROOT, altera_root, local_tools, tool_exe

def check():
    if not local_tools():
        raise SystemExit('For notebooks, run this check beside the tools with ATUM_TOOLS_MODE=local.')
    a = altera_root()
    paths = {name: tool_exe(name) for name in ('quartus','quartus_sh','quartus_pgm','juart-terminal','vsim')}
    paths['Python shared library']=Path(sysconfig.get_config_var('LIBDIR')or '')/(sysconfig.get_config_var('LDLIBRARY')or '')
    paths.update({
        'RV32 GCC': Path(os.getenv('ATUM_RISCV_GCC',str(a/'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc'))),
        'RV32 size': Path(os.getenv('ATUM_RISCV_SIZE',str(a/'riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-size'))),
        'elf2hex': Path(os.getenv('ATUM_ELF2HEX',str(a/'niosv/bin/elf2hex'))),
        'Graphviz': Path(shutil.which('dot')or '/missing/dot'),
        **{name:Path(shutil.which(name)or '/missing/'+name)for name in('Xvfb','xdotool','scrot','pdftoppm','pdfinfo','pdftotext')},
    })
    missing = []
    print('Python:',sys.executable)
    print('Checkout:',ROOT)
    for name,p in paths.items():
        ok=p.is_file()and (name=='Python shared library'or os.access(p,os.X_OK))
        print(('OK     'if ok else 'MISSING'),name,':',p)
        if not ok: missing.append(name)
    print('DISPLAY:',os.getenv('DISPLAY','unset — desktop required for VDS/CyberEther'))
    print('UART:',os.getenv('ATUM_UART','default rig; override for your board'))
    print('JTAG cable:',os.getenv('ATUM_JTAG_CABLE','default rig; override for your board'))
    if missing: raise SystemExit('Configure missing tools: '+', '.join(missing))
    return paths
if __name__=='__main__': check()
