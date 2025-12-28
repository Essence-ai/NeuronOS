# NeuronOS Implementation Guide

## Complete Repository Setup & Development Roadmap for Claude Code Agent

**Created:** December 28, 2025
**Purpose:** Enable Claude Code (or any coding agent) to implement NeuronOS from scratch

---

## Document Analysis & Realism Assessment

### Dev Guide Accuracy Review

| Phase | Accuracy | Issues Found | Verdict |
|-------|----------|--------------|---------|
| **Phase 0** | 95% | Minor: Windows 11 LTSC ISO source may require legit license | Realistic |
| **Phase 1** | 90% | Calamares integration complexity underestimated | Realistic with caveats |
| **Phase 2** | 85% | GTK4/Adwaita learning curve, libvirt-python edge cases | Achievable |
| **Phase 3-5** | 80% | macOS VM very fragile, enterprise features ambitious | Partially realistic |

### Key Issues Identified

1. **Phase 0**: The BIOS settings may vary significantly by manufacturer - some laptops don't expose IOMMU settings
2. **Phase 1**: `looking-glass` AUR package may have build issues; should use official build
3. **Phase 2**: The NeuronGuest C# agent assumes Windows can receive commands via named pipe from Linux - this requires QEMU guest agent or IVSHMEM communication, not named pipes
4. **Phase 3-5**: Bottles integration is not stable; better to use raw Wine or Lutris APIs

### Corrected Architecture Notes

```
NeuronGuest Communication (CORRECTED):
- Cannot use Windows named pipes from Linux host
- Must use: QEMU Guest Agent (qga) OR
- Custom IVSHMEM shared memory protocol OR
- virtio-serial channel

Recommended: virtio-serial with JSON protocol
```

---

## Repository Structure

Create this exact structure to begin development:

```
neuron-os/
├── .github/
│   ├── workflows/
│   │   ├── build-iso.yml          # GitHub Actions to build ISO
│   │   └── test-vm.yml            # Test VM creation
│   └── ISSUE_TEMPLATE/
│       └── bug_report.md
│
├── iso-profile/                    # Archiso custom profile
│   ├── airootfs/                   # Files included in live ISO
│   │   ├── etc/
│   │   │   ├── calamares/          # Installer config
│   │   │   │   ├── settings.conf
│   │   │   │   ├── modules/
│   │   │   │   │   └── neuron-vfio/
│   │   │   │   │       ├── module.desc
│   │   │   │   │       └── main.py
│   │   │   │   └── branding/
│   │   │   │       └── neuron/
│   │   │   │           ├── branding.desc
│   │   │   │           └── show.qml
│   │   │   ├── modprobe.d/         # Module configs (populated at install)
│   │   │   ├── skel/               # Default user files
│   │   │   │   └── .config/
│   │   │   │       └── autostart/
│   │   │   └── tmpfiles.d/
│   │   │       └── 10-looking-glass.conf
│   │   └── usr/
│   │       ├── lib/
│   │       │   └── neuron-os/      # Our Python packages
│   │       │       ├── __init__.py
│   │       │       ├── hardware_detect/
│   │       │       ├── vm_manager/
│   │       │       └── store/
│   │       ├── share/
│   │       │   ├── applications/
│   │       │   │   └── neuron-vm-manager.desktop
│   │       │   ├── neuron-os/
│   │       │   │   ├── icons/
│   │       │   │   └── templates/
│   │       │   │       └── windows11.xml.j2
│   │       │   └── neuron-store/
│   │       │       └── apps.json
│   │       └── bin/
│   │           ├── neuron-hardware-detect
│   │           ├── neuron-vm-manager
│   │           └── neuron-store
│   ├── efiboot/
│   ├── syslinux/
│   ├── packages.x86_64             # Package list
│   ├── pacman.conf
│   └── profiledef.sh
│
├── src/                            # Source code
│   ├── hardware_detect/            # Hardware detection module
│   │   ├── __init__.py
│   │   ├── gpu_scanner.py
│   │   ├── iommu_parser.py
│   │   ├── cpu_detect.py
│   │   └── config_generator.py
│   │
│   ├── vm_manager/                 # NeuronVM Manager
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── libvirt_manager.py
│   │   │   ├── vm_profile.py
│   │   │   └── looking_glass.py
│   │   ├── gui/
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py
│   │   │   ├── vm_card.py
│   │   │   └── settings_dialog.py
│   │   └── main.py
│   │
│   ├── store/                      # NeuronStore
│   │   ├── __init__.py
│   │   ├── catalog.py
│   │   ├── install_engine.py
│   │   └── gui/
│   │       ├── __init__.py
│   │       └── store_window.py
│   │
│   └── guest_agent/                # Windows guest agent
│       ├── NeuronGuest/            # C# .NET project
│       │   ├── NeuronGuest.csproj
│       │   ├── Program.cs
│       │   ├── Worker.cs
│       │   ├── DisplayManager.cs
│       │   └── VirtioSerialListener.cs  # CORRECTED: Not named pipes
│       └── installer/
│           └── neuron-guest-setup.iss   # Inno Setup script
│
├── scripts/                        # Build and utility scripts
│   ├── build-iso.sh                # Build the ISO
│   ├── test-in-vm.sh               # Quick test in QEMU
│   ├── install-dev-deps.sh         # Install dev dependencies
│   └── package-python.sh           # Package Python modules
│
├── templates/                      # VM XML templates
│   ├── windows11-passthrough.xml.j2
│   ├── windows11-basic.xml.j2
│   └── macos-sonoma.xml.j2
│
├── data/                           # Static data files
│   ├── apps.json                   # App catalog
│   ├── hardware-db/                # Known hardware configs
│   │   ├── gpus.json
│   │   └── motherboards.json
│   └── icons/
│       ├── neuron-os-logo.svg
│       └── app-icons/
│
├── docs/                           # Documentation
│   ├── user-guide/
│   ├── developer-guide/
│   └── hardware-compatibility.md
│
├── tests/                          # Test suite
│   ├── test_gpu_scanner.py
│   ├── test_iommu_parser.py
│   ├── test_libvirt_manager.py
│   └── test_catalog.py
│
├── .gitignore
├── README.md
├── LICENSE                         # GPL-3.0
├── pyproject.toml                  # Python project config
├── requirements.txt                # Python dependencies
└── Makefile                        # Build automation
```

---

## Phase 0: What You Need Before Any Coding

### Hardware Requirements (for Development)

You MUST have:
- [ ] CPU with IOMMU support (Intel VT-d or AMD-Vi)
- [ ] Two GPUs: integrated (iGPU) + discrete (dGPU)
- [ ] 32GB+ RAM (16GB for host, 16GB for VM)
- [ ] 500GB+ SSD
- [ ] Monitor connected to dGPU (or HDMI dummy plug)

### Pre-Flight Checklist

Before any code is written, manually verify:

```bash
# 1. Check IOMMU enabled
dmesg | grep -i iommu
# Expected: "IOMMU enabled" or "AMD-Vi: Interrupt remapping enabled"

# 2. List IOMMU groups
for g in $(find /sys/kernel/iommu_groups/* -maxdepth 0 -type d | sort -V); do
    echo "IOMMU Group ${g##*/}:"
    for d in $g/devices/*; do
        echo -e "\t$(lspci -nns ${d##*/})"
    done
done

# 3. Identify your GPUs
lspci -nn | grep -i vga
# You should see TWO entries (iGPU and dGPU)

# 4. Check boot_vga (which GPU is primary)
for card in /sys/class/drm/card*/device/boot_vga; do
    echo "$card: $(cat $card)"
done
```

---

## Step-by-Step Implementation for Claude Code

### Step 1: Initialize Repository

```bash
# Create base structure
mkdir -p neuron-os/{.github/workflows,iso-profile/{airootfs/{etc/{calamares/modules/neuron-vfio,modprobe.d,skel/.config/autostart,tmpfiles.d},usr/{lib/neuron-os/{hardware_detect,vm_manager,store},share/{applications,neuron-os/{icons,templates},neuron-store},bin}},efiboot,syslinux},src/{hardware_detect,vm_manager/{core,gui},store/gui,guest_agent/NeuronGuest},scripts,templates,data/{hardware-db,icons/app-icons},docs/{user-guide,developer-guide},tests}

cd neuron-os
git init
```

### Step 2: Create Core Files

#### `pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "neuron-os"
version = "0.1.0"
description = "NeuronOS system utilities"
requires-python = ">=3.11"
dependencies = [
    "libvirt-python>=9.0.0",
    "PyGObject>=3.42.0",
    "Jinja2>=3.1.0",
    "pyudev>=0.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov",
    "black",
    "mypy",
]

[project.scripts]
neuron-hardware-detect = "hardware_detect.cli:main"
neuron-vm-manager = "vm_manager.main:main"
neuron-store = "store.main:main"

[tool.setuptools.packages.find]
where = ["src"]
```

#### `requirements.txt`
```
libvirt-python>=9.0.0
PyGObject>=3.42.0
Jinja2>=3.1.0
pyudev>=0.24.0
pytest>=7.0.0
```

#### `.gitignore`
```
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
*.iso
/work/
/output/
.venv/
venv/
*.qcow2
*.img
.mypy_cache/
```

#### `Makefile`
```makefile
.PHONY: iso clean test install-deps

PROFILE_DIR = iso-profile
WORK_DIR = /tmp/neuron-archiso-work
OUTPUT_DIR = output

install-deps:
	sudo pacman -S archiso python python-pip
	pip install -e ".[dev]"

test:
	pytest tests/ -v

iso: clean
	sudo mkarchiso -v -w $(WORK_DIR) -o $(OUTPUT_DIR) $(PROFILE_DIR)
	@echo "ISO built: $(OUTPUT_DIR)/neuron-*.iso"

clean:
	sudo rm -rf $(WORK_DIR)
	rm -rf $(OUTPUT_DIR)/*.iso

test-vm:
	qemu-system-x86_64 \
		-enable-kvm \
		-m 4G \
		-cpu host \
		-boot d \
		-cdrom $(OUTPUT_DIR)/neuron-*.iso
```

### Step 3: Implement Hardware Detection Module First

Create these files in order:

#### `src/hardware_detect/__init__.py`
```python
"""NeuronOS Hardware Detection Module."""
from .gpu_scanner import GPUScanner, GPUDevice
from .iommu_parser import IOMMUParser, IOMMUGroup
from .config_generator import ConfigGenerator, VFIOConfig

__all__ = [
    "GPUScanner",
    "GPUDevice",
    "IOMMUParser",
    "IOMMUGroup",
    "ConfigGenerator",
    "VFIOConfig",
]
```

#### `src/hardware_detect/gpu_scanner.py`
(Use the code from dev_guide_phase_1.md - it's accurate)

#### `src/hardware_detect/iommu_parser.py`
(Use the code from dev_guide_phase_1.md - it's accurate)

#### `src/hardware_detect/cpu_detect.py`
```python
#!/usr/bin/env python3
"""CPU detection for IOMMU configuration."""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class CPUInfo:
    """CPU information."""
    vendor: str  # "Intel" or "AMD"
    model_name: str
    cores: int
    threads: int
    has_iommu: bool
    iommu_param: str  # "intel_iommu=on" or "amd_iommu=on"


class CPUDetector:
    """Detects CPU capabilities for VFIO configuration."""

    CPUINFO_PATH = Path("/proc/cpuinfo")

    def detect(self) -> CPUInfo:
        """Detect CPU information."""
        content = self.CPUINFO_PATH.read_text()

        # Parse vendor
        vendor = "Unknown"
        if "GenuineIntel" in content:
            vendor = "Intel"
        elif "AuthenticAMD" in content:
            vendor = "AMD"

        # Parse model name
        model_name = "Unknown"
        for line in content.split("\n"):
            if line.startswith("model name"):
                model_name = line.split(":")[1].strip()
                break

        # Count cores and threads
        cores = content.count("processor\t:")

        # Determine IOMMU parameter
        if vendor == "Intel":
            iommu_param = "intel_iommu=on iommu=pt"
        elif vendor == "AMD":
            iommu_param = "amd_iommu=on iommu=pt"
        else:
            iommu_param = "iommu=pt"

        # Check if IOMMU is supported (check kernel messages)
        has_iommu = self._check_iommu_support()

        return CPUInfo(
            vendor=vendor,
            model_name=model_name,
            cores=cores,
            threads=cores,  # Simplified
            has_iommu=has_iommu,
            iommu_param=iommu_param,
        )

    def _check_iommu_support(self) -> bool:
        """Check if IOMMU is enabled in the kernel."""
        try:
            dmesg = Path("/var/log/dmesg").read_text()
            return "IOMMU enabled" in dmesg or "AMD-Vi" in dmesg
        except:
            # Try running dmesg
            import subprocess
            try:
                result = subprocess.run(
                    ["dmesg"], capture_output=True, text=True
                )
                return "IOMMU enabled" in result.stdout or "AMD-Vi" in result.stdout
            except:
                return False


if __name__ == "__main__":
    detector = CPUDetector()
    info = detector.detect()
    print(f"CPU: {info.model_name}")
    print(f"Vendor: {info.vendor}")
    print(f"Cores: {info.cores}")
    print(f"IOMMU Param: {info.iommu_param}")
    print(f"IOMMU Enabled: {info.has_iommu}")
```

#### `src/hardware_detect/config_generator.py`
(Use the code from dev_guide_phase_1.md with this fix for bootloader detection)

```python
#!/usr/bin/env python3
"""VFIO Configuration Generator - CORRECTED VERSION."""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from .gpu_scanner import GPUScanner, GPUDevice
from .iommu_parser import IOMMUParser
from .cpu_detect import CPUDetector


@dataclass
class VFIOConfig:
    """Generated VFIO configuration."""
    vfio_conf: str
    mkinitcpio_modules: str
    kernel_params: str
    bootloader: str  # "grub" or "systemd-boot"
    warnings: List[str]


class ConfigGenerator:
    """Generates VFIO configuration files."""

    def __init__(self):
        self.scanner = GPUScanner()
        self.iommu_parser = IOMMUParser()
        self.cpu_detector = CPUDetector()

    def detect_bootloader(self, target_root: Path = Path("/")) -> str:
        """Detect which bootloader is installed."""
        grub_cfg = target_root / "boot/grub/grub.cfg"
        systemd_boot = target_root / "boot/loader/loader.conf"

        if systemd_boot.exists():
            return "systemd-boot"
        elif grub_cfg.exists():
            return "grub"
        else:
            return "unknown"

    def detect_and_generate(self) -> VFIOConfig:
        """Run full detection and generate configs."""
        warnings = []

        # Detect CPU
        cpu = self.cpu_detector.detect()

        if not cpu.has_iommu:
            warnings.append(
                "IOMMU not detected! Add kernel parameter and reboot: " + cpu.iommu_param
            )

        # Scan GPUs
        gpus = self.scanner.scan()

        if not gpus:
            raise RuntimeError("No GPUs detected!")

        if len(gpus) < 2:
            warnings.append(
                "Only one GPU detected. Single-GPU passthrough requires special handling."
            )

        # Get passthrough candidate
        candidate = self.scanner.get_passthrough_candidate()

        if not candidate:
            raise RuntimeError("No suitable GPU for passthrough (all GPUs are boot VGA)")

        # Parse IOMMU groups
        try:
            self.iommu_parser.parse_all()
            gpu_group = self.iommu_parser.get_gpu_group(candidate.pci_address)

            if gpu_group and not gpu_group.is_clean:
                warnings.append(
                    f"IOMMU group {gpu_group.group_id} contains other devices. "
                    "ACS Override Patch may be required."
                )
        except RuntimeError as e:
            warnings.append(str(e))
            gpu_group = None

        # Collect all PCI IDs for the GPU + audio
        pci_ids = self._get_all_pci_ids(candidate, gpu_group)

        # Generate configs
        vfio_conf = self._generate_vfio_conf(pci_ids, candidate)
        mkinitcpio = self._generate_mkinitcpio()
        kernel_params = cpu.iommu_param
        bootloader = self.detect_bootloader()

        return VFIOConfig(
            vfio_conf=vfio_conf,
            mkinitcpio_modules=mkinitcpio,
            kernel_params=kernel_params,
            bootloader=bootloader,
            warnings=warnings,
        )

    def _get_all_pci_ids(self, gpu: GPUDevice, group) -> List[str]:
        """Get all PCI IDs that should be bound to vfio-pci."""
        ids = [f"{gpu.vendor_id}:{gpu.device_id}"]

        if group:
            for device in group.devices:
                if "Audio" in device.description or "0403" in device.device_class:
                    # Extract vendor:device from description
                    if "[" in device.description:
                        id_match = device.description.split("[")[-1].rstrip("]")
                        if ":" in id_match and id_match not in ids:
                            ids.append(id_match)

        return ids

    def _generate_vfio_conf(self, pci_ids: List[str], gpu: GPUDevice) -> str:
        """Generate /etc/modprobe.d/vfio.conf content."""
        ids_str = ",".join(pci_ids)

        return f"""# NeuronOS VFIO Configuration
# Auto-generated for GPU passthrough
# Target GPU: {gpu.vendor_name} @ {gpu.pci_address}

# Bind these devices to vfio-pci driver
options vfio-pci ids={ids_str}

# Ensure vfio-pci loads before GPU drivers
softdep nvidia pre: vfio-pci
softdep amdgpu pre: vfio-pci
softdep radeon pre: vfio-pci
softdep nouveau pre: vfio-pci
softdep i915 pre: vfio-pci
"""

    def _generate_mkinitcpio(self) -> str:
        """Generate MODULES line for mkinitcpio.conf."""
        return "MODULES=(vfio_pci vfio vfio_iommu_type1)"

    def apply_to_target(self, target_root: Path):
        """Apply generated configs to a target installation path."""
        config = self.detect_and_generate()

        # Write vfio.conf
        vfio_path = target_root / "etc/modprobe.d/vfio.conf"
        vfio_path.parent.mkdir(parents=True, exist_ok=True)
        vfio_path.write_text(config.vfio_conf)
        print(f"Written: {vfio_path}")

        # Update mkinitcpio.conf
        mkinitcpio_path = target_root / "etc/mkinitcpio.conf"
        if mkinitcpio_path.exists():
            import re
            content = mkinitcpio_path.read_text()
            content = re.sub(
                r'MODULES=\([^)]*\)',
                config.mkinitcpio_modules,
                content
            )
            mkinitcpio_path.write_text(content)
            print(f"Updated: {mkinitcpio_path}")

        # Update bootloader
        if config.bootloader == "grub":
            self._update_grub(target_root, config.kernel_params)
        elif config.bootloader == "systemd-boot":
            self._update_systemd_boot(target_root, config.kernel_params)

        # Print warnings
        for warning in config.warnings:
            print(f"WARNING: {warning}")

    def _update_grub(self, target_root: Path, params: str):
        """Update GRUB configuration."""
        import re
        grub_default = target_root / "etc/default/grub"
        if grub_default.exists():
            content = grub_default.read_text()
            # Add to GRUB_CMDLINE_LINUX_DEFAULT
            content = re.sub(
                r'(GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)',
                f'\\1 {params}',
                content
            )
            grub_default.write_text(content)
            print(f"Updated: {grub_default}")

    def _update_systemd_boot(self, target_root: Path, params: str):
        """Update systemd-boot configuration."""
        entries_dir = target_root / "boot/loader/entries"
        if entries_dir.exists():
            for entry in entries_dir.glob("*.conf"):
                content = entry.read_text()
                lines = content.split("\n")
                new_lines = []
                for line in lines:
                    if line.startswith("options "):
                        if params not in line:
                            line = f"{line} {params}"
                    new_lines.append(line)
                entry.write_text("\n".join(new_lines))
                print(f"Updated: {entry}")


if __name__ == "__main__":
    generator = ConfigGenerator()
    try:
        config = generator.detect_and_generate()

        print("=== Generated VFIO Configuration ===")
        print("\n--- /etc/modprobe.d/vfio.conf ---")
        print(config.vfio_conf)

        print("\n--- mkinitcpio.conf MODULES ---")
        print(config.mkinitcpio_modules)

        print("\n--- Kernel Parameters ---")
        print(config.kernel_params)

        print("\n--- Bootloader ---")
        print(config.bootloader)

        if config.warnings:
            print("\n--- Warnings ---")
            for w in config.warnings:
                print(f"  - {w}")

    except RuntimeError as e:
        print(f"ERROR: {e}")
```

### Step 4: Create the Archiso Profile

#### `iso-profile/packages.x86_64`
```
# Base System
base
linux
linux-firmware
linux-headers
mkinitcpio
sudo
networkmanager
btrfs-progs
dosfstools
e2fsprogs

# Desktop Environment
gnome
gnome-tweaks
gdm
xdg-user-dirs

# Virtualization Core
qemu-full
libvirt
virt-manager
edk2-ovmf
swtpm
dnsmasq

# Installer
calamares
os-prober
arch-install-scripts

# Development
python
python-pip
python-pyudev
python-gobject
python-jinja
libvirt-python
git
vim
base-devel

# Utilities
firefox
gnome-terminal
file-roller
nautilus
gnome-calculator
gnome-text-editor
gnome-system-monitor
baobab
```

#### `iso-profile/profiledef.sh`
```bash
#!/usr/bin/env bash
# NeuronOS ISO Profile Definition

iso_name="neuronos"
iso_label="NEURONOS_$(date +%Y%m)"
iso_publisher="NeuronOS Project"
iso_application="NeuronOS Live/Install Media"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('uefi-x64.systemd-boot.esp')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M')
file_permissions=(
    ["/etc/shadow"]="0:0:400"
    ["/usr/bin/neuron-hardware-detect"]="0:0:755"
    ["/usr/bin/neuron-vm-manager"]="0:0:755"
)
```

### Step 5: Create Essential Scripts

#### `scripts/build-iso.sh`
```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE_DIR="$PROJECT_DIR/iso-profile"
WORK_DIR="/tmp/neuron-archiso-work"
OUTPUT_DIR="$PROJECT_DIR/output"

echo "=== NeuronOS ISO Builder ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Check archiso is installed
if ! command -v mkarchiso &> /dev/null; then
    echo "archiso not found. Installing..."
    pacman -S --noconfirm archiso
fi

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$WORK_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy our Python packages to airootfs
echo "Copying NeuronOS packages..."
mkdir -p "$PROFILE_DIR/airootfs/usr/lib/neuron-os"
cp -r "$PROJECT_DIR/src/"* "$PROFILE_DIR/airootfs/usr/lib/neuron-os/"

# Create entry point scripts
cat > "$PROFILE_DIR/airootfs/usr/bin/neuron-hardware-detect" << 'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/lib/neuron-os")
from hardware_detect.config_generator import ConfigGenerator

if __name__ == "__main__":
    generator = ConfigGenerator()
    config = generator.detect_and_generate()
    print(config.vfio_conf)
EOF

# Build ISO
echo "Building ISO..."
mkarchiso -v -w "$WORK_DIR" -o "$OUTPUT_DIR" "$PROFILE_DIR"

echo ""
echo "=== Build Complete ==="
echo "ISO: $(ls -1 $OUTPUT_DIR/neuronos-*.iso 2>/dev/null | head -1)"
```

#### `scripts/install-dev-deps.sh`
```bash
#!/bin/bash
# Install development dependencies

echo "Installing NeuronOS development dependencies..."

# Check OS
if command -v pacman &> /dev/null; then
    # Arch Linux
    sudo pacman -S --needed \
        python python-pip python-gobject python-jinja libvirt-python \
        qemu-full libvirt virt-manager \
        archiso \
        gtk4 libadwaita
elif command -v apt &> /dev/null; then
    # Debian/Ubuntu (for development only)
    sudo apt install -y \
        python3 python3-pip python3-gi python3-libvirt \
        qemu-kvm libvirt-daemon-system virt-manager
fi

# Install Python packages
pip install -e ".[dev]"

echo "Done! Run 'make test' to verify."
```

---

## Development Workflow for Claude Code

### Working on Hardware Detection (Phase 1)

```bash
# 1. Create test file
cat > tests/test_gpu_scanner.py << 'EOF'
import pytest
from hardware_detect.gpu_scanner import GPUScanner

def test_scanner_initializes():
    scanner = GPUScanner()
    assert scanner is not None

def test_scan_returns_list():
    scanner = GPUScanner()
    # This will fail on systems without GPUs, that's expected
    try:
        gpus = scanner.scan()
        assert isinstance(gpus, list)
    except Exception:
        pytest.skip("No GPU hardware available")
EOF

# 2. Run tests
pytest tests/test_gpu_scanner.py -v

# 3. Iterate on code until tests pass
```

### Working on VM Manager (Phase 2)

```bash
# 1. Verify libvirt is running
sudo systemctl status libvirtd

# 2. Test libvirt connection
python3 -c "
import libvirt
conn = libvirt.open('qemu:///system')
print(f'Connected! {len(conn.listAllDomains())} VMs found')
conn.close()
"

# 3. Run GUI in development mode
cd src/vm_manager
python3 main.py
```

### Building and Testing ISO

```bash
# Full build
sudo make iso

# Quick test in VM
make test-vm
```

---

## Critical Path Summary

```
Week 1-2 (Phase 0):
├── Verify GPU passthrough works manually
├── Document hardware config
└── NO CODING - just manual testing

Week 3-4 (Phase 1 Sprint 1):
├── Create repository structure ✓
├── Implement hardware_detect module
├── Create basic Archiso profile
└── First bootable ISO

Week 5-6 (Phase 1 Sprint 2):
├── Implement VFIO auto-configuration
├── Create Calamares custom module
└── Test installation on 3+ systems

Week 7-8 (Phase 1 Sprint 3):
├── Polish installer UX
├── Add error handling
└── Phase 1 complete

Week 9-16 (Phase 2):
├── NeuronVM Manager GUI
├── Libvirt integration
├── Looking Glass wrapper
└── NeuronGuest Windows agent

Week 17-24 (Phase 3):
├── NeuronStore
├── Btrfs snapshots
└── System polish

Week 25-40 (Phase 4-5):
├── Enterprise features
├── Testing
└── v1.0 release
```

---

## Files to Create First (Priority Order)

1. `pyproject.toml` - Project configuration
2. `requirements.txt` - Dependencies
3. `Makefile` - Build automation
4. `.gitignore` - Git ignores
5. `src/hardware_detect/__init__.py`
6. `src/hardware_detect/gpu_scanner.py`
7. `src/hardware_detect/iommu_parser.py`
8. `src/hardware_detect/cpu_detect.py`
9. `src/hardware_detect/config_generator.py`
10. `iso-profile/packages.x86_64`
11. `iso-profile/profiledef.sh`
12. `scripts/build-iso.sh`

Once these 12 files exist, you have a buildable MVP skeleton.

---

## Commands for Claude Code to Execute

When implementing, use these commands in sequence:

```bash
# Initialize project
mkdir -p neuron-os && cd neuron-os
git init

# Create structure
mkdir -p src/{hardware_detect,vm_manager/{core,gui},store/gui,guest_agent/NeuronGuest}
mkdir -p iso-profile/airootfs/{etc/{calamares/modules/neuron-vfio,modprobe.d},usr/{lib/neuron-os,bin,share/{applications,neuron-os}}}
mkdir -p {scripts,templates,data,docs,tests}

# Create files (use Write tool for each)
# ... create each file listed above ...

# Test hardware detection
python3 -c "from src.hardware_detect import GPUScanner; print(GPUScanner().scan())"

# Build ISO (requires root)
sudo bash scripts/build-iso.sh
```

---

## Success Criteria for MVP

- [ ] `make iso` produces bootable ISO
- [ ] ISO boots to GNOME live session
- [ ] `neuron-hardware-detect` correctly identifies GPUs
- [ ] Installation completes with VFIO auto-configured
- [ ] After install, `lspci -nnk | grep vfio` shows dGPU bound to vfio-pci
- [ ] User can manually create Windows VM with GPU passthrough

This document provides everything needed to start implementation.
