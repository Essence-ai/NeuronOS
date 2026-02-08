#!/usr/bin/env python3
"""
NeuronOS Store GUI - GTK4/Adwaita Application

Full implementation of the Application Store with:
- App catalog browsing and search
- Category and compatibility layer filtering
- App detail view with compatibility info
- Installation and uninstallation with progress tracking
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

# GTK4 imports - will only work on Linux with GTK4 installed
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gio, GLib  # noqa: E402
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False
    Gtk = None
    Adw = None

# Import store modules
try:
    sys.path.insert(0, '/usr/lib/neuron-os')
    from store.app_catalog import (
        AppCatalog, AppInfo, AppCategory, CompatibilityLayer, CompatibilityRating
    )
    from store.installer import AppInstaller, InstallStatus
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    AppCatalog = None
    AppInstaller = None


# Human-readable labels for enums
LAYER_LABELS = {
    "native": "Native",
    "wine": "Wine",
    "proton": "Proton",
    "vm_windows": "Windows VM",
    "vm_macos": "macOS VM",
    "flatpak": "Flatpak",
    "appimage": "AppImage",
}

RATING_LABELS = {
    "perfect": "Perfect",
    "good": "Good",
    "playable": "Playable",
    "runs": "Runs",
    "broken": "Broken",
}

CATEGORY_LABELS = {
    "productivity": "Productivity",
    "creative": "Creative",
    "gaming": "Gaming",
    "development": "Development",
    "communication": "Communication",
    "media": "Media",
    "utilities": "Utilities",
    "system": "System",
}

LAYER_ICONS = {
    "native": "penguin-symbolic",
    "wine": "emblem-system-symbolic",
    "proton": "input-gaming-symbolic",
    "vm_windows": "computer-symbolic",
    "vm_macos": "computer-symbolic",
    "flatpak": "system-software-install-symbolic",
    "appimage": "application-x-executable-symbolic",
}

RATING_CSS_CLASSES = {
    "perfect": "success",
    "good": "success",
    "playable": "warning",
    "runs": "warning",
    "broken": "error",
}


if GTK_AVAILABLE:
    class AppCard(Gtk.Box):
        """A card widget displaying application information."""

        def __init__(self, app: AppInfo, is_installed: bool = False,
                     on_install=None, on_uninstall=None, on_details=None):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.app = app
            self._is_installed = is_installed
            self._on_install = on_install
            self._on_uninstall = on_uninstall
            self._on_details = on_details

            self.add_css_class("card")
            self.set_margin_start(6)
            self.set_margin_end(6)
            self.set_margin_top(6)
            self.set_margin_bottom(6)

            self._build_ui()

        def _build_ui(self):
            # Make the card clickable for details
            click = Gtk.GestureClick()
            click.connect("released", self._on_card_clicked)
            self.add_controller(click)

            # Header with icon and name
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            header_box.set_margin_start(12)
            header_box.set_margin_end(12)
            header_box.set_margin_top(12)

            # App icon
            icon_name = LAYER_ICONS.get(self.app.layer.value, "application-x-executable-symbolic")
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(40)
            header_box.append(icon)

            # Name and description
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info_box.set_hexpand(True)

            name_label = Gtk.Label(label=self.app.name)
            name_label.add_css_class("title-3")
            name_label.set_halign(Gtk.Align.START)
            name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            info_box.append(name_label)

            if self.app.description:
                desc_text = self.app.description
                if len(desc_text) > 80:
                    desc_text = desc_text[:77] + "..."
                desc_label = Gtk.Label(label=desc_text)
                desc_label.add_css_class("dim-label")
                desc_label.set_halign(Gtk.Align.START)
                desc_label.set_ellipsize(3)
                info_box.append(desc_label)

            header_box.append(info_box)
            self.append(header_box)

            # Badges row: category, layer, rating
            badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            badges_box.set_margin_start(12)
            badges_box.set_margin_end(12)

            # Category badge
            cat_label = Gtk.Label(label=CATEGORY_LABELS.get(self.app.category.value, self.app.category.value))
            cat_label.add_css_class("caption")
            cat_label.add_css_class("dim-label")
            badges_box.append(cat_label)

            # Layer badge
            layer_label = Gtk.Label(label=LAYER_LABELS.get(self.app.layer.value, self.app.layer.value))
            layer_label.add_css_class("caption")
            layer_label.add_css_class("accent")
            badges_box.append(layer_label)

            # Rating badge
            rating_text = RATING_LABELS.get(self.app.rating.value, self.app.rating.value)
            rating_label = Gtk.Label(label=rating_text)
            rating_label.add_css_class("caption")
            css_class = RATING_CSS_CLASSES.get(self.app.rating.value, "dim-label")
            rating_label.add_css_class(css_class)
            badges_box.append(rating_label)

            # Publisher
            if self.app.publisher:
                sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                badges_box.append(sep)
                pub_label = Gtk.Label(label=self.app.publisher)
                pub_label.add_css_class("caption")
                pub_label.add_css_class("dim-label")
                badges_box.append(pub_label)

            self.append(badges_box)

            # Action button row
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            button_box.set_margin_start(12)
            button_box.set_margin_end(12)
            button_box.set_margin_bottom(12)
            button_box.set_halign(Gtk.Align.END)
            button_box.set_hexpand(True)

            details_btn = Gtk.Button(label="Details")
            details_btn.add_css_class("flat")
            details_btn.connect("clicked", self._on_details_clicked)
            button_box.append(details_btn)

            if self._is_installed:
                uninstall_btn = Gtk.Button(label="Uninstall")
                uninstall_btn.add_css_class("destructive-action")
                uninstall_btn.connect("clicked", self._on_uninstall_clicked)
                button_box.append(uninstall_btn)

                installed_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
                installed_icon.set_tooltip_text("Installed")
                button_box.append(installed_icon)
            else:
                install_btn = Gtk.Button(label="Install")
                install_btn.add_css_class("suggested-action")
                install_btn.connect("clicked", self._on_install_clicked)
                button_box.append(install_btn)

            self.append(button_box)

        def _on_card_clicked(self, gesture, n_press, x, y):
            if self._on_details:
                self._on_details(self.app)

        def _on_details_clicked(self, button):
            if self._on_details:
                self._on_details(self.app)

        def _on_install_clicked(self, button):
            if self._on_install:
                self._on_install(self.app)

        def _on_uninstall_clicked(self, button):
            if self._on_uninstall:
                self._on_uninstall(self.app)


    class AppDetailView(Adw.Window):
        """Detail view for a single application."""

        def __init__(self, parent: Gtk.Window, app: AppInfo,
                     is_installed: bool = False,
                     on_install=None, on_uninstall=None):
            super().__init__()
            self.set_transient_for(parent)
            self.set_modal(True)
            self.set_title(app.name)
            self.set_default_size(600, 650)

            self._app = app
            self._is_installed = is_installed
            self._on_install = on_install
            self._on_uninstall = on_uninstall

            self._build_ui()

        def _build_ui(self):
            toolbar_view = Adw.ToolbarView()

            # Header bar
            header = Adw.HeaderBar()
            close_btn = Gtk.Button(label="Close")
            close_btn.connect("clicked", lambda b: self.close())
            header.pack_start(close_btn)
            toolbar_view.add_top_bar(header)

            # Scrollable content
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            content.set_margin_start(24)
            content.set_margin_end(24)
            content.set_margin_top(24)
            content.set_margin_bottom(24)

            # App header: icon + name + publisher
            app_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            icon_name = LAYER_ICONS.get(self._app.layer.value, "application-x-executable-symbolic")
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(64)
            app_header.append(icon)

            header_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            header_info.set_valign(Gtk.Align.CENTER)

            title = Gtk.Label(label=self._app.name)
            title.add_css_class("title-1")
            title.set_halign(Gtk.Align.START)
            header_info.append(title)

            if self._app.publisher:
                pub = Gtk.Label(label=self._app.publisher)
                pub.add_css_class("dim-label")
                pub.set_halign(Gtk.Align.START)
                header_info.append(pub)

            app_header.append(header_info)
            content.append(app_header)

            # Install/Uninstall button
            action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            if self._is_installed:
                btn = Gtk.Button(label="Uninstall")
                btn.add_css_class("destructive-action")
                btn.add_css_class("pill")
                btn.connect("clicked", self._do_uninstall)
            else:
                btn = Gtk.Button(label="Install")
                btn.add_css_class("suggested-action")
                btn.add_css_class("pill")
                btn.connect("clicked", self._do_install)
            self._action_btn = btn
            action_box.append(btn)

            # Progress bar (hidden by default)
            self._progress_bar = Gtk.ProgressBar()
            self._progress_bar.set_hexpand(True)
            self._progress_bar.set_visible(False)
            action_box.append(self._progress_bar)

            content.append(action_box)

            # Status label for install progress
            self._status_label = Gtk.Label()
            self._status_label.set_halign(Gtk.Align.START)
            self._status_label.add_css_class("dim-label")
            self._status_label.set_visible(False)
            content.append(self._status_label)

            # Description
            if self._app.description:
                desc_group = Adw.PreferencesGroup(title="Description")
                desc_row = Adw.ActionRow(title=self._app.description)
                desc_row.set_title_lines(0)
                desc_group.add(desc_row)
                content.append(desc_group)

            # App Information group
            info_group = Adw.PreferencesGroup(title="Information")

            cat_row = Adw.ActionRow(
                title="Category",
                subtitle=CATEGORY_LABELS.get(self._app.category.value, self._app.category.value),
            )
            cat_row.add_prefix(Gtk.Image.new_from_icon_name("view-grid-symbolic"))
            info_group.add(cat_row)

            if self._app.version:
                ver_row = Adw.ActionRow(title="Version", subtitle=self._app.version)
                ver_row.add_prefix(Gtk.Image.new_from_icon_name("emblem-default-symbolic"))
                info_group.add(ver_row)

            if self._app.website:
                web_row = Adw.ActionRow(title="Website", subtitle=self._app.website)
                web_row.add_prefix(Gtk.Image.new_from_icon_name("web-browser-symbolic"))
                info_group.add(web_row)

            content.append(info_group)

            # Compatibility group
            compat_group = Adw.PreferencesGroup(title="Compatibility")

            layer_text = LAYER_LABELS.get(self._app.layer.value, self._app.layer.value)
            layer_desc = self._get_layer_description(self._app.layer.value)
            layer_row = Adw.ActionRow(title="Compatibility Layer", subtitle=f"{layer_text} - {layer_desc}")
            layer_row.add_prefix(Gtk.Image.new_from_icon_name(
                LAYER_ICONS.get(self._app.layer.value, "emblem-system-symbolic")))
            compat_group.add(layer_row)

            rating_text = RATING_LABELS.get(self._app.rating.value, self._app.rating.value)
            rating_row = Adw.ActionRow(title="Compatibility Rating", subtitle=rating_text)
            rating_row.add_prefix(Gtk.Image.new_from_icon_name("starred-symbolic"))
            compat_group.add(rating_row)

            if self._app.requires_gpu_passthrough:
                gpu_row = Adw.ActionRow(
                    title="GPU Passthrough",
                    subtitle="Required for this application",
                )
                gpu_row.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
                compat_group.add(gpu_row)

            if self._app.min_ram_gb > 2:
                ram_row = Adw.ActionRow(
                    title="Minimum RAM",
                    subtitle=f"{self._app.min_ram_gb} GB",
                )
                ram_row.add_prefix(Gtk.Image.new_from_icon_name("memory-symbolic"))
                compat_group.add(ram_row)

            content.append(compat_group)

            # Notes, workarounds, known issues
            if self._app.notes or self._app.workarounds or self._app.known_issues:
                notes_group = Adw.PreferencesGroup(title="Notes")

                for note in self._app.notes:
                    row = Adw.ActionRow(title=note)
                    row.set_title_lines(0)
                    row.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
                    notes_group.add(row)

                for wa in self._app.workarounds:
                    row = Adw.ActionRow(title=wa)
                    row.set_title_lines(0)
                    row.add_prefix(Gtk.Image.new_from_icon_name("emblem-important-symbolic"))
                    notes_group.add(row)

                for issue in self._app.known_issues:
                    row = Adw.ActionRow(title=issue)
                    row.set_title_lines(0)
                    row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
                    notes_group.add(row)

                content.append(notes_group)

            # Tags
            if self._app.tags:
                tags_group = Adw.PreferencesGroup(title="Tags")
                tags_row = Adw.ActionRow(title=", ".join(self._app.tags))
                tags_row.add_prefix(Gtk.Image.new_from_icon_name("tag-symbolic"))
                tags_group.add(tags_row)
                content.append(tags_group)

            scroll.set_child(content)
            toolbar_view.set_content(scroll)
            self.set_content(toolbar_view)

        def _get_layer_description(self, layer_value: str) -> str:
            descriptions = {
                "native": "Runs natively on Linux, best performance",
                "wine": "Runs via Wine compatibility layer",
                "proton": "Runs via Steam Proton (Valve's Wine fork)",
                "vm_windows": "Requires a Windows virtual machine",
                "vm_macos": "Requires a macOS virtual machine",
                "flatpak": "Sandboxed Flatpak package from Flathub",
                "appimage": "Self-contained AppImage binary",
            }
            return descriptions.get(layer_value, "Unknown compatibility layer")

        def _do_install(self, button):
            if self._on_install:
                self._action_btn.set_sensitive(False)
                self._action_btn.set_label("Installing...")
                self._progress_bar.set_visible(True)
                self._progress_bar.set_fraction(0)
                self._status_label.set_visible(True)
                self._on_install(self._app, self._on_progress_update)

        def _do_uninstall(self, button):
            if self._on_uninstall:
                self._on_uninstall(self._app)
                self.close()

        def _on_progress_update(self, fraction: float, message: str):
            """Update progress bar and status from main thread."""
            self._progress_bar.set_fraction(fraction)
            self._status_label.set_label(message)
            if fraction >= 1.0:
                self._action_btn.set_label("Installed")
                self._progress_bar.set_visible(False)


    class NeuronStoreWindow(Adw.ApplicationWindow):
        """Main Store application window."""

        def __init__(self, app: Adw.Application):
            super().__init__(application=app)

            self.set_title("NeuronOS Store")
            self.set_default_size(1000, 750)

            self._catalog: Optional[AppCatalog] = None
            self._installer: Optional[AppInstaller] = None
            self._all_apps: List[AppInfo] = []
            self._current_query: str = ""
            self._current_category: Optional[str] = None
            self._current_layer: Optional[str] = None

            self._build_ui()
            self._load_catalog()

        def _build_ui(self) -> None:
            """Build the main UI."""
            # Toast overlay for notifications
            self._toast_overlay = Adw.ToastOverlay()

            toolbar_view = Adw.ToolbarView()

            # Header bar
            header = Adw.HeaderBar()

            # Search entry
            self._search_entry = Gtk.SearchEntry()
            self._search_entry.set_placeholder_text("Search apps...")
            self._search_entry.set_hexpand(True)
            self._search_entry.set_max_width_chars(40)
            self._search_entry.connect("search-changed", self._on_search_changed)
            header.set_title_widget(self._search_entry)

            # Refresh button
            refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
            refresh_btn.set_tooltip_text("Refresh catalog")
            refresh_btn.connect("clicked", lambda b: self._load_catalog())
            header.pack_start(refresh_btn)

            toolbar_view.add_top_bar(header)

            # Main content layout
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

            # Filter bar
            filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            filter_bar.set_margin_start(16)
            filter_bar.set_margin_end(16)
            filter_bar.set_margin_top(12)
            filter_bar.set_margin_bottom(8)

            # Category filter dropdown
            cat_label = Gtk.Label(label="Category:")
            cat_label.add_css_class("dim-label")
            filter_bar.append(cat_label)

            self._category_dropdown = Gtk.DropDown()
            cat_items = ["All Categories"] + [CATEGORY_LABELS.get(c.value, c.value) for c in AppCategory]
            cat_model = Gtk.StringList.new(cat_items)
            self._category_dropdown.set_model(cat_model)
            self._category_dropdown.connect("notify::selected", self._on_category_changed)
            filter_bar.append(self._category_dropdown)

            # Layer filter dropdown
            layer_label = Gtk.Label(label="Layer:")
            layer_label.add_css_class("dim-label")
            filter_bar.append(layer_label)

            self._layer_dropdown = Gtk.DropDown()
            layer_items = ["All Layers"] + [LAYER_LABELS.get(l.value, l.value) for l in CompatibilityLayer]
            layer_model = Gtk.StringList.new(layer_items)
            self._layer_dropdown.set_model(layer_model)
            self._layer_dropdown.connect("notify::selected", self._on_layer_changed)
            filter_bar.append(self._layer_dropdown)

            # App count label (right-aligned)
            self._count_label = Gtk.Label(label="")
            self._count_label.add_css_class("dim-label")
            self._count_label.set_hexpand(True)
            self._count_label.set_halign(Gtk.Align.END)
            filter_bar.append(self._count_label)

            main_box.append(filter_bar)

            # Separator
            main_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

            # Scrollable app list
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_vexpand(True)

            self._app_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self._app_list_box.set_margin_start(12)
            self._app_list_box.set_margin_end(12)
            self._app_list_box.set_margin_top(12)
            self._app_list_box.set_margin_bottom(12)

            scroll.set_child(self._app_list_box)
            main_box.append(scroll)

            toolbar_view.set_content(main_box)
            self._toast_overlay.set_child(toolbar_view)
            self.set_content(self._toast_overlay)

        def _load_catalog(self):
            """Load app catalog in background."""
            def load():
                catalog = None
                installer = None
                apps = []

                if MODULES_AVAILABLE:
                    try:
                        catalog = AppCatalog()
                        catalog.load()
                        installer = AppInstaller()
                        apps = catalog.all()
                    except Exception as e:
                        logger.error(f"Failed to load catalog: {e}")

                GLib.idle_add(self._on_catalog_loaded, catalog, installer, apps)

            thread = threading.Thread(target=load, daemon=True)
            thread.start()

        def _on_catalog_loaded(self, catalog, installer, apps):
            """Called when catalog is loaded (on main thread)."""
            self._catalog = catalog
            self._installer = installer
            self._all_apps = apps

            if not apps:
                self._show_empty_state()
            else:
                self._apply_filters()

            toast = Adw.Toast.new(f"Loaded {len(apps)} applications")
            toast.set_timeout(2)
            self._toast_overlay.add_toast(toast)

        def _show_empty_state(self):
            """Show empty state when no apps are available."""
            self._clear_app_list()

            status = Adw.StatusPage()
            status.set_title("No Applications Found")
            status.set_description(
                "The app catalog could not be loaded. "
                "Make sure the catalog file exists at /usr/share/neuron-os/apps.json"
            )
            status.set_icon_name("system-software-install-symbolic")
            self._app_list_box.append(status)
            self._count_label.set_label("")

        def _clear_app_list(self):
            """Remove all children from the app list."""
            child = self._app_list_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self._app_list_box.remove(child)
                child = next_child

        def _apply_filters(self):
            """Apply current search and filter settings."""
            if not self._catalog:
                return

            # Map dropdown index to enum
            category = None
            cat_idx = self._category_dropdown.get_selected()
            if cat_idx > 0:
                categories = list(AppCategory)
                category = categories[cat_idx - 1]

            layer = None
            layer_idx = self._layer_dropdown.get_selected()
            if layer_idx > 0:
                layers = list(CompatibilityLayer)
                layer = layers[layer_idx - 1]

            results = self._catalog.search(
                query=self._current_query,
                category=category,
                layer=layer,
            )

            self._display_apps(results)

        def _display_apps(self, apps: List[AppInfo]):
            """Display a list of apps as cards."""
            self._clear_app_list()

            if not apps:
                status = Adw.StatusPage()
                status.set_title("No Matching Apps")
                status.set_description("Try adjusting your search or filters")
                status.set_icon_name("edit-find-symbolic")
                self._app_list_box.append(status)
                self._count_label.set_label("0 apps")
                return

            self._count_label.set_label(f"{len(apps)} app{'s' if len(apps) != 1 else ''}")

            for app in apps:
                installed = False
                if self._installer:
                    try:
                        installed = self._installer.is_installed(app)
                    except Exception:
                        pass

                card = AppCard(
                    app,
                    is_installed=installed,
                    on_install=self._on_install_app,
                    on_uninstall=self._on_uninstall_app,
                    on_details=self._on_show_details,
                )
                self._app_list_box.append(card)

        # -- Signal handlers --

        def _on_search_changed(self, entry):
            """Handle search text changes."""
            self._current_query = entry.get_text()
            self._apply_filters()

        def _on_category_changed(self, dropdown, param):
            """Handle category filter changes."""
            self._apply_filters()

        def _on_layer_changed(self, dropdown, param):
            """Handle layer filter changes."""
            self._apply_filters()

        def _on_show_details(self, app: AppInfo):
            """Show the detail view for an app."""
            installed = False
            if self._installer:
                try:
                    installed = self._installer.is_installed(app)
                except Exception:
                    pass

            detail = AppDetailView(
                parent=self,
                app=app,
                is_installed=installed,
                on_install=self._on_install_with_progress,
                on_uninstall=self._on_uninstall_app,
            )
            detail.present()

        def _on_install_app(self, app: AppInfo):
            """Install an app (from card button, no detail progress)."""
            if not self._installer:
                self._show_toast("Store modules not available")
                return

            self._show_toast(f"Installing {app.name}...")

            def do_install():
                try:
                    def progress_cb(percent, message, status):
                        GLib.idle_add(self._on_install_progress_toast, app, percent, message, status)

                    self._installer.set_progress_callback(progress_cb)
                    success = self._installer.install(app)

                    if success:
                        GLib.idle_add(self._on_install_complete, app)
                    else:
                        GLib.idle_add(self._show_toast, f"Failed to install {app.name}")
                except Exception as e:
                    logger.error(f"Installation error: {e}")
                    GLib.idle_add(self._show_toast, f"Error: {e}")

            thread = threading.Thread(target=do_install, daemon=True)
            thread.start()

        def _on_install_with_progress(self, app: AppInfo, ui_progress_callback):
            """Install an app with progress feedback to the detail view."""
            if not self._installer:
                GLib.idle_add(ui_progress_callback, 0.0, "Store modules not available")
                return

            def do_install():
                try:
                    def progress_cb(percent, message, status):
                        fraction = percent / 100.0
                        GLib.idle_add(ui_progress_callback, fraction, message)

                    self._installer.set_progress_callback(progress_cb)
                    success = self._installer.install(app)

                    if success:
                        GLib.idle_add(ui_progress_callback, 1.0, "Installation complete")
                        GLib.idle_add(self._on_install_complete, app)
                    else:
                        GLib.idle_add(ui_progress_callback, 0.0, "Installation failed")
                        GLib.idle_add(self._show_toast, f"Failed to install {app.name}")
                except Exception as e:
                    logger.error(f"Installation error: {e}")
                    GLib.idle_add(ui_progress_callback, 0.0, f"Error: {e}")
                    GLib.idle_add(self._show_toast, f"Error installing {app.name}")

            thread = threading.Thread(target=do_install, daemon=True)
            thread.start()

        def _on_install_progress_toast(self, app, percent, message, status):
            """Show install progress as toast (for card-button installs)."""
            if status == InstallStatus.COMPLETE:
                self._show_toast(f"{app.name} installed successfully")
            elif status == InstallStatus.FAILED:
                self._show_toast(f"Failed: {message}")

        def _on_install_complete(self, app: AppInfo):
            """Called when installation completes."""
            self._show_toast(f"{app.name} installed successfully")
            self._apply_filters()  # Refresh to update install status

        def _on_uninstall_app(self, app: AppInfo):
            """Uninstall an app with confirmation dialog."""
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=f"Uninstall {app.name}?",
                body="This will remove the application from your system.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("uninstall", "Uninstall")
            dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_uninstall_response, app)
            dialog.present()

        def _on_uninstall_response(self, dialog, response, app):
            """Handle uninstall confirmation response."""
            if response != "uninstall":
                return

            if not self._installer:
                self._show_toast("Store modules not available")
                return

            self._show_toast(f"Uninstalling {app.name}...")

            def do_uninstall():
                try:
                    success = self._installer.uninstall(app)
                    if success:
                        GLib.idle_add(self._on_uninstall_complete, app)
                    else:
                        GLib.idle_add(self._show_toast, f"Failed to uninstall {app.name}")
                except Exception as e:
                    logger.error(f"Uninstall error: {e}")
                    GLib.idle_add(self._show_toast, f"Error: {e}")

            thread = threading.Thread(target=do_uninstall, daemon=True)
            thread.start()

        def _on_uninstall_complete(self, app: AppInfo):
            """Called when uninstall completes."""
            self._show_toast(f"{app.name} uninstalled")
            self._apply_filters()

        def _show_toast(self, message: str):
            """Show a toast notification."""
            toast = Adw.Toast.new(message)
            self._toast_overlay.add_toast(toast)


    class NeuronStoreApp(Adw.Application):
        """Main NeuronOS Store application."""

        def __init__(self):
            super().__init__(
                application_id="org.neuronos.store",
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )

        def do_activate(self) -> None:
            """Activate the application."""
            win = NeuronStoreWindow(self)
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

    app = NeuronStoreApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
