"""
Update Verifier

Verifies system health after updates to enable automatic rollback if needed.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False

logger = logging.getLogger(__name__)


class UpdateVerifier:
    """
    Verifies system health after updates.
    
    Checks critical services, binaries, and subsystems to ensure
    the system is functioning properly after an update.
    """
    
    CRITICAL_SERVICES = [
        "sddm",           # Display manager
        "NetworkManager", # Networking
        "libvirtd",       # VM management
    ]
    
    CRITICAL_BINARIES = [
        "/usr/bin/bash",
        "/usr/bin/python3",
        "/usr/bin/systemctl",
    ]
    
    def __init__(self):
        self._issues: List[str] = []
    
    def verify_system_health(self) -> Tuple[bool, List[str]]:
        """
        Verify system is healthy after update.
        
        Runs all health checks and returns results.
        
        Returns:
            Tuple of (is_healthy, list of issues)
        """
        self._issues = []
        
        # Check critical binaries exist
        self._check_binaries()
        
        # Check systemd
        self._check_systemd()
        
        # Check critical services
        self._check_services()
        
        # Check VFIO modules
        self._check_vfio_modules()
        
        # Check libvirt
        self._check_libvirt()
        
        return len(self._issues) == 0, self._issues
    
    def _check_binaries(self) -> None:
        """Check critical binaries exist."""
        for binary in self.CRITICAL_BINARIES:
            if not Path(binary).exists():
                self._issues.append(f"Missing critical binary: {binary}")
    
    def _check_systemd(self) -> bool:
        """Check if systemd is working."""
        try:
            result = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            status = result.stdout.strip()
            if status not in ["running", "degraded"]:
                self._issues.append(f"systemd not healthy: {status}")
                return False
            return True
        except subprocess.TimeoutExpired:
            self._issues.append("systemctl command timed out")
            return False
        except FileNotFoundError:
            self._issues.append("systemctl not found")
            return False
        except Exception as e:
            self._issues.append(f"systemd check failed: {e}")
            return False
    
    def _check_services(self) -> None:
        """Check if critical services are running or can start."""
        for service in self.CRITICAL_SERVICES:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    # Service not active - check if it can be started
                    status = result.stdout.strip()
                    if status == "inactive":
                        # Service is just stopped, not failed
                        logger.debug(f"Service {service} is inactive")
                    else:
                        self._issues.append(f"Critical service failed: {service}")
            except Exception as e:
                self._issues.append(f"Failed to check service {service}: {e}")
    
    def _check_vfio_modules(self) -> bool:
        """Check if VFIO modules are loaded."""
        try:
            with open("/proc/modules") as f:
                modules = f.read()
                if "vfio" not in modules:
                    self._issues.append("VFIO kernel modules not loaded")
                    return False
            return True
        except FileNotFoundError:
            # Not on Linux or /proc not available
            logger.debug("/proc/modules not found, skipping VFIO check")
            return True
        except Exception as e:
            self._issues.append(f"VFIO check failed: {e}")
            return False
    
    def _check_libvirt(self) -> bool:
        """Check if libvirt is responding."""
        if not LIBVIRT_AVAILABLE:
            logger.debug("libvirt-python not available, skipping check")
            return True
        
        try:
            conn = libvirt.open("qemu:///system")
            if conn:
                conn.close()
                return True
            else:
                self._issues.append("libvirt daemon not responding")
                return False
        except Exception as e:
            self._issues.append(f"libvirt check failed: {e}")
            return False
    
    def get_boot_count(self) -> int:
        """
        Get boot count from systemd.
        
        Useful for determining if rollback should trigger.
        """
        try:
            result = subprocess.run(
                ["journalctl", "--list-boots", "-q"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return len(result.stdout.strip().split("\n"))
        except Exception:
            return 0


def verify_post_update() -> Tuple[bool, List[str]]:
    """
    Convenience function to verify system after update.
    
    Returns:
        Tuple of (healthy, issues)
    """
    verifier = UpdateVerifier()
    return verifier.verify_system_health()
