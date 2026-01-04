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
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

from .app_catalog import AppInfo, CompatibilityLayer

logger = logging.getLogger(__name__)


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
                progress.update(0, f"Installation failed", InstallStatus.FAILED)
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

            installer_name = Path(installer_url).name or "installer.exe"
            if not installer_name.lower().endswith(('.exe', '.msi')):
                installer_name += ".exe"

            download_path = prefix_path / installer_name

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
        return True

    def uninstall(self, app: AppInfo) -> bool:
        """Remove Wine prefix for an app."""
        prefix_path = self._get_prefix_path(app)
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
    """Installer for apps that require a Windows/macOS VM."""

    VM_STORAGE_PATH = Path("/var/lib/neuron-os/vms")

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        """
        Install an app that requires a VM.

        This doesn't actually install the app - it configures the VM
        and prompts the user to install within the VM.
        """
        progress.update(10, "Checking VM requirements...", InstallStatus.CONFIGURING)

        # Check if appropriate VM exists
        vm_type = "windows" if app.layer == CompatibilityLayer.VM_WINDOWS else "macos"

        # Check system requirements
        if not self._check_requirements(app, progress):
            return False

        progress.update(50, f"Configuring for {vm_type} VM...", InstallStatus.CONFIGURING)

        # Create app configuration
        config_dir = Path.home() / ".config/neuron-os/vm-apps"
        config_dir.mkdir(parents=True, exist_ok=True)

        app_config = {
            "app_id": app.id,
            "app_name": app.name,
            "vm_type": vm_type,
            "requires_gpu": app.requires_gpu_passthrough,
            "min_ram_gb": getattr(app, 'min_ram_gb', 8),
            "installed_in_vm": False,
        }

        import json
        with open(config_dir / f"{app.id}.json", 'w') as f:
            json.dump(app_config, f, indent=2)

        progress.update(100, f"Ready - install {app.name} in {vm_type} VM", InstallStatus.COMPLETE)
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
