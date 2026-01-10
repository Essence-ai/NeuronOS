# Phase 2A: VM Manager Deep Dive

**Priority:** HIGH - Core VM functionality
**Estimated Time:** 1-2 weeks
**Prerequisites:** Phase 1 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Refactoring](#architecture-refactoring)
3. [VM Creator Implementation](#vm-creator-implementation)
4. [Looking Glass Full Integration](#looking-glass-full-integration)
5. [VM Lifecycle Management](#vm-lifecycle-management)
6. [GPU Passthrough Automation](#gpu-passthrough-automation)
7. [Template System](#template-system)

---

## Overview

The VM Manager is the heart of NeuronOS's Windows/macOS compatibility layer. This guide covers the complete implementation of production-ready VM management.

### Current Issues

| Issue | Impact | Fix Required |
|-------|--------|--------------|
| God class (LibvirtManager 529 lines) | Hard to test/maintain | Split into components |
| VM creation is stub | VMs not created | Implement VMCreator |
| Looking Glass incomplete | Display issues | Full integration |
| No error recovery | VMs can get stuck | State machine |
| Template loading fragile | Paths break | Robust template system |

---

## Architecture Refactoring

### Current Structure (Problematic)
```
vm_manager/
├── core/
│   ├── libvirt_manager.py  # 529 lines - does everything!
│   ├── looking_glass.py
│   └── vm_config.py
```

### Target Structure (Clean)
```
vm_manager/
├── core/
│   ├── connection.py       # LibVirt connection management
│   ├── vm_lifecycle.py     # Start/stop/pause operations
│   ├── vm_creator.py       # VM creation with templates
│   ├── vm_destroyer.py     # Safe VM deletion
│   ├── vm_config.py        # Configuration dataclasses
│   ├── looking_glass.py    # LG client management
│   └── state_machine.py    # VM state transitions
├── passthrough/
│   ├── gpu_attach.py       # GPU binding/unbinding
│   ├── usb_attach.py       # USB passthrough
│   └── ivshmem.py          # Shared memory for LG
├── templates/
│   ├── loader.py           # Template loading
│   ├── validator.py        # XML validation
│   └── *.xml.j2           # Jinja2 templates
└── gui/
    ├── app.py              # Main window
    ├── dialogs.py          # Creation/settings dialogs
    └── widgets.py          # Reusable widgets
```

### Step 1: Create Connection Manager

`src/vm_manager/core/connection.py`:

```python
"""
LibVirt Connection Manager

Handles connection lifecycle with automatic reconnection.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Optional, Callable

import libvirt

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Raised when libvirt connection fails."""
    pass


class LibvirtConnection:
    """
    Thread-safe libvirt connection manager.

    Provides:
    - Automatic connection
    - Connection pooling
    - Reconnection on failure
    - Event loop management
    """

    # Default connection URIs
    SYSTEM_URI = "qemu:///system"
    SESSION_URI = "qemu:///session"

    def __init__(self, uri: str = SYSTEM_URI):
        self._uri = uri
        self._conn: Optional[libvirt.virConnect] = None
        self._lock = threading.RLock()
        self._event_loop_running = False
        self._callbacks: list[Callable] = []

    @property
    def is_connected(self) -> bool:
        """Check if connected to libvirt."""
        with self._lock:
            if self._conn is None:
                return False
            try:
                self._conn.getVersion()
                return True
            except libvirt.libvirtError:
                return False

    def connect(self) -> None:
        """
        Establish connection to libvirt.

        Raises:
            ConnectionError: If connection fails
        """
        with self._lock:
            if self.is_connected:
                return

            try:
                # Register default error handler
                libvirt.registerErrorHandler(self._error_handler, None)

                # Connect
                self._conn = libvirt.open(self._uri)
                if self._conn is None:
                    raise ConnectionError(f"Failed to connect to {self._uri}")

                logger.info(f"Connected to libvirt: {self._uri}")

                # Start event loop if needed
                self._start_event_loop()

            except libvirt.libvirtError as e:
                raise ConnectionError(f"LibVirt error: {e}") from e

    def disconnect(self) -> None:
        """Close connection to libvirt."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                logger.info("Disconnected from libvirt")

    @contextmanager
    def get_connection(self):
        """
        Get a connection, reconnecting if necessary.

        Usage:
            with conn_manager.get_connection() as conn:
                domains = conn.listAllDomains()
        """
        self.connect()
        try:
            yield self._conn
        except libvirt.libvirtError as e:
            # Connection may have dropped
            logger.warning(f"LibVirt error, reconnecting: {e}")
            self._conn = None
            self.connect()
            yield self._conn

    def _error_handler(self, ctx, error):
        """Handle libvirt errors."""
        # Suppress common non-fatal errors
        if error[0] in (libvirt.VIR_ERR_WARNING, libvirt.VIR_ERR_NO_DOMAIN):
            return
        logger.debug(f"LibVirt: {error}")

    def _start_event_loop(self):
        """Start libvirt event loop for async events."""
        if self._event_loop_running:
            return

        def event_loop():
            while self._event_loop_running and self._conn:
                try:
                    libvirt.virEventRunDefaultImpl()
                except Exception:
                    break

        libvirt.virEventRegisterDefaultImpl()
        self._event_loop_running = True

        thread = threading.Thread(target=event_loop, daemon=True)
        thread.start()

    def register_domain_event(
        self,
        callback: Callable[[libvirt.virDomain, int, int], None],
    ) -> int:
        """
        Register callback for domain lifecycle events.

        Args:
            callback: Function(domain, event, detail)

        Returns:
            Callback ID for later removal
        """
        if not self.is_connected:
            self.connect()

        return self._conn.domainEventRegisterAny(
            None,
            libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
            callback,
            None,
        )


# Global connection instance
_default_connection: Optional[LibvirtConnection] = None


def get_connection(uri: str = LibvirtConnection.SYSTEM_URI) -> LibvirtConnection:
    """Get or create the default connection."""
    global _default_connection
    if _default_connection is None or _default_connection._uri != uri:
        _default_connection = LibvirtConnection(uri)
    return _default_connection
```

### Step 2: Create VM Lifecycle Manager

`src/vm_manager/core/vm_lifecycle.py`:

```python
"""
VM Lifecycle Manager

Handles VM state transitions: start, stop, pause, resume, reboot.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional, Callable

import libvirt

from .connection import get_connection, LibvirtConnection
from .vm_config import VMState

logger = logging.getLogger(__name__)


class LifecycleError(Exception):
    """Raised when a lifecycle operation fails."""
    pass


class ShutdownMethod(Enum):
    """Methods for shutting down a VM."""
    GRACEFUL = "graceful"   # ACPI shutdown signal
    FORCE = "force"         # Immediate power off
    REBOOT = "reboot"       # Graceful reboot


class VMLifecycleManager:
    """
    Manages VM lifecycle operations.

    Provides safe start/stop with proper state checking.
    """

    def __init__(self, connection: Optional[LibvirtConnection] = None):
        self._conn = connection or get_connection()

    def get_domain(self, name: str) -> Optional[libvirt.virDomain]:
        """Get domain by name."""
        with self._conn.get_connection() as conn:
            try:
                return conn.lookupByName(name)
            except libvirt.libvirtError:
                return None

    def get_state(self, name: str) -> VMState:
        """Get current VM state."""
        domain = self.get_domain(name)
        if not domain:
            return VMState.NOSTATE

        try:
            state, _ = domain.state()
            state_map = {
                libvirt.VIR_DOMAIN_NOSTATE: VMState.NOSTATE,
                libvirt.VIR_DOMAIN_RUNNING: VMState.RUNNING,
                libvirt.VIR_DOMAIN_BLOCKED: VMState.BLOCKED,
                libvirt.VIR_DOMAIN_PAUSED: VMState.PAUSED,
                libvirt.VIR_DOMAIN_SHUTDOWN: VMState.SHUTDOWN,
                libvirt.VIR_DOMAIN_SHUTOFF: VMState.SHUTOFF,
                libvirt.VIR_DOMAIN_CRASHED: VMState.CRASHED,
            }
            return state_map.get(state, VMState.NOSTATE)
        except libvirt.libvirtError:
            return VMState.NOSTATE

    def start(
        self,
        name: str,
        paused: bool = False,
        wait_timeout: int = 30,
    ) -> bool:
        """
        Start a VM.

        Args:
            name: VM name
            paused: Start in paused state
            wait_timeout: Seconds to wait for VM to start

        Returns:
            True if started successfully

        Raises:
            LifecycleError: If start fails
        """
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        current_state = self.get_state(name)
        if current_state == VMState.RUNNING:
            logger.info(f"VM {name} is already running")
            return True

        try:
            flags = 0
            if paused:
                flags |= libvirt.VIR_DOMAIN_START_PAUSED

            domain.createWithFlags(flags)
            logger.info(f"Started VM: {name}")

            # Wait for running state
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                if self.get_state(name) == VMState.RUNNING:
                    return True
                time.sleep(0.5)

            logger.warning(f"VM {name} started but not confirmed running")
            return True

        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to start {name}: {e}") from e

    def stop(
        self,
        name: str,
        method: ShutdownMethod = ShutdownMethod.GRACEFUL,
        timeout: int = 60,
    ) -> bool:
        """
        Stop a VM.

        Args:
            name: VM name
            method: Shutdown method
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped successfully
        """
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        current_state = self.get_state(name)
        if current_state == VMState.SHUTOFF:
            logger.info(f"VM {name} is already stopped")
            return True

        try:
            if method == ShutdownMethod.FORCE:
                domain.destroy()
                logger.info(f"Force stopped VM: {name}")
                return True

            elif method == ShutdownMethod.REBOOT:
                domain.reboot()
                logger.info(f"Rebooting VM: {name}")
                return True

            else:  # GRACEFUL
                domain.shutdown()
                logger.info(f"Sent shutdown signal to: {name}")

                # Wait for shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.get_state(name) == VMState.SHUTOFF:
                        return True
                    time.sleep(1)

                # Graceful shutdown timed out - force stop
                logger.warning(f"Graceful shutdown timed out for {name}, forcing...")
                domain.destroy()
                return True

        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to stop {name}: {e}") from e

    def pause(self, name: str) -> bool:
        """Pause a running VM."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.suspend()
            logger.info(f"Paused VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to pause {name}: {e}") from e

    def resume(self, name: str) -> bool:
        """Resume a paused VM."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.resume()
            logger.info(f"Resumed VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to resume {name}: {e}") from e

    def reset(self, name: str) -> bool:
        """Hard reset a VM (equivalent to reset button)."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.reset()
            logger.info(f"Reset VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to reset {name}: {e}") from e
```

---

## VM Creator Implementation

### Full VM Creator

`src/vm_manager/core/vm_creator.py`:

```python
"""
VM Creator

Creates new VMs with proper configuration for GPU passthrough and Looking Glass.
"""

from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import libvirt
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .connection import get_connection, LibvirtConnection
from .vm_config import (
    VMConfig, VMType, DisplayMode,
    GPUPassthroughConfig, LookingGlassConfig,
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
            config.disk_path = disk_path

            # Generate VM XML
            xml = self._generate_xml(config)

            # Create IVSHMEM device if Looking Glass enabled
            if config.looking_glass and config.looking_glass.enabled:
                self._setup_ivshmem(config)

            # Define the VM
            with self._conn.get_connection() as conn:
                domain = conn.defineXML(xml)
                if domain is None:
                    raise VMCreationError("Failed to define VM")

                logger.info(f"VM created: {config.name} (UUID: {domain.UUIDString()})")

            # Save configuration
            self._save_config(config)

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
        if config.memory_mb < 1024:
            raise VMCreationError("Minimum 1GB RAM required")

        if config.vcpus < 1:
            raise VMCreationError("At least 1 vCPU required")

        # Validate GPU passthrough if enabled
        if config.gpu_passthrough:
            self._validate_gpu_passthrough(config.gpu_passthrough)

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
        size_gb = config.disk_size_gb or 128

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

    def _generate_xml(self, config: VMConfig) -> str:
        """Generate libvirt XML from config."""
        template_name = self._select_template(config)

        try:
            template = self._jinja_env.get_template(template_name)
        except TemplateNotFound:
            # Fall back to generating XML directly
            logger.warning(f"Template not found: {template_name}, using fallback")
            return self._generate_fallback_xml(config)

        # Prepare template variables
        variables = self._prepare_template_vars(config)

        return template.render(**variables)

    def _select_template(self, config: VMConfig) -> str:
        """Select appropriate template based on config."""
        vm_type = config.vm_type.value.lower()
        has_gpu = config.gpu_passthrough is not None

        if has_gpu:
            return f"{vm_type}-passthrough.xml.j2"
        else:
            return f"{vm_type}-basic.xml.j2"

    def _prepare_template_vars(self, config: VMConfig) -> dict:
        """Prepare variables for template rendering."""
        vm_uuid = str(uuid.uuid4())

        vars = {
            "name": config.name,
            "uuid": vm_uuid,
            "memory_mb": config.memory_mb,
            "vcpus": config.vcpus,
            "disk_path": str(config.disk_path),
            "vm_type": config.vm_type.value,
        }

        # Add ISO if present
        if config.iso_path:
            vars["iso_path"] = str(config.iso_path)

        # Add GPU passthrough
        if config.gpu_passthrough:
            gpu = config.gpu_passthrough
            # Parse PCI address (format: 01:00.0)
            bus, rest = gpu.pci_address.split(":")
            slot, function = rest.split(".")

            vars["gpu_passthrough"] = {
                "bus": f"0x{bus}",
                "slot": f"0x{slot}",
                "function": f"0x{function}",
                "vendor_id": gpu.vendor_id,
                "device_id": gpu.device_id,
            }

            # Add audio device if HDMI audio
            if gpu.include_audio:
                vars["gpu_audio"] = {
                    "bus": f"0x{bus}",
                    "slot": f"0x{slot}",
                    "function": "0x1",  # Audio is usually .1
                }

        # Add Looking Glass
        if config.looking_glass and config.looking_glass.enabled:
            lg = config.looking_glass
            vars["looking_glass"] = {
                "shm_size_mb": lg.shm_size_mb or 128,
                "shm_path": f"/dev/shm/looking-glass-{config.name}",
            }

        return vars

    def _generate_fallback_xml(self, config: VMConfig) -> str:
        """Generate basic XML without template."""
        vm_uuid = str(uuid.uuid4())

        # Machine type based on OS
        machine = "pc-q35-8.0"

        xml = f"""<domain type='kvm'>
  <name>{config.name}</name>
  <uuid>{vm_uuid}</uuid>
  <memory unit='MiB'>{config.memory_mb}</memory>
  <vcpu placement='static'>{config.vcpus}</vcpu>
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
      <source file='{config.disk_path}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
"""

        # Add ISO if present
        if config.iso_path:
            xml += f"""    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{config.iso_path}'/>
      <target dev='sda' bus='sata'/>
      <readonly/>
    </disk>
"""

        # Add network
        xml += """    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
"""

        # Add display
        if config.display_mode == DisplayMode.LOOKING_GLASS:
            xml += """    <graphics type='spice' autoport='yes'>
      <listen type='none'/>
    </graphics>
"""
        else:
            xml += """    <graphics type='spice' autoport='yes'>
      <listen type='address' address='127.0.0.1'/>
    </graphics>
"""

        # Add GPU passthrough
        if config.gpu_passthrough:
            gpu = config.gpu_passthrough
            bus, rest = gpu.pci_address.split(":")
            slot, function = rest.split(".")

            xml += f"""    <hostdev mode='subsystem' type='pci' managed='yes'>
      <source>
        <address domain='0x0000' bus='0x{bus}' slot='0x{slot}' function='0x{function}'/>
      </source>
    </hostdev>
"""

        # Add IVSHMEM for Looking Glass
        if config.looking_glass and config.looking_glass.enabled:
            shm_size = (config.looking_glass.shm_size_mb or 128) * 1024 * 1024
            xml += f"""    <shmem name='looking-glass'>
      <model type='ivshmem-plain'/>
      <size unit='b'>{shm_size}</size>
    </shmem>
"""

        xml += """    <video>
      <model type='none'/>
    </video>
    <memballoon model='virtio'/>
  </devices>
</domain>
"""
        return xml

    def _setup_ivshmem(self, config: VMConfig) -> None:
        """Set up IVSHMEM shared memory for Looking Glass."""
        shm_path = Path(f"/dev/shm/looking-glass-{config.name}")
        shm_size = (config.looking_glass.shm_size_mb or 128) * 1024 * 1024

        # Create shared memory file
        try:
            # Create with fallocate for proper size
            subprocess.run(
                ["fallocate", "-l", str(shm_size), str(shm_path)],
                check=True,
            )

            # Set permissions (allow qemu/libvirt access)
            os.chmod(shm_path, 0o660)

            # Change ownership to qemu group
            import grp
            try:
                qemu_gid = grp.getgrnam("kvm").gr_gid
                os.chown(shm_path, -1, qemu_gid)
            except KeyError:
                pass  # kvm group doesn't exist

            logger.info(f"Created IVSHMEM: {shm_path} ({shm_size} bytes)")

        except Exception as e:
            logger.warning(f"Failed to pre-create IVSHMEM: {e}")
            # Not fatal - QEMU will create it

    def _save_config(self, config: VMConfig) -> None:
        """Save VM configuration for later reference."""
        config_dir = Path.home() / ".config/neuronos/vms" / config.name
        config_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "name": config.name,
            "vm_type": config.vm_type.value,
            "memory_mb": config.memory_mb,
            "vcpus": config.vcpus,
            "disk_path": str(config.disk_path),
            "disk_size_gb": config.disk_size_gb,
            "display_mode": config.display_mode.value if config.display_mode else None,
        }

        if config.gpu_passthrough:
            config_data["gpu_passthrough"] = {
                "pci_address": config.gpu_passthrough.pci_address,
                "vendor_id": config.gpu_passthrough.vendor_id,
                "device_id": config.gpu_passthrough.device_id,
            }

        if config.looking_glass:
            config_data["looking_glass"] = {
                "enabled": config.looking_glass.enabled,
                "shm_size_mb": config.looking_glass.shm_size_mb,
            }

        from utils.atomic_write import atomic_write_json
        atomic_write_json(config_dir / "config.json", config_data)
```

---

## Looking Glass Full Integration

### Complete Looking Glass Manager

`src/vm_manager/core/looking_glass.py`:

```python
"""
Looking Glass Client Manager

Manages Looking Glass client processes for low-latency VM display.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Callable
import threading

logger = logging.getLogger(__name__)


class LGState(Enum):
    """Looking Glass client state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class LGClientConfig:
    """Configuration for Looking Glass client."""
    vm_name: str
    shm_path: Optional[Path] = None
    fps: int = 60
    fullscreen: bool = False
    borderless: bool = True
    no_screensaver: bool = True
    grab_keyboard: bool = True
    escape_key: str = "KEY_RIGHTCTRL"
    spice_host: str = "127.0.0.1"
    spice_port: Optional[int] = None

    def __post_init__(self):
        if self.shm_path is None:
            self.shm_path = Path(f"/dev/shm/looking-glass-{self.vm_name}")


@dataclass
class LGClientState:
    """State of a Looking Glass client instance."""
    config: LGClientConfig
    state: LGState = LGState.STOPPED
    process: Optional[subprocess.Popen] = None
    error: Optional[str] = None
    start_time: Optional[float] = None


class LookingGlassManager:
    """
    Manages Looking Glass client instances.

    Features:
    - Start/stop clients for VMs
    - Automatic restart on crash
    - Fullscreen toggle
    - Wait for IVSHMEM device
    """

    # Looking Glass executable names to search
    LG_EXECUTABLES = [
        "looking-glass-client",
        "looking-glass",
        "/opt/looking-glass/client/build/looking-glass-client",
    ]

    def __init__(self):
        self._clients: Dict[str, LGClientState] = {}
        self._lock = threading.Lock()
        self._lg_path: Optional[Path] = None
        self._state_callbacks: list[Callable[[str, LGState], None]] = []

    def _find_lg_executable(self) -> Optional[Path]:
        """Find Looking Glass client executable."""
        if self._lg_path and self._lg_path.exists():
            return self._lg_path

        for name in self.LG_EXECUTABLES:
            path = Path(name)
            if path.exists() and os.access(path, os.X_OK):
                self._lg_path = path
                return path

            # Check in PATH
            import shutil
            found = shutil.which(name)
            if found:
                self._lg_path = Path(found)
                return self._lg_path

        return None

    def start(
        self,
        vm_name: str,
        config: Optional[LGClientConfig] = None,
        wait_for_shmem: bool = True,
        shmem_timeout: int = 30,
    ) -> bool:
        """
        Start Looking Glass client for a VM.

        Args:
            vm_name: Name of the VM
            config: Client configuration (uses defaults if None)
            wait_for_shmem: Wait for IVSHMEM device to be ready
            shmem_timeout: Seconds to wait for IVSHMEM

        Returns:
            True if client started successfully
        """
        with self._lock:
            # Check if already running
            if vm_name in self._clients:
                existing = self._clients[vm_name]
                if existing.state == LGState.RUNNING and existing.process:
                    if existing.process.poll() is None:
                        logger.info(f"Looking Glass already running for {vm_name}")
                        return True

            # Find executable
            lg_path = self._find_lg_executable()
            if not lg_path:
                logger.error("Looking Glass client not found")
                return False

            # Create config if not provided
            if config is None:
                config = LGClientConfig(vm_name=vm_name)

            # Wait for IVSHMEM if requested
            if wait_for_shmem:
                if not self._wait_for_shmem(config.shm_path, shmem_timeout):
                    logger.error(f"IVSHMEM not ready: {config.shm_path}")
                    return False

            # Build command line
            cmd = self._build_command(lg_path, config)

            try:
                # Start process
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )

                # Create state
                state = LGClientState(
                    config=config,
                    state=LGState.STARTING,
                    process=process,
                    start_time=time.time(),
                )
                self._clients[vm_name] = state

                # Start monitor thread
                self._start_monitor(vm_name)

                logger.info(f"Started Looking Glass for {vm_name}")
                return True

            except Exception as e:
                logger.error(f"Failed to start Looking Glass: {e}")
                return False

    def stop(self, vm_name: str, force: bool = False) -> bool:
        """Stop Looking Glass client for a VM."""
        with self._lock:
            if vm_name not in self._clients:
                return True

            state = self._clients[vm_name]
            if state.process:
                try:
                    if force:
                        state.process.kill()
                    else:
                        state.process.terminate()
                        state.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    state.process.kill()
                except Exception as e:
                    logger.warning(f"Error stopping Looking Glass: {e}")

            state.state = LGState.STOPPED
            state.process = None
            del self._clients[vm_name]

            logger.info(f"Stopped Looking Glass for {vm_name}")
            return True

    def toggle_fullscreen(self, vm_name: str) -> bool:
        """
        Toggle fullscreen mode for a Looking Glass client.

        Uses SIGUSR1 to toggle fullscreen in the running client.
        """
        with self._lock:
            if vm_name not in self._clients:
                return False

            state = self._clients[vm_name]
            if not state.process or state.process.poll() is not None:
                return False

            try:
                # Looking Glass uses SIGUSR1 to toggle fullscreen
                os.kill(state.process.pid, signal.SIGUSR1)

                # Update config
                state.config.fullscreen = not state.config.fullscreen
                logger.info(f"Toggled fullscreen for {vm_name}")
                return True

            except Exception as e:
                logger.error(f"Failed to toggle fullscreen: {e}")
                return False

    def get_state(self, vm_name: str) -> Optional[LGState]:
        """Get state of Looking Glass client."""
        with self._lock:
            if vm_name not in self._clients:
                return None
            return self._clients[vm_name].state

    def is_running(self, vm_name: str) -> bool:
        """Check if Looking Glass is running for a VM."""
        with self._lock:
            if vm_name not in self._clients:
                return False

            state = self._clients[vm_name]
            if state.process and state.process.poll() is None:
                return True
            return False

    def _wait_for_shmem(self, path: Path, timeout: int) -> bool:
        """Wait for IVSHMEM shared memory to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if path.exists():
                # Check if it has content (VM has initialized it)
                try:
                    if path.stat().st_size > 0:
                        return True
                except Exception:
                    pass
            time.sleep(0.5)

        return False

    def _build_command(self, lg_path: Path, config: LGClientConfig) -> list:
        """Build Looking Glass command line."""
        cmd = [str(lg_path)]

        # IVSHMEM device
        cmd.extend(["-f", str(config.shm_path)])

        # FPS limit
        if config.fps:
            cmd.extend(["-K", str(config.fps)])

        # Fullscreen
        if config.fullscreen:
            cmd.append("-F")

        # Borderless
        if config.borderless:
            cmd.extend(["-d"])

        # No screensaver
        if config.no_screensaver:
            cmd.append("-S")

        # Keyboard grab
        if config.grab_keyboard:
            cmd.append("-g")

        # Escape key
        if config.escape_key:
            cmd.extend(["-m", config.escape_key])

        # SPICE for clipboard/input
        if config.spice_port:
            cmd.extend(["-c", f"{config.spice_host}:{config.spice_port}"])

        return cmd

    def _start_monitor(self, vm_name: str):
        """Start thread to monitor Looking Glass process."""
        def monitor():
            time.sleep(1)  # Give it time to start

            with self._lock:
                if vm_name not in self._clients:
                    return
                state = self._clients[vm_name]

                if state.process and state.process.poll() is None:
                    state.state = LGState.RUNNING
                    self._notify_state_change(vm_name, LGState.RUNNING)
                else:
                    # Process exited immediately
                    state.state = LGState.ERROR
                    if state.process:
                        stderr = state.process.stderr.read().decode() if state.process.stderr else ""
                        state.error = stderr[:500]
                    self._notify_state_change(vm_name, LGState.ERROR)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def _notify_state_change(self, vm_name: str, state: LGState):
        """Notify callbacks of state change."""
        for callback in self._state_callbacks:
            try:
                callback(vm_name, state)
            except Exception:
                pass

    def add_state_callback(self, callback: Callable[[str, LGState], None]):
        """Add callback for state changes."""
        self._state_callbacks.append(callback)


# Singleton instance
_manager: Optional[LookingGlassManager] = None


def get_looking_glass_manager() -> LookingGlassManager:
    """Get the global Looking Glass manager instance."""
    global _manager
    if _manager is None:
        _manager = LookingGlassManager()
    return _manager
```

---

## Verification Checklist

### Before Marking Phase 2A Complete

- [ ] Connection manager handles reconnection
- [ ] VM lifecycle operations work (start/stop/pause)
- [ ] VM creator generates valid XML
- [ ] Disk images created correctly
- [ ] GPU passthrough VMs start successfully
- [ ] Looking Glass client starts automatically
- [ ] Looking Glass fullscreen toggle works
- [ ] Template loading works from multiple paths
- [ ] Error messages are helpful

### Test Commands

```bash
# Test VM creation
python -c "
from vm_manager.core.vm_creator import VMCreator
from vm_manager.core.vm_config import VMConfig, VMType

config = VMConfig(
    name='test-vm',
    vm_type=VMType.LINUX,
    memory_mb=2048,
    vcpus=2,
)

creator = VMCreator()
# Note: This will actually create a VM!
# creator.create(config)
"

# Test lifecycle
python -c "
from vm_manager.core.vm_lifecycle import VMLifecycleManager
manager = VMLifecycleManager()
print('VMs:', [manager.get_state(n) for n in ['test-vm']])
"

# Test Looking Glass
python -c "
from vm_manager.core.looking_glass import get_looking_glass_manager, LGClientConfig
lg = get_looking_glass_manager()
print('LG executable:', lg._find_lg_executable())
"
```

---

## Next Steps

After completing this phase:
1. Continue to [Phase 2B: Store Integration](./PHASE_2B_STORE_INTEGRATION.md)
2. Or proceed to [Phase 3: Feature Parity](./PHASE_3_FEATURE_PARITY.md)
