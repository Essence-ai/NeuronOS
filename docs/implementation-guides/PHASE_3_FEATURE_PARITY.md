# Phase 3: Feature Parity & Polish

**Priority:** MEDIUM - Required for MVP
**Estimated Time:** 2 weeks
**Prerequisites:** Phase 2 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Guest Agent Communication](#guest-agent-communication)
3. [Migration System Improvements](#migration-system-improvements)
4. [Hardware Detection Enhancements](#hardware-detection-enhancements)
5. [Update System Completion](#update-system-completion)
6. [UI/UX Polish](#uiux-polish)

---

## Overview

This phase focuses on completing partially-implemented features to reach feature parity with the project's advertised capabilities.

### Incomplete Features

| Feature | Current State | Target State |
|---------|--------------|--------------|
| Guest Agent | Protocol defined, no features | Full clipboard, resolution sync |
| Migration | Basic copy | Browser profiles, app settings |
| Hardware Detect | Basic scan | ACS override, Reset quirk detection |
| Update System | Snapshot exists | Full rollback with verification |
| UI Polish | Functional | Consistent, accessible |

---

## Guest Agent Communication

See [Phase 3A: Guest Agent Protocol](./PHASE_3A_GUEST_AGENT.md) for detailed implementation.

### Quick Overview

The guest agent needs:
1. **Encrypted communication** over virtio-serial
2. **Clipboard synchronization** between host and guest
3. **Resolution synchronization** when Looking Glass window resizes
4. **Application launching** from host-side NeuronStore

### Host-Side Client

Create `src/vm_manager/core/guest_client.py`:

```python
"""
Guest Agent Client

Communicates with the NeuronGuest Windows service.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Commands that can be sent to guest."""
    PING = "ping"
    GET_INFO = "get_info"
    SET_RESOLUTION = "set_resolution"
    LAUNCH_APP = "launch_app"
    CLIPBOARD_GET = "clipboard_get"
    CLIPBOARD_SET = "clipboard_set"
    SCREENSHOT = "screenshot"
    SHUTDOWN = "shutdown"


@dataclass
class GuestCommand:
    """Command to send to guest."""
    type: CommandType
    request_id: str
    data: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "request_id": self.request_id,
            "data": self.data,
        })


@dataclass
class GuestResponse:
    """Response from guest."""
    request_id: str
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

    @classmethod
    def from_json(cls, json_str: str) -> "GuestResponse":
        obj = json.loads(json_str)
        return cls(
            request_id=obj.get("request_id", ""),
            success=obj.get("success", False),
            data=obj.get("data", {}),
            error=obj.get("error"),
        )


class GuestAgentClient:
    """
    Client for communicating with NeuronGuest agent in VM.

    Uses virtio-serial for communication.
    """

    # Virtio-serial device path pattern
    VIRTIO_PATH = "/dev/virtio-ports/{vm_name}-agent"
    SOCKET_PATH = "/var/lib/libvirt/qemu/channel/target/{vm_name}.agent.0"

    # Protocol markers
    MSG_START = b'\x02'  # STX
    MSG_END = b'\x03'    # ETX

    def __init__(self, vm_name: str):
        self.vm_name = vm_name
        self._socket: Optional[Any] = None
        self._lock = threading.Lock()
        self._response_callbacks: Dict[str, Callable] = {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Connect to guest agent via virtio-serial."""
        # Try different socket paths
        paths = [
            self.SOCKET_PATH.format(vm_name=self.vm_name),
            f"/tmp/neuron-agent-{self.vm_name}.sock",
        ]

        for path in paths:
            if Path(path).exists():
                try:
                    import socket
                    self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self._socket.connect(path)
                    self._socket.settimeout(5.0)
                    self._connected = True
                    logger.info(f"Connected to guest agent: {path}")

                    # Start receiver thread
                    self._start_receiver()
                    return True

                except Exception as e:
                    logger.warning(f"Failed to connect to {path}: {e}")

        return False

    def disconnect(self):
        """Disconnect from guest agent."""
        self._connected = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def send_command(
        self,
        cmd_type: CommandType,
        data: Dict[str, Any] = None,
        timeout: float = 5.0,
    ) -> Optional[GuestResponse]:
        """
        Send command to guest and wait for response.

        Args:
            cmd_type: Type of command
            data: Command data
            timeout: Response timeout in seconds

        Returns:
            GuestResponse or None if timeout/error
        """
        if not self._connected:
            if not self.connect():
                return None

        request_id = str(uuid.uuid4())[:8]
        command = GuestCommand(
            type=cmd_type,
            request_id=request_id,
            data=data or {},
        )

        # Set up response waiter
        response_event = threading.Event()
        response_holder = [None]

        def on_response(resp):
            response_holder[0] = resp
            response_event.set()

        self._response_callbacks[request_id] = on_response

        try:
            # Send command
            message = self.MSG_START + command.to_json().encode() + self.MSG_END
            self._socket.sendall(message)

            # Wait for response
            if response_event.wait(timeout):
                return response_holder[0]
            else:
                logger.warning(f"Timeout waiting for response to {cmd_type.value}")
                return None

        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return None
        finally:
            self._response_callbacks.pop(request_id, None)

    def ping(self) -> bool:
        """Check if guest agent is responsive."""
        response = self.send_command(CommandType.PING, timeout=2.0)
        return response is not None and response.success

    def get_info(self) -> Optional[Dict[str, Any]]:
        """Get guest system information."""
        response = self.send_command(CommandType.GET_INFO)
        if response and response.success:
            return response.data
        return None

    def set_resolution(self, width: int, height: int) -> bool:
        """Set guest display resolution."""
        response = self.send_command(
            CommandType.SET_RESOLUTION,
            {"width": width, "height": height},
        )
        return response is not None and response.success

    def launch_app(self, exe_path: str, args: list = None) -> bool:
        """Launch application in guest."""
        response = self.send_command(
            CommandType.LAUNCH_APP,
            {"path": exe_path, "args": args or []},
        )
        return response is not None and response.success

    def get_clipboard(self) -> Optional[str]:
        """Get clipboard content from guest."""
        response = self.send_command(CommandType.CLIPBOARD_GET)
        if response and response.success:
            return response.data.get("text")
        return None

    def set_clipboard(self, text: str) -> bool:
        """Set clipboard content in guest."""
        response = self.send_command(
            CommandType.CLIPBOARD_SET,
            {"text": text},
        )
        return response is not None and response.success

    def _start_receiver(self):
        """Start background thread to receive responses."""
        def receive_loop():
            buffer = b""

            while self._connected and self._socket:
                try:
                    data = self._socket.recv(4096)
                    if not data:
                        break

                    buffer += data

                    # Parse complete messages
                    while self.MSG_START in buffer and self.MSG_END in buffer:
                        start = buffer.index(self.MSG_START)
                        end = buffer.index(self.MSG_END, start)

                        message = buffer[start + 1:end].decode()
                        buffer = buffer[end + 1:]

                        self._handle_message(message)

                except Exception as e:
                    if self._connected:
                        logger.error(f"Receive error: {e}")
                    break

            self._connected = False

        thread = threading.Thread(target=receive_loop, daemon=True)
        thread.start()

    def _handle_message(self, message: str):
        """Handle received message from guest."""
        try:
            response = GuestResponse.from_json(message)

            callback = self._response_callbacks.get(response.request_id)
            if callback:
                callback(response)
            else:
                logger.debug(f"Received unsolicited message: {message[:100]}")

        except Exception as e:
            logger.warning(f"Failed to parse message: {e}")
```

---

## Migration System Improvements

### Add Browser Profile Migration

Update `src/migration/migrator.py`:

```python
class WindowsMigrator(Migrator):
    """Enhanced Windows migrator with browser support."""

    # Browser profile mappings
    BROWSER_MIGRATIONS = {
        FileCategory.BROWSER_CHROME: {
            "source": lambda base: base / "AppData/Local/Google/Chrome/User Data",
            "target": lambda home: home / ".config/google-chrome",
            "items": ["Default", "Profile *"],  # User profiles
            "exclude": ["Cache", "Code Cache", "GPUCache", "ShaderCache"],
        },
        FileCategory.BROWSER_FIREFOX: {
            "source": lambda base: base / "AppData/Roaming/Mozilla/Firefox/Profiles",
            "target": lambda home: home / ".mozilla/firefox",
            "items": ["*.default*"],  # Profile directories
            "exclude": ["cache2", "startupCache"],
        },
        FileCategory.BROWSER_EDGE: {
            "source": lambda base: base / "AppData/Local/Microsoft/Edge/User Data",
            "target": lambda home: home / ".config/microsoft-edge",
            "items": ["Default", "Profile *"],
            "exclude": ["Cache", "Code Cache", "GPUCache"],
        },
    }

    def _migrate_browser(self, category: FileCategory) -> bool:
        """Migrate browser profile with proper filtering."""
        if category not in self.BROWSER_MIGRATIONS:
            return False

        config = self.BROWSER_MIGRATIONS[category]
        source = config["source"](self.source.path)
        target = config["target"](self.target.path)

        if not source.exists():
            logger.info(f"Browser not found: {source}")
            return True  # Not an error

        target.mkdir(parents=True, exist_ok=True)

        for pattern in config["items"]:
            for profile_dir in source.glob(pattern):
                if not profile_dir.is_dir():
                    continue

                # Copy profile, excluding cache directories
                self._copy_browser_profile(
                    profile_dir,
                    target / profile_dir.name,
                    config.get("exclude", []),
                )

        return True

    def _copy_browser_profile(
        self,
        source: Path,
        target: Path,
        exclude: list,
    ):
        """Copy browser profile excluding caches."""
        target.mkdir(parents=True, exist_ok=True)

        for item in source.iterdir():
            # Skip excluded directories
            if item.is_dir() and item.name in exclude:
                continue

            # Skip very large files (likely cache)
            if item.is_file():
                try:
                    if item.stat().st_size > 100 * 1024 * 1024:  # 100MB
                        logger.info(f"Skipping large file: {item.name}")
                        continue
                except OSError:
                    continue

            target_item = target / item.name

            try:
                if item.is_file():
                    self._copy_file(item, target_item)
                elif item.is_dir():
                    self._copy_browser_profile(item, target_item, exclude)
            except Exception as e:
                self.progress.errors.append(f"Failed to copy {item}: {e}")
```

### Add Application Settings Migration

```python
class ApplicationSettingsMigrator:
    """Migrates application settings and configurations."""

    # Mapping of Windows app settings to Linux equivalents
    APP_MAPPINGS = {
        "vscode": {
            "windows": "AppData/Roaming/Code/User",
            "linux": ".config/Code/User",
            "files": ["settings.json", "keybindings.json", "snippets/*"],
        },
        "git": {
            "windows": ".gitconfig",
            "linux": ".gitconfig",
        },
        "ssh": {
            "windows": ".ssh",
            "linux": ".ssh",
            "permissions": {
                "id_*": 0o600,
                "id_*.pub": 0o644,
                "config": 0o600,
                "known_hosts": 0o644,
            },
        },
        "npm": {
            "windows": ".npmrc",
            "linux": ".npmrc",
        },
    }

    def migrate_app_settings(
        self,
        source_home: Path,
        target_home: Path,
        apps: list = None,
    ) -> Dict[str, bool]:
        """
        Migrate application settings.

        Args:
            source_home: Windows user home directory
            target_home: Linux home directory
            apps: List of apps to migrate (None = all)

        Returns:
            Dict of app_name -> success
        """
        results = {}
        apps_to_migrate = apps or list(self.APP_MAPPINGS.keys())

        for app_name in apps_to_migrate:
            if app_name not in self.APP_MAPPINGS:
                continue

            mapping = self.APP_MAPPINGS[app_name]
            source = source_home / mapping["windows"]
            target = target_home / mapping["linux"]

            if not source.exists():
                results[app_name] = True  # Not an error
                continue

            try:
                if source.is_file():
                    self._copy_with_permissions(source, target, mapping)
                else:
                    self._copy_dir_with_permissions(source, target, mapping)

                results[app_name] = True
                logger.info(f"Migrated {app_name} settings")

            except Exception as e:
                logger.error(f"Failed to migrate {app_name}: {e}")
                results[app_name] = False

        return results

    def _copy_with_permissions(self, source: Path, target: Path, mapping: dict):
        """Copy file with proper permissions."""
        import shutil

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

        # Apply permissions if specified
        permissions = mapping.get("permissions", {})
        for pattern, mode in permissions.items():
            import fnmatch
            if fnmatch.fnmatch(target.name, pattern):
                target.chmod(mode)
                break

    def _copy_dir_with_permissions(self, source: Path, target: Path, mapping: dict):
        """Copy directory with proper permissions."""
        target.mkdir(parents=True, exist_ok=True)
        permissions = mapping.get("permissions", {})

        for item in source.rglob("*"):
            relative = item.relative_to(source)
            target_item = target / relative

            if item.is_dir():
                target_item.mkdir(parents=True, exist_ok=True)
            else:
                target_item.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(item, target_item)

                # Apply permissions
                for pattern, mode in permissions.items():
                    import fnmatch
                    if fnmatch.fnmatch(item.name, pattern):
                        target_item.chmod(mode)
                        break
```

---

## Hardware Detection Enhancements

### ACS Override Detection

Add to `src/hardware_detect/iommu_parser.py`:

```python
class IOMMUParser:
    """Enhanced IOMMU parser with ACS detection."""

    def check_acs_override_needed(self, group_id: int) -> bool:
        """
        Check if ACS override is needed for a group.

        ACS (Access Control Services) override may be needed when:
        - Multiple devices share an IOMMU group
        - User wants to pass through only one device from the group
        """
        group = self.groups.get(group_id)
        if not group:
            return False

        # Count PCI devices in group (excluding bridges)
        pci_devices = [d for d in group.devices if not self._is_bridge(d)]

        return len(pci_devices) > 1

    def _is_bridge(self, device_path: Path) -> bool:
        """Check if device is a PCI bridge."""
        try:
            class_file = device_path / "class"
            if class_file.exists():
                class_code = class_file.read_text().strip()
                # PCI bridge class codes start with 0x06
                return class_code.startswith("0x06")
        except Exception:
            pass
        return False

    def get_acs_patch_kernel_param(self) -> str:
        """Get kernel parameter for ACS override."""
        return "pcie_acs_override=downstream,multifunction"

    def check_reset_bug(self, pci_address: str) -> Optional[str]:
        """
        Check for GPU reset bug that prevents passthrough.

        Some GPUs (especially AMD) have a reset bug where they can't
        be properly reset after VM shutdown, requiring a host reboot.

        Returns workaround suggestion if bug detected.
        """
        # Known affected GPUs
        RESET_BUG_DEVICES = {
            # AMD Navi 10/14 (RX 5000 series)
            ("1002", "731f"): "vendor-reset",  # RX 5700 XT
            ("1002", "7340"): "vendor-reset",  # RX 5500 XT
            # AMD Navi 21/22/23 (RX 6000 series)
            ("1002", "73bf"): "vendor-reset",  # RX 6800 XT
            ("1002", "73df"): "vendor-reset",  # RX 6700 XT
        }

        try:
            device_path = Path(f"/sys/bus/pci/devices/{pci_address}")
            vendor = (device_path / "vendor").read_text().strip().replace("0x", "")
            device = (device_path / "device").read_text().strip().replace("0x", "")

            key = (vendor.lower(), device.lower())
            if key in RESET_BUG_DEVICES:
                workaround = RESET_BUG_DEVICES[key]
                return f"This GPU has a known reset bug. Install '{workaround}' kernel module."

        except Exception:
            pass

        return None
```

---

## Update System Completion

### Implement Full Verification

Update `src/updater/updater.py`:

```python
class UpdateVerifier:
    """Verifies system health after updates."""

    CRITICAL_SERVICES = [
        "sddm",           # Display manager
        "NetworkManager", # Networking
        "libvirtd",       # VM management
    ]

    CRITICAL_BINARIES = [
        "/usr/bin/bash",
        "/usr/bin/python3",
        "/usr/bin/systemctl",
    ]

    def verify_system_health(self) -> Tuple[bool, List[str]]:
        """
        Verify system is healthy after update.

        Returns:
            Tuple of (is_healthy, list of issues)
        """
        issues = []

        # Check critical binaries exist
        for binary in self.CRITICAL_BINARIES:
            if not Path(binary).exists():
                issues.append(f"Missing critical binary: {binary}")

        # Check systemd
        if not self._check_systemd():
            issues.append("systemd not functioning properly")

        # Check critical services
        for service in self.CRITICAL_SERVICES:
            if not self._check_service(service):
                issues.append(f"Critical service failed: {service}")

        # Check kernel modules
        if not self._check_vfio_modules():
            issues.append("VFIO kernel modules not loaded")

        # Check libvirt
        if not self._check_libvirt():
            issues.append("libvirt daemon not responding")

        return len(issues) == 0, issues

    def _check_systemd(self) -> bool:
        """Check if systemd is working."""
        try:
            result = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            status = result.stdout.strip()
            return status in ["running", "degraded"]
        except Exception:
            return False

    def _check_service(self, service: str) -> bool:
        """Check if a service is running or can start."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_vfio_modules(self) -> bool:
        """Check if VFIO modules are loaded."""
        try:
            with open("/proc/modules") as f:
                modules = f.read()
                return "vfio" in modules
        except Exception:
            return False

    def _check_libvirt(self) -> bool:
        """Check if libvirt is responding."""
        try:
            import libvirt
            conn = libvirt.open("qemu:///system")
            if conn:
                conn.close()
                return True
        except Exception:
            pass
        return False
```

---

## UI/UX Polish

### Consistent Error Dialogs

Create `src/common/dialogs.py`:

```python
"""
Common dialog utilities for NeuronOS applications.
"""

from gi.repository import Gtk, Adw


def show_error(parent: Gtk.Window, title: str, message: str, details: str = None):
    """Show standardized error dialog."""
    dialog = Adw.MessageDialog(
        transient_for=parent,
        heading=title,
        body=message,
    )

    if details:
        expander = Gtk.Expander(label="Details")
        details_label = Gtk.Label(label=details)
        details_label.set_wrap(True)
        details_label.set_selectable(True)
        expander.set_child(details_label)
        dialog.set_extra_child(expander)

    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.present()


def show_confirmation(
    parent: Gtk.Window,
    title: str,
    message: str,
    confirm_label: str = "Confirm",
    destructive: bool = False,
    callback=None,
):
    """Show confirmation dialog."""
    dialog = Adw.MessageDialog(
        transient_for=parent,
        heading=title,
        body=message,
    )

    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", confirm_label)

    if destructive:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)

    dialog.set_default_response("cancel")

    if callback:
        dialog.connect("response", lambda d, r: callback(r == "confirm"))

    dialog.present()


def show_progress(
    parent: Gtk.Window,
    title: str,
    message: str,
) -> Adw.Window:
    """Show progress dialog with spinner."""
    dialog = Adw.Window()
    dialog.set_transient_for(parent)
    dialog.set_modal(True)
    dialog.set_title(title)
    dialog.set_default_size(400, 150)
    dialog.set_resizable(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_start(24)
    box.set_margin_end(24)
    box.set_margin_top(24)
    box.set_margin_bottom(24)

    spinner = Gtk.Spinner()
    spinner.set_size_request(48, 48)
    spinner.start()
    box.append(spinner)

    label = Gtk.Label(label=message)
    label.set_wrap(True)
    box.append(label)

    progress = Gtk.ProgressBar()
    box.append(progress)

    dialog.set_content(box)

    # Add helper methods
    dialog.set_message = lambda msg: label.set_text(msg)
    dialog.set_progress = lambda frac: progress.set_fraction(frac)

    return dialog
```

### Accessibility Improvements

Add to all GUI components:

```python
# Add tooltips to buttons
button.set_tooltip_text("Create a new virtual machine")

# Add accessible labels
entry.set_accessible_role(Gtk.AccessibleRole.TEXT_BOX)

# Support keyboard navigation
widget.set_focusable(True)

# High contrast support via CSS classes
widget.add_css_class("accent")  # Uses theme accent color
```

---

## Verification Checklist

### Before Marking Phase 3 Complete

- [ ] Guest agent client can ping Windows guest
- [ ] Clipboard sync works between host and guest
- [ ] Resolution sync updates guest when window resizes
- [ ] Browser profiles migrate correctly
- [ ] SSH keys have proper permissions after migration
- [ ] ACS override detection works
- [ ] GPU reset bug detection works
- [ ] Update verification catches broken systems
- [ ] Error dialogs are consistent
- [ ] All UI elements have tooltips

---

## Next Phase

Proceed to [Phase 3A: Guest Agent Protocol](./PHASE_3A_GUEST_AGENT.md) for detailed guest agent implementation, or continue to [Phase 4: Error Handling](./PHASE_4_ERROR_HANDLING.md).
