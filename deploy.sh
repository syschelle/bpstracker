#!/usr/bin/env bash
set -euo pipefail

# Komfort-Wrapper: deployt BPSTracker immer nach /opt/bpstracker.
# Wichtig: Wir starten das Zielskript explizit mit bash. Dadurch funktioniert
# der Deploy auch, wenn beim Entpacken Execute-Bits verloren gegangen sind
# oder das Quellverzeichnis mit noexec gemountet ist.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/deploy-opt.sh"
