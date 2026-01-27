# Phase 2.3: Automatic Hardware Configuration (IOMMU/VFIO/GPU Passthrough)

**Status**: 🟡 PARTIAL - Detection fully works, kernel setup incomplete
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.1-1.5 complete (VM creation foundation)

---

## What is Hardware Configuration?

NeuronOS's unique value is **GPU passthrough** - running Windows in a VM with native GPU performance, so heavy apps like Photoshop and AutoCAD work perfectly. But this requires several kernel and system configurations:

1. **IOMMU** - Allows the kernel to isolate PCIe devices (GPUs) for VM-exclusive access
2. **VFIO** - Virtual Function I/O driver that binds GPUs to the VM
3. **ACS Override** - Enables IOMMU grouping on systems where it's disabled (some AMD boards)
4. **GPU Binding** - Moves GPUs from the host OS driver to the VM driver

**Without this phase**: Users see "GPU passthrough not available" even on capable hardware. VMs default to software rendering (100x slower).

---

## Current State: Partial Implementation

### What Already Works ✅

- **GPU Scanner** (`src/hardware_detect/gpu_scanner.py` - 355 lines)
  - Detects all GPUs (Intel iGPU, AMD/NVIDIA discrete)
  - Identifies which GPU is driving the display
  - Recommends best GPU for passthrough (non-display GPU)
  - JSON export for programmatic use

- **IOMMU Parser** (`src/hardware_detect/iommu_parser.py` - 407 lines)
  - Parses `/sys/kernel/iommu_groups/`
  - Identifies which devices share IOMMU groups
  - Detects GPU reset bugs (e.g., AMD Navi)
  - Checks if IOMMU is enabled in current kernel

- **GPU Passthrough Manager** (`src/vm_manager/passthrough/gpu_attach.py` - 322 lines)
  - Binds GPUs to vfio-pci driver
  - Manages VFIO device IDs
  - Stores original driver info for restoration

### What's Missing ❌

| Missing Piece | Impact | Workaround |
|---|---|---|
| Auto-enable IOMMU in GRUB | Without this, even capable hardware shows "IOMMU disabled" | Manual `grub-mkconfig` needed |
| ACS Override installation | AMD systems fail silently | Manual kernel parameter editing |
| Vendor-reset module | AMD GPU reset hangs | Manual compilation/load |
| Onboarding integration | Users don't know GPU setup failed | Test errors bury the real issue |
| Kernel parameter updates | GRUB config not applied after edits | Manual reboot needed twice |

### The Impact

**Scenario**: A user with AMD Ryzen + RX 6600 XT tries NeuronOS:
1. ✅ Boot succeeds
2. ✅ Onboarding runs
3. ✅ "Creating Windows VM..."
4. ❌ VM creation fails silently
5. ❌ No clear error message
6. ❌ User thinks NeuronOS is broken
7. **Reality**: IOMMU was never enabled in kernel

---

## Objective: Full Automatic Hardware Setup

After completing Phase 2.3:

1. ✅ **Auto-detect hardware capabilities** - Scan IOMMU groups, GPU models, compute capability
2. ✅ **Auto-enable IOMMU** - Modify GRUB to enable VT-d or AMD-Vi automatically
3. ✅ **Auto-configure ACS Override** - Enable for systems that need it
4. ✅ **Auto-install kernel modules** - Vendor-reset for AMD GPU reset bugs
5. ✅ **Create VMs with detected GPUs** - No manual configuration needed
6. ✅ **Clear error messages** - Users understand what failed and why
7. ✅ **Graceful fallbacks** - If GPU setup fails, offer software rendering or VM recreation

---

## Part 1: Understand Current Hardware Detection

The detection code is already complete but isolated. We need to integrate it into the onboarding workflow.

### 1.1: Review Existing Hardware Modules

**GPU Scanner** - `src/hardware_detect/gpu_scanner.py`:
```python
class GPUDevice:
    """Detected GPU."""
    pci_address: str       # "0000:01:00.0"
    vendor_id: str         # "10de" (NVIDIA)
    device_id: str         # "2504" (RTX 4070)
    vendor_name: str       # "NVIDIA Corporation"
    device_name: str       # "GeForce RTX 4070"
    is_integrated: bool    # False for discrete
    is_boot_vga: bool      # True if driving display
    driver: str            # "nvidia" or "amdgpu"
    iommu_group: Optional[int]  # 14 (if IOMMU enabled)

class GPUScanner:
    """Scans for available GPUs."""
    def scan() -> List[GPUDevice]:
        """Return all GPUs on system."""
        # Already works - finds all GPUs

    def get_passthrough_candidate() -> Optional[GPUDevice]:
        """Return best GPU for VM passthrough."""
        # Prefers discrete, non-boot GPU

    def to_json() -> str:
        """Export as JSON for UI display."""
```

**IOMMU Parser** - `src/hardware_detect/iommu_parser.py`:
```python
class IOMMUGroup:
    """Devices in same IOMMU group (can't separate)."""
    group_id: int          # 14
    devices: List[IOMMUDevice]  # GPU + audio + bridges
    has_gpu: bool          # True if contains GPU
    is_clean: bool         # True if only GPU (no other devices)
    needs_acs_override: bool  # True on some AMD boards
    gpu_reset_bug: bool    # True for AMD Navi (needs vendor-reset)

class IOMMUParser:
    """Analyzes IOMMU capabilities."""
    def parse() -> List[IOMMUGroup]:
        """Parse /sys/kernel/iommu_groups/"""
        # Already works

    def is_iommu_enabled() -> bool:
        """Check if IOMMU in kernel cmdline."""
        # Parses /proc/cmdline

    def get_recommendations() -> HardwareRecommendations:
        """Return what hardware changes needed."""
```

**GPU Passthrough Manager** - `src/vm_manager/passthrough/gpu_attach.py`:
```python
class GPUPassthroughManager:
    """Manages GPU binding to vfio-pci."""
    def bind_to_vfio(gpu: GPUDevice, group: IOMMUGroup) -> bool:
        """Bind GPU + audio + bridges to vfio-pci."""
        # Manipulates sysfs to change drivers

    def unbind_from_vfio(gpu: GPUDevice) -> bool:
        """Restore GPU to original driver."""
        # Restores original driver

    def prepare_group_for_passthrough(group: IOMMUGroup) -> bool:
        """Prepare entire IOMMU group."""
        # Binds all devices in group
```

---

## Part 2: Create Hardware Setup Manager

We need a new high-level module that **coordinates** all the detection and kernel setup. Create:

**File**: `src/vm_manager/core/hardware_setup.py`

```python
"""Hardware setup orchestration for GPU passthrough.

This module coordinates:
- Hardware detection (GPUs, IOMMU)
- Kernel configuration (GRUB editing)
- Driver binding (VFIO setup)
- Module installation (vendor-reset)

The goal is: users select "Auto-configure hardware" and everything works.
"""

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from src.hardware_detect.gpu_scanner import GPUDevice, GPUScanner
from src.hardware_detect.iommu_parser import IOMMUParser, IOMMUGroup
from src.vm_manager.passthrough.gpu_attach import GPUPassthroughManager
from src.common.exceptions import HardwareError

logger = logging.getLogger(__name__)


class HardwareSetupStatus(Enum):
    """Status of hardware configuration."""
    NOT_STARTED = "not_started"
    DETECTED = "detected"
    IOMMU_ENABLED = "iommu_enabled"
    VFIO_LOADED = "vfio_loaded"
    GPU_BOUND = "gpu_bound"
    VENDOR_RESET_INSTALLED = "vendor_reset_installed"
    READY = "ready"
    ERROR = "error"
    MANUAL_INTERVENTION_NEEDED = "manual_intervention_needed"


@dataclass
class HardwareSetupResult:
    """Result of hardware setup."""
    status: HardwareSetupStatus
    success: bool
    gpus_detected: List[GPUDevice]
    selected_gpu: Optional[GPUDevice]
    iommu_enabled: bool
    needs_reboot: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    manual_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "success": self.success,
            "gpus_detected": [
                {
                    "pci": gpu.pci_address,
                    "name": gpu.device_name,
                    "vendor": gpu.vendor_name,
                    "integrated": gpu.is_integrated,
                    "boot_vga": gpu.is_boot_vga,
                }
                for gpu in self.gpus_detected
            ],
            "selected_gpu": {
                "pci": self.selected_gpu.pci_address,
                "name": self.selected_gpu.device_name,
            } if self.selected_gpu else None,
            "iommu_enabled": self.iommu_enabled,
            "needs_reboot": self.needs_reboot,
            "warnings": self.warnings,
            "errors": self.errors,
            "manual_steps": self.manual_steps,
        }


class HardwareSetupManager:
    """Orchestrates hardware detection and configuration."""

    def __init__(self):
        """Initialize hardware setup manager."""
        self.gpu_scanner = GPUScanner()
        self.iommu_parser = IOMMUParser()
        self.passthrough_manager = GPUPassthroughManager()
        self.grub_path = Path("/etc/default/grub")
        self.grub_cfg_path = Path("/boot/grub/grub.cfg")

    def auto_detect_and_setup(
        self,
        enable_iommu: bool = True,
        install_vendor_reset: bool = True,
        enable_acs_override: bool = True,
        needs_reboot: bool = False,
    ) -> HardwareSetupResult:
        """Auto-detect hardware and set everything up.

        This is the main entry point for onboarding.

        Args:
            enable_iommu: Automatically update GRUB to enable IOMMU
            install_vendor_reset: Automatically install vendor-reset module if needed
            enable_acs_override: Automatically enable ACS Override on AMD boards
            needs_reboot: If True, skip kernel-based steps (system will reboot)

        Returns:
            HardwareSetupResult with status, errors, and next steps.
        """
        result = HardwareSetupResult(
            status=HardwareSetupStatus.NOT_STARTED,
            success=False,
            gpus_detected=[],
            selected_gpu=None,
            iommu_enabled=False,
            needs_reboot=needs_reboot,
        )

        try:
            logger.info("Starting hardware auto-detection and setup")

            # Step 1: Detect GPUs
            logger.info("Scanning for GPUs...")
            result.gpus_detected = self.gpu_scanner.scan()
            if not result.gpus_detected:
                result.errors.append(
                    "No GPUs detected. This system may not support GPU passthrough."
                )
                result.status = HardwareSetupStatus.ERROR
                return result

            logger.info(f"Found {len(result.gpus_detected)} GPU(s)")
            for gpu in result.gpus_detected:
                logger.info(f"  - {gpu.device_name} ({gpu.pci_address})")

            # Step 2: Check IOMMU capability
            logger.info("Checking IOMMU groups...")
            iommu_groups = self.iommu_parser.parse()
            result.iommu_enabled = self.iommu_parser.is_iommu_enabled()

            if not result.iommu_enabled and enable_iommu:
                logger.info("IOMMU not enabled. Attempting to enable...")
                if self._enable_iommu_in_grub():
                    result.warnings.append(
                        "IOMMU enabled in GRUB. System reboot required."
                    )
                    result.needs_reboot = True
                else:
                    result.errors.append("Failed to enable IOMMU in GRUB")
                    result.status = HardwareSetupStatus.ERROR
                    return result

            # If reboot needed, stop here
            if result.needs_reboot and not needs_reboot:
                result.status = HardwareSetupStatus.IOMMU_ENABLED
                result.manual_steps.append(
                    "1. Reboot system: sudo reboot"
                )
                result.manual_steps.append(
                    "2. After reboot, run NeuronOS setup again"
                )
                return result

            # Step 3: Check ACS Override
            for group in iommu_groups:
                if group.needs_acs_override:
                    logger.info(f"IOMMU group {group.group_id} needs ACS Override")
                    if enable_acs_override:
                        if self._enable_acs_override():
                            result.warnings.append(
                                "ACS Override enabled. System reboot required."
                            )
                            result.needs_reboot = True
                        else:
                            result.errors.append(
                                f"Failed to enable ACS Override for group {group.group_id}"
                            )

            # If reboot needed, stop here
            if result.needs_reboot and not needs_reboot:
                result.status = HardwareSetupStatus.IOMMU_ENABLED
                result.manual_steps.append(
                    "1. Reboot system: sudo reboot"
                )
                result.manual_steps.append(
                    "2. After reboot, run NeuronOS setup again"
                )
                return result

            # Step 4: Select best GPU for passthrough
            result.selected_gpu = self.gpu_scanner.get_passthrough_candidate()
            if not result.selected_gpu:
                result.errors.append(
                    "Could not find suitable GPU for passthrough. "
                    "Please ensure you have a discrete GPU (not just integrated graphics)."
                )
                result.status = HardwareSetupStatus.ERROR
                return result

            logger.info(f"Selected GPU for passthrough: {result.selected_gpu.device_name}")

            # Step 5: Load VFIO modules
            if not self._load_vfio_modules():
                result.errors.append("Failed to load VFIO kernel modules")
                result.status = HardwareSetupStatus.ERROR
                return result
            result.status = HardwareSetupStatus.VFIO_LOADED

            # Step 6: Check for GPU reset bugs and install vendor-reset if needed
            for group in iommu_groups:
                if group.gpu_reset_bug and install_vendor_reset:
                    logger.info(
                        f"GPU reset bug detected in group {group.group_id}. "
                        "Installing vendor-reset module..."
                    )
                    if self._install_vendor_reset():
                        result.status = HardwareSetupStatus.VENDOR_RESET_INSTALLED
                    else:
                        result.warnings.append(
                            "Vendor-reset module not available. "
                            "GPU may hang on reset. Consider compiling from source."
                        )

            # Step 7: Bind GPU to VFIO
            gpu_group = None
            for group in iommu_groups:
                if any(d.pci_address == result.selected_gpu.pci_address for d in group.devices):
                    gpu_group = group
                    break

            if gpu_group:
                if self.passthrough_manager.prepare_group_for_passthrough(gpu_group):
                    result.status = HardwareSetupStatus.GPU_BOUND
                    logger.info(f"GPU bound to VFIO successfully")
                else:
                    result.warnings.append(
                        "GPU binding to VFIO failed. "
                        "Will attempt at VM creation time."
                    )
            else:
                result.warnings.append(
                    "Could not determine IOMMU group for selected GPU. "
                    "Will attempt binding at VM creation time."
                )

            result.status = HardwareSetupStatus.READY
            result.success = True
            logger.info("Hardware setup completed successfully")

            return result

        except Exception as e:
            logger.exception("Hardware setup failed with exception")
            result.status = HardwareSetupStatus.ERROR
            result.errors.append(f"Unexpected error: {str(e)}")
            return result

    def _enable_iommu_in_grub(self) -> bool:
        """Enable IOMMU in GRUB configuration.

        Modifies /etc/default/grub to add IOMMU kernel parameter.
        Requires root privilege.

        For Intel: intel_iommu=on
        For AMD: amd_iommu=on

        Returns:
            True if modification successful, False otherwise.
        """
        try:
            if not self.grub_path.exists():
                logger.error(f"GRUB config not found at {self.grub_path}")
                return False

            # Read current GRUB config
            content = self.grub_path.read_text()

            # Determine CPU type
            cpu_type = self._detect_cpu_type()
            if cpu_type == "intel":
                iommu_param = "intel_iommu=on"
            elif cpu_type == "amd":
                iommu_param = "amd_iommu=on"
            else:
                logger.error(f"Unknown CPU type: {cpu_type}")
                return False

            # Check if already enabled
            if iommu_param in content:
                logger.info(f"IOMMU already enabled ({iommu_param})")
                return True

            # Update GRUB_CMDLINE_LINUX_DEFAULT
            lines = []
            for line in content.split("\n"):
                if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    # Extract existing params and add IOMMU param
                    if '"' in line:
                        start = line.index('"') + 1
                        end = line.rindex('"')
                        params = line[start:end]
                        new_params = f'{params} {iommu_param}'.strip()
                        line = f'GRUB_CMDLINE_LINUX_DEFAULT="{new_params}"'
                    logger.info(f"Updated GRUB line: {line}")
                lines.append(line)

            # Write back atomically
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.grub_path.parent,
                delete=False,
                suffix=".tmp"
            ) as tmp:
                tmp.write("\n".join(lines) + "\n")
                tmp_path = Path(tmp.name)

            # Atomic rename
            tmp_path.replace(self.grub_path)
            logger.info(f"GRUB config updated with {iommu_param}")

            # Regenerate GRUB config
            if not self._regenerate_grub_config():
                logger.error("Failed to regenerate GRUB config")
                return False

            return True

        except Exception as e:
            logger.exception(f"Failed to enable IOMMU in GRUB: {e}")
            return False

    def _enable_acs_override(self) -> bool:
        """Enable ACS Override for systems that need it.

        Some AMD chipsets require ACS Override to enable IOMMU grouping.

        Returns:
            True if enabled, False otherwise.
        """
        try:
            # Check if already enabled
            if "pcie_acs_override=downstream" in Path("/proc/cmdline").read_text():
                logger.info("ACS Override already enabled")
                return True

            # Add to GRUB config
            content = self.grub_path.read_text()
            lines = []
            for line in content.split("\n"):
                if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    if '"' in line:
                        start = line.index('"') + 1
                        end = line.rindex('"')
                        params = line[start:end]
                        new_params = f'{params} pcie_acs_override=downstream'.strip()
                        line = f'GRUB_CMDLINE_LINUX_DEFAULT="{new_params}"'
                    logger.info(f"Enabled ACS Override: {line}")
                lines.append(line)

            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.grub_path.parent,
                delete=False,
                suffix=".tmp"
            ) as tmp:
                tmp.write("\n".join(lines) + "\n")
                tmp_path = Path(tmp.name)

            tmp_path.replace(self.grub_path)

            if not self._regenerate_grub_config():
                return False

            return True

        except Exception as e:
            logger.exception(f"Failed to enable ACS Override: {e}")
            return False

    def _regenerate_grub_config(self) -> bool:
        """Regenerate GRUB configuration after editing.

        Runs grub-mkconfig to apply changes.

        Returns:
            True if successful, False otherwise.
        """
        try:
            result = subprocess.run(
                ["sudo", "grub-mkconfig", "-o", str(self.grub_cfg_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("GRUB config regenerated successfully")
                return True
            else:
                logger.error(f"grub-mkconfig failed: {result.stderr}")
                return False
        except Exception as e:
            logger.exception(f"Failed to regenerate GRUB config: {e}")
            return False

    def _load_vfio_modules(self) -> bool:
        """Load required VFIO kernel modules.

        Loads:
        - vfio
        - vfio_pci
        - vfio_iommu_type1

        Returns:
            True if all modules loaded, False otherwise.
        """
        modules = ["vfio", "vfio_pci", "vfio_iommu_type1"]
        for module in modules:
            try:
                result = subprocess.run(
                    ["sudo", "modprobe", module],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    logger.info(f"Loaded module: {module}")
                else:
                    logger.error(f"Failed to load {module}: {result.stderr}")
                    return False
            except Exception as e:
                logger.exception(f"Failed to load {module}: {e}")
                return False
        return True

    def _install_vendor_reset(self) -> bool:
        """Install vendor-reset kernel module for AMD GPU reset bugs.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Check if already installed
            result = subprocess.run(
                ["modinfo", "vendor-reset"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("vendor-reset module already installed")
                return True

            # Try to install via package manager
            # Arch: yay -S vendor-reset-dkms
            result = subprocess.run(
                ["sudo", "pacman", "-S", "--noconfirm", "vendor-reset-dkms"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info("vendor-reset module installed via pacman")
                return True

            logger.warning("vendor-reset module not available in packages")
            return False

        except Exception as e:
            logger.warning(f"Failed to install vendor-reset: {e}")
            return False

    def _detect_cpu_type(self) -> str:
        """Detect CPU type (intel or amd).

        Returns:
            "intel", "amd", or "unknown"
        """
        try:
            result = subprocess.run(
                ["grep", "-i", "vendor_id", "/proc/cpuinfo"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "GenuineIntel" in result.stdout:
                return "intel"
            elif "AuthenticAMD" in result.stdout:
                return "amd"
            return "unknown"
        except Exception:
            return "unknown"

    def get_status(self) -> dict:
        """Get current hardware setup status.

        Returns:
            Dictionary with hardware capability information.
        """
        try:
            gpus = self.gpu_scanner.scan()
            iommu_groups = self.iommu_parser.parse()
            iommu_enabled = self.iommu_parser.is_iommu_enabled()

            return {
                "gpus": [
                    {
                        "pci": gpu.pci_address,
                        "name": gpu.device_name,
                        "integrated": gpu.is_integrated,
                    }
                    for gpu in gpus
                ],
                "iommu_enabled": iommu_enabled,
                "iommu_groups": len(iommu_groups),
                "ready_for_passthrough": iommu_enabled and bool(gpus),
            }
        except Exception as e:
            logger.exception("Failed to get hardware status")
            return {"error": str(e)}
```

---

## Part 3: Integrate into Onboarding Wizard

The onboarding wizard needs to **call** the hardware setup manager during setup.

**File**: `src/onboarding/wizard.py` (find the `on_wizard_complete()` method)

**Current** (doesn't do hardware setup):
```python
def on_wizard_complete(self):
    """Handle wizard completion."""
    # TODO: Execute setup!
    self.close()
```

**Replace with**:
```python
async def on_wizard_complete(self):
    """Execute full onboarding setup with hardware configuration."""
    from src.vm_manager.core.hardware_setup import HardwareSetupManager

    try:
        # Create progress window
        progress_window = self._create_progress_window()
        progress_window.show()

        # Update progress
        self._update_progress("Detecting hardware...", 10)

        # Run hardware setup
        hardware_manager = HardwareSetupManager()
        setup_result = hardware_manager.auto_detect_and_setup(
            enable_iommu=True,
            install_vendor_reset=True,
            enable_acs_override=True,
            needs_reboot=False,  # First pass, no reboot yet
        )

        if setup_result.needs_reboot:
            # Hardware changes require reboot
            self._show_reboot_required_dialog(setup_result)
            return

        if not setup_result.success:
            # Hardware setup failed
            self._show_hardware_error_dialog(setup_result)
            return

        self._update_progress("Hardware configured. Creating VM...", 30)

        # Continue with rest of onboarding...
        # (rest of setup code remains the same)

    except Exception as e:
        self._show_error(f"Onboarding failed: {str(e)}")
        logger.exception("Onboarding setup error")

def _show_reboot_required_dialog(self, result):
    """Show dialog that reboot is needed."""
    dialog = Gtk.MessageDialog(
        transient_for=self,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="System Reboot Required",
    )
    dialog.format_secondary_text(
        f"Your hardware configuration requires a system reboot.\n\n"
        f"Changes made:\n"
        + "\n".join(f"• {w}" for w in result.warnings)
        + "\n\nPlease reboot and run setup again."
    )
    dialog.run()
    dialog.destroy()
    subprocess.run(["sudo", "reboot"])

def _show_hardware_error_dialog(self, result):
    """Show dialog with hardware setup errors."""
    dialog = Gtk.MessageDialog(
        transient_for=self,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Hardware Setup Failed",
    )
    error_text = "\n".join(f"• {e}" for e in result.errors)
    manual_text = "\n".join(f"{i}. {s}" for i, s in enumerate(result.manual_steps, 1))

    secondary = f"Errors:\n{error_text}"
    if result.manual_steps:
        secondary += f"\n\nManual steps:\n{manual_text}"

    dialog.format_secondary_text(secondary)
    dialog.run()
    dialog.destroy()
```

---

## Part 4: Add Hardware Status Check to VM Creation

When creating a VM, verify that hardware is ready for GPU passthrough.

**File**: `src/vm_manager/core/vm_creator.py` (in `create_vm()` method)

**Add before VM creation**:
```python
async def create_vm(self, vm_config: VMConfig) -> str:
    """Create a new VM with given configuration."""
    from src.vm_manager.core.hardware_setup import HardwareSetupManager

    # If GPU passthrough requested, verify hardware is ready
    if vm_config.gpu_passthrough:
        logger.info("GPU passthrough requested. Checking hardware...")

        hardware_manager = HardwareSetupManager()
        status = hardware_manager.get_status()

        if not status.get("ready_for_passthrough"):
            if not status.get("iommu_enabled"):
                raise VMCreationError(
                    "IOMMU is not enabled. Run hardware setup first."
                )
            if not status.get("gpus"):
                raise VMCreationError(
                    "No GPUs detected. Hardware passthrough not available."
                )

        # Attempt to bind GPU if not already bound
        logger.info("Binding GPU to VFIO...")
        # (rest of VM creation continues...)

    # Continue with normal VM creation...
```

---

## Part 5: Testing Hardware Setup

Create comprehensive tests for the hardware setup module.

**File**: `tests/test_hardware_setup.py`

```python
"""Tests for hardware setup module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.vm_manager.core.hardware_setup import (
    HardwareSetupManager,
    HardwareSetupStatus,
    HardwareSetupResult,
)
from src.hardware_detect.gpu_scanner import GPUDevice
from src.hardware_detect.iommu_parser import IOMMUGroup, IOMMUDevice


@pytest.fixture
def hardware_manager():
    """Create hardware setup manager."""
    return HardwareSetupManager()


@pytest.fixture
def mock_gpu():
    """Create mock GPU device."""
    return GPUDevice(
        pci_address="0000:01:00.0",
        vendor_id="10de",
        device_id="2504",
        vendor_name="NVIDIA Corporation",
        device_name="GeForce RTX 4070",
        is_integrated=False,
        is_boot_vga=False,
        driver="nouveau",
        iommu_group=14,
    )


def test_hardware_setup_manager_init():
    """Test manager initialization."""
    manager = HardwareSetupManager()
    assert manager.gpu_scanner is not None
    assert manager.iommu_parser is not None
    assert manager.passthrough_manager is not None


@patch("src.vm_manager.core.hardware_setup.GPUScanner.scan")
def test_auto_detect_finds_gpus(mock_scan, hardware_manager, mock_gpu):
    """Test that auto-detect finds GPUs."""
    mock_scan.return_value = [mock_gpu]

    # Patch other methods to return success
    with patch.object(hardware_manager, "_enable_iommu_in_grub", return_value=False):
        with patch.object(hardware_manager.iommu_parser, "is_iommu_enabled", return_value=True):
            with patch.object(hardware_manager.iommu_parser, "parse", return_value=[]):
                with patch.object(hardware_manager, "_load_vfio_modules", return_value=True):
                    with patch.object(hardware_manager.gpu_scanner, "get_passthrough_candidate", return_value=mock_gpu):
                        result = hardware_manager.auto_detect_and_setup(enable_iommu=False)

    assert mock_gpu in result.gpus_detected
    assert result.selected_gpu == mock_gpu


@patch("src.vm_manager.core.hardware_setup.GPUScanner.scan")
def test_auto_detect_no_gpus(mock_scan, hardware_manager):
    """Test error handling when no GPUs found."""
    mock_scan.return_value = []

    result = hardware_manager.auto_detect_and_setup()

    assert not result.success
    assert result.status == HardwareSetupStatus.ERROR
    assert "No GPUs detected" in result.errors[0]


@patch("pathlib.Path.exists")
@patch("pathlib.Path.read_text")
def test_enable_iommu_in_grub(mock_read, mock_exists, hardware_manager):
    """Test GRUB modification for IOMMU."""
    mock_exists.return_value = True
    mock_read.return_value = 'GRUB_CMDLINE_LINUX_DEFAULT="quiet"'

    with patch.object(hardware_manager, "_detect_cpu_type", return_value="intel"):
        with patch.object(hardware_manager, "_regenerate_grub_config", return_value=True):
            with patch("pathlib.Path.write_text"):
                success = hardware_manager._enable_iommu_in_grub()

    assert success


@patch("subprocess.run")
def test_load_vfio_modules(mock_run, hardware_manager):
    """Test VFIO module loading."""
    mock_run.return_value = Mock(returncode=0)

    success = hardware_manager._load_vfio_modules()

    assert success
    assert mock_run.call_count == 3  # vfio, vfio_pci, vfio_iommu_type1


@patch("subprocess.run")
def test_cpu_type_detection(mock_run, hardware_manager):
    """Test CPU type detection."""
    mock_run.return_value = Mock(stdout="vendor_id\t: GenuineIntel\n", returncode=0)

    cpu_type = hardware_manager._detect_cpu_type()

    assert cpu_type == "intel"


def test_hardware_setup_result_to_dict(mock_gpu):
    """Test result serialization."""
    result = HardwareSetupResult(
        status=HardwareSetupStatus.READY,
        success=True,
        gpus_detected=[mock_gpu],
        selected_gpu=mock_gpu,
        iommu_enabled=True,
        needs_reboot=False,
        warnings=["test warning"],
    )

    result_dict = result.to_dict()

    assert result_dict["status"] == "ready"
    assert result_dict["success"] is True
    assert result_dict["iommu_enabled"] is True
    assert len(result_dict["gpus_detected"]) == 1


# Run tests: pytest tests/test_hardware_setup.py -v
```

**Run tests**:
```bash
pytest tests/test_hardware_setup.py -v
```

---

## Part 6: CLI Command for Manual Hardware Setup

For advanced users and debugging, provide a CLI command to run hardware setup manually.

**File**: `src/vm_manager/cli.py` (add new command)

```python
@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.option("--skip-reboot", is_flag=True, help="Don't reboot even if needed")
def setup_hardware(dry_run, skip_reboot):
    """Automatically configure hardware for GPU passthrough.

    This command:
    1. Detects GPUs and IOMMU capabilities
    2. Enables IOMMU in GRUB (Intel VT-d or AMD-Vi)
    3. Installs required kernel modules (VFIO)
    4. Installs vendor-reset for AMD GPUs if needed
    5. Prepares GPU for VM passthrough

    After this command, you can create VMs with GPU passthrough.

    Example:
        neuronos hardware setup
        neuronos hardware setup --dry-run
        neuronos hardware setup --skip-reboot
    """
    from src.vm_manager.core.hardware_setup import HardwareSetupManager

    if dry_run:
        click.echo("DRY RUN MODE - Nothing will be modified\n")

    manager = HardwareSetupManager()
    result = manager.auto_detect_and_setup(
        enable_iommu=not dry_run,
        install_vendor_reset=not dry_run,
        enable_acs_override=not dry_run,
        needs_reboot=False,
    )

    # Display results
    click.echo("\n=== Hardware Setup Results ===\n")

    click.echo(f"Status: {result.status.value}")
    click.echo(f"Success: {result.success}")
    click.echo(f"Needs Reboot: {result.needs_reboot}\n")

    if result.gpus_detected:
        click.echo("Detected GPUs:")
        for gpu in result.gpus_detected:
            click.echo(f"  • {gpu.device_name} ({gpu.pci_address})")
    if result.selected_gpu:
        click.echo(f"\nSelected for passthrough: {result.selected_gpu.device_name}")

    click.echo(f"\nIOMMU Enabled: {result.iommu_enabled}")

    if result.warnings:
        click.echo("\n⚠️  Warnings:")
        for warning in result.warnings:
            click.echo(f"  • {warning}")

    if result.errors:
        click.echo("\n❌ Errors:")
        for error in result.errors:
            click.echo(f"  • {error}")

    if result.manual_steps:
        click.echo("\nManual Steps Required:")
        for step in result.manual_steps:
            click.echo(f"  {step}")

    if result.needs_reboot and not skip_reboot:
        click.echo("\n⚠️  System reboot required. Rebooting in 10 seconds...")
        import time
        time.sleep(10)
        subprocess.run(["sudo", "reboot"])
```

---

## Verification Checklist

Before moving to Phase 2.4, verify ALL of these:

**Hardware Detection:**
- [ ] `HardwareSetupManager` initialized without errors
- [ ] `GPUScanner.scan()` returns all GPUs on system
- [ ] `IOMMUParser.parse()` returns IOMMU groups
- [ ] `IOMMUParser.is_iommu_enabled()` correctly identifies kernel state
- [ ] GPU selection returns non-boot discrete GPU preferentially

**Hardware Configuration:**
- [ ] GRUB modification adds correct IOMMU parameter (intel_iommu or amd_iommu)
- [ ] `grub-mkconfig` regenerates config without errors
- [ ] VFIO modules (vfio, vfio_pci, vfio_iommu_type1) load successfully
- [ ] ACS Override added to GRUB when needed
- [ ] Vendor-reset module installation attempted (may fail gracefully)

**Onboarding Integration:**
- [ ] Wizard calls `auto_detect_and_setup()` during completion
- [ ] Progress updates show during hardware setup
- [ ] Reboot dialog appears when kernel changes needed
- [ ] Error dialog shows clear messages on failure
- [ ] Manual steps are actionable and clear

**CLI Command:**
- [ ] `neuronos hardware setup` runs without errors
- [ ] `--dry-run` flag prevents modifications
- [ ] Output shows GPU list and IOMMU status clearly
- [ ] Errors/warnings are displayed
- [ ] Manual steps are shown

**Testing:**
- [ ] All unit tests pass: `pytest tests/test_hardware_setup.py -v`
- [ ] Mock tests cover success and error paths
- [ ] GRUB modification tested
- [ ] Module loading tested

---

## Acceptance Criteria

✅ **Phase 2.3 Complete When**:

1. Hardware auto-detection finds all GPUs
2. IOMMU automatically enabled in kernel (with reboot if needed)
3. ACS Override applied for systems that need it
4. VFIO modules loaded automatically
5. GPU bound to vfio-pci driver for VM access
6. Onboarding wizard integrates hardware setup
7. CLI command available for manual setup
8. All tests pass
9. Error messages are clear and actionable
10. Users can create VMs with GPU passthrough without manual kernel configuration

❌ **Phase 2.3 Fails If**:

- Hardware detection crashes or returns empty list
- GRUB modification corrupts boot process
- IOMMU kernel parameter not applied correctly
- VFIO modules fail to load
- GPU binding fails with no clear error message
- Onboarding doesn't check hardware before creating VM
- Tests fail

---

## Risks & Mitigations

### Risk 1: GRUB Modification Breaks Boot

**Issue**: Editing `/etc/default/grub` incorrectly could prevent boot

**Mitigation**:
- Always read original content first
- Use atomic file operations (temp + rename)
- Backup original `/etc/default/grub` before modification
- Provide recovery instructions if boot fails

**Recovery**:
```bash
# If system won't boot, boot from live USB and:
sudo mount /dev/sda1 /mnt  # Your root partition
cd /mnt/etc/default/
vi grub  # Fix manually
sudo grub-mkconfig -o /boot/grub/grub.cfg
sudo reboot
```

### Risk 2: Wrong CPU Type Detection

**Issue**: Can't distinguish Intel vs AMD, applies wrong IOMMU parameter

**Mitigation**:
- Check `/proc/cpuinfo` for `GenuineIntel` or `AuthenticAMD`
- Default to Intel (intel_iommu) if uncertain
- Log actual CPU type for debugging

### Risk 3: VFIO Modules Not Available

**Issue**: System doesn't have vfio kernel modules

**Mitigation**:
- Check if modules exist before loading
- Provide clear error message with instructions
- Offer kernel compilation instructions
- Don't block VM creation (can use software rendering)

### Risk 4: Vendor-Reset Not Available

**Issue**: AMD GPU hang on VM reset (vendor-reset would fix)

**Mitigation**:
- Try package manager installation (pacman -S vendor-reset-dkms)
- If not available, warn user but don't fail
- Document manual compilation instructions
- Some AMD GPUs (newer RDNA) don't need vendor-reset

### Risk 5: Multiple GPUs Confusion

**Issue**: System has multiple GPUs, choose wrong one for passthrough

**Mitigation**:
- Always prefer discrete GPU over integrated
- Never choose boot GPU
- Show user clearly which GPU will be used
- Offer manual override

### Risk 6: IOMMU Group Size Issues

**Issue**: Selected GPU shares IOMMU group with essential hardware

**Mitigation**:
- Check IOMMU group composition
- Warn if audio or bridges in same group
- Offer alternative GPUs
- Document limitations

---

## Next Steps

Once Phase 2.3 is complete:

1. **Phase 2.4** - Looking Glass auto-launch (needs GPU bound to VFIO)
2. **Phase 2.1** - Onboarding will complete successfully with working hardware
3. **Phase 2.2** - Users can install apps in Windows VMs with GPU support

---

## Resources

- [QEMU IOMMU Setup Guide](https://wiki.qemu.org/Features/IOMMU)
- [Intel VT-d Documentation](https://www.intel.com/content/www/us/en/developer/articles/guide/intel-virtualization-technology-directed-i-o-vt-d-enabling-iommu.html)
- [AMD IOMMU (Vi) Setup](https://wiki.archlinux.org/title/PCI_passthrough_via_IOMMU)
- [Vendor-Reset Project](https://github.com/gnif/vendor-reset)
- [VFIO Kernel Documentation](https://www.kernel.org/doc/html/latest/driver-api/vfio.html)
- [Arch Linux GPU Passthrough Guide](https://wiki.archlinux.org/title/PCI_passthrough_via_IOMMU)

---

## Questions?

If stuck:

1. Check GRUB modification is atomic and uses temp files
2. Verify CPU type detection in `/proc/cpuinfo`
3. Test VFIO module loading: `modprobe -n vfio` (dry run first)
4. For vendor-reset: `pacman -Ss vendor-reset`
5. See ARCHITECTURE.md for hardware module details

Good luck! 🚀
