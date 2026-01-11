"""
VM Lifecycle Manager

Handles VM state transitions: start, stop, pause, resume, reboot.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

try:
    import libvirt
    LIBVIRT_AVAILABLE = True
except ImportError:
    LIBVIRT_AVAILABLE = False
    libvirt = None

from .connection import get_connection, LibvirtConnection
from .vm_config import VMState

logger = logging.getLogger(__name__)


class LifecycleError(Exception):
    """Raised when a lifecycle operation fails."""
    pass


class ShutdownMethod(Enum):
    """Methods for shutting down a VM."""
    GRACEFUL = "graceful"   # ACPI shutdown signal
    FORCE = "force"         # Immediate power off
    REBOOT = "reboot"       # Graceful reboot


class VMLifecycleManager:
    """
    Manages VM lifecycle operations.

    Provides safe start/stop with proper state checking.
    """

    def __init__(self, connection: Optional[LibvirtConnection] = None):
        self._conn = connection or get_connection()

    def get_domain(self, name: str):
        """Get domain by name."""
        with self._conn.get_connection() as conn:
            try:
                return conn.lookupByName(name)
            except libvirt.libvirtError:
                return None

    def get_state(self, name: str) -> VMState:
        """Get current VM state."""
        domain = self.get_domain(name)
        if not domain:
            return VMState.NOSTATE

        try:
            state, _ = domain.state()
            state_map = {
                libvirt.VIR_DOMAIN_NOSTATE: VMState.NOSTATE,
                libvirt.VIR_DOMAIN_RUNNING: VMState.RUNNING,
                libvirt.VIR_DOMAIN_BLOCKED: VMState.BLOCKED,
                libvirt.VIR_DOMAIN_PAUSED: VMState.PAUSED,
                libvirt.VIR_DOMAIN_SHUTDOWN: VMState.SHUTDOWN,
                libvirt.VIR_DOMAIN_SHUTOFF: VMState.SHUTOFF,
                libvirt.VIR_DOMAIN_CRASHED: VMState.CRASHED,
            }
            return state_map.get(state, VMState.NOSTATE)
        except libvirt.libvirtError:
            return VMState.NOSTATE

    def start(
        self,
        name: str,
        paused: bool = False,
        wait_timeout: int = 30,
    ) -> bool:
        """
        Start a VM.

        Args:
            name: VM name
            paused: Start in paused state
            wait_timeout: Seconds to wait for VM to start

        Returns:
            True if started successfully

        Raises:
            LifecycleError: If start fails
        """
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        current_state = self.get_state(name)
        if current_state == VMState.RUNNING:
            logger.info(f"VM {name} is already running")
            return True

        try:
            flags = 0
            if paused:
                flags |= libvirt.VIR_DOMAIN_START_PAUSED

            domain.createWithFlags(flags)
            logger.info(f"Started VM: {name}")

            # Wait for running state
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                if self.get_state(name) == VMState.RUNNING:
                    return True
                time.sleep(0.5)

            logger.warning(f"VM {name} started but not confirmed running")
            return True

        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to start {name}: {e}") from e

    def stop(
        self,
        name: str,
        method: ShutdownMethod = ShutdownMethod.GRACEFUL,
        timeout: int = 60,
    ) -> bool:
        """
        Stop a VM.

        Args:
            name: VM name
            method: Shutdown method
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped successfully
        """
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        current_state = self.get_state(name)
        if current_state == VMState.SHUTOFF:
            logger.info(f"VM {name} is already stopped")
            return True

        try:
            if method == ShutdownMethod.FORCE:
                domain.destroy()
                logger.info(f"Force stopped VM: {name}")
                return True

            elif method == ShutdownMethod.REBOOT:
                domain.reboot()
                logger.info(f"Rebooting VM: {name}")
                return True

            else:  # GRACEFUL
                domain.shutdown()
                logger.info(f"Sent shutdown signal to: {name}")

                # Wait for shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.get_state(name) == VMState.SHUTOFF:
                        return True
                    time.sleep(1)

                # Graceful shutdown timed out - force stop
                logger.warning(f"Graceful shutdown timed out for {name}, forcing...")
                domain.destroy()
                return True

        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to stop {name}: {e}") from e

    def pause(self, name: str) -> bool:
        """Pause a running VM."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.suspend()
            logger.info(f"Paused VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to pause {name}: {e}") from e

    def resume(self, name: str) -> bool:
        """Resume a paused VM."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.resume()
            logger.info(f"Resumed VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to resume {name}: {e}") from e

    def reset(self, name: str) -> bool:
        """Hard reset a VM (equivalent to reset button)."""
        domain = self.get_domain(name)
        if not domain:
            raise LifecycleError(f"VM not found: {name}")

        try:
            domain.reset()
            logger.info(f"Reset VM: {name}")
            return True
        except libvirt.libvirtError as e:
            raise LifecycleError(f"Failed to reset {name}: {e}") from e
