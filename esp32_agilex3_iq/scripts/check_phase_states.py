#!/usr/bin/env python3
"""Offline four-state qualification of saved phase captures; no hardware access."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from common import ROOT
sys.path.insert(0, str(ROOT/'cyberether'))
from phase_states import qualify_states


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    proof = json.loads((a.directory/'proof.json').read_text())
    rows = []
    for row in proof['rows']:
        folder = a.directory/f"{row['case']}-{row['index']}"
        raw = (folder/'capture.ci8').read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != row['transport']['payload_sha256']:
            raise ValueError('Raw capture hash mismatch')
        report = json.loads((folder/'analysis.json').read_text())
        measured = qualify_states(np.frombuffer(raw, dtype=np.int8).reshape(-1, 2),
                                  carrier_hz=report['carrier']['carrier_hz'],
                                  rate=report['sample_rate_hz'], events=report['events'])
        rows.append(dict(case=row['case'], index=row['index'], source_sha256=sha,
                         pulse_cycles=row['config']['pulse_cycles'], result=measured))
        print(row['case'], row['index'], measured['four_states_qualified'], measured['circular_moments'])
    result = dict(kind='physical_rf_four_phase_gate', rows=rows,
                  four_state_captures=sum(r['result']['four_states_qualified'] for r in rows),
                  scope='Four phase states are a prerequisite, not proof of QPSK frames')
    target = a.output or a.directory/'four-state-proof.json'
    target.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
