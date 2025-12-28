# NeuronOS Dev Guide: Phases 3-5 — Store, Enterprise & Launch

This document covers the final phases of NeuronOS development, focusing on the application marketplace, system resilience, and production readiness.

---

# Phase 3: NeuronStore & System Polish (Weeks 17-24)

**Duration:** 8 Weeks
**Developers Required:** 2-3
**Goal:** Build the application marketplace and ensure system resilience.

---

## Sprint 1: Application Database (Week 17-18)

### 🎫 Story 3.1: App Catalog Schema
**As a** User,
**I want** a searchable catalog of applications,
**So that** I can find and install software easily.

**Acceptance Criteria:**
- [ ] JSON schema defined for app entries.
- [ ] Database includes 50+ popular applications.
- [ ] Each app has: name, icon, install method, compatibility rating.

**Tasks:**

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-2 | Define JSON schema | `apps-schema.json` |
| 3-5 | Populate initial database | `apps.json` with 50 apps |
| 6-7 | Create Python API for queries | `catalog.py` |

**apps.json Schema:**
```json
{
  "version": "1.0.0",
  "apps": [
    {
      "id": "adobe-photoshop",
      "name": "Adobe Photoshop",
      "vendor": "Adobe Inc.",
      "description": "Professional image editing software",
      "category": "creative",
      "icon": "adobe-photoshop.png",
      "install_method": "vm",
      "compatibility": {
        "rating": "gold",
        "notes": "Requires GPU passthrough VM"
      },
      "resources": {
        "min_ram_mb": 8192,
        "recommended_ram_mb": 16384,
        "gpu_required": true
      },
      "alternatives": [
        {"id": "gimp", "name": "GIMP", "reason": "Free and open source"}
      ]
    },
    {
      "id": "firefox",
      "name": "Firefox",
      "vendor": "Mozilla",
      "description": "Open source web browser",
      "category": "internet",
      "icon": "firefox.png",
      "install_method": "native",
      "package_name": "firefox",
      "compatibility": {
        "rating": "platinum",
        "notes": "Native Linux application"
      }
    },
    {
      "id": "microsoft-office",
      "name": "Microsoft Office",
      "vendor": "Microsoft",
      "description": "Office productivity suite",
      "category": "productivity",
      "icon": "ms-office.png",
      "install_method": "wine",
      "wine_rating": "gold",
      "compatibility": {
        "rating": "gold",
        "notes": "Works via Wine or VM"
      },
      "alternatives": [
        {"id": "libreoffice", "name": "LibreOffice", "reason": "Native, free alternative"}
      ]
    }
  ]
}
```

**catalog.py:**
```python
#!/usr/bin/env python3
"""NeuronOS Store - Application Catalog"""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class InstallMethod(Enum):
    NATIVE = "native"      # pacman/flatpak
    WINE = "wine"          # Wine/Bottles
    VM = "vm"              # Requires Windows VM
    MACOS_VM = "macos_vm"  # Requires macOS VM


class CompatibilityRating(Enum):
    PLATINUM = "platinum"  # Works perfectly
    GOLD = "gold"          # Works with minor issues
    SILVER = "silver"      # Works with workarounds
    BRONZE = "bronze"      # Barely works
    BROKEN = "broken"      # Does not work


@dataclass
class AppEntry:
    id: str
    name: str
    vendor: str
    description: str
    category: str
    install_method: InstallMethod
    compatibility_rating: CompatibilityRating
    package_name: Optional[str] = None
    vm_profile: Optional[str] = None
    

class AppCatalog:
    """Application catalog manager."""
    
    def __init__(self, catalog_path: Path):
        self.path = catalog_path
        self.apps: List[AppEntry] = []
        self._load()
    
    def _load(self):
        """Load catalog from JSON."""
        with open(self.path) as f:
            data = json.load(f)
        
        for app_data in data.get("apps", []):
            self.apps.append(self._parse_app(app_data))
    
    def _parse_app(self, data: dict) -> AppEntry:
        return AppEntry(
            id=data["id"],
            name=data["name"],
            vendor=data.get("vendor", "Unknown"),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            install_method=InstallMethod(data["install_method"]),
            compatibility_rating=CompatibilityRating(
                data.get("compatibility", {}).get("rating", "bronze")
            ),
            package_name=data.get("package_name"),
            vm_profile=data.get("vm_profile")
        )
    
    def search(self, query: str) -> List[AppEntry]:
        """Search apps by name or description."""
        query = query.lower()
        return [
            app for app in self.apps
            if query in app.name.lower() or query in app.description.lower()
        ]
    
    def by_category(self, category: str) -> List[AppEntry]:
        """Get apps by category."""
        return [app for app in self.apps if app.category == category]
    
    def get_native_apps(self) -> List[AppEntry]:
        """Get all native Linux apps."""
        return [
            app for app in self.apps 
            if app.install_method == InstallMethod.NATIVE
        ]
```

---

## Sprint 2: Store UI (Week 19-20)

### 🎫 Story 3.2: Application Store Interface
**As a** User,
**I want** a visual store to browse and install applications,
**So that** I don't need to use the terminal.

**Acceptance Criteria:**
- [ ] Grid view of applications with icons.
- [ ] Search functionality.
- [ ] Category filtering.
- [ ] One-click install with progress indicator.

**Tasks:**

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-3 | Build store main window (GTK4) | `store_window.py` |
| 4-6 | Implement app card component | `app_card.py` |
| 7-8 | Add search and filtering | Search bar + category sidebar |
| 9-10 | Implement install flow | Progress dialog + backend |
| 11-14 | Polish and test | Animation, error handling |

**store_window.py (Skeleton):**
```python
#!/usr/bin/env python3
"""NeuronOS Store - Main Window"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

from .catalog import AppCatalog, InstallMethod


class StoreWindow(Adw.ApplicationWindow):
    """NeuronOS Application Store main window."""
    
    def __init__(self, app):
        super().__init__(application=app, title="NeuronOS Store")
        self.set_default_size(1000, 700)
        
        self.catalog = AppCatalog(Path("/usr/share/neuron-store/apps.json"))
        
        self._build_ui()
        self._populate_apps()
    
    def _build_ui(self):
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)
        
        # Header
        header = Adw.HeaderBar()
        main_box.append(header)
        
        # Search
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search apps...")
        self.search.connect("search-changed", self._on_search)
        header.set_title_widget(self.search)
        
        # Content with sidebar
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_vexpand(True)
        main_box.append(content)
        
        # Category sidebar
        self._build_sidebar(content)
        
        # App grid
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        content.append(scroll)
        
        self.app_grid = Gtk.FlowBox()
        self.app_grid.set_valign(Gtk.Align.START)
        self.app_grid.set_max_children_per_line(4)
        self.app_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.app_grid)
    
    def _build_sidebar(self, parent):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(200, -1)
        parent.append(sidebar)
        
        categories = [
            ("All Apps", "view-grid-symbolic", None),
            ("Native", "tux-symbolic", "native"),
            ("Creative", "applications-graphics-symbolic", "creative"),
            ("Productivity", "applications-office-symbolic", "productivity"),
            ("Games", "applications-games-symbolic", "games"),
        ]
        
        for label, icon, category in categories:
            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, c=category: self._filter_category(c))
            
            box = Gtk.Box(spacing=10)
            box.append(Gtk.Image.new_from_icon_name(icon))
            box.append(Gtk.Label(label=label))
            btn.set_child(box)
            
            sidebar.append(btn)
    
    def _populate_apps(self, apps=None):
        # Clear
        while child := self.app_grid.get_first_child():
            self.app_grid.remove(child)
        
        apps = apps or self.catalog.apps
        
        for app in apps:
            card = self._create_app_card(app)
            self.app_grid.append(card)
    
    def _create_app_card(self, app):
        # ... App card creation
        pass
    
    def _on_search(self, entry):
        query = entry.get_text()
        if query:
            results = self.catalog.search(query)
            self._populate_apps(results)
        else:
            self._populate_apps()
    
    def _filter_category(self, category):
        if category:
            apps = self.catalog.by_category(category)
        else:
            apps = self.catalog.apps
        self._populate_apps(apps)
```

---

## Sprint 3: Installation Engine (Week 21-22)

### Tasks:

| Day | Task | Details |
|-----|------|---------|
| 1-3 | Native installer (pacman/flatpak) | Wrapper around `pacman -S` |
| 4-6 | Wine installer (Bottles integration) | Use `bottles-cli` API |
| 7-10 | VM app installer | Launch VM + script in guest |
| 11-14 | Testing all install paths | End-to-end tests |

**install_engine.py:**
```python
#!/usr/bin/env python3
"""NeuronOS Store - Installation Engine"""

import subprocess
from enum import Enum
from typing import Callable, Optional
from dataclasses import dataclass

from .catalog import AppEntry, InstallMethod


@dataclass
class InstallProgress:
    """Progress update for installation."""
    step: str
    progress: float  # 0.0 to 1.0
    message: str


class InstallEngine:
    """Handles application installation."""
    
    def __init__(self):
        self.progress_callback: Optional[Callable[[InstallProgress], None]] = None
    
    def install(self, app: AppEntry) -> bool:
        """Install an application."""
        method = app.install_method
        
        if method == InstallMethod.NATIVE:
            return self._install_native(app)
        elif method == InstallMethod.WINE:
            return self._install_wine(app)
        elif method == InstallMethod.VM:
            return self._install_vm(app)
        
        return False
    
    def _report_progress(self, step: str, progress: float, message: str):
        if self.progress_callback:
            self.progress_callback(InstallProgress(step, progress, message))
    
    def _install_native(self, app: AppEntry) -> bool:
        """Install via pacman."""
        self._report_progress("native", 0.1, f"Installing {app.name}...")
        
        try:
            # Check if Flatpak or pacman
            if app.package_name.startswith("com."):
                # Flatpak
                result = subprocess.run(
                    ["flatpak", "install", "-y", "flathub", app.package_name],
                    capture_output=True, text=True
                )
            else:
                # Pacman
                result = subprocess.run(
                    ["pkexec", "pacman", "-S", "--noconfirm", app.package_name],
                    capture_output=True, text=True
                )
            
            self._report_progress("native", 1.0, "Installation complete!")
            return result.returncode == 0
            
        except Exception as e:
            self._report_progress("native", 1.0, f"Error: {str(e)}")
            return False
    
    def _install_wine(self, app: AppEntry) -> bool:
        """Install via Bottles."""
        self._report_progress("wine", 0.1, "Preparing Wine environment...")
        
        # TODO: Integrate with Bottles CLI
        # bottles-cli run -b "NeuronOS" -e "installer.exe"
        
        return False
    
    def _install_vm(self, app: AppEntry) -> bool:
        """App requires VM - guide user through setup."""
        self._report_progress("vm", 0.1, "This app requires a Windows VM")
        
        # TODO: 
        # 1. Check if VM exists
        # 2. Guide user to VM Manager to create one
        # 3. Provide download link / instructions for app
        
        return False
```

---

## Sprint 4: System Resilience (Week 23-24)

### 🎫 Story 3.3: Automatic System Snapshots
**As a** User,
**I want** automatic snapshots before updates,
**So that** I can recover from broken updates.

**Acceptance Criteria:**
- [ ] Snapper configured for root filesystem.
- [ ] Pre/post snapshots on every `pacman` transaction.
- [ ] Boot menu shows snapshot entries (GRUB-BTRFS).
- [ ] GUI tool to restore snapshots.

**Tasks:**

| Day | Task | Details |
|-----|------|---------|
| 1-2 | Install and configure Snapper | `snapper -c root create-config /` |
| 3-4 | Install snap-pac | Auto snapshots on pacman |
| 5-6 | Install grub-btrfs | Bootable snapshots |
| 7-8 | Create snapshot manager GUI | Simple GTK app |
| 9-14 | Testing: Break and restore system | Verify recovery works |

**Snapper Configuration:**
```bash
# Install
sudo pacman -S snapper snap-pac grub-btrfs

# Create config
sudo snapper -c root create-config /

# Configure
sudo vim /etc/snapper/configs/root
# Set: TIMELINE_CREATE=yes
# Set: TIMELINE_LIMIT_HOURLY=5
# Set: TIMELINE_LIMIT_DAILY=7

# Enable services
sudo systemctl enable --now snapper-timeline.timer
sudo systemctl enable --now snapper-cleanup.timer
sudo systemctl enable --now grub-btrfsd
```

---

# Phase 4: Enterprise & macOS (Weeks 25-32)

**Duration:** 8 Weeks
**Developers Required:** 2
**Goal:** Enterprise fleet management and optional macOS VM support.

---

## Sprint 1-2: macOS VM Integration (Week 25-28)

### 🎫 Story 4.1: OSX-KVM Integration
**As a** Power User,
**I want** optional macOS VM support,
**So that** I can run Mac-only applications.

**Acceptance Criteria:**
- [ ] OSX-KVM scripts packaged for NeuronOS.
- [ ] macOS Ventura/Sonoma boots in VM.
- [ ] Clear warnings about EULA and iMessage reliability.
- [ ] Documented as "community supported" feature.

**Tasks:**

| Week | Task |
|------|------|
| 25 | Fork and package OSX-KVM scripts |
| 26 | Create macOS VM profile in NeuronVM Manager |
| 27 | Test GPU passthrough with AMD GPU (limited support) |
| 28 | Documentation and disclaimer UI |

**⚠️ Important Disclaimers:**
```markdown
# macOS VM Support

> [!CAUTION]
> macOS VM support is provided as a **community-supported** feature.
> 
> **Limitations:**
> - Apple EULA technically prohibits running macOS on non-Apple hardware
> - iMessage/FaceTime activation is unreliable and may fail
> - GPU acceleration limited (no NVIDIA, limited AMD support)
> - Apple may block VM detection at any time
> 
> **NeuronOS does NOT:**
> - Bundle macOS images (user must provide)
> - Guarantee iMessage functionality
> - Provide support for EULA-related issues
```

---

## Sprint 3-4: Fleet Management (Week 29-32)

### 🎫 Story 4.2: Enterprise Deployment Tools
**As an** IT Administrator,
**I want** to deploy NeuronOS to multiple machines,
**So that** I can manage a fleet efficiently.

**Acceptance Criteria:**
- [ ] Ansible playbooks for NeuronOS deployment.
- [ ] Centralized configuration management.
- [ ] Remote VM management capabilities.
- [ ] Automated updates with rollback.

**ansible/deploy-neuronos.yml:**
```yaml
---
- name: Deploy NeuronOS Configuration
  hosts: workstations
  become: yes
  
  vars:
    neuron_version: "1.0.0"
    vm_profile: "productivity"
  
  tasks:
    - name: Update system
      pacman:
        update_cache: yes
        upgrade: yes
    
    - name: Install NeuronOS packages
      pacman:
        name:
          - neuron-vm-manager
          - neuron-store
          - neuron-system-guard
        state: present
    
    - name: Copy VM profile
      template:
        src: templates/vm-profile.json.j2
        dest: /etc/neuron-vm/profiles/{{ vm_profile }}.json
    
    - name: Enable services
      systemd:
        name: "{{ item }}"
        enabled: yes
        state: started
      loop:
        - libvirtd
        - neuron-vm-manager
    
    - name: Create Btrfs snapshot
      command: snapper -c root create -d "Post-deployment snapshot"
```

---

# Phase 5: Testing & Production Launch (Weeks 33-40)

**Duration:** 8 Weeks
**Developers Required:** 3+
**Goal:** Bug fixing, documentation, and public release.

---

## Sprint 1-2: Beta Testing (Week 33-36)

### Tasks:

| Week | Task | Deliverable |
|------|------|-------------|
| 33 | Internal QA testing | Bug list |
| 34 | Hardware compatibility matrix | 20+ tested configs |
| 35 | Private beta (50 users) | Feedback collection |
| 36 | Public beta (500 users) | Issue tracker triage |

**Hardware Compatibility Test Matrix:**
```markdown
| Hardware Config | VFIO | LG Latency | Issues |
|----------------|------|------------|--------|
| Intel 12th Gen + RTX 3070 | ✅ | 8ms | None |
| AMD Ryzen 5600X + RX 6700 | ✅ | 12ms | Vendor Reset Bug |
| Intel 10th Gen + GTX 1660 | ✅ | 10ms | None |
| AMD Laptop (iGPU only) | ⚠️ | N/A | Single-GPU mode |
```

---

## Sprint 3-4: Documentation & Launch (Week 37-40)

### Tasks:

| Week | Task | Deliverable |
|------|------|-------------|
| 37 | User documentation | docs.neuronos.org |
| 38 | Video tutorials | YouTube channel |
| 39 | Website launch | neuronos.org |
| 40 | v1.0.0 Release | ISO + announcement |

**Release Checklist:**
- [ ] All blocking bugs fixed
- [ ] Documentation complete
- [ ] ISO hosted on multiple mirrors
- [ ] SHA256 checksums published
- [ ] GPG-signed release
- [ ] Press release prepared
- [ ] Social media announcements scheduled
- [ ] Community forum/Discord ready
- [ ] Support email configured

---

# Final Deliverables

| Component | Description |
|-----------|-------------|
| **NeuronOS ISO** | Bootable installer with auto-VFIO |
| **NeuronVM Manager** | GUI for VM management |
| **NeuronStore** | Application marketplace |
| **NeuronGuest** | Windows resolution sync agent |
| **Documentation** | User guides and tutorials |
| **Website** | neuronos.org with downloads |

---

# Total Timeline Summary

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| Phase 0 | 2 weeks | Working GPU passthrough PoC |
| Phase 1 | 6 weeks | Auto-configuring ISO |
| Phase 2 | 8 weeks | NeuronVM Manager GUI |
| Phase 3 | 8 weeks | NeuronStore + Snapshots |
| Phase 4 | 8 weeks | Enterprise tools |
| Phase 5 | 8 weeks | v1.0.0 Release |
| **TOTAL** | **40 weeks** | **Production OS** |

---

**Congratulations! 🎉**

If you've completed all phases, you have built a production-grade Linux distribution with:
- One-click Windows/macOS app support
- Consumer-friendly UX
- Enterprise deployment capabilities
- Automatic system recovery

**Welcome to NeuronOS v1.0!**
