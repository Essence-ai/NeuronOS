# Phase 1: Minimal Bootable ISO

**Status:** FOUNDATION - Establishes working base
**Estimated Time:** 1-2 days
**Prerequisites:** Phase 0 complete

---

## Recap: What We Are Building

**NeuronOS** is a consumer-grade Linux distribution providing seamless Windows/macOS software compatibility through:
- Native Linux apps (80% of use cases)
- Wine/Proton compatibility (15% of use cases)
- GPU passthrough VMs (5% of use cases - professional software)

**This Phase's Goal:** Create a minimal bootable ISO that:
1. Boots to a working desktop (LXQt)
2. Can be installed via Calamares
3. Has NeuronOS branding
4. Has NO custom NeuronOS features yet

---

## Why This Phase Matters

Many ISO builds fail because too many things are added at once. This phase establishes a **known working baseline**. Every future phase builds on this verified foundation.

**This phase is complete when you have an ISO that:**
- Boots in a VM
- Shows a desktop
- Can install to disk
- Reboots successfully after install

---

## Phase 1 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 1.1 | Clean iso-profile directory | Files match expected structure |
| 1.2 | Minimal packages.x86_64 | Only essential packages |
| 1.3 | Working profiledef.sh | ISO builds without errors |
| 1.4 | Bootable live environment | Boots in QEMU |
| 1.5 | Calamares installation works | Can install to disk |
| 1.6 | Post-install boot works | Installed system boots |

---

## Step 1.1: Clean the iso-profile Directory

The iso-profile may have accumulated broken configurations. Start fresh with a minimal setup.

### Action Required

1. **Read the current profiledef.sh**:
```bash
cat /home/user/NeuronOS/iso-profile/profiledef.sh
```

2. **Verify it has correct values**. The file should look like:

```bash
#!/usr/bin/env bash
# NeuronOS ISO Profile

iso_name="neuronos"
iso_label="NEURONOS_$(date +%Y%m)"
iso_publisher="NeuronOS Project"
iso_application="NeuronOS Live/Install"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito' 'uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
)
```

3. **If it differs significantly**, update it to match.

### Verification
```bash
# profiledef.sh should source without errors
bash -n /home/user/NeuronOS/iso-profile/profiledef.sh && echo "OK"
```

---

## Step 1.2: Create Minimal packages.x86_64

The packages.x86_64 file should contain ONLY packages needed to boot and install. We will add more in later phases.

### Action Required

1. **Read the current packages file**:
```bash
cat /home/user/NeuronOS/iso-profile/packages.x86_64 | head -50
```

2. **Create a minimal version** with only these packages:

```text
# Base System
base
linux
linux-firmware
mkinitcpio
mkinitcpio-archiso

# Boot
syslinux
efibootmgr
grub

# Essential System
sudo
networkmanager
dhcpcd
iwd

# Filesystem
btrfs-progs
dosfstools
e2fsprogs
ntfs-3g
xfsprogs

# Hardware
pciutils
usbutils

# Desktop (LXQt - lightweight)
xorg-server
xorg-xinit
lxqt
sddm
breeze-icons
ttf-dejavu

# Installer
calamares
os-prober
arch-install-scripts
rsync
squashfs-tools

# Basic Applications
firefox
konsole
dolphin
kate

# Archive
arch-install-scripts
```

3. **Write this minimal list** to packages.x86_64, replacing the old one.

### Verification
```bash
# Count packages (should be 35-50 for minimal)
wc -l /home/user/NeuronOS/iso-profile/packages.x86_64

# Check no broken package names (no tabs, no empty lines in middle)
grep -E "^[a-z0-9]" /home/user/NeuronOS/iso-profile/packages.x86_64 | wc -l
```

---

## Step 1.3: Configure pacman.conf

The pacman.conf must include [multilib] for Wine (needed in later phases).

### Action Required

1. **Check current pacman.conf**:
```bash
grep -E "^\[" /home/user/NeuronOS/iso-profile/pacman.conf
```

2. **Ensure these sections exist**:
- [core]
- [extra]
- [multilib]

3. **If [multilib] is missing or commented**, add it:
```ini
[multilib]
Include = /etc/pacman.d/mirrorlist
```

### Verification
```bash
grep -A1 "\[multilib\]" /home/user/NeuronOS/iso-profile/pacman.conf
# Should show [multilib] followed by Include line
```

---

## Step 1.4: Configure SDDM for Auto-Login

For live environment, SDDM should auto-login to the live user.

### Action Required

1. **Create SDDM config directory**:
```bash
mkdir -p /home/user/NeuronOS/iso-profile/airootfs/etc/sddm.conf.d/
```

2. **Create autologin config** at `airootfs/etc/sddm.conf.d/autologin.conf`:
```ini
[Autologin]
User=liveuser
Session=lxqt
```

3. **Create the liveuser** in `airootfs/etc/passwd` (append if exists):
```
liveuser:x:1000:1000:Live User:/home/liveuser:/bin/bash
```

4. **Create group entry** in `airootfs/etc/group` (append):
```
liveuser:x:1000:
```

5. **Create shadow entry** in `airootfs/etc/shadow` (append):
```
liveuser::14871::::::
```

6. **Add liveuser to sudoers** - create `airootfs/etc/sudoers.d/liveuser`:
```
liveuser ALL=(ALL) NOPASSWD: ALL
```

### Verification
```bash
ls -la /home/user/NeuronOS/iso-profile/airootfs/etc/sddm.conf.d/
cat /home/user/NeuronOS/iso-profile/airootfs/etc/sddm.conf.d/autologin.conf
```

---

## Step 1.5: Create Desktop Entries

Create a desktop shortcut for the installer.

### Action Required

1. **Create Desktop directory**:
```bash
mkdir -p /home/user/NeuronOS/iso-profile/airootfs/etc/skel/Desktop/
```

2. **Create installer shortcut** at `airootfs/etc/skel/Desktop/install-neuronos.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Install NeuronOS
Comment=Install NeuronOS to your computer
Exec=sudo calamares
Icon=calamares
Terminal=false
Categories=System;
```

3. **Make it executable** - add to file_permissions in profiledef.sh:
```bash
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/skel/Desktop/install-neuronos.desktop"]="0:0:755"
)
```

### Verification
```bash
cat /home/user/NeuronOS/iso-profile/airootfs/etc/skel/Desktop/install-neuronos.desktop
```

---

## Step 1.6: Configure Calamares

Calamares needs a basic configuration to work.

### Action Required

1. **Create Calamares directories**:
```bash
mkdir -p /home/user/NeuronOS/iso-profile/airootfs/etc/calamares/branding/neuronos/
mkdir -p /home/user/NeuronOS/iso-profile/airootfs/etc/calamares/modules/
```

2. **Create settings.conf** at `airootfs/etc/calamares/settings.conf`:
```yaml
---
modules-search: [ local, /usr/lib/calamares/modules ]

instances:
  - id: rootfs
    module: unpackfs
    config: unpackfs.conf

sequence:
  - show:
    - welcome
    - locale
    - keyboard
    - partition
    - users
    - summary
  - exec:
    - partition
    - mount
    - unpackfs
    - machineid
    - fstab
    - locale
    - keyboard
    - localecfg
    - users
    - networkcfg
    - hwclock
    - grubcfg
    - bootloader
    - umount
  - show:
    - finished

branding: neuronos
prompt-install: true
dont-chroot: false
disable-cancel: false
```

3. **Create branding.desc** at `airootfs/etc/calamares/branding/neuronos/branding.desc`:
```yaml
---
componentName: neuronos
welcomeStyleCalamares: true
strings:
    productName:         NeuronOS
    shortProductName:    NeuronOS
    version:             0.1.0
    shortVersion:        0.1
    versionedName:       NeuronOS 0.1.0
    shortVersionedName:  NeuronOS 0.1
    bootloaderEntryName: NeuronOS
    productUrl:          https://github.com/your-repo/neuronos
    supportUrl:          https://github.com/your-repo/neuronos/issues
    releaseNotesUrl:     https://github.com/your-repo/neuronos/releases

images:
    productLogo:         "logo.png"
    productIcon:         "logo.png"

slideshow:               "show.qml"

style:
   sidebarBackground:    "#2B2B2B"
   sidebarText:          "#FFFFFF"
   sidebarTextSelect:    "#4DD0E1"
```

4. **Create a placeholder logo** (we'll replace with real one later):
```bash
# Create a simple placeholder
cp /usr/share/icons/breeze/apps/48/system-software-install.svg /home/user/NeuronOS/iso-profile/airootfs/etc/calamares/branding/neuronos/logo.png 2>/dev/null || echo "Create logo manually"
```

5. **Create show.qml** at `airootfs/etc/calamares/branding/neuronos/show.qml`:
```qml
import QtQuick 2.0

Rectangle {
    id: root
    color: "#2B2B2B"

    Text {
        anchors.centerIn: parent
        text: "Installing NeuronOS..."
        color: "white"
        font.pixelSize: 24
    }
}
```

### Verification
```bash
ls -la /home/user/NeuronOS/iso-profile/airootfs/etc/calamares/
cat /home/user/NeuronOS/iso-profile/airootfs/etc/calamares/settings.conf
```

---

## Step 1.7: Build the ISO

Now build the ISO and verify it works.

### Action Required

```bash
cd /home/user/NeuronOS

# Clean any previous build artifacts
sudo rm -rf /tmp/neuronos-work /tmp/neuronos-out

# Build the ISO
sudo mkarchiso -v -w /tmp/neuronos-work -o /tmp/neuronos-out iso-profile/

# Check the ISO was created
ls -lh /tmp/neuronos-out/*.iso
```

### Expected Output
- Build should complete without errors
- ISO file should be 1-2 GB

### If Build Fails
Common issues:
1. **Package not found**: Remove the package from packages.x86_64 or fix the name
2. **Syntax error in profiledef.sh**: Check bash syntax
3. **Permission denied**: Use sudo

---

## Step 1.8: Test the ISO in QEMU

### Action Required

```bash
# Boot the ISO in QEMU (no KVM if nested virt not available)
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -cpu host \
  -smp 4 \
  -boot d \
  -cdrom /tmp/neuronos-out/neuronos-*.iso \
  -vga virtio \
  -display gtk
```

### What Should Happen
1. GRUB/bootloader appears
2. Linux boots
3. SDDM login screen appears (may auto-login)
4. LXQt desktop loads
5. "Install NeuronOS" icon is on desktop

### Verification Points
- [ ] ISO boots without kernel panic
- [ ] Desktop environment loads
- [ ] Can open terminal (Konsole)
- [ ] Can open file manager (Dolphin)
- [ ] Install icon exists on desktop

---

## Step 1.9: Test Calamares Installation

Test that the installer works by installing to a virtual disk.

### Action Required

```bash
# Create a virtual disk for installation
qemu-img create -f qcow2 /tmp/neuronos-test.qcow2 32G

# Boot with the disk attached
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -cpu host \
  -smp 4 \
  -boot d \
  -cdrom /tmp/neuronos-out/neuronos-*.iso \
  -drive file=/tmp/neuronos-test.qcow2,format=qcow2 \
  -vga virtio \
  -display gtk
```

### In the VM
1. Click "Install NeuronOS" on desktop
2. Follow Calamares wizard
3. Select the virtual disk for installation
4. Create a user
5. Complete installation
6. Reboot (remove ISO when prompted)

### After Reboot
```bash
# Boot from installed disk (no cdrom)
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -cpu host \
  -smp 4 \
  -drive file=/tmp/neuronos-test.qcow2,format=qcow2 \
  -vga virtio \
  -display gtk
```

### Verification Points
- [ ] Calamares launches without crash
- [ ] Can partition the disk
- [ ] Installation completes
- [ ] System reboots
- [ ] Installed system boots to login
- [ ] Can log in with created user
- [ ] Desktop loads after login

---

## Verification Checklist

### Phase 1 is COMPLETE when ALL boxes are checked:

**Build Success**
- [ ] `mkarchiso` completes without errors
- [ ] ISO file is created (1-2 GB)
- [ ] No package errors during build

**Live Environment**
- [ ] ISO boots in QEMU
- [ ] SDDM login appears (or auto-login works)
- [ ] LXQt desktop loads
- [ ] Terminal (Konsole) opens
- [ ] File manager (Dolphin) opens
- [ ] Network works (can ping)

**Installation**
- [ ] Calamares launches from desktop icon
- [ ] Partitioning works
- [ ] Installation completes without errors
- [ ] System reboots successfully

**Post-Install**
- [ ] Installed system boots (GRUB appears)
- [ ] Login screen appears
- [ ] Can log in with user created during install
- [ ] Desktop loads
- [ ] Firefox opens

---

## Troubleshooting

### "Package X not found"
Remove it from packages.x86_64 or check the exact package name with `pacman -Ss <name>`

### "SDDM doesn't start"
Check that xorg-server is in packages and sddm service is enabled. Add to airootfs:
```bash
mkdir -p airootfs/etc/systemd/system/display-manager.service.d/
ln -sf /usr/lib/systemd/system/sddm.service airootfs/etc/systemd/system/display-manager.service
```

### "Calamares crashes"
Check settings.conf for YAML syntax errors. Ensure all referenced modules exist.

### "No network after install"
Add NetworkManager to packages and enable it:
```bash
mkdir -p airootfs/etc/systemd/system/multi-user.target.wants/
ln -sf /usr/lib/systemd/system/NetworkManager.service airootfs/etc/systemd/system/multi-user.target.wants/
```

---

## What This Phase Does NOT Include

- No NeuronOS custom applications
- No VM manager
- No Wine/Proton
- No GPU passthrough
- No custom themes (default LXQt theme)
- No hardware detection
- No onboarding wizard

These are added in subsequent phases. This phase only establishes a **working bootable base**.

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 2: Hardware Detection](./PHASE_2_HARDWARE_DETECTION.md)**

Phase 2 will add the hardware detection module that identifies GPUs and IOMMU groups.
