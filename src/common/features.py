"""
Feature Management with Graceful Degradation

Provides fallback behavior when features are unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """
    Feature with fallback behavior.
    
    Attributes:
        name: Feature name
        check: Function to check if feature is available
        primary: Primary implementation
        fallback: Fallback implementation (optional)
        error_message: Message to show when feature unavailable
    """
    name: str
    check: Callable[[], bool]
    primary: Callable[..., Any]
    fallback: Optional[Callable[..., Any]] = None
    error_message: str = ""


class FeatureManager:
    """
    Manages features with graceful degradation.
    
    Example:
        manager = FeatureManager()
        
        manager.register(Feature(
            name="gpu_passthrough",
            check=lambda: check_vfio_available(),
            primary=lambda vm: setup_gpu_passthrough(vm),
            fallback=lambda vm: setup_virtual_gpu(vm),
            error_message="GPU passthrough unavailable, using virtual GPU",
        ))
        
        # Will use primary or fallback based on availability
        manager.execute("gpu_passthrough", vm)
    """

    def __init__(self):
        self._features: Dict[str, Feature] = {}
        self._availability_cache: Dict[str, bool] = {}

    def register(self, feature: Feature):
        """Register a feature."""
        self._features[feature.name] = feature
        # Clear cache when registering
        self._availability_cache.pop(feature.name, None)

    def is_available(self, name: str, use_cache: bool = True) -> bool:
        """
        Check if a feature is available.
        
        Args:
            name: Feature name
            use_cache: Use cached result if available
        """
        if name not in self._features:
            return False

        if use_cache and name in self._availability_cache:
            return self._availability_cache[name]

        feature = self._features[name]
        try:
            available = feature.check()
        except Exception as e:
            logger.debug(f"Feature check failed for {name}: {e}")
            available = False

        self._availability_cache[name] = available
        return available

    def execute(self, name: str, *args, **kwargs) -> Any:
        """
        Execute a feature, falling back if unavailable.
        
        Args:
            name: Feature name
            *args, **kwargs: Arguments to pass to feature function
            
        Returns:
            Result from primary or fallback function
            
        Raises:
            KeyError: If feature not registered
            RuntimeError: If feature unavailable and no fallback
        """
        if name not in self._features:
            raise KeyError(f"Feature not registered: {name}")

        feature = self._features[name]

        if self.is_available(name):
            return feature.primary(*args, **kwargs)
        else:
            if feature.fallback:
                if feature.error_message:
                    logger.warning(feature.error_message)
                return feature.fallback(*args, **kwargs)
            else:
                raise RuntimeError(
                    f"Feature '{name}' is unavailable and has no fallback. "
                    f"{feature.error_message}"
                )

    def clear_cache(self, name: Optional[str] = None):
        """
        Clear availability cache.
        
        Args:
            name: Specific feature to clear, or None for all
        """
        if name:
            self._availability_cache.pop(name, None)
        else:
            self._availability_cache.clear()

    def list_features(self) -> Dict[str, bool]:
        """
        List all features and their availability.
        
        Returns:
            Dict of feature_name -> is_available
        """
        return {
            name: self.is_available(name)
            for name in self._features
        }


# Global feature manager
_global_feature_manager = FeatureManager()


def register_feature(feature: Feature):
    """Register a feature with the global manager."""
    _global_feature_manager.register(feature)


def feature_available(name: str) -> bool:
    """Check if a feature is available."""
    return _global_feature_manager.is_available(name)


def execute_feature(name: str, *args, **kwargs) -> Any:
    """Execute a feature with fallback."""
    return _global_feature_manager.execute(name, *args, **kwargs)


# Common feature checks
def check_libvirt_available() -> bool:
    """Check if libvirt is available."""
    try:
        import libvirt
        conn = libvirt.open("qemu:///system")
        if conn:
            conn.close()
            return True
    except Exception:
        pass
    return False


def check_gtk_available() -> bool:
    """Check if GTK is available."""
    try:
        from gi.repository import Gtk
        return True
    except Exception:
        return False


def check_vfio_available() -> bool:
    """Check if VFIO is available."""
    try:
        with open("/proc/modules") as f:
            return "vfio" in f.read()
    except Exception:
        return False
