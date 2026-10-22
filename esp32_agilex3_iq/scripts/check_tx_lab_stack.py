from pathlib import Path
import json
from common import ROOT
from check_original_iq_stack import inspect
build=ROOT/'build-tx-lab'
files=list((build/'esp-idf/main').rglob('*.su'))
reports={str(p.relative_to(build)):inspect(p) for p in files if p.name=='main.c.su' and any(x in str(p) for x in ('original_iq_tx_probe','esp32_tx_probe'))}
if len(reports)!=2:raise ValueError('Expected both certification worker stack reports')
(build/'STACK_USAGE.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports))
