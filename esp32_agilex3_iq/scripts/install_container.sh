#!/usr/bin/env bash
# Compatibility alias; this installer also runs on a regular Linux host.
exec bash "$(dirname "$0")/install_local.sh" "$@"
