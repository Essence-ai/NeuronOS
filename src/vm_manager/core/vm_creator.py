"""
VM Creator

Creates new VMs with proper configuration for GPU passthrough and Looking Glass.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Optional

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False
    libvirt = None

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .connection import get_connection, LibvirtConnection
from .vm_config import (
    VMConfig, GPUPassthroughConfig,
)

logger = logging.getLogger(__name__)


class VMCreationError(Exception):
    """Raised when VM creation fails."""
    pass


class VMCreator:
    """
    Creates VMs from configuration.

    Handles:
    - Template selection based on VM type
    - Disk image creation
    - Network configuration
    - GPU passthrough setup
    - Looking Glass IVSHMEM configuration
    """

    # Default paths
    VM_IMAGES_PATH = Path("/var/lib/libvirt/images")
    TEMPLATE_PATHS = [
        Path(__file__).parent.parent / "templates",
        Path("/usr/share/neuron-os/templates"),
        Path.home() / ".config/neuronos/templates",
    ]

    def __init__(self, connection: Optional[LibvirtConnection] = None):
        self._conn = connection or get_connection()
        self._jinja_env = self._setup_jinja()

    def _setup_jinja(self) -> Environment:
        """Set up Jinja2 environment with template paths."""
        # Find first existing template directory
        template_dir = None
        for path in self.TEMPLATE_PATHS:
            if path.exists():
                template_dir = path
                break

        if template_dir is None:
            # Create default directory
            template_dir = self.TEMPLATE_PATHS[0]
            template_dir.mkdir(parents=True, exist_ok=True)

        return Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def create(self, config: VMConfig) -> bool:
        """
        Create a new VM.

        Args:
            config: VM configuration

        Returns:
            True if creation successful

        Raises:
            VMCreationError: If creation fails
        """
        logger.info(f"Creating VM: {config.name}")

        try:
            # Validate configuration
            self._validate_config(config)

            # Create disk image
            disk_path = self._create_disk(config)

            # Generate VM XML
            xml = self._generate_xml(config, disk_path)

            # Create IVSHMEM device if Looking Glass enabled
            if config.looking_glass and config.looking_glass.enabled:
                self._setup_ivshmem(config)

            # Define the VM
            with self._conn.get_connection() as conn:
                domain = conn.defineXML(xml)
                if domain is None:
                    raise VMCreationError("Failed to define VM")

                logger.info(f"VM created: {config.name} (UUID: {domain.UUIDString()})")

            return True

        except VMCreationError:
            raise
        except Exception as e:
            raise VMCreationError(f"VM creation failed: {e}") from e

    def _validate_config(self, config: VMConfig) -> None:
        """Validate VM configuration."""
        if not config.name:
            raise VMCreationError("VM name is required")

        # Check name doesn't exist
        domain = None
        with self._conn.get_connection() as conn:
            try:
                domain = conn.lookupByName(config.name)
            except libvirt.libvirtError:
                pass

        if domain is not None:
            raise VMCreationError(f"VM '{config.name}' already exists")

        # Validate resources
        if config.memory.size_mb < 1024:
            raise VMCreationError("Minimum 1GB RAM required")

        if config.cpu.total_vcpus < 1:
            raise VMCreationError("At least 1 vCPU required")

        # Validate GPU passthrough if enabled
        if config.gpu.enabled:
            self._validate_gpu_passthrough(config.gpu)

    def _validate_gpu_passthrough(self, gpu_config: GPUPassthroughConfig) -> None:
        """Validate GPU passthrough configuration."""
        # Check PCI address format
        if not gpu_config.pci_address:
            raise VMCreationError("GPU PCI address required for passthrough")

        # Check IOMMU is enabled
        iommu_path = Path("/sys/kernel/iommu_groups")
        if not iommu_path.exists() or not list(iommu_path.iterdir()):
            raise VMCreationError(
                "IOMMU not enabled. Add intel_iommu=on or amd_iommu=on to kernel parameters."
            )

    def _create_disk(self, config: VMConfig) -> Path:
        """Create disk image for VM."""
        # Ensure images directory exists
        self.VM_IMAGES_PATH.mkdir(parents=True, exist_ok=True)

        disk_path = self.VM_IMAGES_PATH / f"{config.name}.qcow2"

        if disk_path.exists():
            raise VMCreationError(f"Disk already exists: {disk_path}")

        # Create qcow2 image
        size_gb = config.storage.size_gb if config.storage else 128

        result = subprocess.run(
            [
                "qemu-img", "create",
                "-f", "qcow2",
                "-o", "preallocation=metadata,lazy_refcounts=on",
                str(disk_path),
                f"{size_gb}G",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise VMCreationError(f"Failed to create disk: {result.stderr}")

        logger.info(f"Created disk: {disk_path} ({size_gb}GB)")
        return disk_path

    def _generate_xml(self, config: VMConfig, disk_path: Path) -> str:
        """Generate libvirt XML from config."""
        template_name = self._select_template(config)

        try:
            template = self._jinja_env.get_template(template_name)
            variables = self._prepare_template_vars(config, disk_path)
            return template.render(**variables)
        except TemplateNotFound:
            # Fall back to generating XML directly
            logger.warning(f"Template not found: {template_name}, using fallback")
            return self._generate_fallback_xml(config, disk_path)

    def _select_template(self, config: VMConfig) -> str:
        """Select appropriate template based on config."""
        vm_type = config.vm_type.value.lower()
        has_gpu = config.gpu.enabled

        if has_gpu:
            return f"{vm_type}-passthrough.xml.j2"
        else:
            return f"{vm_type}-basic.xml.j2"

    def _prepare_template_vars(self, config: VMConfig, disk_path: Path) -> dict:
        """Prepare variables for template rendering."""
        vm_uuid = str(uuid.uuid4())

        vars = {
            "name": config.name,
            "uuid": vm_uuid,
            "memory_mb": config.memory.size_mb,
            "vcpus": config.cpu.total_vcpus,
            "disk_path": str(disk_path),
            "vm_type": config.vm_type.value,
        }

        # Add GPU passthrough
        if config.gpu.enabled and config.gpu.pci_address:
            gpu = config.gpu
            # Parse PCI address (format: 0000:01:00.0 or 01:00.0)
            parts = gpu.pci_address.replace(":", ".").split(".")
            if len(parts) >= 3:
                bus_val = f"0x{parts[-3]}" if len(parts) >= 3 else "0x00"
                slot_val = f"0x{parts[-2]}" if len(parts) >= 2 else "0x00"
                func_val = f"0x{parts[-1]}" if len(parts) >= 1 else "0x0"
                domain_val = f"0x{parts[0]}" if len(parts) == 4 else "0x0000"

                # Nested form (used by windows-passthrough.xml.j2)
                vars["gpu_passthrough"] = {
                    "bus": bus_val,
                    "slot": slot_val,
                    "function": func_val,
                }
                # Flat form (used by windows11-passthrough.xml.j2)
                vars["gpu_domain"] = domain_val
                vars["gpu_bus"] = bus_val
                vars["gpu_slot"] = slot_val
                vars["gpu_function"] = func_val
                vars["gpu_audio_function"] = "0x1"

        # Add Looking Glass
        if config.looking_glass and config.looking_glass.enabled:
            lg = config.looking_glass
            vars["looking_glass"] = {
                "shm_size_mb": lg.shm_size_mb,
                "shm_path": f"/dev/shm/looking-glass-{config.name}",
            }

        return vars

    def _setup_ivshmem(self, config: VMConfig) -> None:
        """Set up IVSHMEM shared memory device for Looking Glass."""
        shm_path = Path(f"/dev/shm/looking-glass-{config.name}")
        shm_size = config.looking_glass.shm_size_mb * 1024 * 1024

        if not shm_path.exists():
            with open(shm_path, "wb") as f:
                f.truncate(shm_size)
            shm_path.chmod(0o660)
            logger.info(f"Created IVSHMEM device: {shm_path}")

    def _generate_fallback_xml(self, config: VMConfig, disk_path: Path) -> str:
        """Generate basic XML without template."""
        vm_uuid = str(uuid.uuid4())
        machine = "pc-q35-8.0"

        xml = f"""<domain type='kvm'>
  <name>{config.name}</name>
  <uuid>{vm_uuid}</uuid>
  <memory unit='MiB'>{config.memory.size_mb}</memory>
  <vcpu placement='static'>{config.cpu.total_vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='{machine}'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/edk2-ovmf/x64/OVMF_CODE.fd</loader>
    <nvram>/var/lib/libvirt/qemu/nvram/{config.name}_VARS.fd</nvram>
    <boot dev='cdrom'/>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough' check='none'/>
  <clock offset='localtime'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{disk_path}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <graphics type='spice' autoport='yes'/>
    <video>
      <model type='qxl'/>
    </video>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
  </devices>
</domain>"""
        return xml
