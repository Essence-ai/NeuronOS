#!/usr/bin/env python3
"""
NeuronOS Drive Detector

Detects mounted drives and identifies Windows/macOS installations.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class DriveType(Enum):
    """Type of detected drive."""
    UNKNOWN = "unknown"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    DATA = "data"


@dataclass
class DetectedDrive:
    """Information about a detected drive."""
    device: str  # e.g., /dev/sda1
    mount_point: Optional[Path]
    label: str
    filesystem: str
    size_bytes: int
    drive_type: DriveType
    users: List[str] = field(default_factory=list)
    is_system_drive: bool = False

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

    @property
    def size_display(self) -> str:
        if self.size_gb >= 1000:
            return f"{self.size_gb / 1024:.1f} TB"
        elif self.size_gb >= 1:
            return f"{self.size_gb:.1f} GB"
        else:
            return f"{self.size_bytes / (1024 ** 2):.0f} MB"


class DriveDetector:
    """
    Detects mounted drives and identifies their type.

    Can identify:
    - Windows installations (NTFS with Windows folder)
    - macOS installations (APFS/HFS+ with Users folder structure)
    - Data drives
    """

    # Known Windows user folders
    WINDOWS_USER_FOLDERS = {
        "Documents", "Downloads", "Pictures", "Music", "Videos", "Desktop",
        "AppData",
    }

    # Known macOS user folders
    MACOS_USER_FOLDERS = {
        "Documents", "Downloads", "Pictures", "Music", "Movies", "Desktop",
        "Library", "Applications",
    }

    def __init__(self):
        self._drives: List[DetectedDrive] = []

    def scan(self) -> List[DetectedDrive]:
        """
        Scan for available drives.

        Returns:
            List of detected drives with type identification.
        """
        self._drives = []

        # Get list of block devices
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                self._parse_lsblk(data)
        except Exception as e:
            logger.warning(f"lsblk failed, falling back to /proc/mounts: {e}")
            self._parse_proc_mounts()

        # Identify drive types
        for drive in self._drives:
            if drive.mount_point:
                self._identify_drive(drive)

        return self._drives

    def _parse_lsblk(self, data: dict):
        """Parse lsblk JSON output."""
        def process_device(device: dict, parent_name: str = ""):
            name = device.get("name", "")
            dev_type = device.get("type", "")
            mountpoint = device.get("mountpoint")
            fstype = device.get("fstype", "")
            label = device.get("label", "")
            size_str = device.get("size", "0")

            # Only process partitions
            if dev_type == "part" and mountpoint:
                size_bytes = self._parse_size(size_str)
                drive = DetectedDrive(
                    device=f"/dev/{name}",
                    mount_point=Path(mountpoint) if mountpoint else None,
                    label=label or name,
                    filesystem=fstype,
                    size_bytes=size_bytes,
                    drive_type=DriveType.UNKNOWN,
                )
                self._drives.append(drive)

            # Process children
            for child in device.get("children", []):
                process_device(child, name)

        for device in data.get("blockdevices", []):
            process_device(device)

    def _parse_proc_mounts(self):
        """Fallback: parse /proc/mounts."""
        try:
            with open("/proc/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        device = parts[0]
                        mountpoint = parts[1]
                        fstype = parts[2]

                        if device.startswith("/dev/"):
                            # Get size from statvfs
                            try:
                                stat = os.statvfs(mountpoint)
                                size_bytes = stat.f_blocks * stat.f_frsize
                            except Exception:
                                size_bytes = 0

                            drive = DetectedDrive(
                                device=device,
                                mount_point=Path(mountpoint),
                                label=Path(device).name,
                                filesystem=fstype,
                                size_bytes=size_bytes,
                                drive_type=DriveType.UNKNOWN,
                            )
                            self._drives.append(drive)
        except Exception as e:
            logger.error(f"Failed to parse /proc/mounts: {e}")

    def _parse_size(self, size_str: str) -> int:
        """Parse size string (e.g., '100G', '500M') to bytes."""
        if not size_str:
            return 0

        multipliers = {
            "K": 1024,
            "M": 1024 ** 2,
            "G": 1024 ** 3,
            "T": 1024 ** 4,
        }

        size_str = size_str.upper().strip()
        for suffix, mult in multipliers.items():
            if size_str.endswith(suffix):
                try:
                    return int(float(size_str[:-1]) * mult)
                except ValueError:
                    return 0

        try:
            return int(size_str)
        except ValueError:
            return 0

    def _identify_drive(self, drive: DetectedDrive):
        """Identify the type of drive and find users."""
        if not drive.mount_point or not drive.mount_point.exists():
            return

        mount = drive.mount_point

        # Check for Windows installation
        if self._is_windows_drive(mount):
            drive.drive_type = DriveType.WINDOWS
            drive.users = self._find_windows_users(mount)
            drive.is_system_drive = (mount / "Windows" / "System32").exists()
            return

        # Check for macOS installation
        if self._is_macos_drive(mount):
            drive.drive_type = DriveType.MACOS
            drive.users = self._find_macos_users(mount)
            drive.is_system_drive = (mount / "System").exists()
            return

        # Check for Linux installation
        if self._is_linux_drive(mount):
            drive.drive_type = DriveType.LINUX
            drive.users = self._find_linux_users(mount)
            return

        # Default to data drive
        drive.drive_type = DriveType.DATA

    def _is_windows_drive(self, mount: Path) -> bool:
        """Check if mount point is a Windows installation."""
        windows_dir = mount / "Windows"
        users_dir = mount / "Users"
        return windows_dir.exists() and users_dir.exists()

    def _is_macos_drive(self, mount: Path) -> bool:
        """Check if mount point is a macOS installation."""
        users_dir = mount / "Users"
        system_dir = mount / "System"
        return users_dir.exists() and (
            system_dir.exists() or
            (mount / "Applications").exists()
        )

    def _is_linux_drive(self, mount: Path) -> bool:
        """Check if mount point is a Linux installation."""
        return (mount / "etc").exists() and (mount / "home").exists()

    def _find_windows_users(self, mount: Path) -> List[str]:
        """Find Windows user accounts."""
        users_dir = mount / "Users"
        users = []

        if users_dir.exists():
            # Skip system accounts
            skip = {"Default", "Default User", "Public", "All Users"}
            for item in users_dir.iterdir():
                if item.is_dir() and item.name not in skip:
                    # Verify it's a real user (has typical folders)
                    if any((item / folder).exists() for folder in self.WINDOWS_USER_FOLDERS):
                        users.append(item.name)

        return users

    def _find_macos_users(self, mount: Path) -> List[str]:
        """Find macOS user accounts."""
        users_dir = mount / "Users"
        users = []

        if users_dir.exists():
            skip = {"Shared", ".localized", "Guest"}
            for item in users_dir.iterdir():
                if item.is_dir() and item.name not in skip and not item.name.startswith("."):
                    if any((item / folder).exists() for folder in self.MACOS_USER_FOLDERS):
                        users.append(item.name)

        return users

    def _find_linux_users(self, mount: Path) -> List[str]:
        """Find Linux user accounts."""
        home_dir = mount / "home"
        users = []

        if home_dir.exists():
            for item in home_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    users.append(item.name)

        return users

    def get_windows_drives(self) -> List[DetectedDrive]:
        """Get only Windows drives."""
        return [d for d in self._drives if d.drive_type == DriveType.WINDOWS]

    def get_macos_drives(self) -> List[DetectedDrive]:
        """Get only macOS drives."""
        return [d for d in self._drives if d.drive_type == DriveType.MACOS]

    def mount_drive(self, device: str, mount_point: Optional[Path] = None) -> Optional[Path]:
        """
        Mount a drive if not already mounted.

        Args:
            device: Device path (e.g., /dev/sda1)
            mount_point: Optional specific mount point

        Returns:
            Mount point path if successful, None otherwise.
        """
        # Check if already mounted
        for drive in self._drives:
            if drive.device == device and drive.mount_point:
                return drive.mount_point

        # Create mount point
        if mount_point is None:
            mount_point = Path(f"/mnt/neuron-migrate-{Path(device).name}")

        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["sudo", "mount", device, str(mount_point)],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Mounted {device} at {mount_point}")
                return mount_point
            else:
                logger.error(f"Failed to mount {device}: {result.stderr.decode()}")
        except Exception as e:
            logger.error(f"Mount failed: {e}")

        return None
