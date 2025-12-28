"""
App Installer - Handles installation of applications via various methods.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable

from .app_catalog import AppInfo, CompatibilityLayer

logger = logging.getLogger(__name__)


class InstallProgress:
    """Progress tracking for installations."""

    def __init__(self, callback: Optional[Callable[[int, str], None]] = None):
        self.callback = callback
        self.percent = 0
        self.message = ""

    def update(self, percent: int, message: str = "") -> None:
        self.percent = percent
        self.message = message
        if self.callback:
            self.callback(percent, message)


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


class PacmanInstaller(BaseInstaller):
    """Installer for native Arch packages via pacman."""

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        if not app.package_name:
            logger.error(f"No package name for {app.id}")
            return False

        progress.update(10, f"Installing {app.package_name}...")

        try:
            result = subprocess.run(
                ["sudo", "pacman", "-S", "--noconfirm", app.package_name],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                progress.update(100, "Installation complete")
                return True
            else:
                logger.error(f"pacman failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False

    def uninstall(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["sudo", "pacman", "-R", "--noconfirm", app.package_name],
                capture_output=True,
                text=True,
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
            )
            return result.returncode == 0
        except Exception:
            return False


class FlatpakInstaller(BaseInstaller):
    """Installer for Flatpak applications."""

    def install(self, app: AppInfo, progress: InstallProgress) -> bool:
        if not app.package_name:
            logger.error(f"No Flatpak ID for {app.id}")
            return False

        progress.update(10, f"Installing {app.package_name} from Flathub...")

        try:
            result = subprocess.run(
                ["flatpak", "install", "-y", "flathub", app.package_name],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                progress.update(100, "Installation complete")
                return True
            else:
                logger.error(f"Flatpak install failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False

    def uninstall(self, app: AppInfo) -> bool:
        if not app.package_name:
            return False

        try:
            result = subprocess.run(
                ["flatpak", "uninstall", "-y", app.package_name],
                capture_output=True,
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
            )
            return app.package_name in result.stdout
        except Exception:
            return False


class AppInstaller:
    """
    Main application installer.

    Routes installations to the appropriate backend based on
    the app's compatibility layer.
    """

    def __init__(self):
        self._installers = {
            CompatibilityLayer.NATIVE: PacmanInstaller(),
            CompatibilityLayer.FLATPAK: FlatpakInstaller(),
        }
        self._progress_callback: Optional[Callable[[int, str], None]] = None

    def set_progress_callback(
        self, callback: Callable[[int, str], None]
    ) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def install(self, app: AppInfo) -> bool:
        """
        Install an application.

        Args:
            app: Application to install

        Returns:
            True if installation successful.
        """
        installer = self._installers.get(app.layer)

        if installer is None:
            if app.layer in (CompatibilityLayer.VM_WINDOWS, CompatibilityLayer.VM_MACOS):
                logger.info(f"{app.name} requires a VM - launch VM Manager")
                return False
            elif app.layer in (CompatibilityLayer.WINE, CompatibilityLayer.PROTON):
                logger.info(f"{app.name} requires Wine/Proton setup")
                return False
            else:
                logger.error(f"No installer for layer: {app.layer}")
                return False

        progress = InstallProgress(self._progress_callback)
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
