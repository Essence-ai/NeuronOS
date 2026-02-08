"""
Wine Prefix Manager - Standalone management of Wine prefixes for NeuronOS.

Provides direct control over Wine prefixes independent of the store
installer workflow. Use this module when you need to:
- Create, list, or delete Wine prefixes
- Install Windows dependencies via winetricks
- Run arbitrary executables in a specific prefix
- Query Wine version and configuration

This module complements installer.WineInstaller, which handles the
store-driven install/uninstall lifecycle. The WineInstaller can
delegate to WineManager for prefix operations.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Base directory where all NeuronOS Wine prefixes are stored.
WINE_PREFIX_BASE = Path.home() / ".local/share/neuron-os/wine-prefixes"

#: Common winetricks verbs grouped by category for convenience.
WINETRICKS_CATEGORIES: Dict[str, List[str]] = {
    "vcredist": [
        "vcrun2005", "vcrun2008", "vcrun2010", "vcrun2012",
        "vcrun2013", "vcrun2015", "vcrun2017", "vcrun2019",
        "vcrun2022",
    ],
    "dotnet": [
        "dotnet20", "dotnet35", "dotnet40", "dotnet45",
        "dotnet46", "dotnet48",
    ],
    "directx": [
        "d3dx9", "d3dx10", "d3dx11_42", "d3dx11_43",
        "d3dcompiler_43", "d3dcompiler_47", "dxvk",
    ],
    "fonts": [
        "corefonts", "tahoma", "arial",
    ],
    "libraries": [
        "mfc42", "vb6run", "physx", "xna40",
    ],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WinePrefixInfo:
    """Information about a single Wine prefix.

    Attributes:
        name: Human-readable prefix name (directory basename).
        path: Absolute path to the prefix directory.
        arch: Windows architecture (``win32`` or ``win64``).
        size_bytes: Total size on disk in bytes, or -1 if unknown.
        created: Creation timestamp if available.
        has_drive_c: Whether the prefix has been fully initialized.
    """
    name: str
    path: Path
    arch: str = "win64"
    size_bytes: int = -1
    created: Optional[datetime] = None
    has_drive_c: bool = False

    @property
    def size_mb(self) -> float:
        """Return size in megabytes, or 0.0 if unknown."""
        if self.size_bytes <= 0:
            return 0.0
        return self.size_bytes / (1024 * 1024)


@dataclass
class WineVersionInfo:
    """Version information for the Wine installation.

    Attributes:
        version: Full version string (e.g. ``wine-9.0``).
        is_staging: Whether Wine Staging patches are present.
        arch: Host architecture reported by Wine.
        path: Path to the ``wine`` binary.
    """
    version: str = "unknown"
    is_staging: bool = False
    arch: str = "unknown"
    path: Optional[Path] = None


# ---------------------------------------------------------------------------
# WineManager
# ---------------------------------------------------------------------------

class WineManager:
    """Manage Wine prefixes used by NeuronOS.

    This class provides a high-level API for creating, listing, and
    deleting Wine prefixes, running executables inside them, and
    installing Windows dependencies through *winetricks*.

    All prefixes are stored under
    ``~/.local/share/neuron-os/wine-prefixes/<name>/``.

    Example::

        manager = WineManager()
        manager.create_prefix("my-app", arch="win64")
        manager.install_dependencies("my-app", ["vcrun2019", "d3dx9"])
        manager.run_executable("my-app", "/path/to/setup.exe")
    """

    def __init__(self, prefix_base: Optional[Path] = None) -> None:
        """Initialise the Wine manager.

        Args:
            prefix_base: Override the default prefix base directory.
                         Defaults to ``WINE_PREFIX_BASE``.
        """
        self._prefix_base = prefix_base or WINE_PREFIX_BASE
        self._prefix_base.mkdir(parents=True, exist_ok=True)
        self._wine_version: Optional[WineVersionInfo] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def prefix_base(self) -> Path:
        """Return the base directory for all prefixes."""
        return self._prefix_base

    # ------------------------------------------------------------------
    # Wine version helpers
    # ------------------------------------------------------------------

    def get_wine_version(self) -> WineVersionInfo:
        """Detect the installed Wine version.

        Runs ``wine --version`` and parses the output to populate a
        :class:`WineVersionInfo` instance.  The result is cached for
        the lifetime of this ``WineManager`` instance.

        Returns:
            A :class:`WineVersionInfo` with whatever information could
            be gathered.  If Wine is not installed the *version* field
            will be ``"not installed"``.
        """
        if self._wine_version is not None:
            return self._wine_version

        info = WineVersionInfo()

        # Locate the wine binary
        wine_path = shutil.which("wine")
        if wine_path:
            info.path = Path(wine_path)
        else:
            info.version = "not installed"
            self._wine_version = info
            return info

        # Query version
        try:
            result = subprocess.run(
                ["wine", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()
                info.version = version_str
                info.is_staging = "staging" in version_str.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Failed to query Wine version: %s", exc)

        # Query architecture
        try:
            result = subprocess.run(
                ["wine", "cmd", "/c", "echo", "%PROCESSOR_ARCHITECTURE%"],
                capture_output=True,
                text=True,
                timeout=15,
                env={**os.environ, "WINEDEBUG": "-all"},
            )
            if result.returncode == 0:
                arch_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
                if arch_line:
                    info.arch = arch_line.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        self._wine_version = info
        return info

    def is_wine_installed(self) -> bool:
        """Return ``True`` if Wine is available on the system."""
        return shutil.which("wine") is not None

    def is_winetricks_installed(self) -> bool:
        """Return ``True`` if winetricks is available on the system."""
        return shutil.which("winetricks") is not None

    # ------------------------------------------------------------------
    # Prefix lifecycle
    # ------------------------------------------------------------------

    def create_prefix(
        self,
        name: str,
        *,
        arch: str = "win64",
        initialize: bool = True,
    ) -> WinePrefixInfo:
        """Create a new Wine prefix.

        If a prefix with the given *name* already exists it is returned
        without modification.

        Args:
            name: Directory name for the prefix (e.g. ``"my-app"``).
            arch: Windows architecture: ``"win32"`` or ``"win64"``.
            initialize: If ``True`` (default), run ``wineboot --init``
                        to fully initialise the prefix.

        Returns:
            A :class:`WinePrefixInfo` describing the new prefix.

        Raises:
            RuntimeError: If Wine is not installed or initialisation
                          fails.
        """
        if not self.is_wine_installed():
            raise RuntimeError("Wine is not installed")

        prefix_path = self._prefix_base / name
        prefix_path.mkdir(parents=True, exist_ok=True)

        env = self._build_env(prefix_path, arch=arch)

        if initialize:
            logger.info("Initialising Wine prefix: %s (arch=%s)", name, arch)
            try:
                subprocess.run(
                    ["wineboot", "--init"],
                    env=env,
                    capture_output=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    f"Timed out initialising Wine prefix '{name}'"
                )
            except (FileNotFoundError, OSError) as exc:
                raise RuntimeError(
                    f"Failed to initialise Wine prefix '{name}': {exc}"
                )

        return self.get_prefix_info(name)

    def list_prefixes(self) -> List[WinePrefixInfo]:
        """Return information about every prefix under the base directory.

        Returns:
            A list of :class:`WinePrefixInfo` objects sorted
            alphabetically by name.
        """
        prefixes: List[WinePrefixInfo] = []

        if not self._prefix_base.exists():
            return prefixes

        try:
            for entry in sorted(self._prefix_base.iterdir()):
                if entry.is_dir():
                    prefixes.append(self._build_prefix_info(entry))
        except PermissionError:
            logger.warning(
                "Permission denied listing prefixes in %s",
                self._prefix_base,
            )

        return prefixes

    def get_prefix_info(self, name: str) -> WinePrefixInfo:
        """Return information about a single prefix.

        Args:
            name: Prefix directory name.

        Returns:
            A :class:`WinePrefixInfo` for the prefix.

        Raises:
            FileNotFoundError: If no prefix with the given name exists.
        """
        prefix_path = self._prefix_base / name
        if not prefix_path.exists():
            raise FileNotFoundError(f"Wine prefix not found: {name}")
        return self._build_prefix_info(prefix_path)

    def delete_prefix(self, name: str) -> bool:
        """Delete a Wine prefix and all of its contents.

        Args:
            name: Prefix directory name.

        Returns:
            ``True`` if the prefix was deleted, ``False`` if it did
            not exist.
        """
        prefix_path = self._prefix_base / name
        if not prefix_path.exists():
            logger.warning("Prefix '%s' does not exist, nothing to delete", name)
            return False

        # Safety: ensure the path is actually inside our base directory
        try:
            prefix_path.resolve().relative_to(self._prefix_base.resolve())
        except ValueError:
            logger.error(
                "Refusing to delete '%s': not inside prefix base '%s'",
                prefix_path,
                self._prefix_base,
            )
            return False

        logger.info("Deleting Wine prefix: %s", name)
        shutil.rmtree(prefix_path)
        return True

    def prefix_exists(self, name: str) -> bool:
        """Return ``True`` if a prefix with *name* exists."""
        return (self._prefix_base / name).is_dir()

    # ------------------------------------------------------------------
    # Dependency management (winetricks)
    # ------------------------------------------------------------------

    def install_dependencies(
        self,
        name: str,
        verbs: List[str],
        *,
        silent: bool = True,
    ) -> bool:
        """Install Windows dependencies into a prefix via winetricks.

        Args:
            name: Prefix directory name.
            verbs: List of winetricks verbs to install (e.g.
                   ``["vcrun2019", "d3dx9"]``).
            silent: If ``True``, run winetricks in unattended mode.

        Returns:
            ``True`` if winetricks completed successfully.

        Raises:
            FileNotFoundError: If the prefix does not exist.
            RuntimeError: If winetricks is not installed.
        """
        if not self.is_winetricks_installed():
            raise RuntimeError("winetricks is not installed")

        prefix_path = self._prefix_base / name
        if not prefix_path.exists():
            raise FileNotFoundError(f"Wine prefix not found: {name}")

        env = self._build_env(prefix_path)

        cmd: List[str] = ["winetricks"]
        if silent:
            cmd.append("-q")
        cmd.extend(verbs)

        logger.info(
            "Installing dependencies in prefix '%s': %s",
            name,
            ", ".join(verbs),
        )

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.error(
                    "winetricks failed (rc=%d): %s",
                    result.returncode,
                    result.stderr[:500] if result.stderr else "(no stderr)",
                )
                return False
            logger.info("Dependencies installed successfully in '%s'", name)
            return True

        except subprocess.TimeoutExpired:
            logger.error("winetricks timed out installing dependencies")
            return False
        except (FileNotFoundError, OSError) as exc:
            logger.error("Failed to run winetricks: %s", exc)
            return False

    def list_available_verbs(self) -> Dict[str, List[str]]:
        """Return the built-in winetricks verb categories.

        This returns the curated set of commonly-needed verbs shipped
        with this module (see :data:`WINETRICKS_CATEGORIES`).  It does
        **not** query winetricks itself, so it works even when
        winetricks is not installed.

        Returns:
            A dict mapping category names to lists of verb strings.
        """
        return dict(WINETRICKS_CATEGORIES)

    # ------------------------------------------------------------------
    # Running executables
    # ------------------------------------------------------------------

    def run_executable(
        self,
        name: str,
        exe_path: str,
        *,
        args: Optional[List[str]] = None,
        arch: str = "win64",
        background: bool = True,
    ) -> bool:
        """Run a Windows executable inside a Wine prefix.

        Args:
            name: Prefix directory name.
            exe_path: Path to the ``.exe`` or ``.msi`` file.
            args: Additional arguments to pass to the executable.
            arch: Architecture override (``"win32"`` or ``"win64"``).
            background: If ``True``, launch the process detached.

        Returns:
            ``True`` if the process was started (background) or
            completed successfully (foreground).

        Raises:
            FileNotFoundError: If the prefix does not exist.
            RuntimeError: If Wine is not installed.
        """
        if not self.is_wine_installed():
            raise RuntimeError("Wine is not installed")

        prefix_path = self._prefix_base / name
        if not prefix_path.exists():
            raise FileNotFoundError(f"Wine prefix not found: {name}")

        env = self._build_env(prefix_path, arch=arch)

        # Build command
        if exe_path.lower().endswith(".msi"):
            cmd = ["wine", "msiexec", "/i", exe_path]
        else:
            cmd = ["wine", exe_path]

        if args:
            cmd.extend(args)

        logger.info(
            "Running executable in prefix '%s': %s",
            name,
            " ".join(cmd),
        )

        try:
            if background:
                subprocess.Popen(
                    cmd,
                    env=env,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            else:
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    timeout=3600,
                )
                return result.returncode == 0

        except (FileNotFoundError, OSError) as exc:
            logger.error("Failed to run executable: %s", exc)
            return False
        except subprocess.TimeoutExpired:
            logger.error("Executable timed out")
            return False

    # ------------------------------------------------------------------
    # Prefix configuration
    # ------------------------------------------------------------------

    def set_windows_version(self, name: str, version: str = "win10") -> bool:
        """Set the reported Windows version for a prefix.

        Uses ``winetricks`` to change the Windows version reported to
        applications running inside the prefix.

        Supported values include ``win7``, ``win8``, ``win10``,
        ``win11``, ``winxp``, ``win2k``, etc.

        Args:
            name: Prefix directory name.
            version: Windows version string (default ``"win10"``).

        Returns:
            ``True`` if the version was set successfully.
        """
        if not self.is_winetricks_installed():
            logger.error("winetricks is required to set Windows version")
            return False

        prefix_path = self._prefix_base / name
        if not prefix_path.exists():
            logger.error("Prefix '%s' does not exist", name)
            return False

        env = self._build_env(prefix_path)

        try:
            result = subprocess.run(
                ["winetricks", "-q", version],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                logger.info(
                    "Set Windows version to '%s' in prefix '%s'",
                    version,
                    name,
                )
                return True
            else:
                logger.error(
                    "Failed to set Windows version: %s",
                    result.stderr[:300] if result.stderr else "(no output)",
                )
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.error("Failed to set Windows version: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_env(
        self,
        prefix_path: Path,
        *,
        arch: str = "win64",
    ) -> Dict[str, str]:
        """Build an environment dict for running Wine commands.

        Args:
            prefix_path: Absolute path to the Wine prefix.
            arch: ``"win32"`` or ``"win64"``.

        Returns:
            A copy of ``os.environ`` with Wine-specific variables set.
        """
        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)
        env["WINEDEBUG"] = "-all"
        if arch == "win32":
            env["WINEARCH"] = "win32"
        else:
            env["WINEARCH"] = "win64"
        return env

    def _build_prefix_info(self, prefix_path: Path) -> WinePrefixInfo:
        """Build a :class:`WinePrefixInfo` from a directory on disk.

        Args:
            prefix_path: Path to the prefix directory.

        Returns:
            Populated :class:`WinePrefixInfo`.
        """
        name = prefix_path.name
        has_drive_c = (prefix_path / "drive_c").is_dir()

        # Detect architecture from system.reg if present
        arch = "win64"
        system_reg = prefix_path / "system.reg"
        if system_reg.exists():
            try:
                header = system_reg.read_text(errors="replace")[:1024]
                if "#arch=win32" in header:
                    arch = "win32"
            except OSError:
                pass

        # Get directory size (best-effort)
        size_bytes = self._dir_size(prefix_path)

        # Get creation time
        created: Optional[datetime] = None
        try:
            stat = prefix_path.stat()
            # Use birth time where available, fall back to mtime
            ctime = getattr(stat, "st_birthtime", None) or stat.st_mtime
            created = datetime.fromtimestamp(ctime)
        except OSError:
            pass

        return WinePrefixInfo(
            name=name,
            path=prefix_path,
            arch=arch,
            size_bytes=size_bytes,
            created=created,
            has_drive_c=has_drive_c,
        )

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Calculate total size of a directory tree in bytes.

        Returns -1 if the size cannot be determined.
        """
        try:
            total = 0
            for entry in path.rglob("*"):
                if entry.is_file():
                    try:
                        total += entry.stat().st_size
                    except OSError:
                        pass
            return total
        except (OSError, PermissionError):
            return -1
