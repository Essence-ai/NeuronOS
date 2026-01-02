#!/usr/bin/env bash
# NeuronOS ISO Build Script
# Builds the NeuronOS live ISO using archiso

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/work"
OUT_DIR="${SCRIPT_DIR}/out"
PROFILE_DIR="${SCRIPT_DIR}/iso-profile"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    log_info "Checking build requirements..."

    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    local required_pkgs=("archiso" "arch-install-scripts" "squashfs-tools")
    local missing=()

    for pkg in "${required_pkgs[@]}"; do
        if ! pacman -Qi "$pkg" &>/dev/null; then
            missing+=("$pkg")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing packages: ${missing[*]}"
        log_info "Install with: pacman -S ${missing[*]}"
        exit 1
    fi

    log_info "All requirements satisfied"
}

clean_work_dir() {
    if [[ -d "$WORK_DIR" ]]; then
        log_info "Cleaning work directory..."
        rm -rf "$WORK_DIR"
    fi
    mkdir -p "$WORK_DIR"
    mkdir -p "$OUT_DIR"
}

copy_python_modules() {
    log_info "Copying NeuronOS Python modules to ISO profile..."

    local neuron_lib="${PROFILE_DIR}/airootfs/usr/lib/neuron-os"
    mkdir -p "$neuron_lib"

    # Copy Python source modules
    cp -r "${SCRIPT_DIR}/src/hardware_detect" "$neuron_lib/"
    cp -r "${SCRIPT_DIR}/src/vm_manager" "$neuron_lib/"
    cp -r "${SCRIPT_DIR}/src/store" "$neuron_lib/"

    # Copy data files
    mkdir -p "${PROFILE_DIR}/airootfs/usr/share/neuron-os"
    cp -r "${SCRIPT_DIR}/data"/* "${PROFILE_DIR}/airootfs/usr/share/neuron-os/" 2>/dev/null || true

    # Copy VM templates
    mkdir -p "${PROFILE_DIR}/airootfs/usr/share/neuron-os/templates"
    cp "${SCRIPT_DIR}/src/vm_manager/templates"/*.j2 "${PROFILE_DIR}/airootfs/usr/share/neuron-os/templates/" 2>/dev/null || true

    log_info "Python modules copied successfully"
}

enable_services() {
    log_info "Setting up systemd service symlinks..."

    # Create systemd symlink directories
    local systemd_dir="${PROFILE_DIR}/airootfs/etc/systemd/system"
    mkdir -p "${systemd_dir}/multi-user.target.wants"
    mkdir -p "${systemd_dir}/graphical.target.wants"

    # Enable SDDM for graphical login (LXQt display manager)
    ln -sf /usr/lib/systemd/system/sddm.service "${systemd_dir}/display-manager.service"

    # Enable NetworkManager
    ln -sf /usr/lib/systemd/system/NetworkManager.service "${systemd_dir}/multi-user.target.wants/NetworkManager.service"

    # Enable libvirtd for VM management
    ln -sf /usr/lib/systemd/system/libvirtd.service "${systemd_dir}/multi-user.target.wants/libvirtd.service"

    log_info "Systemd services configured"
}

build_iso() {
    log_info "Building NeuronOS ISO..."

    # Copy our code into the profile before building
    copy_python_modules

    # Enable systemd services
    enable_services

    mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" "$PROFILE_DIR"

    local iso_file
    iso_file=$(ls -t "$OUT_DIR"/*.iso 2>/dev/null | head -1)

    if [[ -n "$iso_file" ]]; then
        log_info "ISO built successfully: $iso_file"
        log_info "Size: $(du -h "$iso_file" | cut -f1)"
    else
        log_error "ISO build failed - no output file found"
        exit 1
    fi
}

show_usage() {
    cat << EOF
NeuronOS ISO Build Script

Usage: $0 [OPTIONS]

Options:
    -c, --clean     Clean work directory before build
    -h, --help      Show this help message

Examples:
    $0              Build ISO
    $0 --clean      Clean and build ISO
EOF
}

main() {
    local do_clean=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -c|--clean)
                do_clean=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    log_info "=== NeuronOS ISO Builder ==="

    check_requirements

    if [[ "$do_clean" == true ]]; then
        clean_work_dir
    fi

    build_iso

    log_info "=== Build Complete ==="
}

main "$@"
