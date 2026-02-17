#!/usr/bin/env python3
"""
NeuronOS File Migrator

Migrates user files from Windows/macOS installations to NeuronOS.
"""

from __future__ import annotations

import logging
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
        max_file_size: Optional[int] = None,
    ):
        self.source = source
        self.target = target
        self.categories = categories or list(FileCategory)
        self.max_file_size = max_file_size
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
        
        Handles both file and directory sources correctly.

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
                if source_path.is_file():
                    # Handle single file migration (e.g., .gitconfig)
                    self._copy_single_file(source_path, target_path, category)
                elif source_path.is_dir():
                    # Handle directory migration (e.g., .ssh, Documents)
                    target_path.mkdir(parents=True, exist_ok=True)
                    self._copy_directory(source_path, target_path)
                else:
                    logger.warning(f"Skipping {source_path}: not a file or directory")

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

            # Skip files exceeding max_file_size
            if self.max_file_size is not None:
                try:
                    if source.stat().st_size > self.max_file_size:
                        logger.debug(f"Skipping large file: {source.name} (exceeds {self.max_file_size} bytes)")
                        return
                except OSError:
                    pass

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

    def _copy_single_file(self, source: Path, target: Path, category: FileCategory):
        """
        Copy a single file (not a directory).
        
        Used for items like .gitconfig that are files, not directories.
        
        Args:
            source: Source file path
            target: Target file path
            category: File category for special handling
        """
        try:
            # Ensure target parent directory exists
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if target already exists
            if target.exists():
                if target.is_dir():
                    # Target is a directory but should be a file - error
                    error = f"Cannot overwrite directory with file: {target}"
                    logger.error(error)
                    self.progress.errors.append(error)
                    return
                    
                # Compare sizes - skip if same
                if source.stat().st_size == target.stat().st_size:
                    logger.info(f"Skipping {source.name}: already exists with same size")
                    self.progress.files_done += 1
                    self.progress.bytes_done += source.stat().st_size
                    self._notify_progress()
                    return
            
            # Copy the file
            self.progress.current_file = source.name
            shutil.copy2(source, target)
            
            # For SSH keys, set proper permissions
            if category == FileCategory.SSH_KEYS:
                self._set_ssh_permissions(target)
            
            # Update progress
            self.progress.files_done += 1
            self.progress.bytes_done += source.stat().st_size
            self._notify_progress()
            
            logger.info(f"Migrated file: {source} -> {target}")
            
        except PermissionError:
            error = f"Permission denied: {source}"
            logger.warning(error)
            self.progress.errors.append(error)
        except Exception as e:
            error = f"Error copying {source.name}: {e}"
            logger.warning(error)
            self.progress.errors.append(error)

    def _set_ssh_permissions(self, path: Path):
        """
        Set correct permissions for SSH files.
        
        - .ssh directory: 700
        - Private keys: 600
        - Public keys: 644
        """
        import stat
        
        if path.is_dir():
            # .ssh directory: 700 (rwx------)
            path.chmod(stat.S_IRWXU)
        else:
            name = path.name.lower()
            if name.endswith('.pub'):
                # Public keys: 644 (rw-r--r--)
                path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            else:
                # Private keys: 600 (rw-------)
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)


class WindowsMigrator(Migrator):
    """
    Migrator specialized for Windows installations.

    Handles Windows-specific paths and browser profiles.
    """

    # Phase 3: Browser directories to exclude (caches)
    BROWSER_CACHE_EXCLUDES = {
        "Cache", "Code Cache", "GPUCache", "ShaderCache",
        "CacheStorage", "Service Worker", "blob_storage",
    }

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

    # Phase 3: Enhanced browser profile migration
    def _migrate_browser_profile(
        self,
        source: Path,
        target: Path,
        exclude_caches: bool = True,
    ) -> bool:
        """
        Migrate browser profile excluding cache directories.

        Args:
            source: Source browser profile directory
            target: Target directory
            exclude_caches: Whether to skip cache directories

        Returns:
            True if migration successful
        """
        if not source.exists():
            return True  # Not an error

        target.mkdir(parents=True, exist_ok=True)

        for item in source.iterdir():
            # Skip cache directories
            if exclude_caches and item.name in self.BROWSER_CACHE_EXCLUDES:
                logger.debug(f"Skipping browser cache: {item.name}")
                continue

            # Skip very large files (likely cache)
            if item.is_file():
                try:
                    if item.stat().st_size > 100 * 1024 * 1024:  # 100MB
                        logger.info(f"Skipping large file: {item.name}")
                        continue
                except OSError:
                    continue

            target_item = target / item.name

            try:
                if item.is_file():
                    self._copy_file(item, target_item)
                elif item.is_dir():
                    self._migrate_browser_profile(item, target_item, exclude_caches)
            except Exception as e:
                self.progress.errors.append(f"Failed to copy {item}: {e}")

        return True


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


# Phase 3: Application Settings Migrator
class ApplicationSettingsMigrator:
    """
    Migrates application settings and configurations.
    
    Handles VSCode, Git, SSH, NPM, and other developer tool settings.
    """
    
    # Mapping of Windows app settings to Linux equivalents
    APP_MAPPINGS = {
        "vscode": {
            "windows": "AppData/Roaming/Code/User",
            "linux": ".config/Code/User",
            "files": ["settings.json", "keybindings.json", "snippets/*"],
        },
        "git": {
            "windows": ".gitconfig",
            "linux": ".gitconfig",
        },
        "ssh": {
            "windows": ".ssh",
            "linux": ".ssh",
            "permissions": {
                "id_*": 0o600,
                "id_*.pub": 0o644,
                "config": 0o600,
                "known_hosts": 0o644,
            },
        },
        "npm": {
            "windows": ".npmrc",
            "linux": ".npmrc",
        },
        "pip": {
            "windows": "pip/pip.ini",
            "linux": ".config/pip/pip.conf",
        },
    }
    
    def __init__(self):
        pass
    
    def migrate_app_settings(
        self,
        source_home: Path,
        target_home: Path,
        apps: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Migrate application settings.
        
        Args:
            source_home: Windows user home directory
            target_home: Linux home directory
            apps: List of apps to migrate (None = all)
            
        Returns:
            Dict of app_name -> success
        """
        results = {}
        apps_to_migrate = apps or list(self.APP_MAPPINGS.keys())
        
        for app_name in apps_to_migrate:
            if app_name not in self.APP_MAPPINGS:
                continue
            
            mapping = self.APP_MAPPINGS[app_name]
            source = source_home / mapping["windows"]
            target = target_home / mapping["linux"]
            
            if not source.exists():
                results[app_name] = True  # Not an error
                continue
            
            try:
                if source.is_file():
                    self._copy_with_permissions(source, target, mapping)
                else:
                    self._copy_dir_with_permissions(source, target, mapping)
                
                results[app_name] = True
                logger.info(f"Migrated {app_name} settings")
                
            except Exception as e:
                logger.error(f"Failed to migrate {app_name}: {e}")
                results[app_name] = False
        
        return results
    
    def _copy_with_permissions(self, source: Path, target: Path, mapping: dict):
        """Copy file with proper permissions."""
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        
        # Apply permissions if specified
        permissions = mapping.get("permissions", {})
        for pattern, mode in permissions.items():
            import fnmatch
            if fnmatch.fnmatch(target.name, pattern):
                target.chmod(mode)
                break
    
    def _copy_dir_with_permissions(self, source: Path, target: Path, mapping: dict):
        """Copy directory with proper permissions."""
        target.mkdir(parents=True, exist_ok=True)
        permissions = mapping.get("permissions", {})
        
        # Get specific files to copy if defined
        files_to_copy = mapping.get("files", None)
        
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            
            # Filter by files list if specified
            if files_to_copy:
                import fnmatch
                if not any(fnmatch.fnmatch(str(relative), f) for f in files_to_copy):
                    continue
            
            target_item = target / relative
            
            if item.is_dir():
                target_item.mkdir(parents=True, exist_ok=True)
            else:
                target_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target_item)
                
                # Apply permissions
                for pattern, mode in permissions.items():
                    import fnmatch
                    if fnmatch.fnmatch(item.name, pattern):
                        target_item.chmod(mode)
                        break


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
