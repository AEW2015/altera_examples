#!/usr/bin/env python3
"""Check compiler stack-frame evidence before accepting the diagnostic build."""
import argparse,json
from pathlib import Path
from common import ROOT

def inspect(path):
    rows=[]
    for line in Path(path).read_text().splitlines():
        fields=line.split('\t')
        if len(fields)==3:rows.append({'function':fields[0].rsplit(':',1)[-1],'bytes':int(fields[1]),'kind':fields[2]})
    worker=[r for r in rows if r['function']=='worker']
    if len(worker)!=1 or worker[0]['kind']!='static' or worker[0]['bytes']>512:raise ValueError('Worker compiler frame must be static and <=512 bytes')
    return {'passed':True,'compiler_frames':rows,'worker_task_stack_bytes':8192,
            'scope':'Local frame only; vendor call-tree stack requires measured runtime high-water mark'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-dir',type=Path,default=ROOT/'build-original-iq-tx-probe');a=p.parse_args()
    report=inspect(a.build_dir/'esp-idf/main/CMakeFiles/__idf_main.dir/main.c.su')
    (a.build_dir/'STACK_USAGE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
