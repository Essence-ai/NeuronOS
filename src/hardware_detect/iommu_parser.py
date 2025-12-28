#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - IOMMU Parser Module

Analyzes IOMMU groups for GPU passthrough compatibility.
IOMMU groups are critical for safe device passthrough - all devices
in a group must be passed through together.
"""

import os
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class IOMMUDevice:
    """A device within an IOMMU group."""

    pci_address: str        # e.g., "0000:01:00.0"
    device_class: str       # e.g., "0300" (VGA controller)
    class_name: str         # e.g., "VGA compatible controller"
    vendor_id: str          # e.g., "10de"
    device_id: str          # e.g., "1c03"
    description: str        # Full lspci description

    @property
    def is_gpu(self) -> bool:
        """Check if this device is a GPU."""
        return self.device_class.startswith("030")

    @property
    def is_audio(self) -> bool:
        """Check if this device is an audio controller."""
        return self.device_class.startswith("040")

    @property
    def is_bridge(self) -> bool:
        """Check if this device is a PCI bridge."""
        return self.device_class.startswith("060")

    @property
    def is_usb(self) -> bool:
        """Check if this device is a USB controller."""
        return self.device_class.startswith("0c03")

    @property
    def vfio_ids(self) -> str:
        """Return vendor:device ID for VFIO binding."""
        return f"{self.vendor_id}:{self.device_id}"


@dataclass
class IOMMUGroup:
    """Represents an IOMMU group."""

    group_id: int
    devices: List[IOMMUDevice] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """
        Check if IOMMU group is 'clean' for GPU passthrough.

        A clean group contains only:
        - The GPU itself (VGA/3D controller)
        - The GPU's audio controller (HDMI audio)
        - PCI bridge (acceptable, not passed through)

        A dirty group contains other devices like USB controllers,
        SATA controllers, etc. that make passthrough problematic.
        """
        acceptable_prefixes = {
            "030",  # Display controllers (VGA, 3D)
            "040",  # Audio controllers
            "060",  # PCI bridges (acceptable, auto-handled)
        }

        for device in self.devices:
            prefix = device.device_class[:3]
            if prefix not in acceptable_prefixes:
                return False

        return True

    @property
    def device_count(self) -> int:
        """Number of devices in the group."""
        return len(self.devices)

    @property
    def has_gpu(self) -> bool:
        """Check if this group contains a GPU."""
        return any(d.is_gpu for d in self.devices)

    @property
    def has_audio(self) -> bool:
        """Check if this group contains an audio device."""
        return any(d.is_audio for d in self.devices)

    @property
    def passthrough_devices(self) -> List[IOMMUDevice]:
        """
        Get devices that need to be passed through.
        Excludes PCI bridges (handled by kernel).
        """
        return [d for d in self.devices if not d.is_bridge]

    @property
    def vfio_ids(self) -> List[str]:
        """Get all vendor:device IDs for VFIO binding."""
        return [d.vfio_ids for d in self.passthrough_devices]


class IOMMUParser:
    """Parses and analyzes IOMMU groups."""

    IOMMU_PATH = Path("/sys/kernel/iommu_groups")

    def __init__(self):
        self.groups: Dict[int, IOMMUGroup] = {}
        self._iommu_enabled: bool = False

    @property
    def is_iommu_enabled(self) -> bool:
        """Check if IOMMU is enabled on this system."""
        return self._iommu_enabled

    def parse_all(self) -> Dict[int, IOMMUGroup]:
        """Parse all IOMMU groups."""
        self.groups = {}

        if not self.IOMMU_PATH.exists():
            self._iommu_enabled = False
            raise RuntimeError(
                "IOMMU not enabled! Add kernel parameter and reboot:\n"
                "  Intel: intel_iommu=on iommu=pt\n"
                "  AMD:   amd_iommu=on iommu=pt"
            )

        self._iommu_enabled = True

        # Sort numerically
        group_dirs = sorted(
            self.IOMMU_PATH.iterdir(),
            key=lambda x: int(x.name) if x.name.isdigit() else 0
        )

        for group_dir in group_dirs:
            if not group_dir.name.isdigit():
                continue

            group_id = int(group_dir.name)
            devices = []

            devices_path = group_dir / "devices"
            if devices_path.exists():
                for device_link in devices_path.iterdir():
                    pci_addr = device_link.name
                    device = self._get_device_info(pci_addr)
                    if device:
                        devices.append(device)

            self.groups[group_id] = IOMMUGroup(
                group_id=group_id,
                devices=devices
            )

        return self.groups

    def _get_device_info(self, pci_address: str) -> Optional[IOMMUDevice]:
        """Get device information using lspci."""
        try:
            # Run lspci with verbose numeric output
            result = subprocess.run(
                ["lspci", "-nns", pci_address],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            description = result.stdout.strip()
            if not description:
                return None

            # Parse output format:
            # "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GP106 [10de:1c03]"
            # or
            # "01:00.1 Audio device [0403]: NVIDIA Corporation GP106 High Definition Audio [10de:10f1]"

            # Extract class code
            class_match = description.split("[")
            device_class = "0000"
            vendor_id = "0000"
            device_id = "0000"
            class_name = "Unknown"

            if len(class_match) >= 2:
                # Get class from first bracket pair
                class_part = class_match[1].split("]")[0]
                if len(class_part) == 4:
                    device_class = class_part

            # Get vendor:device from last bracket pair
            if "[" in description:
                last_bracket = description.rfind("[")
                ids_part = description[last_bracket:].strip("[]")
                if ":" in ids_part:
                    vendor_id, device_id = ids_part.split(":")[:2]

            # Get class name (between PCI address and [class])
            parts = description.split(":", 1)
            if len(parts) >= 2:
                after_addr = parts[0].split(" ", 1)
                if len(after_addr) >= 2:
                    # Extract everything before the first [
                    class_name_part = after_addr[1].split("[")[0].strip()
                    class_name = class_name_part

            return IOMMUDevice(
                pci_address=pci_address,
                device_class=device_class,
                class_name=class_name,
                vendor_id=vendor_id.lower(),
                device_id=device_id.lower(),
                description=description
            )

        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            print(f"Warning: Failed to get info for {pci_address}: {e}")
            return None

    def get_gpu_group(self, pci_address: str) -> Optional[IOMMUGroup]:
        """Get the IOMMU group containing a specific PCI device."""
        for group in self.groups.values():
            for device in group.devices:
                if device.pci_address == pci_address:
                    return group
        return None

    def get_gpu_groups(self) -> List[IOMMUGroup]:
        """Get all IOMMU groups that contain GPUs."""
        return [g for g in self.groups.values() if g.has_gpu]

    def get_clean_groups(self) -> List[IOMMUGroup]:
        """Get all IOMMU groups suitable for passthrough."""
        return [g for g in self.groups.values() if g.is_clean]

    def print_report(self) -> None:
        """Print a human-readable IOMMU report."""
        print("=== IOMMU Group Analysis ===\n")

        if not self.groups:
            print("No IOMMU groups found. Is IOMMU enabled?")
            return

        # Print summary first
        gpu_groups = self.get_gpu_groups()
        clean_groups = [g for g in gpu_groups if g.is_clean]

        print(f"Total IOMMU groups: {len(self.groups)}")
        print(f"Groups with GPUs: {len(gpu_groups)}")
        print(f"Clean GPU groups (suitable for passthrough): {len(clean_groups)}")
        print()

        # Print GPU groups in detail
        for group in gpu_groups:
            status = "✅ CLEAN" if group.is_clean else "⚠️  SHARED (may need ACS patch)"
            print(f"Group {group.group_id} ({status}):")

            for device in group.devices:
                marker = ""
                if device.is_gpu:
                    marker = " 🎮"
                elif device.is_audio:
                    marker = " 🔊"
                elif device.is_bridge:
                    marker = " 🌉"
                elif device.is_usb:
                    marker = " ⚠️ USB"

                print(f"  └─ [{device.device_class}] {device.pci_address}{marker}")
                print(f"      {device.description}")

            if not group.is_clean:
                print("      ⚠️  This group contains non-GPU devices!")
                print("      You may need the ACS Override Patch for isolation.")

            print()

    def check_acs_needed(self) -> bool:
        """
        Check if ACS Override patch is needed.

        Returns True if any GPU group contains non-passthrough-friendly devices.
        """
        for group in self.get_gpu_groups():
            if not group.is_clean:
                return True
        return False


def main():
    """Command-line interface for IOMMU parsing."""
    import argparse

    parser = argparse.ArgumentParser(description="NeuronOS IOMMU Parser")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Only check if IOMMU is enabled")
    parser.add_argument("-g", "--gpu-only", action="store_true",
                        help="Only show GPU-related groups")
    args = parser.parse_args()

    iommu_parser = IOMMUParser()

    try:
        iommu_parser.parse_all()

        if args.quiet:
            print("IOMMU is enabled")
            exit(0)
        else:
            iommu_parser.print_report()

            if iommu_parser.check_acs_needed():
                print("⚠️  ACS Override Patch may be required for proper isolation.")
                print("   See: https://wiki.archlinux.org/title/PCI_passthrough_via_OVMF#Bypassing_the_IOMMU_groups_(ACS_override_patch)")

    except RuntimeError as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
