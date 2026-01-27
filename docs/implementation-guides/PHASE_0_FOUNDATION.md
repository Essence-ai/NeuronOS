# Phase 0: Foundation & Environment Setup

**Status:** PREREQUISITE - Must complete before any development
**Estimated Time:** 2-4 hours
**Prerequisites:** None

---

## What We Are Building

**NeuronOS** is a consumer-grade Linux distribution that makes it easy for anyone (from grandma to enterprise users) to:

1. Install Linux with a single-click experience like Windows/macOS
2. Run Windows programs seamlessly via GPU passthrough VMs (for Adobe, AutoCAD, etc.)
3. Run simpler Windows apps via Wine/Proton
4. Optionally run macOS in a VM

**This Phase's Goal:** Establish a verified working development environment where all dependencies are installed and basic operations work.

---

## Phase 0 Objectives

This phase ensures your development environment is ready. You will NOT write any code yet - you will only verify that everything works.

### What Must Be Verified

| Check | Description | Command |
|-------|-------------|---------|
| Arch ISO builds | Can build a basic Arch ISO | `mkarchiso` |
| libvirt works | Can connect to libvirt | `virsh list --all` |
| QEMU works | QEMU is installed | `qemu-system-x86_64 --version` |
| Python 3.11+ | Correct Python version | `python --version` |
| Git configured | Can commit/push | `git status` |
| Test VM boots | A test VM can run | Manual test |

---

## Step-by-Step Verification

### 0.1 System Package Verification

Run these commands and verify the output:

```bash
# Check Arch system
cat /etc/os-release | grep -E "^(NAME|VERSION)"
# Expected: Arch Linux or similar

# Check Python version
python3 --version
# Expected: Python 3.11.x or higher

# Check essential packages
pacman -Q archiso qemu-full libvirt virt-manager dnsmasq ebtables 2>/dev/null || echo "MISSING PACKAGES"
```

**If packages are missing, install them:**
```bash
sudo pacman -Syu --needed archiso qemu-full libvirt virt-manager dnsmasq ebtables python python-pip python-gobject python-jinja libvirt-python
```

### 0.2 Libvirt Service Verification

```bash
# Check libvirt is running
sudo systemctl status libvirtd --no-pager
# Expected: Active: active (running)

# If not running:
sudo systemctl enable --now libvirtd

# Add user to libvirt group
sudo usermod -aG libvirt $USER
# NOTE: You must log out and back in for this to take effect

# Test connection
virsh -c qemu:///system list --all
# Expected: Shows list (may be empty) without errors
```

### 0.3 Python Environment Verification

```bash
# Navigate to project
cd /home/user/NeuronOS

# Check Python can import key libraries
python3 -c "import libvirt; print('libvirt OK')"
python3 -c "import gi; gi.require_version('Gtk', '4.0'); print('GTK4 OK')"
python3 -c "from jinja2 import Template; print('Jinja2 OK')"
python3 -c "from pathlib import Path; print('Python OK')"
```

### 0.4 IOMMU Verification (Hardware Check)

This checks if GPU passthrough is possible on your hardware:

```bash
# Check if IOMMU is enabled in kernel
dmesg | grep -i -E "IOMMU|DMAR" | head -5
# Expected: Lines containing "IOMMU enabled" or "DMAR" entries

# List IOMMU groups
ls /sys/kernel/iommu_groups/ | wc -l
# Expected: A number > 0 (if IOMMU is enabled)

# List GPUs
lspci | grep -E "VGA|3D"
# Expected: At least one GPU listed
```

**If IOMMU is not enabled:**
1. This is a BIOS setting - enable Intel VT-d or AMD-Vi
2. Add kernel parameter: `intel_iommu=on` or `amd_iommu=on`
3. Reboot and verify again

### 0.5 Archiso Build Test

This verifies you can build an ISO:

```bash
# Create a temporary test profile
cd /tmp
cp -r /usr/share/archiso/configs/releng test-iso-profile
cd test-iso-profile

# Build minimal ISO (this takes 5-15 minutes)
sudo mkarchiso -v -w /tmp/work -o /tmp/out .

# Verify ISO was created
ls -lh /tmp/out/*.iso
# Expected: An ISO file of 600MB-1GB

# Cleanup
sudo rm -rf /tmp/work /tmp/out /tmp/test-iso-profile
```

### 0.6 Project Structure Verification

Verify the NeuronOS project has expected structure:

```bash
cd /home/user/NeuronOS

# Check key directories exist
ls -d src/hardware_detect src/vm_manager src/store src/onboarding iso-profile templates tests 2>/dev/null || echo "MISSING DIRECTORIES"

# Check key files exist
ls src/hardware_detect/gpu_scanner.py src/vm_manager/core/libvirt_manager.py iso-profile/packages.x86_64 2>/dev/null || echo "MISSING FILES"

# Check tests can run (even if they fail)
python -m pytest tests/ --collect-only 2>/dev/null | head -10
```

---

## Verification Checklist

Before proceeding to Phase 1, ALL boxes must be checked:

### System Requirements
- [ ] Running Arch Linux (or Arch-based distro)
- [ ] Python 3.11+ installed
- [ ] archiso package installed
- [ ] qemu-full package installed
- [ ] libvirt package installed
- [ ] libvirtd service running
- [ ] User is in libvirt group

### Functionality Tests
- [ ] `virsh list --all` works without sudo
- [ ] Python can import libvirt module
- [ ] Python can import GTK4 (gi.require_version('Gtk', '4.0'))
- [ ] A test archiso build completes successfully
- [ ] IOMMU groups exist (or documented reason why not)
- [ ] At least one GPU is detected

### Project Structure
- [ ] NeuronOS repo is cloned and accessible
- [ ] src/ directory contains all modules
- [ ] iso-profile/ directory exists with packages.x86_64
- [ ] tests/ directory exists

---

## Troubleshooting Common Issues

### "virsh: command not found"
```bash
sudo pacman -S libvirt
sudo systemctl enable --now libvirtd
```

### "error: failed to connect to the hypervisor"
```bash
sudo systemctl restart libvirtd
sudo usermod -aG libvirt $USER
# Log out and back in
```

### "No IOMMU groups found"
1. Enter BIOS and enable Intel VT-d or AMD-Vi
2. Add kernel parameter to bootloader:
   - For GRUB: Edit `/etc/default/grub`, add `intel_iommu=on` to `GRUB_CMDLINE_LINUX_DEFAULT`
   - Run `sudo grub-mkconfig -o /boot/grub/grub.cfg`
   - Reboot

### "mkarchiso fails with permission denied"
```bash
sudo mkarchiso ...  # Always run with sudo
```

---

## What NOT to Do in Phase 0

- Do NOT modify any code yet
- Do NOT try to build the NeuronOS ISO yet
- Do NOT configure VFIO yet
- Do NOT install themes or customizations

Phase 0 is purely about verification. Code changes begin in Phase 1.

---

## Completion Criteria

**Phase 0 is complete when:**

1. All items in the Verification Checklist are checked
2. You can run `virsh list --all` without errors
3. A test archiso build succeeds
4. Python can import all required modules
5. You understand what NeuronOS is building

---

## Next Phase

Once all verifications pass, proceed to **[Phase 1: Minimal Bootable ISO](./PHASE_1_MINIMAL_ISO.md)**

Phase 1 will create a basic bootable NeuronOS ISO without any custom features - just a working foundation.
