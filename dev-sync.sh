#!/usr/bin/env bash
# NeuronOS Development Sync Script
# Syncs code changes to a running NeuronOS VM without rebuilding the ISO
#
# Usage:
#   ./dev-sync.sh <vm-ip>
#   ./dev-sync.sh 192.168.56.101
#
# Prerequisites:
#   - SSH access to the VM (enable sshd in the live ISO)
#   - The VM should have the liveuser account

set -euo pipefail

VM_IP="${1:-}"
VM_USER="liveuser"
REMOTE_PATH="/usr/lib/neuron-os"
DATA_PATH="/usr/share/neuron-os"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ -z "$VM_IP" ]]; then
    echo -e "${RED}Usage: $0 <vm-ip>${NC}"
    echo ""
    echo "This script syncs your local code changes to a running NeuronOS VM."
    echo ""
    echo "Steps to use:"
    echo "  1. Boot NeuronOS in VirtualBox/VMware"
    echo "  2. In the VM, run: sudo systemctl start sshd"
    echo "  3. Get the VM's IP: ip addr show"
    echo "  4. Run this script: ./dev-sync.sh 192.168.x.x"
    echo ""
    echo "The script will sync your code and restart the apps for hot-reload."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${GREEN}[DEV]${NC} Syncing code to NeuronOS VM at $VM_IP..."

# Sync Python modules
echo -e "${YELLOW}[SYNC]${NC} Syncing Python modules..."
rsync -avz --delete \
    "${SCRIPT_DIR}/src/hardware_detect/" \
    "${VM_USER}@${VM_IP}:${REMOTE_PATH}/hardware_detect/"

rsync -avz --delete \
    "${SCRIPT_DIR}/src/vm_manager/" \
    "${VM_USER}@${VM_IP}:${REMOTE_PATH}/vm_manager/"

rsync -avz --delete \
    "${SCRIPT_DIR}/src/store/" \
    "${VM_USER}@${VM_IP}:${REMOTE_PATH}/store/"

# Sync data files
echo -e "${YELLOW}[SYNC]${NC} Syncing data files..."
rsync -avz \
    "${SCRIPT_DIR}/data/" \
    "${VM_USER}@${VM_IP}:${DATA_PATH}/"

# Sync VM templates
rsync -avz \
    "${SCRIPT_DIR}/src/vm_manager/templates/" \
    "${VM_USER}@${VM_IP}:${DATA_PATH}/templates/"

echo -e "${GREEN}[DEV]${NC} Sync complete!"
echo ""
echo -e "${YELLOW}[TIP]${NC} To test changes:"
echo "  - NeuronStore: Close and reopen the app"
echo "  - VM Manager: Close and reopen the app"
echo "  - Or restart the whole session: Log out and back in"
