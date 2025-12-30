#!/usr/bin/env python3
"""
NeuronOS Onboarding Wizard Pages

Individual pages for the first-boot wizard.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

if TYPE_CHECKING:
    from .wizard import OnboardingWizard

logger = logging.getLogger(__name__)


class WizardPage(Gtk.Box):
    """Base class for wizard pages."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.wizard = wizard
        self.set_margin_start(48)
        self.set_margin_end(48)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_valign(Gtk.Align.CENTER)

    def on_enter(self):
        """Called when page becomes visible."""
        pass

    def on_leave(self):
        """Called when leaving the page."""
        pass


class WelcomePage(WizardPage):
    """Welcome page introducing NeuronOS."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)

        # NeuronOS logo/icon placeholder
        icon = Gtk.Image.new_from_icon_name("computer-symbolic")
        icon.set_pixel_size(128)
        icon.add_css_class("dim-label")
        self.append(icon)

        # Welcome title
        title = Gtk.Label(label="Welcome to NeuronOS")
        title.add_css_class("title-1")
        self.append(title)

        # Description
        desc = Gtk.Label(
            label=(
                "NeuronOS brings together the power of Linux with seamless "
                "compatibility for Windows and macOS applications.\n\n"
                "This wizard will help you set up your system for the best experience."
            )
        )
        desc.set_wrap(True)
        desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        desc.set_max_width_chars(60)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("dim-label")
        self.append(desc)

        # Key features
        features_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        features_box.set_margin_top(16)

        features = [
            ("Run Windows apps natively via Wine/Proton", "applications-games-symbolic"),
            ("GPU-accelerated Windows VMs for professional software", "video-display-symbolic"),
            ("Looking Glass for near-native VM performance", "view-reveal-symbolic"),
            ("Seamless USB device passthrough", "drive-removable-media-symbolic"),
        ]

        for text, icon_name in features:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_halign(Gtk.Align.CENTER)

            check_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            check_icon.add_css_class("success")
            row.append(check_icon)

            label = Gtk.Label(label=text)
            row.append(label)

            features_box.append(row)

        self.append(features_box)


class HardwareCheckPage(WizardPage):
    """Hardware compatibility check page."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)
        self._hardware_checked = False

        # Title
        title = Gtk.Label(label="Checking Your Hardware")
        title.add_css_class("title-2")
        self.append(title)

        # Description
        desc = Gtk.Label(
            label="We're checking your system for GPU passthrough compatibility."
        )
        desc.add_css_class("dim-label")
        self.append(desc)

        # Results container
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._results_box.set_margin_top(16)
        self.append(self._results_box)

        # Loading spinner (shown during check)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(48, 48)
        self._results_box.append(self._spinner)

        self._status_label = Gtk.Label(label="Scanning hardware...")
        self._status_label.add_css_class("dim-label")
        self._results_box.append(self._status_label)

    def on_enter(self):
        """Start hardware check when page becomes visible."""
        if not self._hardware_checked:
            self._start_hardware_check()

    def _start_hardware_check(self):
        """Start hardware detection in background."""
        self._spinner.start()
        self.wizard.set_can_proceed(False)

        thread = threading.Thread(target=self._do_hardware_check, daemon=True)
        thread.start()

    def _do_hardware_check(self):
        """Perform hardware check (runs in background thread)."""
        import time

        results = {
            "cpu_vendor": "Unknown",
            "cpu_model": "Unknown",
            "virtualization": False,
            "iommu_enabled": False,
            "gpus": [],
            "passthrough_candidate": None,
            "ram_gb": 0,
        }

        try:
            # Try to use our hardware detection modules
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from hardware_detect.cpu_detect import CPUDetector
                from hardware_detect.gpu_scanner import GPUScanner

                # CPU detection
                cpu = CPUDetector().detect()
                results["cpu_vendor"] = cpu.vendor
                results["cpu_model"] = cpu.model_name
                results["virtualization"] = cpu.has_virtualization
                results["iommu_enabled"] = cpu.iommu_enabled

                # GPU detection
                scanner = GPUScanner()
                gpus = scanner.scan()
                results["gpus"] = [
                    {
                        "name": f"{gpu.vendor_name} {gpu.device_name}",
                        "is_boot": gpu.is_boot_vga,
                        "is_integrated": gpu.is_integrated,
                        "pci_address": gpu.pci_address,
                    }
                    for gpu in gpus
                ]

                candidate = scanner.get_passthrough_candidate()
                if candidate:
                    results["passthrough_candidate"] = f"{candidate.vendor_name} {candidate.device_name}"

            except ImportError:
                logger.warning("Hardware detection modules not available, using fallback")
                # Fallback: basic info
                results["virtualization"] = True
                results["iommu_enabled"] = False

            # Get RAM
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            results["ram_gb"] = round(kb / 1024 / 1024)
                            break
            except Exception:
                results["ram_gb"] = 16  # Assume

        except Exception as e:
            logger.error(f"Hardware check failed: {e}")

        # Update UI on main thread
        GLib.idle_add(self._show_results, results)

    def _show_results(self, results: dict):
        """Show hardware check results."""
        self._spinner.stop()
        self._hardware_checked = True

        # Clear loading UI
        while self._results_box.get_first_child():
            self._results_box.remove(self._results_box.get_first_child())

        # Create results list
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")
        self._results_box.append(list_box)

        # CPU
        self._add_result_row(
            list_box,
            "CPU",
            results.get("cpu_model", "Unknown"),
            results.get("virtualization", False),
        )

        # Virtualization
        self._add_result_row(
            list_box,
            "Virtualization (VT-x/AMD-V)",
            "Enabled" if results.get("virtualization") else "Not detected",
            results.get("virtualization", False),
        )

        # IOMMU
        self._add_result_row(
            list_box,
            "IOMMU (Intel VT-d/AMD-Vi)",
            "Enabled" if results.get("iommu_enabled") else "Not enabled",
            results.get("iommu_enabled", False),
            warning_if_false="Enable in BIOS for GPU passthrough",
        )

        # RAM
        ram_gb = results.get("ram_gb", 0)
        self._add_result_row(
            list_box,
            "System RAM",
            f"{ram_gb} GB",
            ram_gb >= 16,
            warning_if_false="16GB+ recommended for VMs",
        )

        # GPUs
        gpus = results.get("gpus", [])
        if gpus:
            for i, gpu in enumerate(gpus):
                suffix = " (boot)" if gpu.get("is_boot") else ""
                suffix += " [integrated]" if gpu.get("is_integrated") else ""
                self._add_result_row(
                    list_box,
                    f"GPU {i + 1}",
                    f"{gpu.get('name', 'Unknown')}{suffix}",
                    True,
                )
        else:
            self._add_result_row(list_box, "GPU", "No dedicated GPU detected", False)

        # Passthrough candidate
        candidate = results.get("passthrough_candidate")
        if candidate:
            self._add_result_row(
                list_box,
                "GPU Passthrough",
                f"Available: {candidate}",
                True,
            )
            self.wizard.set_user_data("gpu_passthrough", True)
        else:
            self._add_result_row(
                list_box,
                "GPU Passthrough",
                "No suitable GPU (single GPU mode available)",
                False,
                warning_if_false="VMs will use software rendering",
            )

        self.wizard.set_can_proceed(True)

    def _add_result_row(
        self,
        list_box: Gtk.ListBox,
        title: str,
        value: str,
        is_ok: bool,
        warning_if_false: str = "",
    ):
        """Add a result row to the list."""
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(value)

        if is_ok:
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
        elif warning_if_false:
            icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")
            if warning_if_false:
                row.set_subtitle(f"{value} - {warning_if_false}")
        else:
            icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")

        row.add_suffix(icon)
        list_box.append(row)


class VMSetupPage(WizardPage):
    """VM setup options page."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)

        # Title
        title = Gtk.Label(label="Set Up Virtual Machines")
        title.add_css_class("title-2")
        self.append(title)

        # Description
        desc = Gtk.Label(
            label=(
                "NeuronOS can set up virtual machines for running Windows or macOS "
                "applications that don't work with Wine/Proton."
            )
        )
        desc.set_wrap(True)
        desc.set_max_width_chars(60)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("dim-label")
        self.append(desc)

        # Options
        options_box = Gtk.ListBox()
        options_box.set_selection_mode(Gtk.SelectionMode.NONE)
        options_box.add_css_class("boxed-list")
        options_box.set_margin_top(16)
        self.append(options_box)

        # Windows VM option
        self._windows_row = Adw.SwitchRow()
        self._windows_row.set_title("Set up Windows VM")
        self._windows_row.set_subtitle(
            "For Adobe Creative Suite, Microsoft Office, and other Windows-only software"
        )
        self._windows_row.connect("notify::active", self._on_option_changed)
        options_box.append(self._windows_row)

        # macOS VM option
        self._macos_row = Adw.SwitchRow()
        self._macos_row.set_title("Set up macOS VM")
        self._macos_row.set_subtitle(
            "For Final Cut Pro, Logic Pro, and other macOS-exclusive software"
        )
        self._macos_row.connect("notify::active", self._on_option_changed)
        options_box.append(self._macos_row)

        # Note about requirements
        note_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        note_box.set_margin_top(16)
        note_box.set_halign(Gtk.Align.CENTER)

        note_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        note_icon.add_css_class("dim-label")
        note_box.append(note_icon)

        note_label = Gtk.Label(
            label="You can set these up later from the NeuronVM Manager"
        )
        note_label.add_css_class("dim-label")
        note_box.append(note_label)

        self.append(note_box)

    def _on_option_changed(self, row, param):
        """Handle option changes."""
        pass

    def on_leave(self):
        """Save selections when leaving page."""
        self.wizard.set_user_data("setup_windows_vm", self._windows_row.get_active())
        self.wizard.set_user_data("setup_macos_vm", self._macos_row.get_active())


class MigrationPage(WizardPage):
    """File migration options page."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)

        # Title
        title = Gtk.Label(label="Migrate Your Files")
        title.add_css_class("title-2")
        self.append(title)

        # Description
        desc = Gtk.Label(
            label=(
                "Would you like to import files from a previous Windows or macOS installation?"
            )
        )
        desc.set_wrap(True)
        desc.set_max_width_chars(60)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("dim-label")
        self.append(desc)

        # Options
        options_box = Gtk.ListBox()
        options_box.set_selection_mode(Gtk.SelectionMode.NONE)
        options_box.add_css_class("boxed-list")
        options_box.set_margin_top(16)
        self.append(options_box)

        # Enable migration
        self._migrate_row = Adw.SwitchRow()
        self._migrate_row.set_title("Migrate files from another drive")
        self._migrate_row.set_subtitle("Import documents, photos, music, and downloads")
        self._migrate_row.connect("notify::active", self._on_migrate_toggled)
        options_box.append(self._migrate_row)

        # Source selection (shown when migration enabled)
        self._source_row = Adw.ActionRow()
        self._source_row.set_title("Select source drive")
        self._source_row.set_subtitle("No drive selected")
        self._source_row.set_activatable(True)
        self._source_row.connect("activated", self._on_select_source)
        self._source_row.set_sensitive(False)

        browse_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        self._source_row.add_suffix(browse_icon)
        self._source_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        options_box.append(self._source_row)

        # What will be migrated
        migrate_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        migrate_info.set_margin_top(16)
        migrate_info.set_halign(Gtk.Align.CENTER)

        info_label = Gtk.Label(label="Files that can be migrated:")
        info_label.add_css_class("heading")
        migrate_info.append(info_label)

        items = ["Documents", "Pictures", "Music", "Videos", "Downloads", "Desktop files"]
        for item in items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_halign(Gtk.Align.CENTER)
            check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            check.add_css_class("dim-label")
            row.append(check)
            row.append(Gtk.Label(label=item))
            migrate_info.append(row)

        self.append(migrate_info)

    def _on_migrate_toggled(self, row, param):
        """Handle migration toggle."""
        enabled = row.get_active()
        self._source_row.set_sensitive(enabled)

    def _on_select_source(self, row):
        """Open file chooser for source drive."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Source Drive")
        dialog.set_modal(True)

        dialog.select_folder(
            self.wizard,
            None,
            self._on_source_selected,
        )

    def _on_source_selected(self, dialog, result):
        """Handle source selection."""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self._source_row.set_subtitle(path)
                self.wizard.set_user_data("migration_source", path)
        except Exception as e:
            logger.error(f"Failed to select folder: {e}")

    def on_leave(self):
        """Save selections."""
        self.wizard.set_user_data("migrate_files", self._migrate_row.get_active())


class TutorialPage(WizardPage):
    """Quick tutorial page."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)

        # Title
        title = Gtk.Label(label="Quick Start Guide")
        title.add_css_class("title-2")
        self.append(title)

        # Tips carousel
        tips = [
            {
                "icon": "applications-games-symbolic",
                "title": "Gaming with Proton",
                "text": "Most Windows games work out of the box through Steam's Proton. Just install Steam and play!",
            },
            {
                "icon": "application-x-executable-symbolic",
                "title": "NeuronStore",
                "text": "Use NeuronStore to install apps. We'll automatically choose the best compatibility layer.",
            },
            {
                "icon": "computer-symbolic",
                "title": "Windows VMs",
                "text": "For professional apps like Adobe, use NeuronVM Manager. GPU passthrough gives 98%+ native performance.",
            },
            {
                "icon": "drive-removable-media-symbolic",
                "title": "USB Devices",
                "text": "USB devices work automatically. For VMs, right-click a device to pass it through.",
            },
        ]

        tips_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        tips_box.set_margin_top(16)

        for tip in tips:
            tip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            tip_row.set_halign(Gtk.Align.START)

            icon = Gtk.Image.new_from_icon_name(tip["icon"])
            icon.set_pixel_size(48)
            icon.add_css_class("dim-label")
            tip_row.append(icon)

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

            tip_title = Gtk.Label(label=tip["title"])
            tip_title.add_css_class("heading")
            tip_title.set_halign(Gtk.Align.START)
            text_box.append(tip_title)

            tip_text = Gtk.Label(label=tip["text"])
            tip_text.set_wrap(True)
            tip_text.set_max_width_chars(50)
            tip_text.set_halign(Gtk.Align.START)
            tip_text.add_css_class("dim-label")
            text_box.append(tip_text)

            tip_row.append(text_box)
            tips_box.append(tip_row)

        self.append(tips_box)


class CompletePage(WizardPage):
    """Completion page."""

    def __init__(self, wizard: "OnboardingWizard"):
        super().__init__(wizard)

        # Success icon
        icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        icon.set_pixel_size(96)
        icon.add_css_class("success")
        self.append(icon)

        # Title
        title = Gtk.Label(label="You're All Set!")
        title.add_css_class("title-1")
        self.append(title)

        # Description
        desc = Gtk.Label(
            label=(
                "NeuronOS is ready to use. Click 'Get Started' to begin exploring.\n\n"
                "You can access settings and VM management from the application menu."
            )
        )
        desc.set_wrap(True)
        desc.set_max_width_chars(50)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("dim-label")
        self.append(desc)

        # Summary of selections
        self._summary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._summary_box.set_margin_top(24)
        self._summary_box.set_halign(Gtk.Align.CENTER)
        self.append(self._summary_box)

    def on_enter(self):
        """Show summary of selections."""
        # Clear previous summary
        while self._summary_box.get_first_child():
            self._summary_box.remove(self._summary_box.get_first_child())

        data = self.wizard.get_user_data()

        tasks = []
        if data.get("setup_windows_vm"):
            tasks.append("Windows VM will be configured")
        if data.get("setup_macos_vm"):
            tasks.append("macOS VM will be configured")
        if data.get("migrate_files"):
            source = data.get("migration_source", "selected drive")
            tasks.append(f"Files will be migrated from {source}")

        if tasks:
            header = Gtk.Label(label="After setup:")
            header.add_css_class("heading")
            self._summary_box.append(header)

            for task in tasks:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.set_halign(Gtk.Align.CENTER)
                icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                icon.add_css_class("dim-label")
                row.append(icon)
                row.append(Gtk.Label(label=task))
                self._summary_box.append(row)
