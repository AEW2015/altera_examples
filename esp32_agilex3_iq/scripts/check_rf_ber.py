#!/usr/bin/env python3
"""Offline BER sweep and separate saved-RF evidence; never opens hardware."""
import argparse
import json
from pathlib import Path
import sys
import time
from common import ROOT
sys.path.insert(0, str(ROOT/'cyberether'))
from ber_qualification import run_sweep, aggregate_rf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--proof', action='append', default=[], type=Path)
    parser.add_argument('--frames', type=int, default=1000)
    parser.add_argument('--payload-bytes', type=int, default=16)
    parser.add_argument('--seed', type=int, default=20261021)
    parser.add_argument('--ebn0', type=float, nargs='+', default=[-2, 0, 2, 4, 6])
    parser.add_argument('--reference-payload', type=lambda x: int(x, 0))
    parser.add_argument('--rf-only', action='store_true')
    args = parser.parse_args()
    result = dict(schema='rf-ber-qualification-v1', created_at=time.time())
    if not args.rf_only:
        print(f'AWGN simulation: {len(args.ebn0)} points × {args.frames} frames; no hardware', flush=True)
        result['simulation'] = run_sweep(args.ebn0, frames=args.frames, payload_bytes=args.payload_bytes, seed=args.seed, progress=lambda i,n,db: print(f'BER point {i}/{n}: '+(f'{db:g} dB' if db is not None else 'complete'), flush=True))
    if args.proof:
        result['rf'] = aggregate_rf(args.proof, reference_payload=args.reference_payload, modulation='BPSK')
        result['rf_qpsk'] = aggregate_rf(args.proof, reference_payload=args.reference_payload, modulation='QPSK')
    if args.rf_only and not args.proof:
        parser.error('--rf-only requires --proof')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'qualification.json'
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    tmp.replace(target)
    print(target)
    return result


if __name__ == '__main__':
    main()
