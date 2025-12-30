#!/usr/bin/env python3
"""
NeuronOS File Migrator

Migrates user files from Windows/macOS installations to NeuronOS.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class FileCategory(Enum):
    """Categories of files to migrate."""
    DOCUMENTS = "documents"
    PICTURES = "pictures"
    MUSIC = "music"
    VIDEOS = "videos"
    DOWNLOADS = "downloads"
    DESKTOP = "desktop"
    BROWSER_CHROME = "browser_chrome"
    BROWSER_FIREFOX = "browser_firefox"
    BROWSER_EDGE = "browser_edge"
    SSH_KEYS = "ssh_keys"
    GIT_CONFIG = "git_config"


@dataclass
class MigrationSource:
    """Source for file migration."""
    path: Path
    user: str
    os_type: str  # "windows" or "macos"

    @property
    def documents_path(self) -> Path:
        if self.os_type == "windows":
            return self.path / "Documents"
        return self.path / "Documents"

    @property
    def pictures_path(self) -> Path:
        if self.os_type == "windows":
            return self.path / "Pictures"
        return self.path / "Pictures"

    @property
    def music_path(self) -> Path:
        if self.os_type == "windows":
            return self.path / "Music"
        return self.path / "Music"

    @property
    def videos_path(self) -> Path:
        if self.os_type == "windows":
            return self.path / "Videos"
        return self.path / "Movies"

    @property
    def downloads_path(self) -> Path:
        return self.path / "Downloads"

    @property
    def desktop_path(self) -> Path:
        return self.path / "Desktop"


@dataclass
class MigrationTarget:
    """Target for file migration."""
    path: Path = field(default_factory=lambda: Path.home())

    @property
    def documents_path(self) -> Path:
        return self.path / "Documents"

    @property
    def pictures_path(self) -> Path:
        return self.path / "Pictures"

    @property
    def music_path(self) -> Path:
        return self.path / "Music"

    @property
    def videos_path(self) -> Path:
        return self.path / "Videos"

    @property
    def downloads_path(self) -> Path:
        return self.path / "Downloads"

    @property
    def desktop_path(self) -> Path:
        return self.path / "Desktop"


@dataclass
class MigrationProgress:
    """Progress information for migration."""
    current_file: str = ""
    files_total: int = 0
    files_done: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    current_category: FileCategory = FileCategory.DOCUMENTS
    errors: List[str] = field(default_factory=list)

    @property
    def percent(self) -> float:
        if self.bytes_total == 0:
            return 0.0
        return (self.bytes_done / self.bytes_total) * 100


class Migrator:
    """
    Base class for file migration.

    Handles copying files from source to target with progress tracking.
    """

    # File extensions to skip (temp files, caches, etc.)
    SKIP_EXTENSIONS: Set[str] = {
        ".tmp", ".temp", ".bak", ".log", ".dmp",
        ".thumbs.db", ".ds_store",
    }

    # Directories to skip
    SKIP_DIRS: Set[str] = {
        "__pycache__", ".git", "node_modules", ".cache",
        "Cache", "CacheStorage", "Code Cache", "GPUCache",
        ".Trash", "Trash",
    }

    def __init__(
        self,
        source: MigrationSource,
        target: MigrationTarget,
        categories: Optional[List[FileCategory]] = None,
    ):
        self.source = source
        self.target = target
        self.categories = categories or list(FileCategory)
        self.progress = MigrationProgress()
        self._cancelled = False
        self._progress_callback: Optional[Callable[[MigrationProgress], None]] = None

    def set_progress_callback(self, callback: Callable[[MigrationProgress], None]):
        """Set callback for progress updates."""
        self._progress_callback = callback

    def cancel(self):
        """Cancel the migration."""
        self._cancelled = True

    def scan(self) -> MigrationProgress:
        """
        Scan source to calculate total size.

        Returns:
            Progress object with totals.
        """
        self.progress = MigrationProgress()

        for category in self.categories:
            source_path = self._get_source_path(category)
            if source_path and source_path.exists():
                self._scan_directory(source_path, category)

        return self.progress

    def migrate(self) -> bool:
        """
        Perform the migration.

        Returns:
            True if successful (may have non-fatal errors).
        """
        self._cancelled = False

        for category in self.categories:
            if self._cancelled:
                break

            self.progress.current_category = category
            source_path = self._get_source_path(category)
            target_path = self._get_target_path(category)

            if source_path and source_path.exists():
                target_path.mkdir(parents=True, exist_ok=True)
                self._copy_directory(source_path, target_path)

        return len(self.progress.errors) == 0

    def _get_source_path(self, category: FileCategory) -> Optional[Path]:
        """Get source path for a category."""
        mapping = {
            FileCategory.DOCUMENTS: self.source.documents_path,
            FileCategory.PICTURES: self.source.pictures_path,
            FileCategory.MUSIC: self.source.music_path,
            FileCategory.VIDEOS: self.source.videos_path,
            FileCategory.DOWNLOADS: self.source.downloads_path,
            FileCategory.DESKTOP: self.source.desktop_path,
        }
        return mapping.get(category)

    def _get_target_path(self, category: FileCategory) -> Optional[Path]:
        """Get target path for a category."""
        mapping = {
            FileCategory.DOCUMENTS: self.target.documents_path,
            FileCategory.PICTURES: self.target.pictures_path,
            FileCategory.MUSIC: self.target.music_path,
            FileCategory.VIDEOS: self.target.videos_path,
            FileCategory.DOWNLOADS: self.target.downloads_path,
            FileCategory.DESKTOP: self.target.desktop_path,
        }
        return mapping.get(category)

    def _scan_directory(self, path: Path, category: FileCategory):
        """Scan a directory and update totals."""
        try:
            for item in path.iterdir():
                if self._should_skip(item):
                    continue

                if item.is_file():
                    try:
                        self.progress.files_total += 1
                        self.progress.bytes_total += item.stat().st_size
                    except OSError:
                        pass
                elif item.is_dir():
                    self._scan_directory(item, category)
        except PermissionError:
            logger.warning(f"Permission denied scanning: {path}")
        except Exception as e:
            logger.warning(f"Error scanning {path}: {e}")

    def _copy_directory(self, source: Path, target: Path):
        """Copy a directory recursively."""
        try:
            for item in source.iterdir():
                if self._cancelled:
                    return

                if self._should_skip(item):
                    continue

                target_item = target / item.name

                if item.is_file():
                    self._copy_file(item, target_item)
                elif item.is_dir():
                    target_item.mkdir(exist_ok=True)
                    self._copy_directory(item, target_item)
        except PermissionError:
            error = f"Permission denied: {source}"
            logger.warning(error)
            self.progress.errors.append(error)
        except Exception as e:
            error = f"Error copying {source}: {e}"
            logger.warning(error)
            self.progress.errors.append(error)

    def _copy_file(self, source: Path, target: Path):
        """Copy a single file."""
        try:
            self.progress.current_file = source.name

            # Skip if target exists and is same size
            if target.exists():
                source_size = source.stat().st_size
                target_size = target.stat().st_size
                if source_size == target_size:
                    self.progress.files_done += 1
                    self.progress.bytes_done += source_size
                    self._notify_progress()
                    return

            # Copy the file
            shutil.copy2(source, target)

            # Update progress
            self.progress.files_done += 1
            self.progress.bytes_done += source.stat().st_size
            self._notify_progress()

        except PermissionError:
            error = f"Permission denied: {source}"
            logger.warning(error)
            self.progress.errors.append(error)
        except Exception as e:
            error = f"Error copying {source.name}: {e}"
            logger.warning(error)
            self.progress.errors.append(error)

    def _should_skip(self, path: Path) -> bool:
        """Check if a file/directory should be skipped."""
        name = path.name.lower()

        # Skip hidden files (except important ones)
        if name.startswith(".") and name not in {".ssh", ".gitconfig"}:
            return True

        # Skip by extension
        if path.suffix.lower() in self.SKIP_EXTENSIONS:
            return True

        # Skip by directory name
        if path.is_dir() and name in self.SKIP_DIRS:
            return True

        return False

    def _notify_progress(self):
        """Notify progress callback."""
        if self._progress_callback:
            self._progress_callback(self.progress)


class WindowsMigrator(Migrator):
    """
    Migrator specialized for Windows installations.

    Handles Windows-specific paths and browser profiles.
    """

    def _get_source_path(self, category: FileCategory) -> Optional[Path]:
        """Get Windows-specific source paths."""
        base = self.source.path

        # Standard paths
        standard = super()._get_source_path(category)
        if standard:
            return standard

        # Browser profiles
        if category == FileCategory.BROWSER_CHROME:
            return base / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
        elif category == FileCategory.BROWSER_FIREFOX:
            return base / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
        elif category == FileCategory.BROWSER_EDGE:
            return base / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"
        elif category == FileCategory.SSH_KEYS:
            return base / ".ssh"
        elif category == FileCategory.GIT_CONFIG:
            return base / ".gitconfig"

        return None

    def _get_target_path(self, category: FileCategory) -> Optional[Path]:
        """Get Linux target paths for Windows categories."""
        standard = super()._get_target_path(category)
        if standard:
            return standard

        home = self.target.path

        if category == FileCategory.BROWSER_CHROME:
            return home / ".config" / "google-chrome"
        elif category == FileCategory.BROWSER_FIREFOX:
            return home / ".mozilla" / "firefox"
        elif category == FileCategory.SSH_KEYS:
            return home / ".ssh"
        elif category == FileCategory.GIT_CONFIG:
            return home / ".gitconfig"

        return None


class MacOSMigrator(Migrator):
    """
    Migrator specialized for macOS installations.

    Handles macOS-specific paths and app data.
    """

    def _get_source_path(self, category: FileCategory) -> Optional[Path]:
        """Get macOS-specific source paths."""
        base = self.source.path

        # Videos is Movies on macOS
        if category == FileCategory.VIDEOS:
            return base / "Movies"

        # Standard paths
        standard = super()._get_source_path(category)
        if standard:
            return standard

        # Browser profiles
        if category == FileCategory.BROWSER_CHROME:
            return base / "Library" / "Application Support" / "Google" / "Chrome"
        elif category == FileCategory.BROWSER_FIREFOX:
            return base / "Library" / "Application Support" / "Firefox" / "Profiles"
        elif category == FileCategory.SSH_KEYS:
            return base / ".ssh"
        elif category == FileCategory.GIT_CONFIG:
            return base / ".gitconfig"

        return None

    def _get_target_path(self, category: FileCategory) -> Optional[Path]:
        """Get Linux target paths for macOS categories."""
        standard = super()._get_target_path(category)
        if standard:
            return standard

        home = self.target.path

        if category == FileCategory.BROWSER_CHROME:
            return home / ".config" / "google-chrome"
        elif category == FileCategory.BROWSER_FIREFOX:
            return home / ".mozilla" / "firefox"
        elif category == FileCategory.SSH_KEYS:
            return home / ".ssh"
        elif category == FileCategory.GIT_CONFIG:
            return home / ".gitconfig"

        return None


def create_migrator(
    source: MigrationSource,
    target: Optional[MigrationTarget] = None,
    categories: Optional[List[FileCategory]] = None,
) -> Migrator:
    """
    Factory function to create appropriate migrator.

    Args:
        source: Migration source information
        target: Migration target (defaults to home directory)
        categories: File categories to migrate

    Returns:
        Appropriate Migrator subclass instance.
    """
    if target is None:
        target = MigrationTarget()

    if source.os_type == "windows":
        return WindowsMigrator(source, target, categories)
    elif source.os_type == "macos":
        return MacOSMigrator(source, target, categories)
    else:
        return Migrator(source, target, categories)
