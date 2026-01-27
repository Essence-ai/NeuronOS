# Phase 2.2: App Store GUI - Complete Implementation

**Status**: 🟡 40% UI COMPLETE, NO FUNCTIONALITY
**Estimated Time**: 3-4 days
**Prerequisites**: Phase 1.1-1.5 (installers must work)

---

## The Problem: App Store GUI Is Empty

The Store window has a **beautiful empty frame but shows no apps**:

### Current Implementation (Broken)

```python
class StoreWindow(Adw.ApplicationWindow):
    def __init__(self):
        # App list is empty or shows placeholder
        pass

    def _load_apps(self):
        """Load apps from catalog."""
        # TODO: Implement
        # Currently does nothing or shows hardcoded list

    def _on_install_clicked(self, app):
        """User clicks Install button."""
        # TODO: Wire to installer
        # No actual installation happens
```

### Missing Features

- ❌ Load apps from catalog
- ❌ Filter by category
- ❌ Search/filter functionality
- ❌ Install button wired to installers
- ❌ Progress reporting during install
- ❌ Installed apps marked as such
- ❌ Uninstall functionality

---

## Objective: Functional App Store

After this phase:

1. ✅ Apps load from catalog
2. ✅ Browse by category
3. ✅ Search for apps
4. ✅ Install with progress feedback
5. ✅ View installed apps
6. ✅ Uninstall apps
7. ✅ Rate compatibility layer

---

## Part 1: Enhance App Catalog

### 1.1: Improve AppInfo Dataclass

**File**: `src/store/app_catalog.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

class CompatibilityRating(Enum):
    """How well app works on NeuronOS."""
    NATIVE = "Native"           # Works perfectly on Linux
    GOLD = "Gold"              # Works perfectly on Proton/Wine
    SILVER = "Silver"          # Works well with minor issues
    BRONZE = "Bronze"          # Works but with problems
    UNTESTED = "Untested"      # Not tested

@dataclass
class AppInfo:
    """Application information for store."""
    id: str                                    # "autocad"
    name: str                                  # "AutoCAD 2024"
    category: str                              # "design", "games"
    layer: str                                 # "NATIVE", "WINE", "PROTON", "VM"
    installer_url: str                         # URL to .exe/.msi
    installer_sha256: Optional[str] = None     # For verification
    installer_size: Optional[int] = None       # In bytes
    icon_url: Optional[str] = None            # App icon (64x64 or larger)
    screenshot_url: Optional[str] = None      # Preview screenshot
    description: str = ""                      # Short description
    long_description: str = ""                # Detailed description
    compatibility_rating: CompatibilityRating = CompatibilityRating.UNTESTED
    requires_vm: bool = False                 # Must use VM (not Wine/Proton)
    steam_app_id: Optional[str] = None        # For Steam games
    version: str = "Latest"                   # App version
    developer: str = ""                       # Developer name
    release_date: str = ""                    # Release date
    homepage_url: str = ""                    # App website
    tags: List[str] = field(default_factory=list)  # "games", "office", "3d"


class AppCatalog:
    """Load and manage application catalog."""

    def __init__(self):
        """Initialize catalog."""
        self.apps: List[AppInfo] = []
        self._load_catalog()

    def _load_catalog(self):
        """Load apps.json from data directory."""
        import json
        from pathlib import Path

        catalog_path = Path(__file__).parent.parent.parent / "data" / "apps.json"

        try:
            with open(catalog_path) as f:
                data = json.load(f)

            for app_data in data.get("apps", []):
                app = AppInfo(**app_data)
                self.apps.append(app)

            logger.info(f"Loaded {len(self.apps)} apps from catalog")

        except Exception as e:
            logger.error(f"Failed to load catalog: {e}")
            self.apps = []

    def get_apps_by_category(self, category: str) -> List[AppInfo]:
        """Get all apps in a category."""
        return [app for app in self.apps if app.category == category]

    def get_apps_by_layer(self, layer: str) -> List[AppInfo]:
        """Get all apps compatible with a layer."""
        return [app for app in self.apps if app.layer == layer]

    def search(self, query: str) -> List[AppInfo]:
        """Search apps by name, description, or tags."""
        query_lower = query.lower()
        results = []

        for app in self.apps:
            if (query_lower in app.name.lower() or
                query_lower in app.description.lower() or
                any(query_lower in tag.lower() for tag in app.tags)):
                results.append(app)

        return results

    def get_categories(self) -> List[str]:
        """Get all available categories."""
        categories = set(app.category for app in self.apps)
        return sorted(list(categories))

    def get_installed_apps(self) -> List[str]:
        """Get IDs of currently installed apps."""
        apps_dir = (
            Path.home() / ".local" / "share" / "neuron-os" / "apps"
        )

        installed = []
        if apps_dir.exists():
            for json_file in apps_dir.glob("*.json"):
                app_id = json_file.stem
                installed.append(app_id)

        return installed

    def is_installed(self, app_id: str) -> bool:
        """Check if app is installed."""
        return app_id in self.get_installed_apps()
```

### 1.2: Create Updated apps.json

**File**: `data/apps.json`

```json
{
  "apps": [
    {
      "id": "vlc",
      "name": "VLC Media Player",
      "category": "media",
      "layer": "NATIVE",
      "installer_url": "",
      "icon_url": "https://www.videolan.org/assets/images/vlc_logo.svg",
      "description": "Powerful multimedia player",
      "long_description": "VLC is a free and open source cross-platform multimedia player and framework that plays most multimedia files.",
      "compatibility_rating": "Native",
      "developer": "VideoLAN",
      "tags": ["media", "video", "audio", "open-source"],
      "version": "3.0.0"
    },
    {
      "id": "7zip",
      "name": "7-Zip",
      "category": "utilities",
      "layer": "WINE",
      "installer_url": "https://7-zip.org/a/7z2301-x64.exe",
      "icon_url": "https://7-zip.org/images/7zip_logo.svg",
      "description": "File archiver with high compression",
      "compatibility_rating": "Gold",
      "steam_app_id": null,
      "developer": "Igor Pavlov",
      "tags": ["archive", "compress", "utilities"],
      "version": "23.01"
    },
    {
      "id": "photoshop",
      "name": "Adobe Photoshop 2024",
      "category": "design",
      "layer": "PROTON",
      "installer_url": "https://adobe-installers.example.com/photoshop_2024.exe",
      "icon_url": "https://adobe.com/images/photoshop_icon.png",
      "screenshot_url": "https://adobe.com/images/photoshop_screenshot.png",
      "description": "Professional image editing software",
      "long_description": "Adobe Photoshop is the industry standard for digital image editing.",
      "compatibility_rating": "Silver",
      "requires_vm": false,
      "developer": "Adobe Systems",
      "release_date": "2024-01-01",
      "homepage_url": "https://adobe.com/photoshop",
      "tags": ["design", "photo", "image-editing", "professional"],
      "version": "2024"
    },
    {
      "id": "autocad",
      "name": "AutoCAD 2024",
      "category": "design",
      "layer": "VM_WINDOWS",
      "installer_url": "https://autodesk-installers.example.com/autocad_2024.exe",
      "icon_url": "https://autodesk.com/images/autocad_icon.png",
      "description": "Professional CAD software",
      "compatibility_rating": "Gold",
      "requires_vm": true,
      "developer": "Autodesk",
      "tags": ["design", "cad", "engineering", "professional"],
      "version": "2024"
    },
    {
      "id": "witcher3",
      "name": "The Witcher 3: Wild Hunt",
      "category": "games",
      "layer": "PROTON",
      "installer_url": "",
      "icon_url": "https://cdn.cloudflare.steamstatic.com/steam/apps/292030/header.jpg",
      "description": "Open-world action RPG",
      "compatibility_rating": "Gold",
      "steam_app_id": "292030",
      "developer": "CD Projekt Red",
      "tags": ["games", "rpg", "action", "steam"],
      "version": "Latest"
    }
  ]
}
```

---

## Part 2: Build Store GUI

### 2.1: Create Store Window Class

**File**: `src/store/gui/store_window.py` (COMPLETE REWRITE)

```python
"""NeuronOS App Store GUI."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GdkPixbuf, GLib
import logging
from pathlib import Path
from typing import Optional, List

from src.store.app_catalog import AppCatalog, AppInfo, CompatibilityRating
from src.store.installer import AppInstaller

logger = logging.getLogger(__name__)


class StoreWindow(Adw.ApplicationWindow):
    """Main application store window."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("NeuronOS App Store")
        self.set_default_size(1200, 800)

        self.catalog = AppCatalog()
        self.installer = AppInstaller()
        self.current_category = "all"

        self._build_ui()
        self._load_apps()

    def _build_ui(self):
        """Build main UI layout."""
        # Header bar with search
        header = Adw.HeaderBar()

        search_button = Gtk.ToggleButton()
        search_button.set_icon_name("system-search-symbolic")
        search_button.connect("toggled", self._on_search_toggled)
        header.pack_end(search_button)

        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Search bar (hidden by default)
        self.search_bar = Gtk.SearchBar()
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search apps...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_bar.set_child(self.search_entry)
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode)
        vbox.append(self.search_bar)

        # Content area: Sidebar + Main panel
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content_box.set_margin_top(10)
        content_box.set_margin_bottom(10)
        content_box.set_margin_start(10)
        content_box.set_margin_end(10)

        # Left sidebar: Categories
        sidebar = self._build_sidebar()
        content_box.append(sidebar)

        # Right side: Apps grid
        self.apps_scroll = Gtk.ScrolledWindow()
        self.apps_flow = Gtk.FlowBox()
        self.apps_flow.set_column_spacing(10)
        self.apps_flow.set_row_spacing(10)
        self.apps_flow.set_homogeneous(False)
        self.apps_flow.set_selection_mode(Gtk.SelectionMode.NONE)

        self.apps_scroll.set_child(self.apps_flow)
        content_box.append(self.apps_scroll)

        vbox.append(content_box)

        # Set window content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        main_box.append(vbox)

        self.set_content(main_box)

    def _build_sidebar(self) -> Gtk.Box:
        """Build category sidebar."""
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sidebar.set_size_request(150, -1)

        # Title
        title = Gtk.Label()
        title.set_markup("<b>Categories</b>")
        title.set_halign(Gtk.Align.START)
        sidebar.append(title)

        # "All" button
        all_btn = Gtk.ToggleButton(label="All Apps")
        all_btn.set_active(True)
        all_btn.connect("toggled", self._on_category_selected, "all")
        sidebar.append(all_btn)

        # Category buttons
        for category in self.catalog.get_categories():
            btn = Gtk.ToggleButton(label=category.capitalize())
            btn.connect("toggled", self._on_category_selected, category)
            btn.set_group(all_btn)
            sidebar.append(btn)

        return sidebar

    def _load_apps(self):
        """Load and display apps."""
        apps = self.catalog.apps

        if self.current_category != "all":
            apps = self.catalog.get_apps_by_category(self.current_category)

        # Clear existing children
        while True:
            child = self.apps_flow.get_first_child()
            if child is None:
                break
            self.apps_flow.remove(child)

        # Add app cards
        for app in apps:
            card = self._create_app_card(app)
            self.apps_flow.append(card)

    def _create_app_card(self, app: AppInfo) -> Gtk.Widget:
        """Create a card widget for an app."""
        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card_box.set_size_request(200, 300)

        # Add CSS class for styling
        card_box.add_css_class("card")

        # Icon/screenshot
        image_box = Gtk.Box()
        image_box.set_size_request(200, 120)

        if app.screenshot_url:
            # Load image
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    app.screenshot_url, 200, 120
                )
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                image_box.append(image)
            except Exception:
                placeholder = Gtk.Label(label="📦")
                placeholder.add_css_class("title-2")
                image_box.append(placeholder)
        else:
            placeholder = Gtk.Label(label="📦")
            placeholder.add_css_class("title-2")
            image_box.append(placeholder)

        card_box.append(image_box)

        # App name
        name_label = Gtk.Label()
        name_label.set_text(app.name)
        name_label.add_css_class("title-3")
        name_label.set_wrap(True)
        card_box.append(name_label)

        # Category and rating
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        category_label = Gtk.Label()
        category_label.set_text(app.category)
        category_label.add_css_class("dim-label")
        category_label.add_css_class("caption")
        info_box.append(category_label)

        rating_label = Gtk.Label()
        rating_label.set_text(f"[{app.compatibility_rating.value}]")
        rating_label.add_css_class("caption")
        info_box.append(rating_label)

        card_box.append(info_box)

        # Description
        desc_label = Gtk.Label()
        desc_label.set_text(app.description)
        desc_label.set_wrap(True)
        desc_label.set_size_request(180, -1)
        desc_label.add_css_class("body")
        card_box.append(desc_label)

        # Install/Uninstall button
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        is_installed = self.catalog.is_installed(app.id)

        if is_installed:
            uninstall_btn = Gtk.Button(label="Uninstall")
            uninstall_btn.add_css_class("destructive-action")
            uninstall_btn.connect("clicked", self._on_uninstall_clicked, app)
            button_box.append(uninstall_btn)
        else:
            install_btn = Gtk.Button(label="Install")
            install_btn.add_css_class("suggested-action")
            install_btn.connect("clicked", self._on_install_clicked, app)
            button_box.append(install_btn)

        card_box.append(button_box)

        # Wrap in frame for styling
        frame = Gtk.Frame()
        frame.set_child(card_box)

        return frame

    def _on_category_selected(self, button, category):
        """Category selected."""
        if button.get_active():
            self.current_category = category
            self._load_apps()

    def _on_search_toggled(self, button):
        """Search button toggled."""
        self.search_bar.set_search_mode(button.get_active())

    def _on_search_mode(self, search_bar, param):
        """Search mode changed."""
        if search_bar.get_search_mode():
            self.search_entry.grab_focus()

    def _on_search_changed(self, search_entry):
        """Search text changed."""
        query = search_entry.get_text()

        if not query:
            self._load_apps()
            return

        results = self.catalog.search(query)

        # Clear and reload
        while True:
            child = self.apps_flow.get_first_child()
            if child is None:
                break
            self.apps_flow.remove(child)

        for app in results:
            card = self._create_app_card(app)
            self.apps_flow.append(card)

    def _on_install_clicked(self, button, app: AppInfo):
        """Install button clicked."""
        logger.info(f"Installing: {app.name}")

        # Show progress dialog
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(f"Installing {app.name}")
        dialog.set_body("Please wait while we download and install the application...")

        # Add spinner
        spinner = Gtk.Spinner()
        spinner.start()

        # Don't show until ready
        dialog.add_response("cancel", "Cancel")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)

        # Run installation in background
        import threading
        def install_task():
            success = self.installer.install(app)
            GLib.idle_add(self._on_install_complete, app, success, dialog)

        thread = threading.Thread(target=install_task, daemon=True)
        thread.start()

        dialog.present()

    def _on_install_complete(self, app: AppInfo, success: bool, dialog):
        """Installation complete."""
        dialog.close()

        if success:
            from src.common.dialogs import show_toast
            show_toast(self, f"{app.name} installed successfully!", timeout=2)

            # Reload apps to show uninstall button
            self._load_apps()
        else:
            from src.common.dialogs import show_toast
            show_toast(self, f"Failed to install {app.name}", timeout=3)

    def _on_uninstall_clicked(self, button, app: AppInfo):
        """Uninstall button clicked."""
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(f"Uninstall {app.name}?")
        dialog.set_body("This will remove the application and all associated data.")

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        dialog.connect("response", self._on_uninstall_confirmed, app)
        dialog.present()

    def _on_uninstall_confirmed(self, dialog, response, app: AppInfo):
        """Uninstall confirmed."""
        if response != "uninstall":
            return

        logger.info(f"Uninstalling: {app.name}")

        success = self.installer.uninstall(app.id)

        if success:
            from src.common.dialogs import show_toast
            show_toast(self, f"{app.name} uninstalled", timeout=2)

            # Reload apps
            self._load_apps()
        else:
            from src.common.dialogs import show_toast
            show_toast(self, f"Failed to uninstall {app.name}", timeout=3)
```

---

## Part 3: Add to Main Application

### 3.1: Update Application Class

**File**: `src/vm_manager/gui/app.py`

```python
def _on_store_clicked(self, button):
    """Open App Store window."""
    from src.store.gui.store_window import StoreWindow

    store_window = StoreWindow(self.application)
    store_window.present()
```

---

## Verification Checklist

Before moving to Phase 2.3:

**Catalog Loading**:
- [ ] Apps load from apps.json
- [ ] All 50+ apps displayable
- [ ] Categories parsed correctly
- [ ] Ratings assigned

**UI Display**:
- [ ] Apps show as cards in grid
- [ ] Icons/screenshots display
- [ ] Categories filter working
- [ ] Search finds apps by name/description
- [ ] Layout responsive

**Installation**:
- [ ] Install button wired to installer
- [ ] Progress shown during install
- [ ] Success/failure messages displayed
- [ ] Installed apps show uninstall button
- [ ] Uninstall works correctly

**Integration**:
- [ ] Store window opens from main menu
- [ ] All installers integrated (Wine, Proton, VM)
- [ ] Proper error messages
- [ ] No crashes

---

## Acceptance Criteria

✅ **Phase 2.2 Complete When**:

1. Store displays 50+ apps
2. Apps filterable by category
3. Search functionality works
4. Install/uninstall buttons functional
5. Progress feedback shown

---

## Next Steps

Phase 2.3 adds hardware auto-configuration
Phase 2.4 adds Looking Glass auto-start

Good luck! 🚀
