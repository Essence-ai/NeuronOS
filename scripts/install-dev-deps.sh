#!/bin/bash
#
# NeuronOS Development Dependencies Installer
# Installs all dependencies needed for development
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "╔════════════════════════════════════════╗"
echo "║  NeuronOS Development Setup            ║"
echo "╚════════════════════════════════════════╝"

# Detect package manager
if command -v pacman &> /dev/null; then
    echo "Detected Arch Linux"
    PKG_MANAGER="pacman"
elif command -v apt &> /dev/null; then
    echo "Detected Debian/Ubuntu (limited support)"
    PKG_MANAGER="apt"
elif command -v dnf &> /dev/null; then
    echo "Detected Fedora (limited support)"
    PKG_MANAGER="dnf"
else
    echo "Error: Unsupported distribution"
    echo "NeuronOS development requires Arch Linux"
    exit 1
fi

# Install system packages
echo ""
echo "Installing system packages..."

if [ "$PKG_MANAGER" == "pacman" ]; then
    sudo pacman -S --needed --noconfirm \
        base-devel \
        python python-pip python-gobject python-jinja \
        gtk4 libadwaita \
        libvirt libvirt-python qemu-full \
        virt-manager edk2-ovmf swtpm \
        archiso \
        git vim nano \
        python-pytest python-pytest-cov
fi

# Enable libvirt
echo ""
echo "Configuring libvirt..."

sudo systemctl enable --now libvirtd.service
sudo usermod -aG libvirt "$USER"
sudo usermod -aG kvm "$USER"

# Set up Python environment
echo ""
echo "Setting up Python environment..."

cd "$PROJECT_DIR"

# Create virtual environment (optional)
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python -m venv .venv
fi

# Install Python dependencies
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

pip install --upgrade pip
pip install -e ".[dev]" 2>/dev/null || pip install -r requirements.txt

# Verify installation
echo ""
echo "Verifying installation..."

python -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('GTK4: OK')"
python -c "import gi; gi.require_version('Adw', '1'); from gi.repository import Adw; print('Adwaita: OK')"
python -c "import libvirt; print('libvirt-python: OK')"
python -c "import jinja2; print('Jinja2: OK')"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Setup Complete!                       ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Log out and back in (for group membership)"
echo "  2. Run 'make test' to verify setup"
echo "  3. Run 'sudo make iso' to build the ISO"
echo ""
echo "Quick commands:"
echo "  python -m vm_manager      # Run VM Manager"
echo "  python -m store           # Run NeuronStore"
echo "  python -m onboarding      # Run Onboarding Wizard"
echo ""
