# Phase 5: Wine, Proton & App Compatibility

**Status:** PARTIALLY DONE - Packages included, integration logic needed
**Estimated Time:** 3-5 days
**Prerequisites:** Phase 4 complete (GPU passthrough verified)

---

## The Three-Layer Compatibility Model

NeuronOS routes Windows software to the best compatibility layer:

1. **Native Linux** (80% of use cases) - pacman/Flatpak packages
2. **Wine/Proton** (15%) - Lightweight Windows app translation, no VM needed
3. **GPU Passthrough VM** (5%) - Full Windows for professional software (Adobe, AutoCAD)

This phase ensures Wine and Proton work out of the box.

---

## What Already Exists

### Packages in ISO (Already Configured)
Wine and its dependencies are already in `iso-profile/packages.x86_64`:
- `wine`, `wine-mono`, `wine-gecko`, `winetricks`
- `lib32-mesa`, `lib32-vulkan-icd-loader`

### Store Module (Partial)
- `src/store/app_catalog.py` (328 lines) - Complete app database with `CompatibilityLayer` enum including `WINE`, `PROTON`, `VM_WINDOWS`
- `src/store/installer.py` (1,176 lines) - Has `WineInstaller`, `ProtonInstaller`, `VMInstaller` classes but installation logic is incomplete
- `data/apps.json` (24KB) - App catalog with layer ratings per app

### What Does NOT Exist
- No standalone `wine_manager.py` or `steam_detect.py` modules
- Wine prefix management is partially in `installer.py` but not complete
- Steam/Proton detection is not implemented

---

## Phase 5 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 5.1 | Wine runs in live ISO | `wine --version` works |
| 5.2 | Wine can run basic .exe | notepad.exe launches |
| 5.3 | Winetricks works | Can install vcrun2019 |
| 5.4 | Proton awareness | Detect Steam/Proton if installed |
| 5.5 | App catalog has layer info | apps.json rates apps by compatibility |

---

## Step 5.1: Verify Wine in ISO

After building the ISO (Phase 1), boot it and verify:

```bash
# In the live ISO or development environment
wine --version
# Expected: wine-9.x or similar

winetricks --version
# Expected: shows version
```

### Additional lib32 Packages to Consider

For better Wine compatibility with common apps, consider adding to `packages.x86_64`:

```text
# Enhanced Wine compatibility (add below existing wine section)
lib32-gnutls
lib32-sdl2
lib32-libpulse
lib32-alsa-lib
```

These improve audio, networking, and input handling in Wine apps. Only add them if ISO size is acceptable (~50MB increase).

---

## Step 5.2: Test Wine with Basic Apps

```bash
# Initialize wine prefix (first run)
WINEPREFIX=~/.wine wineboot --init

# Test notepad
wine notepad

# Test basic Windows dialog
wine control
```

---

## Step 5.3: Test Winetricks

```bash
# Install common runtime
winetricks vcrun2019

# Install DirectX
winetricks d3dx9

# Install .NET
winetricks dotnet48
```

---

## Step 5.4: App Catalog Integration

The app catalog (`data/apps.json` and `src/store/app_catalog.py`) already defines compatibility layers:

```python
class CompatibilityLayer(Enum):
    NATIVE = "native"          # Linux-native package
    FLATPAK = "flatpak"        # Flatpak sandbox
    WINE = "wine"              # Wine translation
    PROTON = "proton"          # Steam Proton
    VM_WINDOWS = "vm_windows"  # GPU passthrough VM
    VM_MACOS = "vm_macos"      # macOS VM
```

Each app in `apps.json` has a `layer` field that tells the store which installer to use.

### Verify Catalog
```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from store.app_catalog import AppCatalog

catalog = AppCatalog()
catalog.load('data/apps.json')

# Count apps by layer
from collections import Counter
layers = Counter(app.layer.value for app in catalog.apps)
for layer, count in layers.most_common():
    print(f'  {layer}: {count} apps')
"
```

---

## Step 5.5: Wine Integration in Store Installer

The `src/store/installer.py` has a `WineInstaller` class that needs completion. It should:

1. Create isolated Wine prefixes per app (`~/.local/share/neuron-os/wine/<app-id>/`)
2. Configure the prefix with correct Windows version and DLLs
3. Download the app installer from a URL
4. Run the installer in the prefix
5. Create a .desktop entry that launches the app via Wine

### What exists in installer.py:
- Security functions (`_safe_filename`, `_ensure_within_directory`) - complete
- `WineInstaller` class skeleton - needs installation logic
- `ProtonInstaller` class skeleton - needs Steam integration
- `VMInstaller` class skeleton - needs VM creation flow

### What needs to be implemented:
```
WineInstaller.install(app_info):
  1. mkdir -p ~/.local/share/neuron-os/wine/<app_id>
  2. WINEPREFIX=<prefix> wineboot --init
  3. WINEPREFIX=<prefix> winetricks <dependencies>
  4. Download installer to temp dir
  5. WINEPREFIX=<prefix> wine <installer.exe>
  6. Create .desktop entry with Exec=env WINEPREFIX=<prefix> wine <app.exe>
```

---

## Deciding on Steam

Steam is a large package (~500MB download) with licensing implications. Options:

1. **Include in ISO** - Adds `steam` package. Users get Proton immediately. Risk: Steam ToS requirements, disk space.
2. **Offer via App Store** - User clicks "Install Steam" in NeuronStore. Cleaner separation.
3. **Flatpak** - `flatpak install com.valvesoftware.Steam`. Sandboxed, automatic updates.

**Recommendation:** Option 2 or 3. Keep the ISO lean, let users opt-in to Steam. Add `steam` to `data/apps.json` as a native-layer app that gets installed via pacman when requested.

---

## Verification Checklist

- [ ] `wine --version` works in live ISO
- [ ] `winetricks --version` works
- [ ] `wine notepad` launches
- [ ] App catalog loads from `data/apps.json`
- [ ] Catalog contains apps with wine/proton/vm layers
- [ ] `WineInstaller` class exists in `src/store/installer.py`
- [ ] Wine prefix creation works (`wineboot --init`)

---

## Next Phase

Proceed to **[Phase 6: App Store & Installation System](./PHASE_6_APP_STORE.md)**
