# Phase 6: App Store & Installation System

**Status:** BACKEND COMPLETE - Needs CLI, GUI, and integration testing
**Estimated Time:** 5-7 days
**Prerequisites:** Phase 5 complete (Wine/Proton verified)

---

## What Already Exists (DO NOT Rewrite)

### App Catalog — `src/store/app_catalog.py` (328 lines) — COMPLETE

Fully implemented app catalog with:

- **`CompatibilityLayer` enum**: NATIVE, WINE, PROTON, VM_WINDOWS, VM_MACOS, FLATPAK, APPIMAGE
- **`CompatibilityRating` enum**: PERFECT, GOOD, PLAYABLE, RUNS, BROKEN
- **`AppCategory` enum**: PRODUCTIVITY, CREATIVE, GAMING, DEVELOPMENT, COMMUNICATION, MEDIA, UTILITIES, SYSTEM
- **`AppInfo` dataclass**: Full app metadata with `to_dict()` / `from_dict()`
- **`AppCatalog` class**: `load()`, `save()`, `get()`, `add()`, `remove()`, `all()`, `search()`, `by_category()`, `by_layer()`, `native_apps()`, `wine_apps()`, `vm_required_apps()`

### Installer System — `src/store/installer.py` (1,177 lines) — COMPLETE

All installer backends implemented with security functions:

| Class | Status | What It Does |
|-------|--------|-------------|
| `PacmanInstaller` | Complete | `sudo pacman -S <pkg>`, checks with `pacman -Q` |
| `FlatpakInstaller` | Complete | `flatpak install`, ensures Flathub remote exists |
| `WineInstaller` | Complete | Creates isolated Wine prefixes, downloads/runs installers, creates `.desktop` entries |
| `ProtonInstaller` | Complete | Detects Steam, handles Steam games + non-Steam apps, creates Proton prefixes |
| `VMInstaller` | Complete | Finds compatible VMs, starts them, opens Looking Glass/virt-viewer |
| `AppInstaller` | Complete | Routes to correct backend based on `app.layer` |

Security functions (`_safe_filename`, `_ensure_within_directory`, `_verify_download`) are all implemented.

### App Catalog Data — `data/apps.json` (714 lines, 46 apps) — COMPLETE

| Layer | Count | Examples |
|-------|-------|---------|
| Native | 20 | Firefox, LibreOffice, GIMP, Blender, Steam, Godot |
| Flatpak | 12 | VSCode, Discord, Zoom, Teams, Bottles |
| Wine | 4 | Notepad++, Rufus, WinRAR, League of Legends |
| VM Windows | 16 | Photoshop, Premiere Pro, MS Office, AutoCAD |
| VM macOS | 2 | Final Cut Pro, Logic Pro |

### What Does NOT Exist

- **No `src/store/cli.py`** — CLI interface needs to be created
- **No store GUI** — No GTK4/Adwaita storefront window
- **No store entry point script** — `iso-profile/airootfs/usr/bin/neuron-store` exists but may need updates

---

## Phase 6 Objectives

| # | Objective | Verification |
|---|-----------|-------------|
| 6.1 | App catalog loads all 46 apps | `AppCatalog().load()` returns 46 apps with correct layers |
| 6.2 | Installer routing selects correct backend | Each `CompatibilityLayer` maps to the right installer class |
| 6.3 | PacmanInstaller installs/detects native apps | Can install `cowsay`, `is_installed()` detects it |
| 6.4 | FlatpakInstaller works with Flathub | Can install a Flatpak app |
| 6.5 | WineInstaller creates prefixes and runs apps | Creates prefix, installs app, creates `.desktop` entry |
| 6.6 | Store CLI created and functional | `neuron-store search/info/install/list` commands work |
| 6.7 | Store GUI scaffold created | GTK4/Adwaita window with catalog browsing |
| 6.8 | ISO integration verified | Entry point, desktop shortcut, and store all work in live ISO |

---

## Step 6.1: Verify App Catalog Loading

The catalog is at `data/apps.json` and loaded by `src/store/app_catalog.py`.

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from store.app_catalog import AppCatalog

catalog = AppCatalog()
catalog.load()
apps = catalog.all()
print(f'Total apps: {len(apps)}')

# Count by layer
from collections import Counter
layers = Counter(app.layer.value for app in apps)
for layer, count in layers.most_common():
    print(f'  {layer}: {count}')

# Count by category
cats = Counter(app.category.value for app in apps)
print()
for cat, count in cats.most_common():
    print(f'  {cat}: {count}')
"
```

### What to Check

- [ ] `catalog.load('data/apps.json')` succeeds without exceptions
- [ ] Returns 46 apps (or more if new apps added)
- [ ] All 5 layer types have at least 1 app
- [ ] All 8 category types are populated
- [ ] `catalog.search('firefox')` returns Firefox app
- [ ] `catalog.by_layer(CompatibilityLayer.WINE)` returns Wine apps
- [ ] `catalog.by_category(AppCategory.GAMING)` returns gaming apps

---

## Step 6.2: Verify Installer Routing

The `AppInstaller` class in `installer.py` routes based on `app.layer`.

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from store.installer import AppInstaller
from store.app_catalog import CompatibilityLayer

installer = AppInstaller()

# Check each layer has a registered installer
for layer in CompatibilityLayer:
    has_it = hasattr(installer, '_installers') and layer in installer._installers
    # Alternative: check the routing method
    print(f'  {layer.value}: registered={has_it}')
"
```

### What to Check

- [ ] `AppInstaller()` instantiates without error
- [ ] NATIVE layer routes to `PacmanInstaller`
- [ ] FLATPAK layer routes to `FlatpakInstaller`
- [ ] WINE layer routes to `WineInstaller`
- [ ] PROTON layer routes to `ProtonInstaller`
- [ ] VM_WINDOWS and VM_MACOS route to `VMInstaller`
- [ ] APPIMAGE layer has a handler (or graceful error)

---

## Step 6.3: Test PacmanInstaller

### Verification Commands

```bash
cd /home/user/NeuronOS

# Test is_installed detection
python3 -c "
import sys; sys.path.insert(0, 'src')
from store.installer import PacmanInstaller
from store.app_catalog import AppInfo, CompatibilityLayer

installer = PacmanInstaller()

# Test with a package we know is installed
test = AppInfo.from_dict({
    'id': 'bash', 'name': 'Bash', 'description': 'Shell',
    'category': 'system', 'layer': 'native', 'package_name': 'bash'
})
print(f'bash installed: {installer.is_installed(test)}')  # Should be True

# Test with a package that's not installed
test2 = AppInfo.from_dict({
    'id': 'cowsay', 'name': 'Cowsay', 'description': 'Talking cow',
    'category': 'utilities', 'layer': 'native', 'package_name': 'cowsay'
})
print(f'cowsay installed: {installer.is_installed(test2)}')
"
```

### What to Check

- [ ] `is_installed()` returns True for installed packages
- [ ] `is_installed()` returns False for missing packages
- [ ] `install()` method calls `sudo pacman -S --noconfirm <package>`
- [ ] Error handling works when package doesn't exist in repos

---

## Step 6.4: Test FlatpakInstaller

### Verification Commands

```bash
# First verify Flatpak is available
flatpak --version
flatpak remotes

cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from store.installer import FlatpakInstaller

installer = FlatpakInstaller()
print('FlatpakInstaller created successfully')
# Check if Flathub remote setup works
print('Ready for Flatpak installations')
"
```

### What to Check

- [ ] `flatpak` binary available in ISO packages
- [ ] `FlatpakInstaller()` instantiates
- [ ] Flathub remote is added on first use
- [ ] `is_installed()` detects installed Flatpaks
- [ ] `install()` calls `flatpak install -y flathub <id>`

---

## Step 6.5: Test WineInstaller

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from store.installer import WineInstaller

installer = WineInstaller()
print('WineInstaller created successfully')

# Check prefix directory configuration
import inspect
source = inspect.getsource(WineInstaller)
if 'WINEPREFIX' in source or 'wine_prefix' in source or 'prefix' in source.lower():
    print('Has prefix management')
if '.desktop' in source:
    print('Has .desktop entry creation')
if 'download' in source.lower():
    print('Has download capability')
"
```

### What to Check

- [ ] Creates isolated Wine prefixes per app at `~/.local/share/neuron-os/wine/<app-id>/`
- [ ] Runs `wineboot --init` for new prefixes
- [ ] Downloads installer executables via HTTPS
- [ ] Runs `_verify_download()` with SHA256 when hash is provided
- [ ] Creates `.desktop` entry with `Exec=env WINEPREFIX=<prefix> wine <app.exe>`
- [ ] `is_installed()` checks for prefix existence

---

## Step 6.6: Create Store CLI

**This module does not exist yet and must be created.**

Create `src/store/cli.py` that provides a command-line interface to the store.

### Required Commands

| Command | Description | Example |
|---------|-------------|---------|
| `search <query>` | Search app catalog | `neuron-store search firefox` |
| `info <app-id>` | Show app details | `neuron-store info photoshop` |
| `install <app-id>` | Install an app | `neuron-store install gimp` |
| `uninstall <app-id>` | Remove an app | `neuron-store uninstall cowsay` |
| `list` | Show installed apps | `neuron-store list` |
| `categories` | List categories with counts | `neuron-store categories` |
| `layers` | Show apps grouped by layer | `neuron-store layers` |

### Implementation Requirements

1. **Use `argparse` with subcommands** — standard Python CLI pattern
2. **Load catalog from the correct path** — in ISO: `/usr/share/neuron-os/apps.json`, in dev: `data/apps.json`
3. **Progress reporting** — `install` command should show download/install progress
4. **Error messages** — clear, actionable error messages (not tracebacks)
5. **Exit codes** — 0 for success, 1 for errors

### Entry Point Integration

The entry point at `iso-profile/airootfs/usr/bin/neuron-store` should call this CLI:

```bash
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/neuron-os')
from store.cli import main
main()
```

### Verification

- [ ] `python3 -m store.cli search firefox` finds Firefox
- [ ] `python3 -m store.cli info gimp` shows GIMP details
- [ ] `python3 -m store.cli categories` lists all categories with counts
- [ ] `python3 -m store.cli layers` shows apps grouped by compatibility layer
- [ ] `python3 -m store.cli list` shows installed apps (or "none installed")
- [ ] Error messages are user-friendly, not Python tracebacks

---

## Step 6.7: Store GUI Scaffold

The store needs a GTK4/Adwaita graphical interface. This is the most significant new work in this phase.

### Architecture

The store GUI should be a standalone GTK4/Adwaita application:

- **Main window**: App catalog browser with search, categories, and featured apps
- **App detail view**: Shows description, screenshots, compatibility info, install button
- **Install progress**: Progress bar during installation
- **Settings**: Flatpak remote configuration, Wine prefix management

### Required Files

| File | Purpose |
|------|---------|
| `src/store/gui/__init__.py` | Package init |
| `src/store/gui/main_window.py` | Main store window (Adw.ApplicationWindow) |
| `src/store/gui/app_card.py` | Individual app card widget |
| `src/store/gui/app_detail.py` | App detail/install page |
| `src/store/gui/search_bar.py` | Search and filter controls |

### Key Design Decisions

1. **Use libadwaita** (`Adw.ApplicationWindow`) for GNOME integration
2. **Category sidebar** with app grid on the right
3. **Compatibility badges** — colored badges showing "Native", "Wine", "VM Required"
4. **One-click install** — single button, installer routing is invisible to user
5. **Progress tracking** — non-blocking installation with progress updates

### GUI Entry Point

Create `iso-profile/airootfs/usr/bin/neuron-store-gui`:

```bash
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/neuron-os')
from store.gui.main_window import main
main()
```

### Verification

- [ ] Store GUI launches without errors
- [ ] Shows app catalog with categories
- [ ] Search filters apps in real-time
- [ ] Clicking an app shows detail view
- [ ] Install button triggers correct installer
- [ ] Progress shown during installation

---

## Step 6.8: ISO Integration

### Verify Entry Points

```bash
# Check entry point exists and is executable
ls -la iso-profile/airootfs/usr/bin/neuron-store

# Check desktop file
cat iso-profile/airootfs/usr/share/applications/neuron-store.desktop

# Check skel desktop shortcut
cat iso-profile/airootfs/etc/skel/Desktop/neuron-store.desktop
```

### Verify Build Script

The `build-iso.sh` `copy_python_modules` function must copy the store module:

```bash
grep -n "store" build-iso.sh
# Should show store in the module copy loop
```

### Verify Package Dependencies

Ensure `iso-profile/packages.x86_64` includes:

```
python-gobject    # GTK bindings
gtk4              # GTK4 toolkit
libadwaita        # Adwaita widgets
python-requests   # HTTP downloads (for WineInstaller)
flatpak           # Flatpak support
```

### Verification

- [ ] `neuron-store` entry point exists at `/usr/bin/neuron-store`
- [ ] Desktop shortcut works from GNOME desktop
- [ ] Store module copied to `/usr/lib/neuron-os/store/`
- [ ] All Python dependencies available in ISO
- [ ] `data/apps.json` copied to `/usr/share/neuron-os/apps.json`

---

## Summary of Work Required

| Item | Status | Effort |
|------|--------|--------|
| App Catalog (`app_catalog.py`) | DONE — verify only | 1 hour |
| Installers (`installer.py`) | DONE — verify only | 2 hours |
| App Data (`apps.json`) | DONE — may add apps | 1 hour |
| Store CLI (`cli.py`) | NOT STARTED — create | 1 day |
| Store GUI | NOT STARTED — create | 3-4 days |
| ISO Integration | PARTIAL — verify | 2 hours |

---

## Verification Checklist

### Phase 6 is COMPLETE when ALL boxes are checked:

**Catalog**
- [ ] `AppCatalog.load()` loads all 46+ apps
- [ ] Search by name works
- [ ] Filter by category works
- [ ] Filter by layer works

**Installers**
- [ ] PacmanInstaller: `is_installed()` and `install()` work
- [ ] FlatpakInstaller: Flathub setup and installation work
- [ ] WineInstaller: Prefix creation and app installation work
- [ ] ProtonInstaller: Steam detection works
- [ ] VMInstaller: VM requirement checking works
- [ ] AppInstaller: Routes to correct backend

**CLI**
- [ ] `neuron-store search` works
- [ ] `neuron-store info` works
- [ ] `neuron-store install` works
- [ ] `neuron-store list` works

**GUI**
- [ ] Store window launches
- [ ] App browsing works
- [ ] Installation from GUI works

**ISO**
- [ ] Entry points executable
- [ ] Desktop shortcuts functional
- [ ] All dependencies available

---

## Next Phase

Proceed to **[Phase 7: Onboarding, Migration & Theming](./PHASE_7_ONBOARDING_MIGRATION.md)**
