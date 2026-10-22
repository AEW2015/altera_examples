#!/usr/bin/env bash
# Build the combined PMOD A image. Never flashes or transmits.
set -euo pipefail
cd "$(dirname "$0")/.."
idf_sdk="${ATUM_ESP_IDF:-$PWD/vendor/esp-idf-sdr}"
[[ -f "$idf_sdk/export.sh" ]] || { echo 'Fetch pinned SDK with scripts/fetch.py firmware' >&2; exit 1; }
[[ "$(git -C "$idf_sdk" rev-parse HEAD)" == 25fe69f946311abdaf9ad56591f25fedbc20ac98 ]] || { echo 'Wrong SDK commit' >&2; exit 1; }
source "$idf_sdk/export.sh"
idf.py -C firmware/tx_lab -B "$PWD/build-tx-lab" \
 -D IDF_TARGET=esp32 -D "SDKCONFIG=$PWD/build-tx-lab/sdkconfig" \
 -D "SDKCONFIG_DEFAULTS=$PWD/firmware/tx_lab/sdkconfig.defaults" reconfigure build
python scripts/check_tx_lab_stack.py
python scripts/flash_esp32.py --module pmod-a --build-dir build-tx-lab --record-build
printf '%s\n' 'Compile only: NOT installed; no original-chip arbitrary-IQ TX is established.'
