#!/usr/bin/env python3
"""
NeuronOS Snapshot Manager

Manages system snapshots using Timeshift for safe updates and rollback.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class SnapshotType(Enum):
    """Type of snapshot."""
    ONDEMAND = "ondemand"  # User-created
    BOOT = "boot"          # Created at boot
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    PRE_UPDATE = "pre_update"  # Created before system update


@dataclass
class Snapshot:
    """Information about a system snapshot."""
    name: str
    timestamp: datetime
    snapshot_type: SnapshotType
    description: str = ""
    tags: List[str] = field(default_factory=list)
    size_mb: int = 0
    path: Optional[Path] = None

    @property
    def age_str(self) -> str:
        """Get human-readable age."""
        delta = datetime.now() - self.timestamp
        if delta.days > 0:
            return f"{delta.days} days ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600} hours ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60} minutes ago"
        else:
            return "Just now"

    @property
    def size_str(self) -> str:
        """Get human-readable size."""
        if self.size_mb >= 1024:
            return f"{self.size_mb / 1024:.1f} GB"
        return f"{self.size_mb} MB"


class SnapshotManager:
    """
    Manages system snapshots using Timeshift.

    Timeshift supports:
    - btrfs snapshots (recommended, instant and space-efficient)
    - rsync snapshots (works on any filesystem)
    """

    def __init__(self):
        self._timeshift_available = self._check_timeshift()
        self._config_path = Path("/etc/timeshift/timeshift.json")

    def _check_timeshift(self) -> bool:
        """Check if Timeshift is installed."""
        try:
            result = subprocess.run(
                ["timeshift", "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @property
    def is_available(self) -> bool:
        """Check if snapshot functionality is available."""
        return self._timeshift_available

    def get_snapshots(self) -> List[Snapshot]:
        """
        Get list of all snapshots.

        Returns:
            List of Snapshot objects, sorted by timestamp (newest first).
        """
        if not self._timeshift_available:
            return []

        snapshots = []

        try:
            result = subprocess.run(
                ["timeshift", "--list", "--scripted"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"Timeshift list failed: {result.stderr}")
                return []

            # Parse Timeshift output
            # Format: Num    Name                                              Tags    Description
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Num") or line.startswith("---") or not line.strip():
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                try:
                    # Parse timestamp from name (format: 2025-12-29_10-30-45)
                    name = parts[1]
                    ts_str = name.replace("_", " ").replace("-", ":", 2)
                    timestamp = datetime.strptime(ts_str[:19], "%Y:%m:%d %H:%M:%S")

                    # Determine type from tags
                    tags = parts[2].split(",") if len(parts) > 2 else []
                    snapshot_type = self._parse_type(tags)

                    # Description is rest of line
                    description = " ".join(parts[3:]) if len(parts) > 3 else ""

                    snapshot = Snapshot(
                        name=name,
                        timestamp=timestamp,
                        snapshot_type=snapshot_type,
                        description=description,
                        tags=tags,
                    )
                    snapshots.append(snapshot)
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse snapshot line: {line} ({e})")

        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")

        # Sort by timestamp, newest first
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)
        return snapshots

    def _parse_type(self, tags: List[str]) -> SnapshotType:
        """Parse snapshot type from tags."""
        tag_map = {
            "O": SnapshotType.ONDEMAND,
            "B": SnapshotType.BOOT,
            "H": SnapshotType.HOURLY,
            "D": SnapshotType.DAILY,
            "W": SnapshotType.WEEKLY,
            "M": SnapshotType.MONTHLY,
        }
        for tag in tags:
            if tag in tag_map:
                return tag_map[tag]
        return SnapshotType.ONDEMAND

    def create_snapshot(
        self,
        description: str = "",
        snapshot_type: SnapshotType = SnapshotType.ONDEMAND,
    ) -> Optional[Snapshot]:
        """
        Create a new system snapshot.

        Args:
            description: Optional description for the snapshot.
            snapshot_type: Type of snapshot to create.

        Returns:
            Created Snapshot object, or None on failure.
        """
        if not self._timeshift_available:
            logger.error("Timeshift not available")
            return None

        logger.info(f"Creating snapshot: {description or 'No description'}")

        try:
            cmd = ["sudo", "timeshift", "--create", "--scripted"]
            if description:
                cmd.extend(["--comments", description])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Failed to create snapshot: {result.stderr}")
                return None

            # Get the newly created snapshot
            snapshots = self.get_snapshots()
            if snapshots:
                logger.info(f"Snapshot created: {snapshots[0].name}")
                return snapshots[0]

        except subprocess.TimeoutExpired:
            logger.error("Snapshot creation timed out")
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")

        return None

    def delete_snapshot(self, snapshot: Snapshot) -> bool:
        """
        Delete a snapshot.

        Args:
            snapshot: Snapshot to delete.

        Returns:
            True if successful.
        """
        if not self._timeshift_available:
            return False

        logger.info(f"Deleting snapshot: {snapshot.name}")

        try:
            result = subprocess.run(
                ["sudo", "timeshift", "--delete", "--snapshot", snapshot.name, "--scripted"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info("Snapshot deleted successfully")
                return True
            else:
                logger.error(f"Failed to delete snapshot: {result.stderr}")

        except Exception as e:
            logger.error(f"Failed to delete snapshot: {e}")

        return False

    def restore_snapshot(self, snapshot: Snapshot, target_device: Optional[str] = None) -> bool:
        """
        Restore a snapshot.

        WARNING: This will replace current system state!

        Args:
            snapshot: Snapshot to restore.
            target_device: Optional target device (default: root device).

        Returns:
            True if restore initiated (system will reboot).
        """
        if not self._timeshift_available:
            return False

        logger.warning(f"Restoring snapshot: {snapshot.name}")

        try:
            cmd = ["sudo", "timeshift", "--restore", "--snapshot", snapshot.name, "--scripted"]
            if target_device:
                cmd.extend(["--target-device", target_device])

            # Note: This will typically require a reboot
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                logger.info("Snapshot restore initiated")
                return True
            else:
                logger.error(f"Failed to restore snapshot: {result.stderr}")

        except Exception as e:
            logger.error(f"Failed to restore snapshot: {e}")

        return False

    def create_pre_update_snapshot(self) -> Optional[Snapshot]:
        """
        Create a snapshot before system update.

        Returns:
            Created snapshot, or None on failure.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        description = f"Pre-update snapshot ({timestamp})"
        return self.create_snapshot(description, SnapshotType.PRE_UPDATE)

    def get_latest_pre_update_snapshot(self) -> Optional[Snapshot]:
        """Get the most recent pre-update snapshot."""
        snapshots = self.get_snapshots()
        for snapshot in snapshots:
            if snapshot.snapshot_type == SnapshotType.PRE_UPDATE:
                return snapshot
            if "pre-update" in snapshot.description.lower():
                return snapshot
        return None

    def configure(
        self,
        backup_device: Optional[str] = None,
        schedule_monthly: bool = True,
        schedule_weekly: bool = True,
        schedule_daily: bool = True,
        schedule_hourly: bool = False,
        schedule_boot: bool = True,
        keep_monthly: int = 2,
        keep_weekly: int = 3,
        keep_daily: int = 5,
        keep_hourly: int = 6,
        keep_boot: int = 5,
    ) -> bool:
        """
        Configure Timeshift settings.

        Args:
            backup_device: Device for storing snapshots.
            schedule_*: Enable scheduled snapshots.
            keep_*: Number of snapshots to keep for each type.

        Returns:
            True if configuration saved successfully.
        """
        try:
            config = {
                "backup_device_uuid": "",
                "parent_device_uuid": "",
                "do_first_run": False,
                "btrfs_mode": True,  # Prefer btrfs if available
                "include_btrfs_home_for_backup": False,
                "include_btrfs_home_for_restore": False,
                "stop_cron_emails": True,
                "schedule_monthly": schedule_monthly,
                "schedule_weekly": schedule_weekly,
                "schedule_daily": schedule_daily,
                "schedule_hourly": schedule_hourly,
                "schedule_boot": schedule_boot,
                "count_monthly": keep_monthly,
                "count_weekly": keep_weekly,
                "count_daily": keep_daily,
                "count_hourly": keep_hourly,
                "count_boot": keep_boot,
                "snapshot_size": "0",
                "snapshot_count": "0",
                "exclude": [],
                "exclude-apps": [],
            }

            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w") as f:
                json.dump(config, f, indent=2)

            logger.info("Timeshift configuration saved")
            return True

        except Exception as e:
            logger.error(f"Failed to configure Timeshift: {e}")
            return False
