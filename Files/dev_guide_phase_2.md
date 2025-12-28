# NeuronOS Dev Guide: Phase 2 — The NeuronVM Manager

**Duration:** 8 Weeks (Weeks 9-16 / Days 57-112)
**Developers Required:** 2
**Goal:** Build the GUI application that manages Windows VMs and provides the "native app" experience.

> [!IMPORTANT]
> **Prerequisites:** Phase 1 must be complete. You must have a working NeuronOS ISO that auto-configures VFIO.

---

## Sprint 1: VM Backend Library (Week 9-10 / Days 57-70)

---

### Week 9, Day 57-59: Project Setup & Architecture

#### 🎫 Story 2.1.1: Backend Architecture
**As a** Developer,
**I want** a clean Python library for VM management,
**So that** the UI can be developed independently.

**Acceptance Criteria:**
- [ ] Python package structure created.
- [ ] Virtual environment configured.
- [ ] Basic libvirt connection works.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📁 Create | Create project structure | See structure below |
| 2 | 🐍 Setup | Create virtual environment | `python -m venv venv` |
| 3 | 📝 Create | Create requirements.txt | List dependencies |
| 4 | 📦 Install | Install dependencies | `pip install -r requirements.txt` |
| 5 | 📝 Code | Create base connection class | `libvirt_manager.py` |
| 6 | 🧪 Test | Test libvirt connection | Connect to `qemu:///system` |

**Project Structure:**
```
neuron-vm-manager/
├── neuron_vm/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── libvirt_manager.py    # libvirt connection handling
│   │   ├── vm_profile.py         # VM configuration profiles
│   │   └── passthrough.py        # GPU passthrough logic
│   ├── templates/
│   │   └── windows11.xml.j2      # Jinja2 VM template
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── vm_card.py
│   │   └── settings_dialog.py
│   └── utils/
│       ├── __init__.py
│       └── looking_glass.py      # LG client launcher
├── tests/
│   ├── test_libvirt.py
│   └── test_profiles.py
├── data/
│   ├── icons/
│   └── styles/
├── requirements.txt
├── setup.py
└── README.md
```

**requirements.txt:**
```
libvirt-python>=9.0.0
PyGObject>=3.42.0
Jinja2>=3.1.0
pydbus>=0.6.0
pytest>=7.0.0
```

---

### Week 9, Day 60-63: Libvirt Connection Manager

#### 🎫 Story 2.1.2: VM Control API
**As a** UI Developer,
**I want** simple Python methods to control VMs,
**So that** I can focus on the interface.

**Acceptance Criteria:**
- [ ] Can list all VMs.
- [ ] Can start/stop VMs.
- [ ] Can get VM status (running/stopped/paused).
- [ ] Handles connection errors gracefully.

**libvirt_manager.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS VM Manager - Libvirt Connection Manager
Provides high-level API for VM management.
"""

import libvirt
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Callable
from pathlib import Path


class VMState(Enum):
    """VM power states."""
    UNKNOWN = 0
    RUNNING = 1
    BLOCKED = 2
    PAUSED = 3
    SHUTDOWN = 4
    SHUTOFF = 5
    CRASHED = 6
    SUSPENDED = 7


@dataclass
class VMInfo:
    """Information about a virtual machine."""
    name: str
    uuid: str
    state: VMState
    memory_mb: int
    vcpus: int
    is_persistent: bool
    has_gpu_passthrough: bool


class LibvirtConnectionError(Exception):
    """Raised when libvirt connection fails."""
    pass


class VMOperationError(Exception):
    """Raised when a VM operation fails."""
    pass


class LibvirtManager:
    """
    Manages connection to libvirt and VM operations.
    
    Usage:
        manager = LibvirtManager()
        manager.connect()
        vms = manager.list_vms()
        manager.start_vm("windows-11")
    """
    
    DEFAULT_URI = "qemu:///system"
    
    def __init__(self, uri: str = None):
        self.uri = uri or self.DEFAULT_URI
        self._conn: Optional[libvirt.virConnect] = None
        self._event_callbacks: List[Callable] = []
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to libvirt."""
        if self._conn is None:
            return False
        try:
            self._conn.getLibVersion()
            return True
        except libvirt.libvirtError:
            return False
    
    def connect(self) -> None:
        """Establish connection to libvirt daemon."""
        try:
            self._conn = libvirt.open(self.uri)
            if self._conn is None:
                raise LibvirtConnectionError(f"Failed to connect to {self.uri}")
        except libvirt.libvirtError as e:
            raise LibvirtConnectionError(f"Connection error: {e}")
    
    def disconnect(self) -> None:
        """Close libvirt connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def _require_connection(self) -> None:
        """Ensure we're connected."""
        if not self.is_connected:
            raise LibvirtConnectionError("Not connected to libvirt")
    
    def list_vms(self, include_inactive: bool = True) -> List[VMInfo]:
        """List all VMs."""
        self._require_connection()
        
        vms = []
        
        # Get all domains
        flags = 0
        if include_inactive:
            flags = libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE | \
                    libvirt.VIR_CONNECT_LIST_DOMAINS_INACTIVE
        
        domains = self._conn.listAllDomains(flags)
        
        for domain in domains:
            info = self._domain_to_info(domain)
            vms.append(info)
        
        return vms
    
    def _domain_to_info(self, domain: libvirt.virDomain) -> VMInfo:
        """Convert libvirt domain to VMInfo."""
        state, _ = domain.state()
        
        # Check for GPU passthrough
        xml = domain.XMLDesc()
        has_gpu = "<hostdev mode='subsystem' type='pci'" in xml
        
        return VMInfo(
            name=domain.name(),
            uuid=domain.UUIDString(),
            state=VMState(state),
            memory_mb=domain.maxMemory() // 1024,
            vcpus=domain.maxVcpus(),
            is_persistent=domain.isPersistent(),
            has_gpu_passthrough=has_gpu
        )
    
    def get_vm(self, name: str) -> Optional[VMInfo]:
        """Get info for a specific VM by name."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            return self._domain_to_info(domain)
        except libvirt.libvirtError:
            return None
    
    def start_vm(self, name: str) -> None:
        """Start a VM."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            if domain.isActive():
                return  # Already running
            domain.create()
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to start {name}: {e}")
    
    def stop_vm(self, name: str, force: bool = False) -> None:
        """Stop a VM (shutdown or destroy)."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            if not domain.isActive():
                return  # Already stopped
            
            if force:
                domain.destroy()
            else:
                domain.shutdown()
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to stop {name}: {e}")
    
    def pause_vm(self, name: str) -> None:
        """Pause a running VM."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            domain.suspend()
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to pause {name}: {e}")
    
    def resume_vm(self, name: str) -> None:
        """Resume a paused VM."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            domain.resume()
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to resume {name}: {e}")
    
    def create_snapshot(self, name: str, snapshot_name: str) -> None:
        """Create a VM snapshot."""
        self._require_connection()
        
        try:
            domain = self._conn.lookupByName(name)
            
            # Create snapshot XML
            snap_xml = f"""
            <domainsnapshot>
                <name>{snapshot_name}</name>
                <description>NeuronOS auto-snapshot</description>
            </domainsnapshot>
            """
            
            domain.snapshotCreateXML(snap_xml)
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to create snapshot: {e}")
    
    def define_vm_from_template(self, template_path: Path, config: dict) -> str:
        """Create a new VM from a Jinja2 template."""
        self._require_connection()
        
        from jinja2 import Environment, FileSystemLoader
        
        env = Environment(loader=FileSystemLoader(template_path.parent))
        template = env.get_template(template_path.name)
        
        xml = template.render(**config)
        
        try:
            domain = self._conn.defineXML(xml)
            return domain.name()
        except libvirt.libvirtError as e:
            raise VMOperationError(f"Failed to define VM: {e}")


# Context manager support
class LibvirtContext:
    """Context manager for libvirt connections."""
    
    def __init__(self, uri: str = None):
        self.manager = LibvirtManager(uri)
    
    def __enter__(self) -> LibvirtManager:
        self.manager.connect()
        return self.manager
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.manager.disconnect()
        return False


# CLI for testing
if __name__ == "__main__":
    print("=== NeuronOS Libvirt Manager Test ===\n")
    
    with LibvirtContext() as manager:
        print("✅ Connected to libvirt")
        
        vms = manager.list_vms()
        print(f"\nFound {len(vms)} VMs:")
        
        for vm in vms:
            gpu_icon = "🎮" if vm.has_gpu_passthrough else "💻"
            state_icon = "🟢" if vm.state == VMState.RUNNING else "🔴"
            print(f"  {state_icon} {gpu_icon} {vm.name}")
            print(f"      Memory: {vm.memory_mb}MB, vCPUs: {vm.vcpus}")
            print(f"      State: {vm.state.name}")
```

---

### Week 10, Day 64-67: VM Profile System

#### 🎫 Story 2.1.3: Application Profiles
**As a** User,
**I want** to configure VMs for specific applications (Adobe, Office),
**So that** the system is optimized for each use case.

**Acceptance Criteria:**
- [ ] Can create/edit/delete profiles.
- [ ] Profiles stored as JSON files.
- [ ] Profiles include: RAM, CPU, GPU binding, startup apps.

**vm_profile.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS VM Manager - VM Profile System
Manages application-specific VM configurations.
"""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional
from enum import Enum


class ProfileType(Enum):
    """Types of VM profiles."""
    GENERAL = "general"
    CREATIVE = "creative"     # Adobe, DaVinci
    PRODUCTIVITY = "productivity"  # Office, Business apps
    GAMING = "gaming"
    DEVELOPMENT = "development"


@dataclass
class GPUPassthroughConfig:
    """GPU passthrough settings."""
    enabled: bool = True
    pci_address: str = ""           # e.g., "0000:01:00.0"
    vendor_id: str = ""
    device_id: str = ""
    include_audio: bool = True
    audio_pci_address: str = ""


@dataclass
class ResourceConfig:
    """VM resource allocation."""
    memory_mb: int = 16384           # 16 GB
    vcpus: int = 8
    cpu_pinning: List[int] = field(default_factory=list)
    hugepages: bool = True


@dataclass
class DisplayConfig:
    """Display/Looking Glass settings."""
    use_looking_glass: bool = True
    fullscreen: bool = False
    borderless: bool = True
    ivshmem_size_mb: int = 64


@dataclass
class StartupConfig:
    """Auto-start applications."""
    auto_start_vm: bool = False
    startup_apps: List[str] = field(default_factory=list)  # e.g., ["photoshop.exe"]
    kiosk_mode: bool = False         # Single-app mode


@dataclass
class VMProfile:
    """Complete VM profile configuration."""
    name: str
    display_name: str
    description: str
    profile_type: ProfileType
    icon: str = "application-x-executable"
    
    # Sub-configurations
    gpu: GPUPassthroughConfig = field(default_factory=GPUPassthroughConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    
    # Windows paths
    windows_iso_path: str = ""
    virtio_iso_path: str = ""
    disk_image_path: str = ""
    disk_size_gb: int = 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['profile_type'] = self.profile_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VMProfile':
        """Create from dictionary."""
        data['profile_type'] = ProfileType(data['profile_type'])
        data['gpu'] = GPUPassthroughConfig(**data['gpu'])
        data['resources'] = ResourceConfig(**data['resources'])
        data['display'] = DisplayConfig(**data['display'])
        data['startup'] = StartupConfig(**data['startup'])
        return cls(**data)


class ProfileManager:
    """Manages VM profile storage and retrieval."""
    
    PROFILES_DIR = Path.home() / ".config" / "neuron-vm" / "profiles"
    
    def __init__(self):
        self.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    def list_profiles(self) -> List[VMProfile]:
        """List all saved profiles."""
        profiles = []
        for file in self.PROFILES_DIR.glob("*.json"):
            try:
                profile = self.load_profile(file.stem)
                profiles.append(profile)
            except Exception:
                continue
        return profiles
    
    def save_profile(self, profile: VMProfile) -> None:
        """Save a profile to disk."""
        path = self.PROFILES_DIR / f"{profile.name}.json"
        with open(path, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)
    
    def load_profile(self, name: str) -> VMProfile:
        """Load a profile from disk."""
        path = self.PROFILES_DIR / f"{name}.json"
        with open(path) as f:
            data = json.load(f)
        return VMProfile.from_dict(data)
    
    def delete_profile(self, name: str) -> None:
        """Delete a profile."""
        path = self.PROFILES_DIR / f"{name}.json"
        path.unlink(missing_ok=True)
    
    def create_default_profiles(self) -> None:
        """Create default starter profiles."""
        
        adobe_profile = VMProfile(
            name="adobe-creative",
            display_name="Adobe Creative Suite",
            description="Optimized for Photoshop, Premiere Pro, After Effects",
            profile_type=ProfileType.CREATIVE,
            icon="applications-graphics",
            resources=ResourceConfig(
                memory_mb=32768,  # 32 GB
                vcpus=12,
                hugepages=True
            ),
            display=DisplayConfig(
                use_looking_glass=True,
                borderless=True
            ),
            disk_size_gb=200
        )
        
        office_profile = VMProfile(
            name="office-productivity",
            display_name="Microsoft Office",
            description="Word, Excel, PowerPoint, Outlook",
            profile_type=ProfileType.PRODUCTIVITY,
            icon="applications-office",
            resources=ResourceConfig(
                memory_mb=8192,  # 8 GB is enough
                vcpus=4,
                hugepages=False
            ),
            display=DisplayConfig(
                use_looking_glass=True,
                borderless=True
            ),
            disk_size_gb=60
        )
        
        gaming_profile = VMProfile(
            name="gaming",
            display_name="Windows Gaming",
            description="High-performance gaming setup",
            profile_type=ProfileType.GAMING,
            icon="applications-games",
            resources=ResourceConfig(
                memory_mb=16384,
                vcpus=8,
                hugepages=True
            ),
            display=DisplayConfig(
                use_looking_glass=True,
                fullscreen=True
            ),
            disk_size_gb=500
        )
        
        for profile in [adobe_profile, office_profile, gaming_profile]:
            self.save_profile(profile)


if __name__ == "__main__":
    manager = ProfileManager()
    
    # Create defaults
    manager.create_default_profiles()
    
    # List all
    profiles = manager.list_profiles()
    print("=== VM Profiles ===\n")
    for p in profiles:
        print(f"📁 {p.display_name}")
        print(f"   Type: {p.profile_type.value}")
        print(f"   RAM: {p.resources.memory_mb}MB, vCPUs: {p.resources.vcpus}")
        print()
```

---

## Sprint 2: GTK4 User Interface (Week 11-12 / Days 71-84)

---

### Week 11, Day 71-74: Main Window & Layout

#### 🎫 Story 2.2.1: Application Shell
**As a** User,
**I want** a clean, modern application window,
**So that** managing VMs feels native to Linux.

**Acceptance Criteria:**
- [ ] Window follows GNOME HIG (Human Interface Guidelines).
- [ ] Header bar with title and controls.
- [ ] Sidebar for navigation.
- [ ] Main content area for VM cards.

**main_window.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS VM Manager - Main Window
GTK4/Adwaita application shell.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from ..core.libvirt_manager import LibvirtManager, VMState
from ..core.vm_profile import ProfileManager
from .vm_card import VMCard


class NeuronVMWindow(Adw.ApplicationWindow):
    """Main application window."""
    
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="NeuronOS VM Manager")
        
        self.set_default_size(900, 600)
        
        # Initialize backends
        self.libvirt = LibvirtManager()
        self.profiles = ProfileManager()
        
        # Build UI
        self._build_ui()
        
        # Connect to libvirt
        self._connect_libvirt()
        
        # Refresh VM list
        self._refresh_vms()
    
    def _build_ui(self):
        """Build the user interface."""
        
        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.main_box)
        
        # Header Bar
        self.header = Adw.HeaderBar()
        self.main_box.append(self.header)
        
        # Title
        self.title_widget = Adw.WindowTitle(
            title="NeuronOS",
            subtitle="VM Manager"
        )
        self.header.set_title_widget(self.title_widget)
        
        # Refresh button
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Refresh VMs")
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        self.header.pack_start(self.refresh_btn)
        
        # Settings button
        self.settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        self.settings_btn.set_tooltip_text("Settings")
        self.header.pack_end(self.settings_btn)
        
        # New VM button
        self.new_vm_btn = Gtk.Button(icon_name="list-add-symbolic")
        self.new_vm_btn.set_tooltip_text("Create New VM")
        self.new_vm_btn.add_css_class("suggested-action")
        self.new_vm_btn.connect("clicked", self._on_new_vm_clicked)
        self.header.pack_end(self.new_vm_btn)
        
        # Content area with navigation
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.content_box.set_vexpand(True)
        self.main_box.append(self.content_box)
        
        # Sidebar
        self._build_sidebar()
        
        # Main content - scrollable grid of VM cards
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_hexpand(True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.content_box.append(self.scroll)
        
        # Clamp for content width
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(1200)
        self.scroll.set_child(self.clamp)
        
        # VM Cards container
        self.vm_grid = Gtk.FlowBox()
        self.vm_grid.set_valign(Gtk.Align.START)
        self.vm_grid.set_max_children_per_line(3)
        self.vm_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.vm_grid.set_margin_start(20)
        self.vm_grid.set_margin_end(20)
        self.vm_grid.set_margin_top(20)
        self.vm_grid.set_margin_bottom(20)
        self.vm_grid.set_column_spacing(20)
        self.vm_grid.set_row_spacing(20)
        self.clamp.set_child(self.vm_grid)
        
        # Status bar
        self._build_status_bar()
    
    def _build_sidebar(self):
        """Build navigation sidebar."""
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.set_size_request(200, -1)
        self.sidebar.add_css_class("sidebar")
        self.content_box.append(self.sidebar)
        
        # Sidebar separator
        self.content_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        
        # Navigation items
        nav_items = [
            ("All VMs", "computer-symbolic"),
            ("Running", "media-playback-start-symbolic"),
            ("Profiles", "folder-symbolic"),
        ]
        
        for label, icon in nav_items:
            btn = Gtk.Button()
            btn.add_css_class("flat")
            
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.append(Gtk.Image.new_from_icon_name(icon))
            box.append(Gtk.Label(label=label, xalign=0))
            btn.set_child(box)
            
            self.sidebar.append(btn)
    
    def _build_status_bar(self):
        """Build bottom status bar."""
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.status_bar.set_margin_start(10)
        self.status_bar.set_margin_end(10)
        self.status_bar.set_margin_top(5)
        self.status_bar.set_margin_bottom(5)
        self.main_box.append(self.status_bar)
        
        self.status_label = Gtk.Label(label="Connecting to libvirt...")
        self.status_label.set_xalign(0)
        self.status_bar.append(self.status_label)
    
    def _connect_libvirt(self):
        """Connect to libvirt daemon."""
        try:
            self.libvirt.connect()
            self.status_label.set_text("✅ Connected to libvirt")
        except Exception as e:
            self.status_label.set_text(f"❌ {str(e)}")
    
    def _refresh_vms(self):
        """Refresh the VM list."""
        # Clear existing cards
        while child := self.vm_grid.get_first_child():
            self.vm_grid.remove(child)
        
        # Get VMs
        try:
            vms = self.libvirt.list_vms()
            
            for vm in vms:
                card = VMCard(vm, self.libvirt)
                self.vm_grid.append(card)
            
            self.status_label.set_text(f"✅ {len(vms)} VMs found")
            
        except Exception as e:
            self.status_label.set_text(f"❌ Error: {str(e)}")
    
    def _on_refresh_clicked(self, button):
        """Handle refresh button click."""
        self._refresh_vms()
    
    def _on_new_vm_clicked(self, button):
        """Handle new VM button click."""
        # TODO: Open new VM dialog
        pass


class NeuronVMApp(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(
            application_id="org.neuronos.VMManager",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
    
    def do_activate(self):
        """Called when the application is activated."""
        win = NeuronVMWindow(self)
        win.present()


def main():
    """Application entry point."""
    app = NeuronVMApp()
    app.run(None)


if __name__ == "__main__":
    main()
```

---

### Week 11-12, Day 75-84: VM Card Component

#### 🎫 Story 2.2.2: VM Control Card
**As a** User,
**I want** visual cards showing each VM with quick actions,
**So that** I can manage VMs at a glance.

**Acceptance Criteria:**
- [ ] Card shows VM name, status, resources.
- [ ] Start/Stop buttons work.
- [ ] "Launch App Mode" opens Looking Glass.
- [ ] Status updates in real-time.

**vm_card.py:**
```python
#!/usr/bin/env python3
"""
NeuronOS VM Manager - VM Card Component
Individual VM control card widget.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

import subprocess
from ..core.libvirt_manager import LibvirtManager, VMInfo, VMState


class VMCard(Gtk.FlowBoxChild):
    """A card widget representing a single VM."""
    
    def __init__(self, vm_info: VMInfo, manager: LibvirtManager):
        super().__init__()
        
        self.vm = vm_info
        self.manager = manager
        
        self._build_ui()
        
        # Start status polling
        GLib.timeout_add_seconds(2, self._update_status)
    
    def _build_ui(self):
        """Build card UI."""
        # Card container
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("card")
        self.card.set_size_request(280, -1)
        self.set_child(self.card)
        
        # Header with icon and status
        self.header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.header.set_margin_start(15)
        self.header.set_margin_end(15)
        self.header.set_margin_top(15)
        self.card.append(self.header)
        
        # VM Icon
        icon_name = "computer-symbolic" if not self.vm.has_gpu_passthrough else "video-display-symbolic"
        self.icon = Gtk.Image.new_from_icon_name(icon_name)
        self.icon.set_pixel_size(48)
        self.header.append(self.icon)
        
        # Title and subtitle
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title_box.set_hexpand(True)
        self.header.append(title_box)
        
        self.title = Gtk.Label(label=self.vm.name)
        self.title.add_css_class("title-3")
        self.title.set_xalign(0)
        title_box.append(self.title)
        
        self.subtitle = Gtk.Label(label=f"{self.vm.memory_mb}MB RAM • {self.vm.vcpus} vCPUs")
        self.subtitle.add_css_class("dim-label")
        self.subtitle.set_xalign(0)
        title_box.append(self.subtitle)
        
        # Status indicator
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.header.append(self.status_box)
        
        self.status_dot = Gtk.Label(label="●")
        self.status_label = Gtk.Label()
        self.status_box.append(self.status_dot)
        self.status_box.append(self.status_label)
        
        self._update_status_display()
        
        # Separator
        self.card.append(Gtk.Separator())
        
        # GPU Badge (if applicable)
        if self.vm.has_gpu_passthrough:
            badge_box = Gtk.Box()
            badge_box.set_margin_start(15)
            badge_box.set_margin_top(10)
            
            badge = Gtk.Label(label="🎮 GPU Passthrough")
            badge.add_css_class("accent")
            badge_box.append(badge)
            
            self.card.append(badge_box)
        
        # Action buttons
        self.actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.actions.set_margin_start(15)
        self.actions.set_margin_end(15)
        self.actions.set_margin_top(15)
        self.actions.set_margin_bottom(15)
        self.actions.set_halign(Gtk.Align.END)
        self.card.append(self.actions)
        
        # Power button
        self.power_btn = Gtk.Button()
        self.power_btn.connect("clicked", self._on_power_clicked)
        self.actions.append(self.power_btn)
        
        # Launch button (Looking Glass)
        self.launch_btn = Gtk.Button(label="Launch")
        self.launch_btn.add_css_class("suggested-action")
        self.launch_btn.connect("clicked", self._on_launch_clicked)
        self.actions.append(self.launch_btn)
        
        self._update_buttons()
    
    def _update_status_display(self):
        """Update status indicator colors and text."""
        state = self.vm.state
        
        if state == VMState.RUNNING:
            self.status_dot.remove_css_class("error")
            self.status_dot.add_css_class("success")
            self.status_label.set_text("Running")
        elif state == VMState.PAUSED:
            self.status_dot.remove_css_class("success")
            self.status_dot.remove_css_class("error")
            self.status_dot.add_css_class("warning")
            self.status_label.set_text("Paused")
        else:
            self.status_dot.remove_css_class("success")
            self.status_dot.add_css_class("error")
            self.status_label.set_text("Stopped")
    
    def _update_buttons(self):
        """Update button states based on VM state."""
        is_running = self.vm.state == VMState.RUNNING
        
        if is_running:
            self.power_btn.set_icon_name("media-playback-stop-symbolic")
            self.power_btn.set_tooltip_text("Stop VM")
            self.power_btn.remove_css_class("suggested-action")
            self.power_btn.add_css_class("destructive-action")
        else:
            self.power_btn.set_icon_name("media-playback-start-symbolic")
            self.power_btn.set_tooltip_text("Start VM")
            self.power_btn.remove_css_class("destructive-action")
            self.power_btn.add_css_class("suggested-action")
        
        self.launch_btn.set_sensitive(is_running)
    
    def _update_status(self) -> bool:
        """Poll and update VM status."""
        try:
            updated = self.manager.get_vm(self.vm.name)
            if updated:
                self.vm = updated
                self._update_status_display()
                self._update_buttons()
        except Exception:
            pass
        
        return True  # Continue polling
    
    def _on_power_clicked(self, button):
        """Handle power button click."""
        try:
            if self.vm.state == VMState.RUNNING:
                self.manager.stop_vm(self.vm.name)
            else:
                self.manager.start_vm(self.vm.name)
            
            # Immediate refresh
            GLib.timeout_add(500, self._update_status)
            
        except Exception as e:
            dialog = Adw.MessageDialog(
                transient_for=self.get_root(),
                heading="Error",
                body=str(e)
            )
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def _on_launch_clicked(self, button):
        """Launch Looking Glass client."""
        if self.vm.state != VMState.RUNNING:
            return
        
        # Launch Looking Glass
        try:
            subprocess.Popen([
                "looking-glass-client",
                "-F",         # Fullscreen
                "-m", "97",   # Escape key mapping
            ])
        except FileNotFoundError:
            dialog = Adw.MessageDialog(
                transient_for=self.get_root(),
                heading="Looking Glass Not Found",
                body="Please install looking-glass-client"
            )
            dialog.add_response("ok", "OK")
            dialog.present()
```

---

## Sprint 3: NeuronGuest Agent (Week 13-14 / Days 85-98)

---

### Week 13, Day 85-91: Windows Guest Agent

#### 🎫 Story 2.3.1: Dynamic Resolution Service
**As a** User,
**I want** the Windows resolution to automatically match my Looking Glass window,
**So that** the experience feels native.

**Acceptance Criteria:**
- [ ] Windows service runs at startup.
- [ ] Listens for resize commands.
- [ ] Changes Windows display resolution via API.
- [ ] Silent operation (no UI).

**NeuronGuest (C# .NET 8 Worker Service):**

**Project Structure:**
```
NeuronGuest/
├── NeuronGuest.csproj
├── Program.cs
├── Worker.cs
├── DisplayManager.cs
├── CommandListener.cs
└── appsettings.json
```

**NeuronGuest.csproj:**
```xml
<Project Sdk="Microsoft.NET.Sdk.Worker">
  <PropertyGroup>
    <TargetFramework>net8.0-windows</TargetFramework>
    <RuntimeIdentifier>win-x64</RuntimeIdentifier>
    <PublishSingleFile>true</PublishSingleFile>
    <SelfContained>true</SelfContained>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Extensions.Hosting.WindowsServices" Version="8.0.0" />
  </ItemGroup>
</Project>
```

**DisplayManager.cs:**
```csharp
using System.Runtime.InteropServices;

namespace NeuronGuest;

/// <summary>
/// Manages Windows display resolution changes.
/// Uses P/Invoke to call Windows API directly.
/// </summary>
public class DisplayManager
{
    #region P/Invoke Definitions
    
    [DllImport("user32.dll")]
    private static extern int ChangeDisplaySettingsEx(
        string? lpszDeviceName,
        ref DEVMODE lpDevMode,
        IntPtr hwnd,
        uint dwflags,
        IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumDisplaySettings(
        string? lpszDeviceName,
        int iModeNum,
        ref DEVMODE lpDevMode);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    private struct DEVMODE
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }

    private const int ENUM_CURRENT_SETTINGS = -1;
    private const int CDS_UPDATEREGISTRY = 0x01;
    private const int CDS_TEST = 0x02;
    private const int DISP_CHANGE_SUCCESSFUL = 0;
    private const int DM_PELSWIDTH = 0x80000;
    private const int DM_PELSHEIGHT = 0x100000;
    private const int DM_DISPLAYFREQUENCY = 0x400000;
    
    #endregion

    private readonly ILogger<DisplayManager> _logger;

    public DisplayManager(ILogger<DisplayManager> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Gets the current display resolution.
    /// </summary>
    public (int Width, int Height) GetCurrentResolution()
    {
        var dm = new DEVMODE();
        dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));

        if (EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref dm))
        {
            return (dm.dmPelsWidth, dm.dmPelsHeight);
        }

        return (0, 0);
    }

    /// <summary>
    /// Changes the display resolution.
    /// </summary>
    public bool SetResolution(int width, int height, int refreshRate = 60)
    {
        _logger.LogInformation("Setting resolution to {Width}x{Height}@{Hz}Hz", 
            width, height, refreshRate);

        var dm = new DEVMODE();
        dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
        dm.dmPelsWidth = width;
        dm.dmPelsHeight = height;
        dm.dmDisplayFrequency = refreshRate;
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY;

        // Test first
        int result = ChangeDisplaySettingsEx(null, ref dm, IntPtr.Zero, CDS_TEST, IntPtr.Zero);
        
        if (result != DISP_CHANGE_SUCCESSFUL)
        {
            _logger.LogWarning("Resolution {Width}x{Height} not supported", width, height);
            return false;
        }

        // Apply
        result = ChangeDisplaySettingsEx(null, ref dm, IntPtr.Zero, CDS_UPDATEREGISTRY, IntPtr.Zero);
        
        if (result == DISP_CHANGE_SUCCESSFUL)
        {
            _logger.LogInformation("Resolution changed successfully");
            return true;
        }

        _logger.LogError("Failed to change resolution: {Result}", result);
        return false;
    }
}
```

**CommandListener.cs:**
```csharp
using System.IO.Pipes;
using System.Text.Json;

namespace NeuronGuest;

/// <summary>
/// Listens for commands from the Linux host via named pipe.
/// </summary>
public class CommandListener
{
    private readonly ILogger<CommandListener> _logger;
    private readonly DisplayManager _displayManager;
    private readonly CancellationToken _stoppingToken;
    
    private const string PipeName = "NeuronGuestPipe";

    public CommandListener(
        ILogger<CommandListener> logger,
        DisplayManager displayManager,
        CancellationToken stoppingToken)
    {
        _logger = logger;
        _displayManager = displayManager;
        _stoppingToken = stoppingToken;
    }

    public async Task StartListeningAsync()
    {
        _logger.LogInformation("Starting command listener on pipe: {Pipe}", PipeName);

        while (!_stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var pipe = new NamedPipeServerStream(
                    PipeName,
                    PipeDirection.InOut,
                    1,
                    PipeTransmissionMode.Message);

                _logger.LogDebug("Waiting for connection...");
                await pipe.WaitForConnectionAsync(_stoppingToken);
                
                _logger.LogInformation("Client connected");

                using var reader = new StreamReader(pipe);
                using var writer = new StreamWriter(pipe) { AutoFlush = true };

                while (pipe.IsConnected && !_stoppingToken.IsCancellationRequested)
                {
                    var line = await reader.ReadLineAsync(_stoppingToken);
                    
                    if (string.IsNullOrEmpty(line))
                        continue;

                    var response = ProcessCommand(line);
                    await writer.WriteLineAsync(response);
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error in command listener");
                await Task.Delay(1000, _stoppingToken);
            }
        }
    }

    private string ProcessCommand(string json)
    {
        try
        {
            var cmd = JsonSerializer.Deserialize<Command>(json);
            
            if (cmd == null)
                return JsonSerializer.Serialize(new { success = false, error = "Invalid command" });

            return cmd.Action switch
            {
                "set_resolution" => HandleSetResolution(cmd),
                "get_resolution" => HandleGetResolution(),
                "ping" => JsonSerializer.Serialize(new { success = true, pong = true }),
                _ => JsonSerializer.Serialize(new { success = false, error = "Unknown action" })
            };
        }
        catch (Exception ex)
        {
            return JsonSerializer.Serialize(new { success = false, error = ex.Message });
        }
    }

    private string HandleSetResolution(Command cmd)
    {
        if (cmd.Width <= 0 || cmd.Height <= 0)
            return JsonSerializer.Serialize(new { success = false, error = "Invalid dimensions" });

        var result = _displayManager.SetResolution(cmd.Width, cmd.Height, cmd.RefreshRate);
        return JsonSerializer.Serialize(new { success = result });
    }

    private string HandleGetResolution()
    {
        var (width, height) = _displayManager.GetCurrentResolution();
        return JsonSerializer.Serialize(new { success = true, width, height });
    }

    private record Command
    {
        public string Action { get; init; } = "";
        public int Width { get; init; }
        public int Height { get; init; }
        public int RefreshRate { get; init; } = 60;
    }
}
```

**Worker.cs:**
```csharp
namespace NeuronGuest;

public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly DisplayManager _displayManager;

    public Worker(ILogger<Worker> logger, DisplayManager displayManager)
    {
        _logger = logger;
        _displayManager = displayManager;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("NeuronGuest Agent starting...");

        var listener = new CommandListener(
            _logger.CreateLogger<CommandListener>(),
            _displayManager,
            stoppingToken);

        await listener.StartListeningAsync();
    }
}
```

---

## Sprint 4: Integration & Polish (Week 15-16 / Days 99-112)

### Week 15-16: System Integration

| Day | Task |
|-----|------|
| 99-100 | Package Python app for distribution (PyInstaller or proper packaging) |
| 101-102 | Create systemd service for NeuronVM Manager auto-start |
| 103-104 | Build NeuronGuest Windows installer (MSI) |
| 105-106 | Test full flow: Boot → Launch VM → Looking Glass with resize |
| 107-108 | Create first-run setup wizard |
| 109-110 | Documentation: User guide for VM management |
| 111-112 | Phase 2 retrospective, tag `v0.3.0-beta` |

---

# Phase 2 Exit Criteria ✅

- [ ] NeuronVM Manager GUI launches and connects to libvirt
- [ ] Can start/stop VMs from GUI
- [ ] Looking Glass launches from GUI with single click
- [ ] NeuronGuest agent installed in Windows VM
- [ ] Window resize on Linux host triggers resolution change in Windows VM
- [ ] Full flow works end-to-end without terminal commands
- [ ] All code documented and tested

**Proceed to:** [Phase 3 Dev Guide](file:///C:/Users/jasbh/.gemini/antigravity/brain/19c55c70-6e71-40e5-9eed-2f5494130b35/dev_guide_phase_3.md)
