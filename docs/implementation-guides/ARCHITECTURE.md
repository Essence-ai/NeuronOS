# NeuronOS Architecture Guide

This document provides a comprehensive overview of the NeuronOS codebase structure, design patterns, and key components. Use this guide to understand how things work before diving into implementation guides.

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Modules](#core-modules)
3. [Data Flow](#data-flow)
4. [Key Classes & Interfaces](#key-classes--interfaces)
5. [Design Patterns](#design-patterns)
6. [Configuration System](#configuration-system)
7. [Common Pitfalls](#common-pitfalls)

---

## System Overview

NeuronOS achieves seamless Windows/macOS software compatibility by:

1. **VM Layer**: QEMU/KVM VMs with GPU passthrough for heavy Windows applications (Adobe, AutoCAD, etc.)
2. **Compatibility Layers**: Wine/Proton for native Windows software compatibility
3. **User Interface**: GTK4/Libadwaita GUI for VM and app management
4. **System Integration**: Hardware detection, automatic configuration, secure host-guest communication
5. **File Migration**: Bring user data from Windows/macOS installations

```
┌─────────────────────────────────────────────────────────────┐
│                  NeuronOS User Interface (GTK4)               │
├─────────────────────────────────────────────────────────────┤
│ VM Manager GUI  │  App Store   │  Settings   │  Onboarding  │
└────────┬─────────────┬─────────────┬─────────────┬──────────┘
         │             │             │             │
┌────────▼─────────────▼─────────────▼─────────────▼──────────┐
│           Application Layer (Python Backend)                 │
├─────────────────────────────────────────────────────────────┤
│ VM Manager  │ App Installer │ File Migration │ Hardware Detect│
│ Updater     │  Onboarding   │  Guest Client  │   Store       │
└────────┬──────────┬────────────┬──────────────┬──────────────┘
         │          │            │              │
┌────────▼──────────▼────────────▼──────────────▼──────────────┐
│             System Layer (libvirt, Pacman, libguestfs)        │
├─────────────────────────────────────────────────────────────┤
│ QEMU/KVM  │  Libvirt  │  Wine/Proton  │  Pacman  │  systemd │
└────────┬──────────────┬────────────────┬──────────┬──────────┘
         │              │                │          │
┌────────▼──────────────▼────────────────▼──────────▼──────────┐
│          Linux Kernel (Custom VFIO, IOMMU Config)             │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Modules

### 1. Hardware Detection (`src/hardware_detect/`)

**Purpose**: Automatically detect GPUs, IOMMU groups, and CPU capabilities. Configure kernel parameters for VFIO.

**Files**:
- `gpu_scanner.py` - Detects GPUs via lspci, groups by IOMMU
- `iommu_parser.py` - Parses /sys/kernel/iommu_groups
- `cpu_detect.py` - Detects nested virt, SVM/VMX support
- `config_generator.py` - Generates grub/modprobe config files

**Key Functions**:

```python
# Detect all GPUs on the system
gpu_list = gpu_scanner.scan_gpus()
# Returns: List[GPUInfo(vendor, device, iommu_group, pci_address)]

# Generate VFIO kernel parameters
vfio_ids = config_generator.generate_vfio_ids(gpu_list)
# Adds to grub: vfio-pci.ids=10de:2204,10de:1aef,...

# Detect IOMMU groups and conflicts
groups = iommu_parser.get_iommu_groups()
# Returns: Dict[group_id, List[devices_in_group]]
```

**Current State**: ✅ Mostly working; fallback mechanisms present

**Known Issues**:
- May incorrectly detect GPUs in single-GPU desktop systems
- IOMMU group detection fails on some AMD systems without ACS override
- No detection for SR-IOV capable devices

---

### 2. VM Manager (`src/vm_manager/`)

**Purpose**: Create, configure, start, stop, and manage QEMU/KVM virtual machines with GPU passthrough.

**Submodules**:

#### **Core VM Management** (`core/`)

**vm_creator.py** - Creates new VMs
```python
creator = VMCreator()
vm_config = VMConfig(
    name="Windows11",
    memory_gb=16,
    vcpu_count=8,
    gpus=[GPU("nvidia", pci_address="0000:01:00.0")],
    iso_path="/path/to/windows.iso",
)
creator.create_vm(vm_config)  # Renders XML template via libvirt
```

**vm_lifecycle.py** - Manages VM state
```python
lifecycle = VMLifecycle()
lifecycle.start(vm_name)      # Start VM
lifecycle.pause(vm_name)      # Pause (suspend to RAM)
lifecycle.resume(vm_name)     # Resume from pause
lifecycle.stop(vm_name)       # Graceful shutdown
lifecycle.kill(vm_name)       # Force shutdown
lifecycle.delete(vm_name)     # Remove VM and disks
```

**guest_client.py** - Host-guest communication
```python
client = GuestClient(vm_name)
# Send commands to Windows guest agent
client.set_resolution(1920, 1080)
client.launch_app("C:\\Windows\\System32\\notepad.exe")
clipboard_text = client.get_clipboard()
```

**looking_glass.py** - Manages Looking Glass display
```python
lg = LookingGlassManager()
lg.check_ivshmem_device(vm_name)  # Verify shared memory attached
lg.start(vm_name)                  # Launch Looking Glass client
```

#### **GPU Passthrough** (`passthrough/`)

**gpu_attach.py** - VFIO device binding
```python
gpu_attach = GPUAttacher()
# Unbind from host driver
gpu_attach.unbind_from_driver(pci_address)
# Bind to VFIO-PCI
gpu_attach.bind_to_vfio(pci_address)
# Return to host driver
gpu_attach.rebind_to_driver(pci_address)
```

**ivshmem.py** - Configures shared memory for Looking Glass
```python
ivshmem = IVSHMEMManager()
# Create shared memory region (512MB for high-res displays)
ivshmem.setup(vm_name, size_mb=512)
```

#### **GUI** (`gui/`)

**app.py** - Main GTK4 window (529 lines)

Key components:
```python
class VMCardWidget:  # Card showing single VM
    - VM name, status, memory/CPU/GPU
    - Start/Stop/Open buttons
    - Theme indicator

class VMManagerApp(Adw.ApplicationWindow):
    - Lists all VMs in scroll view
    - Create VM button → dialog
    - Theme selector dropdown
    - Settings button (TODO)
    - Delete button (TODO)
```

**Current State**: ⚠️ ~80% functional
- ✅ VM listing works
- ✅ Start/Stop works
- ✅ Create VM dialog works
- ❌ Delete button not implemented (TODO)
- ❌ Settings dialog not implemented (TODO)
- ⚠️ Looking Glass fallback to virt-viewer works but no clear feedback

---

### 3. Application Store (`src/store/`)

**Purpose**: Marketplace for applications with multi-layer compatibility (Native, Wine, Proton, Flatpak, VM).

**Files**:

**app_catalog.py** - Application database
```python
@dataclass
class AppInfo:
    id: str                              # "autocad"
    name: str                            # "AutoCAD 2024"
    layer: CompatibilityLayer            # NATIVE, WINE, PROTON, VM_WINDOWS
    installer_url: str                   # URL to .exe/.msi/.zip
    installer_sha256: Optional[str]      # Hash for verification
    category: str                        # "design", "productivity"
    description: str

# Load from apps.json
catalog = AppCatalog()
apps = catalog.get_apps_by_layer(CompatibilityLayer.PROTON)
```

**installer.py** - Multi-layer installer
```python
class AppInstaller:
    def install(app: AppInfo) -> bool:
        # Route to correct installer based on app.layer
        if app.layer == CompatibilityLayer.WINE:
            return WineInstaller().install(app)
        elif app.layer == CompatibilityLayer.PROTON:
            return ProtonInstaller().install(app)
        # ... etc

class WineInstaller(BaseInstaller):
    def install(app) -> bool:
        # 1. Create Wine prefix (~/.local/share/neuron-os/wine/...)
        # 2. Download .exe from app.installer_url
        # 3. Run: WINEPREFIX=/path wine installer.exe
        # 4. Create .desktop file for app launcher

class ProtonInstaller(BaseInstaller):
    def install(app) -> bool:
        # 1. Check Steam installed
        # 2. Create Proton prefix
        # 3. Configure for non-Steam games
        # 4. Download and execute via Proton
```

**Current State**: ⚠️ ~70% functional
- ✅ Wine installer complete
- ⚠️ Proton installer 80% done (missing non-Steam download logic)
- ❌ Store GUI 40% done (app listing incomplete)

---

### 4. File Migration (`src/migration/`)

**Purpose**: Migrate user data from Windows/macOS to NeuronOS.

**Files**:

**migrator.py** - Main migration engine
```python
class WindowsMigrator:
    def migrate(categories: List[FileCategory]) -> bool:
        # categories = [DOCUMENTS, PICTURES, MUSIC, SSH_KEYS, GIT_CONFIG, BROWSERS]
        # For each category:
        #   1. Detect source path (Windows volume)
        #   2. Copy to target (Linux home dir)
        #   3. Set proper permissions (esp. SSH keys)
        #   4. Handle permission errors gracefully

class FileCategory(Enum):
    DOCUMENTS = "Documents"
    PICTURES = "Pictures"
    SSH_KEYS = ".ssh"                  # BUG: Is directory but treated as file
    GIT_CONFIG = ".gitconfig"          # BUG: Is file but treated as directory
    BROWSERS = "browser_profiles"      # Firefox, Chrome profiles
```

**Current State**: ⚠️ ~60% functional
- ✅ Document/picture copying works
- ❌ **CRITICAL BUG**: SSH_KEYS and GIT_CONFIG types are confused (see Phase 1.3)
- ⚠️ Browser profile migration incomplete
- ⚠️ No file conflicts handled (e.g., ~/.gitconfig already exists)

**Common Issues**:
- Migration stuck if source permission denied
- Partial migration on error (incomplete state)
- No progress UI wired to actual migration

---

### 5. Onboarding Wizard (`src/onboarding/`)

**Purpose**: First-boot setup guiding users through hardware detection, VM creation, and file migration.

**Files**:

**wizard.py** - Main wizard window (GTK4)
```python
class OnboardingWizard(Adw.ApplicationWindow):
    # Page stack with navigation
    pages = [
        WelcomePage(),           # "Welcome to NeuronOS"
        HardwareCheckPage(),     # GPU detection
        VMSetupPage(),           # Create Windows VM
        MigrationSourcePage(),   # Select data to migrate
        MigrationProgressPage(), # Show progress
        CompletePage(),          # "Setup complete!"
    ]

    def on_wizard_complete(self):
        # CURRENTLY: Just closes wizard
        # SHOULD: Execute all the setup!
        # - Apply VFIO configuration
        # - Create Windows VM
        # - Start file migration
```

**pages.py** - Individual wizard pages
```python
class HardwareCheckPage(Adw.PreferencesPage):
    # Displays:
    # - Detected GPUs with IOMMU group
    # - CPU capabilities (nested virt)
    # - Warnings if hardware insufficient

class VMSetupPage(Adw.PreferencesPage):
    # Form to configure:
    # - VM name
    # - Memory (default 16GB)
    # - CPU cores (default 8)
    # - GPU to assign
    # - Disk size

class MigrationSourcePage(Adw.PreferencesPage):
    # Checklist of categories to migrate:
    # - Documents
    # - Pictures
    # - SSH Keys
    # - Git Config
    # - Browser profiles
```

**Current State**: ⚠️ ~60% complete
- ✅ Pages render correctly
- ✅ Navigation works
- ❌ Hardware check doesn't run detection
- ❌ VM setup doesn't create VMs
- ❌ Migration doesn't execute

---

### 6. System Updates (`src/updater/`)

**Purpose**: Update system packages with atomic rollback via snapshots.

**Files**:

**updater.py** - Main updater
```python
class SystemUpdater:
    def update(self) -> bool:
        # 1. Create pre-update snapshot (via Timeshift)
        # 2. Update system: pacman -Syu
        # 3. Verify system still works
        # 4. If failed: rollback to snapshot
        # 5. Return success/failure
```

**snapshot.py** - Timeshift integration
```python
class SnapshotManager:
    def create_snapshot(name: str, description: str) -> bool:
        # Uses Timeshift CLI to create system snapshot
        # Stores to /mnt/.snapshots/

    def list_snapshots(self) -> List[Snapshot]:
        # Parse Timeshift output

    def restore_snapshot(snapshot_id: str) -> bool:
        # Restore from snapshot
```

**rollback.py** - Recovery mode setup
```python
class RollbackManager:
    def schedule_rollback_on_boot_failure(self) -> bool:
        # 1. Write systemd service to check boot success
        # 2. If boot fails: automatically rollback on next boot
        # 3. Create GRUB recovery entry

        # ISSUE: Hardcoded GRUB paths assume /boot/grub/grub.cfg
        # ISSUE: Assumes first disk/second partition (hd0,gpt2)
```

**Current State**: ✅ ~90% functional
- ✅ Snapshot creation works
- ✅ System update works
- ❌ Hardcoded GRUB paths (see Phase 1)
- ⚠️ Missing sudo fallback for system operations

---

### 7. Guest Agent (`src/guest_agent/`)

**Purpose**: Windows service in guest VMs enabling host-guest communication for clipboard sync, resolution sync, and app launching.

**Language**: C# (.NET 7.0)

**Components**:

**NeuronGuest/Program.cs** - Main worker service
```csharp
public class NeuronGuestService : BackgroundService
{
    // Runs as Windows Service
    // Listens on virtio-serial device for commands
    // Executes commands and returns results
}
```

**Services/VirtioSerialService.cs** - Communication protocol
```csharp
public class VirtioSerialService
{
    // Listens on: \\.\COM3 (virtio-serial device)
    // Protocol: Length-prefixed JSON messages
    // Commands: PING, GET_INFO, SET_RESOLUTION, LAUNCH_APP, CLIPBOARD_*
}
```

**Services/CommandHandler.cs** - Command execution
```csharp
public class CommandHandler
{
    // Routes commands to appropriate handler:
    // - SET_RESOLUTION → WindowManager.SetResolution()
    // - LAUNCH_APP → Process.Start()
    // - CLIPBOARD_GET → Clipboard.GetText()
    // - CLIPBOARD_SET → Clipboard.SetText()
}
```

**Current State**: ❌ Won't compile
- 🔴 **CRITICAL**: Missing System.IO.Ports assembly reference (CS1069)
- ❌ No encryption/authentication (plain JSON over serial)
- ⚠️ No error handling in command execution
- ⚠️ Incomplete command routing

---

### 8. Common Utilities (`src/common/`)

**Purpose**: Shared utilities used across all modules.

**Files**:

**exceptions.py** - Custom exception hierarchy
```python
class NeuronOSError(Exception):          # Base class
class HardwareDetectionError(NeuronOSError)
class VMCreationError(NeuronOSError)
class MigrationError(NeuronOSError)
class InstallationError(NeuronOSError)
```

**decorators.py** - Common decorators
```python
@retry(max_attempts=3, backoff_ms=1000)  # Retry with exponential backoff
def flaky_operation():
    pass

@timed()  # Log function execution time
def slow_operation():
    pass

@requires_sudo()  # Check for sudo/root
def privileged_operation():
    pass
```

**singleton.py** - Thread-safe singleton pattern
```python
class SingletonMeta(type):
    # Ensures only one instance of a class exists
    # Thread-safe using locks
    _instances = {}
```

**logging_config.py** - Centralized logging
```python
def setup_logging(level=logging.INFO, log_file=None):
    # Configure root logger with both file and console handlers
    # Color output for console
    # Structured JSON for files
```

---

## Data Flow

### User Creates a Windows VM

```
1. User clicks "Create VM" in GUI
   ↓
2. VMCreationDialog opens
   - Input: VM name, RAM, CPU, GPU selection
   ↓
3. User clicks "Create"
   ↓
4. VMCreator.create_vm(config)
   ├─ Generate libvirt XML from template
   ├─ Call: virsh define vm.xml
   ├─ GPUAttacher.bind_to_vfio(gpu_pci)
   ├─ Set up IOMMU groups
   └─ Return success
   ↓
5. GUI shows "Creating..." then "Created"
   ↓
6. VM appears in card view
   ↓
7. User clicks "Start"
   ↓
8. VMLifecycle.start(vm_name)
   ├─ virsh start vm_name
   ├─ Monitor guest startup
   ├─ (Optional) Start Looking Glass client
   └─ Return when guest is booted
   ↓
9. GUI shows "Running"
   ↓
10. User clicks "Open"
    ├─ If Looking Glass available: Open LG client
    └─ Otherwise: Open virt-viewer
```

### User Installs an Application

```
1. User opens App Store GUI
   ↓
2. Store displays list of apps
   ├─ Load from apps.json catalog
   ├─ Filter by category
   └─ Show compatibility layer badge
   ↓
3. User clicks "Install" on app
   ↓
4. AppInstaller.install(app)
   ├─ Determine layer (Wine, Proton, VM, etc.)
   └─ Route to appropriate installer:
      ├─ WineInstaller.install()
      │  ├─ Create prefix: WINEPREFIX=~/.neuron-os/wine/app_id
      │  ├─ Download installer from URL
      │  ├─ Run: wine installer.exe
      │  ├─ Create .desktop launcher
      │  └─ Add to system application menu
      │
      ├─ ProtonInstaller.install()
      │  ├─ Check Steam installed
      │  ├─ Create Proton prefix
      │  ├─ Download .exe
      │  ├─ Run via Proton
      │  └─ Create launcher
      │
      └─ VMInstaller.install()
         ├─ Launch app in Windows VM guest
         └─ Return when installed
   ↓
5. GUI shows "Installation complete"
   ↓
6. App launcher appears in application menu
```

### User Migrates Files from Windows

```
1. User boots NeuronOS with Windows partition mounted
   ↓
2. Onboarding wizard shows "Migration" page
   ↓
3. User selects categories: [Documents, Pictures, SSH Keys]
   ↓
4. Migrator.migrate(categories)
   ├─ For each category:
   │  ├─ Detect source path (Windows partition)
   │  ├─ Create target directory
   │  ├─ Copy files recursively
   │  ├─ Set permissions (esp. SSH keys: 600)
   │  └─ Report errors
   ↓
5. Progress bar updates
   ↓
6. Migration complete or errors shown
```

---

## Key Classes & Interfaces

### Base Classes

```python
# src/common/exceptions.py
class NeuronOSError(Exception):
    """Base exception for all NeuronOS operations"""

# src/store/installer.py
class BaseInstaller(ABC):
    """Interface that all installers implement"""

    @abstractmethod
    def install(self, app: AppInfo) -> bool:
        """Install application. Return True if successful."""
        pass

    @abstractmethod
    def uninstall(self, app_id: str) -> bool:
        """Remove installed application."""
        pass
```

### Main Classes

| Class | File | Purpose |
|-------|------|---------|
| `GPUScanner` | `hardware_detect/gpu_scanner.py` | Detect GPUs via lspci |
| `IMOMUParser` | `hardware_detect/iommu_parser.py` | Parse IOMMU groups |
| `VMCreator` | `vm_manager/core/vm_creator.py` | Create new VMs |
| `VMLifecycle` | `vm_manager/core/vm_lifecycle.py` | Manage VM state |
| `GuestClient` | `vm_manager/core/guest_client.py` | Talk to guest agent |
| `VMManagerApp` | `vm_manager/gui/app.py` | Main GTK4 window |
| `AppCatalog` | `store/app_catalog.py` | App database |
| `AppInstaller` | `store/installer.py` | Route installations |
| `WineInstaller` | `store/installer.py` | Wine layer |
| `ProtonInstaller` | `store/installer.py` | Proton/Steam layer |
| `WindowsMigrator` | `migration/migrator.py` | Migrate from Windows |
| `OnboardingWizard` | `onboarding/wizard.py` | First-boot setup |
| `SystemUpdater` | `updater/updater.py` | System updates |
| `SnapshotManager` | `updater/snapshot.py` | Timeshift integration |

---

## Design Patterns

### 1. Factory Pattern (Installers)

```python
class AppInstaller:
    def install(self, app: AppInfo) -> bool:
        # Factory pattern: route to correct installer
        installer = self._get_installer_for_layer(app.layer)
        return installer.install(app)

    def _get_installer_for_layer(self, layer: CompatibilityLayer) -> BaseInstaller:
        installers = {
            CompatibilityLayer.NATIVE: PacmanInstaller(),
            CompatibilityLayer.WINE: WineInstaller(),
            CompatibilityLayer.PROTON: ProtonInstaller(),
            # ... etc
        }
        return installers[layer]
```

### 2. Singleton Pattern (Managers)

```python
from src.common.singleton import SingletonMeta

class VMManager(metaclass=SingletonMeta):
    """Only one instance of VM manager exists in process"""
    pass

# Usage:
vm_mgr1 = VMManager()
vm_mgr2 = VMManager()
assert vm_mgr1 is vm_mgr2  # Same object!
```

### 3. Strategy Pattern (Hardware Detection)

```python
class HardwareDetector:
    """Different detection strategies based on system"""

    def detect_gpus(self) -> List[GPU]:
        # Strategy 1: Try lspci
        # Strategy 2: Fall back to /sys/class/drm
        # Strategy 3: Fall back to /proc/devices
```

### 4. State Machine (VM Lifecycle)

```python
# VM states: UNKNOWN → DEFINED → RUNNING → PAUSED → SHUTDOWN → DESTROYED
class VMLifecycle:
    # Each operation validates current state before proceeding
    def start(self, vm_name):
        if self.get_state(vm_name) not in [UNDEFINED, SHUTDOWN]:
            raise InvalidStateError()
        # Proceed with start
```

### 5. Observer Pattern (Progress Callbacks)

```python
class Migrator:
    def migrate(self, on_progress: Callable[[MigrationProgress], None]):
        # Call callback as migration progresses
        self.progress = MigrationProgress(0, total_files)
        on_progress(self.progress)  # Notify UI

        # ... copy files ...

        self.progress.files_done += 1
        on_progress(self.progress)  # Update UI
```

---

## Configuration System

### VM Configuration Templates

VM configs are rendered from Jinja2 templates in `src/vm_manager/templates/`:

```jinja2
{# libvirt domain XML template #}
<domain type='kvm'>
  <name>{{ vm_name }}</name>
  <memory unit='GiB'>{{ memory_gb }}</memory>
  <vcpu>{{ vcpu_count }}</vcpu>

  {% for gpu in gpus %}
  <hostdev mode='subsystem' type='pci' managed='yes'>
    <source>
      <address domain='0x{{ gpu.pci_domain }}' bus='0x{{ gpu.pci_bus }}' .../>
    </source>
  </hostdev>
  {% endfor %}

  {# Looking Glass shared memory #}
  {% if use_looking_glass %}
  <device>
    <shmem name='ivshmem'>
      <model type='ivshmem-plain'/>
      <size unit='MB'>{{ ivshmem_size_mb }}</size>
    </shmem>
  </device>
  {% endif %}
</domain>
```

### Application Catalog

Located in `data/apps.json`:

```json
{
  "apps": [
    {
      "id": "autocad",
      "name": "AutoCAD 2024",
      "layer": "VM_WINDOWS",
      "installer_url": "https://...",
      "installer_sha256": "abc123...",
      "category": "design",
      "description": "Professional CAD software"
    },
    {
      "id": "vlc",
      "name": "VLC Media Player",
      "layer": "PROTON",
      "installer_url": "https://...",
      "category": "media"
    }
  ]
}
```

---

## Common Pitfalls

### 1. Forgetting Nested Calls in Lifecycle

```python
# ❌ WRONG: Calling method without returning
def start(self):
    self.verify_hardware()  # Returns bool but we ignore it
    self.create_vm()        # Runs even if verification failed

# ✅ RIGHT: Check return values
def start(self):
    if not self.verify_hardware():
        raise HardwareError("Hardware check failed")
    if not self.create_vm():
        raise VMCreationError("Failed to create VM")
```

### 2. Not Handling Exception in Permission Operations

```python
# ❌ WRONG: Fails if not root
def write_grub_config(self):
    with open("/etc/grub.d/50_my_config", "w") as f:
        f.write(config)

# ✅ RIGHT: Fallback to sudo
def write_grub_config(self):
    try:
        with open("/etc/grub.d/50_my_config", "w") as f:
            f.write(config)
    except PermissionError:
        subprocess.run(["sudo", "tee", "/etc/grub.d/50_my_config"],
                      input=config.encode(), check=True)
```

### 3. Not Validating File Paths

```python
# ❌ WRONG: Path traversal vulnerability
def download(self, url, dest_dir):
    filename = url.split("/")[-1]  # "../../etc/passwd"
    path = Path(dest_dir) / filename
    # Writes to /etc/passwd!

# ✅ RIGHT: Validate path
def download(self, url, dest_dir):
    filename = _safe_filename(url)
    path = Path(dest_dir) / filename
    # Verify path is within dest_dir
    path.resolve().relative_to(Path(dest_dir).resolve())
```

### 4. Assuming File vs Directory

```python
# ❌ WRONG: Assuming all sources are directories
def copy_category(self, source_path):
    for item in source_path.iterdir():  # Fails if source is a file!
        shutil.copy2(item, target)

# ✅ RIGHT: Check type first
def copy_category(self, source_path):
    if source_path.is_file():
        shutil.copy2(source_path, target)
    elif source_path.is_dir():
        for item in source_path.iterdir():
            shutil.copy2(item, target)
```

### 5. Hardcoding Paths

```python
# ❌ WRONG: Assumes specific drive/partition
kernel = "/boot/vmlinuz-linux"  # What if /boot is on different partition?
grub_device = "hd0,gpt2"        # Wrong on NVMe or MBR systems

# ✅ RIGHT: Detect dynamically
kernel = find_kernel_dynamically()  # Check /boot/vmlinuz*
grub_device = detect_grub_device()  # Parse current root device
```

---

## Quick Reference: Module Dependencies

```
┌─────────────────────────────────────────┐
│         GUI Layer (gtk4/adwaita)        │
├─────────────────────────────────────────┤
│ vm_manager.gui ← depends on ↓
├─────────────────────────────────────────┤
│  vm_manager      store       onboarding │
│       ↓          ↓              ↓        │
├────────────────┬──────────┬────────────┤
│ hardware_      │migration │  updater   │
│ detect         │          │            │
├─────────────────────────────────────────┤
│        common (exceptions, logging)     │
├─────────────────────────────────────────┤
│   System Layer (libvirt, pacman, etc)   │
└─────────────────────────────────────────┘
```

**Key Dependencies**:
- Everything depends on `src/common/`
- `vm_manager/gui` depends on all backend modules
- `store` is independent (except common)
- `migration` is independent (except common)
- `updater` is independent (except common)

---

## Where to Find Things

| Need | Location |
|------|----------|
| Add new GPU type | `src/hardware_detect/gpu_scanner.py` |
| Add new app | `data/apps.json` |
| Add new installer | `src/store/installer.py` (subclass `BaseInstaller`) |
| Add new wizard page | `src/onboarding/pages.py` |
| Add new compatibility layer | `src/common/exceptions.py` + router in `src/store/installer.py` |
| Fix GUI bug | `src/vm_manager/gui/app.py` |
| Fix VM creation | `src/vm_manager/core/vm_creator.py` |
| Add system integration | `src/hardware_detect/config_generator.py` |

Good luck with the implementation! 🚀
