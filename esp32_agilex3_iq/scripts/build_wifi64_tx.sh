#!/usr/bin/env bash
# Build only. Does not program hardware or transmit.
set -euo pipefail
cd "$(dirname "$0")/.."
idf_sdk="${ATUM_ESP_IDF:-$PWD/vendor/esp-idf-sdr}"
[[ -f "$idf_sdk/export.sh" ]] || { echo 'Fetch pinned SDK: python scripts/fetch.py firmware' >&2; exit 1; }
[[ "$(git -C "$idf_sdk" rev-parse HEAD)" == 25fe69f946311abdaf9ad56591f25fedbc20ac98 ]] || { echo 'Wrong SDK commit' >&2; exit 1; }
source "$idf_sdk/export.sh"
idf.py -C firmware/wifi64_tx -B "$PWD/build-wifi64-tx" -D IDF_TARGET=esp32 \
 -D "SDKCONFIG=$PWD/build-wifi64-tx/sdkconfig" -D "SDKCONFIG_DEFAULTS=$PWD/firmware/wifi64_tx/sdkconfig.defaults" build
python scripts/flash_esp32.py --module pmod-a --build-dir build-wifi64-tx --record-build
