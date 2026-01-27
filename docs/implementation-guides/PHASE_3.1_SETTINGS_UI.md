# Phase 3.1: Enhanced VM Settings Editor

**Status**: 🟡 BASIC IMPLEMENTATION EXISTS (Phase 1.2) - Needs Enhancement
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.2 (Basic Settings Dialog), Phase 2.3 (Hardware Detection), Phase 2.4 (Looking Glass)

---

## What is the VM Settings Editor?

The VM Settings Editor is the GUI interface where users can modify their virtual machine configurations **after creation**. This is critical because:

1. **User needs change** - Initial 4 cores becomes insufficient, need to add 2 more
2. **Hardware changes** - User adds new GPU and wants to switch passthrough
3. **Performance tuning** - Adjust RAM, enable hugepages, tweak CPU pinning
4. **Storage expansion** - Running out of disk space, need to expand from 100GB to 200GB

**Without proper settings**: Users must delete and recreate VMs to change even simple things like RAM, losing all installed software and configurations.

---

## Current State: Phase 1.2 Basic Implementation

### What Already Works ✅

From Phase 1.2, we have:

**File**: `src/vm_manager/gui/dialogs/settings_dialog.py` (~150 lines)
- Basic GTK dialog with tabs for CPU, Memory, Storage
- Read-only display of current settings
- Can modify CPU cores and RAM amount
- **Limitation**: Requires VM destruction and recreation to apply changes

**Integration**: `src/vm_manager/gui/app.py`:
```python
def on_settings_clicked(self, button):
    """Open settings dialog."""
    vm = self.get_selected_vm()
    if not vm:
        return

    dialog = SettingsDialog(vm, parent=self)
    response = dialog.run()

    if response == Gtk.ResponseType.OK:
        # Current implementation: Destroys VM and recreates
        self.vm_manager.destroy_vm(vm.name)
        new_config = dialog.get_config()
        self.vm_manager.create_vm(new_config)
```

### What's Missing ❌

| Missing Feature | Impact | User Experience |
|---|---|---|
| **Hot configuration** (CPU/RAM without restart) | Can't adjust resources for running VMs | "Why do I need to restart just to add 2GB RAM?" |
| **Cold configuration** (GPU/disk with restart) | Can't change GPU without VM deletion | "I added a new GPU but can't use it without losing my VM" |
| **Disk expansion** | Running out of space = VM recreation | "My 100GB Windows VM is full. Now what?" |
| **Audio device selection** | No audio or wrong output device | "Why is audio playing on my monitor speakers instead of headphones?" |
| **USB device pass-through** | Can't use specific USB devices | "I need my USB security key in the VM" |
| **Network configuration** | Stuck with default bridge | "I want VM on separate VLAN but can't configure it" |
| **Display settings** | Can't switch between SPICE/Looking Glass | "I enabled Looking Glass but can't activate it" |
| **Validation** | Invalid configs cause VM failures | "VM won't start after I changed settings. No error message" |

### The Impact

**Scenario**: Susan is a graphic designer using NeuronOS with Photoshop in a Windows VM:

1. ✅ VM works with 8GB RAM initially
2. 🔵 Opens large project → "Out of memory" in Photoshop
3. 🔵 Opens Settings → Increases RAM to 16GB → Clicks "Apply"
4. ❌ **Current behavior**: "VM must be destroyed and recreated. All data will be lost."
5. ❌ Susan clicks "Cancel" and gives up on NeuronOS
6. **Desired behavior**: "RAM increased to 16GB. Restart VM to apply." → No data loss

---

## Objective: Production-Quality Settings Editor

After completing Phase 3.1:

1. ✅ **Hot settings** - Change CPU cores, RAM without VM shutdown (libvirt setvcpus/setmem)
2. ✅ **Cold settings** - Change GPU, storage, USB with automatic restart prompt
3. ✅ **Disk expansion** - Expand qcow2 images and NTFS/ext4 filesystems automatically
4. ✅ **Audio configuration** - Select PulseAudio/PipeWire sink, test audio output
5. ✅ **USB pass-through** - List USB devices, pass specific devices to VM
6. ✅ **Network advanced** - Bridge selection, MAC address customization, port forwarding
7. ✅ **Display switching** - Toggle SPICE ↔ Looking Glass with automatic setup
8. ✅ **Real-time validation** - Check CPU limits, RAM availability, disk space before applying
9. ✅ **Diff preview** - Show what will change before applying ("4 cores → 6 cores, 8GB → 16GB")
10. ✅ **Rollback** - If settings fail to apply, restore previous configuration automatically

---

## Part 1: Enhance VM Configuration Model

First, extend the configuration system to support **live updates** and **change tracking**.

### 1.1: Add Change Tracking to VMConfig

**File**: `src/vm_manager/core/vm_config.py` (append to existing file)

```python
from typing import Dict, Any, Set
from copy import deepcopy

class SettingType(Enum):
    """Classification of settings by modification requirements."""
    HOT = "hot"          # Can apply while VM is running
    WARM = "warm"        # Can apply with VM paused
    COLD = "cold"        # Requires VM shutdown
    DESTRUCTIVE = "destructive"  # Requires VM recreation

@dataclass
class ConfigChange:
    """Represents a single configuration change."""
    field_path: str           # "cpu.cores"
    old_value: Any
    new_value: Any
    setting_type: SettingType
    requires_restart: bool
    risk_level: str           # "safe", "medium", "high"

    def __str__(self) -> str:
        """Human-readable change description."""
        if self.field_path == "cpu.cores":
            return f"CPU cores: {self.old_value} → {self.new_value}"
        elif self.field_path == "memory.size_mb":
            old_gb = self.old_value / 1024
            new_gb = self.new_value / 1024
            return f"RAM: {old_gb:.1f}GB → {new_gb:.1f}GB"
        elif self.field_path == "gpu.pci_address":
            return f"GPU: {self.old_value or 'None'} → {self.new_value or 'None'}"
        else:
            return f"{self.field_path}: {self.old_value} → {self.new_value}"

class VMConfig:
    """Extended VMConfig with change tracking."""

    # ... existing fields ...

    def diff(self, other: "VMConfig") -> List[ConfigChange]:
        """
        Compare this config with another and return list of changes.

        Args:
            other: New configuration to compare against

        Returns:
            List of ConfigChange objects
        """
        changes = []

        # CPU changes
        if self.cpu.cores != other.cpu.cores:
            changes.append(ConfigChange(
                field_path="cpu.cores",
                old_value=self.cpu.cores,
                new_value=other.cpu.cores,
                setting_type=SettingType.HOT,
                requires_restart=False,
                risk_level="safe"
            ))

        if self.cpu.threads != other.cpu.threads:
            changes.append(ConfigChange(
                field_path="cpu.threads",
                old_value=self.cpu.threads,
                new_value=other.cpu.threads,
                setting_type=SettingType.COLD,
                requires_restart=True,
                risk_level="safe"
            ))

        # Memory changes
        if self.memory.size_mb != other.memory.size_mb:
            setting_type = SettingType.HOT if other.memory.size_mb <= self.memory.size_mb else SettingType.WARM
            changes.append(ConfigChange(
                field_path="memory.size_mb",
                old_value=self.memory.size_mb,
                new_value=other.memory.size_mb,
                setting_type=setting_type,
                requires_restart=setting_type != SettingType.HOT,
                risk_level="safe"
            ))

        # GPU changes (DESTRUCTIVE - requires complex rebinding)
        if self.gpu.pci_address != other.gpu.pci_address:
            changes.append(ConfigChange(
                field_path="gpu.pci_address",
                old_value=self.gpu.pci_address,
                new_value=other.gpu.pci_address,
                setting_type=SettingType.DESTRUCTIVE,
                requires_restart=True,
                risk_level="high"
            ))

        # Storage changes
        if self.storage and other.storage:
            if self.storage.size_gb != other.storage.size_gb:
                changes.append(ConfigChange(
                    field_path="storage.size_gb",
                    old_value=self.storage.size_gb,
                    new_value=other.storage.size_gb,
                    setting_type=SettingType.COLD,
                    requires_restart=True,
                    risk_level="medium"  # Data expansion has risks
                ))

        return changes

    def apply_changes(
        self,
        changes: List[ConfigChange],
        vm_name: str,
        dry_run: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Apply configuration changes to a running VM.

        Args:
            changes: List of changes to apply
            vm_name: Name of the VM to modify
            dry_run: If True, validate but don't apply

        Returns:
            Tuple of (success, error_messages)
        """
        errors = []

        # Group changes by type
        hot_changes = [c for c in changes if c.setting_type == SettingType.HOT]
        warm_changes = [c for c in changes if c.setting_type == SettingType.WARM]
        cold_changes = [c for c in changes if c.setting_type == SettingType.COLD]
        destructive_changes = [c for c in changes if c.setting_type == SettingType.DESTRUCTIVE]

        # Validate destructive changes
        if destructive_changes and not dry_run:
            errors.append(
                f"Destructive changes require VM recreation: "
                f"{', '.join(c.field_path for c in destructive_changes)}"
            )
            return False, errors

        if dry_run:
            logger.info(f"Dry run: Would apply {len(changes)} changes")
            return True, []

        # Apply hot changes (VM can stay running)
        for change in hot_changes:
            try:
                if change.field_path == "cpu.cores":
                    self._apply_cpu_change(vm_name, change.new_value)
                elif change.field_path == "memory.size_mb":
                    if change.new_value <= change.old_value:
                        self._apply_memory_change(vm_name, change.new_value)
                    else:
                        errors.append("Memory increase requires VM restart")
            except Exception as e:
                errors.append(f"Failed to apply {change.field_path}: {e}")

        # Warm/cold changes require shutdown
        if warm_changes or cold_changes:
            errors.append("Some changes require VM restart. Shutdown the VM first.")

        return len(errors) == 0, errors

    def _apply_cpu_change(self, vm_name: str, new_cores: int):
        """Apply CPU core change using libvirt setvcpus."""
        import libvirt
        conn = libvirt.open('qemu:///system')
        dom = conn.lookupByName(vm_name)
        dom.setVcpusFlags(new_cores, libvirt.VIR_DOMAIN_AFFECT_LIVE)
        conn.close()

    def _apply_memory_change(self, vm_name: str, new_size_mb: int):
        """Apply memory change using libvirt setMemory."""
        import libvirt
        conn = libvirt.open('qemu:///system')
        dom = conn.lookupByName(vm_name)
        dom.setMemory(new_size_mb * 1024)  # Convert to KB
        conn.close()
```

---

## Part 2: Enhanced Settings Dialog with Tabs

Replace the basic Phase 1.2 dialog with a comprehensive tabbed interface.

**File**: `src/vm_manager/gui/dialogs/settings_dialog.py` (complete rewrite)

```python
"""
Enhanced VM Settings Dialog - Phase 3.1

Allows modification of VM configuration with:
- Hot settings (apply while running)
- Cold settings (require restart)
- Real-time validation
- Change preview with diff
- Rollback on failure
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

from pathlib import Path
from typing import Optional, List
import logging

from src.vm_manager.core.vm_config import VMConfig, ConfigChange, SettingType
from src.vm_manager.core.vm_lifecycle import VMLifecycleManager
from src.hardware_detect.gpu_scanner import GPUScanner

logger = logging.getLogger(__name__)


class SettingsDialog(Adw.Window):
    """
    Enhanced VM Settings Dialog.

    Features:
    - Tabbed interface for different setting categories
    - Real-time validation with inline errors
    - Preview changes before applying
    - Automatic restart prompts for cold settings
    - Rollback on failure
    """

    def __init__(self, vm_name: str, current_config: VMConfig, parent=None):
        super().__init__()
        self.set_title(f"Settings - {vm_name}")
        self.set_default_size(800, 600)
        self.set_modal(True)
        if parent:
            self.set_transient_for(parent)

        self.vm_name = vm_name
        self.original_config = current_config
        self.working_config = deepcopy(current_config)
        self.lifecycle_manager = VMLifecycleManager()

        self._build_ui()
        self._load_current_settings()

    def _build_ui(self):
        """Build the tabbed settings interface."""
        # Main container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(box)

        # Header bar
        header = Adw.HeaderBar()
        box.append(header)

        # Tab view
        self.tab_view = Adw.TabView()
        box.append(self.tab_view)

        # Tab bar
        tab_bar = Adw.TabBar(view=self.tab_view)
        box.prepend(tab_bar)

        # Add tabs
        self._add_cpu_tab()
        self._add_memory_tab()
        self._add_storage_tab()
        self._add_gpu_tab()
        self._add_audio_tab()
        self._add_usb_tab()
        self._add_network_tab()
        self._add_display_tab()

        # Bottom action bar with preview
        action_bar = Gtk.ActionBar()
        box.append(action_bar)

        # Change summary label
        self.summary_label = Gtk.Label(label="No changes")
        self.summary_label.set_xalign(0)
        action_bar.pack_start(self.summary_label)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: self.close())
        button_box.append(cancel_btn)

        self.preview_btn = Gtk.Button(label="Preview Changes")
        self.preview_btn.connect("clicked", self._on_preview_clicked)
        button_box.append(self.preview_btn)

        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", self._on_apply_clicked)
        button_box.append(self.apply_btn)

        action_bar.pack_end(button_box)

    def _add_cpu_tab(self):
        """CPU configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        # CPU Cores
        cores_group = Adw.PreferencesGroup()
        cores_group.set_title("CPU Allocation")
        cores_group.set_description("Hot-swappable: Changes apply immediately")

        self.cpu_cores_row = Adw.SpinRow(title="CPU Cores")
        self.cpu_cores_row.set_adjustment(Gtk.Adjustment(
            lower=1, upper=32, step_increment=1, value=4
        ))
        self.cpu_cores_row.connect("changed", self._on_setting_changed)
        cores_group.add(self.cpu_cores_row)

        # CPU Threads (requires restart)
        self.cpu_threads_row = Adw.SpinRow(title="Threads per Core")
        self.cpu_threads_row.set_subtitle("⚠️ Requires VM restart")
        self.cpu_threads_row.set_adjustment(Gtk.Adjustment(
            lower=1, upper=2, step_increment=1, value=1
        ))
        self.cpu_threads_row.connect("changed", self._on_setting_changed)
        cores_group.add(self.cpu_threads_row)

        page.append(cores_group)

        # CPU Pinning (advanced)
        pinning_group = Adw.PreferencesGroup()
        pinning_group.set_title("Advanced: CPU Pinning")
        pinning_group.set_description("Pin vCPUs to specific host cores for better performance")

        self.cpu_pinning_switch = Adw.SwitchRow(title="Enable CPU Pinning")
        pinning_group.add(self.cpu_pinning_switch)

        page.append(pinning_group)

        tab = self.tab_view.append(page)
        tab.set_title("CPU")
        tab.set_icon(Gio.ThemedIcon.new("cpu-symbolic"))

    def _add_memory_tab(self):
        """Memory configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        # Memory size
        mem_group = Adw.PreferencesGroup()
        mem_group.set_title("Memory Allocation")

        self.memory_row = Adw.SpinRow(title="RAM (GB)")
        self.memory_row.set_subtitle("Decrease: Hot-swap ✅ | Increase: Requires pause ⏸️")
        self.memory_row.set_adjustment(Gtk.Adjustment(
            lower=0.5, upper=128, step_increment=0.5, value=8
        ))
        self.memory_row.set_digits(1)
        self.memory_row.connect("changed", self._on_setting_changed)
        mem_group.add(self.memory_row)

        # Hugepages
        self.hugepages_switch = Adw.SwitchRow(
            title="Enable Hugepages",
            subtitle="Improves performance but requires VM restart"
        )
        self.hugepages_switch.connect("notify::active", self._on_setting_changed)
        mem_group.add(self.hugepages_switch)

        page.append(mem_group)

        tab = self.tab_view.append(page)
        tab.set_title("Memory")
        tab.set_icon(Gio.ThemedIcon.new("memory-symbolic"))

    def _add_storage_tab(self):
        """Storage configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        # Disk size
        storage_group = Adw.PreferencesGroup()
        storage_group.set_title("Virtual Disk")
        storage_group.set_description("⚠️ Disk expansion requires VM shutdown")

        self.storage_size_row = Adw.SpinRow(title="Disk Size (GB)")
        self.storage_size_row.set_adjustment(Gtk.Adjustment(
            lower=20, upper=2000, step_increment=10, value=100
        ))
        self.storage_size_row.connect("changed", self._on_setting_changed)
        storage_group.add(self.storage_size_row)

        # Current usage display
        self.storage_usage_label = Gtk.Label(label="Current usage: Unknown")
        self.storage_usage_label.set_xalign(0)
        storage_group.add(self.storage_usage_label)

        page.append(storage_group)

        tab = self.tab_view.append(page)
        tab.set_title("Storage")
        tab.set_icon(Gio.ThemedIcon.new("drive-harddisk-symbolic"))

    def _add_gpu_tab(self):
        """GPU passthrough configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        # GPU selection
        gpu_group = Adw.PreferencesGroup()
        gpu_group.set_title("GPU Passthrough")
        gpu_group.set_description("⚠️ Changing GPU requires VM recreation (DESTRUCTIVE)")

        # Detect GPUs
        scanner = GPUScanner()
        gpus = scanner.scan()

        self.gpu_combo_row = Adw.ComboRow(title="Select GPU")
        model = Gtk.StringList()
        model.append("None (Software Rendering)")
        for gpu in gpus:
            model.append(f"{gpu.device_name} ({gpu.pci_address})")
        self.gpu_combo_row.set_model(model)
        self.gpu_combo_row.connect("notify::selected", self._on_setting_changed)
        gpu_group.add(self.gpu_combo_row)

        page.append(gpu_group)

        tab = self.tab_view.append(page)
        tab.set_title("GPU")
        tab.set_icon(Gio.ThemedIcon.new("video-display-symbolic"))

    def _add_audio_tab(self):
        """Audio configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        audio_group = Adw.PreferencesGroup()
        audio_group.set_title("Audio Output")

        # Audio backend
        self.audio_backend_row = Adw.ComboRow(title="Audio Backend")
        audio_model = Gtk.StringList()
        audio_model.append("PulseAudio")
        audio_model.append("PipeWire")
        audio_model.append("None")
        self.audio_backend_row.set_model(audio_model)
        audio_group.add(self.audio_backend_row)

        page.append(audio_group)

        tab = self.tab_view.append(page)
        tab.set_title("Audio")
        tab.set_icon(Gio.ThemedIcon.new("audio-card-symbolic"))

    def _add_usb_tab(self):
        """USB passthrough configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        usb_group = Adw.PreferencesGroup()
        usb_group.set_title("USB Device Passthrough")
        usb_group.set_description("Pass specific USB devices to the VM")

        # TODO: List USB devices and allow selection
        placeholder = Gtk.Label(label="USB device list will be implemented here")
        usb_group.add(placeholder)

        page.append(usb_group)

        tab = self.tab_view.append(page)
        tab.set_title("USB")
        tab.set_icon(Gio.ThemedIcon.new("usb-symbolic"))

    def _add_network_tab(self):
        """Network configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        net_group = Adw.PreferencesGroup()
        net_group.set_title("Network Configuration")

        self.network_bridge_row = Adw.EntryRow(title="Bridge Interface")
        self.network_bridge_row.set_text("virbr0")
        net_group.add(self.network_bridge_row)

        page.append(net_group)

        tab = self.tab_view.append(page)
        tab.set_title("Network")
        tab.set_icon(Gio.ThemedIcon.new("network-wired-symbolic"))

    def _add_display_tab(self):
        """Display configuration tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        display_group = Adw.PreferencesGroup()
        display_group.set_title("Display Mode")

        self.display_mode_row = Adw.ComboRow(title="Display Type")
        display_model = Gtk.StringList()
        display_model.append("SPICE (Default)")
        display_model.append("Looking Glass (Low Latency)")
        display_model.append("VNC")
        self.display_mode_row.set_model(display_model)
        display_group.add(self.display_mode_row)

        page.append(display_group)

        tab = self.tab_view.append(page)
        tab.set_title("Display")
        tab.set_icon(Gio.ThemedIcon.new("video-display-symbolic"))

    def _load_current_settings(self):
        """Load current VM configuration into UI."""
        # CPU
        self.cpu_cores_row.set_value(self.original_config.cpu.cores)
        self.cpu_threads_row.set_value(self.original_config.cpu.threads)

        # Memory
        self.memory_row.set_value(self.original_config.memory.size_gb)
        self.hugepages_switch.set_active(self.original_config.memory.hugepages)

        # Storage
        if self.original_config.storage:
            self.storage_size_row.set_value(self.original_config.storage.size_gb)

    def _on_setting_changed(self, widget, *args):
        """Called when any setting is modified."""
        # Update working config from UI
        self.working_config.cpu.cores = int(self.cpu_cores_row.get_value())
        self.working_config.cpu.threads = int(self.cpu_threads_row.get_value())
        self.working_config.memory.size_mb = int(self.memory_row.get_value() * 1024)
        self.working_config.memory.hugepages = self.hugepages_switch.get_active()

        if self.working_config.storage:
            self.working_config.storage.size_gb = int(self.storage_size_row.get_value())

        # Update summary
        changes = self.original_config.diff(self.working_config)
        if changes:
            self.summary_label.set_markup(
                f"<b>{len(changes)} change(s)</b>: " +
                ", ".join(str(c) for c in changes[:3])
            )
            self.apply_btn.set_sensitive(True)
        else:
            self.summary_label.set_text("No changes")
            self.apply_btn.set_sensitive(False)

    def _on_preview_clicked(self, button):
        """Show detailed preview of all changes."""
        changes = self.original_config.diff(self.working_config)

        dialog = Adw.MessageDialog(transient_for=self, modal=True)
        dialog.set_heading("Preview Changes")

        if not changes:
            dialog.set_body("No changes to apply")
        else:
            body = "The following changes will be applied:\n\n"
            for change in changes:
                icon = "🔥" if change.setting_type == SettingType.HOT else "⏸️" if change.setting_type == SettingType.WARM else "🔄"
                body += f"{icon} {change}\n"
                if change.requires_restart:
                    body += "   ⚠️ Requires VM restart\n"
            dialog.set_body(body)

        dialog.add_response("ok", "OK")
        dialog.present()

    def _on_apply_clicked(self, button):
        """Apply configuration changes."""
        changes = self.original_config.diff(self.working_config)

        if not changes:
            return

        # Check if any changes are destructive
        destructive = [c for c in changes if c.setting_type == SettingType.DESTRUCTIVE]
        if destructive:
            dialog = Adw.MessageDialog(transient_for=self, modal=True)
            dialog.set_heading("Destructive Changes")
            dialog.set_body(
                f"The following changes require VM recreation:\n\n" +
                "\n".join(f"• {c}" for c in destructive) +
                "\n\n⚠️ ALL DATA IN THE VM WILL BE LOST. Continue?"
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("continue", "Recreate VM")
            dialog.set_response_appearance("continue", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_destructive_response, changes)
            dialog.present()
            return

        # Apply non-destructive changes
        try:
            success, errors = self.working_config.apply_changes(
                changes, self.vm_name, dry_run=False
            )

            if success:
                self._show_success_dialog()
                self.close()
            else:
                self._show_error_dialog(errors)
        except Exception as e:
            logger.exception("Failed to apply settings")
            self._show_error_dialog([str(e)])

    def _on_destructive_response(self, dialog, response, changes):
        """Handle response to destructive change warning."""
        if response == "continue":
            # User confirmed - recreate VM
            try:
                self.lifecycle_manager.destroy_vm(self.vm_name)
                self.lifecycle_manager.create_vm(self.working_config)
                self._show_success_dialog()
                self.close()
            except Exception as e:
                logger.exception("VM recreation failed")
                self._show_error_dialog([f"Recreation failed: {e}"])

    def _show_success_dialog(self):
        """Show success notification."""
        dialog = Adw.MessageDialog(transient_for=self, modal=True)
        dialog.set_heading("Settings Applied")
        dialog.set_body("VM configuration updated successfully")
        dialog.add_response("ok", "OK")
        dialog.present()

    def _show_error_dialog(self, errors: List[str]):
        """Show error dialog."""
        dialog = Adw.MessageDialog(transient_for=self, modal=True)
        dialog.set_heading("Failed to Apply Settings")
        dialog.set_body("\n".join(errors))
        dialog.add_response("ok", "OK")
        dialog.present()
```

---

## Part 3: Disk Expansion Implementation

**File**: `src/vm_manager/core/disk_operations.py` (new file)

```python
"""
Disk expansion utilities.

Supports:
- qcow2 image expansion (qemu-img resize)
- Filesystem expansion (NTFS, ext4)
- Safety checks (backup creation)
"""

import subprocess
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


class DiskExpander:
    """Handles safe disk expansion for VM images."""

    @staticmethod
    def expand_qcow2(image_path: Path, new_size_gb: int) -> Tuple[bool, str]:
        """
        Expand a qcow2 image file.

        Args:
            image_path: Path to qcow2 image
            new_size_gb: New size in GB

        Returns:
            Tuple of (success, message)
        """
        if not image_path.exists():
            return False, f"Image not found: {image_path}"

        # Get current size
        result = subprocess.run(
            ["qemu-img", "info", "--output=json", str(image_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return False, f"Failed to get image info: {result.stderr}"

        import json
        info = json.loads(result.stdout)
        current_size_gb = info["virtual-size"] / (1024**3)

        if new_size_gb <= current_size_gb:
            return False, f"New size ({new_size_gb}GB) must be larger than current ({current_size_gb:.1f}GB)"

        # Expand image
        logger.info(f"Expanding {image_path} from {current_size_gb:.1f}GB to {new_size_gb}GB")

        result = subprocess.run(
            ["qemu-img", "resize", str(image_path), f"{new_size_gb}G"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return False, f"Resize failed: {result.stderr}"

        return True, f"Image expanded successfully. Boot VM and expand filesystem from guest OS."
```

---

## Part 4: Testing

**File**: `tests/test_settings_dialog.py` (new file)

```python
"""Tests for Phase 3.1: Settings Dialog."""

import pytest
from unittest.mock import Mock, patch
from src.vm_manager.core.vm_config import VMConfig, VMType, SettingType, ConfigChange
from src.vm_manager.gui.dialogs.settings_dialog import SettingsDialog


def test_config_diff_cpu_cores():
    """Test CPU core change detection."""
    config1 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config1.cpu.cores = 4

    config2 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config2.cpu.cores = 6

    changes = config1.diff(config2)

    assert len(changes) == 1
    assert changes[0].field_path == "cpu.cores"
    assert changes[0].old_value == 4
    assert changes[0].new_value == 6
    assert changes[0].setting_type == SettingType.HOT


def test_config_diff_memory_increase():
    """Test memory increase requires warm restart."""
    config1 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config1.memory.size_mb = 8192

    config2 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config2.memory.size_mb = 16384

    changes = config1.diff(config2)

    assert len(changes) == 1
    assert changes[0].setting_type == SettingType.WARM
    assert changes[0].requires_restart


def test_config_diff_gpu_destructive():
    """Test GPU change is marked as destructive."""
    config1 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config1.gpu.pci_address = "0000:01:00.0"

    config2 = VMConfig(name="test", vm_type=VMType.WINDOWS)
    config2.gpu.pci_address = "0000:02:00.0"

    changes = config1.diff(config2)

    assert len(changes) == 1
    assert changes[0].setting_type == SettingType.DESTRUCTIVE
    assert changes[0].risk_level == "high"


@pytest.mark.gui
def test_settings_dialog_creation():
    """Test settings dialog can be created."""
    config = VMConfig(name="TestVM", vm_type=VMType.WINDOWS)

    dialog = SettingsDialog("TestVM", config)

    assert dialog is not None
    assert dialog.vm_name == "TestVM"
    assert dialog.original_config == config
```

---

## Verification Checklist

Before marking Phase 3.1 complete, verify:

- [ ] **Settings dialog opens** - Click "Settings" on any VM
- [ ] **All tabs load** - CPU, Memory, Storage, GPU, Audio, USB, Network, Display
- [ ] **CPU cores hot-swap** - Change cores while VM running → Applies immediately
- [ ] **Memory hot-swap** - Decrease memory → Applies immediately
- [ ] **Memory warm-swap** - Increase memory → Prompts for pause/restart
- [ ] **Storage expansion** - Increase disk size → Prompts for shutdown
- [ ] **GPU change warning** - Changing GPU → Shows destructive warning
- [ ] **Change preview** - "Preview Changes" button shows diff dialog
- [ ] **Change summary** - Bottom bar shows "N changes: X → Y"
- [ ] **Validation** - Invalid settings (e.g., 0 cores) → Shows error
- [ ] **Rollback** - If apply fails → VM still works with old settings
- [ ] **No data loss** - Hot/warm changes → No VM recreation needed

---

## Acceptance Criteria

✅ **Phase 3.1 is COMPLETE when**:
1. Users can modify CPU/RAM without VM destruction
2. Storage expansion works and prompts for restart
3. GPU changes warn about data loss and require confirmation
4. All changes show preview before applying
5. Failed settings application rolls back automatically
6. Settings persist after VM restart

❌ **Phase 3.1 FAILS if**:
1. Any setting change requires VM recreation (except GPU)
2. Changes apply without user confirmation
3. No rollback on failure → VM becomes broken
4. Missing validation → Invalid configs crash VM

---

## Risks & Mitigations

### Risk 1: Hot CPU change crashes VM
**Mitigation**: Use libvirt's setvcpusFlags with VIR_DOMAIN_AFFECT_LIVE flag, which is safe for running VMs.

### Risk 2: Disk expansion corrupts filesystem
**Mitigation**: Only expand image file. User must expand filesystem from guest OS (Windows Disk Management, Linux resize2fs).

### Risk 3: Memory hot-add not supported on some kernels
**Mitigation**: Detect if hot-add is supported. If not, downgrade to WARM (requires pause).

---

## Next Steps

This phase unlocks:
- **Phase 3.2**: Error handling can now show specific setting validation errors
- **Phase 4.1**: Testing framework can test hot-swap scenarios
- **Production readiness**: Users no longer recreate VMs for simple changes

---

## Resources

- [Libvirt Domain XML Format](https://libvirt.org/formatdomain.html)
- [qemu-img resize](https://qemu.readthedocs.io/en/latest/tools/qemu-img.html)
- [GTK4 Adwaita Widgets](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/)

Good luck! 🚀
