#!/usr/bin/env python3
"""
NeuronOS Update Manager

Handles system updates with automatic snapshot creation for safe rollback.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from .snapshot import SnapshotManager, Snapshot

logger = logging.getLogger(__name__)


class UpdateStatus(Enum):
    """Status of an update operation."""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    CREATING_SNAPSHOT = "creating_snapshot"
    INSTALLING = "installing"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    FAILED = "failed"
    ROLLBACK_NEEDED = "rollback_needed"


class UpdateError(Exception):
    """Error during update process."""
    pass


@dataclass
class PackageUpdate:
    """Information about a package update."""
    name: str
    old_version: str
    new_version: str
    size_bytes: int = 0
    is_security: bool = False

    @property
    def size_str(self) -> str:
        if self.size_bytes >= 1024 * 1024:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"
        elif self.size_bytes >= 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        return f"{self.size_bytes} B"


@dataclass
class UpdateInfo:
    """Information about available updates."""
    packages: List[PackageUpdate] = field(default_factory=list)
    total_download_size: int = 0
    total_install_size: int = 0
    last_check: Optional[datetime] = None
    has_security_updates: bool = False

    @property
    def package_count(self) -> int:
        return len(self.packages)

    @property
    def download_size_str(self) -> str:
        mb = self.total_download_size / (1024 * 1024)
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb:.1f} MB"


class UpdateManager:
    """
    Manages system updates with automatic snapshot creation.

    Workflow:
    1. Check for updates (pacman -Sy)
    2. Create pre-update snapshot with Timeshift
    3. Download packages (pacman -Sw)
    4. Install updates (pacman -Su)
    5. Verify system health
    6. If verification fails, offer rollback
    """

    def __init__(self):
        self.snapshot_manager = SnapshotManager()
        self.status = UpdateStatus.IDLE
        self.current_info: Optional[UpdateInfo] = None
        self.pre_update_snapshot: Optional[Snapshot] = None
        self._progress_callback: Optional[Callable[[UpdateStatus, str, float], None]] = None
        self._cancelled = False

    def set_progress_callback(
        self,
        callback: Callable[[UpdateStatus, str, float], None],
    ):
        """
        Set callback for progress updates.

        Args:
            callback: Function(status, message, percent)
        """
        self._progress_callback = callback

    def _notify(self, status: UpdateStatus, message: str, percent: float = 0):
        """Notify progress callback."""
        self.status = status
        if self._progress_callback:
            self._progress_callback(status, message, percent)

    def check_for_updates(self) -> UpdateInfo:
        """
        Check for available updates.

        Returns:
            UpdateInfo with list of available updates.
        """
        self._notify(UpdateStatus.CHECKING, "Synchronizing package databases...", 10)

        info = UpdateInfo(last_check=datetime.now())

        try:
            # Sync databases
            result = subprocess.run(
                ["sudo", "pacman", "-Sy"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning(f"Database sync warning: {result.stderr}")

            self._notify(UpdateStatus.CHECKING, "Checking for updates...", 50)

            # Check for updates (dry run)
            result = subprocess.run(
                ["pacman", "-Qu"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Parse update list
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 4:
                        # Format: package old_ver -> new_ver
                        name = parts[0]
                        old_ver = parts[1]
                        new_ver = parts[3] if parts[2] == "->" else parts[2]

                        pkg = PackageUpdate(
                            name=name,
                            old_version=old_ver,
                            new_version=new_ver,
                        )
                        info.packages.append(pkg)

                # Check for security updates
                info.has_security_updates = any(
                    "security" in p.name.lower() or
                    p.name in ["linux", "linux-lts", "openssl", "gnutls"]
                    for p in info.packages
                )

            self._notify(UpdateStatus.IDLE, f"Found {info.package_count} updates", 100)

        except subprocess.TimeoutExpired:
            logger.error("Update check timed out")
            self._notify(UpdateStatus.FAILED, "Update check timed out", 0)
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            self._notify(UpdateStatus.FAILED, str(e), 0)

        self.current_info = info
        return info

    def install_updates(
        self,
        create_snapshot: bool = True,
        verify_after: bool = True,
    ) -> bool:
        """
        Install all available updates.

        Args:
            create_snapshot: Create snapshot before updating.
            verify_after: Verify system health after update.

        Returns:
            True if updates installed successfully.
        """
        self._cancelled = False

        if not self.current_info or not self.current_info.packages:
            self._notify(UpdateStatus.IDLE, "No updates available", 0)
            return True

        try:
            # Step 1: Create pre-update snapshot
            if create_snapshot and self.snapshot_manager.is_available:
                self._notify(
                    UpdateStatus.CREATING_SNAPSHOT,
                    "Creating system snapshot...",
                    10,
                )
                self.pre_update_snapshot = self.snapshot_manager.create_pre_update_snapshot()
                if not self.pre_update_snapshot:
                    logger.warning("Failed to create snapshot, continuing without")

            if self._cancelled:
                return False

            # Step 2: Download packages
            self._notify(UpdateStatus.DOWNLOADING, "Downloading packages...", 30)
            result = subprocess.run(
                ["sudo", "pacman", "-Sw", "--noconfirm"],
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes for large updates
            )
            if result.returncode != 0:
                raise UpdateError(f"Download failed: {result.stderr}")

            if self._cancelled:
                return False

            # Step 3: Install updates
            self._notify(UpdateStatus.INSTALLING, "Installing updates...", 60)
            result = subprocess.run(
                ["sudo", "pacman", "-Su", "--noconfirm"],
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour for installation
            )
            if result.returncode != 0:
                raise UpdateError(f"Installation failed: {result.stderr}")

            # Step 4: Verify system
            if verify_after:
                self._notify(UpdateStatus.VERIFYING, "Verifying system...", 90)
                if not self._verify_system():
                    self._notify(
                        UpdateStatus.ROLLBACK_NEEDED,
                        "System verification failed",
                        100,
                    )
                    return False

            self._notify(UpdateStatus.COMPLETE, "Updates installed successfully", 100)
            return True

        except UpdateError as e:
            logger.error(f"Update failed: {e}")
            self._notify(UpdateStatus.FAILED, str(e), 0)
            return False
        except subprocess.TimeoutExpired:
            logger.error("Update operation timed out")
            self._notify(UpdateStatus.FAILED, "Operation timed out", 0)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during update: {e}")
            self._notify(UpdateStatus.FAILED, str(e), 0)
            return False

    def _verify_system(self) -> bool:
        """
        Verify system health after update.

        Checks:
        - Critical services running
        - Package database integrity
        - Boot configuration valid
        """
        try:
            # Check systemd is happy
            result = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            system_state = result.stdout.strip()
            if system_state not in ("running", "degraded"):
                logger.warning(f"System state: {system_state}")

            # Check package database
            result = subprocess.run(
                ["pacman", "-Dk"],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("Package database check found issues")

            # Check if we can still boot
            if Path("/boot/vmlinuz-linux").exists() or Path("/boot/vmlinuz-linux-lts").exists():
                return True
            else:
                logger.error("No kernel found in /boot!")
                return False

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    def cancel(self):
        """Cancel ongoing update operation."""
        self._cancelled = True

    def get_rollback_snapshot(self) -> Optional[Snapshot]:
        """Get the snapshot to rollback to."""
        return self.pre_update_snapshot or self.snapshot_manager.get_latest_pre_update_snapshot()


def check_and_update(
    auto_snapshot: bool = True,
    auto_verify: bool = True,
    progress_callback: Optional[Callable] = None,
) -> bool:
    """
    Convenience function for checking and installing updates.

    Args:
        auto_snapshot: Automatically create snapshot before update.
        auto_verify: Verify system after update.
        progress_callback: Optional progress callback.

    Returns:
        True if updates completed successfully.
    """
    manager = UpdateManager()
    if progress_callback:
        manager.set_progress_callback(progress_callback)

    info = manager.check_for_updates()
    if not info.packages:
        return True

    return manager.install_updates(
        create_snapshot=auto_snapshot,
        verify_after=auto_verify,
    )
