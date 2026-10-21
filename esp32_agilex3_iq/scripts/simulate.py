#!/usr/bin/env python3
"""Run the short standalone gain RTL lesson using Questa in the build container."""
import subprocess
from common import ROOT,CONTAINER,container_root
out=ROOT/'simulation'
subprocess.run(['docker','exec','-u','dev','-w',container_root()+'/simulation',CONTAINER,'/opt/altera/questa_fse/bin/vsim','-c','-do','simulate.do'],check=True)
assert 'PASS gain teaching'in(out/'transcript').read_text()
print('PASS: bypass, half, double, saturation and zero; exact integers and hardware power meters')
