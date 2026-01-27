# Phase 4.4: ISO Build & Validation Testing

**Status**: 🟡 ISO BUILDS - But doesn't fully work end-to-end
**Estimated Time**: 1-2 days ongoing
**Prerequisites**: All Phases 1-4.3 complete

---

## What is ISO Validation?

ISO validation ensures the installation media works reliably across hardware and VM environments. Tests cover:
- **Build process** - ISO builds without errors
- **Boot compatibility** - BIOS and UEFI
- **Live environment** - Desktop, onboarding launch
- **Installation** - Full system install succeeds
- **First boot** - Services start, GUI loads

**Without validation**: Users download broken ISOs, install fails.
**With validation**: Every release is tested before distribution.

---

## Current State

### What Works ✅
- ✅ ISO builds with Arch Linux tools
- ✅ Boots in VMs (QEMU/VirtualBox)

### What Needs Testing ❌

| Test Area | Risk | Current Status |
|---|---|---|
| **UEFI boot** | Won't boot on modern hardware | Untested |
| **Secure Boot** | Rejected by firmware | Untested |
| **Hardware compatibility** | Drivers missing | Limited testing |
| **Onboarding wizard** | Doesn't launch | Untested on ISO |
| **Network** | No connectivity | Works in VMs, untested on hardware |
| **Persistence** | Settings don't save | Untested |

---

## Objective: Production-Ready ISOs

1. ✅ **Clean builds** - No errors, reproducible
2. ✅ **Boot everywhere** - BIOS, UEFI, Secure Boot
3. ✅ **Hardware support** - WiFi, Ethernet, GPUs detected
4. ✅ **Live environment works** - Desktop, apps launch
5. ✅ **Installation succeeds** - To disk, preserves settings
6. ✅ **First boot clean** - No errors, onboarding runs

---

## Part 1: ISO Build Process

**File**: `build/build-iso.sh`

```bash
#!/bin/bash
# NeuronOS ISO builder

set -e  # Exit on error

echo "=== Building NeuronOS ISO ==="

# 1. Clean previous builds
rm -rf build/iso build/work

# 2. Create directory structure
mkdir -p build/iso/{EFI/boot,loader/entries,arch/boot/x86_64,neuronos}

# 3. Install base system
pacstrap -c build/work base base-devel linux linux-firmware

# 4. Copy NeuronOS code
cp -r src/ build/work/usr/lib/neuronos/

# 5. Install dependencies
arch-chroot build/work pacman -S --noconfirm \
    qemu libvirt virt-manager \
    gtk4 libadwaita python-gobject \
    wine proton looking-glass

# 6. Configure services
arch-chroot build/work systemctl enable libvirtd NetworkManager gdm neuronos

# 7. Create squashfs
mksquashfs build/work build/iso/arch/boot/x86_64/airootfs.sfs \
    -comp xz -b 1M -Xdict-size 100%

# 8. Create bootloader
cp /usr/lib/systemd/boot/efi/systemd-bootx64.efi build/iso/EFI/boot/bootx64.efi

cat > build/iso/loader/entries/neuronos.conf <<EOF
title NeuronOS
linux /arch/boot/x86_64/vmlinuz-linux
initrd /arch/boot/x86_64/initramfs-linux.img
options archisobasedir=arch archisolabel=NEURONOS quiet splash
EOF

# 9. Create ISO
xorriso -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid "NEURONOS" \
    -eltorito-boot isolinux/isolinux.bin \
    -eltorito-catalog isolinux/boot.cat \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -isohybrid-mbr /usr/lib/syslinux/bios/isohdpfx.bin \
    -eltorito-alt-boot \
    -e EFI/boot/bootx64.efi \
    -no-emul-boot -isohybrid-gpt-basdat \
    -output neuronos-$(date +%Y.%m.%d)-x86_64.iso \
    build/iso

echo "✅ ISO built: neuronos-$(date +%Y.%m.%d)-x86_64.iso"
```

---

## Part 2: Automated ISO Testing

**File**: `tests/iso/test_iso_boot.py`

```python
"""Automated ISO boot testing."""

import subprocess
import time
from pathlib import Path

def test_iso_boots_uefi():
    """Test ISO boots in UEFI mode."""
    iso_path = Path("neuronos-latest.iso")
    assert iso_path.exists(), "ISO not found"

    # Start QEMU with UEFI
    proc = subprocess.Popen([
        "qemu-system-x86_64",
        "-enable-kvm",
        "-m", "4G",
        "-bios", "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd",
        "-cdrom", str(iso_path),
        "-boot", "d",
        "-display", "none",  # Headless
        "-serial", "stdio",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for boot
    time.sleep(30)

    # Check if still running (didn't crash)
    assert proc.poll() is None, "QEMU crashed during boot"

    # Cleanup
    proc.terminate()
    proc.wait()

def test_iso_size():
    """Test ISO is reasonable size."""
    iso_path = Path("neuronos-latest.iso")
    size_gb = iso_path.stat().st_size / (1024**3)

    assert 2.0 < size_gb < 4.0, f"ISO size {size_gb:.2f}GB out of range (expect 2-4GB)"

def test_iso_contains_files():
    """Test ISO contains required files."""
    # Mount ISO and check contents
    result = subprocess.run([
        "isoinfo", "-l", "-i", "neuronos-latest.iso"
    ], capture_output=True, text=True)

    contents = result.stdout

    assert "/EFI/boot/bootx64.efi" in contents, "Missing UEFI bootloader"
    assert "/arch/boot/x86_64/vmlinuz" in contents, "Missing kernel"
    assert "/arch/boot/x86_64/initramfs" in contents, "Missing initramfs"
```

---

## Part 3: Manual Testing Checklist

**File**: `docs/ISO_TESTING_CHECKLIST.md`

```markdown
# ISO Testing Checklist

## Before Release

Test each ISO on:

### Virtual Machines
- [ ] QEMU/KVM (BIOS)
- [ ] QEMU/KVM (UEFI)
- [ ] VirtualBox
- [ ] VMware Workstation

### Real Hardware
- [ ] Desktop (AMD CPU + NVIDIA GPU)
- [ ] Desktop (Intel CPU + AMD GPU)
- [ ] Laptop (Intel + iGPU only)
- [ ] Laptop (Dual GPU: iGPU + dGPU)
- [ ] Server (Xeon, no GPU)

## Boot Tests

- [ ] BIOS boot successful
- [ ] UEFI boot successful
- [ ] Secure Boot (if signed)
- [ ] Boot from USB
- [ ] Boot from DVD

## Live Environment

- [ ] Desktop loads (GDM/GNOME)
- [ ] WiFi connects
- [ ] Ethernet connects
- [ ] Sound works
- [ ] Keyboard/mouse work
- [ ] Multiple monitors detected

## Onboarding

- [ ] Wizard launches automatically
- [ ] Hardware detection works
- [ ] GPU list populated
- [ ] Can create Windows VM
- [ ] Can migrate files
- [ ] Installation completes

## Post-Install

- [ ] Reboot successful
- [ ] Settings preserved
- [ ] Network still works
- [ ] VMs start
- [ ] Looking Glass works (if GPU passed)

## Known Issues

Document any failures:
- Hardware model:
- Issue:
- Workaround:
```

---

## Part 4: CI/CD ISO Builds

**File**: `.github/workflows/build-iso.yml`

```yaml
name: Build ISO

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: archlinux:latest

    steps:
    - uses: actions/checkout@v3

    - name: Install build dependencies
      run: |
        pacman -Syu --noconfirm
        pacman -S --noconfirm archiso xorriso

    - name: Build ISO
      run: |
        bash build/build-iso.sh

    - name: Test ISO boots
      run: |
        pytest tests/iso/

    - name: Upload ISO
      uses: actions/upload-artifact@v3
      with:
        name: neuronos-iso
        path: neuronos-*.iso

    - name: Create Release
      if: startsWith(github.ref, 'refs/tags/')
      uses: softprops/action-gh-release@v1
      with:
        files: neuronos-*.iso
```

---

## Verification Checklist

- [ ] **ISO builds successfully** - No errors in build log
- [ ] **Boots on diverse hardware** - BIOS, UEFI, real hardware
- [ ] **Desktop launches** - GDM, GNOME load
- [ ] **Onboarding runs end-to-end** - Wizard completes
- [ ] **Can create + start VM** - Test VM boots
- [ ] **Known issues documented** - Compatibility notes

---

## Acceptance Criteria

✅ **Complete when**:
1. ISO builds reproducibly
2. Boots on 5+ hardware configs
3. Onboarding completes without errors
4. VMs can be created and started
5. Release notes document known issues

❌ **Fails if**:
1. ISO doesn't build
2. Fails to boot on common hardware
3. Onboarding crashes
4. Can't create VMs
5. No documentation of limitations

---

## Resources

- [Arch ISO Building](https://wiki.archlinux.org/title/Archiso)
- [UEFI Boot Process](https://wiki.osdev.org/UEFI)
- [ISO Testing Best Practices](https://fedoraproject.org/wiki/QA:Testcase_ISO_size)

Good luck! 🚀
