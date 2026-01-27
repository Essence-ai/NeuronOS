# Phase 4: Wine & Proton Integration

**Status:** CORE FEATURE - Enables running Windows apps without VM
**Estimated Time:** 3-5 days
**Prerequisites:** Phase 3 complete (VM management working)

---

## Recap: What We Are Building

**NeuronOS** provides Windows software compatibility through three layers:
1. **Native Linux** (80% of use cases)
2. **Wine/Proton** (15% of use cases) - Simple Windows apps
3. **GPU passthrough VMs** (5% of use cases) - Professional software

**This Phase's Goal:** Get Wine and Proton working out of the box so users can:
1. Install Wine applications
2. Use Steam with Proton
3. Run Windows .exe files
4. Have a foundation for the App Store installers

---

## Why This Phase Matters

Wine and Proton handle the majority of Windows software needs. Most users will never need a full VM if Wine works correctly. This phase ensures:
- Wine is installed and configured correctly
- Steam/Proton detection works
- Basic Windows apps can run
- Foundation for the app store is in place

---

## Phase 4 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 4.1 | Wine installed in ISO | `wine --version` works |
| 4.2 | Wine runs basic apps | Can run notepad.exe |
| 4.3 | Winetricks works | Can install components |
| 4.4 | Steam detection | Can detect Steam installation |
| 4.5 | Proton detection | Can find Proton versions |
| 4.6 | Wine prefix management | Can create/list prefixes |

---

## Step 4.1: Add Wine to ISO Packages

Update packages.x86_64 to include Wine and dependencies.

### Required Packages

Add these to `/home/user/NeuronOS/iso-profile/packages.x86_64`:

```text
# Wine and compatibility
wine
wine-mono
wine-gecko
winetricks
lib32-gnutls
lib32-sdl2
lib32-libpulse
lib32-alsa-lib
lib32-libxcomposite
lib32-libxinerama
lib32-opencl-icd-loader
lib32-libva
lib32-mesa
lib32-vulkan-icd-loader
vulkan-icd-loader
vulkan-tools

# Gaming/Proton support
steam
gamemode
lib32-gamemode
mangohud
lib32-mangohud
```

### Verify multilib is enabled

```bash
grep -A1 "\[multilib\]" /home/user/NeuronOS/iso-profile/pacman.conf
# Should show [multilib] uncommented
```

### Verification Criteria for 4.1
- [ ] Wine packages added to packages.x86_64
- [ ] multilib repository enabled
- [ ] lib32 packages included for 32-bit support

---

## Step 4.2: Test Wine Installation

After adding packages, rebuild ISO and test Wine.

### In Development Environment

First, ensure Wine is installed locally for testing:

```bash
# Install Wine on development machine
sudo pacman -S wine wine-mono wine-gecko winetricks

# Verify installation
wine --version
# Expected: wine-X.X

# Check architecture support
wine64 --version
wine --version  # Should be 32-bit wine
```

### Basic Wine Test

```bash
# Create test prefix
export WINEPREFIX=~/.wine-test
wineboot --init

# Wait for setup to complete
sleep 10

# Run a basic Windows app
wine notepad

# This should open Notepad
# Close it when done

# Cleanup test prefix
rm -rf ~/.wine-test
```

### Expected Behavior
- Wine initializes without errors
- Notepad opens in a window
- Window is interactive

### Verification Criteria for 4.2
- [ ] Wine initializes successfully
- [ ] Notepad runs
- [ ] GUI appears
- [ ] No crash or missing library errors

---

## Step 4.3: Test Winetricks

Winetricks installs Windows components into Wine prefixes.

### Test Winetricks

```bash
# Create test prefix
export WINEPREFIX=~/.wine-tricks-test
wineboot --init
sleep 5

# Install common components
winetricks -q corefonts
winetricks -q vcrun2019

# Verify installation
ls $WINEPREFIX/drive_c/windows/Fonts/ | head -5

# Cleanup
rm -rf ~/.wine-tricks-test
```

### Key Winetricks Components

For Windows apps, commonly needed:
- `corefonts` - Microsoft core fonts
- `vcrun2019` - Visual C++ 2019 runtime
- `dotnet48` - .NET Framework 4.8
- `dxvk` - DirectX to Vulkan translation

### Verification Criteria for 4.3
- [ ] Winetricks runs without errors
- [ ] Can install corefonts
- [ ] Can install vcrun2019
- [ ] Components appear in prefix

---

## Step 4.4: Steam Detection

Create code to detect Steam installation and configuration.

### Test Steam Detection

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
from pathlib import Path

# Steam installation paths
STEAM_PATHS = [
    Path.home() / ".steam/steam",
    Path.home() / ".local/share/Steam",
    Path("/usr/share/steam"),
]

# Check if Steam is installed
steam_path = None
for path in STEAM_PATHS:
    if path.exists():
        steam_path = path
        print(f"Steam found at: {path}")
        break

if steam_path is None:
    print("Steam not installed")
    sys.exit(0)

# Find Steam libraries
steamapps = steam_path / "steamapps"
if steamapps.exists():
    print(f"\nSteamapps directory: {steamapps}")

    # List installed games (first 10)
    manifests = list(steamapps.glob("appmanifest_*.acf"))
    print(f"Installed games: {len(manifests)}")
    for manifest in manifests[:5]:
        print(f"  - {manifest.name}")
EOF
```

### Create Steam Detection Module

Add to `src/store/steam_detect.py`:

```python
"""Steam and Proton detection for NeuronOS."""

from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import re

@dataclass
class SteamInfo:
    """Steam installation information."""
    path: Path
    steamapps: Path
    library_folders: List[Path]
    installed_games: int

@dataclass
class ProtonVersion:
    """Proton version information."""
    name: str
    path: Path
    version: str

class SteamDetector:
    """Detects Steam installation and configuration."""

    STEAM_PATHS = [
        Path.home() / ".steam/steam",
        Path.home() / ".local/share/Steam",
    ]

    def detect(self) -> Optional[SteamInfo]:
        """Detect Steam installation."""
        for path in self.STEAM_PATHS:
            if path.exists() and (path / "steamapps").exists():
                steamapps = path / "steamapps"
                library_folders = self._find_library_folders(steamapps)
                installed = len(list(steamapps.glob("appmanifest_*.acf")))

                return SteamInfo(
                    path=path,
                    steamapps=steamapps,
                    library_folders=library_folders,
                    installed_games=installed,
                )
        return None

    def _find_library_folders(self, steamapps: Path) -> List[Path]:
        """Find all Steam library folders."""
        folders = [steamapps]

        vdf_path = steamapps / "libraryfolders.vdf"
        if vdf_path.exists():
            content = vdf_path.read_text()
            # Parse VDF for additional library paths
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                folder = Path(match.group(1)) / "steamapps"
                if folder.exists() and folder not in folders:
                    folders.append(folder)

        return folders

    def get_proton_versions(self) -> List[ProtonVersion]:
        """Get list of installed Proton versions."""
        versions = []

        steam = self.detect()
        if not steam:
            return versions

        for library in steam.library_folders:
            common = library / "common"
            if not common.exists():
                continue

            for item in common.iterdir():
                if item.is_dir() and "proton" in item.name.lower():
                    # Extract version
                    version = item.name.split()[-1] if " " in item.name else "unknown"
                    versions.append(ProtonVersion(
                        name=item.name,
                        path=item,
                        version=version,
                    ))

        # Sort by version (newest first)
        versions.sort(key=lambda x: x.version, reverse=True)
        return versions
```

### Test Steam Detection Module

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from store.steam_detect import SteamDetector

detector = SteamDetector()
steam = detector.detect()

if steam:
    print(f'Steam path: {steam.path}')
    print(f'Installed games: {steam.installed_games}')
    print(f'Library folders: {len(steam.library_folders)}')

    proton = detector.get_proton_versions()
    print(f'\nProton versions: {len(proton)}')
    for p in proton[:5]:
        print(f'  - {p.name}')
else:
    print('Steam not installed')
"
```

### Verification Criteria for 4.4
- [ ] SteamDetector class works
- [ ] Detects Steam path correctly
- [ ] Counts installed games
- [ ] Finds library folders
- [ ] Handles missing Steam gracefully

---

## Step 4.5: Proton Detection and Management

### Test Proton Availability

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.steam_detect import SteamDetector

detector = SteamDetector()
versions = detector.get_proton_versions()

if not versions:
    print("No Proton versions found")
    print("To install Proton:")
    print("  1. Open Steam")
    print("  2. Go to Library > Tools")
    print("  3. Install 'Proton Experimental' or 'Proton 9.0'")
else:
    print(f"Found {len(versions)} Proton version(s):")
    for v in versions:
        print(f"  - {v.name}")
        print(f"    Path: {v.path}")

    # Check if recommended version exists
    recommended = ["Proton 9", "Proton 8", "Proton Experimental"]
    found_recommended = None
    for rec in recommended:
        for v in versions:
            if rec in v.name:
                found_recommended = v.name
                break
        if found_recommended:
            break

    if found_recommended:
        print(f"\nRecommended for use: {found_recommended}")
EOF
```

### Create Proton Runner Helper

Add to `src/store/proton_runner.py`:

```python
"""Proton runner for NeuronOS."""

import os
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .steam_detect import SteamDetector, ProtonVersion

@dataclass
class ProtonPrefix:
    """Proton prefix (Wine-like environment)."""
    app_id: str
    path: Path
    proton_version: str

class ProtonRunner:
    """Runs Windows executables using Proton."""

    def __init__(self):
        self.detector = SteamDetector()
        self._steam_info = None
        self._proton = None

    def _get_steam(self):
        if self._steam_info is None:
            self._steam_info = self.detector.detect()
        return self._steam_info

    def _get_proton(self) -> Optional[ProtonVersion]:
        """Get best available Proton version."""
        if self._proton is not None:
            return self._proton

        versions = self.detector.get_proton_versions()
        if not versions:
            return None

        # Prefer stable versions
        preferred = ["Proton 9", "Proton 8", "Proton Experimental"]
        for pref in preferred:
            for v in versions:
                if pref in v.name:
                    self._proton = v
                    return v

        # Fall back to first available
        self._proton = versions[0]
        return self._proton

    def create_prefix(self, app_id: str) -> Optional[ProtonPrefix]:
        """Create a Proton prefix for an application."""
        steam = self._get_steam()
        if not steam:
            return None

        # Proton prefixes go in steamapps/compatdata
        prefix_path = steam.steamapps / "compatdata" / app_id

        proton = self._get_proton()
        if not proton:
            return None

        # Initialize prefix
        env = self._build_env(prefix_path)
        proton_exe = proton.path / "proton"

        try:
            subprocess.run(
                [str(proton_exe), "run", "wineboot", "--init"],
                env=env,
                capture_output=True,
                timeout=120,
            )
        except Exception as e:
            print(f"Failed to create prefix: {e}")
            return None

        return ProtonPrefix(
            app_id=app_id,
            path=prefix_path,
            proton_version=proton.name,
        )

    def run(self, exe_path: str, prefix: ProtonPrefix) -> bool:
        """Run an executable in a Proton prefix."""
        proton = self._get_proton()
        if not proton:
            return False

        env = self._build_env(prefix.path)
        proton_exe = proton.path / "proton"

        try:
            subprocess.Popen(
                [str(proton_exe), "run", exe_path],
                env=env,
                start_new_session=True,
            )
            return True
        except Exception as e:
            print(f"Failed to run: {e}")
            return False

    def _build_env(self, prefix_path: Path) -> dict:
        """Build environment for Proton execution."""
        steam = self._get_steam()
        env = os.environ.copy()

        env["STEAM_COMPAT_DATA_PATH"] = str(prefix_path)
        if steam:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(steam.path)

        return env
```

### Verification Criteria for 4.5
- [ ] Proton versions detected correctly
- [ ] Preferred version selection works
- [ ] Prefix creation works (if Steam installed)
- [ ] Environment variables set correctly

---

## Step 4.6: Wine Prefix Management

Create tools for managing Wine prefixes.

### Create Wine Prefix Manager

Add to `src/store/wine_manager.py`:

```python
"""Wine prefix management for NeuronOS."""

import os
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import json

@dataclass
class WinePrefix:
    """A Wine prefix (isolated Windows environment)."""
    name: str
    path: Path
    arch: str  # "win32" or "win64"
    created: str
    apps: List[str]

class WinePrefixManager:
    """Manages Wine prefixes for NeuronOS applications."""

    PREFIXES_DIR = Path.home() / ".local/share/neuronos/wine-prefixes"
    CONFIG_FILE = Path.home() / ".config/neuronos/wine-prefixes.json"

    def __init__(self):
        self.PREFIXES_DIR.mkdir(parents=True, exist_ok=True)
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def list_prefixes(self) -> List[WinePrefix]:
        """List all Wine prefixes."""
        prefixes = []

        if not self.PREFIXES_DIR.exists():
            return prefixes

        for item in self.PREFIXES_DIR.iterdir():
            if item.is_dir() and (item / "system.reg").exists():
                # Determine architecture
                arch = "win64"
                if (item / "drive_c/windows/syswow64").exists():
                    arch = "win64"
                elif not (item / "drive_c/Program Files (x86)").exists():
                    arch = "win32"

                prefixes.append(WinePrefix(
                    name=item.name,
                    path=item,
                    arch=arch,
                    created="",  # Could parse from reg file
                    apps=[],
                ))

        return prefixes

    def create_prefix(self, name: str, arch: str = "win64") -> Optional[WinePrefix]:
        """Create a new Wine prefix."""
        prefix_path = self.PREFIXES_DIR / name

        if prefix_path.exists():
            return None  # Already exists

        prefix_path.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)
        env["WINEARCH"] = arch

        try:
            subprocess.run(
                ["wineboot", "--init"],
                env=env,
                capture_output=True,
                timeout=120,
            )

            return WinePrefix(
                name=name,
                path=prefix_path,
                arch=arch,
                created="",
                apps=[],
            )
        except Exception as e:
            print(f"Failed to create prefix: {e}")
            # Cleanup failed prefix
            import shutil
            shutil.rmtree(prefix_path, ignore_errors=True)
            return None

    def delete_prefix(self, name: str) -> bool:
        """Delete a Wine prefix."""
        prefix_path = self.PREFIXES_DIR / name

        if not prefix_path.exists():
            return False

        import shutil
        shutil.rmtree(prefix_path)
        return True

    def run_in_prefix(self, name: str, exe_path: str) -> bool:
        """Run an executable in a Wine prefix."""
        prefix_path = self.PREFIXES_DIR / name

        if not prefix_path.exists():
            return False

        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)

        try:
            subprocess.Popen(
                ["wine", exe_path],
                env=env,
                start_new_session=True,
            )
            return True
        except Exception as e:
            print(f"Failed to run: {e}")
            return False

    def install_winetricks(self, name: str, components: List[str]) -> bool:
        """Install winetricks components in a prefix."""
        prefix_path = self.PREFIXES_DIR / name

        if not prefix_path.exists():
            return False

        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)

        try:
            subprocess.run(
                ["winetricks", "-q"] + components,
                env=env,
                capture_output=True,
                timeout=600,  # Components can take a while
            )
            return True
        except Exception as e:
            print(f"Failed to install components: {e}")
            return False
```

### Test Wine Prefix Manager

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from store.wine_manager import WinePrefixManager

manager = WinePrefixManager()

# List existing prefixes
print("Existing prefixes:")
for prefix in manager.list_prefixes():
    print(f"  - {prefix.name} ({prefix.arch})")

# Create test prefix
print("\nCreating test prefix...")
prefix = manager.create_prefix("test-prefix", "win64")
if prefix:
    print(f"Created: {prefix.path}")

    # List again
    print("\nPrefixes after creation:")
    for p in manager.list_prefixes():
        print(f"  - {p.name} ({p.arch})")

    # Delete test prefix
    print("\nDeleting test prefix...")
    manager.delete_prefix("test-prefix")
    print("Done")
else:
    print("Failed to create prefix")
EOF
```

### Verification Criteria for 4.6
- [ ] Can list existing prefixes
- [ ] Can create new prefix
- [ ] Prefix initialization works
- [ ] Can delete prefix
- [ ] Architecture selection works (win32/win64)

---

## Step 4.7: Integration Tests

Run comprehensive tests to verify Wine/Proton integration.

### Integration Test Script

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
import subprocess
sys.path.insert(0, 'src')

print("=" * 50)
print("NeuronOS Wine/Proton Integration Test")
print("=" * 50)

# Test 1: Wine binary
print("\n[1/5] Checking Wine installation...")
try:
    result = subprocess.run(["wine", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: {result.stdout.strip()}")
    else:
        print("  FAIL: Wine not working")
except FileNotFoundError:
    print("  FAIL: Wine not installed")

# Test 2: Winetricks
print("\n[2/5] Checking Winetricks...")
try:
    result = subprocess.run(["winetricks", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: winetricks available")
    else:
        print("  FAIL: Winetricks error")
except FileNotFoundError:
    print("  FAIL: Winetricks not installed")

# Test 3: Wine prefix manager
print("\n[3/5] Testing Wine prefix manager...")
try:
    from store.wine_manager import WinePrefixManager
    manager = WinePrefixManager()
    prefixes = manager.list_prefixes()
    print(f"  OK: Found {len(prefixes)} prefix(es)")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 4: Steam detection
print("\n[4/5] Testing Steam detection...")
try:
    from store.steam_detect import SteamDetector
    detector = SteamDetector()
    steam = detector.detect()
    if steam:
        print(f"  OK: Steam at {steam.path}")
    else:
        print("  INFO: Steam not installed (optional)")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 5: Proton detection
print("\n[5/5] Testing Proton detection...")
try:
    from store.steam_detect import SteamDetector
    detector = SteamDetector()
    proton = detector.get_proton_versions()
    if proton:
        print(f"  OK: Found {len(proton)} Proton version(s)")
    else:
        print("  INFO: No Proton installed (optional)")
except Exception as e:
    print(f"  FAIL: {e}")

print("\n" + "=" * 50)
print("Integration test complete")
print("=" * 50)
EOF
```

---

## Verification Checklist

### Phase 4 is COMPLETE when ALL boxes are checked:

**Wine Installation**
- [ ] Wine packages in packages.x86_64
- [ ] multilib enabled in pacman.conf
- [ ] wine --version works on live ISO
- [ ] 32-bit and 64-bit support work

**Wine Functionality**
- [ ] Can create Wine prefix
- [ ] Notepad runs in Wine
- [ ] Wine GUI appears
- [ ] Winetricks installs components

**Steam/Proton**
- [ ] SteamDetector class works
- [ ] Detects Steam installation
- [ ] Finds Proton versions
- [ ] ProtonRunner class works

**Prefix Management**
- [ ] WinePrefixManager works
- [ ] Can create/delete prefixes
- [ ] Can run apps in prefixes
- [ ] Can install winetricks components

**Integration**
- [ ] All integration tests pass
- [ ] No import errors
- [ ] Works in live ISO environment

---

## Common Issues

### "wine: command not found"
- Ensure wine package is in packages.x86_64
- Rebuild ISO

### "wine: cannot find L"C:\\windows\\system32\\notepad.exe""
- Prefix not initialized, run `wineboot --init`

### "No Proton versions found"
- Normal if Steam not installed or Proton not downloaded
- Install from Steam > Library > Tools

### "winetricks: command not found"
- Add winetricks to packages.x86_64

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 5: GPU Passthrough](./PHASE_5_GPU_PASSTHROUGH.md)**

Phase 5 will enable GPU passthrough for running professional Windows software at near-native performance.
