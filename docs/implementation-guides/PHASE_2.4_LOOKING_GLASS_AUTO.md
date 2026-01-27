# Phase 2.4: Looking Glass Auto-Start & Display Integration

**Status**: 🟡 PARTIAL - Manager exists, auto-launch missing
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 2.3 complete (GPU passthrough working)

---

## What is Looking Glass?

**Looking Glass** is an ultra-low-latency display technology that streams Windows VM displays to the host with near-native performance:

- **IVSHMEM** (Inter-VM Shared Memory) - GPU renders directly to shared memory
- **Virtual to Host Display** - Windows runs at 60+ FPS with <1ms latency
- **No network overhead** - Direct memory access (much faster than VNC/SPICE)
- **Mouse/Keyboard pass-through** - Direct input to VM

**Without this phase**: Users must:
1. Boot Windows VM
2. Manually launch `looking-glass-client` command
3. Wait for display to appear
4. Every reboot = manual relaunching

**With this phase**: Users boot VM once, display appears automatically.

---

## Current State: Manager Exists, Integration Missing

### What Works ✅

- **LookingGlassManager** (`src/vm_manager/core/looking_glass.py` - 430 lines)
  - Detects installation (`looking-glass-client` in PATH)
  - Reads/parses config from `~/.config/neuronos/looking-glass/{vm_name}.json`
  - Starts client process with proper arguments
  - Monitors client state (STOPPED, STARTING, RUNNING, ERROR)
  - Handles config persistence
  - Graceful shutdown with timeout
  - Process detachment (doesn't block VM)

- **IVSHMEM Setup** (`src/vm_manager/passthrough/ivshmem.py` - 185 lines)
  - Creates shared memory files in `/dev/shm/`
  - Sets proper permissions (0o660)
  - Calculates appropriate sizes
  - Cleanup and existence checking

- **Configuration** - `LookingGlassConfig` dataclass with:
  - Display settings (fullscreen, borderless, window position, size)
  - Performance settings (FPS limit, V-sync)
  - Input capture (mouse, keyboard, escape key)
  - Audio settings
  - IVSHMEM device configuration

### What's Missing ❌

| Missing Piece | Impact | Workaround |
|---|---|---|
| Auto-launch on VM boot | User must manually start display | Manual command needed each reboot |
| Fallback to virt-viewer | If Looking Glass fails, users stuck | Manual virt-viewer launch |
| VM lifecycle integration | Display creation not tied to VM state | Display not cleaned up on VM stop |
| Auto-detection | Users don't know if Looking Glass available | Silent failures |
| Window management | No control after launch (fullscreen toggle needs restart) | Restart looking-glass-client manually |
| Resolution tracking | Resolution changes not detected | Manual window resize needed |
| Audio device setup | Audio not routed to host | No sound from VM |

### The Impact

**Scenario**: User creates Windows VM with GPU passthrough:
1. ✅ VM boots
2. ❌ "Looking Glass not found" (but it IS installed)
3. ❌ User must figure out how to launch it
4. ❌ Every VM reboot needs manual relaunching
5. **Reality**: Should be automatic

---

## Objective: Seamless Display Integration

After completing Phase 2.4:

1. ✅ **Auto-detect Looking Glass availability** - Check at VM creation time
2. ✅ **Auto-launch on VM boot** - Display appears automatically
3. ✅ **Fallback display** - If Looking Glass fails, use virt-viewer
4. ✅ **Lifecycle integration** - Start with VM, stop with VM
5. ✅ **Configuration persistence** - Remember user's display preferences
6. ✅ **Audio routing** - Audio streams to host (if configured)
7. ✅ **Resolution sync** - Display updates when VM resolution changes (Phase 2.5)

---

## Part 1: Enhance Looking Glass Manager

The manager exists but needs to integrate with VM lifecycle.

**File**: `src/vm_manager/core/looking_glass.py` (add these methods)

```python
"""Addition to existing LookingGlassManager class."""

class LookingGlassManager:
    """Manages Looking Glass client for VM displays."""

    def is_available(self) -> bool:
        """Check if Looking Glass client is installed and available.

        Returns:
            True if looking-glass-client found in PATH
        """
        return shutil.which("looking-glass-client") is not None

    def get_recommended_config(self, vm_name: str, vm_info: dict) -> LookingGlassConfig:
        """Get recommended config based on VM hardware.

        Args:
            vm_name: Name of the VM
            vm_info: Dict with VM info (memory, cpu_cores, etc.)

        Returns:
            Optimized LookingGlassConfig for this VM
        """
        # Base config
        config = LookingGlassConfig()

        # Adjust based on VM resources
        if vm_info.get("memory_mb", 0) >= 16000:
            # High-end gaming VM
            config.fps_limit = 144
            config.vsync = False  # High refresh gaming
            config.window_width = 2560
            config.window_height = 1440
        else:
            # Standard productivity VM
            config.fps_limit = 60
            config.vsync = True
            config.window_width = 1920
            config.window_height = 1080

        return config

    def wait_for_ivshmem(self, vm_name: str, timeout_seconds: int = 30) -> bool:
        """Wait for IVSHMEM device to appear.

        Looking Glass needs IVSHMEM device from VM before it can connect.
        This waits for the shared memory file to exist.

        Args:
            vm_name: VM name
            timeout_seconds: Max time to wait

        Returns:
            True if device appeared, False if timeout
        """
        ivshmem_path = Path(f"/dev/shm/looking-glass-{vm_name}")
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if ivshmem_path.exists():
                logger.info(f"IVSHMEM device ready: {ivshmem_path}")
                return True
            time.sleep(0.5)

        logger.warning(f"Timeout waiting for IVSHMEM device {ivshmem_path}")
        return False

    def start_with_fallback(
        self,
        vm_name: str,
        use_looking_glass: bool = True,
        use_spice_fallback: bool = True,
    ) -> Tuple[bool, str]:
        """Start display with fallback to virt-viewer if needed.

        Args:
            vm_name: VM name
            use_looking_glass: Try Looking Glass first
            use_spice_fallback: Fall back to virt-viewer if LG fails

        Returns:
            Tuple of (success: bool, display_type: str)
            success True if display started
            display_type "looking-glass" or "spice" or "none"
        """
        display_type = "none"

        if use_looking_glass and self.is_available():
            logger.info(f"Starting Looking Glass for {vm_name}...")

            # Wait for IVSHMEM device
            if not self.wait_for_ivshmem(vm_name, timeout_seconds=30):
                logger.warning("IVSHMEM not ready, trying anyway...")

            # Load config
            config = self.load_config(vm_name)

            # Start Looking Glass
            if self.start(vm_name, config):
                display_type = "looking-glass"
                logger.info("Looking Glass started successfully")
                return True, display_type

            logger.warning(f"Looking Glass failed for {vm_name}, trying fallback...")

        if use_spice_fallback:
            logger.info(f"Falling back to virt-viewer for {vm_name}...")
            if self._start_spice_viewer(vm_name):
                display_type = "spice"
                logger.info("virt-viewer started successfully")
                return True, display_type

        logger.error(f"All display options failed for {vm_name}")
        return False, "none"

    def _start_spice_viewer(self, vm_name: str) -> bool:
        """Start virt-viewer as fallback display.

        Args:
            vm_name: VM name

        Returns:
            True if process started, False otherwise
        """
        try:
            # Check if virt-viewer available
            if not shutil.which("virt-viewer"):
                logger.warning("virt-viewer not found")
                return False

            # Start virt-viewer in background (new session)
            process = subprocess.Popen(
                ["virt-viewer", "-c", "qemu:///system", vm_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            logger.info(f"virt-viewer started with PID {process.pid}")
            return True

        except Exception as e:
            logger.exception(f"Failed to start virt-viewer: {e}")
            return False

    def get_status(self, vm_name: str) -> dict:
        """Get current display status for VM.

        Returns:
            Dict with:
            - is_available: bool (LG installed)
            - is_running: bool (current process running)
            - process_id: int (PID if running)
            - display_type: str ("looking-glass", "spice", or "none")
            - uptime_seconds: int (seconds running)
            - errors: List[str]
        """
        try:
            process_running = self._state == LookingGlassState.RUNNING
            pid = self._process.pid if self._process else None

            uptime = 0
            if process_running and self._start_time:
                uptime = int(time.time() - self._start_time)

            return {
                "is_available": self.is_available(),
                "is_running": process_running,
                "process_id": pid,
                "display_type": self._get_display_type(vm_name),
                "uptime_seconds": uptime,
                "errors": self._get_recent_errors(),
            }
        except Exception as e:
            logger.exception("Failed to get Looking Glass status")
            return {"error": str(e)}

    def _get_display_type(self, vm_name: str) -> str:
        """Determine which display type is running.

        Checks process names to see if Looking Glass or virt-viewer is active.
        """
        if self._process:
            try:
                # Get process name
                process_name = self._process.name() if hasattr(self._process, "name") else ""
                if "looking-glass" in process_name.lower():
                    return "looking-glass"
                elif "virt-viewer" in process_name.lower():
                    return "spice"
            except Exception:
                pass
        return "none"

    def toggle_fullscreen(self, vm_name: str) -> bool:
        """Toggle fullscreen mode.

        Note: This requires restarting Looking Glass client.
        In future phases, we could use IPC to avoid restart.

        Returns:
            True if toggle successful, False otherwise
        """
        try:
            # Load config
            config = self.load_config(vm_name)

            # Toggle fullscreen
            config.fullscreen = not config.fullscreen

            # Save config
            self.save_config(vm_name, config)

            # Restart client
            self.stop()
            time.sleep(1)

            if self.start(vm_name, config):
                logger.info(f"Fullscreen toggled to {config.fullscreen}")
                return True
            else:
                logger.error("Failed to restart after fullscreen toggle")
                return False

        except Exception as e:
            logger.exception(f"Failed to toggle fullscreen: {e}")
            return False
```

---

## Part 2: Integrate with VM Lifecycle

When a VM starts, its display should start automatically. When VM stops, display should stop.

**File**: `src/vm_manager/core/vm_lifecycle.py` (modify VM start/stop methods)

```python
"""VM Lifecycle integration with Looking Glass display."""

class VMLifecycleManager:
    """Manages VM boot/shutdown with display integration."""

    def __init__(self):
        """Initialize with display manager."""
        from src.vm_manager.core.looking_glass import LookingGlassManager
        self.display_manager = LookingGlassManager()

    async def start_vm(self, vm_name: str, vm_config: VMConfig) -> bool:
        """Start VM and configure display.

        Args:
            vm_name: Name of VM to start
            vm_config: VM configuration

        Returns:
            True if VM started, False otherwise
        """
        try:
            logger.info(f"Starting VM: {vm_name}")

            # 1. Boot the VM via libvirt
            if not self._boot_vm_via_libvirt(vm_name):
                logger.error(f"Failed to boot {vm_name}")
                return False

            logger.info(f"VM {vm_name} booted, waiting for display...")

            # 2. Auto-start display (if configured)
            if self._should_auto_start_display(vm_config):
                # Wait for VM to fully boot
                await asyncio.sleep(5)

                # Start display with fallback
                success, display_type = self.display_manager.start_with_fallback(
                    vm_name=vm_name,
                    use_looking_glass=True,
                    use_spice_fallback=True,
                )

                if success:
                    logger.info(f"Display started ({display_type})")
                    # Store which display is being used
                    self._save_display_type(vm_name, display_type)
                else:
                    logger.warning(f"Failed to start display for {vm_name}")
                    # Non-fatal - VM still runs

            logger.info(f"VM {vm_name} started successfully")
            return True

        except Exception as e:
            logger.exception(f"Failed to start VM {vm_name}: {e}")
            return False

    async def stop_vm(self, vm_name: str, force: bool = False) -> bool:
        """Stop VM and close display.

        Args:
            vm_name: Name of VM to stop
            force: Force shutdown if graceful fails

        Returns:
            True if VM stopped, False otherwise
        """
        try:
            logger.info(f"Stopping VM: {vm_name}")

            # 1. Close display first
            try:
                self.display_manager.stop()
                logger.info(f"Display closed for {vm_name}")
            except Exception as e:
                logger.warning(f"Error closing display: {e}")

            # 2. Shut down VM gracefully
            if not force:
                logger.info("Sending ACPI shutdown signal...")
                if self._send_acpi_shutdown(vm_name):
                    # Wait for graceful shutdown (max 30 seconds)
                    if self._wait_for_shutdown(vm_name, timeout_seconds=30):
                        logger.info(f"VM {vm_name} shut down gracefully")
                        return True

            # 3. Force shutdown if graceful failed
            if force or not self._is_vm_running(vm_name):
                logger.info(f"Force stopping VM {vm_name}...")
                if self._destroy_vm(vm_name):
                    logger.info(f"VM {vm_name} destroyed")
                    return True

            logger.error(f"Failed to stop {vm_name}")
            return False

        except Exception as e:
            logger.exception(f"Failed to stop VM {vm_name}: {e}")
            return False

    def _should_auto_start_display(self, vm_config: VMConfig) -> bool:
        """Check if display should auto-start for this VM.

        Returns True if:
        - Looking Glass capable hardware available
        - Looking Glass is installed
        - VM configured with GPU passthrough
        - User enabled auto-display
        """
        # GPU passthrough implies Looking Glass
        if vm_config.gpu_passthrough:
            # Check if installed
            return self.display_manager.is_available()
        return False

    def _save_display_type(self, vm_name: str, display_type: str) -> None:
        """Save which display type is active for this VM."""
        config_dir = Path.home() / ".config/neuronos"
        config_dir.mkdir(parents=True, exist_ok=True)

        display_file = config_dir / f"{vm_name}.display"
        display_file.write_text(display_type)

    def _get_saved_display_type(self, vm_name: str) -> str:
        """Get which display type was saved for this VM."""
        display_file = Path.home() / ".config/neuronos" / f"{vm_name}.display"
        if display_file.exists():
            return display_file.read_text().strip()
        return "none"

    # Helper methods (use existing libvirt manager)
    def _boot_vm_via_libvirt(self, vm_name: str) -> bool:
        """Boot VM using libvirt."""
        # Implementation would use existing libvirt code
        pass

    def _send_acpi_shutdown(self, vm_name: str) -> bool:
        """Send ACPI shutdown signal to VM."""
        pass

    def _wait_for_shutdown(self, vm_name: str, timeout_seconds: int) -> bool:
        """Wait for VM to shut down."""
        pass

    def _is_vm_running(self, vm_name: str) -> bool:
        """Check if VM is currently running."""
        pass

    def _destroy_vm(self, vm_name: str) -> bool:
        """Force destroy running VM."""
        pass
```

---

## Part 3: Auto-Launch Display from GUI

When user clicks "Start" or "Open Display" button, auto-launch with fallback.

**File**: `src/vm_manager/gui/app.py` (modify button handler)

```python
"""GUI integration for display auto-launch."""

class VMManagerWindow(Adw.ApplicationWindow):
    """Main VM Manager window."""

    async def on_open_display_clicked(self, vm_name: str) -> None:
        """User clicked 'Open Display' button."""
        try:
            # Create progress dialog
            progress = self._create_progress_dialog("Opening display...")
            progress.show()

            # Get display manager
            from src.vm_manager.core.looking_glass import LookingGlassManager
            display_manager = LookingGlassManager()

            # Try Looking Glass first, fall back to virt-viewer
            success, display_type = display_manager.start_with_fallback(
                vm_name=vm_name,
                use_looking_glass=True,
                use_spice_fallback=True,
            )

            progress.close()

            if success:
                self._show_info(
                    f"Display opened ({display_type})",
                    f"Displaying {vm_name} using {display_type}"
                )
                # Update button state
                self._update_vm_card(vm_name)
            else:
                self._show_error(
                    "Display failed",
                    f"Could not open display for {vm_name}.\n\n"
                    "Make sure Looking Glass is installed and IVSHMEM is configured."
                )

        except Exception as e:
            logger.exception("Failed to open display")
            self._show_error("Error", f"Display error: {str(e)}")

    async def on_start_vm_clicked(self, vm_name: str) -> None:
        """User clicked 'Start' button."""
        try:
            progress = self._create_progress_dialog(f"Starting {vm_name}...")
            progress.show()

            # Get VM config
            vm_config = self._load_vm_config(vm_name)

            # Start VM and display
            from src.vm_manager.core.vm_lifecycle import VMLifecycleManager
            lifecycle = VMLifecycleManager()
            success = await lifecycle.start_vm(vm_name, vm_config)

            progress.close()

            if success:
                # Update UI
                self._update_vm_card(vm_name)
                self._show_notification(f"{vm_name} started")
            else:
                self._show_error("Start failed", f"Failed to start {vm_name}")

        except Exception as e:
            logger.exception("Failed to start VM")
            self._show_error("Error", str(e))

    def _create_progress_dialog(self, message: str) -> Gtk.MessageDialog:
        """Create progress dialog with spinner."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.OTHER,
            buttons=Gtk.ButtonsType.NONE,
            text=message,
        )
        # Add spinner
        box = dialog.get_message_area()
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        box.append(spinner)
        return dialog
```

---

## Part 4: Auto-detect and Inform User

On first launch, check if Looking Glass is available and inform user.

**File**: `src/vm_manager/core/hardware_setup.py` (add to HardwareSetupResult)

```python
@dataclass
class HardwareSetupResult:
    """Result of hardware setup."""
    # ... existing fields ...

    # NEW: Display capability
    looking_glass_available: bool = False
    looking_glass_recommended: bool = False
    display_warning: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result_dict = {
            # ... existing dict items ...

            # NEW: Display info
            "looking_glass_available": self.looking_glass_available,
            "looking_glass_recommended": self.looking_glass_recommended,
            "display_warning": self.display_warning,
        }
        return result_dict
```

**Add to HardwareSetupManager.__init__**:
```python
def __init__(self):
    """Initialize hardware setup manager."""
    # ... existing init code ...

    from src.vm_manager.core.looking_glass import LookingGlassManager
    self.looking_glass_manager = LookingGlassManager()

def auto_detect_and_setup(self, ...) -> HardwareSetupResult:
    """Auto-detect hardware and set everything up."""
    result = HardwareSetupResult(...)

    # ... existing setup code ...

    # Check Looking Glass availability
    result.looking_glass_available = self.looking_glass_manager.is_available()

    if result.selected_gpu and not result.looking_glass_available:
        result.looking_glass_recommended = True
        result.display_warning = (
            "Looking Glass not found. Install it for ultra-low-latency display:\n"
            "sudo pacman -S looking-glass\n\n"
            "Without it, VMs will use slower SPICE protocol."
        )

    return result
```

---

## Part 5: Testing Display Integration

Create comprehensive tests for Looking Glass integration.

**File**: `tests/test_looking_glass_integration.py`

```python
"""Tests for Looking Glass auto-launch integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
import asyncio

from src.vm_manager.core.looking_glass import LookingGlassManager
from src.vm_manager.core.vm_lifecycle import VMLifecycleManager
from src.vm_manager.core.vm_config import VMConfig


@pytest.fixture
def display_manager():
    """Create Looking Glass manager."""
    return LookingGlassManager()


@pytest.fixture
def lifecycle_manager():
    """Create VM lifecycle manager."""
    return VMLifecycleManager()


def test_is_available_when_installed(display_manager):
    """Test detecting Looking Glass installation."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/looking-glass-client"
        assert display_manager.is_available() is True


def test_is_available_when_not_installed(display_manager):
    """Test when Looking Glass not installed."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None
        assert display_manager.is_available() is False


@patch("time.time")
@patch("pathlib.Path.exists")
def test_wait_for_ivshmem_success(mock_exists, mock_time, display_manager):
    """Test successful IVSHMEM device detection."""
    # Device appears after 1 second
    mock_time.side_effect = [0, 0.5, 1.0]  # time.time() calls
    mock_exists.side_effect = [False, True]  # exists() calls

    result = display_manager.wait_for_ivshmem("TestVM", timeout_seconds=5)

    assert result is True
    assert mock_exists.call_count == 2


@patch("time.time")
@patch("pathlib.Path.exists")
def test_wait_for_ivshmem_timeout(mock_exists, mock_time, display_manager):
    """Test IVSHMEM timeout."""
    # Device never appears, timeout after 2 seconds
    mock_time.side_effect = [0, 0.5, 1.0, 1.5, 2.0, 2.5]
    mock_exists.return_value = False

    result = display_manager.wait_for_ivshmem("TestVM", timeout_seconds=2)

    assert result is False


@patch.object(LookingGlassManager, "is_available", return_value=True)
@patch.object(LookingGlassManager, "wait_for_ivshmem", return_value=True)
@patch.object(LookingGlassManager, "start", return_value=True)
@patch.object(LookingGlassManager, "load_config")
def test_start_with_fallback_looking_glass_success(
    mock_load_config, mock_start, mock_wait, mock_available, display_manager
):
    """Test successful Looking Glass startup."""
    mock_load_config.return_value = Mock()

    success, display_type = display_manager.start_with_fallback(
        "TestVM",
        use_looking_glass=True,
        use_spice_fallback=True,
    )

    assert success is True
    assert display_type == "looking-glass"
    mock_start.assert_called_once()


@patch.object(LookingGlassManager, "is_available", return_value=False)
@patch.object(LookingGlassManager, "_start_spice_viewer", return_value=True)
def test_start_with_fallback_spice(
    mock_spice, mock_available, display_manager
):
    """Test fallback to SPICE/virt-viewer."""
    success, display_type = display_manager.start_with_fallback(
        "TestVM",
        use_looking_glass=False,
        use_spice_fallback=True,
    )

    assert success is True
    assert display_type == "spice"
    mock_spice.assert_called_once_with("TestVM")


@patch("shutil.which", return_value="/usr/bin/virt-viewer")
@patch("subprocess.Popen")
def test_start_spice_viewer(mock_popen, mock_which, display_manager):
    """Test virt-viewer startup."""
    mock_process = Mock()
    mock_process.pid = 12345
    mock_popen.return_value = mock_process

    result = display_manager._start_spice_viewer("TestVM")

    assert result is True
    mock_popen.assert_called_once()
    call_args = mock_popen.call_args
    assert "virt-viewer" in call_args[0][0]
    assert "TestVM" in call_args[0][0]


def test_get_recommended_config_high_end(display_manager):
    """Test config for high-end gaming VM."""
    vm_info = {"memory_mb": 20000, "cpu_cores": 8}
    config = display_manager.get_recommended_config("GamingVM", vm_info)

    assert config.fps_limit == 144
    assert config.vsync is False
    assert config.window_width == 2560


def test_get_recommended_config_productivity(display_manager):
    """Test config for productivity VM."""
    vm_info = {"memory_mb": 8000, "cpu_cores": 4}
    config = display_manager.get_recommended_config("WorkVM", vm_info)

    assert config.fps_limit == 60
    assert config.vsync is True
    assert config.window_width == 1920


@patch.object(LookingGlassManager, "_process", None)
def test_get_status_not_running(display_manager):
    """Test status when display not running."""
    status = display_manager.get_status("TestVM")

    assert status["is_running"] is False
    assert status["process_id"] is None
    assert status["uptime_seconds"] == 0


@patch.object(VMLifecycleManager, "_boot_vm_via_libvirt", return_value=True)
@patch.object(VMLifecycleManager, "_should_auto_start_display", return_value=True)
@patch.object(LookingGlassManager, "start_with_fallback")
def test_start_vm_with_display(mock_fallback, mock_should_start, mock_boot):
    """Test VM start with display auto-launch."""
    mock_fallback.return_value = (True, "looking-glass")

    vm_config = Mock(gpu_passthrough=True)
    lifecycle = VMLifecycleManager()

    result = asyncio.run(lifecycle.start_vm("TestVM", vm_config))

    # Note: This would need proper async/await setup in real test
    # Simplified for example


# Run tests: pytest tests/test_looking_glass_integration.py -v
```

**Run tests**:
```bash
pytest tests/test_looking_glass_integration.py -v
```

---

## Part 6: Configuration UI for Display Settings

Add UI to configure Looking Glass preferences.

**File**: `src/vm_manager/gui/displays.py` (new file)

```python
"""Display configuration UI."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adwaita", "1")

from gi.repository import Gtk, Adwaita
from pathlib import Path
from src.vm_manager.core.looking_glass import LookingGlassManager, LookingGlassConfig


class DisplaySettingsDialog(Adwaita.Window):
    """Dialog for configuring display settings."""

    def __init__(self, parent, vm_name: str):
        """Initialize display settings dialog."""
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 600)
        self.set_title(f"Display Settings - {vm_name}")

        self.vm_name = vm_name
        self.display_manager = LookingGlassManager()

        # Load current config
        self.config = self.display_manager.load_config(vm_name)

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the settings UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # Title
        title = Gtk.Label()
        title.set_markup("<b>Display Configuration</b>")
        title.set_halign(Gtk.Align.START)
        box.append(title)

        # Display mode group
        mode_group = Adwaita.PreferencesGroup()
        mode_group.set_title("Display Mode")

        self.fullscreen_switch = Gtk.Switch()
        self.fullscreen_switch.set_active(self.config.fullscreen)
        mode_group.add(self._create_row("Fullscreen", self.fullscreen_switch))

        self.borderless_switch = Gtk.Switch()
        self.borderless_switch.set_active(self.config.borderless)
        mode_group.add(self._create_row("Borderless", self.borderless_switch))

        box.append(mode_group)

        # Performance group
        perf_group = Adwaita.PreferencesGroup()
        perf_group.set_title("Performance")

        self.fps_spin = Gtk.SpinButton()
        self.fps_spin.set_range(30, 240)
        self.fps_spin.set_increments(5, 10)
        self.fps_spin.set_value(self.config.fps_limit)
        perf_group.add(self._create_row("FPS Limit", self.fps_spin))

        self.vsync_switch = Gtk.Switch()
        self.vsync_switch.set_active(self.config.vsync)
        perf_group.add(self._create_row("V-Sync", self.vsync_switch))

        box.append(perf_group)

        # Input group
        input_group = Adwaita.PreferencesGroup()
        input_group.set_title("Input")

        self.mouse_switch = Gtk.Switch()
        self.mouse_switch.set_active(self.config.capture_mouse)
        input_group.add(self._create_row("Capture Mouse", self.mouse_switch))

        self.keyboard_switch = Gtk.Switch()
        self.keyboard_switch.set_active(self.config.capture_keyboard)
        input_group.add(self._create_row("Capture Keyboard", self.keyboard_switch))

        box.append(input_group)

        # Buttons
        button_box = Gtk.Box(spacing=6)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        button_box.append(apply_btn)

        box.append(button_box)

        # Add scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(box)
        self.set_content(scroll)

    def _create_row(self, label_text: str, control: Gtk.Widget) -> Gtk.Box:
        """Create a settings row."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(6)
        row.set_margin_bottom(6)

        label = Gtk.Label(label=label_text)
        label.set_hexpand(True)
        label.set_halign(Gtk.Align.START)
        row.append(label)

        control.set_halign(Gtk.Align.END)
        row.append(control)

        return row

    def _on_apply(self, button: Gtk.Button) -> None:
        """Apply settings."""
        # Update config from UI
        self.config.fullscreen = self.fullscreen_switch.get_active()
        self.config.borderless = self.borderless_switch.get_active()
        self.config.fps_limit = int(self.fps_spin.get_value())
        self.config.vsync = self.vsync_switch.get_active()
        self.config.capture_mouse = self.mouse_switch.get_active()
        self.config.capture_keyboard = self.keyboard_switch.get_active()

        # Save config
        self.display_manager.save_config(self.vm_name, self.config)

        # Show notification
        # (Would use app notification system)

        self.close()
```

---

## Verification Checklist

Before moving to Phase 2.5, verify ALL of these:

**Display Detection:**
- [ ] `LookingGlassManager.is_available()` correctly detects installation
- [ ] Display settings load from config file
- [ ] Display settings save to config file
- [ ] Recommended config generated for different VM types

**Auto-Launch:**
- [ ] `wait_for_ivshmem()` detects shared memory device
- [ ] `start_with_fallback()` launches Looking Glass first
- [ ] Falls back to virt-viewer if Looking Glass fails
- [ ] Display starts without manual intervention
- [ ] Both display types report correct status

**Lifecycle Integration:**
- [ ] `start_vm()` calls `start_with_fallback()`
- [ ] Display starts ~5 seconds after VM boots
- [ ] `stop_vm()` closes display before stopping VM
- [ ] Display properly cleaned up on VM stop
- [ ] No orphaned display processes left running

**GUI Integration:**
- [ ] "Open Display" button works
- [ ] "Start VM" button starts both VM and display
- [ ] Display settings dialog loads current config
- [ ] Display settings can be modified and saved
- [ ] Progress dialog shown during display startup

**Testing:**
- [ ] All unit tests pass: `pytest tests/test_looking_glass_integration.py -v`
- [ ] Display detection tested
- [ ] IVSHMEM wait tested
- [ ] Fallback logic tested
- [ ] Config load/save tested

---

## Acceptance Criteria

✅ **Phase 2.4 Complete When**:

1. Looking Glass auto-detects and launches on VM boot
2. Fallback to virt-viewer if Looking Glass unavailable
3. Display integrates with VM lifecycle (start/stop)
4. Display settings configurable via GUI
5. Multiple display modes supported (Looking Glass, SPICE, none)
6. Config persists across reboots
7. Clear error messages if display fails
8. All tests pass
9. No manual intervention needed to see VM display
10. Users see display within 10 seconds of VM boot

❌ **Phase 2.4 Fails If**:

- Looking Glass not detected even when installed
- Display doesn't auto-launch on VM boot
- Fallback doesn't work if Looking Glass unavailable
- Display hangs and blocks VM
- Config not saved/restored
- Tests fail
- IVSHMEM not detected properly

---

## Risks & Mitigations

### Risk 1: IVSHMEM Device Not Ready

**Issue**: Looking Glass client starts before IVSHMEM device created by VM

**Mitigation**:
- Wait up to 30 seconds for `/dev/shm/looking-glass-{vm_name}`
- Add exponential backoff (0.5s sleep between checks)
- Log detailed timing for debugging

### Risk 2: Looking Glass Crashes on Startup

**Issue**: Client crashes, user sees blank screen

**Mitigation**:
- Catch process errors and fall back to virt-viewer
- Monitor process after startup (first 5 seconds)
- Log stderr output for debugging
- Suggest re-installing Looking Glass

### Risk 3: Multiple Display Clients Conflict

**Issue**: User manually launches Looking Glass while auto-launch running

**Mitigation**:
- Check if process already running before starting
- Only allow one display per VM
- Provide UI to close existing display first

### Risk 4: Virt-Viewer Fallback Too Slow

**Issue**: Fallback to SPICE adds latency, users think system is broken

**Mitigation**:
- Show notification which display type is active
- Recommend installing Looking Glass
- Performance comparison in docs

### Risk 5: Audio Device Setup Missing

**Issue**: GPU works but no sound from VM

**Mitigation**:
- Document audio device passthrough separately (Phase 3.x)
- Set audio config in `LookingGlassConfig`
- Note: Audio requires separate pulseaudio/alsa setup

### Risk 6: Window Manager Conflicts

**Issue**: Looking Glass window not shown (X11/Wayland incompatibility)

**Mitigation**:
- Test on both X11 and Wayland
- Fallback to virt-viewer (works better on Wayland)
- Document known issues

---

## Next Steps

Once Phase 2.4 is complete:

1. **Phase 2.5** - Proton installer and app management
2. **Phase 3.x** - Audio/input device passthrough
3. **Phase 4.x** - Performance optimization and testing

---

## Resources

- [Looking Glass Project](https://looking-glass.io/)
- [IVSHMEM Device Documentation](https://wiki.qemu.org/Features/ivshmem)
- [virt-viewer Documentation](https://virt-manager.org/)
- [QEMU Display Options](https://qemu.readthedocs.io/en/latest/system/qemu-manpage.html)
- [Latency Testing Guide](https://wiki.archlinux.org/title/PCI_passthrough_via_IOMMU#Benchmarking_performance)

---

## Questions?

If stuck:

1. Check IVSHMEM device exists: `ls -la /dev/shm/looking-glass-*`
2. Verify Looking Glass installed: `which looking-glass-client`
3. Test manual start: `looking-glass-client -h` (shows help)
4. Check virt-viewer: `which virt-viewer`
5. See ARCHITECTURE.md for display module details

Good luck! 🚀
