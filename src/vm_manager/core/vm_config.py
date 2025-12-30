"""
VM Configuration - Dataclasses for VM configuration and state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List


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


class VMType(Enum):
    """Type of virtual machine."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class DisplayMode(Enum):
    """VM display output mode."""
    SPICE = "spice"
    VNC = "vnc"
    LOOKING_GLASS = "looking_glass"
    NONE = "none"


@dataclass
class CPUConfig:
    """CPU configuration for a VM."""
    cores: int = 4
    threads: int = 1
    sockets: int = 1
    model: str = "host-passthrough"
    pinning: Optional[List[int]] = None

    @property
    def total_vcpus(self) -> int:
        return self.cores * self.threads * self.sockets


@dataclass
class MemoryConfig:
    """Memory configuration for a VM."""
    size_mb: int = 8192
    hugepages: bool = False

    @property
    def size_gb(self) -> float:
        return self.size_mb / 1024


@dataclass
class StorageConfig:
    """Storage configuration for a VM."""
    path: Path
    size_gb: int = 100
    format: str = "qcow2"
    bus: str = "virtio"
    cache: str = "writeback"

    @property
    def exists(self) -> bool:
        return self.path.exists()


@dataclass
class NetworkConfig:
    """Network configuration for a VM."""
    type: str = "bridge"
    source: str = "virbr0"
    model: str = "virtio"
    mac_address: Optional[str] = None


@dataclass
class GPUPassthroughConfig:
    """GPU passthrough configuration."""
    enabled: bool = False
    pci_address: Optional[str] = None
    include_audio: bool = True
    rom_file: Optional[Path] = None
    vendor_id: Optional[str] = None
    device_id: Optional[str] = None


@dataclass
class LookingGlassConfig:
    """Looking Glass configuration."""
    enabled: bool = False
    shm_path: str = "/dev/shm/looking-glass"
    shm_size_mb: int = 128
    width: int = 1920
    height: int = 1080


@dataclass
class VMConfig:
    """
    Complete VM configuration.

    This is the main configuration object used to define a VM.
    It can be serialized to/from JSON for persistence.
    """
    name: str
    vm_type: VMType
    cpu: CPUConfig = field(default_factory=CPUConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    storage: Optional[StorageConfig] = None
    network: NetworkConfig = field(default_factory=NetworkConfig)
    gpu: GPUPassthroughConfig = field(default_factory=GPUPassthroughConfig)
    looking_glass: LookingGlassConfig = field(default_factory=LookingGlassConfig)
    display: DisplayMode = DisplayMode.SPICE

    # Windows-specific
    tpm_enabled: bool = False
    secure_boot: bool = False
    uefi: bool = True

    # QEMU options
    machine_type: str = "q35"
    ovmf_path: Path = Path("/usr/share/edk2-ovmf/x64/OVMF_CODE.fd")
    ovmf_vars_template: Path = Path("/usr/share/edk2-ovmf/x64/OVMF_VARS.fd")

    def validate(self) -> List[str]:
        """
        Validate configuration and return list of errors.

        Returns:
            List of error messages. Empty if valid.
        """
        errors = []

        if not self.name:
            errors.append("VM name is required")

        if self.cpu.total_vcpus < 1:
            errors.append("CPU must have at least 1 vCPU")

        if self.memory.size_mb < 512:
            errors.append("Memory must be at least 512MB")

        if self.gpu.enabled and not self.gpu.pci_address:
            errors.append("GPU passthrough enabled but no PCI address specified")

        if self.looking_glass.enabled and not self.gpu.enabled:
            errors.append("Looking Glass requires GPU passthrough")

        if self.storage and not self.storage.path.parent.exists():
            errors.append(f"Storage directory does not exist: {self.storage.path.parent}")

        if self.uefi and not self.ovmf_path.exists():
            errors.append(f"OVMF firmware not found: {self.ovmf_path}")

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "vm_type": self.vm_type.value,
            "cpu": {
                "cores": self.cpu.cores,
                "threads": self.cpu.threads,
                "sockets": self.cpu.sockets,
                "model": self.cpu.model,
                "pinning": self.cpu.pinning,
            },
            "memory": {
                "size_mb": self.memory.size_mb,
                "hugepages": self.memory.hugepages,
            },
            "storage": {
                "path": str(self.storage.path) if self.storage else None,
                "size_gb": self.storage.size_gb if self.storage else None,
                "format": self.storage.format if self.storage else None,
            },
            "network": {
                "type": self.network.type,
                "source": self.network.source,
                "model": self.network.model,
            },
            "gpu": {
                "enabled": self.gpu.enabled,
                "pci_address": self.gpu.pci_address,
                "include_audio": self.gpu.include_audio,
            },
            "looking_glass": {
                "enabled": self.looking_glass.enabled,
                "shm_size_mb": self.looking_glass.shm_size_mb,
            },
            "display": self.display.value,
            "tpm_enabled": self.tpm_enabled,
            "secure_boot": self.secure_boot,
            "uefi": self.uefi,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VMConfig":
        """Create VMConfig from dictionary."""
        config = cls(
            name=data["name"],
            vm_type=VMType(data["vm_type"]),
        )

        if "cpu" in data:
            config.cpu = CPUConfig(**data["cpu"])
        if "memory" in data:
            config.memory = MemoryConfig(**data["memory"])
        if "storage" in data and data["storage"].get("path"):
            config.storage = StorageConfig(
                path=Path(data["storage"]["path"]),
                size_gb=data["storage"].get("size_gb", 100),
                format=data["storage"].get("format", "qcow2"),
            )
        if "network" in data:
            config.network = NetworkConfig(**data["network"])
        if "gpu" in data:
            config.gpu = GPUPassthroughConfig(**data["gpu"])
        if "looking_glass" in data:
            config.looking_glass = LookingGlassConfig(**data["looking_glass"])
        if "display" in data:
            config.display = DisplayMode(data["display"])

        config.tpm_enabled = data.get("tpm_enabled", False)
        config.secure_boot = data.get("secure_boot", False)
        config.uefi = data.get("uefi", True)

        return config


# Preset configurations for common setups
def windows11_gaming_preset(
    name: str = "Windows11-Gaming",
    gpu_pci: Optional[str] = None,
) -> VMConfig:
    """Create a Windows 11 gaming VM preset."""
    return VMConfig(
        name=name,
        vm_type=VMType.WINDOWS,
        cpu=CPUConfig(cores=6, threads=2),
        memory=MemoryConfig(size_mb=16384, hugepages=True),
        gpu=GPUPassthroughConfig(
            enabled=gpu_pci is not None,
            pci_address=gpu_pci,
            include_audio=True,
        ),
        looking_glass=LookingGlassConfig(
            enabled=gpu_pci is not None,
            shm_size_mb=128,
        ),
        display=DisplayMode.LOOKING_GLASS if gpu_pci else DisplayMode.SPICE,
        tpm_enabled=True,
        secure_boot=False,  # Often disabled for gaming
        uefi=True,
    )


def windows11_productivity_preset(name: str = "Windows11-Work") -> VMConfig:
    """Create a Windows 11 productivity VM preset (no GPU passthrough)."""
    return VMConfig(
        name=name,
        vm_type=VMType.WINDOWS,
        cpu=CPUConfig(cores=4, threads=1),
        memory=MemoryConfig(size_mb=8192),
        gpu=GPUPassthroughConfig(enabled=False),
        display=DisplayMode.SPICE,
        tpm_enabled=True,
        uefi=True,
    )


def macos_sonoma_preset(
    name: str = "macOS-Sonoma",
    gpu_pci: Optional[str] = None,
) -> VMConfig:
    """
    Create a macOS Sonoma VM preset.

    Note: macOS VMs require OpenCore bootloader and work best with AMD GPUs.
    NVIDIA GPUs are not supported on macOS Monterey and later.
    """
    return VMConfig(
        name=name,
        vm_type=VMType.MACOS,
        cpu=CPUConfig(cores=4, threads=2),  # 8 vCPUs
        memory=MemoryConfig(size_mb=16384, hugepages=True),
        gpu=GPUPassthroughConfig(
            enabled=gpu_pci is not None,
            pci_address=gpu_pci,
            include_audio=True,
        ),
        looking_glass=LookingGlassConfig(
            enabled=gpu_pci is not None,
            shm_size_mb=128,
        ),
        display=DisplayMode.LOOKING_GLASS if gpu_pci else DisplayMode.SPICE,
        tpm_enabled=False,  # macOS doesn't use TPM
        secure_boot=False,
        uefi=True,
    )


def macos_productivity_preset(name: str = "macOS-Work") -> VMConfig:
    """Create a macOS productivity VM preset (no GPU passthrough)."""
    return VMConfig(
        name=name,
        vm_type=VMType.MACOS,
        cpu=CPUConfig(cores=2, threads=2),  # 4 vCPUs
        memory=MemoryConfig(size_mb=8192),
        gpu=GPUPassthroughConfig(enabled=False),
        display=DisplayMode.SPICE,
        tpm_enabled=False,
        uefi=True,
    )
