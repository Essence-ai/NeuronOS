"""
VM Destroyer

Safe deletion of virtual machines with proper cleanup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False
    libvirt = None

from .connection import get_connection, LibvirtConnection
from .vm_lifecycle import VMLifecycleManager, ShutdownMethod
from ..passthrough.ivshmem import IVSHMEMManager

logger = logging.getLogger(__name__)


class VMDestructionError(Exception):
    """Raised when VM deletion fails."""
    pass


class VMDestroyer:
    """
    Safely deletes virtual machines.
    
    Handles:
    - Stopping running VMs before deletion
    - Removing storage volumes
    - Cleaning up IVSHMEM devices
    - Removing configuration
    """
    
    def __init__(self, connection: Optional[LibvirtConnection] = None):
        self._conn = connection or get_connection()
        self._lifecycle = VMLifecycleManager(self._conn)
        self._ivshmem = IVSHMEMManager()
    
    def delete(
        self,
        name: str,
        delete_storage: bool = False,
        force_stop: bool = False,
        cleanup_ivshmem: bool = True,
    ) -> bool:
        """
        Delete a virtual machine.
        
        Args:
            name: VM name
            delete_storage: Also delete associated storage volumes
            force_stop: Force stop if VM is running
            cleanup_ivshmem: Clean up Looking Glass shared memory
            
        Returns:
            True if deleted successfully
            
        Raises:
            VMDestructionError: If deletion fails
        """
        logger.info(f"Deleting VM: {name}")
        
        with self._conn.get_connection() as conn:
            try:
                domain = conn.lookupByName(name)
            except libvirt.libvirtError:
                raise VMDestructionError(f"VM not found: {name}")
            
            # Stop if running
            if domain.isActive():
                if force_stop:
                    logger.info(f"Force stopping VM before deletion: {name}")
                    self._lifecycle.stop(name, method=ShutdownMethod.FORCE)
                else:
                    raise VMDestructionError(
                        f"VM {name} is running. Stop it first or use force_stop=True"
                    )
            
            # Delete storage if requested
            if delete_storage:
                self._delete_storage(domain)
            
            # Undefine (delete) the VM
            try:
                # Use flags to also remove snapshots, nvram, etc.
                flags = 0
                if LIBVIRT_AVAILABLE:
                    flags = libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
                domain.undefineFlags(flags)
            except libvirt.libvirtError:
                # Fallback to basic undefine
                domain.undefine()
            
            logger.info(f"Deleted VM: {name}")
            
            # Cleanup IVSHMEM
            if cleanup_ivshmem:
                self._ivshmem.delete(name)
            
            return True
    
    def _delete_storage(self, domain) -> None:
        """Delete all storage volumes associated with a VM."""
        try:
            xml = domain.XMLDesc()
            from xml.etree import ElementTree as ET
            root = ET.fromstring(xml)
            
            for disk in root.findall(".//disk[@device='disk']"):
                source = disk.find("source")
                if source is not None:
                    file_path = source.get("file")
                    if file_path:
                        path = Path(file_path)
                        if path.exists():
                            path.unlink()
                            logger.info(f"Deleted disk: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete some storage: {e}")


def delete_vm(name: str, delete_storage: bool = False) -> bool:
    """
    Convenience function to delete a VM.
    
    Args:
        name: VM name
        delete_storage: Also delete storage
        
    Returns:
        True if successful
    """
    destroyer = VMDestroyer()
    return destroyer.delete(name, delete_storage=delete_storage, force_stop=True)
