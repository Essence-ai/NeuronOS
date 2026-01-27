# NeuronOS Implementation Guides

This directory contains the complete implementation roadmap for building NeuronOS from scratch.

---

## What is NeuronOS?

**NeuronOS** is a consumer-grade Linux distribution designed to eliminate the complexity barrier preventing mainstream adoption. It provides:

- **One-click installation** - No terminal required
- **Windows app compatibility** - Via Wine/Proton
- **Professional software support** - Via GPU passthrough VMs (Adobe, AutoCAD, etc.)
- **macOS VM support** - For Mac switchers
- **Familiar UI** - Windows 11-like experience option

---

## Phase Overview

| Phase | Name | Focus | Duration |
|-------|------|-------|----------|
| **0** | [Foundation](./PHASE_0_FOUNDATION.md) | Environment setup, prerequisites | 2-4 hours |
| **1** | [Minimal ISO](./PHASE_1_MINIMAL_ISO.md) | Bootable ISO, basic installation | 1-2 days |
| **2** | [Hardware Detection](./PHASE_2_HARDWARE_DETECTION.md) | GPU/IOMMU detection, VFIO config | 3-5 days |
| **3** | [VM Management](./PHASE_3_VM_MANAGEMENT.md) | Libvirt integration, VM lifecycle | 5-7 days |
| **4** | [Wine & Proton](./PHASE_4_WINE_PROTON.md) | Windows app compatibility | 3-5 days |
| **5** | [GPU Passthrough](./PHASE_5_GPU_PASSTHROUGH.md) | Near-native VM performance | 5-7 days |
| **6** | [App Store](./PHASE_6_APP_STORE.md) | Application marketplace | 5-7 days |
| **7** | [First-Run](./PHASE_7_FIRST_RUN.md) | Onboarding wizard, migration | 4-6 days |
| **8** | [Theming](./PHASE_8_THEMING.md) | Visual polish, dark mode | 3-5 days |
| **9** | [Production](./PHASE_9_PRODUCTION.md) | Testing, security, release | 1-2 weeks |

**Total Estimated Time:** 6-10 weeks for full implementation

---

## How to Use These Guides

### For AI Coding Agents

Each phase guide follows a consistent structure:

1. **Recap** - What we're building and why
2. **Objectives** - Specific goals with verification methods
3. **Step-by-step instructions** - Detailed implementation steps
4. **Code examples** - Reference implementations (not copy-paste)
5. **Verification criteria** - Checkboxes that MUST pass
6. **Troubleshooting** - Common issues and solutions

**Important Principles:**

- **Complete each phase before moving on** - Each phase builds on the previous
- **Verify ALL checkboxes** - Don't skip verification steps
- **Test on real hardware** - VMs can't test everything (especially GPU passthrough)
- **Read existing code first** - These guides show patterns, not complete code

### For Human Developers

Start with Phase 0 to set up your development environment. Each phase is designed to be:

- **Self-contained** - Clear start and end points
- **Testable** - Every change can be verified
- **Incremental** - Small steps that build confidence

---

## Key Principles

### 1. Verify Before Proceeding

Each phase has verification checkboxes. **All boxes must be checked** before moving to the next phase. This prevents cascading failures.

### 2. Test on Real Hardware

GPU passthrough requires actual hardware with IOMMU support. A VM cannot test GPU passthrough.

### 3. Keep the ISO Building

After Phase 1, every change should maintain a buildable ISO. If the ISO stops building, fix it immediately.

### 4. Don't Skip Phases

The phases are ordered deliberately. Phase 5 (GPU passthrough) won't work if Phase 2 (hardware detection) isn't complete.

### 5. Read Existing Code

These guides show patterns and approaches. The actual implementation should integrate with existing code, not replace it wholesale.

---

## Quick Reference

### Essential Commands

```bash
# Build ISO
cd /home/user/NeuronOS
sudo mkarchiso -v -w /tmp/work -o /tmp/out iso-profile/

# Test ISO
qemu-system-x86_64 -enable-kvm -m 4G -boot d -cdrom /tmp/out/neuronos-*.iso

# Run tests
python -m pytest tests/ -v

# Hardware check
python3 -m hardware_detect.cli check

# VM management
python3 -m vm_manager.cli list
```

### Project Structure

```
NeuronOS/
├── src/                    # Python source code
│   ├── hardware_detect/    # GPU/IOMMU detection
│   ├── vm_manager/         # VM lifecycle management
│   ├── store/              # App marketplace
│   ├── onboarding/         # First-run wizard
│   ├── migration/          # File migration
│   └── common/             # Shared utilities
├── iso-profile/            # Archiso configuration
│   ├── airootfs/           # Live filesystem
│   ├── packages.x86_64     # Package list
│   └── profiledef.sh       # Build config
├── templates/              # VM XML templates
├── data/                   # App catalog, icons
├── tests/                  # Test suite
└── docs/                   # Documentation
```

---

## Troubleshooting

### ISO Won't Build

1. Check packages.x86_64 for typos in package names
2. Ensure pacman.conf has [multilib] enabled
3. Run with verbose: `sudo mkarchiso -v ...`
4. Check disk space (needs ~10GB)

### ISO Won't Boot

1. Test in QEMU first
2. Check for kernel panic messages
3. Verify bootloader configuration
4. Check if UEFI vs BIOS mode matches

### Hardware Detection Fails

1. Verify IOMMU is enabled in BIOS
2. Check kernel parameters include `intel_iommu=on` or `amd_iommu=on`
3. Run `dmesg | grep -i iommu` to check status

### VM Won't Start

1. Check libvirtd is running: `sudo systemctl status libvirtd`
2. Verify user is in libvirt group
3. Check VM XML for errors: `virsh dumpxml <vm-name>`

### GPU Passthrough Fails

1. Verify GPU is bound to vfio-pci: `lspci -nnk`
2. Check IOMMU group isolation
3. Ensure Looking Glass host is running in VM

---

## Getting Help

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Check docs/ directory
- **Code Comments**: Each module has docstrings

---

## Contributing

1. Follow the phase structure for new features
2. Add tests for all new code
3. Update documentation
4. Ensure ISO still builds
5. Run security checks before committing

---

## License

NeuronOS is released under GPL-3.0. See LICENSE file for details.
