#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == --system ]]; then
  if [[ $(id -u) == 0 ]]; then atum_sudo=(); else atum_sudo=(sudo); fi
  "${atum_sudo[@]}" apt-get update
  "${atum_sudo[@]}" apt-get install -y python3-venv python3-pip python3-dev graphviz fonts-dejavu-core mesa-vulkan-drivers libvulkan1 libgl1 libegl1 build-essential
fi
for atum_dep in python3 cc dot; do command -v "$atum_dep" >/dev/null || { echo "Missing $atum_dep; rerun with --system"; exit 1; }; done
python3 -m venv .venv-notebooks
.venv-notebooks/bin/python -m pip install -r requirements-notebooks.txt
.venv-notebooks/bin/python -m ipykernel install --user --name atum-a3-iq --display-name 'Atum A3 IQ Demos'
.venv-notebooks/bin/python -m ipykernel install --prefix "$PWD/.venv-notebooks" --name atum-a3-iq --display-name 'Atum A3 IQ Demos'
.venv-notebooks/bin/python scripts/fetch.py cyberether
cc -shared -fPIC -O2 cyberether/runtime/register-bundled-plugins.c -o cyberether/runtime/register-bundled-plugins.so -ldl
.venv-notebooks/bin/python - <<'PY'
from pathlib import Path
import zipfile
p=Path('cyberether/samples')
with zipfile.ZipFile(p/'clean-ddc.zip','w',zipfile.ZIP_DEFLATED)as z:
 for f in (p/'clean-ddc').iterdir():z.write(f,'clean-ddc/'+f.name)
PY
printf '\nUse the kernel: Atum A3 IQ Demos\nStart: .venv-notebooks/bin/jupyter lab notebooks --ip=0.0.0.0 --no-browser\n'
