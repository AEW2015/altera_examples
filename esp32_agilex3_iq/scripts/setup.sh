#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-notebooks
.venv-notebooks/bin/python -m pip install -r requirements.txt
.venv-notebooks/bin/python scripts/fetch.py cyberether
cc -shared -fPIC -O2 cyberether/runtime/register-bundled-plugins.c -o cyberether/runtime/register-bundled-plugins.so -ldl
.venv-notebooks/bin/python - <<'PY'
from pathlib import Path
import zipfile
p=Path('cyberether/samples')
with zipfile.ZipFile(p/'clean-ddc.zip','w',zipfile.ZIP_DEFLATED)as z:
 for f in (p/'clean-ddc').iterdir():z.write(f,'clean-ddc/'+f.name)
PY
