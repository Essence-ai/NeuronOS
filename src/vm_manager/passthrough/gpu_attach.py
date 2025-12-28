"""
GPU Passthrough Manager - Handles GPU attach/detach and VFIO binding.

This module provides functionality for:
- Binding/unbinding GPUs to/from vfio-pci driver
- Attaching GPUs to running or stopped VMs
- Managing IOMMU group isolation
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PassthroughResult:
    """Result of a passthrough operation."""
    success: bool
    message: str
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class GPUPassthroughManager:
    """
    Manages GPU passthrough operations.

    Handles the low-level operations of binding GPUs to vfio-pci driver
    and ensuring clean IOMMU group isolation.
    """

    VFIO_DRIVER = "vfio-pci"
    SYSFS_PCI_PATH = Path("/sys/bus/pci/devices")
    SYSFS_DRIVERS_PATH = Path("/sys/bus/pci/drivers")

    def __init__(self):
        self._original_drivers: dict[str, str] = {}

    def get_current_driver(self, pci_address: str) -> Optional[str]:
        """
        Get the current driver bound to a PCI device.

        Args:
            pci_address: PCI address (e.g., "0000:01:00.0")

        Returns:
            Driver name or None if no driver bound.
        """
        driver_link = self.SYSFS_PCI_PATH / pci_address / "driver"
        if driver_link.exists():
            return driver_link.resolve().name
        return None

    def get_iommu_group(self, pci_address: str) -> Optional[int]:
        """
        Get the IOMMU group number for a PCI device.

        Args:
            pci_address: PCI address

        Returns:
            IOMMU group number or None.
        """
        iommu_link = self.SYSFS_PCI_PATH / pci_address / "iommu_group"
        if iommu_link.exists():
            return int(iommu_link.resolve().name)
        return None

    def get_iommu_group_devices(self, group_id: int) -> List[str]:
        """
        Get all devices in an IOMMU group.

        Args:
            group_id: IOMMU group number

        Returns:
            List of PCI addresses in the group.
        """
        group_path = Path(f"/sys/kernel/iommu_groups/{group_id}/devices")
        if not group_path.exists():
            return []

        return [d.name for d in group_path.iterdir()]

    def bind_to_vfio(self, pci_address: str) -> PassthroughResult:
        """
        Bind a PCI device to vfio-pci driver.

        Args:
            pci_address: PCI address to bind

        Returns:
            PassthroughResult indicating success/failure.
        """
        current_driver = self.get_current_driver(pci_address)
        warnings = []

        # Store original driver for potential restore
        if current_driver and current_driver != self.VFIO_DRIVER:
            self._original_drivers[pci_address] = current_driver
            logger.info(f"Storing original driver for {pci_address}: {current_driver}")

        # Already bound to vfio?
        if current_driver == self.VFIO_DRIVER:
            return PassthroughResult(
                success=True,
                message=f"{pci_address} already bound to vfio-pci",
            )

        try:
            # Unbind from current driver
            if current_driver:
                unbind_path = self.SYSFS_DRIVERS_PATH / current_driver / "unbind"
                unbind_path.write_text(pci_address)
                logger.info(f"Unbound {pci_address} from {current_driver}")

            # Get vendor:device ID
            vendor_id = (self.SYSFS_PCI_PATH / pci_address / "vendor").read_text().strip()
            device_id = (self.SYSFS_PCI_PATH / pci_address / "device").read_text().strip()
            vfio_id = f"{vendor_id} {device_id}".replace("0x", "")

            # Add new ID to vfio-pci
            new_id_path = self.SYSFS_DRIVERS_PATH / self.VFIO_DRIVER / "new_id"
            try:
                new_id_path.write_text(vfio_id)
            except OSError:
                # May already exist, which is fine
                pass

            # Bind to vfio-pci
            bind_path = self.SYSFS_DRIVERS_PATH / self.VFIO_DRIVER / "bind"
            try:
                bind_path.write_text(pci_address)
            except OSError as e:
                # May already be bound
                if self.get_current_driver(pci_address) != self.VFIO_DRIVER:
                    raise e

            logger.info(f"Bound {pci_address} to vfio-pci")

            return PassthroughResult(
                success=True,
                message=f"Successfully bound {pci_address} to vfio-pci",
                warnings=warnings,
            )

        except Exception as e:
            logger.error(f"Failed to bind {pci_address} to vfio-pci: {e}")
            return PassthroughResult(
                success=False,
                message=f"Failed to bind to vfio-pci: {e}",
            )

    def unbind_from_vfio(self, pci_address: str) -> PassthroughResult:
        """
        Unbind a device from vfio-pci and restore original driver.

        Args:
            pci_address: PCI address to unbind

        Returns:
            PassthroughResult indicating success/failure.
        """
        current_driver = self.get_current_driver(pci_address)

        if current_driver != self.VFIO_DRIVER:
            return PassthroughResult(
                success=True,
                message=f"{pci_address} not bound to vfio-pci",
            )

        try:
            # Unbind from vfio-pci
            unbind_path = self.SYSFS_DRIVERS_PATH / self.VFIO_DRIVER / "unbind"
            unbind_path.write_text(pci_address)
            logger.info(f"Unbound {pci_address} from vfio-pci")

            # Restore original driver if known
            original = self._original_drivers.get(pci_address)
            if original:
                # Trigger driver probe
                probe_path = self.SYSFS_PCI_PATH / pci_address / "driver_override"
                probe_path.write_text(original)

                rescan_path = Path("/sys/bus/pci/rescan")
                rescan_path.write_text("1")

                logger.info(f"Restored {pci_address} to {original}")

            return PassthroughResult(
                success=True,
                message=f"Unbound {pci_address} from vfio-pci",
            )

        except Exception as e:
            logger.error(f"Failed to unbind {pci_address}: {e}")
            return PassthroughResult(
                success=False,
                message=f"Failed to unbind: {e}",
            )

    def prepare_gpu_for_passthrough(
        self,
        gpu_pci_address: str,
        bind_entire_group: bool = True,
    ) -> PassthroughResult:
        """
        Prepare a GPU and related devices for passthrough.

        This binds the GPU and optionally all devices in its IOMMU group
        to vfio-pci.

        Args:
            gpu_pci_address: GPU PCI address
            bind_entire_group: Bind all devices in IOMMU group

        Returns:
            PassthroughResult indicating success/failure.
        """
        iommu_group = self.get_iommu_group(gpu_pci_address)
        if iommu_group is None:
            return PassthroughResult(
                success=False,
                message=f"Could not find IOMMU group for {gpu_pci_address}",
            )

        devices_to_bind = [gpu_pci_address]
        warnings = []

        if bind_entire_group:
            group_devices = self.get_iommu_group_devices(iommu_group)
            for device in group_devices:
                if device not in devices_to_bind:
                    devices_to_bind.append(device)
                    warnings.append(
                        f"Also binding {device} (same IOMMU group {iommu_group})"
                    )

        # Bind all devices
        failed = []
        for device in devices_to_bind:
            result = self.bind_to_vfio(device)
            if not result.success:
                failed.append(f"{device}: {result.message}")
            warnings.extend(result.warnings)

        if failed:
            return PassthroughResult(
                success=False,
                message=f"Failed to bind some devices: {'; '.join(failed)}",
                warnings=warnings,
            )

        return PassthroughResult(
            success=True,
            message=f"Prepared GPU {gpu_pci_address} for passthrough",
            warnings=warnings,
        )

    def check_passthrough_ready(self, pci_address: str) -> Tuple[bool, List[str]]:
        """
        Check if a device is ready for passthrough.

        Args:
            pci_address: PCI address to check

        Returns:
            Tuple of (ready, list of issues)
        """
        issues = []

        # Check IOMMU group exists
        iommu_group = self.get_iommu_group(pci_address)
        if iommu_group is None:
            issues.append("Device not in an IOMMU group (IOMMU not enabled?)")
            return False, issues

        # Check current driver
        driver = self.get_current_driver(pci_address)
        if driver and driver != self.VFIO_DRIVER:
            issues.append(f"Device bound to {driver}, needs vfio-pci")

        # Check other devices in IOMMU group
        group_devices = self.get_iommu_group_devices(iommu_group)
        for device in group_devices:
            if device == pci_address:
                continue
            device_driver = self.get_current_driver(device)
            if device_driver and device_driver != self.VFIO_DRIVER:
                issues.append(
                    f"IOMMU group member {device} bound to {device_driver}"
                )

        return len(issues) == 0, issues


def prepare_gpu_passthrough(gpu_pci: str) -> bool:
    """
    Convenience function to prepare a GPU for passthrough.

    Args:
        gpu_pci: GPU PCI address

    Returns:
        True if successful.
    """
    manager = GPUPassthroughManager()
    result = manager.prepare_gpu_for_passthrough(gpu_pci)
    if not result.success:
        logger.error(result.message)
    for warning in result.warnings:
        logger.warning(warning)
    return result.success
