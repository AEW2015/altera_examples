#!/usr/bin/env bash
# Separate SPI-only synthetic transport image. Build only; never flash/start RF.
set -euo pipefail
cd "$(dirname "$0")/.."
idf_sdk="${ATUM_ESP_IDF:-$PWD/vendor/esp-idf-sdr}"
if [[ ! -f "$idf_sdk/export.sh" ]]; then
 echo 'Fetch pinned SDK first: python scripts/fetch.py firmware' >&2;exit 1
fi
if [[ "$(git -C "$idf_sdk" rev-parse HEAD)" != 25fe69f946311abdaf9ad56591f25fedbc20ac98 ]]; then
 echo 'SPI probe requires repository-pinned SDR SDK' >&2;exit 1
fi
source "$idf_sdk/export.sh"
case "${1:-synthetic}" in
 synthetic) project=firmware/esp32_spi_probe;build=build-esp32-spi-probe;defaults="$PWD/firmware/esp32_spi_probe/sdkconfig.defaults";extra=() ;;
 rf) project=unified;build=build-esp32-spi-rx;defaults="$PWD/unified/sdkconfig.defaults";extra=(-D IQ_SPI_RX_PROFILE=ON) ;;
 *) echo 'Usage: bash scripts/build_spi_probe.sh synthetic|rf' >&2;exit 2 ;;
esac
idf.py -C "$project" -B "$PWD/$build" -D IDF_TARGET=esp32 \
 -D "SDKCONFIG=$PWD/$build/sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" "${extra[@]}" build

python scripts/flash_esp32.py --module pmod-b --build-dir "$build" --record-build
