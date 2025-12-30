#!/usr/bin/env python3
"""
NeuronOS USB Passthrough Manager

Provides seamless USB device passthrough to VMs, similar to Windows/macOS:
- Automatic device detection
- Hot-plug support
- User-friendly device names
- Automatic permission handling
"""

import logging
import os
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set
from enum import Enum
import json
import re

try:
    import pyudev
    PYUDEV_AVAILABLE = True
except ImportError:
    PYUDEV_AVAILABLE = False

logger = logging.getLogger(__name__)


class USBDeviceType(Enum):
    """Types of USB devices."""
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    GAMEPAD = "gamepad"
    STORAGE = "storage"
    AUDIO = "audio"
    WEBCAM = "webcam"
    PRINTER = "printer"
    HUB = "hub"
    OTHER = "other"


@dataclass
class USBDevice:
    """Information about a USB device."""
    bus: str
    device: str
    vendor_id: str
    product_id: str
    vendor_name: str
    product_name: str
    device_type: USBDeviceType
    serial: Optional[str] = None
    is_hub: bool = False

    @property
    def usb_id(self) -> str:
        """Get USB ID in vendor:product format."""
        return f"{self.vendor_id}:{self.product_id}"

    @property
    def display_name(self) -> str:
        """Get user-friendly display name."""
        if self.product_name and self.product_name != "Unknown":
            return f"{self.vendor_name} {self.product_name}"
        return f"USB Device ({self.usb_id})"

    @property
    def sysfs_path(self) -> Path:
        """Get sysfs path for this device."""
        return Path(f"/sys/bus/usb/devices/{self.bus}-{self.device}")


@dataclass
class USBPassthroughRule:
    """A rule for automatic USB passthrough."""
    vendor_id: str
    product_id: str
    target_vm: str
    enabled: bool = True
    description: str = ""


class USBDeviceScanner:
    """Scans and monitors USB devices."""

    # USB class codes for device type detection
    USB_CLASS_HUB = 0x09
    USB_CLASS_HID = 0x03
    USB_CLASS_AUDIO = 0x01
    USB_CLASS_VIDEO = 0x0e
    USB_CLASS_STORAGE = 0x08
    USB_CLASS_PRINTER = 0x07

    def __init__(self):
        self._context = None
        self._monitor = None
        if PYUDEV_AVAILABLE:
            self._context = pyudev.Context()

    def scan_all(self) -> List[USBDevice]:
        """Scan all connected USB devices."""
        devices = []

        if self._context:
            for device in self._context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
                usb_dev = self._parse_udev_device(device)
                if usb_dev and not usb_dev.is_hub:
                    devices.append(usb_dev)
        else:
            # Fallback to lsusb
            devices = self._scan_with_lsusb()

        return devices

    def _parse_udev_device(self, device) -> Optional[USBDevice]:
        """Parse a pyudev device object."""
        try:
            vendor_id = device.get('ID_VENDOR_ID', '')
            product_id = device.get('ID_MODEL_ID', '')

            if not vendor_id or not product_id:
                return None

            vendor_name = device.get('ID_VENDOR', 'Unknown')
            product_name = device.get('ID_MODEL', 'Unknown')

            # Clean up names
            vendor_name = vendor_name.replace('_', ' ')
            product_name = product_name.replace('_', ' ')

            # Get bus and device numbers
            bus = device.get('BUSNUM', '0')
            dev = device.get('DEVNUM', '0')

            # Determine device type
            device_type = self._determine_device_type(device)

            # Check if hub
            is_hub = device.get('ID_USB_INTERFACES', '').startswith(':09')

            return USBDevice(
                bus=bus,
                device=dev,
                vendor_id=vendor_id,
                product_id=product_id,
                vendor_name=vendor_name,
                product_name=product_name,
                device_type=device_type,
                serial=device.get('ID_SERIAL_SHORT'),
                is_hub=is_hub,
            )
        except Exception as e:
            logger.debug(f"Failed to parse USB device: {e}")
            return None

    def _determine_device_type(self, device) -> USBDeviceType:
        """Determine the type of USB device."""
        # Check udev properties
        if device.get('ID_INPUT_KEYBOARD'):
            return USBDeviceType.KEYBOARD
        if device.get('ID_INPUT_MOUSE'):
            return USBDeviceType.MOUSE
        if device.get('ID_INPUT_JOYSTICK'):
            return USBDeviceType.GAMEPAD

        # Check USB class
        usb_class = device.get('ID_USB_CLASS_FROM_DATABASE', '')
        if 'Audio' in usb_class:
            return USBDeviceType.AUDIO
        if 'Video' in usb_class:
            return USBDeviceType.WEBCAM
        if 'Mass Storage' in usb_class:
            return USBDeviceType.STORAGE
        if 'Printer' in usb_class:
            return USBDeviceType.PRINTER
        if 'Hub' in usb_class:
            return USBDeviceType.HUB

        return USBDeviceType.OTHER

    def _scan_with_lsusb(self) -> List[USBDevice]:
        """Fallback scanning using lsusb."""
        devices = []

        try:
            result = subprocess.run(
                ['lsusb'],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.strip().split('\n'):
                device = self._parse_lsusb_line(line)
                if device and not device.is_hub:
                    devices.append(device)

        except Exception as e:
            logger.error(f"lsusb scan failed: {e}")

        return devices

    def _parse_lsusb_line(self, line: str) -> Optional[USBDevice]:
        """Parse a line from lsusb output."""
        # Format: Bus 001 Device 002: ID 8087:0024 Intel Corp. Integrated Rate Matching Hub
        match = re.match(
            r'Bus (\d+) Device (\d+): ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)',
            line,
            re.IGNORECASE
        )

        if not match:
            return None

        bus, device, vendor_id, product_id, name = match.groups()

        # Parse vendor and product from name
        name_parts = name.split(' ', 1)
        vendor_name = name_parts[0] if name_parts else 'Unknown'
        product_name = name_parts[1] if len(name_parts) > 1 else 'Unknown'

        # Check for hub
        is_hub = 'hub' in name.lower()

        return USBDevice(
            bus=bus,
            device=device,
            vendor_id=vendor_id,
            product_id=product_id,
            vendor_name=vendor_name,
            product_name=product_name,
            device_type=USBDeviceType.HUB if is_hub else USBDeviceType.OTHER,
            is_hub=is_hub,
        )


class USBPassthroughManager:
    """
    Manages USB device passthrough to VMs.

    Provides seamless USB passthrough similar to Windows/macOS:
    - No manual configuration needed
    - Hot-plug support
    - Automatic rule-based passthrough
    """

    CONFIG_PATH = Path("/etc/neuron-os/usb-passthrough.json")
    RULES_PATH = Path("/etc/neuron-os/usb-rules.json")

    def __init__(self):
        self.scanner = USBDeviceScanner()
        self._rules: List[USBPassthroughRule] = []
        self._attached_devices: Dict[str, str] = {}  # usb_id -> vm_name
        self._load_rules()

    def _load_rules(self):
        """Load passthrough rules from config."""
        if self.RULES_PATH.exists():
            try:
                with open(self.RULES_PATH) as f:
                    data = json.load(f)
                    self._rules = [
                        USBPassthroughRule(**rule)
                        for rule in data.get('rules', [])
                    ]
            except Exception as e:
                logger.error(f"Failed to load USB rules: {e}")

    def _save_rules(self):
        """Save passthrough rules to config."""
        self.RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                'rules': [
                    {
                        'vendor_id': r.vendor_id,
                        'product_id': r.product_id,
                        'target_vm': r.target_vm,
                        'enabled': r.enabled,
                        'description': r.description,
                    }
                    for r in self._rules
                ]
            }
            with open(self.RULES_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save USB rules: {e}")

    def get_available_devices(self) -> List[USBDevice]:
        """Get all available USB devices."""
        return self.scanner.scan_all()

    def get_passthrough_candidates(self) -> List[USBDevice]:
        """Get devices suitable for passthrough (exclude system devices)."""
        devices = self.scanner.scan_all()

        # Filter out common system devices that shouldn't be passed through
        excluded_vendors = {
            '1d6b',  # Linux Foundation (virtual hubs)
            '8087',  # Intel (USB hubs)
        }

        return [
            d for d in devices
            if d.vendor_id not in excluded_vendors
            and not d.is_hub
        ]

    def attach_device(self, device: USBDevice, vm_name: str) -> bool:
        """
        Attach a USB device to a VM.

        Uses virsh attach-device with hotplug support.
        """
        xml = f"""<hostdev mode='subsystem' type='usb' managed='yes'>
  <source>
    <vendor id='0x{device.vendor_id}'/>
    <product id='0x{device.product_id}'/>
  </source>
</hostdev>"""

        try:
            # Write XML to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml)
                xml_path = f.name

            # Attach device
            result = subprocess.run(
                ['virsh', 'attach-device', vm_name, xml_path, '--live'],
                capture_output=True,
                text=True,
                timeout=10
            )

            os.unlink(xml_path)

            if result.returncode == 0:
                self._attached_devices[device.usb_id] = vm_name
                logger.info(f"Attached {device.display_name} to {vm_name}")
                return True
            else:
                logger.error(f"Failed to attach device: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to attach USB device: {e}")
            return False

    def detach_device(self, device: USBDevice, vm_name: str) -> bool:
        """Detach a USB device from a VM."""
        xml = f"""<hostdev mode='subsystem' type='usb' managed='yes'>
  <source>
    <vendor id='0x{device.vendor_id}'/>
    <product id='0x{device.product_id}'/>
  </source>
</hostdev>"""

        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml)
                xml_path = f.name

            result = subprocess.run(
                ['virsh', 'detach-device', vm_name, xml_path, '--live'],
                capture_output=True,
                text=True,
                timeout=10
            )

            os.unlink(xml_path)

            if result.returncode == 0:
                self._attached_devices.pop(device.usb_id, None)
                logger.info(f"Detached {device.display_name} from {vm_name}")
                return True
            else:
                logger.error(f"Failed to detach device: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to detach USB device: {e}")
            return False

    def add_auto_passthrough_rule(
        self,
        device: USBDevice,
        vm_name: str,
        description: str = ""
    ) -> None:
        """Add a rule to automatically pass through a device when detected."""
        rule = USBPassthroughRule(
            vendor_id=device.vendor_id,
            product_id=device.product_id,
            target_vm=vm_name,
            enabled=True,
            description=description or device.display_name,
        )
        self._rules.append(rule)
        self._save_rules()

    def remove_auto_passthrough_rule(self, device: USBDevice) -> None:
        """Remove auto-passthrough rule for a device."""
        self._rules = [
            r for r in self._rules
            if not (r.vendor_id == device.vendor_id and r.product_id == device.product_id)
        ]
        self._save_rules()

    def get_rules_for_vm(self, vm_name: str) -> List[USBPassthroughRule]:
        """Get all passthrough rules for a specific VM."""
        return [r for r in self._rules if r.target_vm == vm_name and r.enabled]

    def apply_rules_for_vm(self, vm_name: str) -> int:
        """
        Apply all matching passthrough rules for a VM.

        Returns the number of devices attached.
        """
        count = 0
        rules = self.get_rules_for_vm(vm_name)
        devices = self.get_available_devices()

        for rule in rules:
            for device in devices:
                if device.vendor_id == rule.vendor_id and device.product_id == rule.product_id:
                    if self.attach_device(device, vm_name):
                        count += 1
                    break

        return count

    def is_device_attached(self, device: USBDevice) -> Optional[str]:
        """Check if a device is attached to any VM."""
        return self._attached_devices.get(device.usb_id)


# Singleton instance
_manager: Optional[USBPassthroughManager] = None


def get_usb_manager() -> USBPassthroughManager:
    """Get the singleton USB passthrough manager instance."""
    global _manager
    if _manager is None:
        _manager = USBPassthroughManager()
    return _manager


if __name__ == "__main__":
    # Test scanning
    manager = get_usb_manager()
    devices = manager.get_passthrough_candidates()

    print("Available USB devices for passthrough:")
    for device in devices:
        print(f"  {device.display_name} [{device.usb_id}] - {device.device_type.value}")
