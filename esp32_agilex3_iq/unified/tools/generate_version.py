#!/usr/bin/env python3
"""Generate the version record embedded in the firmware, once per build."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

MARKER = 'ESP-SDR-VERSION:'


def metadata(root, profile):
    try:
        revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True)
        if dirty:
            revision += '-dirty'
    except (OSError, subprocess.CalledProcessError):
        revision = 'unknown'
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return dict(revision=revision, build_date=stamp[:10], build_timestamp=stamp, profile=profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = MARKER + json.dumps(metadata(args.root, args.profile), separators=(',', ':'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('#pragma once\n#define ESP_SDR_VERSION_RECORD ' + json.dumps(record) + '\n')
