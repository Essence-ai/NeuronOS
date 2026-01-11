# Phase 1: Critical Security & Data Loss Fixes

**Priority:** HIGHEST - Must complete before any other work
**Estimated Time:** 1-2 weeks
**Prerequisites:** None

---

## Table of Contents

1. [Overview](#overview)
2. [SEC-001: Command Injection in VM Manager](#sec-001-command-injection-in-vm-manager)
3. [SEC-002: Unsanitized File Paths](#sec-002-unsanitized-file-paths)
4. [SEC-003: Unsafe Download Without Verification](#sec-003-unsafe-download-without-verification)
5. [DATA-001: Migration File/Directory Confusion](#data-001-migration-filedirectory-confusion)
6. [DATA-002: Non-Atomic Configuration Writes](#data-002-non-atomic-configuration-writes)
7. [SYS-001: Hardcoded GRUB/System Paths](#sys-001-hardcoded-grubsystem-paths)
8. [SYS-002: Missing Sudo for System Operations](#sys-002-missing-sudo-for-system-operations)
9. [Verification Checklist](#verification-checklist)

---

## Overview

This phase addresses **critical vulnerabilities** that could result in:

- Remote Code Execution (RCE)
- Data Loss
- System Unbootable
- Privilege Escalation

**DO NOT proceed to other phases until all items here are complete and tested.**

---

## SEC-001: Command Injection in VM Manager

### Location

`src/vm_manager/gui/app.py:218`

### Current Code (VULNERABLE)

```python
def _on_open_clicked(self, button):
    # Open Looking Glass or virt-viewer
    if self.vm_info.has_looking_glass:
        lg_manager = get_looking_glass_manager()
        lg_manager.start(self.vm_info.name)
    else:
        os.system(f"virt-viewer -c qemu:///system {self.vm_info.name} &")
```

### Why This Is Critical

An attacker who can control the VM name (e.g., via a crafted libvirt config or API) can execute arbitrary shell commands:

```
VM Name: "test; rm -rf / #"
Executed: virt-viewer -c qemu:///system test; rm -rf / # &
```

### Fixed Code

```python
import subprocess
import shlex
import re

# Add at module level
VM_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,63}$')

def _validate_vm_name(name: str) -> bool:
    """Validate VM name follows libvirt naming rules."""
    if not name or len(name) > 64:
        return False
    return bool(VM_NAME_PATTERN.match(name))

def _on_open_clicked(self, button):
    """Open VM display safely."""
    if self.vm_info.has_looking_glass:
        lg_manager = get_looking_glass_manager()
        lg_manager.start(self.vm_info.name)
    else:
        # SECURITY: Validate VM name before shell execution
        if not _validate_vm_name(self.vm_info.name):
            logger.error(f"Invalid VM name rejected: {self.vm_info.name!r}")
            return

        # SECURITY: Use subprocess with list args instead of shell
        try:
            subprocess.Popen(
                ["virt-viewer", "-c", "qemu:///system", self.vm_info.name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("virt-viewer not installed")
        except Exception as e:
            logger.error(f"Failed to launch virt-viewer: {e}")
```

### Testing

1. Create a VM with a normal name - should work
2. Try to create a VM with name `test; echo pwned` - should be rejected
3. Try to create a VM with name `$(whoami)` - should be rejected

### Additional Hardening

Search for and fix all other `os.system()` calls in the codebase:

```bash
grep -rn "os.system" src/
```

Replace ALL instances with `subprocess.run()` or `subprocess.Popen()` with list arguments.

---

## SEC-002: Unsanitized File Paths

### Locations

- `src/store/installer.py:265-300` (Wine installer download)
- `src/migration/migrator.py:258-264` (file copy target)

### Current Code (VULNERABLE)

```python
# installer.py - Wine download
installer_name = Path(installer_url).name or "installer.exe"
download_path = prefix_path / installer_name
# No validation that installer_name doesn't contain path traversal
```

### Why This Is Critical

Path traversal can write files outside intended directory:

```
URL: https://evil.com/foo/../../../etc/cron.d/backdoor
installer_name = "../../../etc/cron.d/backdoor"
download_path = ~/.local/share/neuron-os/wine-prefixes/app/../../../etc/cron.d/backdoor
```

### Fixed Code

```python
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, unquote

def _safe_filename(url: str, default: str = "download") -> str:
    """
    Extract safe filename from URL.

    Prevents path traversal attacks by:
    1. Extracting only the filename component
    2. Removing any path separators
    3. Validating the result
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

        # Limit length
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


# In WineInstaller.install():
installer_name = _safe_filename(installer_url, "installer.exe")
if not installer_name.lower().endswith(('.exe', '.msi')):
    installer_name += ".exe"

download_path = _ensure_within_directory(
    prefix_path,
    prefix_path / installer_name
)
```

### Testing

1. Test with normal URL: `https://example.com/installer.exe`
2. Test with traversal: `https://example.com/../../../etc/passwd` - should use `passwd` or default
3. Test with encoded traversal: `https://example.com/%2e%2e%2fetc%2fpasswd`

---

## SEC-003: Unsafe Download Without Verification

### Location

`src/store/installer.py:271-300`

### Current Code (VULNERABLE)

```python
response = requests.get(installer_url, stream=True)
response.raise_for_status()
# Downloads and executes without any verification
with open(download_path, 'wb') as f:
    f.write(response.content)
subprocess.Popen(["wine", str(download_path)], ...)
```

### Why This Is Critical

- No checksum verification = MITM attacks can replace installer
- No signature verification = cannot verify authentic source
- Immediate execution = malware runs before user can inspect

### Fixed Code

```python
import hashlib
from typing import Optional
from dataclasses import dataclass

@dataclass
class DownloadSpec:
    """Specification for verified download."""
    url: str
    sha256: Optional[str] = None  # Expected SHA256 hash
    size: Optional[int] = None     # Expected file size in bytes


def _verify_download(file_path: Path, spec: DownloadSpec) -> bool:
    """Verify downloaded file matches expected hash and size."""
    if not file_path.exists():
        return False

    # Check size if specified
    if spec.size is not None:
        actual_size = file_path.stat().st_size
        if actual_size != spec.size:
            logger.error(f"Size mismatch: expected {spec.size}, got {actual_size}")
            return False

    # Check hash if specified
    if spec.sha256 is not None:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        actual_hash = sha256_hash.hexdigest().lower()
        expected_hash = spec.sha256.lower()

        if actual_hash != expected_hash:
            logger.error(f"Hash mismatch: expected {expected_hash}, got {actual_hash}")
            return False

    return True


def _secure_download(
    url: str,
    dest: Path,
    spec: Optional[DownloadSpec] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """
    Download file securely with verification.

    Args:
        url: URL to download from
        dest: Destination path
        spec: Optional verification specification
        progress_callback: Optional callback(downloaded_bytes, total_bytes)

    Returns:
        True if download and verification successful
    """
    import requests

    # Download to temporary file first
    temp_path = dest.with_suffix(dest.suffix + ".tmp")

    try:
        # Require HTTPS
        if not url.startswith("https://"):
            logger.warning(f"Insecure URL (not HTTPS): {url}")
            # Could reject entirely, or just warn

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        # Verify size matches expectation if specified
        if spec and spec.size and total_size and total_size != spec.size:
            logger.error(f"Content-Length mismatch: expected {spec.size}, got {total_size}")
            return False

        downloaded = 0
        sha256_hash = hashlib.sha256()

        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256_hash.update(chunk)
                downloaded += len(chunk)

                if progress_callback and total_size:
                    progress_callback(downloaded, total_size)

        # Verify hash
        if spec and spec.sha256:
            actual_hash = sha256_hash.hexdigest().lower()
            if actual_hash != spec.sha256.lower():
                logger.error(f"Hash mismatch: expected {spec.sha256}, got {actual_hash}")
                temp_path.unlink()
                return False

        # Move to final destination
        temp_path.rename(dest)
        return True

    except requests.RequestException as e:
        logger.error(f"Download failed: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False
```

### Data Model Update

Update `AppInfo` in `app_catalog.py` to include verification data:

```python
@dataclass
class AppInfo:
    # ... existing fields ...
    installer_sha256: Optional[str] = None  # SHA256 of installer
    installer_size: Optional[int] = None     # Size in bytes
```

### apps.json Update Example

```json
{
  "id": "7zip",
  "name": "7-Zip",
  "installer_url": "https://www.7-zip.org/a/7z2301-x64.exe",
  "installer_sha256": "a638b3a9c9f8c4c36b52a...",
  "installer_size": 1572864
}
```

---

## DATA-001: Migration File/Directory Confusion

### Location

`src/migration/migrator.py:353-378` (WindowsMigrator and MacOSMigrator)

### Current Code (BUG)

```python
# For SSH_KEYS category
elif category == FileCategory.SSH_KEYS:
    return base / ".ssh"  # This returns the directory

# For GIT_CONFIG category
elif category == FileCategory.GIT_CONFIG:
    return base / ".gitconfig"  # This returns a file

# In _get_target_path:
elif category == FileCategory.SSH_KEYS:
    return home / ".ssh"
elif category == FileCategory.GIT_CONFIG:
    return home / ".gitconfig"

# But the copy logic in _copy_directory expects directories:
def _copy_directory(self, source: Path, target: Path):
    for item in source.iterdir():  # FAILS if source is a file!
```

### Why This Causes Data Loss

When migrating `.gitconfig` (a file), the code:

1. Gets source path: `/mnt/windows/Users/John/.gitconfig` (file)
2. Creates target as directory: `~/.gitconfig/` (mkdir)
3. Tries to iterate file contents: `source.iterdir()` FAILS
4. SSH keys may be partially copied or lost

### Fixed Code

```python
def migrate(self) -> bool:
    """
    Perform the migration.

    Handles both file and directory sources correctly.
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


def _copy_single_file(self, source: Path, target: Path, category: FileCategory):
    """
    Copy a single file (not a directory).

    Used for items like .gitconfig that are files, not directories.
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
    """Set correct permissions for SSH files."""
    import stat

    if path.is_dir():
        # .ssh directory: 700
        path.chmod(stat.S_IRWXU)
    else:
        name = path.name.lower()
        if name.endswith('.pub'):
            # Public keys: 644
            path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        else:
            # Private keys: 600
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
```

### Also Update `_scan_directory`:

```python
def _scan_directory(self, path: Path, category: FileCategory):
    """Scan a path and update totals."""
    try:
        if path.is_file():
            # Single file
            self.progress.files_total += 1
            self.progress.bytes_total += path.stat().st_size
        elif path.is_dir():
            # Directory - recurse
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
```

### Testing

1. Create test Windows partition with:
   - `.gitconfig` file
   - `.ssh/` directory with `id_rsa`, `id_rsa.pub`, `config`
2. Run migration
3. Verify:
   - `~/.gitconfig` is a file (not directory)
   - `~/.ssh/` is a directory with correct permissions
   - `~/.ssh/id_rsa` has mode 600
   - `~/.ssh/id_rsa.pub` has mode 644

---

## DATA-002: Non-Atomic Configuration Writes

### Locations

- `src/store/installer.py:383-384` (VM app config)
- `src/updater/rollback.py:175-176` (GRUB config)
- `src/hardware_detect/config_generator.py` (modprobe config)

### Current Code (VULNERABLE)

```python
with open(config_dir / f"{app.id}.json", 'w') as f:
    json.dump(app_config, f, indent=2)
```

### Why This Is Critical

If the system crashes or loses power during write:

1. File is truncated (partial write)
2. JSON is corrupted
3. Config is lost or invalid

### Fixed Code - Utility Module

Create `src/utils/atomic_write.py`:

```python
"""
Atomic file operations for NeuronOS.

Ensures file writes are atomic - either complete or no change.
"""

import os
import tempfile
import json
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
        os.rename(temp_path, path)

        # Sync parent directory (ensures rename is persisted)
        dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

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
        os.rename(temp_path, path)

        dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

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
        import shutil
        shutil.copy2(path, backup_path)

    return backup_path
```

### Usage in Codebase

Replace all direct file writes with atomic versions:

```python
# Before
with open(config_path, 'w') as f:
    json.dump(config, f)

# After
from utils.atomic_write import atomic_write_json
atomic_write_json(config_path, config)
```

---

## SYS-001: Hardcoded GRUB/System Paths

### Location

`src/updater/rollback.py:159-167`

### Current Code (BROKEN)

```python
grub_entry = """
menuentry 'NeuronOS Recovery (Timeshift)' ... {
    ...
    set root='hd0,gpt2'           # HARDCODED - wrong on most systems!
    linux /boot/vmlinuz-linux root=/dev/sda2 rw init=/bin/bash  # HARDCODED!
}
"""
```

### Why This Is Critical

- `hd0,gpt2` assumes first disk, second partition - often wrong
- `/dev/sda2` assumes specific block device - wrong on NVMe (`/dev/nvme0n1p2`)
- System won't boot into recovery on any non-matching hardware

### Fixed Code

```python
import subprocess
import re
from pathlib import Path
from typing import Optional, Tuple


def _detect_root_device() -> Tuple[Optional[str], Optional[str]]:
    """
    Detect current root device and GRUB device notation.

    Returns:
        Tuple of (linux_device, grub_device) e.g. ("/dev/nvme0n1p2", "hd0,gpt2")
        Returns (None, None) if detection fails.
    """
    # Get root mount point
    try:
        result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None, None

        root_device = result.stdout.strip()

        # Handle btrfs subvolumes
        if "[" in root_device:
            root_device = root_device.split("[")[0]

    except Exception:
        return None, None

    # Convert to GRUB notation
    grub_device = _linux_to_grub_device(root_device)

    return root_device, grub_device


def _linux_to_grub_device(linux_device: str) -> Optional[str]:
    """
    Convert Linux device path to GRUB device notation.

    Examples:
        /dev/sda2 -> hd0,gpt2 or hd0,msdos2
        /dev/nvme0n1p2 -> hd0,gpt2
        /dev/vda3 -> hd0,gpt3
    """
    # Match different device patterns
    patterns = [
        # NVMe: /dev/nvme0n1p2
        (r'/dev/nvme(\d+)n(\d+)p(\d+)', lambda m: f"hd{int(m.group(1)) * 10 + int(m.group(2))},gpt{m.group(3)}"),
        # SATA/SCSI: /dev/sda2
        (r'/dev/sd([a-z])(\d+)', lambda m: f"hd{ord(m.group(1)) - ord('a')},gpt{m.group(2)}"),
        # VirtIO: /dev/vda2
        (r'/dev/vd([a-z])(\d+)', lambda m: f"hd{ord(m.group(1)) - ord('a')},gpt{m.group(2)}"),
    ]

    for pattern, converter in patterns:
        match = re.match(pattern, linux_device)
        if match:
            return converter(match)

    return None


def _detect_partition_table_type(device: str) -> str:
    """Detect if device uses GPT or MBR."""
    try:
        # Get disk (remove partition number)
        disk = re.sub(r'p?\d+$', '', device)

        result = subprocess.run(
            ["blkid", "-o", "value", "-s", "PTTYPE", disk],
            capture_output=True,
            text=True,
            timeout=5,
        )

        pttype = result.stdout.strip().lower()
        if pttype == "gpt":
            return "gpt"
        elif pttype in ("dos", "msdos"):
            return "msdos"
    except Exception:
        pass

    return "gpt"  # Default to GPT for modern systems


def create_recovery_entry(self) -> bool:
    """
    Create a GRUB entry for easy rollback at boot.

    Dynamically detects system configuration.
    """
    # Detect root device
    root_device, grub_device = _detect_root_device()

    if not root_device or not grub_device:
        logger.error("Could not detect root device for recovery entry")
        return False

    # Detect partition table type
    pttype = _detect_partition_table_type(root_device)
    grub_device = grub_device.replace("gpt", pttype)

    # Find kernel
    kernel_path = self._find_kernel()
    if not kernel_path:
        logger.error("Could not find kernel for recovery entry")
        return False

    grub_entry = f"""
menuentry 'NeuronOS Recovery (Timeshift)' --class recovery --class gnu-linux --class gnu --class os {{
    insmod gzio
    insmod part_{pttype}
    insmod btrfs
    set root='{grub_device}'
    linux {kernel_path} root={root_device} rw init=/bin/bash
}}
"""
    recovery_path = Path("/etc/grub.d/45_neuronos_recovery")

    try:
        script = f"""#!/bin/sh
exec tail -n +3 $0
{grub_entry}
"""
        # Use atomic write
        from utils.atomic_write import atomic_write_text
        atomic_write_text(recovery_path, script, mode=0o755)

        # Regenerate GRUB config
        result = subprocess.run(
            ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error(f"grub-mkconfig failed: {result.stderr}")
            return False

        logger.info(f"Recovery GRUB entry created (root={root_device})")
        return True

    except Exception as e:
        logger.error(f"Failed to create recovery entry: {e}")
        return False


def _find_kernel(self) -> Optional[str]:
    """Find the kernel path for GRUB."""
    kernel_paths = [
        "/boot/vmlinuz-linux",
        "/boot/vmlinuz-linux-lts",
        "/boot/vmlinuz",
    ]

    for path in kernel_paths:
        if Path(path).exists():
            return path

    # Try to find any vmlinuz
    boot = Path("/boot")
    for kernel in boot.glob("vmlinuz*"):
        return str(kernel)

    return None
```

---

## SYS-002: Missing Sudo for System Operations

### Locations

- `src/updater/rollback.py:175, 244-249`
- `src/hardware_detect/config_generator.py` (system file writes)

### Current Code (BROKEN)

```python
with open("/etc/systemd/system/neuron-boot-verify.service", "w") as f:
    f.write(service_content)
# FAILS with PermissionError unless running as root
```

### Fixed Code

```python
import subprocess
from typing import Union
from pathlib import Path


def _write_system_file(path: Union[str, Path], content: str, mode: int = 0o644) -> bool:
    """
    Write to a system file, using sudo if necessary.

    Args:
        path: System file path
        content: Content to write
        mode: File permissions

    Returns:
        True if successful
    """
    path = Path(path)

    # Try direct write first (works if already root)
    try:
        from utils.atomic_write import atomic_write_text
        atomic_write_text(path, content, mode)
        return True
    except PermissionError:
        pass

    # Fall back to sudo
    try:
        # Write to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as f:
            f.write(content)
            temp_path = f.name

        # Move with sudo
        result = subprocess.run(
            ["sudo", "mv", temp_path, str(path)],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"sudo mv failed: {result.stderr.decode()}")
            return False

        # Set permissions
        result = subprocess.run(
            ["sudo", "chmod", oct(mode)[2:], str(path)],
            capture_output=True,
            timeout=10,
        )

        return result.returncode == 0

    except Exception as e:
        logger.error(f"Failed to write system file {path}: {e}")
        return False


def _run_system_command(cmd: list, check: bool = True, timeout: int = 60) -> bool:
    """
    Run a system command, adding sudo if necessary.

    Args:
        cmd: Command and arguments
        check: Whether to check return code
        timeout: Command timeout in seconds

    Returns:
        True if successful
    """
    try:
        # Try without sudo first
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode == 0:
            return True
    except PermissionError:
        pass
    except subprocess.SubprocessError:
        pass

    # Try with sudo
    try:
        result = subprocess.run(
            ["sudo"] + cmd,
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Command failed: {' '.join(cmd)}: {e}")
        return False
```

### Usage in rollback.py:

```python
def schedule_rollback_on_boot_failure(self) -> bool:
    """Configure automatic rollback if system fails to boot."""

    service_content = """[Unit]
Description=NeuronOS Boot Verification
After=graphical.target
...
"""

    verify_script = """#!/bin/bash
# NeuronOS Boot Verification
...
"""

    try:
        # Write service file
        if not _write_system_file(
            "/etc/systemd/system/neuron-boot-verify.service",
            service_content,
            mode=0o644,
        ):
            return False

        # Write verification script
        if not _write_system_file(
            "/usr/bin/neuron-boot-verify",
            verify_script,
            mode=0o755,
        ):
            return False

        # Enable service
        if not _run_system_command(["systemctl", "daemon-reload"]):
            return False
        if not _run_system_command(["systemctl", "enable", "neuron-boot-verify.service"]):
            return False

        logger.info("Boot verification configured")
        return True

    except Exception as e:
        logger.error(f"Failed to configure boot verification: {e}")
        return False
```

---

## Verification Checklist

### Before Marking Phase 1 Complete

- [ ] **SEC-001**: No `os.system()` calls remain in codebase
- [ ] **SEC-001**: All subprocess calls use list arguments
- [ ] **SEC-001**: VM name validation implemented and tested
- [ ] **SEC-002**: Path traversal tests pass
- [ ] **SEC-002**: `_safe_filename()` handles all edge cases
- [ ] **SEC-003**: Downloads verify checksums when available
- [ ] **SEC-003**: HTTPS required or warned
- [ ] **DATA-001**: Migration handles files and directories correctly
- [ ] **DATA-001**: SSH key permissions set correctly (600/644)
- [ ] **DATA-001**: `.gitconfig` migrated as file, not directory
- [ ] **DATA-002**: All config writes use atomic operations
- [ ] **SYS-001**: GRUB paths detected dynamically
- [ ] **SYS-001**: NVMe, SATA, and VirtIO devices all work
- [ ] **SYS-002**: System file writes use sudo fallback
- [ ] **SYS-002**: Service installation works as non-root

### Test Commands

```bash
# Run security-focused tests
pytest tests/test_security.py -v

# Check for remaining os.system calls
grep -rn "os.system" src/ && echo "FAIL: os.system still used" || echo "PASS"

# Check for direct file writes to /etc
grep -rn 'open.*"/etc' src/ | grep -v "atomic_write" && echo "FAIL" || echo "PASS"

# Run migration tests
pytest tests/test_migration.py -v

# Test path traversal protection
python -c "
from store.installer import _safe_filename
assert _safe_filename('http://x.com/../../../etc/passwd') == 'passwd'
assert _safe_filename('http://x.com/..%2F..%2Fetc%2Fpasswd') in ['passwd', 'download']
print('Path traversal protection: PASS')
"
```

---

## Next Phase

Once all items are verified, proceed to [Phase 2: Core Feature Completion](./PHASE_2_CORE_FEATURES.md).
