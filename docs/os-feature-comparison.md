# NeuronOS: Honest Assessment vs. ZorinOS 17, Windows 11, macOS Sequoia

## Part 1: OS Feature Comparison

What the majority of daily users actually need. Not power-user features -- the things
a non-technical user, an office worker, and an enterprise user need the moment they sit down.

---

### Installation Experience

| Feature | Windows 11 | macOS | ZorinOS 17 | NeuronOS |
|---|---|---|---|---|
| Installer clicks | ~8 steps, guided | Pre-installed | ~10 steps, GUI | archinstall TUI |
| Time to desktop | 20-30 min | N/A (OEM) | 15-25 min | 20-40 min |
| Non-technical friendly | Yes | Yes | Yes | **No** -- archinstall is a TUI, not a GUI |
| Disk partitioning help | Yes, automatic | Yes | Yes | Manual or guided-but-intimidating |
| Recovery partition | Yes | Yes | Partial | **Not implemented** |
| Accessibility during install | Yes (Narrator) | Yes | Partial | **None** |

**Verdict:** archinstall is a TUI aimed at experienced Arch users. The ArchWiki itself
notes it "hides a lot of things a user is expected to know about." The goal of a
non-technical-friendly installer is fundamentally incompatible with archinstall.
This needs a GUI installer (Calamares or a custom GTK4 front-end).

---

### Out-of-Box Hardware Support

| Feature | Windows 11 | macOS | ZorinOS 17 | NeuronOS |
|---|---|---|---|---|
| WiFi (Intel/Realtek/Broadcom) | Yes, OEM drivers | Yes (Apple only) | Yes, Ubuntu kernel | Arch kernel; Broadcom may need manual setup |
| Bluetooth | Yes | Yes | Yes | Yes |
| NVIDIA GPU | Yes, auto | N/A | Yes (proprietary, optional) | **nouveau default, manual for proprietary** |
| AMD GPU | Yes | N/A | Yes | Yes (mesa) |
| Touchpad gestures | Yes | Yes, best-in-class | Yes, TouchEgg | Yes, GNOME 3-finger |
| Printer (HP/Canon/Epson) | Yes, auto-detect | Yes | Yes, CUPS + drivers | CUPS present, **no auto-detect wizard** |
| Scanner | Yes | Yes | SANE, manual | SANE, manual |
| Webcam | Yes | Yes | Yes | Yes, V4L2 |
| Fingerprint reader | Yes (Windows Hello) | Yes (Touch ID) | fprintd, limited | **Not configured** |
| Face unlock | Yes | Yes | No | No |
| Sleep/hibernate | Yes, reliable | Yes | Varies by hardware | Arch, hit-or-miss |
| 4K/HiDPI scaling | Yes | Yes, native | Yes, GNOME fractional | Yes, GNOME fractional |
| Touchscreen | Yes | Yes | Works, not great | Basic X11 touch |

**Critical gap:** NeuronOS has no NVIDIA proprietary driver setup out of the box.
The majority of gaming/creative users have NVIDIA GPUs. Arch Linux requires manual
`nvidia` package installation and mkinitcpio config changes. **Status: NVIDIA
detection and automated setup has been added to the onboarding wizard.**

---

### App Ecosystem

| Metric | Windows 11 | macOS | ZorinOS 17 | NeuronOS |
|---|---|---|---|---|
| Native app count | Millions (Win32 + Store) | ~3M (Mac App Store) | ~50k+ APT/Snap/Flatpak | ~15k pacman + AUR + Flatpak |
| Microsoft Office | Native + 365 web | Native | LibreOffice + web | LibreOffice + web |
| Adobe Creative Suite | Yes | Yes | Wine/VM | VM (requires dual GPU) |
| AutoCAD | Yes | Yes | No | VM (requires dual GPU) |
| Slack/Discord/Zoom | Yes | Yes | Yes, native/Flatpak | Yes, Flatpak |
| Spotify/Netflix | Yes | Yes | Yes | Yes, browser/Flatpak |
| Browser (Chrome/Firefox/Edge) | Yes | Yes | Yes | Yes, Firefox preinstalled |
| Steam / gaming | Yes, DirectX native | Metal, fewer games | Yes, Steam + Proton | Yes, Steam + Proton |
| VS Code / dev tools | Yes | Yes | Yes | Yes, Flatpak |
| Package manager UX | Store GUI | App Store | Software Center | **Store GUI incomplete** |

---

### Windows/macOS Software Compatibility (Core Value Proposition)

| Method | ZorinOS 17 | NeuronOS | Reality Check |
|---|---|---|---|
| Wine / Bottles | Pre-installed, GUI | Wine in packages | Works for ~50% of Win apps, not enterprise suite |
| Proton (Steam games) | Via Steam | Via Steam | ~80% of Steam library works |
| GPU Passthrough VM | **Not offered** | **Designed for this** | Requires 2 GPUs or iGPU+dGPU |
| Looking Glass display | No | Yes, implemented | Requires IVSHMEM + VFIO setup |
| Windows license needed | N/A | Yes, user pays | $120+ Windows license required |
| AutoCAD in VM | No | Theoretically yes | Requires dual GPU + Windows license |
| Photoshop in VM | No | Theoretically yes | Same hardware constraint |
| macOS VM | No | In app catalog (unsupported) | **Violates Apple EULA on non-Apple hardware** |

#### GPU Passthrough Reality

The feature works on paper, but hardware requirements eliminate most of the target audience:

1. **Two GPUs required** (or verified iGPU+dGPU IOMMU separation) -- most consumer laptops and many desktops have only one GPU
2. **IOMMU must be enabled and working** -- AMD Ryzen platforms are good; Intel is patchy; many OEM boards have it disabled
3. **Clean IOMMU groups required** -- if the GPU shares an IOMMU group with other PCI devices, passthrough fails
4. **Windows license** ($120 retail)
5. **Windows ISO + installation** inside the VM

Even with NeuronOS automating the VFIO setup, hardware requirements alone mean this works for approximately 15-20% of typical consumer hardware.

---

### Gaming

| Feature | Windows 11 | macOS | ZorinOS 17 | NeuronOS |
|---|---|---|---|---|
| Steam native | Yes, DirectX 12 | Metal, limited | Yes, Proton | Yes, Proton |
| Game Pass / Xbox | Yes | No | No | No |
| DirectStorage | Yes | No | No | No |
| DLSS / FSR | Yes | FSR only | Yes, FSR + DLSS via Proton | Same as ZorinOS |
| AntiCheat (EAC/BattlEye) | Yes | No | Some games | Same as ZorinOS |
| GPU VM for Windows games | No | No | No | Yes (dual GPU only) |

ZorinOS and NeuronOS are identical for gaming on single-GPU hardware.

---

### Daily User Features

| Feature | Windows 11 | macOS | ZorinOS 17 | NeuronOS |
|---|---|---|---|---|
| AI assistant | Copilot (GPT-4) | Apple Intelligence | No | No |
| Screenshot tool | Snipping Tool | Cmd+Shift+4 | GNOME screenshot | GNOME screenshot |
| System-wide search | Windows Search | Spotlight | GNOME search | GNOME search |
| Phone integration | Phone Link | iPhone Mirroring | Zorin Connect (KDE Connect) | **Not implemented** |
| Cloud storage | OneDrive built-in | iCloud built-in | Web only | Web only |
| Video calling | Teams built-in | FaceTime | Apps only | Apps only |
| Night light | Yes | Yes | Yes | Yes, GNOME |
| Multiple desktops | Yes | Yes | Yes | Yes |
| Window snapping/tiling | Snap Layouts | Sequoia added it | Added in 17 | GNOME tiling |
| Notification center | Yes | Yes | Yes | Yes |
| Auto updates | Yes | Yes | Yes | **Updater module exists, no auto-update GUI** |
| System backup | Backup + File History | Time Machine | Deja Dup | Btrfs snapshots, **no UI** |
| Settings app | Complete | Complete | Complete | **No custom settings, just GNOME defaults** |
| Accessibility | Comprehensive | Best-in-class | GNOME a11y | GNOME a11y (present, not configured) |

**Missing from NeuronOS that ZorinOS has:**
- Zorin Connect (phone-to-PC file transfer, clipboard sync, notifications)
- Power Modes (performance/balanced/power saver)
- One-click layout switching (Windows-like, macOS-like, GNOME)
- A working Software Center UI

---

## Part 2: Code Review -- Production Readiness

### Production-Ready Components (ships as-is)

| Component | Lines | Why |
|---|---|---|
| vm_creator.py | 312 | Proper validation, fallback XML, disk creation |
| looking_glass.py | 430 | Excellent process lifecycle, proper shmem cleanup |
| gpu_attach.py | 322 | Correct VFIO bind/unbind, driver restoration |
| installer.py | 1,177 | Secure, comprehensive, all 5 install layers |
| app_catalog.py | 328 | Clean data model, correct serialization |
| gpu_scanner.py | 354 | Solid sysfs scanning, good fallbacks |
| migrator.py | 734 | Robust, handles Windows + macOS paths |
| vm_manager/gui/app.py | 911 | Fully functional GTK4 GUI |
| windows11-passthrough.xml.j2 | 228 | Production-grade Libvirt template |

### Partial (needs work before shipping)

| Component | Issues |
|---|---|
| libvirt_manager.py (569 lines) | ~~Audio errors swallowed with bare pass~~ **Fixed**: now logs warning. Lazy import path for GPUScanner is fragile. `_delete_vm_storage()` bypasses libvirt volume management. |
| config_generator.py (469 lines) | Logic is there. Bootloader update calls are fire-and-forget with no verification the kernel cmdline was actually applied. |
| onboarding/wizard.py + pages.py | ~~`generator.generate()` method name mismatch~~ **Fixed**: now calls `detect_and_generate()`. ~~`configs.items()` on VFIOConfig dataclass~~ **Fixed**: now writes individual config files correctly. |

### Skeleton / Not Shipped

| Component | Why |
|---|---|
| store/gui/store_window.py | GTK4 version incomplete; store_window_qt.py is the live one |
| neuron-store entry point | Imports store_window_qt -- Qt GUI exists but has no real catalog browsing |
| updater/ | Rollback logic written; no UI, no autostart, no scheduler |
| ~~NVIDIA driver setup~~ | ~~Completely absent~~ **Added**: detection in onboarding + automated install via pending-tasks |
| Phone integration | Not in codebase at all |
| Backup UI | Btrfs snapshot code exists, zero UI |
| ~~Post-install first-boot wizard~~ | ~~No mechanism to run onboarding on installed system~~ **Added**: systemd one-shot service + XDG autostart |

---

## Part 3: Bugs Found and Fixed

### 1. Method name mismatch -- crashed onboarding wizard

**File:** `src/onboarding/wizard.py:273`

`generator.generate()` called a non-existent method. Actual method is `detect_and_generate()`.
Additionally, the code called `.items()` on a `VFIOConfig` dataclass (not a dict).

**Fix:** Changed to `generator.detect_and_generate()` and rewrote config persistence to write
individual files (`vfio.conf`, `mkinitcpio_modules`, `kernel_params`, `bootloader`).

### 2. libvirt_manager.py -- silent audio device attachment failure

**File:** `src/vm_manager/core/libvirt_manager.py:571`

`except libvirt.libvirtError: pass` swallowed the error. User gets no audio, no error message.

**Fix:** Changed to `logger.warning(f"Failed to attach PCI device {pci_address}: {e}")`.

### 3. Looking Glass IVSHMEM size hardcoded

**File:** `src/vm_manager/templates/windows11-passthrough.xml.j2:162`

`<size unit='M'>128</size>` was hardcoded. At 4K resolution, Looking Glass needs 256MB minimum.

**Fix:** Changed to `{{ looking_glass_size_mb | default(128) }}` making it configurable per-VM.
(The other template at `templates/windows11-passthrough.xml.j2` was already parameterized.)

### 4. No Looking Glass client binary on ISO

Looking Glass is not in the Arch repos. The packages list included build dependencies but
never compiled the client. GPU passthrough VMs had no display.

**Fix:** Added Looking Glass client build step to `customize_airootfs.sh`.

### 5. No first-boot wizard trigger after installation

`neuron-welcome` exits for non-liveuser. After archinstall, the user gets bare GNOME
with no hardware detection, no GPU setup, no onboarding.

**Fix:** Created `neuron-first-boot.service` (systemd one-shot), `neuron-onboarding` entry
point, and XDG autostart desktop entry. Service runs once on first graphical boot, installs
the autostart entry, then marks itself done.

### 6. macOS apps violate Apple EULA

Final Cut Pro and Logic Pro in the app catalog were listed as `playable` via `vm_macos`.
Apple's EULA explicitly prohibits running macOS on non-Apple hardware.

**Fix:** Changed rating to `unsupported`, added legal warnings in notes and known_issues.

---

## Part 4: Competitive Summary

### NeuronOS vs. ZorinOS 17

| Category | ZorinOS 17 | NeuronOS | Winner |
|---|---|---|---|
| Works today, out of box | Yes | Mostly | ZorinOS |
| Installer UX | GUI | TUI | ZorinOS |
| Hardware support | Ubuntu kernel | Arch kernel | ZorinOS |
| Software library | Ubuntu/PPA | Arch/AUR | ZorinOS |
| GPU passthrough | Not offered | Designed for it | **NeuronOS** |
| Enterprise Windows apps (dual GPU) | No | Theoretically yes | **NeuronOS** |
| Stability (non-technical user) | LTS | Rolling | ZorinOS |
| Privacy (no telemetry) | Yes | Yes | Tie |
| Gaming (Proton) | Yes | Yes | Tie |
| Phone integration | Zorin Connect | Not implemented | ZorinOS |
| First-boot experience | Polished | ~~Incomplete~~ Partially fixed | ZorinOS |

### For single-GPU hardware (most users): ZorinOS wins

On single-GPU hardware, NeuronOS and ZorinOS offer an identical experience: Linux desktop + Wine/Proton.
ZorinOS is strictly better because of Ubuntu base (better hardware support, more stable), real GUI installer,
Zorin Appearance, Zorin Connect, polished Software Center, and 5-year LTS.

### For dual-GPU hardware (power users): NeuronOS has a unique value proposition

For users with iGPU+dGPU or desktop users with two cards, NeuronOS is genuinely unique:
- Automated VFIO setup
- One-click Windows VM with GPU passthrough
- Looking Glass seamless windowed display
- Run Photoshop/AutoCAD at near-native GPU speed from a Linux desktop

No other consumer Linux distro offers this combination.

---

## Part 5: Remaining Priority Items

### P0 (blocking core value proposition) -- RESOLVED

- [x] ~~Build Looking Glass client binary into ISO~~
- [x] ~~Post-install first-boot wizard trigger~~
- [x] ~~Fix method name bug in wizard.py~~
- [x] ~~NVIDIA driver automation~~

### P1 (required to be better than ZorinOS for non-technical users)

- [ ] Replace archinstall with a GUI installer (Calamares or custom GTK4 front-end)
- [ ] Phone integration (GSConnect extension -- one-package addition)
- [ ] Working NeuronStore UI with functional install buttons
- [ ] Power modes UI widget (powerprofilesctl integration)

### P2 (parity with ZorinOS)

- [x] ~~Looking Glass IVSHMEM size as template variable~~
- [x] ~~libvirt_manager audio error surfacing~~
- [ ] Backup UI for Btrfs snapshots
- [ ] Auto-update GUI for the updater module

---

## The Bottom Line

NeuronOS's GPU passthrough concept is technically real and genuinely differentiated.
The core implementation (VFIO binding, Looking Glass, VM templates) is largely production-ready.

However, it currently falls below ZorinOS on every metric a typical user cares about at
first boot: installation UX, hardware setup, software availability, and out-of-box appearance.

The path forward is clear:

1. **GUI installer** -- currently prevents the entire target market from installing
2. **First-boot wizard trigger** -- ~~was missing~~ now implemented
3. **Looking Glass binary on ISO** -- ~~the killer feature had no display~~ now builds from source

The rolling-release Arch base is a strategic risk for non-technical users. A 5-year LTS
question is worth revisiting post-MVP.
