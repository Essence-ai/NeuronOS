"""NeuronOS Hardware Detection Module.

This module provides automatic detection of:
- GPUs (integrated and discrete)
- IOMMU groups and passthrough compatibility
- CPU capabilities (VT-d/AMD-Vi)
- VFIO configuration generation
"""

from .gpu_scanner import GPUScanner, GPUDevice
from .iommu_parser import IOMMUParser, IOMMUGroup, IOMMUDevice
from .cpu_detect import CPUDetector, CPUInfo
from .config_generator import ConfigGenerator, VFIOConfig

__all__ = [
    # GPU Scanner
    "GPUScanner",
    "GPUDevice",
    # IOMMU Parser
    "IOMMUParser",
    "IOMMUGroup",
    "IOMMUDevice",
    # CPU Detection
    "CPUDetector",
    "CPUInfo",
    # Config Generation
    "ConfigGenerator",
    "VFIOConfig",
]

__version__ = "0.1.0"
