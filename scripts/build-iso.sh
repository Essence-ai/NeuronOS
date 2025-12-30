#!/bin/bash
#
# NeuronOS ISO Build Script
# Builds the NeuronOS live/install ISO using archiso
#
# Usage: sudo ./build-iso.sh [clean]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE_DIR="$PROJECT_DIR/iso-profile"
WORK_DIR="/tmp/neuron-archiso-work"
OUTPUT_DIR="$PROJECT_DIR/output"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       NeuronOS ISO Builder             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run as root (sudo)${NC}"
    exit 1
fi

# Handle clean argument
if [ "$1" == "clean" ]; then
    echo -e "${YELLOW}Cleaning build artifacts...${NC}"
    rm -rf "$WORK_DIR"
    rm -rf "$OUTPUT_DIR"/*.iso
    echo -e "${GREEN}Clean complete.${NC}"
    exit 0
fi

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"

if ! command -v mkarchiso &> /dev/null; then
    echo -e "${YELLOW}archiso not found. Installing...${NC}"
    pacman -S --noconfirm archiso
fi

if ! command -v mksquashfs &> /dev/null; then
    echo -e "${YELLOW}squashfs-tools not found. Installing...${NC}"
    pacman -S --noconfirm squashfs-tools
fi

# Verify profile exists
if [ ! -f "$PROFILE_DIR/profiledef.sh" ]; then
    echo -e "${RED}Error: Profile not found at $PROFILE_DIR${NC}"
    exit 1
fi

# Clean previous build
echo -e "${YELLOW}Cleaning previous build...${NC}"
rm -rf "$WORK_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy Python packages to airootfs
echo -e "${BLUE}Copying NeuronOS Python packages...${NC}"

AIROOTFS_LIB="$PROFILE_DIR/airootfs/usr/lib/neuron-os"
mkdir -p "$AIROOTFS_LIB"

# Copy source packages
for pkg in hardware_detect vm_manager store onboarding migration updater; do
    if [ -d "$PROJECT_DIR/src/$pkg" ]; then
        echo "  Copying $pkg..."
        cp -r "$PROJECT_DIR/src/$pkg" "$AIROOTFS_LIB/"
    fi
done

# Copy templates
if [ -d "$PROJECT_DIR/templates" ]; then
    echo "  Copying templates..."
    mkdir -p "$PROFILE_DIR/airootfs/usr/share/neuron-os/templates"
    cp -r "$PROJECT_DIR/templates"/* "$PROFILE_DIR/airootfs/usr/share/neuron-os/templates/"
fi

# Copy app catalog
if [ -f "$PROJECT_DIR/data/apps.json" ]; then
    echo "  Copying app catalog..."
    mkdir -p "$PROFILE_DIR/airootfs/usr/share/neuron-os/data"
    cp "$PROJECT_DIR/data/apps.json" "$PROFILE_DIR/airootfs/usr/share/neuron-os/data/"
fi

# Create entry point scripts
echo -e "${BLUE}Creating entry point scripts...${NC}"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-hardware-detect" << 'EOF'
#!/usr/bin/env python3
"""NeuronOS Hardware Detection CLI."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from hardware_detect.cli import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-hardware-detect"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-vm-manager" << 'EOF'
#!/usr/bin/env python3
"""NeuronOS VM Manager."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from vm_manager.gui.app import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-vm-manager"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-store" << 'EOF'
#!/usr/bin/env python3
"""NeuronStore Application."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from store.gui.store_window import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-store"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-onboarding" << 'EOF'
#!/usr/bin/env python3
"""NeuronOS First-Boot Onboarding Wizard."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from onboarding.wizard import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-onboarding"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-migrate" << 'EOF'
#!/usr/bin/env python3
"""NeuronOS Migration Tool."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from migration.cli import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-migrate"

cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-update" << 'EOF'
#!/usr/bin/env python3
"""NeuronOS Update Manager."""
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from updater.cli import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$PROFILE_DIR/airootfs/usr/bin/neuron-update"

# Build ISO
echo -e "${BLUE}Building ISO...${NC}"
echo "  Profile: $PROFILE_DIR"
echo "  Work dir: $WORK_DIR"
echo "  Output: $OUTPUT_DIR"

mkarchiso -v -w "$WORK_DIR" -o "$OUTPUT_DIR" "$PROFILE_DIR"

# Report result
ISO_FILE=$(ls -1 "$OUTPUT_DIR"/neuronos-*.iso 2>/dev/null | head -1)

if [ -n "$ISO_FILE" ] && [ -f "$ISO_FILE" ]; then
    ISO_SIZE=$(du -h "$ISO_FILE" | cut -f1)
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          Build Complete!               ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "ISO: ${BLUE}$ISO_FILE${NC}"
    echo -e "Size: ${BLUE}$ISO_SIZE${NC}"
    echo ""
    echo "To test in QEMU:"
    echo "  qemu-system-x86_64 -enable-kvm -m 4G -cpu host -boot d -cdrom $ISO_FILE"
    echo ""
    echo "To write to USB (replace /dev/sdX):"
    echo "  sudo dd if=$ISO_FILE of=/dev/sdX bs=4M status=progress oflag=sync"
else
    echo -e "${RED}Build failed - no ISO file produced${NC}"
    exit 1
fi
