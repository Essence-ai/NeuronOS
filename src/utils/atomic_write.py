"""
Atomic file operations for NeuronOS.

Ensures file writes are atomic - either complete successfully or no change.
Uses write-to-temp-then-rename pattern for POSIX atomicity guarantees.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Union


def atomic_write_text(path: Union[str, Path], content: str, mode: int = 0o644) -> None:
    """
    Write text content to file atomically.

    Uses write-to-temp-then-rename pattern to ensure atomicity.
    On POSIX systems, rename() is atomic within the same filesystem.

    Args:
        path: Destination file path
        content: Text content to write
        mode: File permissions (default 0o644)
    """
    path = Path(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (same filesystem for atomic rename)
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )

    try:
        # Write content
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # Ensure written to disk

        # Set permissions before rename
        os.chmod(temp_path, mode)

        # Atomic rename
        os.replace(temp_path, path)

        # Sync parent directory (ensures rename is persisted)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            # O_DIRECTORY not available on all platforms
            pass

    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Union[str, Path],
    data: Any,
    indent: int = 2,
    mode: int = 0o644,
) -> None:
    """
    Write JSON data to file atomically.

    Args:
        path: Destination file path
        data: JSON-serializable data
        indent: JSON indentation (default 2)
        mode: File permissions (default 0o644)
    """
    content = json.dumps(data, indent=indent, ensure_ascii=False)
    atomic_write_text(path, content + '\n', mode)


def atomic_write_bytes(path: Union[str, Path], content: bytes, mode: int = 0o644) -> None:
    """
    Write binary content to file atomically.

    Args:
        path: Destination file path
        content: Binary content to write
        mode: File permissions (default 0o644)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )

    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(temp_path, mode)
        os.replace(temp_path, path)

        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            pass

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def safe_backup(path: Union[str, Path], backup_suffix: str = ".bak") -> Path:
    """
    Create a backup of a file before modifying.

    Args:
        path: File to backup
        backup_suffix: Suffix for backup file

    Returns:
        Path to backup file
    """
    path = Path(path)
    backup_path = path.with_suffix(path.suffix + backup_suffix)

    if path.exists():
        shutil.copy2(path, backup_path)

    return backup_path
