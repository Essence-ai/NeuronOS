# Phase 7: First-Run Experience & Migration

**Status:** USER EXPERIENCE - Critical for adoption
**Estimated Time:** 4-6 days
**Prerequisites:** Phase 6 complete (App Store working)

---

## Recap: What We Are Building

**NeuronOS** targets non-technical users who have never opened a terminal. The first-run experience must:
- Guide users through initial setup
- Configure the system based on user needs
- Migrate files from Windows/macOS if needed
- Set up VMs if user wants professional software

**This Phase's Goal:** Create an onboarding wizard that:
1. Welcomes users and explains features
2. Checks hardware compatibility
3. Offers to set up VMs
4. Migrates files from other OS
5. Applies user preferences

---

## Phase 7 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 7.1 | Wizard launches on first boot | Auto-starts, shows welcome |
| 7.2 | Hardware check works | Detects GPUs, shows capability |
| 7.3 | VM setup options work | Queues VM creation |
| 7.4 | File migration works | Copies files from Windows/Mac |
| 7.5 | Preferences saved | Config persists after reboot |
| 7.6 | Wizard only runs once | Doesn't repeat on next boot |

---

## Step 7.1: First-Boot Detection

The wizard should only run on first boot after installation.

### Check First-Boot Status

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, 'src')

FIRST_BOOT_FLAG = Path.home() / ".config/neuronos/first-boot-complete"

def is_first_boot() -> bool:
    return not FIRST_BOOT_FLAG.exists()

def mark_first_boot_complete():
    FIRST_BOOT_FLAG.parent.mkdir(parents=True, exist_ok=True)
    FIRST_BOOT_FLAG.touch()

print(f"First boot: {is_first_boot()}")
print(f"Flag path: {FIRST_BOOT_FLAG}")
EOF
```

### Create Autostart Entry

Create `iso-profile/airootfs/etc/xdg/autostart/neuron-welcome.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=NeuronOS Welcome
Comment=First-boot setup wizard
Exec=neuron-welcome
Icon=neuronos
Terminal=false
Categories=System;
X-GNOME-Autostart-enabled=true
OnlyShowIn=LXQt;GNOME;KDE;XFCE;
```

### Verification Criteria for 7.1
- [ ] First-boot detection works
- [ ] Autostart entry exists
- [ ] Wizard launches on first login
- [ ] Wizard doesn't launch after completion

---

## Step 7.2: Hardware Compatibility Check

Show users their system's capabilities.

### Hardware Check Page

```python
# In onboarding/pages.py

class HardwareCheckPage:
    """Page that shows hardware compatibility."""

    def __init__(self):
        self.results = {}

    def run_checks(self):
        """Run all hardware checks."""
        from hardware_detect.gpu_scanner import GPUScanner
        from hardware_detect.cpu_detect import CPUDetector
        from hardware_detect.iommu_parser import IOMMUParser

        # CPU Check
        cpu = CPUDetector().detect()
        self.results['cpu'] = {
            'vendor': cpu.vendor,
            'model': cpu.model_name,
            'iommu_supported': cpu.has_iommu,
        }

        # GPU Check
        gpus = GPUScanner().scan()
        self.results['gpus'] = [{
            'name': f"{g.vendor_name} {g.device_name}",
            'is_primary': g.is_boot_vga,
            'passthrough_candidate': not g.is_boot_vga,
        } for g in gpus]

        # IOMMU Check
        parser = IOMMUParser()
        parser.parse_all()
        self.results['iommu'] = {
            'enabled': len(parser.groups) > 0,
            'groups': len(parser.groups),
        }

        # Determine capability level
        self.results['capability'] = self._determine_capability()

    def _determine_capability(self) -> str:
        """Determine system capability level."""
        gpus = self.results.get('gpus', [])
        iommu = self.results.get('iommu', {})

        if len(gpus) >= 2 and iommu.get('enabled'):
            return 'full'  # Full GPU passthrough supported
        elif len(gpus) == 1 and iommu.get('enabled'):
            return 'limited'  # Single GPU passthrough (with limitations)
        else:
            return 'basic'  # Wine/Proton only, no passthrough

    def get_summary(self) -> str:
        """Get human-readable summary."""
        cap = self.results.get('capability', 'unknown')

        if cap == 'full':
            return (
                "Your system fully supports GPU passthrough!\n"
                "You can run Windows applications at near-native performance."
            )
        elif cap == 'limited':
            return (
                "Your system supports single-GPU passthrough.\n"
                "VMs will require temporarily disabling your display."
            )
        else:
            return (
                "GPU passthrough is not available.\n"
                "You can still run many Windows apps via Wine/Proton."
            )
```

### Test Hardware Check

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')

# Simulate the page
class HardwareCheckPage:
    def __init__(self):
        self.results = {}

    def run_checks(self):
        from hardware_detect.gpu_scanner import GPUScanner
        from hardware_detect.cpu_detect import CPUDetector
        from hardware_detect.iommu_parser import IOMMUParser

        cpu = CPUDetector().detect()
        gpus = GPUScanner().scan()
        parser = IOMMUParser()
        parser.parse_all()

        self.results = {
            'cpu': cpu.vendor,
            'gpu_count': len(gpus),
            'iommu_enabled': len(parser.groups) > 0,
        }

        if len(gpus) >= 2 and len(parser.groups) > 0:
            self.results['capability'] = 'full'
        elif len(gpus) == 1 and len(parser.groups) > 0:
            self.results['capability'] = 'limited'
        else:
            self.results['capability'] = 'basic'

        return self.results

page = HardwareCheckPage()
results = page.run_checks()
print("Hardware Check Results:")
for k, v in results.items():
    print(f"  {k}: {v}")
EOF
```

### Verification Criteria for 7.2
- [ ] Hardware check runs without errors
- [ ] CPU detected correctly
- [ ] GPUs detected correctly
- [ ] IOMMU status detected
- [ ] Capability level determined

---

## Step 7.3: VM Setup Options

Allow users to opt into VM creation.

### VM Setup Page

The page should offer:
1. Windows VM - for Office, Adobe, etc.
2. macOS VM - for Mac switchers
3. Neither - for users who only need Wine/Proton

### Save VM Preferences

```python
def queue_vm_creation(vm_type: str, user_data: dict):
    """Queue a VM for creation after wizard completes."""
    from pathlib import Path
    from utils.atomic_write import atomic_write_json
    from datetime import datetime

    queue_dir = Path.home() / ".config/neuronos/pending-vms"
    queue_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "type": vm_type,
        "queued_at": datetime.now().isoformat(),
        "user_selections": user_data,
        "status": "pending",
    }

    atomic_write_json(queue_dir / f"{vm_type}.json", config)
```

### Test VM Queue

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, 'src')

queue_dir = Path.home() / ".config/neuronos/pending-vms"

# Create test queue entry
from utils.atomic_write import atomic_write_json
from datetime import datetime

queue_dir.mkdir(parents=True, exist_ok=True)

config = {
    "type": "windows",
    "queued_at": datetime.now().isoformat(),
    "status": "pending",
}

atomic_write_json(queue_dir / "windows-test.json", config)
print("VM queued for creation")

# List pending
for f in queue_dir.glob("*.json"):
    print(f"  - {f.name}")

# Cleanup
(queue_dir / "windows-test.json").unlink()
EOF
```

### Verification Criteria for 7.3
- [ ] VM options displayed
- [ ] User can select Windows/macOS/Neither
- [ ] Selection saved to pending queue
- [ ] Queue processed on next boot

---

## Step 7.4: File Migration

Migrate files from Windows or macOS partitions.

### Detect Migration Sources

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from migration.drive_detector import DriveDetector

detector = DriveDetector()
sources = detector.detect_sources()

print("Detected migration sources:")
for source in sources:
    print(f"  {source.os_type}: {source.path}")
    print(f"    User: {source.user}")
    print(f"    Size: {source.size_bytes / 1024 / 1024 / 1024:.1f} GB")
EOF
```

### Migration Categories

The migrator should support:
- Documents
- Pictures
- Music
- Videos
- Downloads
- Desktop
- Browser data (bookmarks, passwords)
- SSH keys
- Git config

### Test Migration

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from migration.migrator import Migrator, FileCategory
from pathlib import Path

# Create mock source for testing
mock_source = Path("/tmp/mock-windows")
(mock_source / "Users/TestUser/Documents").mkdir(parents=True, exist_ok=True)
(mock_source / "Users/TestUser/Documents/test.txt").write_text("Test file")

# Test migrator
from dataclasses import dataclass

@dataclass
class MockSource:
    path: Path = mock_source
    user: str = "TestUser"
    os_type: str = "windows"

# This would be the actual migrator test
print("Migration test would run here")
print(f"Mock source: {mock_source}")

# Cleanup
import shutil
shutil.rmtree(mock_source, ignore_errors=True)
EOF
```

### Verification Criteria for 7.4
- [ ] Drive detector finds Windows/macOS partitions
- [ ] User selection for what to migrate
- [ ] Files copied correctly
- [ ] Permissions preserved (especially SSH keys)
- [ ] Progress shown during migration

---

## Step 7.5: Save Preferences

All user selections should be saved for later reference.

### Preferences File

```python
def save_preferences(user_data: dict):
    """Save wizard preferences."""
    from pathlib import Path
    from utils.atomic_write import atomic_write_json
    from datetime import datetime

    config_dir = Path.home() / ".config/neuronos"
    config_dir.mkdir(parents=True, exist_ok=True)

    preferences = {
        "setup_windows_vm": user_data.get("setup_windows_vm", False),
        "setup_macos_vm": user_data.get("setup_macos_vm", False),
        "enable_gpu_passthrough": user_data.get("gpu_passthrough", False),
        "migrate_files": user_data.get("migrate_files", False),
        "theme": user_data.get("theme", "default"),
        "completed_at": datetime.now().isoformat(),
    }

    atomic_write_json(config_dir / "preferences.json", preferences)
```

### Verification Criteria for 7.5
- [ ] Preferences saved to file
- [ ] File is valid JSON
- [ ] All selections persisted
- [ ] Readable after reboot

---

## Step 7.6: First-Boot Completion

Ensure wizard only runs once.

### Mark Complete

```python
def mark_first_boot_complete():
    """Mark first boot as complete."""
    from pathlib import Path

    flag_path = Path.home() / ".config/neuronos/first-boot-complete"
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    flag_path.touch()
```

### Remove Autostart

After completion, remove or disable the autostart:

```python
def disable_autostart():
    """Disable wizard autostart."""
    from pathlib import Path

    # Option 1: Create user override
    user_autostart = Path.home() / ".config/autostart/neuron-welcome.desktop"
    user_autostart.parent.mkdir(parents=True, exist_ok=True)

    with open(user_autostart, 'w') as f:
        f.write("""[Desktop Entry]
Type=Application
Name=NeuronOS Welcome
Hidden=true
""")
```

### Verification Criteria for 7.6
- [ ] First-boot flag created
- [ ] Wizard doesn't run again
- [ ] User can manually re-run if needed

---

## Verification Checklist

### Phase 7 is COMPLETE when ALL boxes are checked:

**First-Boot Detection**
- [ ] Correctly detects first boot
- [ ] Autostart works
- [ ] Wizard launches automatically

**Hardware Check**
- [ ] CPU detected
- [ ] GPUs detected
- [ ] IOMMU status shown
- [ ] Capability level determined
- [ ] Clear explanation for user

**VM Setup**
- [ ] Options displayed
- [ ] Selection saved
- [ ] VM creation queued

**File Migration**
- [ ] Sources detected
- [ ] User can select categories
- [ ] Files copied correctly
- [ ] Progress shown

**Preferences**
- [ ] All selections saved
- [ ] File persists across reboot

**Completion**
- [ ] First-boot marked complete
- [ ] Wizard doesn't repeat
- [ ] User can re-run manually

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 8: Theming & Polish](./PHASE_8_THEMING.md)**

Phase 8 will apply visual polish and theme customization.
