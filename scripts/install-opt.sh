#!/usr/bin/env bash
set -euo pipefail

# Installiert und startet BPSTracker immer unter /opt/bpstracker.
"$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/deploy-opt.sh"
