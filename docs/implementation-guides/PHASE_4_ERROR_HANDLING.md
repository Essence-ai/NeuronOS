# Phase 4: Error Handling & Robustness

**Priority:** MEDIUM - Required for stability
**Estimated Time:** 1-2 weeks
**Prerequisites:** Phase 3 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Exception Handling Strategy](#exception-handling-strategy)
3. [Logging Framework](#logging-framework)
4. [Resource Management](#resource-management)
5. [Thread Safety](#thread-safety)
6. [Graceful Degradation](#graceful-degradation)

---

## Overview

This phase transforms the codebase from "works in happy path" to "handles errors gracefully."

### Current Issues

| Issue | Count | Impact |
|-------|-------|--------|
| Bare `except: pass` | 25+ | Silent failures |
| Missing null checks | 15+ | Crashes |
| Unclosed resources | 20+ | Resource leaks |
| Non-thread-safe singletons | 7+ | Race conditions |
| Unclear error messages | 30+ | Hard to debug |

---

## Exception Handling Strategy

### Hierarchy of Custom Exceptions

Create `src/common/exceptions.py`:

```python
"""
NeuronOS Exception Hierarchy

Provides clear, actionable error messages.
"""

from typing import Optional, Dict, Any


class NeuronError(Exception):
    """Base exception for all NeuronOS errors."""

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


# VM-related errors
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


class VMCreationError(VMError):
    """Failed to create VM."""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(
            message,
            code="VM_CREATION_FAILED",
            cause=cause,
        )


# Hardware-related errors
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
                "intel_param": "intel_iommu=on",
                "amd_param": "amd_iommu=on",
            },
            recoverable=False,
        )


# Installation errors
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


# Connection errors
class ConnectionError(NeuronError):
    """Connection-related errors."""
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


# Configuration errors
class ConfigError(NeuronError):
    """Configuration errors."""
    pass


class InvalidConfigError(ConfigError):
    """Invalid configuration."""
    def __init__(self, field: str, value: Any, reason: str):
        super().__init__(
            f"Invalid configuration: {field}={value}: {reason}",
            code="INVALID_CONFIG",
            details={"field": field, "value": value, "reason": reason},
        )


# Permission errors
class PermissionError(NeuronError):
    """Permission denied."""
    def __init__(self, resource: str, operation: str):
        super().__init__(
            f"Permission denied: {operation} on {resource}",
            code="PERMISSION_DENIED",
            details={"resource": resource, "operation": operation},
        )
```

### Replace Bare Excepts

Find and replace all bare exception handlers:

```bash
# Find all bare except clauses
grep -rn "except:" src/ --include="*.py"
grep -rn "except Exception:" src/ --include="*.py"
```

**Before:**
```python
try:
    do_something()
except:
    pass
```

**After:**
```python
try:
    do_something()
except SpecificError as e:
    logger.warning(f"Expected error handled: {e}")
    # Handle specifically
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise NeuronError("Operation failed", cause=e) from e
```

### Error Handler Decorator

```python
# src/common/decorators.py

import functools
import logging
from typing import Type, Tuple, Callable, Any

logger = logging.getLogger(__name__)


def handle_errors(
    *exception_types: Type[Exception],
    default: Any = None,
    log_level: int = logging.ERROR,
    reraise: bool = False,
):
    """
    Decorator to handle exceptions consistently.

    Args:
        exception_types: Exception types to catch (default: Exception)
        default: Value to return on error
        log_level: Logging level for errors
        reraise: Whether to re-raise after logging
    """
    if not exception_types:
        exception_types = (Exception,)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                logger.log(
                    log_level,
                    f"{func.__name__} failed: {e}",
                    exc_info=log_level >= logging.ERROR,
                )
                if reraise:
                    raise
                return default
        return wrapper
    return decorator


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator to retry failed operations with exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import time

            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator
```

---

## Logging Framework

### Structured Logging Setup

Create `src/common/logging_config.py`:

```python
"""
Logging configuration for NeuronOS.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
import json


class JSONFormatter(logging.Formatter):
    """JSON log formatter for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter."""

    COLORS = {
        logging.DEBUG: "\033[36m",    # Cyan
        logging.INFO: "\033[32m",     # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    json_logs: bool = False,
):
    """
    Configure logging for NeuronOS.

    Args:
        level: Logging level
        log_file: Path to log file (optional)
        json_logs: Use JSON format for file logs
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)

    if sys.stderr.isatty():
        console_format = ColoredFormatter(
            "%(levelname)s %(name)s: %(message)s"
        )
    else:
        console_format = logging.Formatter(
            "%(levelname)s %(name)s: %(message)s"
        )

    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)  # Capture all to file

        if json_logs:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s"
            ))

        root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("libvirt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


class LogContext:
    """Context manager for adding context to log messages."""

    def __init__(self, **kwargs):
        self.context = kwargs
        self._old_factory = None

    def __enter__(self):
        self._old_factory = logging.getLogRecordFactory()

        context = self.context

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            record.extra_data = context
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args):
        logging.setLogRecordFactory(self._old_factory)
```

---

## Resource Management

### Context Manager for Connections

```python
# src/common/resources.py

from contextlib import contextmanager
from typing import TypeVar, Generic, Callable, Optional
import threading

T = TypeVar('T')


class ManagedResource(Generic[T]):
    """
    Thread-safe managed resource with automatic cleanup.
    """

    def __init__(
        self,
        acquire: Callable[[], T],
        release: Callable[[T], None],
        validate: Optional[Callable[[T], bool]] = None,
    ):
        self._acquire = acquire
        self._release = release
        self._validate = validate
        self._resource: Optional[T] = None
        self._lock = threading.RLock()

    def get(self) -> T:
        """Get the resource, acquiring if needed."""
        with self._lock:
            if self._resource is None or (
                self._validate and not self._validate(self._resource)
            ):
                if self._resource is not None:
                    try:
                        self._release(self._resource)
                    except Exception:
                        pass
                self._resource = self._acquire()
            return self._resource

    def release(self):
        """Release the resource."""
        with self._lock:
            if self._resource is not None:
                try:
                    self._release(self._resource)
                finally:
                    self._resource = None

    @contextmanager
    def use(self):
        """Context manager for using the resource."""
        resource = self.get()
        try:
            yield resource
        finally:
            pass  # Don't release - keep for reuse

    def __enter__(self):
        return self.get()

    def __exit__(self, *args):
        pass  # Keep resource for reuse


class ResourcePool(Generic[T]):
    """
    Pool of reusable resources.
    """

    def __init__(
        self,
        create: Callable[[], T],
        destroy: Callable[[T], None],
        validate: Callable[[T], bool],
        max_size: int = 10,
    ):
        self._create = create
        self._destroy = destroy
        self._validate = validate
        self._max_size = max_size
        self._pool: list[T] = []
        self._lock = threading.Lock()

    @contextmanager
    def acquire(self):
        """Acquire a resource from the pool."""
        resource = self._get()
        try:
            yield resource
        finally:
            self._return(resource)

    def _get(self) -> T:
        with self._lock:
            while self._pool:
                resource = self._pool.pop()
                if self._validate(resource):
                    return resource
                try:
                    self._destroy(resource)
                except Exception:
                    pass

            return self._create()

    def _return(self, resource: T):
        with self._lock:
            if len(self._pool) < self._max_size and self._validate(resource):
                self._pool.append(resource)
            else:
                try:
                    self._destroy(resource)
                except Exception:
                    pass

    def clear(self):
        """Clear all pooled resources."""
        with self._lock:
            for resource in self._pool:
                try:
                    self._destroy(resource)
                except Exception:
                    pass
            self._pool.clear()
```

### File Handle Management

```python
def ensure_closed(func):
    """Decorator to ensure file handles are closed."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        # If result is a file-like object, warn
        if hasattr(result, 'close') and hasattr(result, 'read'):
            import warnings
            warnings.warn(
                f"{func.__name__} returned unclosed file handle",
                ResourceWarning,
            )

        return result
    return wrapper
```

---

## Thread Safety

### Thread-Safe Singleton

```python
# src/common/singleton.py

import threading
from typing import TypeVar, Type, Dict, Any

T = TypeVar('T')


class ThreadSafeSingleton(type):
    """
    Thread-safe singleton metaclass.
    """

    _instances: Dict[Type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls: Type[T], *args, **kwargs) -> T:
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class LazySingleton:
    """
    Lazy singleton with thread-safe initialization.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._create_instance()
        return cls._instance

    @classmethod
    def _create_instance(cls):
        raise NotImplementedError
```

### Thread-Safe State Machine

```python
# src/common/state_machine.py

import threading
from enum import Enum
from typing import Dict, Set, Callable, Optional, TypeVar

S = TypeVar('S', bound=Enum)


class StateMachine:
    """
    Thread-safe state machine with transition validation.
    """

    def __init__(
        self,
        initial_state: S,
        transitions: Dict[S, Set[S]],
    ):
        self._state = initial_state
        self._transitions = transitions
        self._lock = threading.RLock()
        self._callbacks: Dict[S, list[Callable]] = {}

    @property
    def state(self) -> S:
        with self._lock:
            return self._state

    def can_transition(self, to_state: S) -> bool:
        """Check if transition is valid."""
        with self._lock:
            allowed = self._transitions.get(self._state, set())
            return to_state in allowed

    def transition(self, to_state: S) -> bool:
        """
        Attempt to transition to new state.

        Returns True if transition successful.
        """
        with self._lock:
            if not self.can_transition(to_state):
                return False

            old_state = self._state
            self._state = to_state

        # Call callbacks outside lock
        for callback in self._callbacks.get(to_state, []):
            try:
                callback(old_state, to_state)
            except Exception:
                pass

        return True

    def on_enter(self, state: S, callback: Callable[[S, S], None]):
        """Register callback for entering a state."""
        if state not in self._callbacks:
            self._callbacks[state] = []
        self._callbacks[state].append(callback)
```

---

## Graceful Degradation

### Feature Fallbacks

```python
# src/common/features.py

from dataclasses import dataclass
from typing import Optional, Callable, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """Feature with fallback behavior."""
    name: str
    check: Callable[[], bool]
    primary: Callable[..., Any]
    fallback: Optional[Callable[..., Any]] = None
    error_message: str = ""


class FeatureManager:
    """Manages features with graceful degradation."""

    def __init__(self):
        self._features: dict[str, Feature] = {}
        self._availability_cache: dict[str, bool] = {}

    def register(self, feature: Feature):
        """Register a feature."""
        self._features[feature.name] = feature

    def is_available(self, name: str) -> bool:
        """Check if feature is available."""
        if name in self._availability_cache:
            return self._availability_cache[name]

        feature = self._features.get(name)
        if not feature:
            return False

        try:
            available = feature.check()
        except Exception:
            available = False

        self._availability_cache[name] = available
        return available

    def execute(self, name: str, *args, **kwargs) -> Any:
        """Execute feature with fallback."""
        feature = self._features.get(name)
        if not feature:
            raise ValueError(f"Unknown feature: {name}")

        if self.is_available(name):
            try:
                return feature.primary(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Feature {name} failed: {e}")
                if feature.fallback:
                    return feature.fallback(*args, **kwargs)
                raise
        elif feature.fallback:
            logger.info(f"Using fallback for {name}: {feature.error_message}")
            return feature.fallback(*args, **kwargs)
        else:
            raise RuntimeError(feature.error_message or f"Feature unavailable: {name}")


# Example usage
features = FeatureManager()

features.register(Feature(
    name="looking_glass",
    check=lambda: Path("/usr/bin/looking-glass-client").exists(),
    primary=lambda vm: start_looking_glass(vm),
    fallback=lambda vm: start_virt_viewer(vm),
    error_message="Looking Glass not installed, using virt-viewer",
))
```

---

## Verification Checklist

- [ ] No bare `except:` clauses remain
- [ ] All exceptions inherit from NeuronError
- [ ] Logging configured with rotation
- [ ] All file handles use context managers
- [ ] Singletons are thread-safe
- [ ] State machines validate transitions
- [ ] Features have fallback behavior

---

## Next Phase

Proceed to [Phase 5: Testing & QA](./PHASE_5_TESTING.md).
