#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f vendor/esp-idf-sdr/export.sh ]]; then
  python3 scripts/fetch.py firmware
fi
vendor/esp-idf-sdr/install.sh esp32
source vendor/esp-idf-sdr/export.sh
idf.py -C unified -B build-esp32 -D IDF_TARGET=esp32 build
