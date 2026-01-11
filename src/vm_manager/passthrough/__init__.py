"""
GPU Passthrough Module - Handles VFIO device attachment and management.
"""

from .gpu_attach import GPUPassthroughManager
from .ivshmem import IVSHMEMManager

__all__ = ["GPUPassthroughManager", "IVSHMEMManager"]
