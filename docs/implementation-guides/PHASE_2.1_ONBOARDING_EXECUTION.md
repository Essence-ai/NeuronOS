# Phase 2.1: Onboarding Wizard - Full Execution

**Status**: 🟡 FUNCTIONAL UI, NON-FUNCTIONAL LOGIC
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.1-1.5 complete (VM creation, migration, installers)

---

## The Problem: UI Without Execution

The onboarding wizard has a **beautiful UI but does nothing**:

### Current State (Broken)

```python
class OnboardingWizard(Adw.ApplicationWindow):
    def on_wizard_complete(self):
        """Wizard completed."""
        # TODO: Execute setup!
        # Currently just closes the wizard

        # Missing:
        # - Apply VFIO kernel parameters
        # - Enable IOMMU in GRUB
        # - Create Windows VM
        # - Start file migration
        # - Launch Store for app installation
```

### What Users See

1. Boot NeuronOS ✓
2. Onboarding wizard opens ✓
3. Select "Create Windows VM" with GPU ✓
4. Click "Complete" ✓
5. ❌ **NOTHING HAPPENS** - No VM created
6. User left staring at desktop with no working system

### The Impact

Users cannot complete first-time setup. The entire system is non-functional without manual CLI configuration.

---

## Objective: Wire Wizard to Actual Setup

After this phase:

1. ✅ Hardware detection runs and shows results
2. ✅ VFIO/IOMMU configured automatically
3. ✅ Windows VM created with user's GPU
4. ✅ File migration executes in background
5. ✅ User gets step-by-step feedback
6. ✅ Errors show clearly with recovery options

---

## Part 1: Connect Wizard to Backend

### 1.1: Update Wizard Completion Handler

**File**: `src/onboarding/wizard.py`

**Find the on_wizard_complete() method** (around line 250-300):

```python
def on_wizard_complete(self):
    """Handle wizard completion."""
    # CURRENTLY DOES NOTHING - just closes
    self.close()
```

**Replace with**:

```python
async def on_wizard_complete(self):
    """Execute full onboarding setup.

    This runs in background with progress reporting.
    """
    logger.info("Starting full onboarding setup")

    try:
        # Step 1: Apply hardware configuration
        if not await self._apply_hardware_config():
            self._show_error("Hardware configuration failed")
            return

        # Step 2: Create Windows VM
        if not await self._create_windows_vm():
            self._show_error("VM creation failed")
            return

        # Step 3: Migrate files (if selected)
        if self.selected_migration_categories:
            if not await self._start_file_migration():
                logger.warning("File migration failed (non-fatal)")

        # Step 4: Show completion screen with next steps
        self._show_completion_screen()

    except Exception as e:
        logger.error(f"Onboarding error: {e}")
        self._show_error(f"Setup failed: {e}")

async def _apply_hardware_config(self) -> bool:
    """Apply hardware configuration (VFIO, IOMMU).

    Returns:
        True if successful
    """
    try:
        self._show_progress("Configuring hardware...")

        from src.hardware_detect.config_generator import ConfigGenerator

        config_gen = ConfigGenerator()

        # Step 1: Detect GPUs and IOMMU groups
        self._show_progress("Detecting GPUs...")
        gpu_info = config_gen.scan_hardware()

        if not gpu_info.gpus:
            logger.warning("No GPUs detected")
            self._show_warning("No dedicated GPUs found. VM will use CPU rendering.")
            return True  # Not fatal

        # Step 2: Generate VFIO and modprobe config
        self._show_progress("Generating kernel configuration...")
        vfio_config = config_gen.generate_vfio_config(gpu_info.gpus)
        modprobe_config = config_gen.generate_modprobe_config()

        # Step 3: Apply kernel parameters (requires sudo)
        self._show_progress("Updating system configuration...")
        if not config_gen.apply_kernel_config(vfio_config, modprobe_config):
            logger.error("Failed to apply kernel config")
            return False

        # Step 4: Enable IOMMU in GRUB (requires reboot)
        self._show_progress("Updating bootloader...")
        iommu_enabled = config_gen.enable_iommu_in_grub()

        if not iommu_enabled:
            self._show_warning(
                "IOMMU not enabled. Reboot required. "
                "System will configure it after restart."
            )

        logger.info("Hardware configuration applied")
        return True

    except Exception as e:
        logger.error(f"Hardware config error: {e}")
        return False

async def _create_windows_vm(self) -> bool:
    """Create Windows VM with user's configuration.

    Returns:
        True if successful
    """
    try:
        self._show_progress("Creating Windows VM...")

        from src.vm_manager.core.vm_creator import VMCreator, VMConfig

        # Build VM config from wizard selections
        vm_config = VMConfig(
            name=self.vm_name or "Windows",
            memory_gb=self.selected_memory_gb or 16,
            vcpu_count=self.selected_vcpu_count or 8,
            disk_size_gb=self.selected_disk_size_gb or 50,
            gpus=[self.selected_gpu] if self.selected_gpu else [],
            iso_path=self.selected_windows_iso,
        )

        # Create VM
        creator = VMCreator()
        if not creator.create_vm(vm_config):
            logger.error("VM creation failed")
            return False

        # Generate encryption keys for guest agent (Phase 1.5)
        from src.security.key_generator import KeyGenerator
        encryption_key, hmac_key = KeyGenerator.generate_key_pair()
        KeyGenerator.write_vm_keys(vm_config.name, encryption_key, hmac_key)

        logger.info(f"VM created successfully: {vm_config.name}")
        return True

    except Exception as e:
        logger.error(f"VM creation error: {e}")
        return False

async def _start_file_migration(self) -> bool:
    """Start file migration in background.

    Returns:
        True if migration started successfully
    """
    try:
        self._show_progress("Starting file migration...")

        from src.migration.migrator import WindowsMigrator, MacOSMigrator

        # Detect which system to migrate from
        migrator_class = WindowsMigrator  # For now, default to Windows
        if self.selected_migration_source == "macos":
            migrator_class = MacOSMigrator

        # Detect source drive
        source_drive = self._detect_migration_source()
        if not source_drive:
            logger.warning("No source drive found for migration")
            return True  # Not fatal

        # Start migration
        migrator = migrator_class(source_drive, Path.home())
        migrator.categories = self.selected_migration_categories

        # Set progress callback
        migrator.on_progress = self._on_migration_progress

        # Run in background thread
        import threading
        migration_thread = threading.Thread(
            target=migrator.migrate,
            daemon=True,
        )
        migration_thread.start()

        logger.info("File migration started in background")
        return True

    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False

def _detect_migration_source(self) -> Optional[Path]:
    """Detect Windows/macOS partition to migrate from.

    Returns:
        Path to mounted Windows partition, or None
    """
    from src.migration.drive_detector import DriveDetector

    detector = DriveDetector()
    drives = detector.find_migration_sources()

    if not drives:
        return None

    # Use first available source
    return drives[0].mount_point

def _show_progress(self, message: str):
    """Show progress message in wizard."""
    # Update progress page
    if hasattr(self, "progress_page"):
        self.progress_page.set_message(message)

def _show_warning(self, message: str):
    """Show warning to user."""
    logger.warning(message)
    # Update progress with warning styling

def _show_error(self, message: str):
    """Show error to user."""
    logger.error(message)
    # Show error page with "Retry" or "Skip" buttons

def _on_migration_progress(self, progress):
    """Handle migration progress updates."""
    percentage = (progress.files_done / progress.files_total * 100) if progress.files_total > 0 else 0
    self._show_progress(f"Migrating files... {percentage:.0f}%")

def _show_completion_screen(self):
    """Show completion screen with next steps."""
    message = """
    Setup Complete! 🎉

    Your system is ready:
    ✓ Hardware configured for GPU passthrough
    ✓ Windows VM created (starting up...)
    ✓ Files migrated to Linux home
    ✓ App Store ready for installation

    Next Steps:
    1. Let Windows finish installing (10-15 minutes)
    2. Install essential apps from Store
    3. Create additional VMs if needed

    You can close this wizard anytime.
    """
    self._show_info_page(message)
```

### 1.2: Update Wizard Page Classes

**File**: `src/onboarding/pages.py`

The wizard pages need to actually collect configuration. Update these pages:

**HardwareCheckPage**:

```python
class HardwareCheckPage(Adw.PreferencesPage):
    """Show hardware detection results."""

    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        self.set_title("Hardware Check")

        # Run detection and display results
        self._run_detection()

    def _run_detection(self):
        """Run hardware detection."""
        from src.hardware_detect.gpu_scanner import GPUScanner
        from src.hardware_detect.cpu_detect import CPUDetector

        try:
            # Detect GPUs
            gpu_scanner = GPUScanner()
            self.gpus = gpu_scanner.scan_gpus()

            # Detect CPU features
            cpu_detector = CPUDetector()
            cpu_caps = cpu_detector.detect()

            # Display results
            self._display_results(cpu_caps)

        except Exception as e:
            logger.error(f"Hardware detection error: {e}")
            self._show_error(f"Detection failed: {e}")

    def _display_results(self, cpu_caps):
        """Display hardware detection results."""
        group = Adw.PreferencesGroup()
        group.set_title("Detected Hardware")

        # Show GPUs
        gpu_group = Adw.ActionRow()
        gpu_group.set_title("GPUs Detected")
        gpu_group.set_subtitle(f"{len(self.gpus)} GPU(s)")
        group.add(gpu_group)

        for gpu in self.gpus:
            gpu_row = Adw.ActionRow()
            gpu_row.set_title(gpu.name)
            gpu_row.set_subtitle(f"IOMMU Group: {gpu.iommu_group}")
            group.add(gpu_row)

        # Show CPU features
        cpu_group = Adw.PreferencesGroup()
        cpu_group.set_title("CPU Features")

        if cpu_caps.has_nested_virt:
            feature = Adw.ActionRow()
            feature.set_title("✓ Nested Virtualization")
            cpu_group.add(feature)

        if cpu_caps.has_iommu:
            feature = Adw.ActionRow()
            feature.set_title("✓ IOMMU Support")
            cpu_group.add(feature)

        self.set_content(group)
```

**VMConfigPage**:

```python
class VMConfigPage(Adw.PreferencesPage):
    """Configure Windows VM settings."""

    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        self.set_title("VM Configuration")

        # Build UI
        self._build_ui()

    def _build_ui(self):
        """Build configuration UI."""
        group = Adw.PreferencesGroup()
        group.set_title("Windows VM Settings")

        # VM Name
        name_row = Adw.EntryRow()
        name_row.set_title("VM Name")
        name_row.set_text("Windows")
        name_row.connect("notify::text", self._on_name_changed)
        group.add(name_row)

        # Memory size
        memory_row = Adw.SpinRow()
        memory_row.set_title("Memory (GB)")
        memory_row.set_range(2, 128)
        memory_row.set_value(16)
        memory_row.connect("notify::value", self._on_memory_changed)
        group.add(memory_row)

        # CPU cores
        cpu_row = Adw.SpinRow()
        cpu_row.set_title("CPU Cores")
        cpu_row.set_range(1, 16)
        cpu_row.set_value(8)
        cpu_row.connect("notify::value", self._on_cpu_changed)
        group.add(cpu_row)

        # GPU selection
        gpu_group = Adw.PreferencesGroup()
        gpu_group.set_title("GPU Assignment")

        # List available GPUs
        from src.hardware_detect.gpu_scanner import GPUScanner
        scanner = GPUScanner()
        gpus = scanner.scan_gpus()

        if gpus:
            for gpu in gpus:
                gpu_row = Adw.CheckRow()
                gpu_row.set_title(gpu.name)
                gpu_row.set_subtitle(f"IOMMU: {gpu.iommu_group}")
                gpu_row.connect("toggled", self._on_gpu_selected, gpu)
                gpu_group.add(gpu_row)
        else:
            no_gpu = Adw.ActionRow()
            no_gpu.set_title("No GPUs detected")
            no_gpu.set_subtitle("VM will use CPU rendering")
            gpu_group.add(no_gpu)

        self.set_content(group)

    def _on_name_changed(self, row, param):
        """VM name changed."""
        self.wizard.vm_name = row.get_text()

    def _on_memory_changed(self, row, param):
        """Memory size changed."""
        self.wizard.selected_memory_gb = int(row.get_value())

    def _on_cpu_changed(self, row, param):
        """CPU cores changed."""
        self.wizard.selected_vcpu_count = int(row.get_value())

    def _on_gpu_selected(self, row, gpu):
        """GPU selected."""
        self.wizard.selected_gpu = gpu if row.get_active() else None
```

**MigrationSourcePage**:

```python
class MigrationSourcePage(Adw.PreferencesPage):
    """Select files to migrate."""

    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        self.set_title("File Migration")

        self._build_ui()

    def _build_ui(self):
        """Build migration selection UI."""
        group = Adw.PreferencesGroup()
        group.set_title("Select what to migrate")

        from src.migration.migrator import FileCategory

        # Checkboxes for each category
        for category in [
            FileCategory.DOCUMENTS,
            FileCategory.PICTURES,
            FileCategory.MUSIC,
            FileCategory.SSH_KEYS,
            FileCategory.GIT_CONFIG,
            FileCategory.BROWSERS,
        ]:
            row = Adw.CheckRow()
            row.set_title(category.value)
            row.connect("toggled", self._on_category_toggled, category)
            group.add(row)

        self.set_content(group)

    def _on_category_toggled(self, row, category):
        """Category selection changed."""
        if not hasattr(self.wizard, 'selected_migration_categories'):
            self.wizard.selected_migration_categories = []

        if row.get_active():
            self.wizard.selected_migration_categories.append(category)
        else:
            self.wizard.selected_migration_categories.remove(category)
```

---

## Part 2: Add Progress Reporting

### 2.1: Create Progress Page

**File**: `src/onboarding/progress_page.py` (NEW FILE)

```python
"""Progress reporting during onboarding."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib


class ProgressPage(Adw.PreferencesPage):
    """Show progress of setup tasks."""

    def __init__(self):
        super().__init__()
        self.set_title("Setting Up")

        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_margin_top(40)
        vbox.set_margin_bottom(40)
        vbox.set_margin_start(40)
        vbox.set_margin_end(40)

        # Status message
        self.status_label = Gtk.Label()
        self.status_label.set_markup("<b>Configuring hardware...</b>")
        self.status_label.set_wrap(True)
        vbox.append(self.status_label)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        vbox.append(self.progress_bar)

        # Details
        self.details_label = Gtk.Label()
        self.details_label.add_css_class("dim-label")
        self.details_label.set_wrap(True)
        vbox.append(self.details_label)

        # Spinner
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.spinner.start()
        vbox.append(self.spinner)

        self.set_content(vbox)

    def set_message(self, message: str):
        """Update status message."""
        self.status_label.set_markup(f"<b>{message}</b>")

    def set_progress(self, fraction: float):
        """Update progress bar (0.0-1.0)."""
        self.progress_bar.set_fraction(fraction)

    def set_details(self, details: str):
        """Update details text."""
        self.details_label.set_text(details)

    def show_spinner(self, visible: bool = True):
        """Show or hide spinner."""
        self.spinner.set_visible(visible)
        if visible:
            self.spinner.start()
        else:
            self.spinner.stop()
```

### 2.2: Update Wizard to Use Progress Page

**File**: `src/onboarding/wizard.py`

```python
# In wizard page navigation, add progress page
self.progress_page = ProgressPage()

# Update pages list to include it
self.pages = [
    WelcomePage(self),
    HardwareCheckPage(self),
    VMConfigPage(self),
    MigrationSourcePage(self),
    self.progress_page,
    CompletionPage(self),
]
```

---

## Part 3: Error Handling

### 3.1: Add Error Recovery

**File**: `src/onboarding/wizard.py`

```python
def _show_error(self, message: str):
    """Show error with recovery options."""
    error_page = Adw.PreferencesPage()
    error_page.set_title("Setup Error")

    # Error message
    group = Adw.PreferencesGroup()
    error_label = Gtk.Label()
    error_label.set_markup(f"<b>Error:</b> {message}")
    error_label.set_wrap(True)
    group.add(error_label)

    # Buttons
    button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    button_box.set_halign(Gtk.Align.CENTER)

    retry_btn = Gtk.Button(label="Retry")
    retry_btn.connect("clicked", self._retry_setup)
    button_box.append(retry_btn)

    skip_btn = Gtk.Button(label="Skip & Continue")
    skip_btn.connect("clicked", self._skip_error)
    button_box.append(skip_btn)

    group.add(button_box)
    error_page.add(group)

    self.set_visible_page(error_page)
```

---

## Verification Checklist

Before moving to Phase 2.2:

**Hardware Configuration**:
- [ ] Hardware detection runs automatically
- [ ] GPU detection shows correct info
- [ ] VFIO config generated correctly
- [ ] GRUB updated with kernel parameters
- [ ] IOMMU enabled (or marked for reboot)

**VM Creation**:
- [ ] VM created with user's settings (name, RAM, CPUs)
- [ ] GPU assigned to VM correctly
- [ ] Encryption keys generated
- [ ] VM appears in VM Manager after setup
- [ ] VM can be started

**File Migration**:
- [ ] Migration runs in background (non-blocking)
- [ ] Progress bar updates during migration
- [ ] Files copied to correct locations
- [ ] SSH key permissions set (600/644)
- [ ] Migration errors don't crash wizard

**UI/UX**:
- [ ] Pages display hardware info clearly
- [ ] User selections stored correctly
- [ ] Progress page updates throughout setup
- [ ] Error page shows with recovery options
- [ ] Completion page displays next steps
- [ ] No crashes on edge cases

**Integration**:
- [ ] All Phase 1 components integrated:
  - [ ] Hardware detection (Phase 1.1 guest agent not needed here)
  - [ ] VM creation (Phase 1.2)
  - [ ] Migration (Phase 1.3)
  - [ ] Encryption keys (Phase 1.5)
- [ ] Proper error handling and logging
- [ ] No unhandled exceptions

---

## Acceptance Criteria

✅ **Phase 2.1 Complete When**:

1. Wizard executes full setup workflow
2. Hardware configured automatically
3. Windows VM created and ready to boot
4. File migration runs in background
5. User gets clear feedback throughout
6. Errors handled gracefully

❌ **Phase 2.1 Fails If**:

- Wizard closes without doing setup
- VM not created after completion
- No error messages on failures
- Wizard crashes

---

## Notes

### Async Operations

Use `async`/`await` for long operations to keep UI responsive:

```python
async def _apply_hardware_config(self) -> bool:
    # Long operation runs in thread pool
    # UI stays responsive
    pass
```

###  Next Reboot Warning

If IOMMU needs reboot:

```python
self._show_warning(
    "IOMMU configuration requires system reboot. "
    "This will happen on next startup."
)
```

---

## Next Steps

1. **Phase 2.2** completes the App Store GUI
2. **Phase 2.3** adds more hardware auto-configuration
3. **Phase 2.4** enables Looking Glass auto-start

Good luck! 🚀
