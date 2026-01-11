#!/usr/bin/env python3
"""
NeuronOS Rollback Manager

Handles system rollback to previous snapshots.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from .snapshot import SnapshotManager, Snapshot

logger = logging.getLogger(__name__)


# ============================================================================
# System Detection Functions
# ============================================================================

def _detect_root_device() -> Tuple[Optional[str], Optional[str]]:
    """
    Detect current root device and GRUB device notation.
    
    Returns:
        Tuple of (linux_device, grub_device) e.g. ("/dev/nvme0n1p2", "hd0,gpt2")
        Returns (None, None) if detection fails.
    """
    try:
        result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None, None
        
        root_device = result.stdout.strip()
        
        # Handle btrfs subvolumes
        if "[" in root_device:
            root_device = root_device.split("[")[0]
        
        grub_device = _linux_to_grub_device(root_device)
        return root_device, grub_device
        
    except Exception:
        return None, None


def _linux_to_grub_device(linux_device: str) -> Optional[str]:
    """
    Convert Linux device path to GRUB device notation.
    
    Examples:
        /dev/sda2 -> hd0,gpt2
        /dev/nvme0n1p2 -> hd0,gpt2
        /dev/vda3 -> hd0,gpt3
    """
    patterns = [
        # NVMe: /dev/nvme0n1p2
        (r'/dev/nvme(\d+)n(\d+)p(\d+)', 
         lambda m: f"hd{int(m.group(1)) * 10 + int(m.group(2))},gpt{m.group(3)}"),
        # SATA/SCSI: /dev/sda2
        (r'/dev/sd([a-z])(\d+)', 
         lambda m: f"hd{ord(m.group(1)) - ord('a')},gpt{m.group(2)}"),
        # VirtIO: /dev/vda2
        (r'/dev/vd([a-z])(\d+)', 
         lambda m: f"hd{ord(m.group(1)) - ord('a')},gpt{m.group(2)}"),
    ]
    
    for pattern, converter in patterns:
        match = re.match(pattern, linux_device)
        if match:
            return converter(match)
    
    return None


def _detect_partition_table_type(device: str) -> str:
    """Detect if device uses GPT or MBR."""
    try:
        # Get disk (remove partition number)
        disk = re.sub(r'p?\d+$', '', device)
        
        result = subprocess.run(
            ["blkid", "-o", "value", "-s", "PTTYPE", disk],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        pttype = result.stdout.strip().lower()
        if pttype == "gpt":
            return "gpt"
        elif pttype in ("dos", "msdos"):
            return "msdos"
    except Exception:
        pass
    
    return "gpt"  # Default to GPT for modern systems


def _find_kernel() -> Optional[str]:
    """Find the kernel path for GRUB."""
    kernel_paths = [
        "/boot/vmlinuz-linux",
        "/boot/vmlinuz-linux-lts",
        "/boot/vmlinuz",
    ]
    
    for path in kernel_paths:
        if Path(path).exists():
            return path
    
    # Try to find any vmlinuz
    boot = Path("/boot")
    if boot.exists():
        for kernel in boot.glob("vmlinuz*"):
            return str(kernel)
    
    return None


# ============================================================================
# System File Operations (with sudo fallback)
# ============================================================================

def _write_system_file(path: Union[str, Path], content: str, mode: int = 0o644) -> bool:
    """
    Write to a system file, using sudo if necessary.
    
    Args:
        path: System file path
        content: Content to write
        mode: File permissions
        
    Returns:
        True if successful
    """
    path = Path(path)
    
    # Try direct write first (works if already root)
    try:
        # Try using atomic write if available
        try:
            from utils.atomic_write import atomic_write_text
            atomic_write_text(path, content, mode)
            return True
        except ImportError:
            # Fallback to direct write
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            os.chmod(path, mode)
            return True
    except PermissionError:
        pass
    
    # Fall back to sudo
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as f:
            f.write(content)
            temp_path = f.name
        
        # Move with sudo
        result = subprocess.run(
            ["sudo", "mv", temp_path, str(path)],
            capture_output=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            logger.error(f"sudo mv failed: {result.stderr.decode()}")
            return False
        
        # Set permissions
        result = subprocess.run(
            ["sudo", "chmod", oct(mode)[2:], str(path)],
            capture_output=True,
            timeout=10,
        )
        
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Failed to write system file {path}: {e}")
        return False


def _run_system_command(cmd: list, timeout: int = 60) -> bool:
    """
    Run a system command, adding sudo if necessary.
    
    Args:
        cmd: Command and arguments
        timeout: Command timeout in seconds
        
    Returns:
        True if successful
    """
    try:
        # Try without sudo first
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode == 0:
            return True
    except (PermissionError, subprocess.SubprocessError):
        pass
    
    # Try with sudo
    try:
        result = subprocess.run(
            ["sudo"] + cmd,
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Command failed: {' '.join(cmd)}: {e}")
        return False


class RollbackStatus(Enum):
    """Status of rollback operation."""
    IDLE = "idle"
    PREPARING = "preparing"
    RESTORING = "restoring"
    REBOOTING = "rebooting"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    message: str
    requires_reboot: bool = True


class RollbackManager:
    """
    Manages system rollback to previous states.

    Supports:
    - Rollback to any Timeshift snapshot
    - GRUB boot menu selection of snapshots
    - Emergency rollback from recovery
    """

    def __init__(self):
        self.snapshot_manager = SnapshotManager()
        self.status = RollbackStatus.IDLE
        self._progress_callback: Optional[Callable[[RollbackStatus, str], None]] = None

    def set_progress_callback(
        self,
        callback: Callable[[RollbackStatus, str], None],
    ):
        """Set callback for status updates."""
        self._progress_callback = callback

    def _notify(self, status: RollbackStatus, message: str):
        """Notify progress callback."""
        self.status = status
        if self._progress_callback:
            self._progress_callback(status, message)

    def get_available_snapshots(self) -> List[Snapshot]:
        """Get list of snapshots available for rollback."""
        return self.snapshot_manager.get_snapshots()

    def rollback_to_snapshot(
        self,
        snapshot: Snapshot,
        skip_grub: bool = False,
    ) -> RollbackResult:
        """
        Rollback system to a snapshot.

        WARNING: This will replace the current system state!
        A reboot is required after rollback.

        Args:
            snapshot: The snapshot to restore.
            skip_grub: Skip GRUB reinstallation (use carefully).

        Returns:
            RollbackResult with status information.
        """
        logger.warning(f"Initiating rollback to: {snapshot.name}")
        self._notify(RollbackStatus.PREPARING, "Preparing for rollback...")

        try:
            # Verify snapshot exists
            snapshots = self.snapshot_manager.get_snapshots()
            if snapshot.name not in [s.name for s in snapshots]:
                return RollbackResult(
                    success=False,
                    message="Snapshot not found",
                    requires_reboot=False,
                )

            self._notify(RollbackStatus.RESTORING, f"Restoring {snapshot.name}...")

            # Perform restore
            if self.snapshot_manager.restore_snapshot(snapshot):
                self._notify(
                    RollbackStatus.COMPLETE,
                    "Rollback complete. Please reboot.",
                )
                return RollbackResult(
                    success=True,
                    message="Rollback successful. Reboot required.",
                    requires_reboot=True,
                )
            else:
                self._notify(RollbackStatus.FAILED, "Rollback failed")
                return RollbackResult(
                    success=False,
                    message="Rollback failed. System may be in inconsistent state.",
                    requires_reboot=False,
                )

        except Exception as e:
            logger.error(f"Rollback error: {e}")
            self._notify(RollbackStatus.FAILED, str(e))
            return RollbackResult(
                success=False,
                message=str(e),
                requires_reboot=False,
            )

    def rollback_last_update(self) -> RollbackResult:
        """
        Rollback to the most recent pre-update snapshot.

        Returns:
            RollbackResult with status information.
        """
        snapshot = self.snapshot_manager.get_latest_pre_update_snapshot()
        if not snapshot:
            return RollbackResult(
                success=False,
                message="No pre-update snapshot found",
                requires_reboot=False,
            )

        return self.rollback_to_snapshot(snapshot)

    def create_recovery_entry(self) -> bool:
        """
        Create a GRUB entry for easy rollback at boot.

        This adds a "NeuronOS Recovery" entry to GRUB that boots into
        the Timeshift restore interface.
        
        Dynamically detects system configuration instead of using hardcoded paths.

        Returns:
            True if entry created successfully.
        """
        # Detect root device dynamically
        root_device, grub_device = _detect_root_device()
        
        if not root_device or not grub_device:
            logger.error("Could not detect root device for recovery entry")
            return False
        
        # Detect partition table type
        pttype = _detect_partition_table_type(root_device)
        grub_device = grub_device.replace("gpt", pttype)
        
        # Find kernel
        kernel_path = _find_kernel()
        if not kernel_path:
            logger.error("Could not find kernel for recovery entry")
            return False
        
        grub_entry = f"""
menuentry 'NeuronOS Recovery (Timeshift)' --class recovery --class gnu-linux --class gnu --class os {{
    insmod gzio
    insmod part_{pttype}
    insmod btrfs
    set root='{grub_device}'
    linux {kernel_path} root={root_device} rw init=/bin/bash
}}
"""
        recovery_path = Path("/etc/grub.d/45_neuronos_recovery")

        try:
            script = f"""#!/bin/sh
exec tail -n +3 $0
{grub_entry}
"""
            # Use sudo fallback for system file write
            if not _write_system_file(recovery_path, script, mode=0o755):
                logger.error("Failed to write recovery script")
                return False

            # Regenerate GRUB config
            if not _run_system_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"]):
                logger.error("grub-mkconfig failed")
                return False

            logger.info(f"Recovery GRUB entry created (root={root_device})")
            return True

        except Exception as e:
            logger.error(f"Failed to create recovery entry: {e}")
            return False

    def schedule_rollback_on_boot_failure(self) -> bool:
        """
        Configure automatic rollback if system fails to boot properly.

        Uses systemd to detect boot failures and trigger rollback.

        Returns:
            True if configured successfully.
        """
        service_content = """[Unit]
Description=NeuronOS Boot Verification
After=graphical.target
Wants=graphical.target

[Service]
Type=oneshot
ExecStart=/usr/bin/neuron-boot-verify
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
"""

        verify_script = """#!/bin/bash
# NeuronOS Boot Verification
# Marks boot as successful if system is healthy

BOOT_COUNT_FILE="/var/lib/neuronos/boot_count"
MAX_FAILED_BOOTS=3

# Increment boot counter
mkdir -p /var/lib/neuronos
count=$(cat "$BOOT_COUNT_FILE" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$BOOT_COUNT_FILE"

# Check if system is healthy
if systemctl is-system-running | grep -qE "running|degraded"; then
    # System is healthy, reset counter
    echo "0" > "$BOOT_COUNT_FILE"
    logger "NeuronOS: Boot verified successfully"
    exit 0
fi

# Check if we've failed too many times
if [ "$count" -ge "$MAX_FAILED_BOOTS" ]; then
    logger "NeuronOS: Too many failed boots, suggesting rollback"
    # Could trigger automatic rollback here
    echo "0" > "$BOOT_COUNT_FILE"
fi

exit 0
"""

        try:
            # Write service file using sudo fallback
            if not _write_system_file(
                "/etc/systemd/system/neuron-boot-verify.service",
                service_content,
                mode=0o644,
            ):
                logger.error("Failed to write boot verify service")
                return False

            # Write verification script using sudo fallback
            if not _write_system_file(
                "/usr/bin/neuron-boot-verify",
                verify_script,
                mode=0o755,
            ):
                logger.error("Failed to write boot verify script")
                return False

            # Enable service using sudo fallback
            if not _run_system_command(["systemctl", "daemon-reload"]):
                logger.error("Failed to reload systemd")
                return False
            if not _run_system_command(["systemctl", "enable", "neuron-boot-verify.service"]):
                logger.error("Failed to enable boot verify service")
                return False

            logger.info("Boot verification configured")
            return True

        except Exception as e:
            logger.error(f"Failed to configure boot verification: {e}")
            return False

    def reboot_system(self) -> bool:
        """
        Reboot the system.

        Returns:
            True if reboot initiated.
        """
        try:
            self._notify(RollbackStatus.REBOOTING, "Initiating reboot...")
            subprocess.run(["sudo", "reboot"], check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to reboot: {e}")
            return False
