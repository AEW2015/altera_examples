#!/usr/bin/env python3
"""Fetch pinned upstream dependencies; no SDK or application binary is committed."""
import argparse,hashlib,os,subprocess,urllib.request
from common import ROOT
p=argparse.ArgumentParser();p.add_argument('dependency',choices=('cyberether','firmware'));a=p.parse_args()
def checkout(url,commit,directory,recursive=False):
    fresh=not directory.exists()
    if fresh:subprocess.run(['git','clone','--filter=blob:none','--no-checkout',url,str(directory)],check=True)
    if not fresh and subprocess.check_output(['git','-C',str(directory),'status','--porcelain'],text=True).strip():raise RuntimeError('Refusing to overwrite modified dependency '+str(directory))
    subprocess.run(['git','-C',str(directory),'checkout','--detach',commit],check=True)
    if recursive:subprocess.run(['git','-C',str(directory),'submodule','update','--init','--recursive'],check=True)
if a.dependency=='cyberether':
    d=ROOT/'cyberether/runtime';d.mkdir(exist_ok=True);target=d/'CyberEther-linux-x64-v1.15.0.AppImage';sha='65a69903043cfe21ada98ad9c61ebbdb3b7208729bad6ad84aeb17cbe5f0565f'
    if not target.exists():
        temp=target.with_suffix('.download')
        urllib.request.urlretrieve('https://github.com/luigifcruz/CyberEther/releases/download/v1.15.0/CyberEther-linux-x64.AppImage',temp)
        if hashlib.sha256(temp.read_bytes()).hexdigest()!=sha:temp.unlink();raise RuntimeError('CyberEther digest mismatch')
        temp.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==sha;target.chmod(0o755);print('CyberEther v1.15.0 digest verified')
else:
    d=ROOT/'vendor';d.mkdir(exist_ok=True)
    checkout('https://github.com/ESPARGOS/esp-sdr.git','f86da81807b7f6e850742f6b789d9468c190ad41',d/'esp-sdr',True)
    checkout('https://github.com/espressif/esp-idf.git','25fe69f946311abdaf9ad56591f25fedbc20ac98',d/'esp-idf-sdr',True)
