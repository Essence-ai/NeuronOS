"""
App Installer - Handles installation of applications via various methods.

Supports:
- Native packages (pacman)
- Flatpak apps
- Wine applications
- VM-based Windows/macOS apps
"""

from __future__ import annotations

import logging
import subprocess
import os
import shutil
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse, unquote

from .app_catalog import AppInfo, CompatibilityLayer

logger = logging.getLogger(__name__)


# ============================================================================
# Security Functions - Path Safety and Download Verification
# ============================================================================

def _safe_filename(url: str, default: str = "download") -> str:
    """
    Extract safe filename from URL, preventing path traversal attacks.
    
    Prevents attacks where malicious URLs contain:
    - Path separators: ../../../etc/passwd
    - URL-encoded traversal: %2e%2e%2f
    
    Args:
        url: URL to extract filename from
        default: Default filename if extraction fails
        
    Returns:
        Safe filename string
    """
    try:
        # Parse URL and get path
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Get just the filename (last component)
        filename = PurePosixPath(path).name
        
        # Remove any remaining path separators (paranoid check)
        filename = filename.replace("/", "").replace("\\", "").replace("..", "")
        
        # Validate filename
        if not filename or filename.startswith("."):
            return default
        
        # Limit length to filesystem max
        if len(filename) > 255:
            # Keep extension if present
            base, ext = os.path.splitext(filename)
            filename = base[:255 - len(ext)] + ext
        
        return filename
    except Exception:
        return default


def _ensure_within_directory(base: Path, target: Path) -> Path:
    """
    Ensure target path is within base directory.
    
    Raises ValueError if path traversal detected.
    
    Args:
        base: Base directory path
        target: Target path to validate
        
    Returns:
        Resolved target path
        
    Raises:
        ValueError: If target escapes base directory
    """
    # Resolve both paths to absolute
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    
    # Check that target is within base
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected: {target} escapes {base}")
    
    return target_resolved


def _verify_download(file_path: Path, expected_sha256: Optional[str]) -> bool:
    """
    Verify downloaded file matches expected SHA256 hash.
    
    Args:
        file_path: Path to downloaded file
        expected_sha256: Expected SHA256 hash (hex string)
        
    Returns:
        True if hash matches or no hash provided, False otherwise
    """
    if expected_sha256 is None:
        return True  # No verification available
    
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest().lower()
        expected_hash = expected_sha256.lower()
        
        if actual_hash != expected_hash:
            logger.error(f"Hash mismatch: expected {expected_hash}, got {actual_hash}")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to verify download: {e}")
        return False


class InstallStatus(Enum):
    """Status of an installation."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    CONFIGURING = "configuring"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class InstallProgress:
    """Progress tracking for installations."""
    percent: int = 0
    message: str = ""
    status: InstallStatus = InstallStatus.PENDING
    callback: Optional[Callable[[int, str, InstallStatus], None]] = None

    def update(self, percent: int, message: str = "", status: Optional[InstallStatus] = None) -> None:
        self.percent = percent
        self.message = message
        if status:
            self.status = status
        if self.callback:
            self.callback(percent, message, self.status)


class BaseInstaller(ABC):
    """Base class for app installers."""

    @abstractmethod
    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        """Install an application."""
        pass

    @abstractmethod
    def uninstall(self, app: AppInfo) -> bool:
        """Uninstall an application."""
        pass

    @abstractmethod
    def is_installed(self, app: AppInfo) -> bool:
        """Check if app is installed."""
        pass

    def get_install_path(self, app: AppInfo) -> Optional[Path]:
        """Get installation path for an app."""
        return None


class PacmanInstaller(BaseInstaller):
    """Installer for native Arch packages via pacman."""

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        if not app.package_name:
            logger.error(f"No package name for {app.id}")
            return False

        progress.update(10, f"Installing {app.package_name}...", InstallStatus.INSTALLING)

        try:
            result = subprocess.run(
                ["sudo", "pacman", "-S", "--noconfirm", "--needed", app.package_name],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                progress.update(100, "Installation complete", InstallStatus.COMPLETE)
                return True
            else:
                logger.error(f"pacman failed: {result.stderr}")
                progress.update(0, f"Installation failed: {result.stderr}", InstallStatus.FAILED)
                return False

        except subprocess.TimeoutExpired:
            logger.error("Installation timed out")
            progress.update(0, "Installation timed out", InstallStatus.FAILED)
            return False
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            progress.update(0, str(e), InstallStatus.FAILED)
            return False

    def uninstall(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["sudo", "pacman", "-R", "--noconfirm", app.package_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0

        except Exception as e:
            logger.error(f"Uninstall failed: {e}")
            return False

    def is_installed(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["pacman", "-Q", app.package_name],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False


class FlatpakInstaller(BaseInstaller):
    """Installer for Flatpak applications."""

    FLATHUB_REMOTE = "flathub"

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        if not app.package_name:
            logger.error(f"No Flatpak ID for {app.id}")
            return False

        # Ensure Flathub is added
        self._ensure_flathub()

        progress.update(10, f"Installing {app.package_name} from Flathub...", InstallStatus.DOWNLOADING)

        try:
            result = subprocess.run(
                ["flatpak", "install", "-y", self.FLATHUB_REMOTE, app.package_name],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode == 0:
                progress.update(100, "Installation complete", InstallStatus.COMPLETE)
                return True
            else:
                logger.error(f"Flatpak install failed: {result.stderr}")
                progress.update(0, "Installation failed", InstallStatus.FAILED)
                return False

        except subprocess.TimeoutExpired:
            logger.error("Flatpak installation timed out")
            return False
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False

    def _ensure_flathub(self) -> None:
        """Ensure Flathub remote is configured."""
        try:
            subprocess.run(
                ["flatpak", "remote-add", "--if-not-exists", "flathub",
                 "https://flathub.org/repo/flathub.flatpakrepo"],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass

    def uninstall(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["flatpak", "uninstall", "-y", app.package_name],
                capture_output=True,
                timeout=60,
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_installed(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return app.package_name in result.stdout
        except Exception:
            return False


class WineInstaller(BaseInstaller):
    """Installer for Windows applications via Wine."""

    WINE_PREFIX_BASE = Path.home() / ".local/share/neuron-os/wine-prefixes"

    def __init__(self):
        self.WINE_PREFIX_BASE.mkdir(parents=True, exist_ok=True)

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        """
        Install a Windows app via Wine.
        """
        progress.update(10, "Creating Wine prefix...", InstallStatus.CONFIGURING)

        prefix_path = self._get_prefix_path(app)
        prefix_path.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)
        env["WINEDEBUG"] = "-all"

        # Initialize prefix
        try:
            progress.update(20, "Initializing Wine prefix...", InstallStatus.CONFIGURING)
            subprocess.run(
                ["wineboot", "--init"],
                env=env,
                capture_output=True,
                timeout=120,
            )
        except Exception as e:
            logger.error(f"Failed to initialize Wine prefix: {e}")
            progress.update(0, "Failed to initialize Wine", InstallStatus.FAILED)
            return False

        # If there's an installer URL, download and run it
        installer_url = getattr(app, 'installer_url', None)
        if installer_url:
            progress.update(40, "Downloading installer...", InstallStatus.DOWNLOADING)

            # SECURITY: Use safe filename extraction to prevent path traversal
            installer_name = _safe_filename(installer_url, "installer.exe")
            if not installer_name.lower().endswith(('.exe', '.msi')):
                installer_name += ".exe"

            # SECURITY: Validate download path stays within prefix
            download_path = _ensure_within_directory(
                prefix_path,
                prefix_path / installer_name
            )

            try:
                import requests
                response = requests.get(installer_url, stream=True)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))

                with open(download_path, 'wb') as f:
                    if total_size == 0:
                        f.write(response.content)
                    else:
                        downloaded = 0
                        for data in response.iter_content(chunk_size=8192):
                            downloaded += len(data)
                            f.write(data)
                            done = int(50 * downloaded / total_size)
                            progress.update(40 + done, f"Downloading: {downloaded/1024/1024:.1f}MB")

                progress.update(90, "Launching installer...", InstallStatus.INSTALLING)
                cmd = ["wine", str(download_path)]
                if installer_name.lower().endswith('.msi'):
                    cmd = ["wine", "msiexec", "/i", str(download_path)]

                subprocess.Popen(cmd, env=env, start_new_session=True)
                progress.update(100, "Installer launched - please complete setup", InstallStatus.COMPLETE)
                return True

            except Exception as e:
                logger.error(f"Download/Run failed: {e}")
                progress.update(0, f"Error: {str(e)}", InstallStatus.FAILED)
                return False

        progress.update(100, "Wine prefix ready", InstallStatus.COMPLETE)

        # Create desktop entry so the app can be found
        self._create_desktop_entry(app)

        return True

    def _create_desktop_entry(self, app: AppInfo) -> None:
        """Create a .desktop file for the Wine app."""
        prefix_path = self._get_prefix_path(app)

        # Create desktop entry in user's applications folder
        desktop_dir = Path.home() / ".local/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = desktop_dir / f"neuron-wine-{app.id}.desktop"

        # Create a launcher script
        launcher_dir = Path.home() / ".local/share/neuron-os/launchers"
        launcher_dir.mkdir(parents=True, exist_ok=True)
        launcher_script = launcher_dir / f"{app.id}.sh"

        # Write launcher script
        launcher_content = f"""#!/bin/bash
export WINEPREFIX="{prefix_path}"
export WINEDEBUG="-all"

# Find the main executable in the Wine prefix
EXE_PATH=$(find "$WINEPREFIX/drive_c" -iname "*.exe" -type f 2>/dev/null | grep -iv uninstall | grep -iv setup | head -1)

if [ -n "$EXE_PATH" ]; then
    wine "$EXE_PATH" "$@"
else
    # Open file manager at prefix location for manual selection
    xdg-open "$WINEPREFIX/drive_c"
fi
"""
        try:
            launcher_script.write_text(launcher_content)
            launcher_script.chmod(0o755)

            # Write desktop entry
            desktop_content = f"""[Desktop Entry]
Name={app.name}
Comment={app.description}
Exec={launcher_script}
Icon=wine
Type=Application
Categories=Wine;Application;
Keywords={';'.join(getattr(app, 'tags', []))};
"""
            desktop_file.write_text(desktop_content)
            logger.info(f"Created desktop entry for {app.name}")
        except Exception as e:
            logger.warning(f"Failed to create desktop entry: {e}")

    def uninstall(self, app: AppInfo) -> bool:
        """Remove Wine prefix for an app."""
        prefix_path = self._get_prefix_path(app)

        # Remove desktop entry and launcher
        desktop_file = Path.home() / ".local/share/applications" / f"neuron-wine-{app.id}.desktop"
        launcher_script = Path.home() / ".local/share/neuron-os/launchers" / f"{app.id}.sh"

        if desktop_file.exists():
            desktop_file.unlink()
        if launcher_script.exists():
            launcher_script.unlink()

        if prefix_path.exists():
            shutil.rmtree(prefix_path)
            return True
        return False

    def is_installed(self, app: AppInfo) -> bool:
        """Check if Wine prefix exists for app."""
        prefix_path = self._get_prefix_path(app)
        return prefix_path.exists() and (prefix_path / "drive_c").exists()

    def _get_prefix_path(self, app: AppInfo) -> Path:
        """Get Wine prefix path for an app."""
        return self.WINE_PREFIX_BASE / app.id

    def get_install_path(self, app: AppInfo) -> Optional[Path]:
        return self._get_prefix_path(app)

    def run_app(self, app: AppInfo, exe_path: str) -> bool:
        """Run a Windows app in its Wine prefix."""
        prefix_path = self._get_prefix_path(app)
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
            logger.error(f"Failed to run Wine app: {e}")
            return False


class VMInstaller(BaseInstaller):
    """
    Installer for apps that require a Windows/macOS VM.
    
    Integrates with VM Manager to:
    - Find or create appropriate VMs
    - Start VMs and open display
    - Track which apps are installed in which VMs
    """

    CONFIG_PATH = Path.home() / ".config/neuronos/vm-apps"

    def __init__(self):
        self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        self._vm_manager = None

    def _get_vm_manager(self):
        """Lazy-load VM manager."""
        if self._vm_manager is None:
            try:
                from vm_manager.core.libvirt_manager import LibvirtManager
                self._vm_manager = LibvirtManager()
                self._vm_manager.connect()
            except Exception as e:
                logger.warning(f"Could not connect to libvirt: {e}")
        return self._vm_manager

    def _find_compatible_vm(self, vm_type: str) -> Optional[str]:
        """
        Find an existing VM compatible with the app.

        Args:
            vm_type: "windows" or "macos"

        Returns:
            VM name if found, None otherwise
        """
        manager = self._get_vm_manager()
        if not manager:
            return None

        try:
            vms = manager.list_vms()
            for vm in vms:
                vm_name_lower = vm.name.lower()
                if vm_type == "windows" and any(
                    w in vm_name_lower for w in ["windows", "win10", "win11"]
                ):
                    return vm.name
                elif vm_type == "macos" and any(
                    m in vm_name_lower for m in ["macos", "mac", "osx"]
                ):
                    return vm.name
        except Exception as e:
            logger.error(f"Failed to list VMs: {e}")

        return None

    def _open_vm_display(self, vm_name: str):
        """Open display for VM (Looking Glass or virt-viewer)."""
        lg_config = Path.home() / ".config/neuronos/vms" / vm_name / "looking-glass.json"

        if lg_config.exists():
            try:
                from vm_manager.core.looking_glass import get_looking_glass_manager
                lg_manager = get_looking_glass_manager()
                lg_manager.start(vm_name)
                return
            except Exception as e:
                logger.warning(f"Looking Glass failed: {e}")

        # Fall back to virt-viewer (with validated VM name)
        import re
        if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,63}$', vm_name):
            subprocess.Popen(
                ["virt-viewer", "-c", "qemu:///system", vm_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        """
        Install an app that requires a VM.

        1. Checks system requirements
        2. Finds or suggests creating appropriate VM
        3. Starts VM and opens display
        4. Creates app entry for tracking
        """
        progress.update(10, "Checking VM requirements...", InstallStatus.CONFIGURING)

        vm_type = "windows" if app.layer == CompatibilityLayer.VM_WINDOWS else "macos"

        # Check system requirements
        if not self._check_requirements(app, progress):
            return False

        progress.update(20, f"Looking for {vm_type} VM...", InstallStatus.CONFIGURING)

        # Find compatible VM
        vm_name = self._find_compatible_vm(vm_type)

        if not vm_name:
            progress.update(
                30,
                f"No {vm_type} VM found. Please create one in VM Manager first.",
                InstallStatus.FAILED,
            )
            # Try to launch VM Manager for creation
            try:
                subprocess.Popen(
                    ["neuron-vm-manager", "--create", vm_type],
                    start_new_session=True,
                )
            except FileNotFoundError:
                pass
            return False

        progress.update(50, f"Starting VM: {vm_name}...", InstallStatus.INSTALLING)

        # Start VM if not running
        manager = self._get_vm_manager()
        if manager:
            try:
                vms = manager.list_vms()
                vm = next((v for v in vms if v.name == vm_name), None)

                if vm and getattr(vm.state, 'value', vm.state) != "running":
                    manager.start_vm(vm_name)
                    progress.update(60, "VM starting...", InstallStatus.INSTALLING)

                    # Wait for VM to start
                    import time
                    for _ in range(15):
                        time.sleep(1)
                        vms = manager.list_vms()
                        vm = next((v for v in vms if v.name == vm_name), None)
                        if vm and getattr(vm.state, 'value', vm.state) == "running":
                            break

            except Exception as e:
                logger.error(f"Failed to start VM: {e}")

        progress.update(70, "Opening VM display...", InstallStatus.INSTALLING)

        # Open display
        self._open_vm_display(vm_name)

        progress.update(80, "Creating app entry...", InstallStatus.CONFIGURING)

        # Save app configuration
        from datetime import datetime
        app_config = {
            "app_id": app.id,
            "app_name": app.name,
            "vm_type": vm_type,
            "vm_name": vm_name,
            "requires_gpu": app.requires_gpu_passthrough,
            "min_ram_gb": getattr(app, 'min_ram_gb', 8),
            "installed_at": datetime.now().isoformat(),
            "installed_in_vm": False,
        }

        try:
            from utils.atomic_write import atomic_write_json
            atomic_write_json(self.CONFIG_PATH / f"{app.id}.json", app_config)
        except ImportError:
            import json
            config_file = self.CONFIG_PATH / f"{app.id}.json"
            config_file.write_text(json.dumps(app_config, indent=2))

        progress.update(
            100,
            f"VM opened. Install {app.name} inside, then mark as complete.",
            InstallStatus.COMPLETE,
        )
        return True

    def _check_requirements(self, app: AppInfo, progress: InstallProgress) -> bool:
        """Check if system meets requirements for VM app."""
        # Check RAM
        min_ram = getattr(app, 'min_ram_gb', 8)
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        total_kb = int(line.split()[1])
                        total_gb = total_kb / 1024 / 1024
                        if total_gb < min_ram + 8:  # Need RAM for host too
                            progress.update(0, f"Insufficient RAM: {total_gb:.1f}GB, need {min_ram + 8}GB", InstallStatus.FAILED)
                            return False
                        break
        except Exception:
            pass

        # Check for GPU passthrough if required
        if app.requires_gpu_passthrough:
            # Check IOMMU
            try:
                result = subprocess.run(
                    ["dmesg"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if "IOMMU enabled" not in result.stdout and "AMD-Vi" not in result.stdout:
                    progress.update(0, "IOMMU not enabled - GPU passthrough unavailable", InstallStatus.FAILED)
                    return False
            except Exception:
                pass

        return True

    def uninstall(self, app: AppInfo) -> bool:
        """Remove VM app configuration."""
        config_file = Path.home() / ".config/neuron-os/vm-apps" / f"{app.id}.json"
        if config_file.exists():
            config_file.unlink()
            return True
        return False

    def is_installed(self, app: AppInfo) -> bool:
        """Check if VM app is configured."""
        config_file = Path.home() / ".config/neuron-os/vm-apps" / f"{app.id}.json"
        return config_file.exists()


class ProtonInstaller(BaseInstaller):
    """
    Installer for games and apps via Steam's Proton.

    Proton is Valve's compatibility layer for running Windows games/apps
    on Linux. This installer handles:
    - Ensuring Steam is installed
    - Configuring Steam for non-Steam games
    - Setting up Proton prefixes
    """

    STEAM_APPS_PATH = Path.home() / ".local/share/Steam/steamapps"
    PROTON_PATH = STEAM_APPS_PATH / "common"
    COMPAT_DATA_PATH = STEAM_APPS_PATH / "compatdata"
    CONFIG_PATH = Path.home() / ".config/neuronos/proton-apps"

    def __init__(self):
        self._steam_installed: Optional[bool] = None
        self._available_proton_versions: List[str] = []
        self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    def _check_steam(self) -> bool:
        """Check if Steam is installed."""
        if self._steam_installed is not None:
            return self._steam_installed

        # Check for Steam binary
        steam_paths = [
            Path("/usr/bin/steam"),
            Path("/usr/bin/steam-runtime"),
            Path.home() / ".steam/steam.sh",
        ]

        for path in steam_paths:
            if path.exists():
                self._steam_installed = True
                return True

        # Check if Flatpak Steam exists
        try:
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "com.valvesoftware.Steam" in result.stdout:
                self._steam_installed = True
                return True
        except Exception:
            pass

        self._steam_installed = False
        return False

    def _get_proton_versions(self) -> List[str]:
        """Get list of installed Proton versions."""
        if self._available_proton_versions:
            return self._available_proton_versions

        versions = []

        # Check common Steam library locations
        library_paths = [
            self.PROTON_PATH,
            Path.home() / ".steam/steam/steamapps/common",
        ]

        for lib_path in library_paths:
            if not lib_path.exists():
                continue

            try:
                for item in lib_path.iterdir():
                    if item.is_dir() and item.name.startswith("Proton"):
                        versions.append(item.name)
            except PermissionError:
                continue

        # Sort by version (Proton 8.0 > Proton 7.0)
        versions.sort(key=lambda x: x.split()[-1] if " " in x else x, reverse=True)
        self._available_proton_versions = versions
        return versions

    def _get_recommended_proton(self) -> Optional[Path]:
        """Get path to recommended Proton version."""
        versions = self._get_proton_versions()

        # Prefer stable versions
        preferred_order = [
            "Proton 9",
            "Proton 8",
            "Proton-8",
            "Proton Experimental",
            "Proton 7",
            "GE-Proton",
        ]

        for preferred in preferred_order:
            for version in versions:
                if preferred in version:
                    return self.PROTON_PATH / version

        # Fall back to first available
        if versions:
            return self.PROTON_PATH / versions[0]

        return None

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        """
        Install an application via Proton.

        For Steam games: Returns instructions to install via Steam
        For non-Steam apps: Sets up Proton prefix and desktop entry
        """
        progress.update(10, "Checking Steam installation...", InstallStatus.CONFIGURING)

        if not self._check_steam():
            progress.update(
                0,
                "Steam is not installed. Please install Steam first.",
                InstallStatus.FAILED,
            )
            return False

        # Check Proton availability
        proton_path = self._get_recommended_proton()
        if not proton_path or not proton_path.exists():
            progress.update(
                0,
                "No Proton version found. Open Steam and install Proton from Library > Tools.",
                InstallStatus.FAILED,
            )
            return False

        progress.update(30, f"Using {proton_path.name}...", InstallStatus.CONFIGURING)

        # Check if this is a Steam game
        steam_app_id = getattr(app, 'proton_app_id', None)
        if steam_app_id:
            return self._install_steam_game(app, steam_app_id, progress)
        else:
            return self._install_non_steam(app, proton_path, progress)

    def _install_steam_game(
        self,
        app: AppInfo,
        steam_id: int,
        progress: InstallProgress,
    ) -> bool:
        """Handle Steam game installation."""
        progress.update(50, "Opening Steam to install game...", InstallStatus.INSTALLING)

        try:
            # Open Steam to the game's store page for installation
            subprocess.Popen(
                ["steam", f"steam://install/{steam_id}"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            progress.update(
                100,
                f"Steam opened for {app.name}. Complete installation there.",
                InstallStatus.COMPLETE,
            )
            return True

        except FileNotFoundError:
            # Try Flatpak Steam
            try:
                subprocess.Popen(
                    ["flatpak", "run", "com.valvesoftware.Steam", f"steam://install/{steam_id}"],
                    start_new_session=True,
                )
                progress.update(
                    100,
                    "Steam opened. Complete installation there.",
                    InstallStatus.COMPLETE,
                )
                return True
            except Exception:
                pass

        progress.update(0, "Could not launch Steam", InstallStatus.FAILED)
        return False

    def _install_non_steam(
        self,
        app: AppInfo,
        proton_path: Path,
        progress: InstallProgress,
    ) -> bool:
        """Install a non-Steam Windows app with Proton."""
        # Create Proton prefix for this app
        prefix_id = abs(hash(app.id)) % 1000000 + 1000000
        prefix_path = self.COMPAT_DATA_PATH / str(prefix_id)

        progress.update(40, "Creating Proton prefix...", InstallStatus.CONFIGURING)

        try:
            prefix_path.mkdir(parents=True, exist_ok=True)

            # Initialize prefix
            proton_exe = proton_path / "proton"
            env = os.environ.copy()
            env["STEAM_COMPAT_DATA_PATH"] = str(prefix_path)
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(Path.home() / ".steam/steam")

            # Run proton with wineboot to initialize
            subprocess.run(
                [str(proton_exe), "run", "wineboot", "--init"],
                env=env,
                capture_output=True,
                timeout=120,
            )

            progress.update(70, "Prefix created", InstallStatus.CONFIGURING)

        except Exception as e:
            logger.error(f"Failed to create Proton prefix: {e}")
            progress.update(0, f"Failed to create prefix: {e}", InstallStatus.FAILED)
            return False

        # Download installer if URL provided
        installer_url = getattr(app, 'installer_url', None)
        if installer_url:
            progress.update(75, "Downloading installer...", InstallStatus.DOWNLOADING)

            installer_name = _safe_filename(installer_url, "installer.exe")
            download_path = prefix_path / "pfx" / "drive_c" / installer_name

            download_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                import requests
                response = requests.get(installer_url, stream=True, timeout=300)
                response.raise_for_status()

                with open(download_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                progress.update(90, "Launching installer...", InstallStatus.INSTALLING)

                # Launch installer with Proton
                subprocess.Popen(
                    [str(proton_exe), "run", str(download_path)],
                    env=env,
                    start_new_session=True,
                )

            except Exception as e:
                logger.error(f"Failed to download/run installer: {e}")
                progress.update(0, f"Download failed: {e}", InstallStatus.FAILED)
                return False

        # Save configuration
        self._save_app_config(app, prefix_path, proton_path)

        progress.update(100, "Setup complete", InstallStatus.COMPLETE)
        return True

    def _save_app_config(self, app: AppInfo, prefix_path: Path, proton_path: Path):
        """Save app configuration for later launching."""
        from datetime import datetime

        config = {
            "app_id": app.id,
            "app_name": app.name,
            "prefix_path": str(prefix_path),
            "proton_path": str(proton_path),
            "installed_at": datetime.now().isoformat(),
        }

        try:
            from utils.atomic_write import atomic_write_json
            atomic_write_json(self.CONFIG_PATH / f"{app.id}.json", config)
        except ImportError:
            # Fallback if utils not available
            import json
            config_file = self.CONFIG_PATH / f"{app.id}.json"
            config_file.write_text(json.dumps(config, indent=2))

    def uninstall(self, app: AppInfo) -> bool:
        """Remove Proton app and its prefix."""
        config_path = self.CONFIG_PATH / f"{app.id}.json"

        if not config_path.exists():
            return False

        try:
            import json
            with open(config_path) as f:
                config = json.load(f)

            # Remove prefix
            prefix_path = Path(config.get("prefix_path", ""))
            if prefix_path.exists():
                shutil.rmtree(prefix_path)

            # Remove config
            config_path.unlink()

            return True
        except Exception as e:
            logger.error(f"Failed to uninstall {app.id}: {e}")
            return False

    def is_installed(self, app: AppInfo) -> bool:
        """Check if Proton app is configured."""
        # For Steam games, check if installed
        steam_app_id = getattr(app, 'proton_app_id', None)
        if steam_app_id:
            manifest = self.STEAM_APPS_PATH / f"appmanifest_{steam_app_id}.acf"
            return manifest.exists()

        # For non-Steam apps
        config_path = self.CONFIG_PATH / f"{app.id}.json"
        return config_path.exists()

    def get_install_path(self, app: AppInfo) -> Optional[Path]:
        """Get Proton prefix path."""
        config_path = self.CONFIG_PATH / f"{app.id}.json"

        if config_path.exists():
            try:
                import json
                with open(config_path) as f:
                    config = json.load(f)
                return Path(config.get("prefix_path", ""))
            except Exception:
                pass

        return None

class AppInstaller:
    """
    Main application installer.

    Routes installations to the appropriate backend based on
    the app's compatibility layer. Provides a unified interface
    for installing any app regardless of how it needs to run.
    """

    def __init__(self):
        self._installers: Dict[CompatibilityLayer, BaseInstaller] = {
            CompatibilityLayer.NATIVE: PacmanInstaller(),
            CompatibilityLayer.FLATPAK: FlatpakInstaller(),
            CompatibilityLayer.WINE: WineInstaller(),
            CompatibilityLayer.PROTON: ProtonInstaller(),  # Steam Proton support
            CompatibilityLayer.VM_WINDOWS: VMInstaller(),
            CompatibilityLayer.VM_MACOS: VMInstaller(),
        }
        self._progress_callback: Optional[Callable[[int, str, InstallStatus], None]] = None

    def set_progress_callback(
        self, callback: Callable[[int, str, InstallStatus], None]
    ) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def install(self, app: AppInfo) -> bool:
        """
        Install an application.

        Automatically routes to the correct installer based on the
        app's compatibility layer.

        Args:
            app: Application to install

        Returns:
            True if installation successful.
        """
        installer = self._installers.get(app.layer)

        if installer is None:
            logger.error(f"No installer for layer: {app.layer}")
            return False

        progress = InstallProgress(callback=self._progress_callback)
        return installer.install(app, progress)

    def uninstall(self, app: AppInfo) -> bool:
        """Uninstall an application."""
        installer = self._installers.get(app.layer)
        if installer:
            return installer.uninstall(app)
        return False

    def is_installed(self, app: AppInfo) -> bool:
        """Check if an application is installed."""
        installer = self._installers.get(app.layer)
        if installer:
            return installer.is_installed(app)
        return False

    def get_install_path(self, app: AppInfo) -> Optional[Path]:
        """Get installation path for an app if applicable."""
        installer = self._installers.get(app.layer)
        if installer:
            return installer.get_install_path(app)
        return None

    def get_installer_for_layer(self, layer: CompatibilityLayer) -> Optional[BaseInstaller]:
        """Get the installer for a specific layer."""
        return self._installers.get(layer)


# Convenience function
def install_app(app: AppInfo, progress_callback=None) -> bool:
    """
    Convenience function to install an app.

    Args:
        app: Application to install
        progress_callback: Optional callback for progress updates

    Returns:
        True if installation successful
    """
    installer = AppInstaller()
    if progress_callback:
        installer.set_progress_callback(progress_callback)
    return installer.install(app)
