# NeuronOS Implementation Guides

This directory contains the complete implementation roadmap for building NeuronOS.

---

## What is NeuronOS?

**NeuronOS** is a consumer-grade Linux distribution designed to eliminate the complexity barrier preventing mainstream adoption. It provides:

- **One-click installation** via archinstall — No terminal required
- **Windows app compatibility** — Via Wine/Proton (15% of apps)
- **Professional software support** — Via GPU passthrough VMs with Looking Glass (5% of apps)
- **macOS VM support** — For Mac switchers
- **Familiar UI** — Windows 11-like and macOS-like theme options
- **Native Linux apps** — 80% of use cases served natively

---

## Architecture

| Component | Technology |
|-----------|-----------|
| **Base** | Arch Linux (archiso) |
| **Desktop** | GNOME with GDM (auto-login for live ISO) |
| **Themes** | GTK4 CSS (neuron.css, win11.css, macos.css) |
| **Installer** | archinstall (archinstall CLI) |
| **Virtualization** | libvirt/QEMU/KVM with VFIO passthrough |
| **Display Sharing** | Looking Glass (KVMFR shared memory) |
| **Windows Compat** | Wine, Proton (via Steam) |
| **App Store** | Custom Python backend + GTK4/Adwaita GUI |
| **Dialogs** | Zenity (GNOME-native) |

**Important:** NeuronOS uses **GNOME + GDM**, NOT LXQt/SDDM. All configuration references GNOME tools (gnome-terminal, nautilus, gnome-system-monitor).

---

## Phase Overview

| Phase | Name | Focus | Duration | Status |
|-------|------|-------|----------|--------|
| **0** | [Foundation](./PHASE_0_FOUNDATION.md) | Environment setup, prerequisites | 2-4 hours | Reference |
| **1** | [Bootable ISO](./PHASE_1_MINIMAL_ISO.md) | GNOME desktop, GDM, archinstall | 1-2 days | DONE |
| **2** | [Hardware Detection](./PHASE_2_HARDWARE_DETECTION.md) | GPU/IOMMU/VFIO detection & config | 3-5 days | DONE |
| **3** | [VM Management](./PHASE_3_VM_MANAGEMENT.md) | Libvirt lifecycle, guest agent, GUI | 5-7 days | DONE |
| **4** | [GPU Passthrough](./PHASE_4_GPU_PASSTHROUGH.md) | VFIO binding, Looking Glass, single-GPU | 5-7 days | Code complete |
| **5** | [Wine & Proton](./PHASE_5_WINE_PROTON.md) | Wine prefixes, Proton detection | 3-5 days | DONE |
| **6** | [App Store](./PHASE_6_APP_STORE.md) | Catalog, installers, CLI, GUI | 5-7 days | DONE |
| **7** | [Onboarding & Migration](./PHASE_7_ONBOARDING_MIGRATION.md) | Wizard, file migration, theming | 4-6 days | DONE |
| **8** | [Testing & Production](./PHASE_8_TESTING_PRODUCTION.md) | Tests, security, release process | 1-2 weeks | In progress |

**Total Estimated Time:** 5-8 weeks for full implementation

---

## How to Use These Guides

### For AI Coding Agents

Each phase guide documents:

1. **What Already Exists** — Complete inventory of existing code (DO NOT rewrite)
2. **Objectives** — Specific goals with verification methods
3. **Verification commands** — Runnable commands to test each feature
4. **What to Check** — Checkboxes that MUST pass before moving on
5. **What Needs Work** — Gaps identified, with implementation guidance

**Critical Rules:**

- **DO NOT strip down or rewrite existing code** — The codebase is built to Phase 7-8 level. Stripping it breaks everything.
- **Read existing code BEFORE implementing** — Most modules are 80-100% complete
- **Verify ALL checkboxes** — Don't skip verification steps
- **GNOME, not LXQt** — All references must use GNOME apps (gnome-terminal, nautilus, etc.)
- **GDM, not SDDM** — Display manager is GDM with auto-login for liveuser
- **archinstall, not Calamares** — Calamares is not in Arch repos

### For Human Developers

Start with Phase 0 to set up your development environment. Each phase is designed to be:

- **Self-contained** — Clear start and end points
- **Testable** — Every change can be verified
- **Incremental** — Small steps that build confidence

---

## Codebase Status

### Python Modules (~18,300 lines across 67+ source files, 15 test files)

| Module | Files | Lines | Completion |
|--------|-------|-------|------------|
| `hardware_detect/` | 8 | ~2,200 | 100% — GPU, CPU, IOMMU, VFIO all working |
| `vm_manager/` | 20 | ~4,500 | 95% — Backend + GTK4 GUI complete |
| `store/` | 10 | ~3,200 | 100% — Catalog, installers, CLI, GUI, Wine manager, Steam detect |
| `onboarding/` | 5 | ~800 | 100% — Wizard + pending-tasks executor |
| `migration/` | 4 | ~1,200 | 100% — Drive detection + migrators + max_file_size |
| `updater/` | 7 | ~1,000 | 95% — Verifier + rollback + snapshot |
| `common/` | 6 | ~1,500 | 100% — Logging, config, permissions |
| `utils/` | 5 | ~700 | 100% — Atomic writes, helpers |

### Other Components

| Component | Status |
|-----------|--------|
| ISO Profile | GNOME + GDM configured, 104 packages |
| GTK4 Themes | 3 themes complete (neuron, win11, macos) |
| App Catalog | 55+ apps across 7 layers |
| VM Templates | Jinja2 templates for Windows VMs |
| Guest Agent | C# agent for Windows VMs (~1,250 lines) |
| Test Suite | 15 test files, 241 tests passing, 51 ISO validation checks |
| Store GUI | GTK4/Adwaita app store browser |
| Wine/Proton | Prefix manager + Steam/Proton detection |

---

## Quick Reference

### Essential Commands

```bash
# Build ISO (must be root)
cd /home/user/NeuronOS
sudo ./build-iso.sh --clean

# Test ISO in QEMU
make test-vm

# Run tests
python -m pytest tests/ -v

# Validate ISO profile
./scripts/validate-iso-profile.sh
```

### Project Structure

```
NeuronOS/
├── src/                    # Python source code
│   ├── hardware_detect/    # GPU/IOMMU/VFIO detection
│   ├── vm_manager/         # VM lifecycle, guest agent, GUI
│   │   ├── core/           # Backend (lifecycle, template engine, network)
│   │   └── gui/            # PyQt6 VM manager GUI (stub)
│   ├── store/              # App catalog, installers
│   ├── onboarding/         # GTK4/Adwaita setup wizard
│   ├── migration/          # Drive detection, file migration
│   ├── updater/            # System updates, snapshots, rollback
│   ├── common/             # Logging, config, permissions
│   └── utils/              # Atomic writes, helpers
├── iso-profile/            # Archiso configuration
│   ├── airootfs/           # Live filesystem
│   │   ├── etc/gdm/        # GDM auto-login config
│   │   ├── etc/dconf/      # GNOME system defaults
│   │   ├── etc/skel/       # User skeleton (Desktop shortcuts)
│   │   └── usr/bin/        # Entry points (neuron-*)
│   ├── packages.x86_64     # Package list (~186 packages)
│   ├── profiledef.sh       # Build configuration
│   └── pacman.conf         # Pacman config with [multilib]
├── data/                   # App catalog (apps.json, 46 apps)
├── tests/                  # Test suite (9 test files)
├── docs/                   # Documentation
│   └── implementation-guides/  # These phase guides
├── build-iso.sh            # Primary build script
├── Makefile                # Build targets
└── scripts/                # Utility scripts
```

### Key File Locations

| What | Where |
|------|-------|
| GDM auto-login | `iso-profile/airootfs/etc/gdm/custom.conf` |
| GNOME defaults | `iso-profile/airootfs/etc/dconf/db/local.d/00-neuronos` |
| Desktop shortcuts | `iso-profile/airootfs/etc/skel/Desktop/` |
| Themes | `iso-profile/airootfs/usr/share/neuron-os/themes/` |
| Entry points | `iso-profile/airootfs/usr/bin/neuron-*` |
| Welcome autostart | `iso-profile/airootfs/etc/xdg/autostart/neuron-welcome.desktop` |

---

## Troubleshooting

### ISO Won't Build

1. Check `packages.x86_64` for typos or duplicate package names
2. Ensure `pacman.conf` has `[multilib]` enabled
3. Run with verbose: `sudo mkarchiso -v ...`
4. Check disk space (needs ~10GB free)
5. Run `scripts/validate-iso-profile.sh` to catch common issues

### ISO Won't Boot

1. Test in QEMU first: `make test-vm`
2. Check for kernel panic messages
3. Verify bootloader configuration (BIOS: syslinux, UEFI: GRUB)
4. Check if UEFI vs BIOS mode matches your test environment

### Desktop Doesn't Load

1. Verify GDM is enabled: check `display-manager.service` symlink
2. Check GDM auto-login config: `etc/gdm/custom.conf`
3. Verify GNOME packages installed: `gnome`, `gdm`, `gnome-extra`
4. Check for wrong DE references (no LXQt, SDDM, Calamares)

### Hardware Detection Fails

1. Verify IOMMU enabled in BIOS
2. Check kernel parameters: `intel_iommu=on` or `amd_iommu=on`
3. Run `dmesg | grep -i iommu` to check status

### VM Won't Start

1. Check libvirtd: `sudo systemctl status libvirtd`
2. Verify user in libvirt group
3. Check VM XML: `virsh dumpxml <vm-name>`

---

## Contributing

1. Follow the phase structure for new features
2. Add tests for all new code
3. Update documentation
4. Ensure ISO still builds after changes
5. Run security checks before committing
6. Use GNOME tools only (no LXQt/KDE references)

---

## License

NeuronOS is released under GPL-3.0. See LICENSE file for details.
