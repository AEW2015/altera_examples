#!/usr/bin/env bash
# Separate original-chip diagnostic build. Never flashes or starts RF.
set -euo pipefail
cd "$(dirname "$0")/.."
idf_sdk="${ATUM_ESP_IDF:-$PWD/vendor/esp-idf-sdr}"
if [[ ! -f "$idf_sdk/export.sh" ]]; then
  echo 'Fetch the pinned SDK first: python scripts/fetch.py firmware' >&2
  exit 1
fi
actual_commit="$(git -C "$idf_sdk" rev-parse HEAD)"
if [[ "$actual_commit" != 25fe69f946311abdaf9ad56591f25fedbc20ac98 ]]; then
  echo 'The original-chip TX probe requires the repository-pinned SDR SDK.' >&2
  exit 1
fi
source "$idf_sdk/export.sh"
idf.py -C firmware/esp32_tx_probe -B "$PWD/build-esp32-tx-probe" \
  -D IDF_TARGET=esp32 -D "SDKCONFIG=$PWD/build-esp32-tx-probe/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=$PWD/firmware/esp32_tx_probe/sdkconfig.defaults" build
python scripts/flash_esp32.py --module pmod-a --build-dir build-esp32-tx-probe --record-build
