#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
profile="${1:-rfs2}"
case "$profile" in
  rfs2) build=build-esp32 ; defaults="$PWD/unified/sdkconfig.defaults" ;;
  pmod|pmod-a|pmod-b) build=build-esp32-pmod ; defaults="$PWD/unified/sdkconfig.defaults;$PWD/unified/sdkconfig.pmod.defaults" ;;
  *) echo 'Usage: bash scripts/build_firmware.sh rfs2|pmod' >&2; exit 2 ;;
esac
idf_sdk="${ATUM_ESP_IDF:-$PWD/vendor/esp-idf-sdr}"
if [[ ! -f "$idf_sdk/export.sh" || ! -d vendor/esp-sdr ]]; then
  python3 scripts/fetch.py firmware
fi
if [[ ! -f "$idf_sdk/export.sh" ]]; then echo "Missing ESP-IDF: $idf_sdk" >&2; exit 1; fi
# SDK installation mutates a shared tools cache. Serialize setup and reuse a
# healthy environment so independent profile builds never reinstall it together.
idf_cache="${IDF_TOOLS_PATH:-$HOME/.espressif}"
mkdir -p "$idf_cache"
exec {idf_setup_lock}>"$idf_cache/.atum-install.lock"
flock "$idf_setup_lock"
if ! (source "$idf_sdk/export.sh" >/dev/null 2>&1); then
  "$idf_sdk/install.sh" esp32
fi
flock -u "$idf_setup_lock"
source "$idf_sdk/export.sh"
# A separate SDK config per profile prevents one module's pin settings leaking into another.
idf.py -C unified -B "$PWD/$build" -D IDF_TARGET=esp32 \
  -D "SDKCONFIG=$PWD/$build/sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" build
python scripts/flash_esp32.py --module "$profile" --build-dir "$build" --record-build
