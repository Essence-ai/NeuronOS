#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - GPU Scanner Module

Scans system for VGA/3D controllers and identifies passthrough candidates.
This is the core component for automatic VFIO configuration.
"""

import os
import re
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional


@dataclass
class GPUDevice:
    """Represents a detected GPU device."""

    pci_address: str           # e.g., "0000:01:00.0"
    vendor_id: str             # e.g., "10de"
    device_id: str             # e.g., "1c03"
    vendor_name: str           # e.g., "NVIDIA Corporation"
    device_name: str           # e.g., "GP106 [GeForce GTX 1060 6GB]"
    subsystem_vendor: str = "" # Subsystem vendor ID
    subsystem_device: str = "" # Subsystem device ID
    is_boot_vga: bool = False  # True if this is the primary display
    iommu_group: int = -1      # IOMMU group number (-1 if not found)
    driver_in_use: Optional[str] = None  # Current kernel driver
    device_class: str = "0300"  # PCI class code (0300=VGA, 0302=3D)

    @property
    def is_integrated(self) -> bool:
        """Check if this is likely an integrated GPU."""
        # Intel integrated GPUs typically have specific device classes
        # and are on bus 00
        if self.vendor_id == "8086":  # Intel
            return self.pci_address.startswith("0000:00:")
        # AMD APUs are also on bus 00 typically
        if self.vendor_id == "1002":  # AMD
            return self.pci_address.startswith("0000:00:")
        return False

    @property
    def is_discrete(self) -> bool:
        """Check if this is a discrete GPU."""
        return not self.is_integrated

    @property
    def vfio_ids(self) -> str:
        """Return the vendor:device ID string for VFIO binding."""
        return f"{self.vendor_id}:{self.device_id}"


class GPUScanner:
    """Scans system for GPU devices."""

    PCI_DEVICE_PATH = Path("/sys/bus/pci/devices")
    PCI_IDS_PATH = Path("/usr/share/hwdata/pci.ids")

    # PCI class codes for display devices
    VGA_CLASS = "0x030000"      # VGA compatible controller
    DISPLAY_3D_CLASS = "0x030200"  # 3D controller
    DISPLAY_CLASS_PREFIX = "0x0300"  # Any display class

    def __init__(self):
        self.devices: List[GPUDevice] = []
        self._pci_ids_cache: dict = {}
        self._load_pci_ids()

    def _load_pci_ids(self) -> None:
        """Load PCI vendor/device names from pci.ids database."""
        # Fallback vendor names
        self._pci_ids_cache = {
            "vendors": {
                "10de": "NVIDIA Corporation",
                "1002": "Advanced Micro Devices, Inc. [AMD/ATI]",
                "8086": "Intel Corporation",
                "1022": "Advanced Micro Devices, Inc. [AMD]",
            },
            "devices": {}
        }

        # Try to load full database
        if self.PCI_IDS_PATH.exists():
            try:
                self._parse_pci_ids(self.PCI_IDS_PATH)
            except Exception:
                pass  # Use fallback

    def _parse_pci_ids(self, path: Path) -> None:
        """Parse pci.ids file for vendor/device names."""
        current_vendor = None

        with open(path, 'r', errors='ignore') as f:
            for line in f:
                # Skip comments and empty lines
                if line.startswith('#') or not line.strip():
                    continue

                # Vendor line (no leading whitespace)
                if not line.startswith('\t') and not line.startswith(' '):
                    parts = line.strip().split(None, 1)
                    if len(parts) >= 2:
                        vendor_id = parts[0].lower()
                        vendor_name = parts[1].strip()
                        self._pci_ids_cache["vendors"][vendor_id] = vendor_name
                        current_vendor = vendor_id

                # Device line (single tab)
                elif line.startswith('\t') and not line.startswith('\t\t'):
                    if current_vendor:
                        parts = line.strip().split(None, 1)
                        if len(parts) >= 2:
                            device_id = parts[0].lower()
                            device_name = parts[1].strip()
                            key = f"{current_vendor}:{device_id}"
                            self._pci_ids_cache["devices"][key] = device_name

    def scan(self) -> List[GPUDevice]:
        """Scan all PCI devices for GPUs."""
        self.devices = []

        if not self.PCI_DEVICE_PATH.exists():
            return self.devices

        for device_path in self.PCI_DEVICE_PATH.iterdir():
            if not device_path.is_dir():
                continue

            class_path = device_path / "class"
            if not class_path.exists():
                continue

            try:
                device_class = class_path.read_text().strip()
            except (IOError, PermissionError):
                continue

            # Check if VGA or 3D controller
            if device_class.startswith(self.DISPLAY_CLASS_PREFIX):
                gpu = self._parse_device(device_path)
                if gpu:
                    self.devices.append(gpu)

        # Sort: boot VGA first, then by PCI address
        self.devices.sort(key=lambda g: (not g.is_boot_vga, g.pci_address))

        return self.devices

    def _parse_device(self, device_path: Path) -> Optional[GPUDevice]:
        """Parse a single PCI device."""
        pci_address = device_path.name

        try:
            # Read basic info
            vendor_id = self._read_sysfs(device_path / "vendor").replace("0x", "")
            device_id = self._read_sysfs(device_path / "device").replace("0x", "")
            device_class = self._read_sysfs(device_path / "class").replace("0x", "")[:4]

            # Read subsystem info
            subsystem_vendor = self._read_sysfs(device_path / "subsystem_vendor").replace("0x", "")
            subsystem_device = self._read_sysfs(device_path / "subsystem_device").replace("0x", "")

            # Check if boot VGA
            boot_vga_path = device_path / "boot_vga"
            is_boot_vga = boot_vga_path.exists() and self._read_sysfs(boot_vga_path) == "1"

            # Get IOMMU group
            iommu_group = self._get_iommu_group(device_path)

            # Get current driver
            driver_in_use = self._get_driver(device_path)

            # Get human-readable names
            vendor_name = self._lookup_vendor(vendor_id)
            device_name = self._lookup_device(vendor_id, device_id)

            return GPUDevice(
                pci_address=pci_address,
                vendor_id=vendor_id.lower(),
                device_id=device_id.lower(),
                vendor_name=vendor_name,
                device_name=device_name,
                subsystem_vendor=subsystem_vendor.lower(),
                subsystem_device=subsystem_device.lower(),
                is_boot_vga=is_boot_vga,
                iommu_group=iommu_group,
                driver_in_use=driver_in_use,
                device_class=device_class,
            )

        except Exception as e:
            print(f"Warning: Failed to parse {pci_address}: {e}")
            return None

    def _read_sysfs(self, path: Path) -> str:
        """Read a sysfs file safely."""
        try:
            return path.read_text().strip()
        except (IOError, PermissionError):
            return ""

    def _get_iommu_group(self, device_path: Path) -> int:
        """Get the IOMMU group number for a device."""
        iommu_link = device_path / "iommu_group"
        if iommu_link.exists():
            try:
                target = os.readlink(iommu_link)
                return int(os.path.basename(target))
            except (OSError, ValueError):
                pass
        return -1

    def _get_driver(self, device_path: Path) -> Optional[str]:
        """Get the current driver for a device."""
        driver_path = device_path / "driver"
        if driver_path.exists():
            try:
                target = os.readlink(driver_path)
                return os.path.basename(target)
            except OSError:
                pass
        return None

    def _lookup_vendor(self, vendor_id: str) -> str:
        """Lookup vendor name from PCI IDs database."""
        vendor_id = vendor_id.lower()
        return self._pci_ids_cache["vendors"].get(vendor_id, f"Unknown ({vendor_id})")

    def _lookup_device(self, vendor_id: str, device_id: str) -> str:
        """Lookup device name from PCI IDs database."""
        key = f"{vendor_id.lower()}:{device_id.lower()}"
        if key in self._pci_ids_cache["devices"]:
            return self._pci_ids_cache["devices"][key]

        # Fallback: try lspci
        try:
            pci_address = None
            for gpu in self.devices:
                if gpu.vendor_id == vendor_id and gpu.device_id == device_id:
                    pci_address = gpu.pci_address
                    break

            if pci_address:
                result = subprocess.run(
                    ["lspci", "-s", pci_address],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Parse output: "01:00.0 VGA compatible controller: NVIDIA Corporation..."
                    parts = result.stdout.split(": ", 1)
                    if len(parts) >= 2:
                        return parts[1].strip()
        except Exception:
            pass

        return f"Device {device_id}"

    def get_passthrough_candidate(self) -> Optional[GPUDevice]:
        """
        Return the GPU that should be passed through to a VM.

        Strategy:
        1. If we have both iGPU and dGPU, pass through the dGPU
        2. The boot VGA (primary display) should stay on Linux
        3. Non-boot-VGA discrete GPU is ideal for passthrough
        """
        # First, find non-boot discrete GPUs (ideal)
        for gpu in self.devices:
            if not gpu.is_boot_vga and gpu.is_discrete:
                return gpu

        # If all discrete GPUs are boot VGA, we need single-GPU passthrough
        # This is more complex and requires the boot GPU
        for gpu in self.devices:
            if gpu.is_discrete:
                return gpu

        # No discrete GPU found
        return None

    def get_boot_gpu(self) -> Optional[GPUDevice]:
        """Get the GPU currently used for the primary display."""
        for gpu in self.devices:
            if gpu.is_boot_vga:
                return gpu
        return self.devices[0] if self.devices else None

    def to_json(self) -> str:
        """Export scan results as JSON."""
        return json.dumps([asdict(d) for d in self.devices], indent=2)

    def print_summary(self) -> None:
        """Print a human-readable summary of detected GPUs."""
        print("=== NeuronOS GPU Scan ===\n")

        if not self.devices:
            print("No GPUs detected!")
            return

        for gpu in self.devices:
            # Determine status icon
            if gpu.is_boot_vga:
                status = "🖥️  BOOT GPU (Linux display)"
            elif gpu.is_discrete:
                status = "🎮 PASSTHROUGH CANDIDATE"
            else:
                status = "💻 INTEGRATED GPU"

            print(f"{status}: {gpu.pci_address}")
            print(f"  {gpu.vendor_name} {gpu.device_name}")
            print(f"  IDs: {gpu.vfio_ids}")
            print(f"  IOMMU Group: {gpu.iommu_group}")
            print(f"  Driver: {gpu.driver_in_use or 'none'}")
            print()

        candidate = self.get_passthrough_candidate()
        if candidate:
            print(f"✅ Recommended for passthrough: {candidate.pci_address}")
            print(f"   VFIO IDs: {candidate.vfio_ids}")
        else:
            print("⚠️  No suitable GPU found for passthrough")


# CLI entry point
def main():
    """Command-line interface for GPU scanning."""
    import argparse

    parser = argparse.ArgumentParser(description="NeuronOS GPU Scanner")
    parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only show passthrough candidate")
    args = parser.parse_args()

    scanner = GPUScanner()
    gpus = scanner.scan()

    if args.json:
        print(scanner.to_json())
    elif args.quiet:
        candidate = scanner.get_passthrough_candidate()
        if candidate:
            print(candidate.vfio_ids)
        else:
            print("NONE")
            exit(1)
    else:
        scanner.print_summary()


if __name__ == "__main__":
    main()
