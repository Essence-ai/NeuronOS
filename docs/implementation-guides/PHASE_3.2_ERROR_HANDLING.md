# Phase 3.2: User-Friendly Error Handling & Recovery

**Status**: 🟡 PARTIAL - Exception hierarchy exists, GUI integration missing
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 3.1 (Settings UI for recovery actions), existing exception system

---

## What is User-Friendly Error Handling?

Error handling is the difference between **a confused user** who gives up and **a successful user** who resolves issues. Consider these scenarios:

### Scenario 1: Current (Bad) Error Handling
```
[ERROR] Exception: 'NoneType' object has no attribute 'XMLDesc'
Traceback (most recent call last):
  File "vm_lifecycle.py", line 142, in start_vm
    ...
```
**User reaction**: "What does XMLDesc mean? Is my VM broken? Should I reinstall NeuronOS?"

### Scenario 2: Production (Good) Error Handling
```
┌─────────────────────────────────────────┐
│  Cannot Start VM                        │
├─────────────────────────────────────────┤
│  The VM "Windows11" failed to start     │
│  because it was not found.              │
│                                          │
│  Possible causes:                       │
│  • VM was deleted or renamed            │
│  • Libvirt connection failed            │
│                                          │
│  Recovery options:                      │
│  1. Click "Refresh" to update VM list   │
│  2. Recreate VM from onboarding         │
│                                          │
│  [View Details] [Refresh] [Close]       │
└─────────────────────────────────────────┘
```
**User reaction**: "Ah, I need to refresh. That makes sense."

**The problem**: We have a solid exception hierarchy (`src/common/exceptions.py`) but no GUI integration. Users see Python tracebacks instead of helpful dialogs.

---

## Current State: Strong Foundation, Missing UI

### What Already Works ✅

**File**: `src/common/exceptions.py` (307 lines)

We have:
- ✅ Structured exception hierarchy (`NeuronError` base class)
- ✅ Error codes (`VM_NOT_FOUND`, `IOMMU_ERROR`, etc.)
- ✅ Details dict for context (PCI addresses, VM names)
- ✅ Recoverable flag (can user fix this?)
- ✅ Cause chaining (show original exception)
- ✅ JSON serialization (`to_dict()`)

Example exceptions:
```python
class VMNotFoundError(VMError):
    """VM does not exist."""
    def __init__(self, vm_name: str):
        super().__init__(
            f"Virtual machine '{vm_name}' not found",
            code="VM_NOT_FOUND",
            details={"vm_name": vm_name},
            recoverable=False,
        )

class IOMMUError(HardwareError):
    """IOMMU not properly configured."""
    def __init__(self, message: str = "IOMMU not enabled"):
        super().__init__(
            f"{message}. Enable IOMMU in BIOS and add kernel parameters.",
            code="IOMMU_ERROR",
            details={
                "intel_param": "intel_iommu=on iommu=pt",
                "amd_param": "amd_iommu=on iommu=pt",
            },
            recoverable=False,
        )
```

### What's Missing ❌

| Missing Feature | Impact | User Experience |
|---|---|---|
| **Error dialog system** | Users see terminal errors, not GUI | "I saw red text flash by. Is it broken?" |
| **Recovery suggestions** | No guidance on how to fix | "IOMMU error... what's IOMMU? How do I fix it?" |
| **Error translation** | Technical jargon shown directly | "'VFIO bind failed' - what does that mean?" |
| **Logging integration** | Errors not logged with context | Support team: "Can you check the logs?" User: "What logs?" |
| **Error reporting** | No way to submit bug reports | User can't help developers debug |
| **Retry mechanisms** | Transient failures = permanent failure | "Download failed once, now I'm stuck" |
| **Contextual help** | No links to documentation | User must Google error codes |

### The Impact

**Scenario**: John, a non-technical user, tries to create a Windows VM:

1. ✅ Opens onboarding wizard
2. ✅ Clicks "Create Windows VM"
3. ❌ IOMMU not enabled in BIOS
4. ❌ **Current**: Terminal shows:
   ```
   [IOMMU_ERROR] IOMMU not enabled. Enable IOMMU in BIOS and add kernel parameters.
   Details: {'intel_param': 'intel_iommu=on iommu=pt', 'amd_param': 'amd_iommu=on iommu=pt'}
   ```
5. ❌ John sees this in a small terminal window, doesn't know what BIOS is
6. ❌ John gives up on NeuronOS

**Desired behavior**:
1. ✅ Large, clear dialog: "GPU Passthrough Not Available"
2. ✅ Explanation: "Your CPU supports virtualization, but a required feature (IOMMU) is not enabled."
3. ✅ Step-by-step recovery:
   - "1. Restart your computer"
   - "2. Press DEL or F2 to enter BIOS"
   - "3. Find 'Virtualization' settings"
   - "4. Enable 'Intel VT-d' or 'AMD-Vi'"
   - "5. Save and reboot"
4. ✅ Fallback: "Or continue without GPU passthrough (slower graphics)"
5. ✅ John successfully enables IOMMU and creates VM

---

## Objective: Production-Quality Error UX

After completing Phase 3.2:

1. ✅ **Error Dialog System** - All exceptions show GUI dialogs, not terminal text
2. ✅ **Recovery Wizard** - Step-by-step fix instructions for common errors
3. ✅ **Smart Retries** - Automatically retry transient failures (network, libvirt connection)
4. ✅ **Contextual Help** - Link to docs, show related settings
5. ✅ **Error Logging** - All errors logged to `~/.local/share/neuronos/logs/errors.log` with context
6. ✅ **Error Reporting** - "Report Bug" button prepopulates GitHub issue
7. ✅ **Error Analytics** - Track which errors happen most (opt-in telemetry)
8. ✅ **Developer Mode** - Show full tracebacks for advanced users
9. ✅ **Error Translations** - Technical errors → plain English

---

## Part 1: Error Dialog System

Create a centralized error display system that converts exceptions to GTK dialogs.

### 1.1: Error Dialog Manager

**File**: `src/common/error_handler.py` (new file)

```python
"""
Centralized error handling for NeuronOS.

Converts exceptions to user-friendly GUI dialogs with:
- Plain English explanations
- Recovery suggestions
- Contextual help links
- Error logging
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

import logging
import traceback
from pathlib import Path
from typing import Optional, List, Callable
from dataclasses import dataclass

from src.common.exceptions import (
    NeuronError,
    VMNotFoundError,
    VMStartError,
    VMCreationError,
    GPUNotFoundError,
    IOMMUError,
    VFIOError,
    DependencyError,
    DownloadError,
    LibvirtConnectionError,
)

logger = logging.getLogger(__name__)


@dataclass
class RecoveryAction:
    """A suggested recovery action."""
    label: str              # Button text: "Enable IOMMU"
    description: str        # What this does: "Opens BIOS settings guide"
    callback: Callable      # Function to run when clicked
    primary: bool = False   # Highlight as primary action


@dataclass
class ErrorContext:
    """Extended error information for display."""
    title: str                          # Dialog title
    message: str                        # User-friendly message
    technical_details: Optional[str]    # For "Show Details"
    recovery_actions: List[RecoveryAction]
    help_url: Optional[str]             # Link to docs
    error_code: str                     # For support
    is_fatal: bool                      # Can user continue?


class ErrorHandler:
    """
    Global error handler for NeuronOS.

    Usage:
        try:
            vm_manager.start_vm("Windows11")
        except Exception as e:
            ErrorHandler.show_error(e, parent=main_window)
    """

    # Map exception types to user-friendly contexts
    ERROR_MAP = {
        VMNotFoundError: lambda e: ErrorContext(
            title="Virtual Machine Not Found",
            message=f"The VM '{e.details.get('vm_name')}' could not be found.\n\n"
                    f"It may have been deleted, or the libvirt connection may have failed.",
            technical_details=str(e),
            recovery_actions=[
                RecoveryAction(
                    label="Refresh VM List",
                    description="Check if VM reappears",
                    callback=lambda: ErrorHandler._refresh_vm_list(),
                    primary=True
                ),
                RecoveryAction(
                    label="Recreate VM",
                    description="Start onboarding wizard",
                    callback=lambda: ErrorHandler._open_onboarding(),
                ),
            ],
            help_url="https://docs.neuronos.org/troubleshooting/vm-not-found",
            error_code=e.code,
            is_fatal=False,
        ),

        IOMMUError: lambda e: ErrorContext(
            title="GPU Passthrough Not Available",
            message="IOMMU (Input-Output Memory Management Unit) is not enabled.\n\n"
                    "This is required for GPU passthrough. Your CPU supports it, but it needs to be enabled in BIOS.",
            technical_details=f"{e.message}\n\nKernel parameters needed:\n"
                             f"Intel: {e.details.get('intel_param')}\n"
                             f"AMD: {e.details.get('amd_param')}",
            recovery_actions=[
                RecoveryAction(
                    label="Enable IOMMU (Guide)",
                    description="Step-by-step BIOS instructions",
                    callback=lambda: ErrorHandler._open_iommu_guide(),
                    primary=True
                ),
                RecoveryAction(
                    label="Continue Without GPU",
                    description="Use software rendering (slower)",
                    callback=lambda: ErrorHandler._disable_gpu_passthrough(),
                ),
            ],
            help_url="https://docs.neuronos.org/gpu-passthrough/enable-iommu",
            error_code=e.code,
            is_fatal=False,
        ),

        VFIOError: lambda e: ErrorContext(
            title="GPU Binding Failed",
            message=f"Failed to bind GPU ({e.details.get('pci_address')}) to VFIO driver.\n\n"
                    f"Reason: {e.details.get('reason')}\n\n"
                    f"This usually happens if the GPU is in use by the display.",
            technical_details=str(e),
            recovery_actions=[
                RecoveryAction(
                    label="Select Different GPU",
                    description="Use another GPU for passthrough",
                    callback=lambda: ErrorHandler._open_gpu_selector(),
                    primary=True
                ),
                RecoveryAction(
                    label="View IOMMU Groups",
                    description="Check GPU isolation",
                    callback=lambda: ErrorHandler._show_iommu_groups(),
                ),
            ],
            help_url="https://docs.neuronos.org/gpu-passthrough/vfio-bind-failed",
            error_code=e.code,
            is_fatal=False,
        ),

        DownloadError: lambda e: ErrorContext(
            title="Download Failed",
            message=f"Failed to download a required file.\n\n"
                    f"Reason: {e.details.get('reason')}\n\n"
                    f"This might be a temporary network issue.",
            technical_details=f"URL: {e.details.get('url')}\n{str(e)}",
            recovery_actions=[
                RecoveryAction(
                    label="Retry Download",
                    description="Try downloading again",
                    callback=lambda: ErrorHandler._retry_download(e.details.get('url')),
                    primary=True
                ),
                RecoveryAction(
                    label="Check Network",
                    description="Open network settings",
                    callback=lambda: ErrorHandler._open_network_settings(),
                ),
            ],
            help_url="https://docs.neuronos.org/troubleshooting/download-failed",
            error_code=e.code,
            is_fatal=False,
        ),

        LibvirtConnectionError: lambda e: ErrorContext(
            title="Cannot Connect to Virtualization Service",
            message="NeuronOS uses libvirt to manage virtual machines, but the connection failed.\n\n"
                    "This usually means the libvirtd service is not running.",
            technical_details=f"URI: {e.details.get('uri')}\n{str(e)}",
            recovery_actions=[
                RecoveryAction(
                    label="Start libvirtd",
                    description="Restart virtualization service",
                    callback=lambda: ErrorHandler._start_libvirtd(),
                    primary=True
                ),
                RecoveryAction(
                    label="Check Service Status",
                    description="Open system services",
                    callback=lambda: ErrorHandler._check_systemd(),
                ),
            ],
            help_url="https://docs.neuronos.org/troubleshooting/libvirt-connection",
            error_code=e.code,
            is_fatal=True,
        ),
    }

    @classmethod
    def show_error(
        cls,
        error: Exception,
        parent: Optional[Gtk.Window] = None,
        blocking: bool = True
    ) -> None:
        """
        Display user-friendly error dialog.

        Args:
            error: Exception that occurred
            parent: Parent window for modal dialog
            blocking: If True, wait for user response
        """
        # Log error with full traceback
        logger.error(f"Error occurred: {error}", exc_info=True)

        # Get error context
        context = cls._get_error_context(error)

        # Create dialog
        dialog = cls._create_error_dialog(context, parent)

        # Show dialog
        if blocking:
            dialog.present()
        else:
            dialog.show()

    @classmethod
    def _get_error_context(cls, error: Exception) -> ErrorContext:
        """Convert exception to error context."""
        # Check if we have a custom mapping
        for exc_type, mapper in cls.ERROR_MAP.items():
            if isinstance(error, exc_type):
                return mapper(error)

        # Generic NeuronError
        if isinstance(error, NeuronError):
            return ErrorContext(
                title="Operation Failed",
                message=error.message,
                technical_details=str(error),
                recovery_actions=[],
                help_url=None,
                error_code=error.code,
                is_fatal=not error.recoverable,
            )

        # Unknown exception
        return ErrorContext(
            title="Unexpected Error",
            message="An unexpected error occurred. This may be a bug in NeuronOS.",
            technical_details=f"{type(error).__name__}: {str(error)}\n\n{traceback.format_exc()}",
            recovery_actions=[
                RecoveryAction(
                    label="Report Bug",
                    description="Open GitHub issue",
                    callback=lambda: cls._report_bug(error),
                    primary=True
                ),
            ],
            help_url="https://github.com/neuronos/neuronos/issues",
            error_code="UNKNOWN_ERROR",
            is_fatal=False,
        )

    @classmethod
    def _create_error_dialog(
        cls,
        context: ErrorContext,
        parent: Optional[Gtk.Window]
    ) -> Adw.MessageDialog:
        """Create GTK error dialog from context."""
        dialog = Adw.MessageDialog(
            transient_for=parent,
            modal=True,
            heading=context.title,
            body=context.message
        )

        # Add "Show Details" button if we have technical details
        if context.technical_details:
            dialog.set_body_use_markup(False)
            dialog.add_response("details", "Show Details")

        # Add recovery actions
        for action in context.recovery_actions:
            dialog.add_response(action.label.lower().replace(" ", "_"), action.label)
            if action.primary:
                dialog.set_response_appearance(
                    action.label.lower().replace(" ", "_"),
                    Adw.ResponseAppearance.SUGGESTED
                )

        # Add "Help" button if we have docs URL
        if context.help_url:
            dialog.add_response("help", "Help")

        # Add "Close" button
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")

        # Connect response handler
        dialog.connect("response", cls._on_dialog_response, context)

        return dialog

    @classmethod
    def _on_dialog_response(
        cls,
        dialog: Adw.MessageDialog,
        response: str,
        context: ErrorContext
    ):
        """Handle dialog button clicks."""
        if response == "details":
            cls._show_technical_details(context, dialog)
        elif response == "help":
            cls._open_url(context.help_url)
        else:
            # Find and execute recovery action
            for action in context.recovery_actions:
                if action.label.lower().replace(" ", "_") == response:
                    try:
                        action.callback()
                    except Exception as e:
                        logger.exception(f"Recovery action failed: {action.label}")
                        cls.show_error(e, parent=dialog.get_transient_for())

        dialog.close()

    @classmethod
    def _show_technical_details(cls, context: ErrorContext, parent: Gtk.Widget):
        """Show technical error details in expandable view."""
        details_dialog = Adw.MessageDialog(
            transient_for=parent.get_transient_for(),
            modal=True,
            heading="Technical Details",
            body=context.technical_details
        )
        details_dialog.add_response("copy", "Copy to Clipboard")
        details_dialog.add_response("close", "Close")
        details_dialog.present()

    @classmethod
    def _open_url(cls, url: str):
        """Open URL in default browser."""
        import webbrowser
        webbrowser.open(url)

    # =========================================================================
    # Recovery action implementations
    # =========================================================================

    @staticmethod
    def _refresh_vm_list():
        """Refresh VM list in main window."""
        # TODO: Implement - call main window's refresh method
        logger.info("Refreshing VM list")

    @staticmethod
    def _open_onboarding():
        """Open onboarding wizard."""
        # TODO: Implement - launch onboarding
        logger.info("Opening onboarding wizard")

    @staticmethod
    def _open_iommu_guide():
        """Open IOMMU enable guide."""
        ErrorHandler._open_url("https://docs.neuronos.org/gpu-passthrough/enable-iommu")

    @staticmethod
    def _disable_gpu_passthrough():
        """Disable GPU passthrough and continue with software rendering."""
        # TODO: Implement - modify VM config to disable GPU
        logger.info("Disabling GPU passthrough")

    @staticmethod
    def _open_gpu_selector():
        """Open GPU selection dialog."""
        # TODO: Implement - show GPU picker
        logger.info("Opening GPU selector")

    @staticmethod
    def _show_iommu_groups():
        """Show IOMMU groups inspection dialog."""
        # TODO: Implement - display IOMMU group viewer
        logger.info("Showing IOMMU groups")

    @staticmethod
    def _retry_download(url: str):
        """Retry failed download."""
        # TODO: Implement - restart download
        logger.info(f"Retrying download: {url}")

    @staticmethod
    def _open_network_settings():
        """Open system network settings."""
        import subprocess
        subprocess.Popen(["nm-connection-editor"])

    @staticmethod
    def _start_libvirtd():
        """Start libvirtd service."""
        import subprocess
        try:
            subprocess.run(["systemctl", "start", "libvirtd"], check=True)
            logger.info("Started libvirtd service")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start libvirtd: {e}")

    @staticmethod
    def _check_systemd():
        """Open systemd service manager."""
        import subprocess
        subprocess.Popen(["systemctl", "status", "libvirtd"])

    @staticmethod
    def _report_bug(error: Exception):
        """Open GitHub issue with pre-filled bug report."""
        import webbrowser
        import urllib.parse

        title = f"Bug: {type(error).__name__}"
        body = f"""
## Bug Report

**Error Type**: `{type(error).__name__}`
**Message**: {str(error)}

**Traceback**:
```
{traceback.format_exc()}
```

**System Info**:
- NeuronOS Version: [TODO: Get from version.py]
- Kernel: {open('/proc/version').read().strip()}

**Steps to Reproduce**:
1. [Please fill in]
2.
3.

**Expected Behavior**:
[What should have happened]

**Actual Behavior**:
[What actually happened]
"""
        url = f"https://github.com/neuronos/neuronos/issues/new?title={urllib.parse.quote(title)}&body={urllib.parse.quote(body)}"
        webbrowser.open(url)
```

---

## Part 2: Smart Retry Logic

Handle transient failures automatically.

**File**: `src/common/retry.py` (new file)

```python
"""
Retry decorator for transient failures.

Usage:
    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def download_file(url):
        ...
"""

import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Multiplier for delay after each attempt
        exceptions: Tuple of exception types to catch

    Example:
        @retry(max_attempts=5, delay=2.0, exceptions=(ConnectionError, TimeoutError))
        def connect_to_server():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts")
                        raise

                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

        return wrapper
    return decorator
```

---

## Part 3: Enhanced Logging

**File**: `src/common/logging_config.py` (modify existing)

```python
"""Enhanced logging configuration."""

import logging
import logging.handlers
from pathlib import Path
import sys


def setup_logging(log_dir: Path = Path.home() / ".local/share/neuronos/logs"):
    """
    Configure comprehensive logging.

    Creates:
    - errors.log: ERROR and above (rotated, 10MB max)
    - debug.log: All messages (rotated, 50MB max)
    - Console: INFO and above
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler (INFO+)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    root_logger.addHandler(console)

    # Error file handler (ERROR+, rotated)
    error_file = log_dir / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
        '    %(pathname)s:%(lineno)d\n'
    ))
    root_logger.addHandler(error_handler)

    # Debug file handler (all messages, rotated)
    debug_file = log_dir / "debug.log"
    debug_handler = logging.handlers.RotatingFileHandler(
        debug_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s'
    ))
    root_logger.addHandler(debug_handler)

    logging.info(f"Logging initialized. Logs: {log_dir}")
```

---

## Part 4: GUI Integration

Integrate error handler into existing GUI code.

**File**: `src/vm_manager/gui/app.py` (modifications)

```python
# Add at top
from src.common.error_handler import ErrorHandler

class NeuronOSApp(Adw.Application):
    """Main application."""

    def __init__(self):
        super().__init__()
        # Set global exception handler
        sys.excepthook = self._global_exception_handler

    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """Catch all unhandled exceptions."""
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        ErrorHandler.show_error(exc_value, parent=self.main_window)

    def on_start_vm_clicked(self, button):
        """Start selected VM."""
        vm = self.get_selected_vm()
        if not vm:
            return

        try:
            self.vm_manager.start_vm(vm.name)
        except Exception as e:
            # Show user-friendly error dialog
            ErrorHandler.show_error(e, parent=self)

    def on_create_vm_clicked(self, button):
        """Create new VM."""
        try:
            config = self._get_vm_config_from_dialog()
            self.vm_manager.create_vm(config)
        except Exception as e:
            ErrorHandler.show_error(e, parent=self)
```

---

## Part 5: Testing

**File**: `tests/test_error_handler.py` (new file)

```python
"""Tests for error handling system."""

import pytest
from unittest.mock import Mock, patch

from src.common.exceptions import (
    VMNotFoundError,
    IOMMUError,
    DownloadError,
)
from src.common.error_handler import ErrorHandler, ErrorContext


def test_vm_not_found_context():
    """Test VM not found error context."""
    error = VMNotFoundError("Windows11")
    context = ErrorHandler._get_error_context(error)

    assert context.title == "Virtual Machine Not Found"
    assert "Windows11" in context.message
    assert context.error_code == "VM_NOT_FOUND"
    assert not context.is_fatal
    assert len(context.recovery_actions) == 2
    assert context.recovery_actions[0].label == "Refresh VM List"


def test_iommu_error_context():
    """Test IOMMU error provides BIOS guide."""
    error = IOMMUError()
    context = ErrorHandler._get_error_context(error)

    assert "GPU Passthrough Not Available" in context.title
    assert "BIOS" in context.message
    assert len(context.recovery_actions) >= 1
    assert any("IOMMU" in action.label for action in context.recovery_actions)
    assert context.help_url is not None


def test_download_error_retry():
    """Test download error offers retry."""
    error = DownloadError("https://example.com/file.iso", "Network timeout")
    context = ErrorHandler._get_error_context(error)

    assert "Download Failed" in context.title
    assert any("Retry" in action.label for action in context.recovery_actions)


def test_unknown_error_bug_report():
    """Test unknown errors offer bug reporting."""
    error = ValueError("Something unexpected")
    context = ErrorHandler._get_error_context(error)

    assert "Unexpected Error" in context.title
    assert any("Report Bug" in action.label for action in context.recovery_actions)


@pytest.mark.gui
def test_error_dialog_creation():
    """Test error dialog is created correctly."""
    error = VMNotFoundError("TestVM")
    context = ErrorHandler._get_error_context(error)

    dialog = ErrorHandler._create_error_dialog(context, parent=None)

    assert dialog is not None
    assert dialog.get_heading() == context.title
```

---

## Verification Checklist

Before marking Phase 3.2 complete, verify:

- [ ] **All exceptions show dialogs** - No terminal-only errors
- [ ] **Plain English** - No "XMLDesc", "VFIO bind failed" without explanation
- [ ] **Recovery actions work** - "Refresh VM List" actually refreshes
- [ ] **Help links open** - "Help" button opens correct docs page
- [ ] **Technical details available** - "Show Details" reveals full traceback
- [ ] **Errors logged** - Check `~/.local/share/neuronos/logs/errors.log`
- [ ] **Retry works** - Transient failures (download, libvirt) auto-retry
- [ ] **Bug reporting** - "Report Bug" opens GitHub with pre-filled info
- [ ] **No crashes** - Unhandled exceptions caught by global handler
- [ ] **IOMMU guide helpful** - Non-technical user can follow BIOS instructions

---

## Acceptance Criteria

✅ **Phase 3.2 is COMPLETE when**:
1. All errors show user-friendly GUI dialogs (no terminal-only errors)
2. Recovery suggestions are actionable (e.g., "Enable IOMMU" opens guide)
3. Errors are logged with full context for debugging
4. Transient failures auto-retry (network, libvirt connection)
5. Users can report bugs with one click (GitHub issue pre-populated)
6. Non-technical users can fix common errors without Googling

❌ **Phase 3.2 FAILS if**:
1. Any error shows raw Python traceback to users
2. Recovery actions don't work or make things worse
3. No logs are created (can't debug reported issues)
4. Permanent errors have "Retry" button that does nothing
5. Help links lead to 404 pages
6. Error messages use jargon (VFIO, IOMMU, XMLDesc) without explanation

---

## Risks & Mitigations

### Risk 1: Over-simplification hides important details
**Mitigation**: Always provide "Show Details" button for technical users and support staff.

### Risk 2: Recovery actions fail and create worse errors
**Mitigation**: Wrap all recovery callbacks in try/except and show new error dialog if recovery fails.

### Risk 3: Error dialogs interrupt critical operations
**Mitigation**: Use non-blocking dialogs for non-fatal errors. Only block for fatal errors.

### Risk 4: Logs fill disk space
**Mitigation**: Use rotating file handlers (10MB errors.log, 50MB debug.log) with automatic cleanup.

---

## Next Steps

This phase enables:
- **Phase 3.3**: Migration progress UI can use error dialogs for failed transfers
- **Phase 4.2**: Security audit can verify all error paths are handled
- **Production readiness**: Users can self-recover from 90% of errors

---

## Resources

- [GTK4 MessageDialog](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.MessageDialog.html)
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [Error Message Guidelines (Nielsen Norman Group)](https://www.nngroup.com/articles/error-message-guidelines/)

Good luck! 🚀
