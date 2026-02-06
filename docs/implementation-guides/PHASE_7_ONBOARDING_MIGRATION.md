# Phase 7: Onboarding, Migration & Theming

**Status:** WIZARD COMPLETE, MIGRATION COMPLETE, THEMING DONE — Needs integration testing
**Estimated Time:** 4-6 days
**Prerequisites:** Phase 6 complete (App Store functional)

---

## What Already Exists (DO NOT Rewrite)

### Onboarding Wizard — `src/onboarding/wizard.py` (408 lines) — COMPLETE

GTK4/Adwaita onboarding wizard with 6 pages:

| Page | Purpose | Status |
|------|---------|--------|
| Welcome | Introduction to NeuronOS | Complete |
| Hardware Check | GPU/IOMMU capability detection | Complete |
| VM Setup | Windows/macOS VM creation options | Complete |
| Migration | File migration from other OSes | Complete |
| Tutorial | Quick usage guide | Complete |
| Complete | Setup finalization | Complete |

All methods implemented: navigation (`_on_back_clicked`, `_on_next_clicked`, `_on_skip_clicked`), configuration (`_save_preferences`, `_configure_gpu`, `_setup_vms`, `_start_migration`), finalization (`_finalize_setup`, `_mark_first_boot_complete`).

User data tracked: `setup_windows_vm`, `setup_macos_vm`, `gpu_passthrough`, `migrate_files`, `migration_source`.

### Drive Detector — `src/migration/drive_detector.py` (334 lines) — COMPLETE

- **`DriveType` enum**: UNKNOWN, WINDOWS, MACOS, LINUX, DATA
- **`DetectedDrive` dataclass**: device, mount_point, label, filesystem, size_bytes, drive_type, users, is_system_drive
- **`DriveDetector` class**: `scan()`, `_is_windows_drive()`, `_is_macos_drive()`, `_is_linux_drive()`, `_find_windows_users()`, `_find_macos_users()`, `_find_linux_users()`, `get_windows_drives()`, `get_macos_drives()`, `mount_drive()`
- Uses `lsblk --json` with `/proc/mounts` fallback

### File Migrator — `src/migration/migrator.py` (734 lines) — COMPLETE

- **`FileCategory` enum**: DOCUMENTS, PICTURES, MUSIC, VIDEOS, DOWNLOADS, DESKTOP, BROWSER_CHROME, BROWSER_FIREFOX, BROWSER_EDGE, SSH_KEYS, GIT_CONFIG
- **`Migrator` base class**: `scan()`, `migrate()`, `_copy_directory()`, `_copy_file()`, `_set_ssh_permissions()`
- **`WindowsMigrator`**: Handles AppData paths, browser profiles, SSH keys, `.gitconfig`
- **`MacOSMigrator`**: Handles macOS-specific paths (Movies, Library)
- **`ApplicationSettingsMigrator`**: VSCode, Git, SSH, NPM, Pip with proper permissions
- **`create_migrator()` factory**: Returns correct subclass based on OS type

### GTK4 Themes — `iso-profile/airootfs/usr/share/neuron-os/themes/` — COMPLETE

Three theme CSS files already exist:

| Theme | File | Description |
|-------|------|-------------|
| NeuronOS Default | `neuron.css` | Modern dark theme with blue accents |
| Windows 11 Style | `win11.css` | Windows 11-like appearance |
| macOS Style | `macos.css` | macOS-like appearance |

Themes are GTK4 CSS applied via `~/.config/gtk-4.0/gtk.css`.

### GNOME Defaults — `iso-profile/airootfs/etc/dconf/db/local.d/00-neuronos` — COMPLETE

System-wide GNOME defaults configured:
- Materia-dark GTK theme
- NeuronOS wallpaper
- Window buttons: minimize, maximize, close
- Dock favorites: Files, Firefox, Terminal, Store, VM Manager
- Tap-to-click enabled
- No auto screen lock

### What Needs Work

- **Wizard-to-theme integration** — The wizard's theme selection page should apply the chosen CSS theme
- **Wizard-to-migration integration** — The wizard's migration page should use `DriveDetector` + `Migrator`
- **Wizard-to-VM integration** — The wizard's VM setup page should queue VM creation via `vm_manager`
- **First-boot autostart** — Verify `neuron-welcome.desktop` triggers wizard correctly
- **Post-wizard processing** — Background service to process queued VMs and migration tasks

---

## Phase 7 Objectives

| # | Objective | Verification |
|---|-----------|-------------|
| 7.1 | Wizard launches on first boot | Autostart triggers, wizard window appears |
| 7.2 | Hardware check page shows real data | GPU count, IOMMU status, capability level displayed |
| 7.3 | VM setup page queues VM creation | User selections saved to `~/.config/neuronos/pending-vms/` |
| 7.4 | Migration page detects drives and copies files | Windows/macOS partitions found, files migrated |
| 7.5 | Theme selection applies CSS | Chosen theme CSS copied to `~/.config/gtk-4.0/gtk.css` |
| 7.6 | Wizard marks first-boot complete | Flag file prevents re-run, user can manually re-run |
| 7.7 | All three themes work correctly | Each theme visually distinct, all GNOME apps styled |

---

## Step 7.1: Verify First-Boot Autostart

### Check Autostart Entry

The autostart entry exists at `iso-profile/airootfs/etc/xdg/autostart/neuron-welcome.desktop`:

```bash
cat iso-profile/airootfs/etc/xdg/autostart/neuron-welcome.desktop
# Should contain:
# Exec=/usr/bin/neuron-welcome
# X-GNOME-Autostart-enabled=true
```

### Check Welcome Script

The welcome script at `iso-profile/airootfs/usr/bin/neuron-welcome` should:

1. Check if running as `liveuser` — if yes, show live ISO welcome with install option
2. Check if first-boot flag exists — if not, launch the onboarding wizard
3. If first-boot already complete — exit silently

### Check Entry Point

```bash
cat iso-profile/airootfs/usr/bin/neuron-welcome
# Should launch the onboarding wizard for installed systems
```

### First-Boot Detection Logic

The wizard uses `~/.config/neuronos/first-boot-complete` as a flag file:

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path

flag = Path.home() / '.config/neuronos/first-boot-complete'
print(f'First boot flag: {flag}')
print(f'Exists: {flag.exists()}')
print(f'Is first boot: {not flag.exists()}')
"
```

### What to Check

- [ ] `neuron-welcome.desktop` exists in `/etc/xdg/autostart/`
- [ ] `X-GNOME-Autostart-enabled=true` is set
- [ ] `neuron-welcome` script checks for liveuser vs installed system
- [ ] First-boot flag path is `~/.config/neuronos/first-boot-complete`
- [ ] Wizard doesn't launch if flag file exists

---

## Step 7.2: Verify Hardware Check Integration

The wizard's Hardware Check page should use the existing `hardware_detect` module.

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')

# Test the hardware detection modules the wizard should use
from hardware_detect.gpu_scanner import GPUScanner
from hardware_detect.cpu_detect import CPUDetector
from hardware_detect.iommu_parser import IOMMUParser

# CPU
cpu = CPUDetector()
info = cpu.detect()
print(f'CPU: {info.vendor} - {info.model_name}')
print(f'IOMMU capable: {info.has_iommu}')

# GPUs
scanner = GPUScanner()
gpus = scanner.scan()
print(f'GPUs found: {len(gpus)}')
for g in gpus:
    print(f'  {g.vendor_name} {g.device_name} (boot_vga={g.is_boot_vga})')

# IOMMU
parser = IOMMUParser()
parser.parse_all()
print(f'IOMMU groups: {len(parser.groups)}')

# Capability determination
if len(gpus) >= 2 and len(parser.groups) > 0:
    print('Capability: FULL (dual GPU + IOMMU)')
elif len(gpus) == 1 and len(parser.groups) > 0:
    print('Capability: LIMITED (single GPU passthrough)')
else:
    print('Capability: BASIC (Wine/Proton only)')
"
```

### What to Check

- [ ] `GPUScanner().scan()` returns GPU list without errors
- [ ] `CPUDetector().detect()` returns CPU info
- [ ] `IOMMUParser().parse_all()` works (even if 0 groups in VM/container)
- [ ] Wizard Hardware Check page calls these modules
- [ ] Capability level shown to user (Full/Limited/Basic)

---

## Step 7.3: Verify VM Setup Integration

The wizard's VM Setup page should queue VM creation for post-wizard processing.

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
import json

# Test that the wizard can save VM preferences
queue_dir = Path.home() / '.config/neuronos/pending-vms'
queue_dir.mkdir(parents=True, exist_ok=True)

# Simulate wizard saving a Windows VM request
config = {
    'type': 'windows',
    'status': 'pending',
    'user_selections': {
        'ram_gb': 8,
        'disk_gb': 64,
        'gpu_passthrough': True,
    }
}

test_file = queue_dir / 'windows-test.json'
test_file.write_text(json.dumps(config, indent=2))
print(f'Queued VM config at: {test_file}')
print(f'Contents: {json.dumps(config, indent=2)}')

# Cleanup
test_file.unlink()
queue_dir.rmdir()
print('Test cleanup complete')
"
```

### Post-Wizard VM Processing

After the wizard completes, a background process should:

1. Read pending VM configs from `~/.config/neuronos/pending-vms/`
2. Use `vm_manager.core.vm_lifecycle.VMLifecycle` to create VMs
3. Use `vm_manager.core.template_engine.TemplateEngine` to generate XML
4. Report success/failure via desktop notification

### What to Check

- [ ] Wizard VM Setup page saves preferences to JSON
- [ ] Preferences include: VM type, RAM, disk, GPU passthrough choice
- [ ] `vm_manager` module can read and process the queued configs
- [ ] VM creation uses existing `TemplateEngine` for XML generation
- [ ] User notified when VM creation completes

---

## Step 7.4: Verify Migration Integration

The wizard's Migration page should use `DriveDetector` + `Migrator`.

### Test Drive Detection

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from migration.drive_detector import DriveDetector

detector = DriveDetector()
drives = detector.scan()

print(f'Detected {len(drives)} drives:')
for d in drives:
    print(f'  {d.device}: {d.drive_type.value} ({d.filesystem})')
    print(f'    Mount: {d.mount_point or \"not mounted\"}')
    print(f'    Size: {d.size_display}')
    if d.users:
        print(f'    Users: {d.users}')
"
```

### Test Migration Flow

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from migration.migrator import create_migrator, FileCategory

# Test factory function
migrator = create_migrator('windows', '/mnt/windows', 'TestUser')
print(f'Migrator type: {type(migrator).__name__}')
print(f'Categories: {[c.value for c in FileCategory]}')

migrator_mac = create_migrator('macos', '/mnt/macos', 'TestUser')
print(f'Mac migrator type: {type(migrator_mac).__name__}')
"
```

### Migration Categories

The migrator supports these file categories:

| Category | Windows Source | Linux Destination |
|----------|--------------|-------------------|
| Documents | `C:\Users\X\Documents` | `~/Documents` |
| Pictures | `C:\Users\X\Pictures` | `~/Pictures` |
| Music | `C:\Users\X\Music` | `~/Music` |
| Videos | `C:\Users\X\Videos` | `~/Videos` |
| Downloads | `C:\Users\X\Downloads` | `~/Downloads` |
| Desktop | `C:\Users\X\Desktop` | `~/Desktop` |
| Chrome | `AppData\Local\Google\Chrome` | `~/.config/google-chrome` |
| Firefox | `AppData\Roaming\Mozilla\Firefox` | `~/.mozilla/firefox` |
| SSH Keys | `C:\Users\X\.ssh` | `~/.ssh` (with correct permissions) |
| Git Config | `C:\Users\X\.gitconfig` | `~/.gitconfig` |

### What to Check

- [ ] `DriveDetector().scan()` lists block devices
- [ ] `_is_windows_drive()` correctly identifies NTFS partitions with Windows dirs
- [ ] `_is_macos_drive()` correctly identifies macOS partitions
- [ ] `create_migrator()` returns correct subclass
- [ ] `WindowsMigrator.scan()` calculates file counts and sizes
- [ ] `WindowsMigrator.migrate()` copies files to correct destinations
- [ ] SSH key permissions set correctly (700 dir, 600 private keys, 644 public keys)
- [ ] Browser profile migration preserves directory structure

---

## Step 7.5: Verify Theme Selection

The wizard should offer theme selection and apply the chosen theme.

### Check Theme Files Exist

```bash
ls -la iso-profile/airootfs/usr/share/neuron-os/themes/
# Should show:
#   neuron.css   (NeuronOS default - dark with blue accents)
#   win11.css    (Windows 11 style)
#   macos.css    (macOS style)
```

### Theme Application Logic

The theme system works by copying the selected CSS to `~/.config/gtk-4.0/gtk.css`:

```bash
cd /home/user/NeuronOS

python3 -c "
from pathlib import Path

themes_dir = Path('iso-profile/airootfs/usr/share/neuron-os/themes')
for css in sorted(themes_dir.glob('*.css')):
    size = css.stat().st_size
    # Read first line for description
    first_line = css.read_text().split('\n')[0]
    print(f'{css.name} ({size} bytes): {first_line}')
"
```

### Theme Integration with Wizard

The wizard's theme selection should:

1. Show preview/description of each theme
2. Copy selected CSS to `~/.config/gtk-4.0/gtk.css`
3. Save theme choice in `~/.config/neuronos/preferences.json`
4. Apply immediately (GTK4 apps pick up CSS changes)

### Theme Integration with GNOME

Beyond GTK4 CSS, themes should also configure:

- **GTK theme**: Set via dconf (`org.gnome.desktop.interface.gtk-theme`)
- **Icon theme**: Set via dconf (`org.gnome.desktop.interface.icon-theme`)
- **Color scheme**: Set via dconf (`org.gnome.desktop.interface.color-scheme`)

### What to Check

- [ ] All three theme CSS files exist and are non-empty
- [ ] Wizard offers theme selection (NeuronOS, Windows 11, macOS)
- [ ] Selected theme CSS copied to `~/.config/gtk-4.0/gtk.css`
- [ ] Theme preference saved in `~/.config/neuronos/preferences.json`
- [ ] GTK4 apps reflect the theme immediately
- [ ] dconf settings updated for system-wide consistency

---

## Step 7.6: Verify First-Boot Completion

### Completion Flow

After the wizard finishes:

1. Save all preferences to `~/.config/neuronos/preferences.json`
2. Create first-boot flag: `touch ~/.config/neuronos/first-boot-complete`
3. Queue any pending VM creation tasks
4. Apply selected theme
5. Optionally disable autostart (or rely on flag file check)

### Verification Commands

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path

config_dir = Path.home() / '.config/neuronos'
flag = config_dir / 'first-boot-complete'
prefs = config_dir / 'preferences.json'

print(f'Config dir: {config_dir}')
print(f'Flag exists: {flag.exists()}')
print(f'Prefs exists: {prefs.exists()}')

if prefs.exists():
    import json
    data = json.loads(prefs.read_text())
    print(f'Preferences: {json.dumps(data, indent=2)}')
"
```

### What to Check

- [ ] `_mark_first_boot_complete()` creates the flag file
- [ ] `_save_preferences()` writes valid JSON
- [ ] Preferences include: theme, VM choices, migration status
- [ ] Wizard exits cleanly after completion
- [ ] Next login does NOT re-launch wizard
- [ ] User can manually re-run wizard via `neuron-welcome --force` or similar

---

## Step 7.7: Verify All Three Themes

### Test Each Theme Manually

```bash
cd /home/user/NeuronOS

# Check NeuronOS theme
echo "=== NeuronOS Default Theme ==="
head -20 iso-profile/airootfs/usr/share/neuron-os/themes/neuron.css

echo ""
echo "=== Windows 11 Theme ==="
head -20 iso-profile/airootfs/usr/share/neuron-os/themes/win11.css

echo ""
echo "=== macOS Theme ==="
head -20 iso-profile/airootfs/usr/share/neuron-os/themes/macos.css
```

### Theme Application Test

To test theme application in a live environment:

```bash
# Apply NeuronOS theme
cp /usr/share/neuron-os/themes/neuron.css ~/.config/gtk-4.0/gtk.css

# Apply Windows 11 theme
cp /usr/share/neuron-os/themes/win11.css ~/.config/gtk-4.0/gtk.css

# Apply macOS theme
cp /usr/share/neuron-os/themes/macos.css ~/.config/gtk-4.0/gtk.css
```

### What to Check

- [ ] NeuronOS theme: Dark background, blue accents, modern feel
- [ ] Windows 11 theme: Windows 11 color scheme, familiar look
- [ ] macOS theme: macOS-like appearance, proper button positions
- [ ] Switching themes doesn't break any GNOME apps
- [ ] Themes apply to GTK4 apps (Files, Terminal, Settings)
- [ ] Default theme (neuron.css) applied during ISO build for liveuser

---

## Summary of Work Required

| Item | Status | Effort |
|------|--------|--------|
| Onboarding Wizard (`wizard.py`) | DONE — verify integration | 1 day |
| Drive Detector (`drive_detector.py`) | DONE — verify | 2 hours |
| File Migrator (`migrator.py`) | DONE — verify | 2 hours |
| GTK4 Themes (3 CSS files) | DONE — verify | 1 hour |
| GNOME Defaults (dconf) | DONE — verify | 1 hour |
| Wizard-to-hardware integration | NEEDS TESTING | 4 hours |
| Wizard-to-VM integration | NEEDS TESTING | 4 hours |
| Wizard-to-migration integration | NEEDS TESTING | 4 hours |
| Wizard-to-theme integration | NEEDS TESTING | 4 hours |
| Post-wizard VM processing | MAY NEED WORK | 1 day |
| neuron-welcome script updates | MAY NEED WORK | 4 hours |

---

## Verification Checklist

### Phase 7 is COMPLETE when ALL boxes are checked:

**First-Boot Detection**
- [ ] Autostart entry exists and is GNOME-compatible
- [ ] Flag file mechanism works
- [ ] Wizard launches on first boot
- [ ] Wizard does NOT launch on subsequent boots

**Hardware Check**
- [ ] CPU detection works in wizard
- [ ] GPU detection works in wizard
- [ ] IOMMU status shown
- [ ] Capability level (Full/Limited/Basic) displayed

**VM Setup**
- [ ] Windows VM option offered
- [ ] macOS VM option offered
- [ ] "Neither" option available
- [ ] Selections queued for processing

**Migration**
- [ ] Drive detector finds Windows/macOS partitions
- [ ] User selects what to migrate
- [ ] Files copied correctly with progress
- [ ] SSH permissions preserved

**Theming**
- [ ] All three themes exist and are valid CSS
- [ ] Theme selection in wizard works
- [ ] Selected theme applied immediately
- [ ] Theme persists after reboot
- [ ] Default theme applied for liveuser

**Completion**
- [ ] Preferences saved to JSON
- [ ] First-boot flag created
- [ ] No errors during finalization

---

## Next Phase

Proceed to **[Phase 8: Testing & Production](./PHASE_8_TESTING_PRODUCTION.md)**
