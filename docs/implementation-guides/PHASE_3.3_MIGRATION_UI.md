# Phase 3.3: Migration Progress UI & File Transfer Management

**Status**: 🟡 PARTIAL - Backend works, GUI progress tracking missing
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.3 (Migration Bug Fix), Phase 3.2 (Error Handling)

---

## What is Migration Progress UI?

When users switch from Windows or macOS to NeuronOS, they want to bring their files with them (Documents, Pictures, Desktop, etc.). This requires copying potentially **hundreds of gigabytes** of data from old installations.

**Without progress UI**: Users see a spinning cursor for hours, not knowing if it's working or frozen.

**With progress UI**: Users see:
- Current file being copied
- Transfer speed (MB/s)
- Estimated time remaining
- Total progress (45% complete, 23GB / 50GB)
- Ability to pause/cancel
- Clear error messages if a file fails

---

## Current State: Working Backend, Missing Frontend

### What Already Works ✅

**File**: `src/migration/migrator.py` (~400 lines)

We have:
- ✅ **Drive detection** - Finds Windows/macOS partitions automatically
- ✅ **File enumeration** - Lists all user files to migrate
- ✅ **Parallel copying** - Uses rsync for efficient transfers
- ✅ **Error handling** - Skips locked/permission-denied files
- ✅ **Conflict resolution** - Handles duplicate filenames

Example backend code:
```python
class FileMigrator:
    def migrate_files(
        self,
        source_drive: Path,
        target_dir: Path,
        callback: Optional[Callable] = None
    ) -> MigrationResult:
        """
        Migrate files from source to target.

        Args:
            source_drive: Windows/macOS partition mount point
            target_dir: Destination (usually /home/user/)
            callback: Progress callback(current_file, bytes_done, bytes_total)

        Returns:
            MigrationResult with files copied, failed, etc.
        """
        # Works but callback is rarely called
        ...
```

### What's Missing ❌

| Missing Feature | Impact | User Experience |
|---|---|---|
| **Real-time progress** | Users don't know if it's working | "Has it frozen? Should I restart?" |
| **File count/size tracking** | No idea how much is left | "Is this 10% done or 90% done?" |
| **Speed calculation** | Can't estimate completion | "Will this take 5 minutes or 5 hours?" |
| **Current file display** | Black box process | "What's it doing right now?" |
| **Pause/resume** | All-or-nothing | "I need to close my laptop but migration will fail" |
| **Conflict resolution UI** | Files silently overwrite/skip | "Did it copy my important.docx or skip it?" |
| **Error recovery** | One failed file stops everything | "Locked file caused entire migration to fail" |

### The Impact

**Scenario**: Maria is migrating from Windows 10 to NeuronOS:

1. ✅ NeuronOS detects her Windows partition (C:\)
2. ✅ Shows list of folders to migrate: Documents (45GB), Pictures (23GB), Desktop (2GB)
3. ✅ Maria clicks "Migrate"
4. ❌ **Current**: Spinner appears. No information for 2 hours.
5. ❌ Maria's laptop battery dies after 90 minutes
6. ❌ Migration fails. All progress lost. Must start over.
7. ❌ Maria gives up on NeuronOS

**Desired behavior**:
1. ✅ Progress dialog shows: "Copying Documents/Taxes/2023/receipts.pdf"
2. ✅ "45% complete (32GB / 70GB) - Speed: 28MB/s - 23 minutes remaining"
3. ✅ Maria sees it's working, not frozen
4. ✅ Laptop battery low → Maria clicks "Pause" → Closes laptop
5. ✅ Resumes later → Migration continues from where it left off
6. ✅ One file fails (locked by Windows) → Shown in "Skipped Files" list, rest continue
7. ✅ Migration completes successfully

---

## Objective: Production-Quality Migration UX

After completing Phase 3.3:

1. ✅ **Real-time Progress Bar** - Updates every second with % complete
2. ✅ **File Counter** - "Copying file 1,234 of 5,678"
3. ✅ **Current File Path** - Show full path of file being copied
4. ✅ **Transfer Speed** - Calculate MB/s with 5-second rolling average
5. ✅ **ETA Calculation** - Remaining time based on current speed
6. ✅ **Pause/Resume** - Graceful interruption and continuation
7. ✅ **Conflict Resolution Dialog** - Ask user: Skip, Overwrite, or Rename
8. ✅ **Error List** - Show all failed files with reasons
9. ✅ **Completion Summary** - "Copied 5,632 files (68GB), Skipped 46 files (234MB)"
10. ✅ **Background Operation** - Can minimize and do other tasks

---

## Part 1: Enhanced Migration Backend with Progress Callbacks

Upgrade the migrator to support fine-grained progress reporting.

### 1.1: Migration Progress Protocol

**File**: `src/migration/migrator.py` (modifications)

```python
"""
File migration with comprehensive progress reporting.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, List
import time
import shutil
import threading

class MigrationStatus(Enum):
    """Migration status."""
    SCANNING = "scanning"           # Counting files
    COPYING = "copying"             # Transferring files
    PAUSED = "paused"               # User paused
    COMPLETED = "completed"         # Finished successfully
    FAILED = "failed"               # Error occurred
    CANCELLED = "cancelled"         # User cancelled


@dataclass
class MigrationProgress:
    """Real-time migration progress."""
    status: MigrationStatus
    current_file: Optional[Path]    # File being copied right now
    files_copied: int               # Files completed
    files_total: int                # Total files to copy
    bytes_copied: int               # Bytes completed
    bytes_total: int                # Total bytes to copy
    current_file_bytes: int         # Bytes of current file copied
    current_file_total: int         # Total bytes of current file
    speed_bytes_per_sec: float      # Transfer speed (bytes/s)
    eta_seconds: float              # Estimated time remaining
    errors: List[str]               # Error messages

    @property
    def percent_complete(self) -> float:
        """Calculate percentage complete."""
        if self.bytes_total == 0:
            return 0.0
        return (self.bytes_copied / self.bytes_total) * 100

    @property
    def speed_mb_per_sec(self) -> float:
        """Speed in MB/s."""
        return self.speed_bytes_per_sec / (1024 * 1024)

    @property
    def eta_minutes(self) -> float:
        """ETA in minutes."""
        return self.eta_seconds / 60


class EnhancedMigrator:
    """
    File migrator with real-time progress reporting.

    Usage:
        def on_progress(progress: MigrationProgress):
            print(f"{progress.percent_complete:.1f}% - {progress.current_file}")

        migrator = EnhancedMigrator()
        result = migrator.migrate(
            source="/mnt/windows/Users/Maria",
            dest="/home/maria",
            progress_callback=on_progress
        )
    """

    def __init__(self):
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._progress = None
        self._start_time = None
        self._bytes_at_start = 0

    def migrate(
        self,
        source: Path,
        dest: Path,
        progress_callback: Optional[Callable[[MigrationProgress], None]] = None
    ) -> "MigrationResult":
        """
        Migrate files with progress tracking.

        Args:
            source: Source directory
            dest: Destination directory
            progress_callback: Called every 100ms with progress update

        Returns:
            MigrationResult
        """
        self._stop_flag.clear()
        self._pause_flag.clear()
        self._start_time = time.time()

        # Phase 1: Scan files
        self._progress = MigrationProgress(
            status=MigrationStatus.SCANNING,
            current_file=None,
            files_copied=0,
            files_total=0,
            bytes_copied=0,
            bytes_total=0,
            current_file_bytes=0,
            current_file_total=0,
            speed_bytes_per_sec=0,
            eta_seconds=0,
            errors=[]
        )

        if progress_callback:
            progress_callback(self._progress)

        # Get list of all files
        files_to_copy = self._scan_directory(source)
        self._progress.files_total = len(files_to_copy)
        self._progress.bytes_total = sum(f.stat().st_size for f in files_to_copy if f.exists())

        # Phase 2: Copy files
        self._progress.status = MigrationStatus.COPYING

        for file_path in files_to_copy:
            # Check for pause/stop
            while self._pause_flag.is_set():
                time.sleep(0.1)

            if self._stop_flag.is_set():
                self._progress.status = MigrationStatus.CANCELLED
                break

            # Update current file
            self._progress.current_file = file_path
            self._progress.current_file_total = file_path.stat().st_size if file_path.exists() else 0

            if progress_callback:
                progress_callback(self._progress)

            # Copy file with progress
            try:
                self._copy_file_with_progress(file_path, dest, progress_callback)
                self._progress.files_copied += 1
            except Exception as e:
                self._progress.errors.append(f"{file_path}: {e}")

        # Phase 3: Complete
        self._progress.status = MigrationStatus.COMPLETED
        if progress_callback:
            progress_callback(self._progress)

        return MigrationResult(
            files_copied=self._progress.files_copied,
            bytes_copied=self._progress.bytes_copied,
            errors=self._progress.errors
        )

    def _scan_directory(self, path: Path) -> List[Path]:
        """Recursively list all files."""
        files = []
        for item in path.rglob("*"):
            if item.is_file():
                files.append(item)
        return files

    def _copy_file_with_progress(
        self,
        source: Path,
        dest_dir: Path,
        progress_callback: Optional[Callable]
    ):
        """Copy single file with byte-level progress."""
        dest = dest_dir / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)

        total_size = source.stat().st_size
        copied_size = 0

        # Copy in chunks to report progress
        CHUNK_SIZE = 1024 * 1024  # 1MB chunks

        with source.open('rb') as src_f:
            with dest.open('wb') as dest_f:
                while True:
                    chunk = src_f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    dest_f.write(chunk)
                    copied_size += len(chunk)

                    # Update progress
                    self._progress.current_file_bytes = copied_size
                    self._progress.bytes_copied += len(chunk)

                    # Calculate speed and ETA
                    elapsed = time.time() - self._start_time
                    if elapsed > 0:
                        self._progress.speed_bytes_per_sec = (
                            (self._progress.bytes_copied - self._bytes_at_start) / elapsed
                        )

                        if self._progress.speed_bytes_per_sec > 0:
                            remaining_bytes = self._progress.bytes_total - self._progress.bytes_copied
                            self._progress.eta_seconds = remaining_bytes / self._progress.speed_bytes_per_sec

                    if progress_callback:
                        progress_callback(self._progress)

    def pause(self):
        """Pause migration."""
        self._pause_flag.set()
        self._progress.status = MigrationStatus.PAUSED

    def resume(self):
        """Resume paused migration."""
        self._pause_flag.clear()
        self._progress.status = MigrationStatus.COPYING
        # Reset speed calculation
        self._start_time = time.time()
        self._bytes_at_start = self._progress.bytes_copied

    def cancel(self):
        """Cancel migration."""
        self._stop_flag.set()


@dataclass
class MigrationResult:
    """Migration result summary."""
    files_copied: int
    bytes_copied: int
    errors: List[str]
```

---

## Part 2: Progress Dialog UI

**File**: `src/migration/gui/progress_dialog.py` (new file)

```python
"""
Migration progress dialog with real-time updates.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from pathlib import Path
from typing import Optional
import threading

from src.migration.migrator import EnhancedMigrator, MigrationProgress, MigrationStatus


class MigrationProgressDialog(Adw.Window):
    """
    Full-featured migration progress dialog.

    Features:
    - Real-time progress bar
    - File counter and current file display
    - Speed and ETA calculation
    - Pause/Resume/Cancel buttons
    - Error list
    - Completion summary
    """

    def __init__(self, source: Path, dest: Path, parent: Optional[Gtk.Window] = None):
        super().__init__()
        self.set_title("Migrating Files")
        self.set_default_size(600, 400)
        self.set_modal(True)
        if parent:
            self.set_transient_for(parent)

        self.source = source
        self.dest = dest
        self.migrator = EnhancedMigrator()
        self.migration_thread = None

        self._build_ui()

    def _build_ui(self):
        """Build progress dialog UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(box)

        # Header
        header = Adw.HeaderBar()
        box.append(header)

        # Content area
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        box.append(content)

        # Progress group
        progress_group = Adw.PreferencesGroup()
        progress_group.set_title("Migration Progress")

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        progress_group.add(self.progress_bar)

        # Current file
        self.current_file_label = Gtk.Label(label="Scanning files...")
        self.current_file_label.set_xalign(0)
        self.current_file_label.set_wrap(True)
        self.current_file_label.add_css_class("dim-label")
        progress_group.add(self.current_file_label)

        # Stats row
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.speed_label = Gtk.Label(label="Speed: --")
        stats_box.append(self.speed_label)

        self.eta_label = Gtk.Label(label="ETA: --")
        stats_box.append(self.eta_label)

        self.file_count_label = Gtk.Label(label="Files: 0 / 0")
        stats_box.append(self.file_count_label)

        progress_group.add(stats_box)

        content.append(progress_group)

        # Error list (expandable)
        self.error_expander = Adw.ExpanderRow(title="Errors (0)")
        self.error_list_box = Gtk.ListBox()
        self.error_list_box.add_css_class("boxed-list")
        self.error_expander.add_row(self.error_list_box)
        content.append(self.error_expander)

        # Action buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_halign(Gtk.Align.END)

        self.pause_btn = Gtk.Button(label="Pause")
        self.pause_btn.connect("clicked", self._on_pause_clicked)
        button_box.append(self.pause_btn)

        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        button_box.append(self.cancel_btn)

        content.append(button_box)

    def start_migration(self):
        """Start migration in background thread."""
        self.migration_thread = threading.Thread(
            target=self._run_migration,
            daemon=True
        )
        self.migration_thread.start()

    def _run_migration(self):
        """Run migration with progress updates."""
        result = self.migrator.migrate(
            source=self.source,
            dest=self.dest,
            progress_callback=self._on_progress_update
        )

        # Show completion on main thread
        GLib.idle_add(self._show_completion, result)

    def _on_progress_update(self, progress: MigrationProgress):
        """Called from migration thread with progress updates."""
        # Update UI on main thread
        GLib.idle_add(self._update_ui, progress)

    def _update_ui(self, progress: MigrationProgress):
        """Update UI with progress (runs on main thread)."""
        # Progress bar
        fraction = progress.percent_complete / 100.0
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{progress.percent_complete:.1f}%")

        # Current file
        if progress.current_file:
            self.current_file_label.set_text(str(progress.current_file))
        else:
            self.current_file_label.set_text("Scanning files...")

        # Speed
        if progress.speed_mb_per_sec > 0:
            self.speed_label.set_text(f"Speed: {progress.speed_mb_per_sec:.1f} MB/s")

        # ETA
        if progress.eta_minutes > 0:
            if progress.eta_minutes < 1:
                eta_str = f"{progress.eta_seconds:.0f} seconds"
            else:
                eta_str = f"{progress.eta_minutes:.1f} minutes"
            self.eta_label.set_text(f"ETA: {eta_str}")

        # File count
        self.file_count_label.set_text(
            f"Files: {progress.files_copied} / {progress.files_total}"
        )

        # Errors
        if progress.errors:
            self.error_expander.set_title(f"Errors ({len(progress.errors)})")
            # Add new errors to list
            # (simplified - in real impl, track which errors are already shown)

        return False  # Don't repeat

    def _on_pause_clicked(self, button):
        """Pause/resume migration."""
        if button.get_label() == "Pause":
            self.migrator.pause()
            button.set_label("Resume")
        else:
            self.migrator.resume()
            button.set_label("Pause")

    def _on_cancel_clicked(self, button):
        """Cancel migration."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Cancel Migration?",
            body="Are you sure? Progress will be lost."
        )
        dialog.add_response("no", "No")
        dialog.add_response("yes", "Yes, Cancel")
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_cancel_confirmed)
        dialog.present()

    def _on_cancel_confirmed(self, dialog, response):
        """Handle cancel confirmation."""
        if response == "yes":
            self.migrator.cancel()
            self.close()

    def _show_completion(self, result):
        """Show completion dialog."""
        if result.errors:
            msg = f"Migration completed with {len(result.errors)} errors.\n\n"
            msg += f"Copied {result.files_copied} files ({result.bytes_copied / (1024**3):.2f} GB)"
        else:
            msg = f"Migration completed successfully!\n\n"
            msg += f"Copied {result.files_copied} files ({result.bytes_copied / (1024**3):.2f} GB)"

        dialog = Adw.MessageDialog(
            transient_for=self.get_transient_for(),
            heading="Migration Complete",
            body=msg
        )
        dialog.add_response("ok", "OK")
        dialog.present()

        self.close()
```

---

## Part 3: Integration with Onboarding

**File**: `src/onboarding/pages.py` (modifications)

```python
# Add migration progress integration

from src.migration.gui.progress_dialog import MigrationProgressDialog

class MigrationPage(Adw.NavigationPage):
    """Onboarding migration page."""

    def on_migrate_clicked(self, button):
        """Start migration with progress dialog."""
        source = self.get_selected_source_drive()
        dest = Path.home()

        # Show progress dialog
        progress_dialog = MigrationProgressDialog(source, dest, parent=self.get_root())
        progress_dialog.start_migration()
        progress_dialog.present()
```

---

## Part 4: Testing

**File**: `tests/test_migration_progress.py` (new file)

```python
"""Tests for migration progress tracking."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from src.migration.migrator import EnhancedMigrator, MigrationProgress, MigrationStatus


def test_progress_updates(tmp_path):
    """Test that progress callback is called during migration."""
    # Create test files
    source = tmp_path / "source"
    source.mkdir()
    (source / "file1.txt").write_text("x" * 1000)
    (source / "file2.txt").write_text("y" * 2000)

    dest = tmp_path / "dest"
    dest.mkdir()

    # Track progress updates
    updates = []

    def callback(progress: MigrationProgress):
        updates.append(progress)

    # Run migration
    migrator = EnhancedMigrator()
    result = migrator.migrate(source, dest, callback)

    # Verify we got updates
    assert len(updates) > 0
    assert updates[0].status == MigrationStatus.SCANNING
    assert any(u.status == MigrationStatus.COPYING for u in updates)
    assert updates[-1].status == MigrationStatus.COMPLETED


def test_pause_resume(tmp_path):
    """Test pause/resume functionality."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "large.bin").write_bytes(b"x" * 10_000_000)  # 10MB

    dest = tmp_path / "dest"

    migrator = EnhancedMigrator()

    # Start migration
    import threading
    thread = threading.Thread(
        target=lambda: migrator.migrate(source, dest),
        daemon=True
    )
    thread.start()

    # Let it start
    import time
    time.sleep(0.1)

    # Pause
    migrator.pause()
    assert migrator._pause_flag.is_set()

    # Resume
    migrator.resume()
    assert not migrator._pause_flag.is_set()

    thread.join(timeout=5)


def test_cancel(tmp_path):
    """Test cancellation."""
    source = tmp_path / "source"
    source.mkdir()
    for i in range(100):
        (source / f"file{i}.txt").write_text(f"content{i}")

    dest = tmp_path / "dest"

    migrator = EnhancedMigrator()

    # Start migration
    import threading
    thread = threading.Thread(
        target=lambda: migrator.migrate(source, dest),
        daemon=True
    )
    thread.start()

    # Cancel immediately
    import time
    time.sleep(0.05)
    migrator.cancel()

    thread.join(timeout=2)

    # Verify not all files were copied
    copied_files = list(dest.rglob("*"))
    assert len(copied_files) < 100
```

---

## Verification Checklist

Before marking Phase 3.3 complete, verify:

- [ ] **Progress bar updates** - Smooth animation, not jumpy
- [ ] **File count accurate** - "Copying file 234 of 567" matches reality
- [ ] **Current file shown** - Full path displayed, truncated if too long
- [ ] **Speed calculated** - MB/s shown, updates every second
- [ ] **ETA accurate** - Within 20% of actual completion time for large transfers
- [ ] **Pause works** - Migration stops, can resume from same point
- [ ] **Cancel works** - Migration stops immediately, partial files cleaned up
- [ ] **Error handling** - Locked files don't stop migration, shown in error list
- [ ] **Completion summary** - Shows total files, bytes, errors
- [ ] **Background operation** - Can minimize dialog and continue

---

## Acceptance Criteria

✅ **Phase 3.3 is COMPLETE when**:
1. Progress updates at least once per second
2. Speed and ETA are accurate (within 20% margin)
3. Pause/resume works without data loss
4. Errors don't stop migration, are listed separately
5. Users can minimize and monitor in background
6. Large migrations (100GB+) complete successfully

❌ **Phase 3.3 FAILS if**:
1. Progress bar freezes or doesn't update
2. ETA is wildly inaccurate (off by 10x)
3. Pause corrupts files or loses progress
4. Single error stops entire migration
5. Dialog must stay open (can't minimize)
6. Memory usage grows unbounded for large file counts

---

## Risks & Mitigations

### Risk 1: Progress updates slow down copying
**Mitigation**: Update UI maximum once per 100ms, batch small file updates.

### Risk 2: Pause leaves files in inconsistent state
**Mitigation**: Only pause between files, never mid-file. Finish current file before pausing.

### Risk 3: ETA calculation unstable
**Mitigation**: Use 5-second rolling average for speed, not instant speed.

### Risk 4: Memory leak from tracking thousands of errors
**Mitigation**: Limit error list to 100 most recent errors. Log all to file.

---

## Next Steps

This phase enables:
- **Phase 4.1**: Testing framework can test migration scenarios
- **Onboarding**: Users see professional migration experience
- **Production readiness**: Large data migrations (100GB+) are reliable

---

## Resources

- [GTK4 ProgressBar](https://docs.gtk.org/gtk4/class.ProgressBar.html)
- [Python Threading](https://docs.python.org/3/library/threading.html)
- [GLib.idle_add for thread-safe UI updates](https://docs.gtk.org/glib/func.idle_add.html)

Good luck! 🚀
