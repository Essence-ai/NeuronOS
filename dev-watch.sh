#!/usr/bin/env bash
# NeuronOS Development Watch Mode
# Watches for file changes and auto-syncs to VM
#
# Usage:
#   ./dev-watch.sh <vm-ip>
#
# Requires: inotify-tools (sudo pacman -S inotify-tools)

set -euo pipefail

VM_IP="${1:-}"

if [[ -z "$VM_IP" ]]; then
    echo "Usage: $0 <vm-ip>"
    echo "Watches for changes and auto-syncs to NeuronOS VM."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[WATCH] Watching for changes... (Ctrl+C to stop)"
echo "[WATCH] Syncing to $VM_IP"

# Initial sync
"${SCRIPT_DIR}/dev-sync.sh" "$VM_IP"

# Watch for changes
inotifywait -m -r -e modify,create,delete \
    --exclude '(__pycache__|\.pyc|\.git)' \
    "${SCRIPT_DIR}/src" "${SCRIPT_DIR}/data" |
while read -r directory events filename; do
    echo "[CHANGE] $directory$filename"
    "${SCRIPT_DIR}/dev-sync.sh" "$VM_IP" 2>/dev/null || true
done
