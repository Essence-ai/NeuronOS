"""
LibvirtManager - High-level facade for VM management.

This module provides the primary interface for interacting with libvirt.
It now delegates to specialized modules:
- LibvirtConnection for connection management
- VMLifecycleManager for start/stop/pause operations
- VMCreator for VM creation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List, Callable
from xml.etree import ElementTree as ET

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False
    libvirt = None

# Import new modular components
from .connection import LibvirtConnection
from .vm_lifecycle import VMLifecycleManager, ShutdownMethod
from .vm_creator import VMCreator
from .vm_config import VMConfig

logger = logging.getLogger(__name__)


class VMState(Enum):
    """Virtual machine states."""
    NOSTATE = 0
    RUNNING = 1
    BLOCKED = 2
    PAUSED = 3
    SHUTDOWN = 4
    SHUTOFF = 5
    CRASHED = 6
    PMSUSPENDED = 7


@dataclass
class VMInfo:
    """Information about a virtual machine."""
    name: str
    uuid: str
    state: VMState
    memory_mb: int
    vcpus: int
    has_gpu_passthrough: bool = False
    gpu_pci_address: Optional[str] = None
    has_looking_glass: bool = False


class LibvirtManager:
    """
    Manages libvirt connection and VM lifecycle.

    Provides high-level operations for:
    - Connecting to libvirt (system or session)
    - Listing and querying VMs
    - Creating VMs from templates
    - Starting/stopping VMs
    - Attaching GPU devices for passthrough
    """

    def __init__(
        self,
        uri: str = "qemu:///system",
        template_dir: Optional[Path] = None,
    ):
        """
        Initialize LibvirtManager.

        Args:
            uri: libvirt connection URI
            template_dir: Path to Jinja2 VM XML templates
        """
        if not LIBVIRT_AVAILABLE:
            raise RuntimeError(
                "libvirt-python is not installed. "
                "Install with: pip install libvirt-python"
            )

        self.uri = uri
        self.template_dir = template_dir

        # Delegate to modular components
        self._connection = LibvirtConnection(uri)
        self._lifecycle = VMLifecycleManager(self._connection)
        self._creator = VMCreator(self._connection)

        # Legacy direct connection (for backwards compatibility)
        self._conn: Optional[libvirt.virConnect] = None
        self._event_callbacks: List[Callable] = []

    def connect(self) -> bool:
        """
        Establish connection to libvirt.

        Delegates to LibvirtConnection.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self._connection.connect()
            return True
        except Exception as e:
            logger.error(f"libvirt connection error: {e}")
            return False

    def disconnect(self) -> None:
        """Close the libvirt connection."""
        self._connection.disconnect()

    @property
    def connected(self) -> bool:
        """Check if connected to libvirt."""
        return self._connection.is_connected

    def _ensure_connected(self) -> None:
        """Ensure we have an active connection."""
        if not self.connected:
            if not self.connect():
                raise RuntimeError("Not connected to libvirt")

    def list_vms(self, include_inactive: bool = True) -> List[VMInfo]:
        """
        List all virtual machines.

        Args:
            include_inactive: Include stopped VMs in the list.

        Returns:
            List of VMInfo objects.
        """
        self._ensure_connected()
        vms = []

        # Get active domains
        for domain_id in self._conn.listDomainsID():
            try:
                domain = self._conn.lookupByID(domain_id)
                vms.append(self._domain_to_info(domain))
            except libvirt.libvirtError as e:
                logger.warning(f"Error getting domain {domain_id}: {e}")

        # Get inactive domains
        if include_inactive:
            for name in self._conn.listDefinedDomains():
                try:
                    domain = self._conn.lookupByName(name)
                    vms.append(self._domain_to_info(domain))
                except libvirt.libvirtError as e:
                    logger.warning(f"Error getting domain {name}: {e}")

        return vms

    def _domain_to_info(self, domain: libvirt.virDomain) -> VMInfo:
        """Convert libvirt domain to VMInfo."""
        state, _ = domain.state()
        info = domain.info()

        # Check for GPU passthrough by parsing XML
        has_gpu, gpu_addr = self._check_gpu_passthrough(domain)

        # Check for Looking Glass
        has_lg = self._check_looking_glass(domain)

        return VMInfo(
            name=domain.name(),
            uuid=domain.UUIDString(),
            state=VMState(state),
            memory_mb=info[2] // 1024,
            vcpus=info[3],
            has_gpu_passthrough=has_gpu,
            gpu_pci_address=gpu_addr,
            has_looking_glass=has_lg,
        )

    def _check_gpu_passthrough(
        self, domain: libvirt.virDomain
    ) -> tuple[bool, Optional[str]]:
        """Check if domain has GPU passthrough configured."""
        try:
            xml = domain.XMLDesc()
            root = ET.fromstring(xml)

            for hostdev in root.findall(".//hostdev[@type='pci']"):
                source = hostdev.find("source/address")
                if source is not None:
                    domain_attr = source.get("domain", "0x0000")
                    bus = source.get("bus", "0x00")
                    slot = source.get("slot", "0x00")
                    func = source.get("function", "0x0")

                    pci_addr = f"{domain_attr}:{bus}:{slot}.{func}".replace("0x", "")
                    return True, pci_addr

        except Exception as e:
            logger.warning(f"Error parsing domain XML: {e}")

        return False, None

    def _check_looking_glass(self, domain: libvirt.virDomain) -> bool:
        """Check if domain has Looking Glass IVSHMEM configured."""
        try:
            xml = domain.XMLDesc()
            root = ET.fromstring(xml)

            # Check for shmem device with looking-glass name
            for shmem in root.findall(".//shmem"):
                name = shmem.get("name", "")
                if "looking-glass" in name.lower():
                    return True

        except Exception as e:
            logger.warning(f"Error checking Looking Glass config: {e}")

        return False

    def get_vm(self, name: str) -> Optional[VMInfo]:
        """Get VM by name."""
        self._ensure_connected()
        try:
            domain = self._conn.lookupByName(name)
            return self._domain_to_info(domain)
        except libvirt.libvirtError:
            return None

    def start_vm(self, name: str) -> bool:
        """
        Start a virtual machine.

        Delegates to VMLifecycleManager.

        Args:
            name: VM name

        Returns:
            True if started successfully.
        """
        try:
            return self._lifecycle.start(name)
        except Exception as e:
            logger.error(f"Failed to start VM {name}: {e}")
            return False

    def stop_vm(self, name: str, force: bool = False) -> bool:
        """
        Stop a virtual machine.

        Delegates to VMLifecycleManager.

        Args:
            name: VM name
            force: If True, force shutdown (destroy). If False, graceful shutdown.

        Returns:
            True if stopped successfully.
        """
        try:
            method = ShutdownMethod.FORCE if force else ShutdownMethod.GRACEFUL
            return self._lifecycle.stop(name, method=method)
        except Exception as e:
            logger.error(f"Failed to stop VM {name}: {e}")
            return False

    def create_vm_from_template(
        self,
        template_name: str,
        vm_name: str,
        **template_vars,
    ) -> Optional[str]:
        """
        Create a new VM from a Jinja2 XML template.

        Args:
            template_name: Name of template file (e.g., "windows11-passthrough.xml.j2")
            vm_name: Name for the new VM
            **template_vars: Variables to pass to template

        Returns:
            UUID of created VM, or None on failure.
        """
        self._ensure_connected()

        if self._jinja_env is None:
            logger.error("Template environment not initialized")
            return None

        try:
            template = self._jinja_env.get_template(template_name)
            xml = template.render(vm_name=vm_name, **template_vars)

            domain = self._conn.defineXML(xml)
            logger.info(f"Created VM: {vm_name}")
            return domain.UUIDString()

        except Exception as e:
            logger.error(f"Failed to create VM from template: {e}")
            return None

    def create_vm(self, config: "VMConfig") -> bool:
        """
        Generic method to create a VM from a VMConfig.

        Delegates to VMCreator.

        Args:
            config: VMConfig object

        Returns:
            True if created successfully.
        """
        try:
            return self._creator.create(config)
        except Exception as e:
            logger.error(f"Failed to create VM: {e}")
            return False

    def create_windows_vm(
        self,
        name: str,
        ram_gb: int = 8,
        cpu_cores: int = 4,
        disk_gb: int = 64,
        gpu_passthrough: bool = False,
        iso_path: Optional[str] = None,
    ) -> bool:
        """
        High-level method to create a Windows VM.

        Args:
            name: VM name
            ram_gb: RAM in GB
            cpu_cores: Number of CPU cores
            disk_gb: Disk size in GB
            gpu_passthrough: Whether to enable GPU passthrough
            iso_path: Path to Windows ISO for installation
        """
        import subprocess
        import shutil

        # Define storage directory
        storage_base = Path("/var/lib/neuron-os/vms")
        vm_dir = storage_base / name

        # Ensure directory exists
        try:
            vm_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create VM directory {vm_dir}: {e}")
            return False

        disk_path = vm_dir / "system.qcow2"
        ovmf_vars_path = vm_dir / "OVMF_VARS.fd"

        try:
            # 1. Create disk image if it doesn't exist
            if not disk_path.exists():
                logger.info(f"Creating {disk_gb}GB disk at {disk_path}")
                subprocess.run([
                    "qemu-img", "create", "-f", "qcow2",
                    str(disk_path), f"{disk_gb}G"
                ], check=True)

            # 2. Copy OVMF vars for UEFI
            if not ovmf_vars_path.exists():
                orig_vars = Path("/usr/share/edk2-ovmf/x64/OVMF_VARS.fd")
                if orig_vars.exists():
                    shutil.copy2(orig_vars, ovmf_vars_path)
                else:
                    logger.warning("OVMF variables template not found at default location")

            # 3. Handle GPU passthrough
            template_vars = {
                "memory_mb": ram_gb * 1024,
                "cpu_cores": cpu_cores,
                "vcpus": cpu_cores * 2,
                "disk_path": str(disk_path),
                "iso_path": iso_path,
                "ovmf_vars": str(ovmf_vars_path),
                "has_gpu": gpu_passthrough
            }

            if gpu_passthrough:
                # Use hardware detection to find a candidate if possible
                try:
                    # Search for hardware detect scanner
                    from hardware_detect.gpu_scanner import GPUScanner
                    scanner = GPUScanner()
                    candidate = scanner.get_passthrough_candidate()

                    if candidate:
                        # Parse address like 0000:01:00.0
                        addr_parts = candidate.pci_address.replace(":", ".").split(".")
                        if len(addr_parts) == 4:
                            template_vars.update({
                                "gpu_domain": f"0x{addr_parts[0]}",
                                "gpu_bus": f"0x{addr_parts[1]}",
                                "gpu_slot": f"0x{addr_parts[2]}",
                                "gpu_function": f"0x{addr_parts[3]}",
                                "gpu_audio_function": "0x1"
                            })
                            logger.info(f"Using GPU {candidate.pci_address} for passthrough")
                except Exception as e:
                    logger.warning(f"GPU detection failed: {e}")

            # 4. Define from template
            uuid = self.create_vm_from_template(
                "windows11-passthrough.xml.j2",
                name,
                **template_vars
            )

            return uuid is not None

        except Exception as e:
            logger.error(f"Failed to create Windows VM: {e}")
            return False

    def delete_vm(self, name: str, delete_storage: bool = False) -> bool:
        """
        Delete a virtual machine.

        Args:
            name: VM name
            delete_storage: Also delete associated storage volumes

        Returns:
            True if deleted successfully.
        """
        self._ensure_connected()
        try:
            domain = self._conn.lookupByName(name)

            # Stop if running
            if domain.isActive():
                domain.destroy()

            # Optionally delete storage
            if delete_storage:
                self._delete_vm_storage(domain)

            # Undefine the domain
            domain.undefine()
            logger.info(f"Deleted VM: {name}")
            return True

        except libvirt.libvirtError as e:
            logger.error(f"Failed to delete VM {name}: {e}")
            return False

    def _delete_vm_storage(self, domain: libvirt.virDomain) -> None:
        """Delete storage volumes associated with a VM."""
        try:
            xml = domain.XMLDesc()
            root = ET.fromstring(xml)

            for disk in root.findall(".//disk[@device='disk']/source"):
                file_path = disk.get("file")
                if file_path:
                    path = Path(file_path)
                    if path.exists():
                        path.unlink()
                        logger.info(f"Deleted storage: {file_path}")

        except Exception as e:
            logger.warning(f"Error deleting VM storage: {e}")

    def attach_gpu(
        self,
        vm_name: str,
        pci_address: str,
        include_audio: bool = True,
    ) -> bool:
        """
        Attach a GPU to a VM for passthrough.

        Args:
            vm_name: Name of the VM
            pci_address: PCI address of GPU (e.g., "0000:01:00.0")
            include_audio: Also attach the GPU's audio device

        Returns:
            True if attached successfully.
        """
        self._ensure_connected()

        # Parse PCI address
        parts = pci_address.replace(":", ".").split(".")
        if len(parts) != 4:
            logger.error(f"Invalid PCI address format: {pci_address}")
            return False

        domain_hex, bus, slot, func = parts

        hostdev_xml = f"""
        <hostdev mode='subsystem' type='pci' managed='yes'>
          <source>
            <address domain='0x{domain_hex}' bus='0x{bus}' slot='0x{slot}' function='0x{func}'/>
          </source>
        </hostdev>
        """

        try:
            domain = self._conn.lookupByName(vm_name)

            flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
            if domain.isActive():
                flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE

            domain.attachDeviceFlags(hostdev_xml, flags)
            logger.info(f"Attached GPU {pci_address} to VM {vm_name}")

            # Attach audio device if requested
            if include_audio:
                audio_addr = pci_address[:-1] + "1"  # Usually .1 for audio
                self._attach_pci_device(domain, audio_addr, flags)

            return True

        except libvirt.libvirtError as e:
            logger.error(f"Failed to attach GPU: {e}")
            return False

    def _attach_pci_device(
        self,
        domain: libvirt.virDomain,
        pci_address: str,
        flags: int,
    ) -> None:
        """Attach a generic PCI device to domain."""
        parts = pci_address.replace(":", ".").split(".")
        if len(parts) != 4:
            return

        domain_hex, bus, slot, func = parts

        hostdev_xml = f"""
        <hostdev mode='subsystem' type='pci' managed='yes'>
          <source>
            <address domain='0x{domain_hex}' bus='0x{bus}' slot='0x{slot}' function='0x{func}'/>
          </source>
        </hostdev>
        """

        try:
            domain.attachDeviceFlags(hostdev_xml, flags)
        except libvirt.libvirtError:
            pass  # Audio device may not exist


# Convenience function for simple use cases
def quick_connect(uri: str = "qemu:///system") -> LibvirtManager:
    """Create a connected LibvirtManager instance."""
    manager = LibvirtManager(uri)
    if not manager.connect():
        raise RuntimeError(f"Failed to connect to {uri}")
    return manager
