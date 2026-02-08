"""
Steam & Proton Detection - Standalone detection of Steam and Proton installations.

Provides comprehensive detection of Steam installations (native and
Flatpak), installed Proton versions, Steam library folders, and
installed games.  This module is designed to work without any GUI
dependencies and can be imported standalone.

This module complements installer.ProtonInstaller, which handles the
store-driven install/uninstall lifecycle.  The ProtonInstaller can
delegate to SteamDetector for discovery operations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Well-known paths where a native Steam installation may live.
_NATIVE_STEAM_PATHS: List[Path] = [
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".steam",
]

#: Well-known paths where a Flatpak Steam installation stores data.
_FLATPAK_STEAM_PATHS: List[Path] = [
    Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam",
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
]

#: Known binary paths for the Steam client.
_STEAM_BINARY_PATHS: List[Path] = [
    Path("/usr/bin/steam"),
    Path("/usr/bin/steam-runtime"),
    Path.home() / ".steam/steam.sh",
]

#: Flatpak application ID for Steam.
STEAM_FLATPAK_ID = "com.valvesoftware.Steam"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SteamInstallation:
    """Describes a detected Steam installation.

    Attributes:
        install_type: One of ``"native"``, ``"flatpak"``, or
                      ``"runtime"``.
        root_path: Absolute path to the Steam root directory.
        steamapps_path: Absolute path to the ``steamapps`` directory.
        binary_path: Path to the Steam binary/script, if found.
    """
    install_type: str
    root_path: Path
    steamapps_path: Path
    binary_path: Optional[Path] = None


@dataclass
class ProtonVersion:
    """Information about a single installed Proton version.

    Attributes:
        name: Directory name (e.g. ``"Proton 9.0-4"``).
        path: Absolute path to the Proton directory.
        proton_script: Path to the ``proton`` launch script, if present.
        is_experimental: Whether this is the Proton Experimental build.
        is_ge: Whether this is a GloriousEggroll (GE-Proton) build.
        version_tuple: A parsed ``(major, minor)`` tuple for sorting,
                       or ``(0, 0)`` if the version could not be parsed.
    """
    name: str
    path: Path
    proton_script: Optional[Path] = None
    is_experimental: bool = False
    is_ge: bool = False
    version_tuple: tuple = (0, 0)


@dataclass
class SteamGameInfo:
    """Basic information about an installed Steam game.

    Parsed from an ``appmanifest_<id>.acf`` file.

    Attributes:
        app_id: Steam application ID.
        name: Display name of the game.
        install_dir: Relative install directory name inside
                     ``steamapps/common/``.
        size_bytes: Size on disk in bytes (from manifest), or 0.
        state_flags: Steam internal state flags integer.
        library_path: Path to the ``steamapps`` directory that holds
                      this game.
    """
    app_id: int
    name: str
    install_dir: str = ""
    size_bytes: int = 0
    state_flags: int = 0
    library_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# VDF / ACF parsing helpers
# ---------------------------------------------------------------------------

def _parse_vdf_simple(text: str) -> Dict[str, Any]:
    """Parse a simplified subset of Valve Data Format (VDF/ACF) text.

    This handles the flat key-value structure used in
    ``libraryfolders.vdf`` and ``appmanifest_*.acf`` files.  Nested
    sections are returned as nested dicts.

    This is intentionally minimal; it does **not** attempt to handle
    the full VDF grammar (e.g. escape sequences or multi-line values).

    Args:
        text: Raw VDF/ACF text.

    Returns:
        A nested dictionary of parsed values.
    """
    result: Dict[str, Any] = {}
    stack: List[Dict[str, Any]] = [result]
    current_key: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("//"):
            continue

        if stripped == "{":
            # Open a new section under current_key
            if current_key is not None:
                new_section: Dict[str, Any] = {}
                stack[-1][current_key] = new_section
                stack.append(new_section)
                current_key = None
            continue

        if stripped == "}":
            if len(stack) > 1:
                stack.pop()
            continue

        # Match "key" "value" pairs
        match = re.match(r'"([^"]*)"(?:\s+"([^"]*)")?', stripped)
        if match:
            key = match.group(1)
            value = match.group(2)
            if value is not None:
                stack[-1][key] = value
            else:
                # Bare key -- the next line should be "{" or another value
                current_key = key

    return result


# ---------------------------------------------------------------------------
# SteamDetector
# ---------------------------------------------------------------------------

class SteamDetector:
    """Detect Steam installations, Proton versions, and installed games.

    Example::

        detector = SteamDetector()
        install = detector.detect_steam()
        if install:
            print(f"Steam found: {install.install_type} at {install.root_path}")
            for pv in detector.list_proton_versions():
                print(f"  Proton: {pv.name}")
    """

    def __init__(self) -> None:
        self._installation: Optional[SteamInstallation] = None
        self._library_folders: Optional[List[Path]] = None

    # ------------------------------------------------------------------
    # Steam installation detection
    # ------------------------------------------------------------------

    def detect_steam(self) -> Optional[SteamInstallation]:
        """Detect the primary Steam installation.

        Searches native paths first, then Flatpak paths.  The first
        valid installation found is returned and cached for subsequent
        calls.

        Returns:
            A :class:`SteamInstallation` if found, or ``None``.
        """
        if self._installation is not None:
            return self._installation

        # Try native installs first
        for steam_root in _NATIVE_STEAM_PATHS:
            install = self._probe_steam_root(steam_root, "native")
            if install:
                self._installation = install
                logger.info(
                    "Detected native Steam at %s", install.root_path,
                )
                return install

        # Try Flatpak installs
        for steam_root in _FLATPAK_STEAM_PATHS:
            install = self._probe_steam_root(steam_root, "flatpak")
            if install:
                self._installation = install
                logger.info(
                    "Detected Flatpak Steam at %s", install.root_path,
                )
                return install

        logger.info("No Steam installation detected")
        return None

    def is_steam_installed(self) -> bool:
        """Return ``True`` if any Steam installation was detected."""
        return self.detect_steam() is not None

    def get_steam_binary(self) -> Optional[Path]:
        """Return the path to a usable Steam binary/script.

        Checks well-known binary paths and the Flatpak wrapper.

        Returns:
            :class:`Path` to the binary, or ``None``.
        """
        for bin_path in _STEAM_BINARY_PATHS:
            if bin_path.exists():
                return bin_path

        # Check for Flatpak Steam command
        flatpak_bin = Path("/usr/bin/flatpak")
        if flatpak_bin.exists():
            try:
                import subprocess
                result = subprocess.run(
                    ["flatpak", "list", "--app", "--columns=application"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if STEAM_FLATPAK_ID in result.stdout:
                    return flatpak_bin  # Caller should invoke via flatpak run
            except Exception:
                pass

        return None

    # ------------------------------------------------------------------
    # Library folder detection
    # ------------------------------------------------------------------

    def get_library_folders(self) -> List[Path]:
        """Return all Steam library folders (steamapps directories).

        Parses ``libraryfolders.vdf`` from the primary Steam
        installation to discover additional library locations (e.g.
        on other drives).

        Returns:
            A list of :class:`Path` objects pointing to ``steamapps``
            directories.  The primary installation's ``steamapps``
            directory is always first if Steam is installed.
        """
        if self._library_folders is not None:
            return list(self._library_folders)

        folders: List[Path] = []

        install = self.detect_steam()
        if install is None:
            self._library_folders = folders
            return folders

        # The primary steamapps is always a library folder
        if install.steamapps_path.is_dir():
            folders.append(install.steamapps_path)

        # Parse libraryfolders.vdf for additional locations
        vdf_path = install.steamapps_path / "libraryfolders.vdf"
        if vdf_path.exists():
            try:
                text = vdf_path.read_text(errors="replace")
                data = _parse_vdf_simple(text)

                # The VDF has a top-level "libraryfolders" section
                lib_data = data.get("libraryfolders", data)

                for key, value in lib_data.items():
                    if not isinstance(value, dict):
                        continue
                    folder_path_str = value.get("path")
                    if folder_path_str:
                        steamapps = Path(folder_path_str) / "steamapps"
                        if steamapps.is_dir() and steamapps not in folders:
                            folders.append(steamapps)
                            logger.debug(
                                "Found Steam library folder: %s", steamapps,
                            )

            except OSError as exc:
                logger.warning(
                    "Failed to read libraryfolders.vdf: %s", exc,
                )

        self._library_folders = folders
        return list(folders)

    # ------------------------------------------------------------------
    # Proton version detection
    # ------------------------------------------------------------------

    def list_proton_versions(self) -> List[ProtonVersion]:
        """List all installed Proton versions across all library folders.

        Scans every ``steamapps/common/`` directory for directories
        whose name starts with ``Proton`` or ``GE-Proton``.

        Returns:
            A list of :class:`ProtonVersion` objects sorted from newest
            to oldest.
        """
        versions: List[ProtonVersion] = []
        seen_paths: set = set()

        for lib_folder in self.get_library_folders():
            common_dir = lib_folder / "common"
            if not common_dir.is_dir():
                continue

            try:
                for entry in common_dir.iterdir():
                    if not entry.is_dir():
                        continue
                    if entry in seen_paths:
                        continue

                    name = entry.name
                    if not (
                        name.startswith("Proton")
                        or name.startswith("GE-Proton")
                    ):
                        continue

                    seen_paths.add(entry)

                    proton_script = entry / "proton"
                    pv = ProtonVersion(
                        name=name,
                        path=entry,
                        proton_script=proton_script if proton_script.exists() else None,
                        is_experimental="Experimental" in name,
                        is_ge=name.startswith("GE-Proton"),
                        version_tuple=self._parse_proton_version(name),
                    )
                    versions.append(pv)

            except PermissionError:
                logger.warning(
                    "Permission denied scanning %s", common_dir,
                )

        # Sort: highest version first, experimental and GE after stable
        versions.sort(
            key=lambda v: (
                not v.is_experimental and not v.is_ge,  # stable first
                v.version_tuple,
            ),
            reverse=True,
        )
        return versions

    def get_recommended_proton(self) -> Optional[ProtonVersion]:
        """Return the recommended Proton version to use.

        Selection priority:
        1. Newest stable Proton (e.g. Proton 9.x over 8.x).
        2. Proton Experimental.
        3. Newest GE-Proton build.
        4. Any available version.

        Returns:
            A :class:`ProtonVersion`, or ``None`` if no Proton is
            installed.
        """
        versions = self.list_proton_versions()
        if not versions:
            return None

        # Prefer stable versions (not experimental, not GE)
        stable = [v for v in versions if not v.is_experimental and not v.is_ge]
        if stable:
            return stable[0]  # Already sorted newest-first

        # Then experimental
        experimental = [v for v in versions if v.is_experimental]
        if experimental:
            return experimental[0]

        # Then GE
        ge = [v for v in versions if v.is_ge]
        if ge:
            return ge[0]

        # Fallback
        return versions[0]

    # ------------------------------------------------------------------
    # Game detection
    # ------------------------------------------------------------------

    def is_game_installed(self, app_id: int) -> bool:
        """Check whether a Steam game is installed by its app ID.

        Searches all library folders for an ``appmanifest_<id>.acf``
        file.

        Args:
            app_id: Steam application ID.

        Returns:
            ``True`` if the game's manifest file exists.
        """
        for lib_folder in self.get_library_folders():
            manifest = lib_folder / f"appmanifest_{app_id}.acf"
            if manifest.exists():
                return True
        return False

    def get_game_info(self, app_id: int) -> Optional[SteamGameInfo]:
        """Return information about an installed Steam game.

        Args:
            app_id: Steam application ID.

        Returns:
            A :class:`SteamGameInfo` if the game is installed, else
            ``None``.
        """
        for lib_folder in self.get_library_folders():
            manifest = lib_folder / f"appmanifest_{app_id}.acf"
            if not manifest.exists():
                continue

            try:
                text = manifest.read_text(errors="replace")
                data = _parse_vdf_simple(text)
                app_state = data.get("AppState", data)

                return SteamGameInfo(
                    app_id=int(app_state.get("appid", app_id)),
                    name=app_state.get("name", f"App {app_id}"),
                    install_dir=app_state.get("installdir", ""),
                    size_bytes=int(app_state.get("SizeOnDisk", 0)),
                    state_flags=int(app_state.get("StateFlags", 0)),
                    library_path=lib_folder,
                )
            except (OSError, ValueError, KeyError) as exc:
                logger.warning(
                    "Failed to parse manifest for app %d: %s", app_id, exc,
                )

        return None

    def list_installed_games(self) -> List[SteamGameInfo]:
        """Return information about all installed Steam games.

        Scans every library folder for ``appmanifest_*.acf`` files and
        parses each one.

        Returns:
            A list of :class:`SteamGameInfo` objects sorted by name.
        """
        games: List[SteamGameInfo] = []

        for lib_folder in self.get_library_folders():
            try:
                for manifest in lib_folder.glob("appmanifest_*.acf"):
                    # Extract app_id from filename
                    match = re.match(r"appmanifest_(\d+)\.acf", manifest.name)
                    if not match:
                        continue

                    app_id = int(match.group(1))
                    info = self.get_game_info(app_id)
                    if info:
                        games.append(info)

            except PermissionError:
                logger.warning(
                    "Permission denied scanning %s", lib_folder,
                )

        games.sort(key=lambda g: g.name.lower())
        return games

    def get_game_install_path(self, app_id: int) -> Optional[Path]:
        """Return the absolute install path for a Steam game.

        Args:
            app_id: Steam application ID.

        Returns:
            Path to the game's install directory, or ``None`` if not
            installed or the directory does not exist.
        """
        info = self.get_game_info(app_id)
        if info is None or not info.install_dir or info.library_path is None:
            return None

        game_path = info.library_path / "common" / info.install_dir
        if game_path.is_dir():
            return game_path

        return None

    # ------------------------------------------------------------------
    # Compatibility data path
    # ------------------------------------------------------------------

    def get_compat_data_path(self, app_id: int) -> Optional[Path]:
        """Return the Proton compatibility data (prefix) path for a game.

        Each game that runs under Proton has a Wine prefix stored in
        ``steamapps/compatdata/<app_id>/``.

        Args:
            app_id: Steam application ID.

        Returns:
            Path to the compatdata directory if it exists, else
            ``None``.
        """
        for lib_folder in self.get_library_folders():
            compat_path = lib_folder / "compatdata" / str(app_id)
            if compat_path.is_dir():
                return compat_path
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _probe_steam_root(
        self,
        root: Path,
        install_type: str,
    ) -> Optional[SteamInstallation]:
        """Check whether *root* is a valid Steam installation.

        A directory is considered a valid Steam root if it contains a
        ``steamapps`` subdirectory.

        Args:
            root: Candidate root path.
            install_type: Label for the installation type.

        Returns:
            :class:`SteamInstallation` if valid, else ``None``.
        """
        if not root.is_dir():
            return None

        steamapps = root / "steamapps"
        # Some installs use SteamApps (case-sensitive filesystems)
        if not steamapps.is_dir():
            steamapps = root / "SteamApps"
        if not steamapps.is_dir():
            return None

        # Find binary
        binary: Optional[Path] = None
        for bin_path in _STEAM_BINARY_PATHS:
            if bin_path.exists():
                binary = bin_path
                break

        return SteamInstallation(
            install_type=install_type,
            root_path=root,
            steamapps_path=steamapps,
            binary_path=binary,
        )

    @staticmethod
    def _parse_proton_version(name: str) -> tuple:
        """Parse a Proton directory name into a sortable version tuple.

        Examples::

            "Proton 9.0-4"       -> (9, 0)
            "Proton 8.0"         -> (8, 0)
            "Proton Experimental"-> (0, 0)
            "GE-Proton9-7"       -> (9, 7)

        Args:
            name: Proton directory name.

        Returns:
            A ``(major, minor)`` tuple.
        """
        # Try "Proton X.Y" or "Proton X.Y-Z"
        match = re.search(r"Proton\s+(\d+)\.(\d+)", name)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        # Try "GE-ProtonX-Y"
        match = re.search(r"GE-Proton(\d+)-(\d+)", name)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        # Try "GE-ProtonX" (no minor)
        match = re.search(r"GE-Proton(\d+)", name)
        if match:
            return (int(match.group(1)), 0)

        return (0, 0)
