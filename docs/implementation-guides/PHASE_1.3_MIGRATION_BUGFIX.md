# Phase 1.3: Migration Bug Fix - File/Directory Type Confusion

**Status**: 🔴 CRITICAL BUG - Causes data loss during migration
**Estimated Time**: 2 days
**Prerequisites**: None (can work in parallel)

---

## The Problem: Data Loss Bug

When migrating files from Windows/macOS, the system **loses SSH keys and Git config** because the code doesn't distinguish between **files** and **directories**.

### What Happens Today

```python
# Current buggy code treats all migration sources the same way:

# SSH_KEYS is a DIRECTORY: ~/.ssh/
#   Contains: id_rsa, id_rsa.pub, config (files inside)

# GIT_CONFIG is a FILE: ~/.gitconfig
#   Is: A single configuration file

# But the code does this for both:
def migrate(self, source_path):
    # Assumes source_path is always a directory
    for item in source_path.iterdir():  # ← FAILS if source is a file!
        shutil.copy2(item, target)
```

### The Impact

**Scenario**: User runs migration with "SSH Keys" and "Git Config" selected:

```
Step 1: Get source path for GIT_CONFIG
  source_path = /mnt/windows/Users/John/.gitconfig  ← This is a FILE

Step 2: Call migrate()
  target_path.mkdir()  ← Creates directory ~/.gitconfig/

Step 3: Try to iterate file
  for item in source_path.iterdir():  ← BUG! This fails

Step 4: Exception caught silently
  logger.warning("Error copying...")  ← User never sees this

Result: Git config lost, SSH keys partially migrated or lost
```

**User Experience**:
- User selects both SSH Keys and Git Config
- Migration completes "successfully"
- But Git config is missing
- SSH keys might be partially copied
- User has no idea what went wrong

---

## Objective: Fix File/Directory Handling

After this phase:

1. ✅ SSH keys (directories) migrated correctly
2. ✅ Git config (files) migrated correctly
3. ✅ File permissions set correctly (SSH keys: 600, pub keys: 644)
4. ✅ Proper error handling and user feedback
5. ✅ No data loss during migration

---

## Part 1: Understand Current Code

### 1.1: Current Buggy Implementation

**File**: `src/migration/migrator.py` (lines 340-450)

```python
class WindowsMigrator:
    def migrate(self) -> bool:
        """Migrate user files from Windows."""

        for category in self.categories:
            source_path = self._get_source_path(category)
            target_path = self._get_target_path(category)

            if source_path and source_path.exists():
                # BUG: Doesn't check if source is file or directory!
                self._copy_directory(source_path, target_path)  # Always assumes directory

    def _copy_directory(self, source: Path, target: Path):
        """Copy directory contents."""
        try:
            # BUG: This fails if source is a file!
            for item in source.iterdir():  # ← ERROR if source is ~/.gitconfig (file)
                if item.is_file():
                    shutil.copy2(item, target)
                elif item.is_dir():
                    shutil.copytree(item, target / item.name)
        except Exception as e:
            logger.warning(f"Error copying: {e}")  # Silently logs, user doesn't see
            self.progress.errors.append(str(e))
```

### 1.2: Migration Categories

**File**: `src/migration/migrator.py` (lines 50-75)

```python
class FileCategory(Enum):
    """File categories to migrate."""

    DOCUMENTS = "Documents"           # Directory
    PICTURES = "Pictures"              # Directory
    MUSIC = "Music"                    # Directory
    DOWNLOADS = "Downloads"            # Directory
    VIDEOS = "Videos"                  # Directory
    DESKTOP = "Desktop"                # Directory

    SSH_KEYS = ".ssh"                  # ← DIRECTORY (but code treats as both)
    GIT_CONFIG = ".gitconfig"          # ← FILE (but code treats as both)

    BROWSERS = "browser_profiles"      # Directory (complex)
```

### 1.3: Source/Target Path Detection

```python
def _get_source_path(self, category: FileCategory) -> Optional[Path]:
    """Get source path for category on Windows volume."""

    if category == FileCategory.DOCUMENTS:
        return self.windows_home / "Documents"  # Directory
    elif category == FileCategory.SSH_KEYS:
        return self.windows_home / ".ssh"  # Directory
    elif category == FileCategory.GIT_CONFIG:
        return self.windows_home / ".gitconfig"  # FILE - but no distinction!

def _get_target_path(self, category: FileCategory) -> Path:
    """Get target path in Linux home."""

    if category == FileCategory.DOCUMENTS:
        return self.linux_home / "Documents"  # Directory
    elif category == FileCategory.SSH_KEYS:
        return self.linux_home / ".ssh"  # Directory
    elif category == FileCategory.GIT_CONFIG:
        return self.linux_home / ".gitconfig"  # FILE - but creates directory!
```

---

## Part 2: Implement File/Directory Handling

### 2.1: Fix Main Migrate Method

**File**: `src/migration/migrator.py`

**Find this method** (around line 340):

```python
def migrate(self) -> bool:
    """Perform the migration."""
    self._cancelled = False

    for category in self.categories:
        if self._cancelled:
            break

        self.progress.current_category = category
        source_path = self._get_source_path(category)
        target_path = self._get_target_path(category)

        if source_path and source_path.exists():
            # BUG: Doesn't check file vs directory!
            self._copy_directory(source_path, target_path)

    return len(self.progress.errors) == 0
```

**Replace with**:

```python
def migrate(self) -> bool:
    """
    Perform the migration.

    Handles both file and directory sources correctly.
    This fixes the bug where SSH_KEYS and GIT_CONFIG were confused.
    """
    self._cancelled = False

    try:
        for category in self.categories:
            if self._cancelled:
                logger.info("Migration cancelled by user")
                break

            self.progress.current_category = category
            source_path = self._get_source_path(category)
            target_path = self._get_target_path(category)

            if not source_path:
                logger.info(f"Source path not found for {category}")
                continue

            if not source_path.exists():
                logger.warning(f"Source does not exist: {source_path}")
                self.progress.errors.append(f"Source not found: {source_path}")
                continue

            logger.info(f"Migrating {category}: {source_path} → {target_path}")

            # FIX: Check if source is file or directory
            if source_path.is_file():
                # Handle single file (e.g., .gitconfig)
                self._copy_single_file(source_path, target_path, category)
            elif source_path.is_dir():
                # Handle directory (e.g., .ssh, Documents)
                self._copy_directory(source_path, target_path, category)
            else:
                logger.warning(f"Source is neither file nor directory: {source_path}")
                self.progress.errors.append(f"Invalid source type: {source_path}")

        logger.info(f"Migration complete. Errors: {len(self.progress.errors)}")
        return len(self.progress.errors) == 0

    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}")
        self.progress.errors.append(f"Migration failed: {e}")
        return False
```

### 2.2: Add Single File Copy Method

**File**: `src/migration/migrator.py`

**Add this new method** (after the migrate() method):

```python
def _copy_single_file(
    self,
    source: Path,
    target: Path,
    category: FileCategory
) -> bool:
    """
    Copy a single file (not a directory).

    Used for items like .gitconfig that are files, not directories.
    Handles:
    - Creating parent directories
    - File permission setting (SSH keys: 600, others: 644)
    - Conflict handling
    """
    try:
        # Step 1: Ensure target parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Step 2: Check if target already exists
        if target.exists():
            # Target exists - check if it's a file or directory
            if target.is_dir():
                # ERROR: Target is a directory but we want to write a file
                error = (
                    f"Cannot migrate {source.name}: "
                    f"target is a directory, expected a file at {target}"
                )
                logger.error(error)
                self.progress.errors.append(error)
                return False

            # File exists - check if it's the same
            source_size = source.stat().st_size
            target_size = target.stat().st_size

            if source_size == target_size:
                # Files are same size - skip
                logger.info(
                    f"Skipping {source.name}: already exists with same size"
                )
                self.progress.files_done += 1
                self.progress.bytes_done += source_size
                self._notify_progress()
                return True
            else:
                # Different size - back up original and replace
                logger.info(f"Replacing {target.name} (backup created)")
                backup_path = target.with_suffix(target.suffix + ".backup")
                target.rename(backup_path)

        # Step 3: Copy the file
        logger.info(f"Copying file: {source.name} ({source.stat().st_size} bytes)")
        self.progress.current_file = source.name

        import shutil
        shutil.copy2(source, target)

        # Step 4: Set proper permissions based on category
        self._set_file_permissions(target, category)

        # Step 5: Update progress
        self.progress.files_done += 1
        self.progress.bytes_done += source.stat().st_size
        self._notify_progress()

        logger.info(f"Successfully copied: {source} → {target}")
        return True

    except PermissionError as e:
        error = f"Permission denied copying {source}: {e}"
        logger.warning(error)
        self.progress.errors.append(error)
        return False

    except OSError as e:
        error = f"OS error copying {source}: {e}"
        logger.warning(error)
        self.progress.errors.append(error)
        return False

    except Exception as e:
        error = f"Unexpected error copying {source}: {e}"
        logger.error(error)
        self.progress.errors.append(error)
        return False
```

### 2.3: Fix Directory Copy Method

**File**: `src/migration/migrator.py`

**Find and replace** `_copy_directory()` method:

```python
def _copy_directory(self, source: Path, target: Path) -> bool:
    """
    Copy a directory and all its contents recursively.

    Used for categories like Documents, .ssh, Pictures, etc.
    Handles:
    - Recursive directory traversal
    - File permission setting
    - Conflict handling (skip or replace)
    - Progress tracking
    """
    try:
        # Step 1: Create target directory if it doesn't exist
        if not target.exists():
            logger.info(f"Creating directory: {target}")
            target.mkdir(parents=True, exist_ok=True)
        elif not target.is_dir():
            error = f"Target exists but is not a directory: {target}"
            logger.error(error)
            self.progress.errors.append(error)
            return False

        # Step 2: Set initial permissions for target directory
        self._set_directory_permissions(target)

        # Step 3: Copy all items in source directory
        logger.info(f"Copying directory contents: {source}")

        import shutil
        for item in source.iterdir():
            if self._cancelled:
                logger.info("Copy cancelled by user")
                break

            if self._should_skip(item):
                logger.info(f"Skipping: {item.name}")
                continue

            target_item = target / item.name

            try:
                if item.is_file():
                    # Copy file
                    logger.info(f"Copying file: {item.name}")
                    shutil.copy2(item, target_item)

                    # Set permissions based on filename
                    self._set_file_permissions(target_item, None)

                    self.progress.files_done += 1
                    self.progress.bytes_done += item.stat().st_size
                    self.progress.current_file = item.name

                elif item.is_dir():
                    # Recursively copy subdirectory
                    logger.info(f"Copying subdirectory: {item.name}")
                    if target_item.exists():
                        logger.info(f"Directory exists, merging: {target_item}")

                    self._copy_directory(item, target_item)

                self._notify_progress()

            except (PermissionError, OSError) as e:
                error = f"Error copying {item.name}: {e}"
                logger.warning(error)
                self.progress.errors.append(error)
                # Continue with next item
                continue

        logger.info(f"Directory copy complete: {source} → {target}")
        return True

    except PermissionError as e:
        error = f"Permission denied accessing {source}: {e}"
        logger.warning(error)
        self.progress.errors.append(error)
        return False

    except Exception as e:
        error = f"Error copying directory {source}: {e}"
        logger.error(error)
        self.progress.errors.append(error)
        return False
```

### 2.4: Add Permission Setting Methods

**File**: `src/migration/migrator.py`

**Add these new helper methods**:

```python
def _set_file_permissions(self, path: Path, category: Optional[FileCategory]):
    """
    Set appropriate permissions for a migrated file.

    SSH keys need special handling:
    - Private keys: 600 (read/write owner only)
    - Public keys: 644 (read-only for others)
    - Other files: 644 (default)
    """
    import stat

    try:
        filename_lower = path.name.lower()

        # SSH key handling
        if category == FileCategory.SSH_KEYS or path.parent.name == ".ssh":
            if filename_lower.endswith(".pub") or filename_lower == "config":
                # Public keys and config: 644
                mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
                path.chmod(mode)
                logger.debug(f"Set permissions 644 on {path.name}")
            else:
                # Private keys: 600
                mode = stat.S_IRUSR | stat.S_IWUSR
                path.chmod(mode)
                logger.debug(f"Set permissions 600 on {path.name}")
        else:
            # Default: 644
            mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            path.chmod(mode)

    except Exception as e:
        logger.warning(f"Could not set permissions on {path}: {e}")
        # Non-fatal - continue
```

```python
def _set_directory_permissions(self, path: Path):
    """
    Set appropriate permissions for a migrated directory.

    Standard: 755 (owner RWX, group RX, others RX)
    SSH directories: 700 (owner RWX only)
    """
    import stat

    try:
        if path.name == ".ssh":
            # .ssh directory: 700 (very restrictive)
            mode = stat.S_IRWXU
            path.chmod(mode)
            logger.debug(f"Set permissions 700 on {path.name}")
        else:
            # Default directories: 755
            mode = (
                stat.S_IRWXU  # Owner: rwx
                | stat.S_IRGRP  # Group: r-x
                | stat.S_IXGRP
                | stat.S_IROTH  # Others: r-x
                | stat.S_IXOTH
            )
            path.chmod(mode)
            logger.debug(f"Set permissions 755 on {path.name}")

    except Exception as e:
        logger.warning(f"Could not set directory permissions on {path}: {e}")
        # Non-fatal
```

### 2.5: Improve Progress Scanning

**File**: `src/migration/migrator.py`

**Update the `_scan_directory()` method** to handle both files and directories:

```python
def _scan_directory(self, path: Path, category: FileCategory):
    """
    Scan a path (file or directory) and update total bytes/files.

    This is called before migration to show progress bar accurately.
    Must handle both file and directory paths.
    """
    try:
        if path.is_file():
            # Single file - just add its size
            logger.info(f"Scanning file: {path.name}")
            self.progress.files_total += 1
            self.progress.bytes_total += path.stat().st_size

        elif path.is_dir():
            # Directory - recursively scan
            logger.info(f"Scanning directory: {path}")
            for item in path.iterdir():
                if self._should_skip(item):
                    continue

                if item.is_file():
                    try:
                        file_size = item.stat().st_size
                        self.progress.files_total += 1
                        self.progress.bytes_total += file_size
                    except OSError as e:
                        logger.warning(f"Could not stat file {item}: {e}")
                        continue

                elif item.is_dir():
                    # Recursively scan subdirectory
                    self._scan_directory(item, category)

    except PermissionError as e:
        logger.warning(f"Permission denied scanning {path}: {e}")

    except Exception as e:
        logger.warning(f"Error scanning {path}: {e}")
```

---

## Part 3: Add Tests

### 3.1: Create Test File

**File**: `tests/test_migration_bugfix.py` (NEW FILE)

```python
"""
Tests for file/directory migration bug fix.

This tests that SSH keys (directories) and Git config (files)
are migrated correctly without data loss.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from src.migration.migrator import (
    WindowsMigrator,
    FileCategory,
    MigrationProgress,
)


@pytest.fixture
def temp_dirs():
    """Create temporary source and target directories."""
    with tempfile.TemporaryDirectory() as source_tmp:
        with tempfile.TemporaryDirectory() as target_tmp:
            source = Path(source_tmp)
            target = Path(target_tmp)

            yield source, target


def test_ssh_keys_directory_migration(temp_dirs):
    """Test that .ssh directory (with files inside) is migrated correctly."""
    source, target = temp_dirs

    # Create mock .ssh directory with files
    ssh_dir = source / ".ssh"
    ssh_dir.mkdir()

    # Create SSH key files
    (ssh_dir / "id_rsa").write_text("PRIVATE KEY CONTENT")
    (ssh_dir / "id_rsa.pub").write_text("PUBLIC KEY CONTENT")
    (ssh_dir / "config").write_text("SSH CONFIG")

    # Create migrator
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.SSH_KEYS]

    # Run migration
    assert migrator.migrate()

    # Verify directory structure
    target_ssh = target / ".ssh"
    assert target_ssh.exists()
    assert target_ssh.is_dir()

    # Verify files exist
    assert (target_ssh / "id_rsa").exists()
    assert (target_ssh / "id_rsa.pub").exists()
    assert (target_ssh / "config").exists()

    # Verify file content
    assert (target_ssh / "id_rsa").read_text() == "PRIVATE KEY CONTENT"

    # Verify permissions
    import stat
    id_rsa_mode = (target_ssh / "id_rsa").stat().st_mode
    # Check that private key is readable/writable by owner only
    assert id_rsa_mode & stat.S_IRUSR  # Owner can read
    assert id_rsa_mode & stat.S_IWUSR  # Owner can write

    id_rsa_pub_mode = (target_ssh / "id_rsa.pub").stat().st_mode
    # Check that public key is readable by others
    assert id_rsa_pub_mode & stat.S_IROTH  # Others can read


def test_git_config_file_migration(temp_dirs):
    """Test that .gitconfig file (not directory) is migrated correctly."""
    source, target = temp_dirs

    # Create mock .gitconfig file
    git_config = source / ".gitconfig"
    git_config_content = "[user]\n    name = John Doe\n    email = john@example.com"
    git_config.write_text(git_config_content)

    # Create migrator
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.GIT_CONFIG]

    # Run migration
    assert migrator.migrate()

    # Verify file was copied (not as directory)
    target_config = target / ".gitconfig"
    assert target_config.exists()
    assert target_config.is_file()
    assert not target_config.is_dir()

    # Verify content
    assert target_config.read_text() == git_config_content


def test_migration_with_missing_file(temp_dirs):
    """Test that missing source files are handled gracefully."""
    source, target = temp_dirs

    # .gitconfig doesn't exist

    # Create migrator
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.GIT_CONFIG]

    # Should complete without error (missing source is not fatal)
    assert migrator.migrate()
    assert len(migrator.progress.errors) == 0


def test_migration_preserves_directory_structure(temp_dirs):
    """Test that nested directories are preserved."""
    source, target = temp_dirs

    # Create nested Documents structure
    docs = source / "Documents"
    docs.mkdir()
    (docs / "Work").mkdir()
    (docs / "Work" / "Project1").mkdir()
    (docs / "Work" / "Project1" / "file.txt").write_text("content")
    (docs / "Personal").mkdir()
    (docs / "Personal" / "file2.txt").write_text("content2")

    # Migrate
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.DOCUMENTS]

    assert migrator.migrate()

    # Verify structure
    target_docs = target / "Documents"
    assert (target_docs / "Work" / "Project1" / "file.txt").exists()
    assert (target_docs / "Personal" / "file2.txt").exists()


def test_migration_handles_permission_denied(temp_dirs):
    """Test that permission errors are handled gracefully."""
    source, target = temp_dirs

    # Create a file
    (source / "test.txt").write_text("content")

    # Create migrator
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.DOCUMENTS]

    # Mock the copy2 to raise PermissionError
    with patch("shutil.copy2") as mock_copy:
        mock_copy.side_effect = PermissionError("Access denied")

        # Migration should complete but record error
        result = migrator.migrate()

        # Should fail (has errors)
        assert not result
        assert len(migrator.progress.errors) > 0


def test_migration_progress_tracking(temp_dirs):
    """Test that progress is properly tracked during migration."""
    source, target = temp_dirs

    # Create some files
    docs = source / "Documents"
    docs.mkdir()
    (docs / "file1.txt").write_text("a" * 1000)
    (docs / "file2.txt").write_text("b" * 2000)

    # Create migrator
    migrator = WindowsMigrator(source, target)
    migrator.categories = [FileCategory.DOCUMENTS]

    # Track progress
    progress_updates = []
    def on_progress(prog):
        progress_updates.append((prog.files_done, prog.bytes_done))

    migrator.on_progress = on_progress

    # Migrate
    assert migrator.migrate()

    # Verify progress was tracked
    assert len(progress_updates) > 0
    assert progress_updates[-1][0] == 2  # 2 files
    assert progress_updates[-1][1] == 3000  # 3000 bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 3.2: Run Tests

```bash
# Run the new tests
pytest tests/test_migration_bugfix.py -v

# Expected output:
# test_ssh_keys_directory_migration PASSED
# test_git_config_file_migration PASSED
# test_migration_with_missing_file PASSED
# test_migration_preserves_directory_structure PASSED
# test_migration_handles_permission_denied PASSED
# test_migration_progress_tracking PASSED
```

---

## Verification Checklist

Before moving to Phase 1.4:

**File/Directory Handling**:
- [ ] `migrate()` correctly detects file vs directory
- [ ] Single file (`.gitconfig`) copied as file, not directory
- [ ] Directory (`.ssh`) contents copied recursively
- [ ] Nested directories preserved (Documents/Work/Project1/file)
- [ ] Source is checked with `.is_file()` and `.is_dir()` before processing

**Permission Setting**:
- [ ] SSH private keys have 600 permissions (user RW only)
- [ ] SSH public keys have 644 permissions (others can read)
- [ ] SSH directory has 700 permissions (user RWX only)
- [ ] Regular files have 644 permissions
- [ ] Regular directories have 755 permissions

**Error Handling**:
- [ ] Missing source files don't cause crash
- [ ] Permission denied is logged and caught
- [ ] Partial migration doesn't lose data from earlier categories
- [ ] All errors collected and reported in `progress.errors`

**File Conflicts**:
- [ ] Existing files with same size are skipped
- [ ] Existing files with different size are backed up and replaced
- [ ] Existing directories block file copy (appropriate error)

**Progress Tracking**:
- [ ] `_scan_directory()` handles both files and directories
- [ ] Progress bar shows accurate totals
- [ ] `files_done` and `bytes_done` increment correctly
- [ ] User can cancel during large migrations

**Test Coverage**:
- [ ] All 6 tests in `test_migration_bugfix.py` pass
- [ ] No data loss in any test scenario
- [ ] Permission errors handled gracefully
- [ ] Directory structure preserved

**Code Quality**:
- [ ] No hardcoded paths
- [ ] All exceptions logged with context
- [ ] No silent failures (errors reported)
- [ ] Comments explain file vs directory handling
- [ ] `_copy_single_file()` and `_copy_directory()` clearly separated

---

## Acceptance Criteria

✅ **Phase 1.3 Complete When**:

1. SSH keys migrate as directory with files inside
2. Git config migrates as single file
3. File permissions set correctly
4. All tests pass
5. No data loss in any scenario

❌ **Phase 1.3 Fails If**:

- `.gitconfig` still treated as directory
- SSH keys lost or partially migrated
- Permissions not set correctly
- Tests fail

---

## Risks & Mitigations

### Risk 1: Breaking Existing Migration

**Issue**: Changes might break working directory migrations

**Mitigation**:
- Changes are backward compatible (add handling, don't remove it)
- Run all existing migration tests
- Test with multiple directory structures

### Risk 2: SSH Key Permissions Too Restrictive

**Issue**: User can't read SSH keys after migration

**Mitigation**:
- Set 600 only for private keys (id_rsa, etc.)
- Set 644 for public keys (id_rsa.pub)
- Test SSH login after migration

### Risk 3: Directory vs File Detection Fails

**Issue**: Symlinks or special files confuse detection

**Mitigation**:
- Use `.is_file()` and `.is_dir()` only (don't follow symlinks)
- Log what type was detected
- Handle symlinks explicitly (skip or follow based on setting)

---

## Next Steps

1. **Phase 1.4** completes the Proton installer
2. **Phase 1.5** adds encryption to guest agent
3. After all Phase 1 complete, move to Phase 2

---

## Testing Checklist

Run these commands to verify everything works:

```bash
# Run migration tests
pytest tests/test_migration_bugfix.py -v

# Run all migration tests
pytest tests/test_migration*.py -v

# Check for file/directory type checks
grep -n "is_file\|is_dir" src/migration/migrator.py

# Verify permissions are set
grep -n "_set_file_permissions\|_set_directory_permissions" src/migration/migrator.py

# Look for silent failures
grep -n "except.*pass" src/migration/migrator.py
```

Good luck! 🚀
