#!/usr/bin/env bash
set -euo pipefail

# Installiert und startet BPSTracker immer unter /opt/bpstracker.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/deploy-opt.sh" "$@"
