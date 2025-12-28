# NeuronOS Dev Guide: Phase 1 — The Core OS & Auto-VFIO

**Duration:** 6 Weeks (Weeks 3-8 / Days 15-56)
**Developers Required:** 1-2
**Goal:** Create a bootable NeuronOS ISO that automates all Phase 0 manual configuration.

> [!IMPORTANT]
> **Prerequisites:** Phase 0 must be complete. You must have a working GPU passthrough setup documented in `phase_0_results.md`.

---

## Sprint 1: Build Environment & Skeleton ISO (Week 3-4 / Days 15-28)

---

### Week 3, Day 15-17: Archiso Build Environment

#### 🎫 Story 1.1.1: Development Workspace
**As a** Release Engineer,
**I want** a dedicated build environment for ISO creation,
**So that** builds are reproducible.

**Acceptance Criteria:**
- [ ] Git repository initialized with proper structure.
- [ ] `archiso` installed and working.
- [ ] Baseline profile copied and customizable.

**Tasks:**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 📁 Setup | Create project directory | `mkdir -p ~/projects/neuron-os && cd ~/projects/neuron-os` |
| 2 | 🔧 Git | Initialize repository | `git init` |
| 3 | 📦 Install | Install archiso | `sudo pacman -S archiso` |
| 4 | 📁 Copy | Copy releng profile | `cp -r /usr/share/archiso/configs/releng/ ./iso-profile` |
| 5 | 📝 Doc | Create README.md | Document build instructions |
| 6 | 🔧 Git | Initial commit | `git add . && git commit -m "Initial archiso profile"` |

**Repository Structure:**
```
neuron-os/
├── iso-profile/                 # archiso profile
│   ├── airootfs/                # Files to include in live ISO
│   │   └── etc/
│   │   └── usr/
│   ├── efiboot/
│   ├── syslinux/
│   ├── packages.x86_64          # Packages to install
│   ├── pacman.conf
│   └── profiledef.sh
├── scripts/                     # Build scripts
│   └── build.sh
├── src/                         # Custom NeuronOS code
│   └── hardware-detect/
├── docs/
└── README.md
```

---

### Week 3, Day 18-21: Package Selection & Customization

#### 🎫 Story 1.1.2: Curated Package List
**As a** User,
**I want** a pre-configured desktop environment,
**So that** I have a functional system immediately.

**Acceptance Criteria:**
- [ ] GNOME desktop included.
- [ ] Virtualization stack included.
- [ ] No unnecessary packages.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📝 Edit | Edit `packages.x86_64` | Add/remove packages per list below |
| 2 | 📝 Edit | Create custom pacman.conf | Enable multilib if needed |
| 3 | 📁 Add | Add custom configs to airootfs | Desktop files, autostart entries |
| 4 | 🔧 Test | Test build | `sudo mkarchiso -v -w /tmp/archiso-tmp -o ~/iso-output ./iso-profile` |

**packages.x86_64 - Core Packages:**
```
# Base System
base
linux
linux-firmware
linux-headers
sudo
networkmanager
btrfs-progs

# Desktop Environment
gnome
gnome-tweaks
gnome-shell-extensions
gdm

# Virtualization (The Core Stack)
qemu-full
libvirt
virt-manager
edk2-ovmf
swtpm
dnsmasq
looking-glass

# Installer
calamares
os-prober

# Development Tools (for debugging)
vim
git
python
python-pip
python-pyudev
base-devel

# Utilities
firefox
file-roller
gnome-calculator

# NeuronOS Custom (placeholder)
# neuron-hardware-detect
# neuron-vm-manager
```

**Packages to REMOVE from default profile:**
```
# Remove from packages.x86_64:
- arch-install-scripts (using Calamares instead)
- mkinitcpio-archiso (not needed for installed system)
```

---

### Week 4, Day 22-24: First ISO Build

#### 🎫 Story 1.1.3: Bootable Skeleton
**As a** Developer,
**I want** a bootable ISO that installs a basic NeuronOS,
**So that** I can iterate on features.

**Acceptance Criteria:**
- [ ] ISO builds without errors.
- [ ] ISO boots in VM.
- [ ] GNOME live session starts.
- [ ] Calamares installer launches.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📝 Script | Create build script | `scripts/build.sh` |
| 2 | 🔧 Build | Run first build | Execute build script |
| 3 | 🧪 Test | Test in VM | Boot ISO in QEMU |
| 4 | 🐛 Debug | Fix any issues | Iterate on package list |
| 5 | 🔧 Git | Commit working state | Tag as `v0.1.0-skeleton` |

**build.sh Script:**
```bash
#!/bin/bash
set -e

PROFILE_DIR="./iso-profile"
WORK_DIR="/tmp/neuron-archiso-work"
OUTPUT_DIR="./output"

# Clean previous build
sudo rm -rf "$WORK_DIR"
mkdir -p "$OUTPUT_DIR"

# Build ISO
sudo mkarchiso -v -w "$WORK_DIR" -o "$OUTPUT_DIR" "$PROFILE_DIR"

echo "ISO built: $OUTPUT_DIR/neuron-*.iso"
```

**Testing in QEMU:**
```bash
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -boot d \
  -cdrom ./output/neuron-*.iso \
  -cpu host
```

---

### Week 4, Day 25-28: Calamares Configuration

#### 🎫 Story 1.1.4: Installer Framework
**As a** User,
**I want** a graphical installer,
**So that** I don't need to use the terminal to install the OS.

**Acceptance Criteria:**
- [ ] Calamares launches from live session.
- [ ] Basic installation completes (partition, user, bootloader).
- [ ] System boots after installation.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📁 Copy | Copy Calamares default configs | From `/etc/calamares/` |
| 2 | 📝 Edit | Configure `settings.conf` | Set module sequence |
| 3 | 📝 Edit | Configure `branding/` | NeuronOS branding |
| 4 | 📁 Add | Add to airootfs | `/etc/calamares/` |
| 5 | 📝 Add | Create desktop launcher | `airootfs/usr/share/applications/` |
| 6 | 🧪 Test | Test installation | Full install in VM |

**Calamares settings.conf (Key Sections):**
```yaml
modules-search: [ local, /usr/lib/calamares/modules ]

sequence:
- show:
  - welcome
  - locale
  - keyboard
  - partition
  - users
  - summary

- exec:
  - partition
  - mount
  - unpackfs
  - machineid
  - fstab
  - locale
  - keyboard
  - localecfg
  - users
  - networkcfg
  - hwclock
  - services-systemd
  - bootloader
  - neuron-vfio  # OUR CUSTOM MODULE (Phase 1 Sprint 2)
  
- show:
  - finished
```

**Branding Files:**
```
iso-profile/airootfs/etc/calamares/branding/neuron/
├── branding.desc
├── show.qml
├── welcome.png
└── sidebar.png
```

---

## Sprint 2: Hardware Detection Engine (Week 5-6 / Days 29-42)

---

### Week 5, Day 29-32: Hardware Detection Script - Core Logic

#### 🎫 Story 1.2.1: GPU Detection Module
**As a** Installer,
**I want** to automatically detect all GPUs and their IOMMU groups,
**So that** I can configure VFIO without user input.

**Acceptance Criteria:**
- [ ] Script lists all VGA/3D controllers.
- [ ] Script identifies which GPU is the boot GPU.
- [ ] Script outputs JSON with device details.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📁 Create | Create Python package | `src/hardware-detect/` |
| 2 | 📝 Code | Implement `gpu_scanner.py` | Core GPU detection |
| 3 | 📝 Code | Implement `iommu_parser.py` | IOMMU group analysis |
| 4 | 🧪 Test | Unit tests | Test on dev machine |
| 5 | 🔧 Git | Commit | "Add hardware detection core" |

**Directory Structure:**
```
src/hardware-detect/
├── neuron_hw/
│   ├── __init__.py
│   ├── gpu_scanner.py
│   ├── iommu_parser.py
│   └── config_generator.py
├── tests/
│   └── test_scanner.py
├── setup.py
└── requirements.txt
```

**gpu_scanner.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - GPU Scanner Module
Scans system for VGA/3D controllers and identifies passthrough candidates.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
import json


@dataclass
class GPUDevice:
    """Represents a detected GPU device."""
    pci_address: str           # e.g., "0000:01:00.0"
    vendor_id: str             # e.g., "10de"
    device_id: str             # e.g., "1c03"
    vendor_name: str           # e.g., "NVIDIA Corporation"
    device_name: str           # e.g., "GP106 [GeForce GTX 1060 6GB]"
    is_boot_vga: bool          # True if this is the primary display
    iommu_group: int           # IOMMU group number
    driver_in_use: Optional[str]  # Current kernel driver


class GPUScanner:
    """Scans system for GPU devices."""
    
    PCI_DEVICE_PATH = Path("/sys/bus/pci/devices")
    VGA_CLASS = "0x030000"      # VGA compatible controller
    DISPLAY_CLASS = "0x030200"  # 3D controller
    
    def __init__(self):
        self.devices: List[GPUDevice] = []
    
    def scan(self) -> List[GPUDevice]:
        """Scan all PCI devices for GPUs."""
        self.devices = []
        
        for device_path in self.PCI_DEVICE_PATH.iterdir():
            if not device_path.is_dir():
                continue
            
            class_path = device_path / "class"
            if not class_path.exists():
                continue
            
            device_class = class_path.read_text().strip()
            
            # Check if VGA or 3D controller
            if device_class.startswith("0x0300"):
                gpu = self._parse_device(device_path)
                if gpu:
                    self.devices.append(gpu)
        
        return self.devices
    
    def _parse_device(self, device_path: Path) -> Optional[GPUDevice]:
        """Parse a single PCI device."""
        pci_address = device_path.name
        
        # Read vendor and device IDs
        vendor_id = (device_path / "vendor").read_text().strip().replace("0x", "")
        device_id = (device_path / "device").read_text().strip().replace("0x", "")
        
        # Check if boot VGA
        boot_vga_path = device_path / "boot_vga"
        is_boot_vga = boot_vga_path.exists() and boot_vga_path.read_text().strip() == "1"
        
        # Get IOMMU group
        iommu_link = device_path / "iommu_group"
        iommu_group = -1
        if iommu_link.exists():
            iommu_group = int(os.path.basename(os.readlink(iommu_link)))
        
        # Get current driver
        driver_path = device_path / "driver"
        driver_in_use = None
        if driver_path.exists():
            driver_in_use = os.path.basename(os.readlink(driver_path))
        
        # Get human-readable names (from /usr/share/hwdata/pci.ids)
        vendor_name, device_name = self._lookup_names(vendor_id, device_id)
        
        return GPUDevice(
            pci_address=pci_address,
            vendor_id=vendor_id,
            device_id=device_id,
            vendor_name=vendor_name,
            device_name=device_name,
            is_boot_vga=is_boot_vga,
            iommu_group=iommu_group,
            driver_in_use=driver_in_use
        )
    
    def _lookup_names(self, vendor_id: str, device_id: str) -> tuple:
        """Lookup human-readable names from pci.ids database."""
        # Simplified - in production, parse /usr/share/hwdata/pci.ids
        vendor_map = {
            "10de": "NVIDIA Corporation",
            "1002": "Advanced Micro Devices, Inc. [AMD/ATI]",
            "8086": "Intel Corporation",
        }
        return vendor_map.get(vendor_id, f"Unknown ({vendor_id})"), f"Device {device_id}"
    
    def get_passthrough_candidate(self) -> Optional[GPUDevice]:
        """Return the GPU that should be passed through (non-boot GPU)."""
        for gpu in self.devices:
            if not gpu.is_boot_vga:
                return gpu
        return None
    
    def to_json(self) -> str:
        """Export scan results as JSON."""
        return json.dumps([asdict(d) for d in self.devices], indent=2)


# CLI Usage
if __name__ == "__main__":
    scanner = GPUScanner()
    gpus = scanner.scan()
    
    print("=== NeuronOS GPU Scan ===")
    for gpu in gpus:
        status = "🖥️ BOOT GPU" if gpu.is_boot_vga else "🎮 PASSTHROUGH CANDIDATE"
        print(f"{status}: {gpu.pci_address}")
        print(f"  {gpu.vendor_name} {gpu.device_name}")
        print(f"  IDs: {gpu.vendor_id}:{gpu.device_id}")
        print(f"  IOMMU Group: {gpu.iommu_group}")
        print(f"  Driver: {gpu.driver_in_use}")
        print()
    
    candidate = scanner.get_passthrough_candidate()
    if candidate:
        print(f"✅ Recommended for passthrough: {candidate.pci_address}")
    else:
        print("⚠️ No suitable GPU found for passthrough")
```

---

### Week 5, Day 33-35: IOMMU Group Analysis

#### 🎫 Story 1.2.2: IOMMU Group Validator
**As a** System,
**I want** to analyze IOMMU groups for passthrough compatibility,
**So that** I can warn users about potential issues.

**Acceptance Criteria:**
- [ ] Script lists all devices in each IOMMU group.
- [ ] Script flags "dirty" groups (multiple devices).
- [ ] Script provides recommendations.

**iommu_parser.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - IOMMU Parser Module
Analyzes IOMMU groups for GPU passthrough compatibility.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
import subprocess


@dataclass
class IOMMUDevice:
    """A device within an IOMMU group."""
    pci_address: str
    device_class: str
    description: str


@dataclass
class IOMMUGroup:
    """Represents an IOMMU group."""
    group_id: int
    devices: List[IOMMUDevice]
    is_clean: bool  # True if only contains GPU and its audio controller


class IOMMUParser:
    """Parses and analyzes IOMMU groups."""
    
    IOMMU_PATH = Path("/sys/kernel/iommu_groups")
    
    def __init__(self):
        self.groups: Dict[int, IOMMUGroup] = {}
    
    def parse_all(self) -> Dict[int, IOMMUGroup]:
        """Parse all IOMMU groups."""
        self.groups = {}
        
        if not self.IOMMU_PATH.exists():
            raise RuntimeError("IOMMU not enabled! Check kernel parameters.")
        
        for group_dir in sorted(self.IOMMU_PATH.iterdir(), key=lambda x: int(x.name)):
            group_id = int(group_dir.name)
            devices = []
            
            devices_path = group_dir / "devices"
            if devices_path.exists():
                for device_link in devices_path.iterdir():
                    pci_addr = device_link.name
                    device = self._get_device_info(pci_addr)
                    devices.append(device)
            
            is_clean = self._check_group_clean(devices)
            
            self.groups[group_id] = IOMMUGroup(
                group_id=group_id,
                devices=devices,
                is_clean=is_clean
            )
        
        return self.groups
    
    def _get_device_info(self, pci_address: str) -> IOMMUDevice:
        """Get device information using lspci."""
        try:
            result = subprocess.run(
                ["lspci", "-nns", pci_address],
                capture_output=True,
                text=True,
                check=True
            )
            description = result.stdout.strip()
            
            # Extract class from description
            # Format: "01:00.0 VGA compatible controller [0300]: ..."
            parts = description.split(": ", 1)
            device_class = parts[0].split("[")[-1].rstrip("]") if "[" in parts[0] else "unknown"
            
            return IOMMUDevice(
                pci_address=pci_address,
                device_class=device_class,
                description=description
            )
        except subprocess.CalledProcessError:
            return IOMMUDevice(pci_address, "unknown", f"Unknown device {pci_address}")
    
    def _check_group_clean(self, devices: List[IOMMUDevice]) -> bool:
        """
        Check if IOMMU group is 'clean' for GPU passthrough.
        A clean group contains only:
        - The GPU itself (VGA controller)
        - The GPU's audio controller (often on same card)
        - PCI bridge (acceptable)
        """
        acceptable_classes = {"0300", "0403", "0604"}  # VGA, Audio, PCI Bridge
        
        for device in devices:
            if device.device_class[:4] not in acceptable_classes:
                return False
        return True
    
    def get_gpu_group(self, pci_address: str) -> Optional[IOMMUGroup]:
        """Get the IOMMU group containing a specific PCI device."""
        for group in self.groups.values():
            for device in group.devices:
                if device.pci_address == pci_address:
                    return group
        return None
    
    def print_report(self):
        """Print a human-readable IOMMU report."""
        print("=== IOMMU Group Analysis ===\n")
        
        for group_id, group in sorted(self.groups.items()):
            status = "✅ CLEAN" if group.is_clean else "⚠️ SHARED"
            print(f"Group {group_id} ({status}):")
            for device in group.devices:
                print(f"  └─ {device.description}")
            print()


if __name__ == "__main__":
    parser = IOMMUParser()
    try:
        parser.parse_all()
        parser.print_report()
    except RuntimeError as e:
        print(f"❌ Error: {e}")
```

---

### Week 6, Day 36-38: Config Generation

#### 🎫 Story 1.2.3: Auto-Configuration Generator
**As a** Installer,
**I want** to generate VFIO configuration files automatically,
**So that** the system is ready on first boot.

**Acceptance Criteria:**
- [ ] Generates `/etc/modprobe.d/vfio.conf` with correct IDs.
- [ ] Generates kernel parameter additions.
- [ ] Handles edge cases (no suitable GPU, shared IOMMU).

**config_generator.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - Config Generator
Generates all necessary configuration files for GPU passthrough.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from .gpu_scanner import GPUScanner, GPUDevice
from .iommu_parser import IOMMUParser


@dataclass
class VFIOConfig:
    """Generated VFIO configuration."""
    vfio_conf: str          # Content for /etc/modprobe.d/vfio.conf
    mkinitcpio_modules: str # Modules to add to mkinitcpio.conf
    kernel_params: str      # Kernel command line parameters
    warnings: List[str]     # Any warnings for the user


class ConfigGenerator:
    """Generates VFIO configuration files."""
    
    def __init__(self):
        self.scanner = GPUScanner()
        self.iommu_parser = IOMMUParser()
    
    def detect_and_generate(self) -> VFIOConfig:
        """Run full detection and generate configs."""
        warnings = []
        
        # Scan GPUs
        gpus = self.scanner.scan()
        
        if not gpus:
            raise RuntimeError("No GPUs detected!")
        
        if len(gpus) < 2:
            warnings.append("Only one GPU detected. Single-GPU passthrough requires special handling.")
        
        # Get passthrough candidate
        candidate = self.scanner.get_passthrough_candidate()
        
        if not candidate:
            raise RuntimeError("No suitable GPU for passthrough (all GPUs are boot VGA)")
        
        # Parse IOMMU groups
        self.iommu_parser.parse_all()
        gpu_group = self.iommu_parser.get_gpu_group(candidate.pci_address)
        
        if gpu_group and not gpu_group.is_clean:
            warnings.append(
                f"IOMMU group {gpu_group.group_id} contains other devices. "
                "ACS Override Patch may be required for optimal isolation."
            )
        
        # Find all device IDs in the GPU's IOMMU group (GPU + Audio controller)
        pci_ids = self._get_all_pci_ids_in_group(candidate, gpu_group)
        
        # Generate configs
        vfio_conf = self._generate_vfio_conf(pci_ids, candidate)
        mkinitcpio = self._generate_mkinitcpio()
        kernel_params = self._generate_kernel_params()
        
        return VFIOConfig(
            vfio_conf=vfio_conf,
            mkinitcpio_modules=mkinitcpio,
            kernel_params=kernel_params,
            warnings=warnings
        )
    
    def _get_all_pci_ids_in_group(self, gpu: GPUDevice, group) -> List[str]:
        """Get all PCI IDs that should be bound to vfio-pci."""
        ids = [f"{gpu.vendor_id}:{gpu.device_id}"]
        
        # Also bind any audio controller on the same card
        if group:
            for device in group.devices:
                if "Audio" in device.description or "0403" in device.device_class:
                    # Extract vendor:device from lspci output
                    # Format: "01:00.1 Audio device [0403]: NVIDIA [10de:10f1]"
                    if "[" in device.description:
                        id_match = device.description.split("[")[-1].rstrip("]")
                        if ":" in id_match and id_match not in ids:
                            ids.append(id_match)
        
        return ids
    
    def _generate_vfio_conf(self, pci_ids: List[str], gpu: GPUDevice) -> str:
        """Generate /etc/modprobe.d/vfio.conf content."""
        ids_str = ",".join(pci_ids)
        
        content = f"""# NeuronOS VFIO Configuration
# Auto-generated for GPU passthrough
# Target GPU: {gpu.vendor_name} @ {gpu.pci_address}

# Bind these devices to vfio-pci driver
options vfio-pci ids={ids_str}

# Ensure vfio-pci loads before GPU drivers
softdep nvidia pre: vfio-pci
softdep amdgpu pre: vfio-pci
softdep radeon pre: vfio-pci
softdep nouveau pre: vfio-pci
"""
        return content
    
    def _generate_mkinitcpio(self) -> str:
        """Generate MODULES line for mkinitcpio.conf."""
        return "MODULES=(vfio_pci vfio vfio_iommu_type1)"
    
    def _generate_kernel_params(self) -> str:
        """Generate kernel command line parameters."""
        # TODO: Detect Intel vs AMD
        return "intel_iommu=on iommu=pt"
    
    def apply_to_target(self, target_root: Path):
        """Apply generated configs to a target installation path."""
        config = self.detect_and_generate()
        
        # Write vfio.conf
        vfio_path = target_root / "etc/modprobe.d/vfio.conf"
        vfio_path.parent.mkdir(parents=True, exist_ok=True)
        vfio_path.write_text(config.vfio_conf)
        print(f"✅ Written: {vfio_path}")
        
        # TODO: Modify mkinitcpio.conf
        # TODO: Modify GRUB/systemd-boot kernel params
        
        # Print warnings
        for warning in config.warnings:
            print(f"⚠️ {warning}")


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
        
        if config.warnings:
            print("\n⚠️ Warnings:")
            for w in config.warnings:
                print(f"  - {w}")
                
    except RuntimeError as e:
        print(f"❌ Error: {e}")
```

---

### Week 6, Day 39-42: Calamares Integration

#### 🎫 Story 1.2.4: Custom Installer Module
**As a** Installer,
**I want** to run the hardware detection during installation,
**So that** the installed system is pre-configured for GPU passthrough.

**Acceptance Criteria:**
- [ ] Calamares calls `neuron-hardware-detect` during install.
- [ ] Config files are written to target system.
- [ ] GRUB is configured with correct kernel params.
- [ ] mkinitcpio is regenerated on target.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📁 Create | Create Calamares module dir | `iso-profile/airootfs/etc/calamares/modules/neuron-vfio/` |
| 2 | 📝 Code | Write `module.desc` | Module descriptor |
| 3 | 📝 Code | Write `main.py` | Python job implementation |
| 4 | 📝 Edit | Update settings.conf | Add module to exec sequence |
| 5 | 🧪 Test | Test full installation | Verify configs on installed system |

**Module Structure:**
```
iso-profile/airootfs/etc/calamares/modules/neuron-vfio/
├── module.desc
└── main.py
```

**module.desc:**
```yaml
---
type: "job"
name: "neuron-vfio"
interface: "python"
script: "main.py"
```

**main.py:**
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2025 NeuronOS Project
# SPDX-License-Identifier: GPL-3.0-or-later

"""
NeuronOS VFIO Configuration Module for Calamares

This module runs during installation to:
1. Detect GPU hardware
2. Generate VFIO configuration
3. Apply configs to the installed system
4. Update bootloader with kernel parameters
5. Regenerate initramfs
"""

import os
import subprocess
from pathlib import Path

import libcalamares

# Import our hardware detection library
# Note: In production, this would be properly packaged
import sys
sys.path.insert(0, "/usr/lib/neuron-os/")
from neuron_hw.config_generator import ConfigGenerator


def pretty_name():
    return "Configuring GPU Passthrough"


def run():
    """Main entry point for Calamares module."""
    
    # Get target root from Calamares global storage
    root_mount_point = libcalamares.globalstorage.value("rootMountPoint")
    
    if not root_mount_point:
        return ("No root mount point found", "Configuration failed")
    
    target_root = Path(root_mount_point)
    
    libcalamares.utils.debug("NeuronOS: Starting VFIO configuration...")
    
    try:
        # Initialize config generator
        generator = ConfigGenerator()
        config = generator.detect_and_generate()
        
        # 1. Write vfio.conf
        vfio_path = target_root / "etc/modprobe.d/vfio.conf"
        vfio_path.parent.mkdir(parents=True, exist_ok=True)
        vfio_path.write_text(config.vfio_conf)
        libcalamares.utils.debug(f"Written: {vfio_path}")
        
        # 2. Update mkinitcpio.conf
        mkinitcpio_path = target_root / "etc/mkinitcpio.conf"
        if mkinitcpio_path.exists():
            content = mkinitcpio_path.read_text()
            # Replace MODULES line
            if "MODULES=(" in content:
                import re
                content = re.sub(
                    r'MODULES=\([^)]*\)',
                    config.mkinitcpio_modules,
                    content
                )
                mkinitcpio_path.write_text(content)
                libcalamares.utils.debug("Updated mkinitcpio.conf")
        
        # 3. Update GRUB configuration
        grub_default = target_root / "etc/default/grub"
        if grub_default.exists():
            content = grub_default.read_text()
            # Append to GRUB_CMDLINE_LINUX_DEFAULT
            if "GRUB_CMDLINE_LINUX_DEFAULT=" in content:
                import re
                content = re.sub(
                    r'(GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)',
                    f'\\1 {config.kernel_params}',
                    content
                )
                grub_default.write_text(content)
                libcalamares.utils.debug("Updated GRUB config")
        
        # 4. Regenerate initramfs and GRUB (in chroot)
        subprocess.run(
            ["arch-chroot", str(target_root), "mkinitcpio", "-P"],
            check=True
        )
        
        subprocess.run(
            ["arch-chroot", str(target_root), "grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
            check=True
        )
        
        libcalamares.utils.debug("NeuronOS: VFIO configuration complete!")
        
        # Store warnings for display
        if config.warnings:
            libcalamares.globalstorage.insert("neuron_warnings", config.warnings)
        
        return None  # Success
        
    except Exception as e:
        return (f"VFIO configuration failed: {str(e)}", str(e))
```

---

## Sprint 3: Testing & Refinement (Week 7-8 / Days 43-56)

### Week 7: Integration Testing

| Day | Task |
|-----|------|
| 43 | Test ISO build with all components |
| 44 | Test installation on VM with dual GPUs (simulated) |
| 45 | Test installation on real hardware #1 |
| 46 | Document and fix bugs |
| 47 | Test installation on real hardware #2 (different vendor) |
| 48 | Performance validation - compare to Phase 0 baseline |
| 49 | Update documentation with any workarounds |

### Week 8: Polish & Release Prep

| Day | Task |
|-----|------|
| 50 | Code review and cleanup |
| 51 | Add error handling and user-friendly messages |
| 52 | Create user documentation (installation guide) |
| 53 | Tag release `v0.2.0-alpha` |
| 54 | Prepare demo video |
| 55 | Internal team testing |
| 56 | Phase 1 retrospective and planning for Phase 2 |

---

# Phase 1 Exit Criteria ✅

- [ ] NeuronOS ISO builds successfully
- [ ] ISO boots into live GNOME session
- [ ] Calamares installer completes without errors
- [ ] VFIO is automatically configured during installation
- [ ] Installed system boots with GPU isolated
- [ ] `lspci -nnk` shows vfio-pci for discrete GPU
- [ ] Ready for manual VM testing (Phase 2 will automate VM creation)

**Proceed to:** [Phase 2 Dev Guide](file:///C:/Users/jasbh/.gemini/antigravity/brain/19c55c70-6e71-40e5-9eed-2f5494130b35/dev_guide_phase_2.md)
