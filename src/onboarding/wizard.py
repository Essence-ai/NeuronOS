#!/usr/bin/env python3
"""
NeuronOS Onboarding Wizard - Main Window

A GTK4/Adwaita wizard that guides users through first-boot setup.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio  # noqa: E402

logger = logging.getLogger(__name__)


class OnboardingWizard(Adw.ApplicationWindow):
    """
    First-boot onboarding wizard for NeuronOS.

    Guides users through:
    1. Welcome and introduction
    2. Hardware compatibility check
    3. VM setup options
    4. File migration
    5. Quick tutorial
    6. Completion
    """

    def __init__(self, application: Adw.Application):
        super().__init__(application=application)
        self.set_title("Welcome to NeuronOS")
        self.set_default_size(900, 650)
        self.set_resizable(False)

        # Track wizard state
        self._current_page_index = 0
        self._pages: List[Gtk.Widget] = []
        self._page_titles: List[str] = []
        self._can_proceed: List[bool] = []

        # User selections (passed between pages)
        self._user_data = {
            "setup_windows_vm": False,
            "setup_macos_vm": False,
            "gpu_passthrough": False,
            "migrate_files": False,
            "migration_source": None,
        }

        self._build_ui()

    def _build_ui(self):
        """Build the wizard UI."""
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_box)

        # Header bar with progress
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        header.set_show_start_title_buttons(True)

        # Progress indicator in header
        self._progress_label = Gtk.Label(label="Step 1 of 6")
        self._progress_label.add_css_class("dim-label")
        header.set_title_widget(self._progress_label)

        main_box.append(header)

        # Stack for pages
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(300)
        self._stack.set_vexpand(True)
        main_box.append(self._stack)

        # Navigation bar at bottom
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav_box.set_margin_start(24)
        nav_box.set_margin_end(24)
        nav_box.set_margin_top(12)
        nav_box.set_margin_bottom(24)

        # Back button
        self._back_button = Gtk.Button(label="Back")
        self._back_button.connect("clicked", self._on_back_clicked)
        nav_box.append(self._back_button)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        nav_box.append(spacer)

        # Skip button (optional)
        self._skip_button = Gtk.Button(label="Skip")
        self._skip_button.connect("clicked", self._on_skip_clicked)
        self._skip_button.add_css_class("flat")
        nav_box.append(self._skip_button)

        # Next/Finish button
        self._next_button = Gtk.Button(label="Next")
        self._next_button.add_css_class("suggested-action")
        self._next_button.connect("clicked", self._on_next_clicked)
        nav_box.append(self._next_button)

        main_box.append(nav_box)

        # Add pages
        self._setup_pages()
        self._update_navigation()

    def _setup_pages(self):
        """Set up all wizard pages."""
        from .pages import (
            WelcomePage,
            HardwareCheckPage,
            VMSetupPage,
            MigrationPage,
            TutorialPage,
            CompletePage,
        )

        pages = [
            ("welcome", "Welcome", WelcomePage(self)),
            ("hardware", "Hardware Check", HardwareCheckPage(self)),
            ("vm_setup", "VM Setup", VMSetupPage(self)),
            ("migration", "Migration", MigrationPage(self)),
            ("tutorial", "Tutorial", TutorialPage(self)),
            ("complete", "Complete", CompletePage(self)),
        ]

        for page_id, title, page in pages:
            self._stack.add_named(page, page_id)
            self._pages.append(page)
            self._page_titles.append(title)
            self._can_proceed.append(True)

    def _update_navigation(self):
        """Update navigation buttons based on current page."""
        total = len(self._pages)
        current = self._current_page_index

        # Update progress label
        self._progress_label.set_text(f"Step {current + 1} of {total}")

        # Back button
        self._back_button.set_visible(current > 0)

        # Skip button (hide on first and last page)
        self._skip_button.set_visible(0 < current < total - 1)

        # Next button text
        if current == total - 1:
            self._next_button.set_label("Get Started")
            self._next_button.remove_css_class("suggested-action")
            self._next_button.add_css_class("suggested-action")
        else:
            self._next_button.set_label("Next")

        # Enable/disable next based on page validation
        self._next_button.set_sensitive(self._can_proceed[current])

    def set_can_proceed(self, can_proceed: bool):
        """Set whether the current page allows proceeding."""
        self._can_proceed[self._current_page_index] = can_proceed
        self._next_button.set_sensitive(can_proceed)

    def get_user_data(self) -> dict:
        """Get user selections from all pages."""
        return self._user_data.copy()

    def set_user_data(self, key: str, value):
        """Set a user selection value."""
        self._user_data[key] = value

    def _on_back_clicked(self, button: Gtk.Button):
        """Handle back button click."""
        if self._current_page_index > 0:
            self._current_page_index -= 1
            page = self._pages[self._current_page_index]
            self._stack.set_visible_child(page)
            self._update_navigation()

    def _on_skip_clicked(self, button: Gtk.Button):
        """Handle skip button click."""
        self._on_next_clicked(button)

    def _on_next_clicked(self, button: Gtk.Button):
        """Handle next button click."""
        if self._current_page_index < len(self._pages) - 1:
            # Call page's on_leave if it exists
            current_page = self._pages[self._current_page_index]
            if hasattr(current_page, "on_leave"):
                current_page.on_leave()

            self._current_page_index += 1
            next_page = self._pages[self._current_page_index]

            # Call page's on_enter if it exists
            if hasattr(next_page, "on_enter"):
                next_page.on_enter()

            self._stack.set_visible_child(next_page)
            self._update_navigation()
        else:
            # Finish wizard
            self._finish_wizard()

    def _finish_wizard(self):
        """Complete the wizard and apply all user settings."""
        logger.info("Finishing onboarding wizard...")
        logger.info(f"User selections: {self._user_data}")

        # Apply settings in background to avoid blocking UI
        def apply_settings():
            try:
                self._save_preferences()
                self._setup_nvidia_driver()
                self._configure_gpu()
                self._setup_vms()
                self._start_migration()
                self._finalize_setup()
            except Exception as e:
                logger.error(f"Onboarding error: {e}")
            finally:
                GLib.idle_add(self._finish_and_close)

        import threading
        thread = threading.Thread(target=apply_settings, daemon=True)
        thread.start()

    def _save_preferences(self):
        """Save user preferences to config file."""
        from datetime import datetime
        
        config_dir = Path.home() / ".config/neuronos"
        config_dir.mkdir(parents=True, exist_ok=True)

        preferences = {
            "setup_windows_vm": self._user_data.get("setup_windows_vm", False),
            "setup_macos_vm": self._user_data.get("setup_macos_vm", False),
            "gpu_passthrough": self._user_data.get("gpu_passthrough", False),
            "migrate_files": self._user_data.get("migrate_files", False),
            "onboarding_completed_at": datetime.now().isoformat(),
        }

        try:
            from utils.atomic_write import atomic_write_json
            atomic_write_json(config_dir / "preferences.json", preferences)
        except ImportError:
            import json
            (config_dir / "preferences.json").write_text(json.dumps(preferences, indent=2))
        
        logger.info("Preferences saved")

    def _setup_nvidia_driver(self):
        """Install NVIDIA proprietary driver if needed."""
        if not self._user_data.get("nvidia_needs_setup"):
            return

        logger.info("NVIDIA GPU detected without proprietary driver, queuing setup")

        import json
        config_dir = Path.home() / ".config/neuronos/pending-gpu-config"
        config_dir.mkdir(parents=True, exist_ok=True)

        nvidia_config = {
            "action": "install_nvidia",
            "packages": ["nvidia", "nvidia-utils", "nvidia-settings", "lib32-nvidia-utils"],
            "post_install": [
                "mkinitcpio -P",
            ],
            "needs_reboot": True,
        }
        (config_dir / "nvidia_setup.json").write_text(json.dumps(nvidia_config, indent=2))
        logger.info("NVIDIA driver installation queued for next boot")

    def _configure_gpu(self):
        """Configure GPU passthrough if requested."""
        if not self._user_data.get("gpu_passthrough"):
            logger.info("GPU passthrough not requested, skipping")
            return

        try:
            from hardware_detect.config_generator import ConfigGenerator

            generator = ConfigGenerator()
            config = generator.detect_and_generate()

            if config.is_valid:
                config_dir = Path.home() / ".config/neuronos/pending-gpu-config"
                config_dir.mkdir(parents=True, exist_ok=True)

                (config_dir / "vfio.conf").write_text(config.vfio_conf)
                (config_dir / "mkinitcpio_modules").write_text(config.mkinitcpio_modules)
                (config_dir / "kernel_params").write_text(config.kernel_params)
                (config_dir / "bootloader").write_text(config.bootloader)

                logger.info("GPU passthrough config generated (pending apply)")
            else:
                for error in config.errors:
                    logger.error(f"GPU config error: {error}")
                for warning in config.warnings:
                    logger.warning(f"GPU config warning: {warning}")

        except Exception as e:
            logger.error(f"GPU configuration failed: {e}")

    def _setup_vms(self):
        """Queue VMs for creation based on user selections."""
        from datetime import datetime
        
        queue_dir = Path.home() / ".config/neuronos/pending-vms"
        queue_dir.mkdir(parents=True, exist_ok=True)

        for vm_type, key in [("windows", "setup_windows_vm"), ("macos", "setup_macos_vm")]:
            if self._user_data.get(key):
                vm_config = {
                    "type": vm_type,
                    "queued_at": datetime.now().isoformat(),
                    "status": "pending",
                }
                import json
                (queue_dir / f"{vm_type}.json").write_text(json.dumps(vm_config, indent=2))
                logger.info(f"Queued {vm_type} VM for creation")

    def _start_migration(self):
        """Queue file migration if requested."""
        if not self._user_data.get("migrate_files"):
            logger.info("File migration not requested, skipping")
            return

        source = self._user_data.get("migration_source")
        if not source:
            logger.info("No migration source selected")
            return

        try:
            from datetime import datetime
            
            config_dir = Path.home() / ".config/neuronos/pending-migration"
            config_dir.mkdir(parents=True, exist_ok=True)

            migration_config = {
                "source_path": str(getattr(source, 'path', source)),
                "queued_at": datetime.now().isoformat(),
                "status": "pending",
            }

            import json
            (config_dir / "migration.json").write_text(json.dumps(migration_config, indent=2))
            logger.info("Migration queued")

        except Exception as e:
            logger.error(f"Migration setup failed: {e}")

    def _finalize_setup(self):
        """Create autostart entry for pending tasks if any exist."""
        pending_dir = Path.home() / ".config/neuronos"
        has_pending = any([
            (pending_dir / "pending-vms").exists(),
            (pending_dir / "pending-migration").exists(),
            (pending_dir / "pending-gpu-config").exists(),
        ])

        if has_pending:
            autostart_dir = Path.home() / ".config/autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)

            desktop_entry = """[Desktop Entry]
Type=Application
Name=NeuronOS Setup
Exec=neuron-pending-tasks
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Complete NeuronOS setup tasks
"""
            (autostart_dir / "neuron-pending-tasks.desktop").write_text(desktop_entry)

        logger.info("Finalization complete")

    def _finish_and_close(self):
        """Mark first boot complete and close wizard."""
        self._mark_first_boot_complete()
        self.close()

    def _mark_first_boot_complete(self):
        """Create a marker file indicating first-boot is complete."""
        marker_path = Path.home() / ".config" / "neuronos" / ".first-boot-complete"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
        logger.info("First-boot wizard completed")


class OnboardingApplication(Adw.Application):
    """Application wrapper for the onboarding wizard."""

    def __init__(self):
        super().__init__(
            application_id="org.neuronos.onboarding",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        """Activate the application."""
        # Check if first-boot is already complete
        marker_path = Path.home() / ".config" / "neuronos" / ".first-boot-complete"
        if marker_path.exists() and "--force" not in sys.argv:
            logger.info("First-boot already completed, exiting")
            return

        win = OnboardingWizard(self)
        win.present()


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    app = OnboardingApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
