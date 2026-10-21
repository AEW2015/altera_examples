#!/usr/bin/env python3
"""Run the short standalone gain RTL lesson using the local Questa installation."""
import subprocess
from common import ROOT,tool_command,tool_path,tool_exe,tool_env
out=ROOT/'simulation'
subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do','simulate.do'],cwd=tool_path(out)),cwd=out,env=tool_env(),check=True)
assert 'PASS gain teaching'in(out/'transcript').read_text()
print('PASS: bypass, half, double, saturation and zero; exact integers and hardware power meters')
