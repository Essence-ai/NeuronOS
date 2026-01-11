"""
Resource Management Utilities

Provides thread-safe resource acquisition, pooling, and cleanup.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import TypeVar, Generic, Callable, Optional, List
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ManagedResource(Generic[T]):
    """
    Thread-safe managed resource with automatic cleanup and reconnection.
    
    Example:
        connection = ManagedResource(
            acquire=lambda: libvirt.open("qemu:///system"),
            release=lambda c: c.close(),
            validate=lambda c: c.isAlive(),
        )
        
        with connection.use() as conn:
            conn.listDomainsID()
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
            # Check if we need to (re)acquire
            if self._resource is None or (
                self._validate and not self._validate(self._resource)
            ):
                # Release old resource if exists
                if self._resource is not None:
                    try:
                        self._release(self._resource)
                    except Exception as e:
                        logger.debug(f"Error releasing stale resource: {e}")
                
                # Acquire new resource
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
    
    Example:
        pool = ResourcePool(
            create=lambda: create_connection(),
            destroy=lambda c: c.close(),
            validate=lambda c: c.is_open(),
            max_size=10,
        )
        
        with pool.acquire() as conn:
            conn.execute("SELECT 1")
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
        self._pool: List[T] = []
        self._lock = threading.Lock()
        self._created_count = 0

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
            # Try to get from pool
            while self._pool:
                resource = self._pool.pop()
                if self._validate(resource):
                    return resource
                # Invalid resource, destroy it
                try:
                    self._destroy(resource)
                    self._created_count -= 1
                except Exception as e:
                    logger.debug(f"Error destroying invalid resource: {e}")

            # Create new resource
            resource = self._create()
            self._created_count += 1
            return resource

    def _return(self, resource: T):
        with self._lock:
            if len(self._pool) < self._max_size and self._validate(resource):
                self._pool.append(resource)
            else:
                try:
                    self._destroy(resource)
                    self._created_count -= 1
                except Exception as e:
                    logger.debug(f"Error destroying resource: {e}")

    def clear(self):
        """Clear all pooled resources."""
        with self._lock:
            for resource in self._pool:
                try:
                    self._destroy(resource)
                except Exception as e:
                    logger.debug(f"Error destroying pooled resource: {e}")
            self._pool.clear()
            self._created_count = 0

    @property
    def size(self) -> int:
        """Current pool size."""
        with self._lock:
            return len(self._pool)

    @property
    def total_created(self) -> int:
        """Total resources created."""
        with self._lock:
            return self._created_count


class CleanupRegistry:
    """
    Registry for cleanup callbacks to ensure resources are released.
    
    Example:
        registry = CleanupRegistry()
        registry.register(lambda: connection.close())
        registry.register(lambda: temp_file.unlink())
        
        # On shutdown
        registry.cleanup_all()
    """

    def __init__(self):
        self._callbacks: List[Callable[[], None]] = []
        self._lock = threading.Lock()

    def register(self, callback: Callable[[], None]):
        """Register a cleanup callback."""
        with self._lock:
            self._callbacks.append(callback)

    def unregister(self, callback: Callable[[], None]):
        """Unregister a cleanup callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def cleanup_all(self):
        """Execute all cleanup callbacks (in reverse order)."""
        with self._lock:
            callbacks = self._callbacks.copy()
            self._callbacks.clear()

        for callback in reversed(callbacks):
            try:
                callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")


# Global cleanup registry
_global_cleanup = CleanupRegistry()


def register_cleanup(callback: Callable[[], None]):
    """Register a global cleanup callback."""
    _global_cleanup.register(callback)


def cleanup_all():
    """Execute all global cleanup callbacks."""
    _global_cleanup.cleanup_all()
