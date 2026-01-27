# Phase 6: App Store & Installation System

**Status:** USER-FACING FEATURE - The application marketplace
**Estimated Time:** 5-7 days
**Prerequisites:** Phase 5 complete (GPU passthrough working)

---

## Recap: What We Are Building

**NeuronOS** provides a unified App Store that intelligently routes applications to the right compatibility layer:
- **Native Linux** apps via pacman/Flatpak
- **Wine/Proton** apps for simple Windows software
- **VM apps** for professional software (Adobe, AutoCAD)

**This Phase's Goal:** Create a working App Store that:
1. Displays a catalog of applications
2. Shows compatibility information
3. Installs apps using the correct method
4. Tracks installed applications
5. Works from both GUI and CLI

---

## Why This Phase Matters

The App Store is how users discover and install software. It abstracts away the complexity of different installation methods and presents a unified experience.

---

## Phase 6 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 6.1 | App catalog loads correctly | Can read apps.json |
| 6.2 | Installer routing works | Correct installer for each layer |
| 6.3 | Pacman installer works | Can install native apps |
| 6.4 | Flatpak installer works | Can install Flatpak apps |
| 6.5 | Wine installer works | Can install Wine apps |
| 6.6 | Store CLI works | `neuron-store` commands work |

---

## Step 6.1: Verify App Catalog

The app catalog is stored in `data/apps.json`.

### Check Catalog Structure

```bash
cd /home/user/NeuronOS

# View catalog structure
python3 -c "
import json
with open('data/apps.json') as f:
    catalog = json.load(f)

print(f'Total apps: {len(catalog.get(\"apps\", []))}')
print(f'Categories: {list(catalog.get(\"categories\", {}).keys())}')

# Show first few apps
for app in catalog.get('apps', [])[:5]:
    print(f\"\\n{app['name']}:\"
    print(f'  ID: {app[\"id\"]}'
    print(f'  Layer: {app.get(\"layer\", \"native\")}'
    print(f'  Category: {app.get(\"category\", \"other\")}'
"
```

### Expected App Structure

Each app in `apps.json` should have:

```json
{
  "id": "unique-id",
  "name": "Display Name",
  "description": "What the app does",
  "category": "productivity|gaming|creative|development|utilities",
  "layer": "native|wine|proton|vm_windows|vm_macos|flatpak",
  "icon": "icon-name or URL",
  "package_name": "for native: arch package name",
  "flatpak_id": "for flatpak: org.example.App",
  "installer_url": "for wine: download URL",
  "steam_app_id": "for proton: Steam app ID",
  "compatibility_rating": "platinum|gold|silver|bronze|broken",
  "requires_gpu_passthrough": false
}
```

### Load Catalog in Code

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from store.app_catalog import AppCatalog

catalog = AppCatalog()
apps = catalog.list_all()

print(f'Loaded {len(apps)} apps')

# Group by layer
layers = {}
for app in apps:
    layer = app.layer.value if hasattr(app.layer, 'value') else str(app.layer)
    layers[layer] = layers.get(layer, 0) + 1

print('\\nApps by layer:')
for layer, count in sorted(layers.items()):
    print(f'  {layer}: {count}')
"
```

### Verification Criteria for 6.1
- [ ] apps.json exists and is valid JSON
- [ ] AppCatalog class loads apps
- [ ] Each app has required fields
- [ ] Apps have correct layer assignments
- [ ] Categories are populated

---

## Step 6.2: Installer Routing

The AppInstaller class routes installation to the correct method.

### Test Installer Routing

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.app_catalog import AppCatalog
from store.installer import AppInstaller, CompatibilityLayer

catalog = AppCatalog()
installer = AppInstaller()

# Test each layer has an installer
layers_to_test = [
    CompatibilityLayer.NATIVE,
    CompatibilityLayer.FLATPAK,
    CompatibilityLayer.WINE,
    CompatibilityLayer.PROTON,
    CompatibilityLayer.VM_WINDOWS,
]

print("Checking installer routing:")
for layer in layers_to_test:
    has_installer = layer in installer._installers
    status = "OK" if has_installer else "MISSING"
    print(f"  {layer.value}: {status}")
EOF
```

### Expected Result
All layers should show "OK"

### If Installer Missing

The `AppInstaller` class in `src/store/installer.py` needs all layers registered:

```python
def __init__(self):
    self._installers: Dict[CompatibilityLayer, BaseInstaller] = {
        CompatibilityLayer.NATIVE: PacmanInstaller(),
        CompatibilityLayer.FLATPAK: FlatpakInstaller(),
        CompatibilityLayer.WINE: WineInstaller(),
        CompatibilityLayer.PROTON: ProtonInstaller(),
        CompatibilityLayer.VM_WINDOWS: VMInstaller(),
        CompatibilityLayer.VM_MACOS: VMInstaller(),
    }
```

### Verification Criteria for 6.2
- [ ] All layers have installers
- [ ] Installer selection works based on app.layer
- [ ] No KeyError when installing apps

---

## Step 6.3: Pacman Installer (Native Apps)

Test installation of native Arch packages.

### Test Pacman Installer

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.installer import PacmanInstaller
from store.app_catalog import AppInfo, CompatibilityLayer

# Create a test app (use a small, safe package)
test_app = AppInfo(
    id="cowsay",
    name="Cowsay",
    description="A talking cow",
    category="utilities",
    layer=CompatibilityLayer.NATIVE,
    package_name="cowsay",
)

installer = PacmanInstaller()

# Check if already installed
if installer.is_installed(test_app):
    print("cowsay is already installed")
else:
    print("Installing cowsay...")
    # Note: This requires root/sudo
    print("Run: sudo pacman -S cowsay")
EOF
```

### Pacman Installer Requirements

The `PacmanInstaller` should:
1. Check if package is installed: `pacman -Q <package>`
2. Install package: `pacman -S <package>` (needs sudo)
3. Handle errors gracefully

### Verification Criteria for 6.3
- [ ] is_installed() correctly detects packages
- [ ] install() calls pacman with correct arguments
- [ ] Handles package not found errors
- [ ] Handles permission errors

---

## Step 6.4: Flatpak Installer

Test Flatpak application installation.

### Check Flatpak Availability

```bash
# Check if Flatpak is installed
flatpak --version

# Check if Flathub is added
flatpak remotes
```

### Test Flatpak Installer

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.installer import FlatpakInstaller
from store.app_catalog import AppInfo, CompatibilityLayer

# Test app
test_app = AppInfo(
    id="org.gnome.Calculator",
    name="GNOME Calculator",
    description="A calculator",
    category="utilities",
    layer=CompatibilityLayer.FLATPAK,
    flatpak_id="org.gnome.Calculator",
)

installer = FlatpakInstaller()

# Check if installed
print(f"Is installed: {installer.is_installed(test_app)}")

# List available runtimes
import subprocess
result = subprocess.run(["flatpak", "remotes"], capture_output=True, text=True)
print(f"Remotes: {result.stdout}")
EOF
```

### Flatpak Installer Requirements

```python
class FlatpakInstaller(BaseInstaller):
    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        try:
            subprocess.run(
                ["flatpak", "install", "-y", "flathub", app.flatpak_id],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def is_installed(self, app: AppInfo) -> bool:
        result = subprocess.run(
            ["flatpak", "info", app.flatpak_id],
            capture_output=True,
        )
        return result.returncode == 0
```

### Verification Criteria for 6.4
- [ ] Flatpak available in ISO
- [ ] Flathub remote configured
- [ ] is_installed() works
- [ ] install() downloads and installs

---

## Step 6.5: Wine Installer

Test Wine application installation.

### Test Wine Installer

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.installer import WineInstaller
from store.app_catalog import AppInfo, CompatibilityLayer
from pathlib import Path

# Test app (7-Zip as example)
test_app = AppInfo(
    id="7zip",
    name="7-Zip",
    description="File archiver",
    category="utilities",
    layer=CompatibilityLayer.WINE,
    installer_url="https://www.7-zip.org/a/7z2301-x64.exe",
)

installer = WineInstaller()

print("Wine prefix directory:", installer.PREFIXES_DIR)
print("Is installed:", installer.is_installed(test_app))

# Don't actually install, just verify code works
print("WineInstaller verified")
EOF
```

### Wine Installer Requirements

The Wine installer should:
1. Create a prefix for the app
2. Download the installer (with verification)
3. Run the installer in Wine
4. Track installation status

### Key Security: Download Verification

```python
def _secure_download(self, url: str, dest: Path, sha256: Optional[str] = None) -> bool:
    """Download with optional hash verification."""
    import hashlib
    import requests

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    hasher = hashlib.sha256() if sha256 else None

    with open(dest, 'wb') as f:
        for chunk in response.iter_content(8192):
            f.write(chunk)
            if hasher:
                hasher.update(chunk)

    if sha256 and hasher.hexdigest().lower() != sha256.lower():
        dest.unlink()
        return False

    return True
```

### Verification Criteria for 6.5
- [ ] WineInstaller creates prefixes
- [ ] Download works with HTTPS
- [ ] Hash verification works (when provided)
- [ ] App runs after installation
- [ ] is_installed() detects Wine apps

---

## Step 6.6: Store CLI

Create command-line interface for the store.

### Create CLI

Create or update `src/store/cli.py`:

```python
#!/usr/bin/env python3
"""NeuronOS Store CLI."""

import argparse
import sys

def cmd_search(args):
    """Search for apps."""
    from store.app_catalog import AppCatalog

    catalog = AppCatalog()
    apps = catalog.search(args.query)

    if not apps:
        print(f"No apps found for: {args.query}")
        return

    print(f"Found {len(apps)} app(s):\n")
    for app in apps[:10]:
        layer = app.layer.value if hasattr(app.layer, 'value') else str(app.layer)
        print(f"  {app.id}")
        print(f"    Name: {app.name}")
        print(f"    Layer: {layer}")
        print(f"    Category: {app.category}")
        print()

def cmd_info(args):
    """Show app information."""
    from store.app_catalog import AppCatalog

    catalog = AppCatalog()
    app = catalog.get(args.app_id)

    if not app:
        print(f"App not found: {args.app_id}")
        sys.exit(1)

    print(f"Name: {app.name}")
    print(f"ID: {app.id}")
    print(f"Description: {app.description}")
    print(f"Category: {app.category}")
    print(f"Layer: {app.layer.value if hasattr(app.layer, 'value') else app.layer}")
    if hasattr(app, 'compatibility_rating') and app.compatibility_rating:
        print(f"Compatibility: {app.compatibility_rating}")

def cmd_install(args):
    """Install an app."""
    from store.app_catalog import AppCatalog
    from store.installer import AppInstaller, InstallProgress

    catalog = AppCatalog()
    app = catalog.get(args.app_id)

    if not app:
        print(f"App not found: {args.app_id}")
        sys.exit(1)

    print(f"Installing {app.name}...")

    progress = InstallProgress()
    installer = AppInstaller()

    success = installer.install(app, progress)

    if success:
        print(f"Successfully installed {app.name}")
    else:
        print(f"Failed to install {app.name}")
        sys.exit(1)

def cmd_list(args):
    """List installed apps."""
    from store.installer import AppInstaller
    from store.app_catalog import AppCatalog

    catalog = AppCatalog()
    installer = AppInstaller()

    installed = []
    for app in catalog.list_all():
        if installer.is_installed(app):
            installed.append(app)

    if not installed:
        print("No apps installed via NeuronOS Store")
        return

    print(f"Installed apps ({len(installed)}):\n")
    for app in installed:
        print(f"  {app.id}: {app.name}")

def cmd_categories(args):
    """List app categories."""
    from store.app_catalog import AppCatalog

    catalog = AppCatalog()
    categories = catalog.get_categories()

    print("Categories:")
    for cat in sorted(categories):
        count = len(catalog.filter_by_category(cat))
        print(f"  {cat}: {count} apps")

def main():
    parser = argparse.ArgumentParser(
        prog='neuron-store',
        description='NeuronOS Application Store'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # search
    search_parser = subparsers.add_parser('search', help='Search for apps')
    search_parser.add_argument('query', help='Search query')
    search_parser.set_defaults(func=cmd_search)

    # info
    info_parser = subparsers.add_parser('info', help='Show app info')
    info_parser.add_argument('app_id', help='App ID')
    info_parser.set_defaults(func=cmd_info)

    # install
    install_parser = subparsers.add_parser('install', help='Install an app')
    install_parser.add_argument('app_id', help='App ID')
    install_parser.set_defaults(func=cmd_install)

    # list
    list_parser = subparsers.add_parser('list', help='List installed apps')
    list_parser.set_defaults(func=cmd_list)

    # categories
    cat_parser = subparsers.add_parser('categories', help='List categories')
    cat_parser.set_defaults(func=cmd_categories)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == '__main__':
    main()
```

### Test CLI

```bash
cd /home/user/NeuronOS

# Test search
python3 -m store.cli search firefox

# Test info
python3 -m store.cli info firefox

# Test categories
python3 -m store.cli categories

# Test list installed
python3 -m store.cli list
```

### Verification Criteria for 6.6
- [ ] search command finds apps
- [ ] info command shows details
- [ ] install command works
- [ ] list command shows installed apps
- [ ] categories command lists all categories

---

## Step 6.7: Integration into ISO

Add store to the ISO.

### Update packages.x86_64

The store GUI needs GTK4:
```text
# Already included from Phase 1
python-gobject
gtk4
libadwaita
```

### Create Entry Point

Create `iso-profile/airootfs/usr/bin/neuron-store`:

```bash
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/neuron-os')
from store.cli import main
main()
```

### Create Desktop Entry

Create `iso-profile/airootfs/etc/skel/Desktop/neuron-store.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=NeuronOS Store
Comment=Install applications
Exec=neuron-store-gui
Icon=system-software-install
Terminal=false
Categories=System;
```

### Verification Criteria for 6.7
- [ ] Store CLI available in ISO
- [ ] Desktop shortcut works
- [ ] Can search for apps
- [ ] Can install apps

---

## Verification Checklist

### Phase 6 is COMPLETE when ALL boxes are checked:

**App Catalog**
- [ ] apps.json loads correctly
- [ ] All apps have required fields
- [ ] Search works
- [ ] Category filtering works

**Installer Routing**
- [ ] All layers have installers registered
- [ ] Correct installer selected for each layer
- [ ] No missing installer errors

**Native Installer**
- [ ] pacman is_installed() works
- [ ] pacman install() works
- [ ] Error handling works

**Flatpak Installer**
- [ ] Flatpak available
- [ ] Flathub configured
- [ ] Installation works

**Wine Installer**
- [ ] Prefix creation works
- [ ] Download with verification works
- [ ] App installation works

**CLI**
- [ ] All commands work
- [ ] Error messages helpful
- [ ] Help text clear

**ISO Integration**
- [ ] Store available in live environment
- [ ] Desktop shortcut works
- [ ] Can install apps after OS install

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 7: First-Run Experience](./PHASE_7_FIRST_RUN.md)**

Phase 7 will create the onboarding wizard and file migration system.
