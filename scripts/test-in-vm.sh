#!/bin/bash
#
# NeuronOS Quick Test Script
# Tests the built ISO in QEMU
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/output"

# Find ISO
ISO_FILE=$(ls -1t "$OUTPUT_DIR"/neuronos-*.iso 2>/dev/null | head -1)

if [ -z "$ISO_FILE" ] || [ ! -f "$ISO_FILE" ]; then
    echo "Error: No ISO found in $OUTPUT_DIR"
    echo "Run 'sudo ./scripts/build-iso.sh' first"
    exit 1
fi

echo "Testing ISO: $ISO_FILE"
echo ""

# Default settings
RAM="${RAM:-4G}"
CPUS="${CPUS:-2}"
UEFI="${UEFI:-1}"

# Check for OVMF
OVMF_CODE="/usr/share/edk2-ovmf/x64/OVMF_CODE.fd"
OVMF_VARS="/usr/share/edk2-ovmf/x64/OVMF_VARS.fd"

if [ "$UEFI" == "1" ] && [ -f "$OVMF_CODE" ]; then
    echo "Using UEFI boot..."

    # Create temporary VARS copy
    TEMP_VARS=$(mktemp)
    cp "$OVMF_VARS" "$TEMP_VARS"

    qemu-system-x86_64 \
        -enable-kvm \
        -m "$RAM" \
        -cpu host \
        -smp "$CPUS" \
        -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
        -drive if=pflash,format=raw,file="$TEMP_VARS" \
        -cdrom "$ISO_FILE" \
        -boot d \
        -vga virtio \
        -display gtk \
        -device virtio-net-pci,netdev=net0 \
        -netdev user,id=net0

    rm -f "$TEMP_VARS"
else
    echo "Using BIOS boot..."

    qemu-system-x86_64 \
        -enable-kvm \
        -m "$RAM" \
        -cpu host \
        -smp "$CPUS" \
        -cdrom "$ISO_FILE" \
        -boot d \
        -vga virtio \
        -display gtk \
        -device virtio-net-pci,netdev=net0 \
        -netdev user,id=net0
fi
