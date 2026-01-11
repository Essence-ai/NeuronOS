"""
IVSHMEM Manager - Handles Inter-VM Shared Memory for Looking Glass.

Creates and manages shared memory devices for high-performance
display sharing between host and guest.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class IVSHMEMError(Exception):
    """Raised when IVSHMEM operation fails."""
    pass


class IVSHMEMManager:
    """
    Manages IVSHMEM (Inter-VM Shared Memory) devices.
    
    IVSHMEM is used by Looking Glass to share framebuffer data
    between the Windows guest and Linux host with minimal latency.
    """
    
    DEFAULT_SHM_PATH = Path("/dev/shm")
    DEFAULT_SIZE_MB = 128  # 128MB is typical for 1080p
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or self.DEFAULT_SHM_PATH
    
    def get_shm_path(self, vm_name: str) -> Path:
        """Get the shared memory path for a VM."""
        return self.base_path / f"looking-glass-{vm_name}"
    
    def create(self, vm_name: str, size_mb: int = DEFAULT_SIZE_MB) -> Path:
        """
        Create IVSHMEM device for a VM.
        
        Args:
            vm_name: Name of the VM
            size_mb: Size in megabytes
            
        Returns:
            Path to the created device
            
        Raises:
            IVSHMEMError: If creation fails
        """
        shm_path = self.get_shm_path(vm_name)
        size_bytes = size_mb * 1024 * 1024
        
        try:
            if shm_path.exists():
                # Check if size matches
                current_size = shm_path.stat().st_size
                if current_size != size_bytes:
                    logger.warning(
                        f"IVSHMEM size mismatch for {vm_name}: "
                        f"{current_size} != {size_bytes}, recreating"
                    )
                    shm_path.unlink()
                else:
                    logger.info(f"IVSHMEM device already exists: {shm_path}")
                    return shm_path
            
            # Create the file with correct size
            with open(shm_path, "wb") as f:
                f.truncate(size_bytes)
            
            # Set permissions (user must be in 'kvm' group typically)
            os.chmod(shm_path, 0o660)
            
            logger.info(f"Created IVSHMEM device: {shm_path} ({size_mb}MB)")
            return shm_path
            
        except Exception as e:
            raise IVSHMEMError(f"Failed to create IVSHMEM device: {e}") from e
    
    def delete(self, vm_name: str) -> bool:
        """
        Delete IVSHMEM device for a VM.
        
        Args:
            vm_name: Name of the VM
            
        Returns:
            True if deleted, False if not found
        """
        shm_path = self.get_shm_path(vm_name)
        
        if shm_path.exists():
            try:
                shm_path.unlink()
                logger.info(f"Deleted IVSHMEM device: {shm_path}")
                return True
            except Exception as e:
                logger.warning(f"Failed to delete IVSHMEM device: {e}")
                return False
        
        return False
    
    def exists(self, vm_name: str) -> bool:
        """Check if IVSHMEM device exists for a VM."""
        return self.get_shm_path(vm_name).exists()
    
    def get_size(self, vm_name: str) -> Optional[int]:
        """
        Get size of IVSHMEM device in megabytes.
        
        Returns:
            Size in MB or None if not found
        """
        shm_path = self.get_shm_path(vm_name)
        
        if shm_path.exists():
            return shm_path.stat().st_size // (1024 * 1024)
        
        return None
    
    def cleanup_all(self) -> int:
        """
        Clean up all IVSHMEM devices.
        
        Returns:
            Number of devices deleted
        """
        count = 0
        for shm_file in self.base_path.glob("looking-glass-*"):
            try:
                shm_file.unlink()
                count += 1
                logger.info(f"Cleaned up: {shm_file}")
            except Exception:
                pass
        
        return count
    
    @staticmethod
    def calculate_size_for_resolution(width: int, height: int) -> int:
        """
        Calculate recommended IVSHMEM size for a resolution.
        
        Looking Glass formula: (width * height * 4 * 2) rounded up
        with some overhead.
        
        Args:
            width: Display width
            height: Display height
            
        Returns:
            Recommended size in MB
        """
        # 4 bytes per pixel, double-buffered, with 20% overhead
        bytes_needed = width * height * 4 * 2 * 1.2
        mb_needed = int(bytes_needed / (1024 * 1024)) + 1
        
        # Round up to nearest power of 2
        size = 1
        while size < mb_needed:
            size *= 2
        
        return min(size, 512)  # Cap at 512MB


# Convenience function
def setup_looking_glass_shm(vm_name: str, size_mb: int = 128) -> Path:
    """
    Set up shared memory for Looking Glass.
    
    Args:
        vm_name: Name of the VM
        size_mb: Size in megabytes
        
    Returns:
        Path to the shared memory device
    """
    manager = IVSHMEMManager()
    return manager.create(vm_name, size_mb)
