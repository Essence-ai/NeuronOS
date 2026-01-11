"""
NeuronOS Common Utilities

Shared utilities and widgets for NeuronOS applications.
"""

from .dialogs import show_error, show_confirmation, show_progress
from .exceptions import (
    NeuronError, VMError, VMNotFoundError, VMStartError, VMStopError,
    VMCreationError, VMStateError, HardwareError, GPUNotFoundError,
    IOMMUError, VFIOError, InstallError, DependencyError, DownloadError,
    ChecksumError, ConnectionError, LibvirtConnectionError,
    GuestAgentConnectionError, ConfigError, InvalidConfigError,
    MissingConfigError, PermissionError, TemplateError, TemplateNotFoundError,
    TemplateRenderError,
)
from .decorators import (
    handle_errors, retry, ensure_connected, deprecated, require_root, timed,
)
from .logging_config import setup_logging, get_logger, LogContext
from .resources import ManagedResource, ResourcePool, register_cleanup, cleanup_all
from .singleton import ThreadSafeSingleton, LazySingleton, ReadWriteLock, AtomicCounter
from .features import (
    Feature, FeatureManager, register_feature, feature_available, execute_feature,
)

__all__ = [
    # Dialogs
    "show_error", "show_confirmation", "show_progress",
    # Exceptions
    "NeuronError", "VMError", "VMNotFoundError", "VMStartError", "VMStopError",
    "VMCreationError", "VMStateError", "HardwareError", "GPUNotFoundError",
    "IOMMUError", "VFIOError", "InstallError", "DependencyError", "DownloadError",
    "ChecksumError", "ConnectionError", "LibvirtConnectionError",
    "GuestAgentConnectionError", "ConfigError", "InvalidConfigError",
    "MissingConfigError", "PermissionError", "TemplateError", "TemplateNotFoundError",
    "TemplateRenderError",
    # Decorators
    "handle_errors", "retry", "ensure_connected", "deprecated", "require_root", "timed",
    # Logging
    "setup_logging", "get_logger", "LogContext",
    # Resources
    "ManagedResource", "ResourcePool", "register_cleanup", "cleanup_all",
    # Singletons
    "ThreadSafeSingleton", "LazySingleton", "ReadWriteLock", "AtomicCounter",
    # Features
    "Feature", "FeatureManager", "register_feature", "feature_available", "execute_feature",
]
