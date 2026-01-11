"""
NeuronOS Exception Hierarchy

Provides clear, actionable error messages with structured information
for logging, user feedback, and programmatic error handling.
"""

from typing import Optional, Dict, Any


class NeuronError(Exception):
    """
    Base exception for all NeuronOS errors.
    
    Attributes:
        message: Human-readable error message
        code: Machine-readable error code
        details: Additional context as key-value pairs
        cause: Original exception that caused this error
        recoverable: Whether the error is recoverable
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.cause = cause
        self.recoverable = recoverable

    def __str__(self):
        s = f"[{self.code}] {self.message}"
        if self.details:
            s += f" (details: {self.details})"
        if self.cause:
            s += f" caused by: {self.cause}"
        return s

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }


# =============================================================================
# VM-related errors
# =============================================================================

class VMError(NeuronError):
    """Base for VM-related errors."""
    pass


class VMNotFoundError(VMError):
    """VM does not exist."""
    def __init__(self, vm_name: str):
        super().__init__(
            f"Virtual machine '{vm_name}' not found",
            code="VM_NOT_FOUND",
            details={"vm_name": vm_name},
            recoverable=False,
        )


class VMStartError(VMError):
    """Failed to start VM."""
    def __init__(self, vm_name: str, reason: str):
        super().__init__(
            f"Failed to start VM '{vm_name}': {reason}",
            code="VM_START_FAILED",
            details={"vm_name": vm_name, "reason": reason},
        )


class VMStopError(VMError):
    """Failed to stop VM."""
    def __init__(self, vm_name: str, reason: str):
        super().__init__(
            f"Failed to stop VM '{vm_name}': {reason}",
            code="VM_STOP_FAILED",
            details={"vm_name": vm_name, "reason": reason},
        )


class VMCreationError(VMError):
    """Failed to create VM."""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(
            message,
            code="VM_CREATION_FAILED",
            cause=cause,
        )


class VMStateError(VMError):
    """Invalid VM state for operation."""
    def __init__(self, vm_name: str, current_state: str, required_state: str):
        super().__init__(
            f"VM '{vm_name}' is in state '{current_state}', requires '{required_state}'",
            code="VM_INVALID_STATE",
            details={
                "vm_name": vm_name,
                "current_state": current_state,
                "required_state": required_state,
            },
        )


# =============================================================================
# Hardware-related errors
# =============================================================================

class HardwareError(NeuronError):
    """Base for hardware-related errors."""
    pass


class GPUNotFoundError(HardwareError):
    """No suitable GPU found for passthrough."""
    def __init__(self, reason: str = "No discrete GPU available"):
        super().__init__(
            reason,
            code="GPU_NOT_FOUND",
            recoverable=False,
        )


class IOMMUError(HardwareError):
    """IOMMU not properly configured."""
    def __init__(self, message: str = "IOMMU not enabled"):
        super().__init__(
            f"{message}. Enable IOMMU in BIOS and add kernel parameters.",
            code="IOMMU_ERROR",
            details={
                "intel_param": "intel_iommu=on iommu=pt",
                "amd_param": "amd_iommu=on iommu=pt",
            },
            recoverable=False,
        )


class VFIOError(HardwareError):
    """VFIO binding failed."""
    def __init__(self, pci_address: str, reason: str):
        super().__init__(
            f"Failed to bind {pci_address} to VFIO: {reason}",
            code="VFIO_BIND_FAILED",
            details={"pci_address": pci_address, "reason": reason},
        )


# =============================================================================
# Installation errors
# =============================================================================

class InstallError(NeuronError):
    """Base for installation errors."""
    pass


class DependencyError(InstallError):
    """Missing dependency."""
    def __init__(self, dependency: str, package: Optional[str] = None):
        super().__init__(
            f"Missing dependency: {dependency}",
            code="MISSING_DEPENDENCY",
            details={"dependency": dependency, "package": package},
        )


class DownloadError(InstallError):
    """Download failed."""
    def __init__(self, url: str, reason: str):
        super().__init__(
            f"Failed to download: {reason}",
            code="DOWNLOAD_FAILED",
            details={"url": url, "reason": reason},
        )


class ChecksumError(InstallError):
    """Checksum verification failed."""
    def __init__(self, filename: str, expected: str, actual: str):
        super().__init__(
            f"Checksum mismatch for {filename}",
            code="CHECKSUM_MISMATCH",
            details={
                "filename": filename,
                "expected": expected,
                "actual": actual,
            },
            recoverable=False,
        )


# =============================================================================
# Connection errors
# =============================================================================

class ConnectionError(NeuronError):
    """Base for connection-related errors."""
    pass


class LibvirtConnectionError(ConnectionError):
    """Failed to connect to libvirt."""
    def __init__(self, uri: str, cause: Optional[Exception] = None):
        super().__init__(
            f"Cannot connect to libvirt at {uri}",
            code="LIBVIRT_CONNECTION_FAILED",
            details={"uri": uri},
            cause=cause,
        )


class GuestAgentConnectionError(ConnectionError):
    """Failed to connect to guest agent."""
    def __init__(self, vm_name: str):
        super().__init__(
            f"Cannot connect to guest agent in VM '{vm_name}'",
            code="GUEST_AGENT_UNAVAILABLE",
            details={"vm_name": vm_name},
        )


# =============================================================================
# Configuration errors
# =============================================================================

class ConfigError(NeuronError):
    """Base for configuration errors."""
    pass


class InvalidConfigError(ConfigError):
    """Invalid configuration."""
    def __init__(self, field: str, value: Any, reason: str):
        super().__init__(
            f"Invalid configuration: {field}={value}: {reason}",
            code="INVALID_CONFIG",
            details={"field": field, "value": str(value), "reason": reason},
        )


class MissingConfigError(ConfigError):
    """Required configuration missing."""
    def __init__(self, field: str):
        super().__init__(
            f"Missing required configuration: {field}",
            code="MISSING_CONFIG",
            details={"field": field},
        )


# =============================================================================
# Permission errors
# =============================================================================

class PermissionError(NeuronError):
    """Permission denied."""
    def __init__(self, resource: str, operation: str):
        super().__init__(
            f"Permission denied: {operation} on {resource}",
            code="PERMISSION_DENIED",
            details={"resource": resource, "operation": operation},
        )


# =============================================================================
# Template errors
# =============================================================================

class TemplateError(NeuronError):
    """Template-related errors."""
    pass


class TemplateNotFoundError(TemplateError):
    """Template not found."""
    def __init__(self, template_name: str):
        super().__init__(
            f"Template not found: {template_name}",
            code="TEMPLATE_NOT_FOUND",
            details={"template": template_name},
        )


class TemplateRenderError(TemplateError):
    """Template rendering failed."""
    def __init__(self, template_name: str, reason: str):
        super().__init__(
            f"Failed to render template '{template_name}': {reason}",
            code="TEMPLATE_RENDER_FAILED",
            details={"template": template_name, "reason": reason},
        )
