"""Offline audit of explicitly selected saved RF batches, never hardware I/O."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zlib
import numpy as np

PHYSICAL_KINDS=('physical_rf_bpsk','physical_rf_qpsk')


def discover_proofs(paths=(), directories=()):
    """Only recurse under directories explicitly supplied by the caller."""
    selected=[Path(p) for p in paths]
    for root in directories:
        root=Path(root)
        if not root.is_dir():raise ValueError(f'Proof directory does not exist: {root}')
        selected.extend(sorted(root.rglob('proof.json')))
    return sorted(set(p.resolve() for p in selected))


def audit_raw(proof_paths,*,require_complete=False,redecode=False,progress=None):
    """Check raw byte count/CRC/SHA and optionally recover without known bits.

    Raw re-decode compares acquired/CRC results and received payload/CRC bytes,
    never passes a known payload into the acquisition function. This does not
    replace saved results, exclude failed frames or create a new RF measurement.
    """
    proofs=[];checked=0;unique=set();duplicate=0;excluded=0
    for path in proof_paths:
        path=Path(path)
        proof_bytes=path.read_bytes()
        proof=json.loads(proof_bytes)
        if proof.get('kind') not in PHYSICAL_KINDS:
            excluded+=1;continue
        if require_complete and (not proof.get('completed') or proof.get('error')):
            raise ValueError(f'Incomplete RF proof: {path}; error={proof.get("error")}')
        rows=proof.get('rows',[])
        for index,row in enumerate(rows):
            rawpath=path.parent/f'capture-{index:03d}.ci8'
            raw=rawpath.read_bytes()
            transport=row['transport'];digest=hashlib.sha256(raw).hexdigest()
            if len(raw)!=2*transport['samples'] or len(raw)!=transport['length']:
                raise ValueError(f'Raw byte/sample count mismatch: {rawpath}')
            if zlib.crc32(raw)!=transport['raw_crc'] or digest!=transport['payload_sha256']:
                raise ValueError(f'Raw CRC/SHA256 mismatch: {rawpath}')
            if digest in unique:duplicate+=1
            unique.add(digest);checked+=1
            if redecode:
                from rf_bpsk import receive as receive_bpsk
                from rf_qpsk import receive as receive_qpsk
                receive=receive_qpsk if proof['kind']=='physical_rf_qpsk' else receive_bpsk
                recovered=receive(np.frombuffer(raw,np.int8).reshape(-1,2),rate=transport['rate'],
                    symbol_us=row['config']['period_us'])
                saved=row['report']
                for name in ('valid_frames','acquired_frames','acquisition_failures','crc_failures'):
                    if recovered[name]!=saved[name]:raise ValueError(f'Independent raw receive {name} mismatch: {rawpath}')
                threshold=2 if proof['kind']=='physical_rf_qpsk' else 1
                def outcomes(report):
                    return sorted((int(c['payload']),int(c['crc_received']),bool(c['crc_ok']))
                        for c in report['candidates'] if c['sync_errors']<=threshold)
                if outcomes(recovered)!=outcomes(saved):raise ValueError(f'Independent raw payload/CRC mismatch: {rawpath}')
            if progress:progress(path,index+1,len(rows))
        proofs.append(dict(path=str(path),kind=proof['kind'],completed=bool(proof.get('completed')),
            error=proof.get('error'),captures=len(rows),proof_sha256=hashlib.sha256(proof_bytes).hexdigest()))
    return dict(schema='rf-batch-byte-audit-v1',status='PASS',proofs=proofs,physical_proofs=len(proofs),
        captures_checked=checked,unique_raw_sha256=len(unique),duplicate_captures=duplicate,
        non_rf_proofs_excluded=excluded,raw_crc_sha_length_verified=True,
        independently_redecoded_without_known_payload=bool(redecode),hardware_access=False,
        scope='Saved files only; no new RF acquisition. Partial proofs are explicit unless require_complete requested. Failed CRC/acquisition attempts remain in the aggregate.')


def validate_audit_snapshot(audit):
    """Refuse to attach a byte audit to changed/live proof contents."""
    for record in audit['proofs']:
        path=Path(record['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['proof_sha256']:
            raise ValueError(f'Proof changed while auditing; retry after capture completes: {path}')
