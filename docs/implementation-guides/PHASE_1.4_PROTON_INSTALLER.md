# Phase 1.4: Proton Installer - Complete Non-Steam Installation

**Status**: 🔴 CRITICAL BLOCKER - Proton layer incomplete
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.1 (guest agent), Phase 1.3 (not directly, but good context)

---

## The Problem: Incomplete Proton Installer

The **ProtonInstaller** class exists but is only **50% complete**:

### What Works Today
```python
class ProtonInstaller(BaseInstaller):
    def install(self, app: AppInfo) -> bool:
        # ✅ Detects Steam installation
        # ✅ Creates Proton prefix
        # ✅ Saves app configuration
```

### What's Missing
```python
def install(self, app: AppInfo) -> bool:
    # ❌ Doesn't download the installer file
    # ❌ Doesn't execute it via Proton
    # ❌ No environment variable setup
    # ❌ No progress callback
    # ❌ Fallback if Steam not installed incomplete
```

### The Impact

**Scenario**: User tries to install "The Witcher 3" via Proton:

```
1. User clicks "Install" in Store
   ↓
2. ProtonInstaller.install() is called
   ↓
3. Creates Proton prefix ✓
   ↓
4. Tries to execute installer...
   ↓
5. ❌ FAILS - No code to download or run it!

User sees: "Installation failed" with no helpful message
```

---

## Objective: Complete Proton Installation Workflow

After this phase:

1. ✅ Detect Steam and Proton installation
2. ✅ Download game/app installer from URL
3. ✅ Create Proton prefix with environment setup
4. ✅ Execute installer via Proton WINEPREFIX mechanism
5. ✅ Create desktop launcher for easy access
6. ✅ Handle Steam games vs non-Steam games
7. ✅ Proper error handling and progress reporting

---

## Part 1: Understand Current Code

### 1.1: Current ProtonInstaller (Incomplete)

**File**: `src/store/installer.py` (lines 749-1050)

```python
class ProtonInstaller(BaseInstaller):
    """Install apps via Proton/Steam."""

    def __init__(self):
        self.steam_dir = self._find_steam_directory()
        self.proton_version = None

    def install(self, app: AppInfo) -> bool:
        """Install application via Proton."""

        # Step 1: Find Steam and Proton
        if not self._check_steam_installed():
            logger.error("Steam not installed")
            return False

        # Step 2: Find Proton version
        self.proton_version = self._detect_proton_version()
        if not self.proton_version:
            logger.error("Proton not installed")
            return False

        # Step 3: Create prefix
        prefix_path = self._create_proton_prefix(app.id)
        if not prefix_path:
            logger.error("Failed to create prefix")
            return False

        # Step 4: Install the app
        # ❌ MISSING CODE HERE!
        # Should download installer and run it

        # Step 5: Save app config
        self._save_app_config(app, prefix_path)

        return True

    def _check_steam_installed(self) -> bool:
        """Check if Steam is installed."""
        return self.steam_dir.exists()

    def _detect_proton_version(self) -> Optional[str]:
        """Detect available Proton version."""
        # Lists: ~/.steam/steamapps/compatibilitytools/Proton*
        pass  # Simplified

    def _create_proton_prefix(self, app_id: str) -> Optional[Path]:
        """Create a Proton prefix for the app."""
        # ✅ This is implemented
        pass

    def _save_app_config(self, app: AppInfo, prefix: Path):
        """Save app config for later."""
        # ✅ This is implemented
        pass
```

### 1.2: Missing Pieces

The installer needs:

1. **Download handler** - Fetch .exe/.msi from URL
2. **Proton runner** - Execute via PROTONPREFIX mechanism
3. **Environment setup** - Set PROTON_* variables correctly
4. **Progress tracking** - Report download/install progress
5. **Error recovery** - Handle failed downloads gracefully
6. **Steam game detection** - Handle Steam game IDs vs regular .exe

---

## Part 2: Complete Proton Installation

### 2.1: Enhance ProtonInstaller Class

**File**: `src/store/installer.py`

**Find the ProtonInstaller class** and add these methods:

```python
class ProtonInstaller(BaseInstaller):
    """Install applications via Proton (Steam compatibility layer)."""

    def __init__(self):
        """Initialize Proton installer."""
        self.steam_dir = self._find_steam_directory()
        self.proton_version = None
        self.proton_path = None

    def install(self, app: AppInfo, progress_callback=None) -> bool:
        """
        Install application via Proton.

        Args:
            app: Application info
            progress_callback: Optional callback(progress: DownloadProgress)

        Returns:
            True if installation successful
        """
        logger.info(f"Installing via Proton: {app.name}")

        try:
            # Step 1: Check Steam installed
            if not self._check_steam_installed():
                logger.error("Steam is not installed")
                return False

            # Step 2: Detect Proton
            self.proton_version = self._detect_proton_version()
            self.proton_path = self._get_proton_path(self.proton_version)

            if not self.proton_path or not self.proton_path.exists():
                logger.error(f"Proton not found: {self.proton_path}")
                return False

            logger.info(f"Using Proton: {self.proton_version}")

            # Step 3: Create Proton prefix
            prefix_path = self._create_proton_prefix(app.id)
            if not prefix_path:
                logger.error("Failed to create Proton prefix")
                return False

            logger.info(f"Proton prefix created: {prefix_path}")

            # Step 4: Detect if Steam game or non-Steam app
            if self._is_steam_game(app):
                # For Steam games, just launch Steam with app ID
                success = self._install_steam_game(app)
            else:
                # For non-Steam apps, download and run installer
                success = self._install_non_steam_game(app, prefix_path, progress_callback)

            if not success:
                logger.error(f"Installation failed for {app.name}")
                return False

            # Step 5: Create desktop launcher
            self._create_desktop_launcher(app, prefix_path)

            # Step 6: Save app configuration
            self._save_app_config(app, prefix_path)

            logger.info(f"Successfully installed: {app.name}")
            return True

        except Exception as e:
            logger.error(f"Exception during Proton installation: {e}")
            return False

    def _check_steam_installed(self) -> bool:
        """Check if Steam is installed."""
        if not self.steam_dir or not self.steam_dir.exists():
            # Try common Steam locations
            steam_locations = [
                Path.home() / ".steam" / "steam",
                Path.home() / ".local" / "share" / "steam",
                Path("/opt/steam"),
                Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
            ]

            for loc in steam_locations:
                if loc.exists():
                    self.steam_dir = loc
                    logger.info(f"Found Steam at: {loc}")
                    return True

            logger.warning("Steam not found in any location")
            return False

        return True

    def _detect_proton_version(self) -> Optional[str]:
        """
        Detect available Proton version.

        Looks for Proton in the compatibility tools directory:
        ~/.steam/steamapps/compatibilitytools/Proton-X.Y/
        """
        if not self.steam_dir:
            return None

        compat_dir = self.steam_dir / "steamapps" / "compatibilitytools"
        if not compat_dir.exists():
            logger.warning(f"Compatibility tools dir not found: {compat_dir}")
            return None

        try:
            # Find Proton directories, sorted by version (newest first)
            proton_dirs = sorted(
                [d for d in compat_dir.glob("Proton*") if d.is_dir()],
                reverse=True,
                key=lambda x: self._parse_version(x.name),
            )

            if proton_dirs:
                version = proton_dirs[0].name
                logger.info(f"Detected Proton version: {version}")
                return version
            else:
                logger.warning("No Proton installations found")
                return None

        except Exception as e:
            logger.error(f"Error detecting Proton: {e}")
            return None

    def _parse_version(self, version_str: str) -> tuple:
        """Parse version string to tuple for comparison."""
        import re
        # Extract version numbers: "Proton-8.3-GE-1" → (8, 3, 1)
        match = re.search(r"Proton[^0-9]*(\d+)\.(\d+)", version_str)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (0, 0)

    def _get_proton_path(self, version: str) -> Optional[Path]:
        """Get the full path to Proton binary."""
        if not self.steam_dir or not version:
            return None

        proton_dir = (
            self.steam_dir / "steamapps" / "compatibilitytools" / version / "proton"
        )

        if proton_dir.exists():
            return proton_dir
        else:
            logger.warning(f"Proton path not found: {proton_dir}")
            return None

    def _create_proton_prefix(self, app_id: str) -> Optional[Path]:
        """
        Create a Proton WINEPREFIX for the application.

        Creates a directory where the app will be installed with its
        own Wine prefix, separate from other Proton apps.
        """
        try:
            data_dir = Path.home() / ".local" / "share" / "neuron-os"
            prefix_dir = data_dir / "proton-prefixes" / app_id
            prefix_dir.mkdir(parents=True, exist_ok=True)

            # Initialize the prefix by running Proton's wineboot
            # This creates the Windows directory structure
            self._wineboot_prefix(prefix_dir)

            logger.info(f"Proton prefix created: {prefix_dir}")
            return prefix_dir

        except Exception as e:
            logger.error(f"Failed to create prefix: {e}")
            return None

    def _wineboot_prefix(self, prefix_dir: Path):
        """Initialize Wine prefix with wineboot."""
        import subprocess

        try:
            # WINEPREFIX=path proton run wineboot -i
            env = os.environ.copy()
            env["WINEPREFIX"] = str(prefix_dir)

            # Use Proton's wineboot if available
            result = subprocess.run(
                [str(self.proton_path / "wineboot"), "-i"],
                env=env,
                capture_output=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info("Prefix initialized with wineboot")
            else:
                logger.warning(f"wineboot returned {result.returncode}")

        except FileNotFoundError:
            # wineboot not in Proton directory, might be in system
            logger.warning("wineboot not found, prefix will initialize on first use")
        except Exception as e:
            logger.warning(f"Error initializing prefix: {e}")

    def _is_steam_game(self, app: AppInfo) -> bool:
        """Check if app is a Steam game (has steam_app_id)."""
        return hasattr(app, "steam_app_id") and app.steam_app_id

    def _install_steam_game(self, app: AppInfo) -> bool:
        """
        Install a Steam game.

        For Steam games, we just launch Steam with the game ID
        and let Steam handle the installation.
        """
        import subprocess

        try:
            steam_app_id = app.steam_app_id
            logger.info(f"Launching Steam for app {steam_app_id}")

            # Launch Steam with app URI
            # steam://run/APPID launches game immediately
            subprocess.Popen(
                ["steam", f"steam://run/{steam_app_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info(f"Steam launched for {app.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to launch Steam: {e}")
            return False

    def _install_non_steam_game(
        self,
        app: AppInfo,
        prefix_dir: Path,
        progress_callback=None,
    ) -> bool:
        """
        Install a non-Steam application via Proton.

        This downloads the installer and runs it through Proton.
        """
        import subprocess

        try:
            logger.info(f"Installing non-Steam app: {app.name}")

            # Step 1: Download installer
            installer_path = self._download_installer(
                app.installer_url,
                prefix_dir,
                progress_callback,
            )

            if not installer_path or not installer_path.exists():
                logger.error("Failed to download installer")
                return False

            logger.info(f"Installer downloaded: {installer_path}")

            # Step 2: Run installer via Proton
            success = self._run_installer_via_proton(installer_path, prefix_dir, app)

            if not success:
                logger.error("Failed to run installer via Proton")
                return False

            logger.info(f"Installer completed")

            # Step 3: Clean up installer
            try:
                installer_path.unlink()
                logger.info("Installer cleaned up")
            except Exception as e:
                logger.warning(f"Could not delete installer: {e}")

            return True

        except Exception as e:
            logger.error(f"Exception during non-Steam installation: {e}")
            return False

    def _download_installer(
        self,
        url: str,
        dest_dir: Path,
        progress_callback=None,
    ) -> Optional[Path]:
        """
        Download installer file.

        Uses the same secure download mechanism as Wine installer.
        """
        import requests
        from src.utils.atomic_write import atomic_write_bytes

        try:
            logger.info(f"Downloading: {url}")

            # Get filename from URL
            filename = url.split("/")[-1] or "installer.exe"
            dest_path = dest_dir / filename

            # Download
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
                    downloaded += len(chunk)

                    if progress_callback and total_size:
                        progress_callback(downloaded, total_size)

            # Write atomically
            atomic_write_bytes(dest_path, content)

            logger.info(f"Download complete: {dest_path} ({len(content)} bytes)")
            return dest_path

        except requests.RequestException as e:
            logger.error(f"Download failed: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error downloading: {e}")
            return None

    def _run_installer_via_proton(
        self,
        installer_path: Path,
        prefix_dir: Path,
        app: AppInfo,
    ) -> bool:
        """
        Run Windows installer via Proton.

        Sets up environment variables and executes the installer
        with Proton as the WINE layer.
        """
        import subprocess

        try:
            logger.info(f"Running installer via Proton")

            # Prepare environment
            env = os.environ.copy()
            env["WINEPREFIX"] = str(prefix_dir)
            env["PROTON_NO_ESYNC"] = "1"  # Disable esync (can cause issues)
            env["DXVK_HUD"] = "off"  # Disable HUD overlay

            # Determine installer type and run
            installer_name = installer_path.name.lower()

            if installer_name.endswith(".msi"):
                # MSI installers need msiexec
                cmd = [
                    str(self.proton_path),
                    "run",
                    "msiexec",
                    "/i",
                    str(installer_path),
                    "/qb",  # Quiet with progress bar
                ]
            else:
                # Assume .exe installer
                cmd = [
                    str(self.proton_path),
                    "run",
                    str(installer_path),
                ]

            logger.info(f"Executing: {' '.join(cmd)}")

            # Run installer
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                logger.info("Installer completed successfully")
                return True
            else:
                logger.error(f"Installer failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Installer timeout (10 minutes)")
            return False

        except Exception as e:
            logger.error(f"Error running installer: {e}")
            return False

    def _create_desktop_launcher(self, app: AppInfo, prefix_dir: Path) -> bool:
        """
        Create .desktop launcher for the application.

        Makes the app appear in the applications menu.
        """
        try:
            applications_dir = Path.home() / ".local" / "share" / "applications"
            applications_dir.mkdir(parents=True, exist_ok=True)

            # Create .desktop file
            desktop_content = f"""[Desktop Entry]
Type=Application
Name={app.name}
Comment=Installed via Proton
Exec=WINEPREFIX={prefix_dir} proton run {prefix_dir}/drive_c/Program Files/{app.id}/game.exe
Icon=application-x-ms-dos-executable
Categories=Games;
"""

            desktop_path = applications_dir / f"proton-{app.id}.desktop"
            from src.utils.atomic_write import atomic_write_text
            atomic_write_text(desktop_path, desktop_content, mode=0o755)

            logger.info(f"Desktop launcher created: {desktop_path}")
            return True

        except Exception as e:
            logger.warning(f"Failed to create launcher: {e}")
            return False

    def _save_app_config(self, app: AppInfo, prefix_dir: Path) -> bool:
        """Save application configuration for later retrieval."""
        try:
            config_dir = Path.home() / ".local" / "share" / "neuron-os" / "apps"
            config_dir.mkdir(parents=True, exist_ok=True)

            config_data = {
                "id": app.id,
                "name": app.name,
                "installer_layer": "proton",
                "proton_version": self.proton_version,
                "prefix_path": str(prefix_dir),
                "installed_at": str(Path.ctime(prefix_dir)),
            }

            config_file = config_dir / f"{app.id}.json"
            from src.utils.atomic_write import atomic_write_json
            atomic_write_json(config_file, config_data)

            logger.info(f"App config saved: {config_file}")
            return True

        except Exception as e:
            logger.warning(f"Failed to save config: {e}")
            return False

    def _find_steam_directory(self) -> Optional[Path]:
        """Find Steam installation directory."""
        steam_paths = [
            Path.home() / ".steam" / "steam",
            Path.home() / ".local" / "share" / "steam",
            Path("/opt/steam"),
            Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
        ]

        for path in steam_paths:
            if path.exists():
                logger.debug(f"Found Steam at: {path}")
                return path

        return None

    def uninstall(self, app_id: str) -> bool:
        """Uninstall a Proton-installed application."""
        try:
            prefix_dir = (
                Path.home()
                / ".local"
                / "share"
                / "neuron-os"
                / "proton-prefixes"
                / app_id
            )

            if prefix_dir.exists():
                import shutil
                shutil.rmtree(prefix_dir)
                logger.info(f"Proton prefix removed: {prefix_dir}")

            # Remove desktop launcher
            desktop_path = (
                Path.home() / ".local" / "share" / "applications" / f"proton-{app_id}.desktop"
            )
            if desktop_path.exists():
                desktop_path.unlink()

            # Remove config
            config_path = (
                Path.home()
                / ".local"
                / "share"
                / "neuron-os"
                / "apps"
                / f"{app_id}.json"
            )
            if config_path.exists():
                config_path.unlink()

            logger.info(f"App uninstalled: {app_id}")
            return True

        except Exception as e:
            logger.error(f"Error uninstalling app: {e}")
            return False
```

### 2.2: Update AppInfo Dataclass

**File**: `src/store/app_catalog.py`

**Add optional steam_app_id field**:

```python
@dataclass
class AppInfo:
    """Application information for store."""

    id: str                                # "witcher3"
    name: str                              # "The Witcher 3"
    category: str                          # "games", "apps"
    layer: CompatibilityLayer              # PROTON, WINE, VM_WINDOWS, etc.
    installer_url: str                     # URL to .exe/.msi
    installer_sha256: Optional[str] = None # For verification
    installer_size: Optional[int] = None   # In bytes
    description: str = ""                  # User-friendly description

    # ADDED: Steam game ID (optional, for Steam games)
    steam_app_id: Optional[str] = None     # "292030" for Witcher 3

    # ... other existing fields ...
```

### 2.3: Update apps.json

**File**: `data/apps.json`

**Add steam_app_id for Steam games**:

```json
{
  "apps": [
    {
      "id": "witcher3",
      "name": "The Witcher 3: Wild Hunt",
      "category": "games",
      "layer": "PROTON",
      "steam_app_id": "292030",
      "installer_url": "",
      "description": "Action RPG by CD Projekt Red"
    },
    {
      "id": "starfield",
      "name": "Starfield",
      "category": "games",
      "layer": "PROTON",
      "steam_app_id": "1716740",
      "installer_url": "",
      "description": "Space exploration game by Bethesda"
    },
    {
      "id": "photoshop",
      "name": "Adobe Photoshop 2024",
      "category": "design",
      "layer": "PROTON",
      "installer_url": "https://example.com/photoshop_2024_installer.exe",
      "installer_sha256": "abc123...",
      "description": "Professional image editing software"
    }
  ]
}
```

---

## Part 3: Testing

### 3.1: Create Tests

**File**: `tests/test_proton_installer.py` (NEW FILE)

```python
"""Tests for Proton installer."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.store.installer import ProtonInstaller
from src.store.app_catalog import AppInfo, CompatibilityLayer


@pytest.fixture
def temp_steam_dir():
    """Create a mock Steam directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        steam_dir = Path(tmpdir) / "steam"
        steam_dir.mkdir()

        # Create Proton directory structure
        proton_dir = steam_dir / "steamapps" / "compatibilitytools" / "Proton-8.3"
        proton_dir.mkdir(parents=True, exist_ok=True)
        (proton_dir / "proton").touch()

        yield steam_dir


def test_proton_detection(temp_steam_dir):
    """Test that Proton version is detected."""
    installer = ProtonInstaller()
    installer.steam_dir = temp_steam_dir

    version = installer._detect_proton_version()
    assert version == "Proton-8.3"


def test_steam_location_fallback(temp_steam_dir):
    """Test that Steam is found in alternative locations."""
    installer = ProtonInstaller()

    # Mock the home directory to point to temp dir
    with patch("pathlib.Path.home", return_value=temp_steam_dir.parent):
        # Create Steam in alternate location
        steam_alt = temp_steam_dir.parent / ".local" / "share" / "steam"
        steam_alt.mkdir(parents=True, exist_ok=True)

        found = installer._check_steam_installed()
        assert found


def test_proton_prefix_creation(temp_steam_dir):
    """Test that Proton prefix is created."""
    installer = ProtonInstaller()
    installer.steam_dir = temp_steam_dir
    installer.proton_version = "Proton-8.3"

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            prefix = installer._create_proton_prefix("testapp")
            assert prefix is not None
            assert prefix.exists()
            assert "proton-prefixes" in str(prefix)


def test_steam_game_detection():
    """Test that Steam games are detected vs non-Steam apps."""
    installer = ProtonInstaller()

    # Steam game (has steam_app_id)
    steam_game = Mock()
    steam_game.steam_app_id = "292030"
    assert installer._is_steam_game(steam_game)

    # Non-Steam app (no steam_app_id)
    non_steam = Mock()
    non_steam.steam_app_id = None
    assert not installer._is_steam_game(non_steam)


def test_installer_download_progress():
    """Test that download progress is reported."""
    installer = ProtonInstaller()

    progress_updates = []

    def progress_cb(downloaded, total):
        progress_updates.append((downloaded, total))

    # Mock requests.get to simulate download
    mock_response = MagicMock()
    mock_response.headers = {"content-length": "1000"}
    mock_response.iter_content = lambda chunk_size: [b"x" * 500, b"x" * 500]

    with patch("requests.get", return_value=mock_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer._download_installer(
                "http://example.com/installer.exe",
                Path(tmpdir),
                progress_cb,
            )

            assert result is not None
            assert len(progress_updates) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 3.2: Run Tests

```bash
pytest tests/test_proton_installer.py -v
```

---

## Verification Checklist

Before moving to Phase 1.5:

**Proton Detection**:
- [ ] Steam location detected correctly
- [ ] Proton version detected from ~/.steam/steamapps/compatibilitytools
- [ ] Fallback locations checked (Flatpak, etc.)
- [ ] Error handling if Proton not found

**Installation Workflow**:
- [ ] Prefix created successfully
- [ ] Installer downloaded from URL
- [ ] Download progress reported to callback
- [ ] Installer executed via Proton
- [ ] MSI installers handled via msiexec
- [ ] EXE installers run directly
- [ ] Desktop launcher created
- [ ] App config saved

**Steam Game Support**:
- [ ] Steam games detected by steam_app_id
- [ ] Steam URI launched correctly (steam://run/APPID)
- [ ] Non-Steam apps installed normally
- [ ] Both paths work without errors

**Error Handling**:
- [ ] Steam not installed handled gracefully
- [ ] Proton not found shows clear error
- [ ] Download failure handled
- [ ] Installer failure captured and reported
- [ ] Timeout on long installations handled
- [ ] Permission errors caught

**Configuration**:
- [ ] App config saved to ~/.local/share/neuron-os/apps/
- [ ] Prefix path recorded
- [ ] Proton version recorded
- [ ] Config loaded correctly on next access

**Tests**:
- [ ] test_proton_detection passes
- [ ] test_steam_location_fallback passes
- [ ] test_proton_prefix_creation passes
- [ ] test_steam_game_detection passes
- [ ] test_installer_download_progress passes

---

## Acceptance Criteria

✅ **Phase 1.4 Complete When**:

1. ProtonInstaller downloads and executes installers
2. Both Steam and non-Steam games supported
3. All tests pass
4. Proper error messages on failures
5. Progress is reported during downloads

❌ **Phase 1.4 Fails If**:

- Installer download incomplete
- Proton execution fails silently
- No way to track progress
- Missing error handling

---

## Risks & Mitigations

### Risk 1: Proton Installation Timeout

**Issue**: Large installers take > 10 minutes

**Mitigation**:
- Timeout set to 600 seconds (10 min) - adjust if needed
- Show progress during installation
- Allow user cancellation

### Risk 2: Steam Not Installed

**Issue**: System has Proton but not Steam

**Mitigation**:
- Detect Proton separately
- Provide clear error message
- Fall back to Wine for non-Steam apps

### Risk 3: Version Conflicts

**Issue**: Multiple Proton versions installed

**Mitigation**:
- Use newest version (sorted reverse)
- Make version selectable in config
- Document in app info

---

## Next Steps

1. **Phase 1.5** adds encryption to guest agent
2. After Phase 1 complete, move to Phase 2

Good luck! 🚀
