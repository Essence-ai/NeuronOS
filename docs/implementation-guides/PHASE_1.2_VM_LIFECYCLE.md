# Phase 1.2: VM Lifecycle - Deletion & Settings Dialog

**Status**: 🔴 CRITICAL BLOCKER - Users cannot delete VMs or modify settings
**Estimated Time**: 2-3 days
**Prerequisites**: None (can work in parallel)

---

## What We're Building

Currently, users can **create and start** VMs but **cannot**:

1. ❌ **Delete VMs** - "Delete" button exists but does nothing (TODO)
2. ❌ **Modify Settings** - "Settings" button doesn't exist
3. ❌ **Reclaim Disk Space** - Deleted VMs still consume storage

After this phase:

- ✅ Users can delete VMs with confirmation
- ✅ Users can edit VM settings (CPU, RAM, GPU assignment)
- ✅ Disk space is properly freed
- ✅ Settings changes apply without VM recreation

---

## Current Code State

### Where to Find It

**File**: `src/vm_manager/gui/app.py`

**Current Implementation** (lines 865-880):

```python
def _on_delete_response(self, dialog, response):
    """Handle delete confirmation response."""
    if response == "delete":
        # TODO: Actually delete the VM!
        print(f"Would delete {self.vm_info.name}")
        # Missing code here ↓
        # - Unbind GPU from VFIO
        # - Destroy VM in libvirt
        # - Delete disk images
        # - Remove .desktop launcher

def _on_settings_clicked(self, button):
    """Show settings dialog."""
    # COMPLETELY EMPTY - No settings dialog exists!
    pass  # ← This does nothing!
```

**The Problem**:
1. Delete just prints a message
2. Settings button doesn't do anything
3. Users see buttons but they don't work

---

## Part 1: Implement VM Deletion

### 1.1: Create VM Destroyer Class

**File**: `src/vm_manager/core/vm_destroyer.py` (NEW FILE)

```python
"""
VM Destruction and Cleanup

Safely destroys VMs and reclaims resources (disk, GPUs).
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VMDestroyError(Exception):
    """Raised when VM destruction fails."""
    pass


class VMDestroyer:
    """Safely destroy QEMU/KVM virtual machines."""

    def __init__(self):
        """Initialize destroyer."""
        self.data_dir = Path.home() / ".local" / "share" / "neuron-os"
        self.vm_disks_dir = self.data_dir / "vm-disks"
        self.vm_configs_dir = self.data_dir / "vm-configs"

    def destroy(self, vm_name: str, force: bool = False) -> bool:
        """
        Destroy a VM and all associated resources.

        Args:
            vm_name: Name of VM to destroy
            force: Force destroy even if VM is running

        Returns:
            True if successful

        Raises:
            VMDestroyError: If destruction fails
        """
        logger.info(f"Starting destruction of VM: {vm_name}")

        try:
            # Step 1: Check if VM exists
            if not self._vm_exists(vm_name):
                logger.warning(f"VM not found: {vm_name}")
                return False

            # Step 2: Stop running VM
            if self._vm_is_running(vm_name):
                if force:
                    logger.info(f"Force stopping VM: {vm_name}")
                    self._force_stop_vm(vm_name)
                else:
                    logger.info(f"Gracefully stopping VM: {vm_name}")
                    self._stop_vm(vm_name)

            # Step 3: Unbind GPU from VFIO
            self._unbind_gpus(vm_name)

            # Step 4: Destroy VM definition in libvirt
            self._destroy_libvirt_vm(vm_name)

            # Step 5: Delete disk images
            self._delete_disks(vm_name)

            # Step 6: Delete configuration files
            self._delete_config_files(vm_name)

            # Step 7: Remove .desktop launcher
            self._remove_desktop_launcher(vm_name)

            logger.info(f"Successfully destroyed VM: {vm_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to destroy VM {vm_name}: {e}")
            raise VMDestroyError(f"Destruction failed: {e}") from e

    def _vm_exists(self, vm_name: str) -> bool:
        """Check if VM is defined in libvirt."""
        try:
            result = subprocess.run(
                ["virsh", "dominfo", vm_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _vm_is_running(self, vm_name: str) -> bool:
        """Check if VM is currently running."""
        try:
            result = subprocess.run(
                ["virsh", "domstate", vm_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            state = result.stdout.strip()
            return state == "running"
        except Exception:
            return False

    def _stop_vm(self, vm_name: str, timeout: int = 30) -> bool:
        """Gracefully stop a running VM."""
        try:
            logger.info(f"Stopping VM {vm_name} with timeout {timeout}s")
            subprocess.run(
                ["virsh", "shutdown", vm_name],
                capture_output=True,
                timeout=timeout,
            )

            # Wait for VM to stop
            import time
            waited = 0
            while self._vm_is_running(vm_name) and waited < timeout:
                time.sleep(1)
                waited += 1

            if self._vm_is_running(vm_name):
                logger.warning(f"VM {vm_name} did not stop gracefully, forcing")
                return self._force_stop_vm(vm_name)

            return True
        except Exception as e:
            logger.error(f"Failed to stop VM: {e}")
            return False

    def _force_stop_vm(self, vm_name: str) -> bool:
        """Force stop a VM immediately."""
        try:
            logger.warning(f"Force stopping VM: {vm_name}")
            subprocess.run(
                ["virsh", "destroy", vm_name],
                capture_output=True,
                timeout=10,
            )
            return True
        except Exception as e:
            logger.error(f"Force stop failed: {e}")
            return False

    def _unbind_gpus(self, vm_name: str) -> bool:
        """
        Unbind any GPUs that were bound to VFIO for this VM.

        This is a best-effort operation - we try to return GPUs to
        their original drivers.
        """
        try:
            # Get VM configuration
            result = subprocess.run(
                ["virsh", "dumpxml", vm_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.warning("Could not get VM XML to find GPUs")
                return True  # Non-fatal

            xml = result.stdout

            # Parse PCI addresses from hostdev sections
            import re
            pci_addresses = re.findall(
                r"<address domain='0x(\w+)' bus='0x(\w+)' slot='0x(\w+)' function='0x(\w+)'/>",
                xml,
            )

            # For each GPU, try to rebind to original driver
            from src.vm_manager.passthrough.gpu_attach import GPUAttacher
            attacher = GPUAttacher()

            for domain, bus, slot, function in pci_addresses:
                pci_address = f"{domain}:{bus}:{slot}.{function}"
                try:
                    logger.info(f"Rebinding GPU {pci_address} from VFIO")
                    attacher.rebind_to_driver(pci_address)
                except Exception as e:
                    logger.warning(f"Failed to rebind {pci_address}: {e}")
                    # Continue with other GPUs

            return True

        except Exception as e:
            logger.warning(f"GPU unbinding failed (non-fatal): {e}")
            return True  # Don't fail VM destruction for this

    def _destroy_libvirt_vm(self, vm_name: str) -> bool:
        """Destroy VM definition in libvirt."""
        try:
            logger.info(f"Destroying libvirt domain: {vm_name}")

            # First undefine the VM (removes it from libvirt)
            result = subprocess.run(
                ["virsh", "undefine", vm_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info(f"VM {vm_name} undefined from libvirt")
                return True
            else:
                logger.error(f"Failed to undefine VM: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Libvirt destroy failed: {e}")
            return False

    def _delete_disks(self, vm_name: str) -> bool:
        """Delete VM disk images."""
        try:
            # VM disks stored in: ~/.local/share/neuron-os/vm-disks/{vm_name}/
            vm_disk_path = self.vm_disks_dir / vm_name

            if not vm_disk_path.exists():
                logger.warning(f"VM disk directory not found: {vm_disk_path}")
                return True  # Non-fatal

            logger.info(f"Deleting VM disks at: {vm_disk_path}")

            # Remove all files in VM directory
            import shutil
            shutil.rmtree(vm_disk_path, ignore_errors=True)

            if vm_disk_path.exists():
                logger.warning(f"Could not fully delete disk directory")
                return False

            logger.info(f"Successfully deleted VM disks")
            return True

        except Exception as e:
            logger.error(f"Disk deletion failed: {e}")
            return False

    def _delete_config_files(self, vm_name: str) -> bool:
        """Delete VM configuration files."""
        try:
            # Config files: ~/.local/share/neuron-os/vm-configs/{vm_name}.json
            config_path = self.vm_configs_dir / f"{vm_name}.json"

            if not config_path.exists():
                logger.warning(f"Config file not found: {config_path}")
                return True

            logger.info(f"Deleting VM config: {config_path}")
            config_path.unlink()

            return True

        except Exception as e:
            logger.error(f"Config deletion failed: {e}")
            return False

    def _remove_desktop_launcher(self, vm_name: str) -> bool:
        """Remove .desktop file launcher for VM."""
        try:
            # Desktop files: ~/.local/share/applications/neuron-{vm_name}.desktop
            desktop_path = (
                Path.home()
                / ".local"
                / "share"
                / "applications"
                / f"neuron-{vm_name}.desktop"
            )

            if not desktop_path.exists():
                logger.warning(f"Desktop launcher not found: {desktop_path}")
                return True

            logger.info(f"Deleting launcher: {desktop_path}")
            desktop_path.unlink()

            return True

        except Exception as e:
            logger.error(f"Launcher deletion failed: {e}")
            return False
```

### 1.2: Update GUI Delete Handler

**File**: `src/vm_manager/gui/app.py`

**Find this section** (around line 860-880):

```python
def _on_delete_response(self, dialog, response):
    """Handle delete confirmation response."""
    if response == "delete":
        # TODO: Actually delete the VM!
        print(f"Would delete {self.vm_info.name}")
```

**Replace with**:

```python
def _on_delete_response(self, dialog, response):
    """Handle delete confirmation response."""
    if response != "delete":
        return  # User clicked Cancel

    vm_name = self.vm_info.name

    # Show "Deleting..." toast
    from src.common.dialogs import show_toast
    toast = show_toast(self.window, "Deleting VM...", timeout=0)

    try:
        # Import destroyer (already exists after 1.1 implementation)
        from src.vm_manager.core.vm_destroyer import VMDestroyer

        destroyer = VMDestroyer()
        success = destroyer.destroy(vm_name)

        if success:
            # Update UI to remove VM from list
            self.window.remove_vm_card(vm_name)
            show_toast(
                self.window,
                f"VM '{vm_name}' deleted successfully",
                timeout=2,
            )
            logger.info(f"VM deletion completed: {vm_name}")
        else:
            show_toast(
                self.window,
                f"Failed to delete VM '{vm_name}'",
                timeout=3,
            )
            logger.error(f"VM deletion failed: {vm_name}")

    except Exception as e:
        logger.error(f"Exception during VM deletion: {e}")
        show_toast(
            self.window,
            f"Error deleting VM: {str(e)}",
            timeout=3,
        )
    finally:
        toast.dismiss()
```

### 1.3: Add Confirmation Dialog

**File**: `src/vm_manager/gui/app.py`

**Find where delete button is created** (around line 850):

```python
delete_button = Gtk.Button(label="Delete")
delete_button.connect("clicked", self._on_delete_clicked)
```

**Replace `_on_delete_clicked` with**:

```python
def _on_delete_clicked(self, button):
    """Show confirmation dialog before deleting VM."""
    vm_name = self.vm_info.name

    # Create confirmation dialog
    dialog = Adw.MessageDialog.new(self.window)
    dialog.set_heading(f"Delete '{vm_name}'?")
    dialog.set_body(
        "This will:\n"
        "• Stop the VM if running\n"
        "• Delete all VM data (~50GB)\n"
        "• Free disk space\n\n"
        "This action cannot be undone."
    )

    # Add buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("delete", "Delete VM")
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    # Connect response signal
    dialog.connect("response", self._on_delete_response)

    # Show dialog
    dialog.present()
```

---

## Part 2: Implement Settings Dialog

### 2.1: Create Settings Dialog Widget

**File**: `src/vm_manager/gui/settings_dialog.py` (NEW FILE)

```python
"""
VM Settings Editor Dialog

Allows users to modify VM settings:
- CPU count
- Memory size
- GPU assignment
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GObject
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VMSettings:
    """VM settings that can be edited."""
    vcpu_count: int
    memory_gb: int
    gpu_pci_address: str  # "0000:01:00.0" or empty for no GPU


class SettingsDialog(Adw.Window):
    """Dialog for editing VM settings."""

    def __init__(self, parent: Adw.ApplicationWindow, vm_info):
        """
        Initialize settings dialog.

        Args:
            parent: Parent window
            vm_info: Current VM info
        """
        super().__init__()

        self.parent = parent
        self.vm_info = vm_info
        self.vm_name = vm_info.name

        # Load current settings
        self.original_settings = self._load_settings()
        self.current_settings = VMSettings(
            vcpu_count=self.original_settings.vcpu_count,
            memory_gb=self.original_settings.memory_gb,
            gpu_pci_address=self.original_settings.gpu_pci_address,
        )

        self.set_title(f"Settings - {self.vm_name}")
        self.set_default_size(400, 500)
        self.set_modal(True)
        self.set_transient_for(parent)

        # Create content
        self._build_ui()

    def _build_ui(self):
        """Build settings dialog UI."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)

        # Title
        title = Gtk.Label()
        title.set_markup(f"<b>VM Settings: {self.vm_name}</b>")
        title.set_halign(Gtk.Align.START)
        vbox.append(title)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.append(sep)

        # CPU Cores
        cpu_box = self._build_cpu_spinbutton()
        vbox.append(cpu_box)

        # Memory
        mem_box = self._build_memory_spinbutton()
        vbox.append(mem_box)

        # GPU (read-only for now)
        gpu_box = self._build_gpu_selector()
        vbox.append(gpu_box)

        # Spacer
        vbox.append(Gtk.Box())

        # Buttons
        button_box = self._build_button_box()
        vbox.append(button_box)

        # Set as content
        content = Adw.WindowTitle()
        header = Gtk.HeaderBar()
        header.set_title_widget(content)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        main_box.append(vbox)

        self.set_content(main_box)

    def _build_cpu_spinbutton(self) -> Gtk.Box:
        """Build CPU core selector."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        label = Gtk.Label(label="CPU Cores:")
        label.set_halign(Gtk.Align.START)
        label.set_size_request(100, -1)
        box.append(label)

        adjustment = Gtk.Adjustment(
            value=self.current_settings.vcpu_count,
            lower=1,
            upper=64,
            step_increment=1,
        )
        spin = Gtk.SpinButton()
        spin.set_adjustment(adjustment)
        spin.set_size_request(80, -1)
        spin.connect("value-changed", self._on_cpu_changed)
        self.cpu_spin = spin
        box.append(spin)

        info = Gtk.Label(label="(1-64)")
        info.set_size_request(50, -1)
        info.add_css_class("dim-label")
        box.append(info)

        return box

    def _build_memory_spinbutton(self) -> Gtk.Box:
        """Build memory size selector."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        label = Gtk.Label(label="Memory:")
        label.set_halign(Gtk.Align.START)
        label.set_size_request(100, -1)
        box.append(label)

        adjustment = Gtk.Adjustment(
            value=self.current_settings.memory_gb,
            lower=2,
            upper=128,
            step_increment=1,
        )
        spin = Gtk.SpinButton()
        spin.set_adjustment(adjustment)
        spin.set_size_request(80, -1)
        spin.connect("value-changed", self._on_memory_changed)
        self.memory_spin = spin
        box.append(spin)

        unit = Gtk.Label(label="GB")
        unit.set_size_request(40, -1)
        box.append(unit)

        return box

    def _build_gpu_selector(self) -> Gtk.Box:
        """Build GPU assignment selector."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        label = Gtk.Label(label="GPU Assignment:")
        label.set_halign(Gtk.Align.START)
        box.append(label)

        # Current GPU display (read-only for now)
        current_gpu = self.current_settings.gpu_pci_address or "None (CPU rendering)"
        gpu_label = Gtk.Label(label=f"Current: {current_gpu}")
        gpu_label.set_halign(Gtk.Align.START)
        gpu_label.add_css_class("dim-label")
        box.append(gpu_label)

        info = Gtk.Label(label="GPU reassignment requires VM restart")
        info.set_halign(Gtk.Align.START)
        info.add_css_class("dim-label")
        info.set_wrap(True)
        box.append(info)

        return box

    def _build_button_box(self) -> Gtk.Box:
        """Build dialog buttons (Cancel, Apply)."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        box.append(cancel_btn)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        self.apply_btn = apply_btn
        box.append(apply_btn)

        return box

    def _on_cpu_changed(self, spin):
        """CPU cores changed."""
        self.current_settings.vcpu_count = int(spin.get_value())
        self._update_apply_button_state()

    def _on_memory_changed(self, spin):
        """Memory changed."""
        self.current_settings.memory_gb = int(spin.get_value())
        self._update_apply_button_state()

    def _update_apply_button_state(self):
        """Enable apply button only if settings changed."""
        changed = (
            self.current_settings.vcpu_count != self.original_settings.vcpu_count
            or self.current_settings.memory_gb != self.original_settings.memory_gb
        )
        self.apply_btn.set_sensitive(changed)

    def _on_apply_clicked(self, button):
        """Apply settings changes."""
        logger.info(
            f"Applying settings: CPU={self.current_settings.vcpu_count}, "
            f"Memory={self.current_settings.memory_gb}GB"
        )

        # Save settings to config file
        try:
            self._save_settings(self.current_settings)
            from src.common.dialogs import show_toast
            show_toast(
                self.parent,
                "Settings saved. VM must be restarted for changes to apply.",
                timeout=3,
            )
            self.close()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            from src.common.dialogs import show_toast
            show_toast(self.parent, f"Error saving settings: {e}", timeout=3)

    def _load_settings(self) -> VMSettings:
        """Load current VM settings from config file."""
        config_dir = Path.home() / ".local" / "share" / "neuron-os" / "vm-configs"
        config_file = config_dir / f"{self.vm_name}.json"

        if not config_file.exists():
            # Return defaults
            return VMSettings(vcpu_count=8, memory_gb=16, gpu_pci_address="")

        try:
            import json
            with open(config_file) as f:
                data = json.load(f)

            return VMSettings(
                vcpu_count=data.get("vcpu_count", 8),
                memory_gb=data.get("memory_gb", 16),
                gpu_pci_address=data.get("gpu_pci_address", ""),
            )
        except Exception as e:
            logger.warning(f"Failed to load settings, using defaults: {e}")
            return VMSettings(vcpu_count=8, memory_gb=16, gpu_pci_address="")

    def _save_settings(self, settings: VMSettings):
        """Save VM settings to config file."""
        config_dir = Path.home() / ".local" / "share" / "neuron-os" / "vm-configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / f"{self.vm_name}.json"

        import json
        from src.utils.atomic_write import atomic_write_json

        config_data = {
            "vcpu_count": settings.vcpu_count,
            "memory_gb": settings.memory_gb,
            "gpu_pci_address": settings.gpu_pci_address,
        }

        atomic_write_json(config_file, config_data)
```

### 2.2: Wire Settings Button in Main GUI

**File**: `src/vm_manager/gui/app.py`

**Find the settings button creation** (around line 876):

```python
def _on_settings_clicked(self, button):
    """Show settings dialog."""
    pass  # ← This does nothing!
```

**Replace with**:

```python
def _on_settings_clicked(self, button):
    """Show settings dialog."""
    from src.vm_manager.gui.settings_dialog import SettingsDialog

    try:
        settings_window = SettingsDialog(self.window, self.vm_info)
        settings_window.present()
    except Exception as e:
        logger.error(f"Failed to open settings: {e}")
        from src.common.dialogs import show_toast
        show_toast(self.window, f"Error opening settings: {e}", timeout=2)
```

---

## Part 3: Update VM Config Loading

**File**: `src/vm_manager/core/vm_creator.py`

When creating VMs, save settings to config file so they can be edited later:

```python
def create_vm(self, config: VMConfig) -> bool:
    """Create and define a VM."""
    # ... existing code ...

    # After successful VM creation, save config
    self._save_vm_config(config)

    return True

def _save_vm_config(self, config: VMConfig):
    """Save VM configuration to file for later editing."""
    config_dir = Path.home() / ".local" / "share" / "neuron-os" / "vm-configs"
    config_dir.mkdir(parents=True, exist_ok=True)

    import json
    from src.utils.atomic_write import atomic_write_json

    config_data = {
        "name": config.name,
        "vcpu_count": config.vcpu_count,
        "memory_gb": config.memory_gb,
        "gpu_pci_address": config.gpus[0].pci_address if config.gpus else "",
        "iso_path": str(config.iso_path) if config.iso_path else "",
        "disk_size_gb": config.disk_size_gb,
    }

    config_file = config_dir / f"{config.name}.json"
    atomic_write_json(config_file, config_data)
```

---

## Verification Checklist

Before moving to Phase 1.3:

**VM Deletion**:
- [ ] Delete button is active and clickable
- [ ] Clicking delete shows confirmation dialog
- [ ] Canceling dialog closes without deleting
- [ ] Confirming delete actually removes VM
- [ ] VM is removed from virsh: `virsh list --all` doesn't show it
- [ ] VM disks deleted: directory under `~/.local/share/neuron-os/vm-disks/` is gone
- [ ] Disk space freed: `df -h` shows more free space
- [ ] GPU unbinded from VFIO (if assigned)
- [ ] .desktop launcher removed

**VM Settings Dialog**:
- [ ] Settings button appears on VM card
- [ ] Clicking opens settings window
- [ ] CPU spinner works (1-64)
- [ ] Memory spinner works (2-128 GB)
- [ ] GPU assignment shows current assignment (read-only)
- [ ] Apply button only active when settings changed
- [ ] Apply button saves settings to config file
- [ ] Settings persist after VM restart

**Configuration**:
- [ ] VM config saved as JSON after creation
- [ ] Config loaded correctly when opening settings
- [ ] Invalid/missing config doesn't crash settings dialog
- [ ] Settings changes don't affect running VM (require restart)

**Error Handling**:
- [ ] Deleting non-existent VM shows error toast
- [ ] Deleting VM that won't stop shows error after timeout
- [ ] GPU unbinding failure doesn't prevent VM deletion
- [ ] Settings dialog opens even if config file missing
- [ ] Invalid settings values are rejected

**Code Quality**:
- [ ] No hardcoded paths (use Path.home())
- [ ] All exceptions caught and logged
- [ ] Proper resource cleanup (close dialogs, etc.)
- [ ] No zombie processes after stopping VM
- [ ] Proper permissions (can delete config files)

---

## Acceptance Criteria

✅ **Phase 1.2 Complete When**:

1. VM deletion works end-to-end with confirmation
2. All VM resources cleaned up (disks, config, launcher)
3. Settings dialog opens and saves changes
4. Settings changes persist in config files
5. Error handling is robust (no crashes)

❌ **Phase 1.2 Fails If**:

- Delete button still does nothing
- VMs cannot be actually removed
- Settings dialog doesn't save changes
- Unhandled exceptions crash GUI

---

## Risks & Mitigations

### Risk 1: Accidental Data Loss

**Issue**: Users might accidentally delete wrong VM

**Mitigation**:
- Require confirmation dialog (implemented)
- Show warning about disk space being freed
- Could add 5-second countdown confirmation (nice-to-have)

### Risk 2: VM Won't Stop

**Issue**: VM ignores shutdown request, requires force kill

**Mitigation**:
- Use graceful shutdown first (30s timeout)
- Force kill if graceful fails
- Log both attempts

### Risk 3: GPU Still Bound After Deletion

**Issue**: GPU remains stuck in VFIO, can't be used on host

**Mitigation**:
- Parse VM XML to find GPU PCI addresses
- Call gpu_attach.rebind_to_driver() for each
- Log errors but don't fail VM destruction
- User can manually rebind if needed

### Risk 4: Settings Change Applied to Running VM

**Issue**: User changes CPU/RAM while VM is running

**Mitigation**:
- Show warning: "VM must be restarted for changes to apply"
- Don't actually apply to running VM (just save config)
- Next time VM starts, new settings are used

---

## Next Steps

1. Phase 1.3 fixes the file/directory migration bug
2. Phase 1.4 completes the Proton installer
3. Phase 1.5 adds security to guest agent

---

## Resources

- [Libvirt VM Management](https://libvirt.org/manpages/virsh.html)
- [GTK4 Dialog Documentation](https://docs.gtk.org/gtk4/class.Dialog.html)
- [Adwaita Dialogs](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1.3/class.MessageDialog.html)

Good luck! 🚀
