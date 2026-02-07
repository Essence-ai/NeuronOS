#!/usr/bin/env python3
"""
NeuronOS VM Manager GUI - GTK4/Adwaita Application

Full implementation of the VM Manager with:
- VM listing and management
- VM creation wizard
- GPU passthrough configuration
- Looking Glass integration
- USB passthrough
"""

from __future__ import annotations

import logging
import sys
import re
import subprocess
import threading
from pathlib import Path
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# VM name validation pattern - follows libvirt naming rules
# Must start with alphanumeric, contain only alphanumeric, underscore, hyphen, or period
# Maximum 64 characters
VM_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,63}$')


def _validate_vm_name(name: str) -> bool:
    """
    Validate VM name follows libvirt naming rules.
    
    Prevents command injection by ensuring only safe characters are allowed.
    
    Args:
        name: VM name to validate
        
    Returns:
        True if name is valid, False otherwise
    """
    if not name or len(name) > 64:
        return False
    return bool(VM_NAME_PATTERN.match(name))

# GTK4 imports - will only work on Linux with GTK4 installed
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gio, GLib, Gdk  # noqa: E402, F401
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False
    Gtk = None
    Adw = None

# Import our modules
try:
    sys.path.insert(0, '/usr/lib/neuron-os')
    from hardware_detect.gpu_scanner import GPUScanner
    from hardware_detect.iommu_parser import IOMMUParser
    from vm_manager.core.libvirt_manager import LibvirtManager
    from vm_manager.core.looking_glass import get_looking_glass_manager  # noqa: F401
    from vm_manager.core.vm_config import VMConfig  # noqa: F401
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    GPUScanner = None
    LibvirtManager = None


@dataclass
class VMInfo:
    """Information about a virtual machine."""
    name: str
    uuid: str
    state: str
    memory_mb: int
    vcpus: int
    has_gpu: bool
    has_looking_glass: bool


if GTK_AVAILABLE:
    class ThemeManager:
        """Manages GTK CSS themes at runtime."""
        
        def __init__(self):
            self.provider = Gtk.CssProvider()
            self.display = Gdk.Display.get_default() if Gtk else None
            self.themes_dir = Path(__file__).parent / "themes"
            self.current_theme = "neuron"

        def apply_theme(self, theme_name: str):
            """Load and apply a CSS theme."""
            theme_file = self.themes_dir / f"{theme_name}.css"
            if not theme_file.exists():
                logger.error(f"Theme file not found: {theme_file}")
                return

            try:
                # Remove prior provider if any (Gtk4 handles this by adding/removing providers)
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(),
                    self.provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                
                with open(theme_file, "r") as f:
                    css_data = f.read()
                    self.provider.load_from_data(css_data, len(css_data))
                
                self.current_theme = theme_name
                logger.info(f"Applied theme: {theme_name}")
            except Exception as e:
                logger.error(f"Failed to apply theme {theme_name}: {e}")

    class VMCard(Gtk.Box):
        """A card widget displaying VM information."""

        def __init__(self, vm_info: VMInfo, on_start=None, on_stop=None, on_delete=None):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.vm_info = vm_info
            self._on_start = on_start
            self._on_stop = on_stop
            self._on_delete = on_delete

            self.add_css_class("vm-card") # Changed from "card" to "vm-card" for our themes
            self.set_margin_start(12)
            self.set_margin_end(12)
            self.set_margin_top(6)
            self.set_margin_bottom(6)

            self._build_ui()

        def _build_ui(self):
            # Header with name and status
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            header_box.set_margin_start(12)
            header_box.set_margin_end(12)
            header_box.set_margin_top(12)

            # VM Icon
            icon = Gtk.Image.new_from_icon_name("computer-symbolic")
            icon.set_pixel_size(32)
            header_box.append(icon)

            # Name and status
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            name_label = Gtk.Label(label=self.vm_info.name)
            name_label.add_css_class("title-3")
            name_label.set_halign(Gtk.Align.START)
            info_box.append(name_label)

            status_label = Gtk.Label(label=self._get_status_text())
            status_label.add_css_class("dim-label")
            if self.vm_info.state == "running":
                status_label.add_css_class("status-running")
            status_label.set_halign(Gtk.Align.START)
            info_box.append(status_label)

            header_box.append(info_box)

            # Status indicator
            status_icon = Gtk.Image.new_from_icon_name(self._get_status_icon())
            status_icon.set_halign(Gtk.Align.END)
            status_icon.set_hexpand(True)
            header_box.append(status_icon)

            self.append(header_box)

            # Specs row
            specs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            specs_box.set_margin_start(12)
            specs_box.set_margin_end(12)

            # Memory
            mem_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            mem_icon = Gtk.Image.new_from_icon_name("memory-symbolic")
            mem_box.append(mem_icon)
            mem_label = Gtk.Label(label=f"{self.vm_info.memory_mb // 1024} GB RAM")
            mem_box.append(mem_label)
            specs_box.append(mem_box)

            # CPUs
            cpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            cpu_icon = Gtk.Image.new_from_icon_name("cpu-symbolic")
            cpu_box.append(cpu_icon)
            cpu_label = Gtk.Label(label=f"{self.vm_info.vcpus} vCPUs")
            cpu_box.append(cpu_label)
            specs_box.append(cpu_box)

            # GPU badge
            if self.vm_info.has_gpu:
                gpu_badge = Gtk.Label(label="GPU")
                gpu_badge.add_css_class("success")
                specs_box.append(gpu_badge)

            # Looking Glass badge
            if self.vm_info.has_looking_glass:
                lg_badge = Gtk.Label(label="Looking Glass")
                lg_badge.add_css_class("accent")
                specs_box.append(lg_badge)

            self.append(specs_box)

            # Action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            button_box.set_margin_start(12)
            button_box.set_margin_end(12)
            button_box.set_margin_bottom(12)
            button_box.set_halign(Gtk.Align.END)

            if self.vm_info.state == "running":
                stop_btn = Gtk.Button(label="Stop")
                stop_btn.add_css_class("destructive-action")
                stop_btn.connect("clicked", self._on_stop_clicked)
                button_box.append(stop_btn)

                open_btn = Gtk.Button(label="Open Display")
                open_btn.add_css_class("suggested-action")
                open_btn.connect("clicked", self._on_open_clicked)
                button_box.append(open_btn)
            else:
                start_btn = Gtk.Button(label="Start")
                start_btn.add_css_class("suggested-action")
                start_btn.connect("clicked", self._on_start_clicked)
                button_box.append(start_btn)

                delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                delete_btn.add_css_class("flat")
                delete_btn.connect("clicked", self._on_delete_clicked)
                button_box.append(delete_btn)

            self.append(button_box)

        def _get_status_text(self) -> str:
            if self.vm_info.state == "running":
                return "Running"
            elif self.vm_info.state == "paused":
                return "Paused"
            else:
                return "Stopped"

        def _get_status_icon(self) -> str:
            if self.vm_info.state == "running":
                return "media-playback-start-symbolic"
            elif self.vm_info.state == "paused":
                return "media-playback-pause-symbolic"
            else:
                return "media-playback-stop-symbolic"

        def _on_start_clicked(self, button):
            if self._on_start:
                self._on_start(self.vm_info)

        def _on_stop_clicked(self, button):
            if self._on_stop:
                self._on_stop(self.vm_info)

        def _on_delete_clicked(self, button):
            if self._on_delete:
                self._on_delete(self.vm_info)

        def _on_open_clicked(self, button):
            """Open VM display safely."""
            if self.vm_info.has_looking_glass:
                lg_manager = get_looking_glass_manager()
                lg_manager.start(self.vm_info.name)
            else:
                # SECURITY: Validate VM name before execution to prevent command injection
                if not _validate_vm_name(self.vm_info.name):
                    logger.error(f"Invalid VM name rejected: {self.vm_info.name!r}")
                    return

                # SECURITY: Use subprocess with list args instead of shell
                try:
                    subprocess.Popen(
                        ["virt-viewer", "-c", "qemu:///system", self.vm_info.name],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    logger.error("virt-viewer not installed")
                except Exception as e:
                    logger.error(f"Failed to launch virt-viewer: {e}")


    class CreateVMDialog(Adw.Window):
        """Dialog for creating a new virtual machine."""

        def __init__(self, parent: Gtk.Window, on_create=None):
            super().__init__()
            self.set_transient_for(parent)
            self.set_modal(True)
            self.set_title("Create Virtual Machine")
            self.set_default_size(600, 700)

            self._on_create = on_create
            self._gpu_scanner = GPUScanner() if MODULES_AVAILABLE else None
            self._available_gpus = []

            self._build_ui()
            self._scan_hardware()

        def _build_ui(self):
            # Main layout
            toolbar_view = Adw.ToolbarView()

            # Header bar
            header = Adw.HeaderBar()
            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", lambda b: self.close())
            header.pack_start(cancel_btn)

            create_btn = Gtk.Button(label="Create")
            create_btn.add_css_class("suggested-action")
            create_btn.connect("clicked", self._on_create_clicked)
            header.pack_end(create_btn)

            toolbar_view.add_top_bar(header)

            # Scrollable content
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            content_box.set_margin_start(24)
            content_box.set_margin_end(24)
            content_box.set_margin_top(24)
            content_box.set_margin_bottom(24)

            # VM Type selection
            type_group = Adw.PreferencesGroup(title="Virtual Machine Type")

            self.type_combo = Adw.ComboRow(title="Operating System")
            type_model = Gtk.StringList.new(["Windows 11", "Windows 10", "Linux", "macOS (Experimental)"])
            self.type_combo.set_model(type_model)
            type_group.add(self.type_combo)

            self.name_entry = Adw.EntryRow(title="VM Name")
            self.name_entry.set_text("Windows 11")
            type_group.add(self.name_entry)

            content_box.append(type_group)

            # Resources
            res_group = Adw.PreferencesGroup(title="Resources")

            # Memory slider
            self.memory_row = Adw.ActionRow(title="Memory", subtitle="8 GB")
            memory_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2, 64, 2)
            memory_scale.set_value(8)
            memory_scale.set_size_request(200, -1)
            memory_scale.connect("value-changed", self._on_memory_changed)
            self.memory_row.add_suffix(memory_scale)
            res_group.add(self.memory_row)

            # CPU slider
            self.cpu_row = Adw.ActionRow(title="CPU Cores", subtitle="4 cores")
            cpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 16, 1)
            cpu_scale.set_value(4)
            cpu_scale.set_size_request(200, -1)
            cpu_scale.connect("value-changed", self._on_cpu_changed)
            self.cpu_row.add_suffix(cpu_scale)
            res_group.add(self.cpu_row)

            # Disk size
            self.disk_row = Adw.ActionRow(title="Disk Size", subtitle="128 GB")
            disk_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 32, 512, 32)
            disk_scale.set_value(128)
            disk_scale.set_size_request(200, -1)
            disk_scale.connect("value-changed", self._on_disk_changed)
            self.disk_row.add_suffix(disk_scale)
            res_group.add(self.disk_row)

            content_box.append(res_group)

            # GPU Passthrough
            gpu_group = Adw.PreferencesGroup(title="GPU Passthrough")

            self.gpu_switch = Adw.SwitchRow(title="Enable GPU Passthrough")
            self.gpu_switch.set_subtitle("Pass dedicated GPU to VM for near-native performance")
            self.gpu_switch.connect("notify::active", self._on_gpu_toggled)
            gpu_group.add(self.gpu_switch)

            self.gpu_combo = Adw.ComboRow(title="Select GPU")
            self.gpu_combo.set_sensitive(False)
            gpu_group.add(self.gpu_combo)

            content_box.append(gpu_group)

            # Looking Glass
            lg_group = Adw.PreferencesGroup(title="Display")

            self.lg_switch = Adw.SwitchRow(title="Enable Looking Glass")
            self.lg_switch.set_subtitle("Low-latency display for seamless experience (requires GPU passthrough)")
            self.lg_switch.set_sensitive(False)
            lg_group.add(self.lg_switch)

            content_box.append(lg_group)

            # Installation Media
            iso_group = Adw.PreferencesGroup(title="Installation Media")

            self.iso_row = Adw.ActionRow(title="Windows ISO")
            self.iso_row.set_subtitle("No ISO selected")
            iso_btn = Gtk.Button(label="Browse...")
            iso_btn.set_valign(Gtk.Align.CENTER)
            iso_btn.connect("clicked", self._on_browse_iso)
            self.iso_row.add_suffix(iso_btn)
            iso_group.add(self.iso_row)

            content_box.append(iso_group)

            scroll.set_child(content_box)
            toolbar_view.set_content(scroll)
            self.set_content(toolbar_view)

        def _scan_hardware(self):
            """Scan for available GPUs in background."""
            def scan():
                if self._gpu_scanner:
                    try:
                        gpus = self._gpu_scanner.scan()
                        # Filter to non-boot GPUs
                        passthrough_gpus = [g for g in gpus if not g.is_boot_vga]
                        GLib.idle_add(self._update_gpu_list, passthrough_gpus)
                    except Exception as e:
                        logger.error(f"GPU scan failed: {e}")

            thread = threading.Thread(target=scan, daemon=True)
            thread.start()

        def _update_gpu_list(self, gpus):
            """Update GPU combo box with available GPUs."""
            self._available_gpus = gpus
            if gpus:
                gpu_names = [f"{g.vendor_name} {g.device_name}" for g in gpus]
                model = Gtk.StringList.new(gpu_names)
                self.gpu_combo.set_model(model)
            else:
                model = Gtk.StringList.new(["No passthrough GPUs available"])
                self.gpu_combo.set_model(model)
                self.gpu_switch.set_sensitive(False)

        def _on_memory_changed(self, scale):
            value = int(scale.get_value())
            self.memory_row.set_subtitle(f"{value} GB")

        def _on_cpu_changed(self, scale):
            value = int(scale.get_value())
            self.cpu_row.set_subtitle(f"{value} cores")

        def _on_disk_changed(self, scale):
            value = int(scale.get_value())
            self.disk_row.set_subtitle(f"{value} GB")

        def _on_gpu_toggled(self, switch, param):
            active = switch.get_active()
            self.gpu_combo.set_sensitive(active)
            self.lg_switch.set_sensitive(active)
            if active:
                self.lg_switch.set_active(True)

        def _on_browse_iso(self, button):
            dialog = Gtk.FileDialog()
            dialog.set_title("Select Windows ISO")

            filter_iso = Gtk.FileFilter()
            filter_iso.set_name("ISO Images")
            filter_iso.add_pattern("*.iso")

            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_iso)
            dialog.set_filters(filters)

            dialog.open(self, None, self._on_iso_selected)

        def _on_iso_selected(self, dialog, result):
            try:
                file = dialog.open_finish(result)
                if file:
                    path = file.get_path()
                    self.iso_row.set_subtitle(Path(path).name)
                    self._selected_iso = path
            except Exception:
                pass

        def _on_create_clicked(self, button):
            """Create the VM with selected settings."""
            if self._on_create:
                config = {
                    "name": self.name_entry.get_text(),
                    "type": self.type_combo.get_selected(),
                    "memory_gb": int(self.memory_row.get_subtitle().split()[0]),
                    "cpus": int(self.cpu_row.get_subtitle().split()[0]),
                    "disk_gb": int(self.disk_row.get_subtitle().split()[0]),
                    "gpu_passthrough": self.gpu_switch.get_active(),
                    "looking_glass": self.lg_switch.get_active(),
                    "iso_path": getattr(self, '_selected_iso', None),
                }
                if self.gpu_switch.get_active() and self._available_gpus:
                    config["gpu"] = self._available_gpus[self.gpu_combo.get_selected()]
                self._on_create(config)
            self.close()


    class VMManagerWindow(Adw.ApplicationWindow):
        """Main application window."""

        def __init__(self, app: Adw.Application):
            super().__init__(application=app)

            self.set_title("NeuronOS VM Manager")
            self.set_default_size(1200, 800)

            self._libvirt_manager = None
            self._vms: List[VMInfo] = []

            self._build_ui()
            self._load_vms()

        def _build_ui(self) -> None:
            """Build the main UI."""
            # Toolbar view
            toolbar_view = Adw.ToolbarView()

            # Header bar
            header = Adw.HeaderBar()

            # New VM button
            new_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
            new_btn.set_tooltip_text("Create new VM")
            new_btn.connect("clicked", self._on_new_vm_clicked)
            header.pack_start(new_btn)

            # Theme Switcher
            self.theme_combo = Adw.ComboRow(title="Appearance")
            self.theme_combo.set_model(Gtk.StringList.new(["Neuron", "Windows 11", "macOS"]))
            self.theme_combo.connect("notify::selected", self._on_theme_changed)
            # Find a way to put it in the header or a popover
            theme_btn = Gtk.MenuButton()
            theme_btn.set_icon_name("preferences-desktop-theme-symbolic")
            
            popover = Gtk.Popover()
            pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            pop_box.set_margin_all(6)
            
            theme_title = Gtk.Label(label="Select Theme")
            theme_title.add_css_class("title-4")
            pop_box.append(theme_title)
            
            for i, name in enumerate(["Neuron", "Windows 11", "macOS"]):
                btn = Gtk.Button(label=name)
                btn.connect("clicked", lambda b, idx=i: self._on_theme_btn_clicked(idx))
                pop_box.append(btn)
                
            popover.set_child(pop_box)
            theme_btn.set_popover(popover)
            header.pack_end(theme_btn)

            # Refresh button
            refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
            refresh_btn.set_tooltip_text("Refresh VM list")
            refresh_btn.connect("clicked", lambda b: self._load_vms())
            header.pack_start(refresh_btn)

            # Settings button
            settings_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
            settings_btn.set_tooltip_text("Settings")
            settings_btn.connect("clicked", self._on_settings_clicked)
            header.pack_end(settings_btn)

            toolbar_view.add_top_bar(header)

            # Main content - scrollable VM list
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

            self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.content_box.add_css_class("window-content") # Added for theme backgrounds
            self.content_box.set_margin_start(24)
            self.content_box.set_margin_end(24)
            self.content_box.set_margin_top(24)
            self.content_box.set_margin_bottom(24)

            # Header section
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

            title = Gtk.Label(label="Virtual Machines")
            title.add_css_class("title-1")
            title.set_halign(Gtk.Align.START)
            header_box.append(title)

            self.content_box.append(header_box)

            # System status banner
            self.status_banner = self._create_status_banner()
            self.content_box.append(self.status_banner)

            # VM list container
            self.vm_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.content_box.append(self.vm_list_box)

            scroll.set_child(self.content_box)
            toolbar_view.set_content(scroll)
            self.set_content(toolbar_view)
            
            # Application instance theme manager
            self.theme_manager = ThemeManager()
            self.theme_manager.apply_theme("neuron")

        def _on_theme_btn_clicked(self, index):
            themes = ["neuron", "win11", "macos"]
            self.theme_manager.apply_theme(themes[index])

        def _on_theme_changed(self, combo, param):
            idx = combo.get_selected()
            themes = ["neuron", "win11", "macos"]
            self.theme_manager.apply_theme(themes[idx])

        def _create_status_banner(self) -> Gtk.Widget:
            """Create system status banner."""
            banner = Adw.Banner()
            banner.set_title("Checking GPU passthrough status...")
            banner.set_revealed(True)

            # Check status in background
            def check_status():
                gpu_ok = False
                iommu_ok = False

                if MODULES_AVAILABLE:
                    try:
                        scanner = GPUScanner()
                        gpus = scanner.scan()
                        gpu_ok = any(not g.is_boot_vga for g in gpus)

                        parser = IOMMUParser()
                        parser.parse_all()
                        iommu_ok = len(parser.groups) > 0
                    except Exception:
                        pass

                GLib.idle_add(self._update_status_banner, gpu_ok, iommu_ok)

            thread = threading.Thread(target=check_status, daemon=True)
            thread.start()

            return banner

        def _update_status_banner(self, gpu_ok: bool, iommu_ok: bool):
            """Update status banner with results."""
            if gpu_ok and iommu_ok:
                self.status_banner.set_title("✓ GPU passthrough ready")
                self.status_banner.add_css_class("success")
            elif iommu_ok:
                self.status_banner.set_title("⚠ IOMMU enabled, but no passthrough GPU detected")
            else:
                self.status_banner.set_title("⚠ IOMMU not enabled - GPU passthrough unavailable")
                self.status_banner.set_button_label("Learn More")

        def _load_vms(self):
            """Load VMs from libvirt."""
            # Clear existing
            child = self.vm_list_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.vm_list_box.remove(child)
                child = next_child

            # Load VMs in background
            def load():
                vms = []
                if MODULES_AVAILABLE:
                    try:
                        manager = LibvirtManager()
                        manager.connect()
                        for vm in manager.list_vms():
                            vms.append(VMInfo(
                                name=vm.name,
                                uuid=vm.uuid,
                                state=vm.state.value if hasattr(vm.state, 'value') else str(vm.state),
                                memory_mb=vm.memory_mb,
                                vcpus=vm.vcpus,
                                has_gpu=vm.has_gpu_passthrough,
                                has_looking_glass=vm.has_looking_glass,
                            ))
                    except Exception as e:
                        logger.error(f"Failed to load VMs: {e}")

                GLib.idle_add(self._display_vms, vms)

            thread = threading.Thread(target=load, daemon=True)
            thread.start()

        def _display_vms(self, vms: List[VMInfo]):
            """Display loaded VMs."""
            self._vms = vms

            if not vms:
                # Show empty state
                status = Adw.StatusPage()
                status.set_title("No Virtual Machines")
                status.set_description("Create your first VM to get started")
                status.set_icon_name("computer-symbolic")

                create_btn = Gtk.Button(label="Create Virtual Machine")
                create_btn.add_css_class("suggested-action")
                create_btn.add_css_class("pill")
                create_btn.set_halign(Gtk.Align.CENTER)
                create_btn.connect("clicked", self._on_new_vm_clicked)
                status.set_child(create_btn)

                self.vm_list_box.append(status)
            else:
                for vm in vms:
                    card = VMCard(
                        vm,
                        on_start=self._on_start_vm,
                        on_stop=self._on_stop_vm,
                        on_delete=self._on_delete_vm,
                    )
                    self.vm_list_box.append(card)

        def _on_new_vm_clicked(self, button: Gtk.Button) -> None:
            """Handle new VM button click."""
            dialog = CreateVMDialog(self, on_create=self._create_vm)
            dialog.present()

        def _create_vm(self, config: dict):
            """Create a new VM with the given configuration."""
            logger.info(f"Creating VM: {config}")

            # Show progress toast
            toast = Adw.Toast.new(f"Creating VM: {config['name']}...")
            toast.set_timeout(0)  # Don't auto-dismiss
            self.add_toast(toast)

            # Run creation in background
            def create():
                try:
                    if not MODULES_AVAILABLE:
                        GLib.idle_add(self._show_error, "VM modules not available")
                        return

                    from vm_manager.core.vm_config import VMConfig, VMType
                    
                    # Map UI selection to VMType
                    vm_type_map = {
                        0: VMType.WINDOWS,   # Windows 11
                        1: VMType.WINDOWS,   # Windows 10
                        2: VMType.LINUX,
                        3: VMType.MACOS,
                    }

                    # Build VM configuration
                    vm_config = VMConfig(
                        name=config['name'],
                        vm_type=vm_type_map.get(config.get('type', 0), VMType.WINDOWS),
                    )
                    
                    # Set resources
                    vm_config.cpu.cores = config.get('cpus', 4)
                    vm_config.memory.size_mb = config.get('memory_gb', 8) * 1024
                    
                    # Set storage
                    if hasattr(vm_config, 'storage'):
                        vm_config.storage.size_gb = config.get('disk_gb', 128)

                    # Add GPU passthrough if selected
                    if config.get('gpu_passthrough') and config.get('gpu'):
                        from vm_manager.core.vm_config import GPUPassthroughConfig
                        gpu = config['gpu']
                        vm_config.gpu = GPUPassthroughConfig(
                            enabled=True,
                            pci_address=getattr(gpu, 'pci_address', None),
                        )

                    # Add Looking Glass if selected
                    if config.get('looking_glass'):
                        from vm_manager.core.vm_config import LookingGlassConfig
                        vm_config.looking_glass = LookingGlassConfig(enabled=True)

                    # Create VM using LibvirtManager
                    manager = LibvirtManager()
                    manager.connect()
                    
                    # Generate XML and define VM
                    success = manager.create_vm(vm_config)

                    if success:
                        GLib.idle_add(self._on_vm_created, config['name'])
                    else:
                        GLib.idle_add(self._show_error, "VM creation failed")

                except Exception as e:
                    logger.error(f"VM creation error: {e}")
                    GLib.idle_add(self._show_error, str(e))

            thread = threading.Thread(target=create, daemon=True)
            thread.start()

        def _on_vm_created(self, vm_name: str):
            """Called when VM creation succeeds."""
            toast = Adw.Toast.new(f"VM '{vm_name}' created successfully!")
            self.add_toast(toast)
            self._load_vms()

        def _show_error(self, message: str):
            """Show error toast."""
            toast = Adw.Toast.new(f"Error: {message}")
            self.add_toast(toast)

        def _on_start_vm(self, vm: VMInfo):
            """Start a VM."""
            logger.info(f"Starting VM: {vm.name}")
            if MODULES_AVAILABLE:
                try:
                    manager = LibvirtManager()
                    manager.connect()
                    manager.start_vm(vm.name)

                    # Start Looking Glass if enabled
                    if vm.has_looking_glass:
                        lg_manager = get_looking_glass_manager()
                        lg_manager.start(vm.name, wait_for_shmem=True)

                    self._load_vms()
                except Exception as e:
                    logger.error(f"Failed to start VM: {e}")

        def _on_stop_vm(self, vm: VMInfo):
            """Stop a VM."""
            logger.info(f"Stopping VM: {vm.name}")
            if MODULES_AVAILABLE:
                try:
                    manager = LibvirtManager()
                    manager.connect()
                    manager.stop_vm(vm.name)

                    # Stop Looking Glass
                    lg_manager = get_looking_glass_manager()
                    lg_manager.stop(vm.name)

                    self._load_vms()
                except Exception as e:
                    logger.error(f"Failed to stop VM: {e}")

        def _on_delete_vm(self, vm: VMInfo):
            """Delete a VM."""
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=f"Delete {vm.name}?",
                body="This will permanently delete the VM and its disk. This action cannot be undone.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("delete", "Delete")
            dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_delete_response, vm)
            dialog.present()

        def _on_delete_response(self, dialog, response, vm):
            if response == "delete":
                logger.info(f"Deleting VM: {vm.name}")
                if MODULES_AVAILABLE:
                    try:
                        manager = LibvirtManager()
                        manager.connect()
                        manager.delete_vm(vm.name, delete_storage=True)
                        toast = Adw.Toast.new(f"VM '{vm.name}' deleted")
                        self.add_toast(toast)
                    except Exception as e:
                        logger.error(f"Failed to delete VM: {e}")
                        self._show_error(f"Failed to delete VM: {e}")
                self._load_vms()

        def _on_settings_clicked(self, button):
            """Open settings dialog."""
            dialog = Adw.PreferencesWindow(transient_for=self)
            dialog.set_title("VM Manager Settings")

            # General page
            general_page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")

            # Connection group
            conn_group = Adw.PreferencesGroup(title="Libvirt Connection")
            uri_row = Adw.ActionRow(title="Connection URI", subtitle="qemu:///system")
            uri_row.set_activatable(False)
            conn_group.add(uri_row)
            general_page.add(conn_group)

            # VM defaults group
            defaults_group = Adw.PreferencesGroup(title="VM Defaults")
            ram_row = Adw.SpinRow.new_with_range(1024, 65536, 1024)
            ram_row.set_title("Default RAM (MB)")
            ram_row.set_value(8192)
            defaults_group.add(ram_row)

            cpu_row = Adw.SpinRow.new_with_range(1, 32, 1)
            cpu_row.set_title("Default CPU Cores")
            cpu_row.set_value(4)
            defaults_group.add(cpu_row)
            general_page.add(defaults_group)

            # Display group
            display_group = Adw.PreferencesGroup(title="Display")
            lg_row = Adw.SwitchRow(title="Auto-start Looking Glass", subtitle="Start Looking Glass when launching GPU-passthrough VMs")
            lg_row.set_active(True)
            display_group.add(lg_row)
            general_page.add(display_group)

            dialog.add(general_page)
            dialog.present()


    class VMManagerApp(Adw.Application):
        """Main application class."""

        def __init__(self):
            super().__init__(
                application_id="org.neuronos.vmmanager",
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )

        def do_activate(self) -> None:
            """Activate the application."""
            win = VMManagerWindow(self)
            win.present()


def main() -> int:
    """Main entry point."""
    if not GTK_AVAILABLE:
        print("GTK4 is not available. This application requires:")
        print("  - Linux operating system")
        print("  - GTK4 and libadwaita installed")
        print("  - PyGObject with GTK4 bindings")
        print()
        print("Install with: pacman -S gtk4 libadwaita python-gobject")
        return 1

    app = VMManagerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
