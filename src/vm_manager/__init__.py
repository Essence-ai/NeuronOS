"""
NeuronOS VM Manager

Provides libvirt-based VM management with GPU passthrough support.
"""

from .core.libvirt_manager import LibvirtManager
from .core.vm_config import VMConfig, VMState
from .passthrough.gpu_attach import GPUPassthroughManager

__all__ = [
    "LibvirtManager",
    "VMConfig",
    "VMState",
    "GPUPassthroughManager",
]
