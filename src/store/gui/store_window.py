#!/usr/bin/env python3
"""
NeuronStore - Application store for NeuronOS.

A GTK4/Adwaita application that provides a unified interface for
installing applications across different compatibility layers:
- Native Linux apps (pacman)
- Flatpak apps
- Wine/Proton apps
- Windows VM apps
- macOS VM apps
"""
from __future__ import annotations

import logging
import threading
from typing import Optional, List, Callable

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango

from ..app_catalog import (
    AppCatalog, AppInfo, AppCategory,
    CompatibilityLayer, CompatibilityRating
)
from ..installer import AppInstaller, InstallStatus

logger = logging.getLogger(__name__)


class AppCard(Gtk.Box):
    """Card widget displaying an application."""

    def __init__(self, app: AppInfo, on_install: Callable[[AppInfo], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.app = app
        self.on_install = on_install

        self.add_css_class("card")
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        # Header with icon placeholder and name
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(12)

        # Icon placeholder
        icon = Gtk.Image.new_from_icon_name(self._get_category_icon())
        icon.set_pixel_size(48)
        header.append(icon)

        # Name and publisher
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_box.set_hexpand(True)

        name_label = Gtk.Label(label=app.name)
        name_label.set_halign(Gtk.Align.START)
        name_label.add_css_class("title-3")
        name_box.append(name_label)

        if app.publisher:
            publisher_label = Gtk.Label(label=app.publisher)
            publisher_label.set_halign(Gtk.Align.START)
            publisher_label.add_css_class("dim-label")
            name_box.append(publisher_label)

        header.append(name_box)

        # Rating badge
        rating_badge = self._create_rating_badge()
        header.append(rating_badge)

        self.append(header)

        # Description
        desc_label = Gtk.Label(label=app.description)
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_wrap(True)
        desc_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        desc_label.set_max_width_chars(50)
        desc_label.set_margin_start(12)
        desc_label.set_margin_end(12)
        desc_label.add_css_class("dim-label")
        self.append(desc_label)

        # Tags
        if app.tags:
            tags_box = Gtk.FlowBox()
            tags_box.set_selection_mode(Gtk.SelectionMode.NONE)
            tags_box.set_max_children_per_line(5)
            tags_box.set_margin_start(12)
            tags_box.set_margin_end(12)

            for tag in app.tags[:5]:
                tag_label = Gtk.Label(label=tag)
                tag_label.add_css_class("caption")
                tag_label.add_css_class("dim-label")
                tags_box.append(tag_label)

            self.append(tags_box)

        # Layer indicator and install button
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_box.set_margin_start(12)
        action_box.set_margin_end(12)
        action_box.set_margin_bottom(12)

        layer_label = Gtk.Label(label=self._get_layer_text())
        layer_label.set_halign(Gtk.Align.START)
        layer_label.set_hexpand(True)
        layer_label.add_css_class("caption")
        action_box.append(layer_label)

        self.install_button = Gtk.Button(label="Install")
        self.install_button.add_css_class("suggested-action")
        self.install_button.connect("clicked", self._on_install_clicked)
        action_box.append(self.install_button)

        self.append(action_box)

        # Progress bar (hidden by default)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_start(12)
        self.progress_bar.set_margin_end(12)
        self.progress_bar.set_margin_bottom(12)
        self.progress_bar.set_visible(False)
        self.append(self.progress_bar)

    def _get_category_icon(self) -> str:
        icons = {
            AppCategory.PRODUCTIVITY: "x-office-document-symbolic",
            AppCategory.CREATIVE: "applications-graphics-symbolic",
            AppCategory.GAMING: "input-gaming-symbolic",
            AppCategory.DEVELOPMENT: "utilities-terminal-symbolic",
            AppCategory.COMMUNICATION: "mail-unread-symbolic",
            AppCategory.MEDIA: "applications-multimedia-symbolic",
            AppCategory.UTILITIES: "applications-utilities-symbolic",
            AppCategory.SYSTEM: "emblem-system-symbolic",
        }
        return icons.get(self.app.category, "application-x-executable-symbolic")

    def _create_rating_badge(self) -> Gtk.Label:
        colors = {
            CompatibilityRating.PERFECT: "success",
            CompatibilityRating.GOOD: "accent",
            CompatibilityRating.PLAYABLE: "warning",
            CompatibilityRating.RUNS: "warning",
            CompatibilityRating.BROKEN: "error",
        }
        texts = {
            CompatibilityRating.PERFECT: "★★★",
            CompatibilityRating.GOOD: "★★☆",
            CompatibilityRating.PLAYABLE: "★☆☆",
            CompatibilityRating.RUNS: "☆☆☆",
            CompatibilityRating.BROKEN: "✕",
        }
        badge = Gtk.Label(label=texts.get(self.app.rating, "?"))
        badge.add_css_class(colors.get(self.app.rating, "dim-label"))
        return badge

    def _get_layer_text(self) -> str:
        layers = {
            CompatibilityLayer.NATIVE: "🐧 Native",
            CompatibilityLayer.FLATPAK: "📦 Flatpak",
            CompatibilityLayer.WINE: "🍷 Wine",
            CompatibilityLayer.PROTON: "🎮 Proton",
            CompatibilityLayer.VM_WINDOWS: "🪟 Windows VM",
            CompatibilityLayer.VM_MACOS: "🍎 macOS VM",
        }
        return layers.get(self.app.layer, "Unknown")

    def _on_install_clicked(self, button: Gtk.Button) -> None:
        self.on_install(self.app)

    def set_installing(self, installing: bool) -> None:
        self.install_button.set_sensitive(not installing)
        self.progress_bar.set_visible(installing)
        if installing:
            self.install_button.set_label("Installing...")

    def set_progress(self, fraction: float, text: str = "") -> None:
        self.progress_bar.set_fraction(fraction)
        if text:
            self.progress_bar.set_text(text)
            self.progress_bar.set_show_text(True)

    def set_installed(self) -> None:
        self.install_button.set_label("Installed")
        self.install_button.set_sensitive(False)
        self.install_button.remove_css_class("suggested-action")
        self.progress_bar.set_visible(False)


class CategorySidebar(Gtk.Box):
    """Sidebar for category navigation."""

    def __init__(self, on_category_selected: Callable[[Optional[AppCategory]], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_category_selected = on_category_selected

        self.set_size_request(200, -1)

        # All apps button
        all_button = Gtk.Button(label="All Apps")
        all_button.set_halign(Gtk.Align.FILL)
        all_button.add_css_class("flat")
        all_button.connect("clicked", lambda b: self.on_category_selected(None))
        self.append(all_button)

        self.append(Gtk.Separator())

        # Category buttons
        categories = [
            (AppCategory.PRODUCTIVITY, "📄 Productivity"),
            (AppCategory.CREATIVE, "🎨 Creative"),
            (AppCategory.GAMING, "🎮 Gaming"),
            (AppCategory.DEVELOPMENT, "💻 Development"),
            (AppCategory.COMMUNICATION, "💬 Communication"),
            (AppCategory.MEDIA, "🎬 Media"),
            (AppCategory.UTILITIES, "🔧 Utilities"),
        ]

        for category, label in categories:
            btn = Gtk.Button(label=label)
            btn.set_halign(Gtk.Align.FILL)
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, c=category: self.on_category_selected(c))
            self.append(btn)

        self.append(Gtk.Separator())

        # Layer filters
        layer_label = Gtk.Label(label="Run Method")
        layer_label.add_css_class("heading")
        layer_label.set_margin_top(12)
        layer_label.set_halign(Gtk.Align.START)
        layer_label.set_margin_start(12)
        self.append(layer_label)

        layers = [
            ("🐧 Native", CompatibilityLayer.NATIVE),
            ("📦 Flatpak", CompatibilityLayer.FLATPAK),
            ("🪟 Windows VM", CompatibilityLayer.VM_WINDOWS),
        ]

        for label, layer in layers:
            btn = Gtk.Button(label=label)
            btn.set_halign(Gtk.Align.FILL)
            btn.add_css_class("flat")
            self.append(btn)


class NeuronStoreWindow(Adw.ApplicationWindow):
    """Main NeuronStore window."""

    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_title("NeuronStore")
        self.set_default_size(1200, 800)

        self.catalog = AppCatalog()
        self.catalog.load()
        self.installer = AppInstaller()

        self._current_category: Optional[AppCategory] = None
        self._search_query: str = ""

        self._build_ui()
        self._load_apps()

    def _build_ui(self) -> None:
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        header = Adw.HeaderBar()

        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search apps...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header.set_title_widget(self.search_entry)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        header.pack_end(menu_button)

        main_box.append(header)

        # Content area with sidebar
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Sidebar
        sidebar = CategorySidebar(self._on_category_selected)
        sidebar.add_css_class("navigation-sidebar")
        content_box.append(sidebar)

        content_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Main content
        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_hexpand(True)
        content_scroll.set_vexpand(True)

        self.apps_grid = Gtk.FlowBox()
        self.apps_grid.set_valign(Gtk.Align.START)
        self.apps_grid.set_max_children_per_line(4)
        self.apps_grid.set_min_children_per_line(1)
        self.apps_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.apps_grid.set_homogeneous(True)
        self.apps_grid.set_column_spacing(8)
        self.apps_grid.set_row_spacing(8)
        self.apps_grid.set_margin_start(16)
        self.apps_grid.set_margin_end(16)
        self.apps_grid.set_margin_top(16)
        self.apps_grid.set_margin_bottom(16)

        content_scroll.set_child(self.apps_grid)
        content_box.append(content_scroll)

        main_box.append(content_box)

        # Status bar
        self.status_bar = Gtk.Label(label="")
        self.status_bar.set_halign(Gtk.Align.START)
        self.status_bar.set_margin_start(16)
        self.status_bar.set_margin_bottom(8)
        self.status_bar.add_css_class("dim-label")
        main_box.append(self.status_bar)

        self.set_content(main_box)

    def _load_apps(self, apps: Optional[List[AppInfo]] = None) -> None:
        # Clear existing
        while child := self.apps_grid.get_first_child():
            self.apps_grid.remove(child)

        if apps is None:
            apps = self.catalog.search(
                query=self._search_query,
                category=self._current_category
            )

        for app in apps:
            card = AppCard(app, self._on_install_app)

            # Check if already installed
            if self.installer.is_installed(app):
                card.set_installed()

            self.apps_grid.append(card)

        self.status_bar.set_label(f"{len(apps)} apps")

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_query = entry.get_text()
        self._load_apps()

    def _on_category_selected(self, category: Optional[AppCategory]) -> None:
        self._current_category = category
        self._load_apps()

    def _on_install_app(self, app: AppInfo) -> None:
        # Find the card
        child = self.apps_grid.get_first_child()
        card: Optional[AppCard] = None
        while child:
            flow_child = child
            if hasattr(flow_child, 'get_child'):
                inner = flow_child.get_child()
                if isinstance(inner, AppCard) and inner.app.id == app.id:
                    card = inner
                    break
            child = child.get_next_sibling()

        if card:
            card.set_installing(True)

        # Install in background thread
        def install_thread():
            def progress_callback(percent, message, status):
                GLib.idle_add(self._update_install_progress, app.id, percent, message, status)

            self.installer.set_progress_callback(progress_callback)
            success = self.installer.install(app)

            GLib.idle_add(self._install_complete, app.id, success)

        thread = threading.Thread(target=install_thread)
        thread.daemon = True
        thread.start()

    def _update_install_progress(
        self, app_id: str, percent: int, message: str, status: InstallStatus
    ) -> None:
        # Find card and update progress
        child = self.apps_grid.get_first_child()
        while child:
            flow_child = child
            if hasattr(flow_child, 'get_child'):
                inner = flow_child.get_child()
                if isinstance(inner, AppCard) and inner.app.id == app_id:
                    inner.set_progress(percent / 100.0, message)
                    break
            child = child.get_next_sibling()

    def _install_complete(self, app_id: str, success: bool) -> None:
        child = self.apps_grid.get_first_child()
        while child:
            flow_child = child
            if hasattr(flow_child, 'get_child'):
                inner = flow_child.get_child()
                if isinstance(inner, AppCard) and inner.app.id == app_id:
                    if success:
                        inner.set_installed()
                    else:
                        inner.set_installing(False)
                        inner.install_button.set_label("Retry")
                    break
            child = child.get_next_sibling()


class NeuronStoreApp(Adw.Application):
    """NeuronStore GTK Application."""

    def __init__(self):
        super().__init__(
            application_id="org.neuronos.store",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        win = NeuronStoreWindow(self)
        win.present()


def main():
    """Entry point for NeuronStore."""
    logging.basicConfig(level=logging.INFO)
    app = NeuronStoreApp()
    app.run()


if __name__ == "__main__":
    main()
