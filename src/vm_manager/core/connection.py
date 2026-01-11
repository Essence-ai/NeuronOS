"""
LibVirt Connection Manager

Handles connection lifecycle with automatic reconnection.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Optional, Callable, List

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False
    libvirt = None

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
        if not LIBVIRT_AVAILABLE:
            raise RuntimeError(
                "libvirt-python is not installed. "
                "Install with: pip install libvirt-python"
            )
        self._uri = uri
        self._conn: Optional[libvirt.virConnect] = None
        self._lock = threading.RLock()
        self._event_loop_running = False
        self._callbacks: List[Callable] = []

    @property
    def uri(self) -> str:
        """Get the connection URI."""
        return self._uri

    @property
    def is_connected(self) -> bool:
        """Check if connected to libvirt."""
        with self._lock:
            if self._conn is None:
                return False
            try:
                self._conn.getVersion()
                return True
            except Exception:
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
        callback: Callable,
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
