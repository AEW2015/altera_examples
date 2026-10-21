#!/usr/bin/env python3
"""Correct generated FIR II coefficient reset contract without editing installed IP.
The 19.3.8 descriptor marks coeff_in_areset as reset_n, but the generated
VHDL h_areset is active high. Invert at the generated Verilog wrapper boundary.
"""
from pathlib import Path
import hashlib,json,re
stage=Path(__file__).resolve().parents[1]
(stage/'results').mkdir(exist_ok=True)
p=stage/'gen/vds/iq_bridge_system/ip/iq_bridge_system_fir_ii/synth/iq_bridge_system_fir_ii.v'
t=p.read_text();old=re.compile(r'(\.coeff_in_areset\s*\()coeff_in_areset(\),)')
if old.search(t):t,n=old.subn(r'\1~coeff_in_areset\2',t);assert n==1;p.write_text(t)
assert len(re.findall(r'\.coeff_in_areset\s*\(~coeff_in_areset\)',p.read_text()))==1
result=dict(status='PASS',reason='FIR II 19.3.8 descriptor reset_n vs VHDL active-high h_areset',path=str(p.relative_to(stage)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
(stage/'results/fir-reset-fix.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
