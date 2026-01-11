#!/usr/bin/env python3
"""
NeuronOS Guest Agent Host Client.

Communicates with NeuronGuest agent running inside Windows VMs
via virtio-serial. Enables seamless host-guest integration:
- Launch Windows applications from Linux
- Window management (focus, minimize, maximize)
- Get running windows list
- Health monitoring
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import ssl
import subprocess

logger = logging.getLogger(__name__)


class GuestAgentError(Exception):
    """Error communicating with guest agent."""
    pass


class CommandType(Enum):
    """Commands supported by guest agent."""
    PING = "ping"
    GET_INFO = "get_info"
    LAUNCH = "launch"
    CLOSE = "close"
    LIST_WINDOWS = "list_windows"
    FOCUS = "focus"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    CLIPBOARD_GET = "clipboard_get"
    CLIPBOARD_SET = "clipboard_set"
    SET_RESOLUTION = "set_resolution"  # Phase 3: Resolution sync for Looking Glass
    SCREENSHOT = "screenshot"           # Phase 3: Capture guest screen


@dataclass
class WindowInfo:
    """Information about a window in the guest."""
    handle: int
    title: str
    process_name: str
    is_visible: bool = True
    is_minimized: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WindowInfo":
        return cls(
            handle=data.get("handle", 0),
            title=data.get("title", ""),
            process_name=data.get("process_name", ""),
            is_visible=data.get("is_visible", True),
            is_minimized=data.get("is_minimized", False),
        )


@dataclass
class GuestInfo:
    """Information about the guest system."""
    os_version: str = ""
    hostname: str = ""
    username: str = ""
    agent_version: str = ""
    uptime_seconds: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuestInfo":
        return cls(
            os_version=data.get("os_version", ""),
            hostname=data.get("hostname", ""),
            username=data.get("username", ""),
            agent_version=data.get("agent_version", ""),
            uptime_seconds=data.get("uptime_seconds", 0),
        )


@dataclass
class GuestAgentResponse:
    """Response from guest agent."""
    success: bool
    command: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def from_json(cls, json_str: str) -> "GuestAgentResponse":
        data = json.loads(json_str)
        return cls(
            success=data.get("success", False),
            command=data.get("command", ""),
            data=data.get("data", {}),
            error=data.get("error"),
        )


class VirtioSerialClient:
    """
    Client for communicating with guest via virtio-serial.

    The virtio-serial channel appears as a Unix socket on the host.
    Messages use a simple framing protocol:
    - STX (0x02) + JSON message + ETX (0x03)
    """

    STX = b'\x02'
    ETX = b'\x03'

    def __init__(self, socket_path: str):
        """
        Initialize virtio-serial client.

        Args:
            socket_path: Path to the virtio-serial Unix socket
        """
        self.socket_path = socket_path
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
        self._recv_buffer = b""
        self._cert_path = Path.home() / ".config" / "neuronos" / "certs" / "host.crt"
        self._key_path = Path.home() / ".config" / "neuronos" / "certs" / "host.key"

    def _ensure_certificates(self):
        """Ensure self-signed certificates exist for TLS."""
        if self._cert_path.exists() and self._key_path.exists():
            return

        self._cert_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Generating self-signed certificate for Guest Agent communication")
        
        # Generate self-signed certificate using openssl
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:4096",
            "-keyout", str(self._key_path),
            "-out", str(self._cert_path),
            "-sha256", "-days", "3650", "-nodes",
            "-subj", "/CN=NeuronOS-Host"
        ], check=True, capture_output=True)

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Connect to guest agent.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        if self._connected:
            return True

        try:
            raw_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            raw_socket.settimeout(timeout)
            raw_socket.connect(self.socket_path)

            # Wrap with TLS
            self._ensure_certificates()
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(certfile=str(self._cert_path), keyfile=str(self._key_path))
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE  # In production, use client certs

            self._socket = context.wrap_socket(raw_socket, server_side=True)
            self._connected = True
            logger.info(f"Connected to guest agent at {self.socket_path} (Encrypted)")
            return True

        except socket.error as e:
            logger.error(f"Failed to connect to guest agent: {e}")
            self._socket = None
            return False

    def disconnect(self) -> None:
        """Disconnect from guest agent."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._connected = False

    def send_command(
        self,
        command: CommandType,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0
    ) -> GuestAgentResponse:
        """
        Send command to guest agent and wait for response.

        Args:
            command: Command to send
            params: Optional command parameters
            timeout: Response timeout in seconds

        Returns:
            Response from guest agent

        Raises:
            GuestAgentError: If communication fails
        """
        if not self._connected:
            if not self.connect():
                raise GuestAgentError("Not connected to guest agent")

        message = {
            "command": command.value,
            "params": params or {},
            "timestamp": time.time(),
        }

        with self._lock:
            try:
                # Send message
                json_bytes = json.dumps(message).encode('utf-8')
                frame = self.STX + json_bytes + self.ETX
                self._socket.sendall(frame)

                # Receive response
                self._socket.settimeout(timeout)
                response_json = self._recv_message()

                return GuestAgentResponse.from_json(response_json)

            except socket.timeout:
                raise GuestAgentError(f"Timeout waiting for response to {command.value}")
            except socket.error as e:
                self._connected = False
                raise GuestAgentError(f"Socket error: {e}")
            except json.JSONDecodeError as e:
                raise GuestAgentError(f"Invalid response JSON: {e}")

    def _recv_message(self) -> str:
        """Receive a complete framed message."""
        while True:
            # Check buffer for complete message
            stx_pos = self._recv_buffer.find(self.STX)
            if stx_pos != -1:
                etx_pos = self._recv_buffer.find(self.ETX, stx_pos)
                if etx_pos != -1:
                    # Extract message
                    message = self._recv_buffer[stx_pos + 1:etx_pos]
                    self._recv_buffer = self._recv_buffer[etx_pos + 1:]
                    return message.decode('utf-8')

            # Need more data
            chunk = self._socket.recv(4096)
            if not chunk:
                raise GuestAgentError("Connection closed by guest")
            self._recv_buffer += chunk


class GuestAgentClient:
    """
    High-level client for NeuronGuest agent.

    Provides a simple API for host-guest integration features.
    """

    def __init__(self, vm_name: str):
        """
        Initialize guest agent client.

        Args:
            vm_name: Name of the VM to connect to
        """
        self.vm_name = vm_name
        self._client: Optional[VirtioSerialClient] = None
        self._socket_path = self._find_socket_path(vm_name)

    def _find_socket_path(self, vm_name: str) -> str:
        """Find the virtio-serial socket for a VM."""
        # Standard locations for virtio-serial sockets
        possible_paths = [
            f"/var/lib/libvirt/qemu/channel/target/domain-{vm_name}/org.neuronos.guest.0",
            f"/tmp/neuron-guest-{vm_name}.sock",
            f"/run/user/{os.getuid()}/neuron-guest-{vm_name}.sock",
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        # Return default path (may not exist yet)
        return f"/var/lib/libvirt/qemu/channel/target/domain-{vm_name}/org.neuronos.guest.0"

    def connect(self, timeout: float = 5.0) -> bool:
        """Connect to guest agent."""
        self._client = VirtioSerialClient(self._socket_path)
        return self._client.connect(timeout)

    def disconnect(self) -> None:
        """Disconnect from guest agent."""
        if self._client:
            self._client.disconnect()
            self._client = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to guest agent."""
        return self._client is not None and self._client._connected

    def ping(self) -> bool:
        """
        Check if guest agent is responsive.

        Returns:
            True if agent responded to ping
        """
        try:
            response = self._client.send_command(CommandType.PING, timeout=3.0)
            return response.success
        except GuestAgentError:
            return False

    def get_info(self) -> Optional[GuestInfo]:
        """
        Get information about the guest system.

        Returns:
            GuestInfo or None if failed
        """
        try:
            response = self._client.send_command(CommandType.GET_INFO)
            if response.success:
                return GuestInfo.from_dict(response.data)
            return None
        except GuestAgentError as e:
            logger.error(f"Failed to get guest info: {e}")
            return None

    def launch(self, executable: str, arguments: str = "", working_dir: str = "") -> bool:
        """
        Launch an application in the guest.

        Args:
            executable: Path to executable or command
            arguments: Command line arguments
            working_dir: Working directory

        Returns:
            True if launch was initiated
        """
        try:
            response = self._client.send_command(
                CommandType.LAUNCH,
                {
                    "executable": executable,
                    "arguments": arguments,
                    "working_dir": working_dir,
                }
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to launch application: {e}")
            return False

    def close(self, window_handle: int) -> bool:
        """
        Close a window in the guest.

        Args:
            window_handle: Handle of window to close

        Returns:
            True if close was successful
        """
        try:
            response = self._client.send_command(
                CommandType.CLOSE,
                {"handle": window_handle}
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to close window: {e}")
            return False

    def list_windows(self) -> List[WindowInfo]:
        """
        Get list of windows in the guest.

        Returns:
            List of WindowInfo objects
        """
        try:
            response = self._client.send_command(CommandType.LIST_WINDOWS)
            if response.success:
                windows = response.data.get("windows", [])
                return [WindowInfo.from_dict(w) for w in windows]
            return []
        except GuestAgentError as e:
            logger.error(f"Failed to list windows: {e}")
            return []

    def focus(self, window_handle: int) -> bool:
        """
        Focus a window in the guest.

        Args:
            window_handle: Handle of window to focus

        Returns:
            True if focus was successful
        """
        try:
            response = self._client.send_command(
                CommandType.FOCUS,
                {"handle": window_handle}
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to focus window: {e}")
            return False

    def minimize(self, window_handle: int) -> bool:
        """Minimize a window in the guest."""
        try:
            response = self._client.send_command(
                CommandType.MINIMIZE,
                {"handle": window_handle}
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to minimize window: {e}")
            return False

    def maximize(self, window_handle: int) -> bool:
        """Maximize a window in the guest."""
        try:
            response = self._client.send_command(
                CommandType.MAXIMIZE,
                {"handle": window_handle}
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to maximize window: {e}")
            return False

    # Phase 3: Resolution synchronization for Looking Glass
    def set_resolution(self, width: int, height: int) -> bool:
        """
        Set guest display resolution.

        Used to synchronize resolution when Looking Glass window resizes.

        Args:
            width: Display width in pixels
            height: Display height in pixels

        Returns:
            True if resolution was set successfully
        """
        try:
            response = self._client.send_command(
                CommandType.SET_RESOLUTION,
                {"width": width, "height": height}
            )
            if response.success:
                logger.info(f"Set guest resolution to {width}x{height}")
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to set resolution: {e}")
            return False

    # Phase 3: Clipboard synchronization
    def get_clipboard(self) -> Optional[str]:
        """
        Get clipboard content from guest.

        Returns:
            Clipboard text content, or None if failed
        """
        try:
            response = self._client.send_command(CommandType.CLIPBOARD_GET)
            if response.success:
                return response.data.get("text")
            return None
        except GuestAgentError as e:
            logger.error(f"Failed to get clipboard: {e}")
            return None

    def set_clipboard(self, text: str) -> bool:
        """
        Set clipboard content in guest.

        Args:
            text: Text to copy to guest clipboard

        Returns:
            True if clipboard was set successfully
        """
        try:
            response = self._client.send_command(
                CommandType.CLIPBOARD_SET,
                {"text": text}
            )
            return response.success
        except GuestAgentError as e:
            logger.error(f"Failed to set clipboard: {e}")
            return False

    def screenshot(self) -> Optional[bytes]:
        """
        Capture a screenshot of the guest display.

        Returns:
            PNG image bytes, or None if failed
        """
        try:
            response = self._client.send_command(CommandType.SCREENSHOT)
            if response.success:
                import base64
                data = response.data.get("image_base64")
                if data:
                    return base64.b64decode(data)
            return None
        except GuestAgentError as e:
            logger.error(f"Failed to capture screenshot: {e}")
            return None


class GuestAgentMonitor:
    """
    Monitor for guest agent connectivity.

    Periodically checks if guest is responsive and calls
    callbacks on state changes.
    """

    def __init__(
        self,
        vm_name: str,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
        poll_interval: float = 5.0
    ):
        """
        Initialize guest agent monitor.

        Args:
            vm_name: Name of VM to monitor
            on_connected: Callback when guest connects
            on_disconnected: Callback when guest disconnects
            poll_interval: Seconds between connectivity checks
        """
        self.vm_name = vm_name
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.poll_interval = poll_interval

        self._client: Optional[GuestAgentClient] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._was_connected = False

    def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._client:
            self._client.disconnect()
            self._client = None

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                if self._client is None:
                    self._client = GuestAgentClient(self.vm_name)

                if not self._client.is_connected:
                    connected = self._client.connect(timeout=2.0)
                else:
                    connected = self._client.ping()

                if connected and not self._was_connected:
                    self._was_connected = True
                    if self.on_connected:
                        self.on_connected()

                elif not connected and self._was_connected:
                    self._was_connected = False
                    if self.on_disconnected:
                        self.on_disconnected()

            except Exception as e:
                logger.debug(f"Monitor check failed: {e}")
                if self._was_connected:
                    self._was_connected = False
                    if self.on_disconnected:
                        self.on_disconnected()

            time.sleep(self.poll_interval)


# Convenience functions
def connect_to_vm(vm_name: str, timeout: float = 5.0) -> Optional[GuestAgentClient]:
    """
    Connect to a VM's guest agent.

    Args:
        vm_name: Name of the VM
        timeout: Connection timeout

    Returns:
        Connected GuestAgentClient or None
    """
    client = GuestAgentClient(vm_name)
    if client.connect(timeout):
        return client
    return None


def launch_in_vm(vm_name: str, executable: str, arguments: str = "") -> bool:
    """
    Launch an application in a VM.

    Args:
        vm_name: Name of the VM
        executable: Executable to launch
        arguments: Command line arguments

    Returns:
        True if launch was initiated
    """
    client = connect_to_vm(vm_name)
    if client:
        result = client.launch(executable, arguments)
        client.disconnect()
        return result
    return False


if __name__ == "__main__":
    # Test usage
    logging.basicConfig(level=logging.DEBUG)

    import sys
    if len(sys.argv) < 2:
        print("Usage: guest_client.py <vm_name> [command] [args...]")
        sys.exit(1)

    vm_name = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "ping"

    client = GuestAgentClient(vm_name)

    if not client.connect():
        print(f"Failed to connect to guest agent for VM: {vm_name}")
        sys.exit(1)

    if command == "ping":
        if client.ping():
            print("Guest agent is responsive")
        else:
            print("Guest agent not responding")

    elif command == "info":
        info = client.get_info()
        if info:
            print(f"OS: {info.os_version}")
            print(f"Hostname: {info.hostname}")
            print(f"User: {info.username}")
            print(f"Agent: {info.agent_version}")
        else:
            print("Failed to get guest info")

    elif command == "list":
        windows = client.list_windows()
        for w in windows:
            print(f"[{w.handle}] {w.process_name}: {w.title}")

    elif command == "launch" and len(sys.argv) > 3:
        exe = sys.argv[3]
        args = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        if client.launch(exe, args):
            print(f"Launched: {exe}")
        else:
            print(f"Failed to launch: {exe}")

    else:
        print(f"Unknown command: {command}")

    client.disconnect()
