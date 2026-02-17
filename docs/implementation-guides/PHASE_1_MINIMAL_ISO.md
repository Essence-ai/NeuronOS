# Phase 1: Bootable NeuronOS ISO

**Status:** FOUNDATION - Establishes working base
**Estimated Time:** 1-2 days
**Prerequisites:** Phase 0 complete

---

## Recap: What We Are Building

**NeuronOS** is a consumer-grade Linux distribution providing seamless Windows/macOS software compatibility through:
- Native Linux apps (80% of use cases)
- Wine/Proton compatibility (15% of use cases)
- GPU passthrough VMs (5% of use cases - professional software)

**This Phase's Goal:** Create a bootable ISO that:
1. Boots to a working GNOME desktop
2. Can be installed via archinstall
3. Has NeuronOS branding, themes, and wallpaper
4. Includes all NeuronOS entry points (VM Manager, Store, Hardware Detect)
5. Has GDM auto-login for the live session

---

## Why This Phase Matters

This phase establishes a **known working baseline**. Every future phase builds on this verified foundation.

**IMPORTANT:** Do NOT strip down the codebase to a "minimal" package list. The existing packages and configurations represent the full NeuronOS feature set. Removing packages (virtualization, Wine, GPU drivers) will break the integration that makes NeuronOS unique.

**This phase is complete when you have an ISO that:**
- Boots in a VM (QEMU)
- Shows the GNOME desktop with NeuronOS theming
- Can install to disk via archinstall
- Reboots successfully after install

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Desktop Environment | **GNOME** | GTK4 themes, Zenity dialogs, modern touch support, Wayland-ready |
| Display Manager | **GDM** | Native GNOME integration, auto-login support |
| Installer | **archinstall** | Available in Arch repos, no AUR dependency |
| Theme Engine | **GTK4 CSS** | Three themes: Neural, Clarity, Frost |
| Boot Modes | **BIOS (syslinux) + UEFI (GRUB)** | Maximum hardware compatibility |

---

## Phase 1 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 1.1 | Clean iso-profile with no conflicts | No duplicate packages, consistent DE choice |
| 1.2 | GNOME desktop with GDM auto-login | Live session boots to desktop automatically |
| 1.3 | All desktop shortcuts work | Terminal, File Manager, System Monitor launch |
| 1.4 | NeuronOS branding present | Wallpaper, themes, logo visible |
| 1.5 | archinstall works from desktop | Can install to disk |
| 1.6 | Post-install boot works | Installed system boots |

---

## Step 1.1: Verify iso-profile Configuration

### profiledef.sh

The file should define:
- `iso_name="neuronos"`
- Boot modes for both BIOS and UEFI
- squashfs with xz compression
- File permissions for NeuronOS entry points

### packages.x86_64

Must include these categories (do NOT remove any):
- **Base system**: base, linux, linux-firmware, sudo, networkmanager
- **Bootloader**: grub, efibootmgr, os-prober
- **GNOME Desktop**: gdm, gnome, gnome-extra, gnome-terminal, gnome-tweaks, zenity
- **Virtualization**: qemu-full, libvirt, virt-manager, edk2-ovmf
- **GPU Drivers**: mesa, vulkan-icd-loader, Intel + AMD drivers
- **Wine**: wine, wine-mono, wine-gecko, winetricks
- **Python**: python, python-pyqt6, libvirt-python, python-gobject
- **Looking Glass deps**: cmake, fontconfig, spice-protocol
- **Audio**: pipewire stack
- **Flatpak**: flatpak, xdg-desktop-portal-gnome

### Verification
```bash
# Check no duplicate packages
sort iso-profile/packages.x86_64 | grep -v '^#' | grep -v '^$' | uniq -d
# Expected: no output (no duplicates)

# Check profiledef.sh syntax
bash -n iso-profile/profiledef.sh && echo "OK"
```

---

## Step 1.2: Configure GDM Auto-Login

GDM must auto-login the liveuser for the live session.

### Required File: `airootfs/etc/gdm/custom.conf`
```ini
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=liveuser
WaylandEnable=false

[security]

[xdmcp]

[chooser]

[debug]
```

### Required: systemd service symlink
The build script must create:
```bash
ln -sf /usr/lib/systemd/system/gdm.service airootfs/etc/systemd/system/display-manager.service
```

### Verification
```bash
cat iso-profile/airootfs/etc/gdm/custom.conf | grep AutomaticLogin
# Expected: AutomaticLoginEnable=True and AutomaticLogin=liveuser
```

---

## Step 1.3: Configure Desktop Shortcuts

All desktop shortcuts must reference GNOME applications (NOT LXQt applications).

### Desktop Entries in `airootfs/etc/skel/Desktop/`

| Shortcut | Exec Command | Icon |
|----------|-------------|------|
| Install NeuronOS | `gnome-terminal -- bash -c "sudo archinstall..."` | system-software-install |
| File Manager | `nautilus` | org.gnome.Nautilus |
| Terminal | `gnome-terminal` | org.gnome.Terminal |
| System Monitor | `gnome-system-monitor` | org.gnome.SystemMonitor |
| NeuronVM Manager | `neuron-vm-manager` | virt-manager |
| NeuronStore | `neuron-store` | gnome-software |

### Verification
```bash
grep -r "qterminal\|pcmanfm-qt\|sddm\|lxqt" iso-profile/airootfs/
# Expected: no output (no LXQt references remaining)
```

---

## Step 1.4: Configure GNOME Defaults via dconf

### Required File: `airootfs/etc/dconf/profile/user`
```
user-db:user
system-db:local
```

### Required File: `airootfs/etc/dconf/db/local.d/00-neuronos`
Sets defaults for:
- Dark theme (materia-dark)
- NeuronOS wallpaper
- Window button layout (minimize, maximize, close)
- Favorite apps in dock
- Tap-to-click on touchpad
- No screen lock in live session

---

## Step 1.5: NeuronOS Welcome Script

The `neuron-welcome` script (`airootfs/usr/bin/neuron-welcome`) runs on first login via XDG autostart and:
1. Shows a theme selection dialog (Neural / Clarity / Frost)
2. Applies the selected GTK4 CSS theme
3. Optionally launches archinstall

This script uses Zenity (GNOME dialog tool) and gnome-terminal.

---

## Step 1.6: Build the ISO

```bash
cd /home/user/NeuronOS

# Using the build script (recommended)
sudo ./build-iso.sh --clean

# Or using the scripts directory version
sudo ./scripts/build-iso.sh

# Or using make
sudo make iso
```

### What the Build Does
1. Copies Python source modules to `airootfs/usr/lib/neuron-os/`
2. Creates systemd service symlinks (GDM, NetworkManager, libvirtd)
3. Copies skel configs to liveuser home
4. Applies default Neural theme to liveuser
5. Runs `mkarchiso` to produce the ISO

### Expected Output
- Build completes without errors
- ISO file is 2-4 GB (full GNOME + virtualization stack)

### If Build Fails
1. **Package not found**: Check exact package name with `pacman -Ss <name>`
2. **Syntax error in profiledef.sh**: Run `bash -n iso-profile/profiledef.sh`
3. **Permission denied**: Run with sudo
4. **Disk space**: Needs ~15GB free in /tmp

---

## Step 1.7: Test the ISO in QEMU

```bash
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -cpu host \
  -smp 4 \
  -boot d \
  -cdrom out/neuronos-*.iso \
  -vga virtio \
  -display gtk
```

### What Should Happen
1. GRUB bootloader appears with NeuronOS entries
2. Linux boots
3. GDM auto-logs in as liveuser
4. GNOME desktop loads with NeuronOS wallpaper
5. Welcome dialog appears with theme selection
6. Desktop shortcuts are visible

---

## Step 1.8: Test Installation

```bash
# Create a virtual disk
qemu-img create -f qcow2 /tmp/neuronos-test.qcow2 32G

# Boot with disk attached
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \
  -cpu host \
  -smp 4 \
  -boot d \
  -cdrom out/neuronos-*.iso \
  -drive file=/tmp/neuronos-test.qcow2,format=qcow2 \
  -vga virtio \
  -display gtk
```

### In the VM
1. Click "Install NeuronOS" on desktop
2. Follow archinstall wizard in terminal
3. Select the virtual disk
4. Complete installation and reboot

---

## Verification Checklist

### Phase 1 is COMPLETE when ALL boxes are checked:

**Build Success**
- [ ] ISO builds without errors
- [ ] ISO file is created (2-4 GB)
- [ ] No package errors during build

**Live Environment**
- [ ] ISO boots in QEMU
- [ ] GDM auto-login works (no login prompt)
- [ ] GNOME desktop loads
- [ ] NeuronOS wallpaper is visible
- [ ] Welcome dialog appears with theme selection

**Desktop Shortcuts**
- [ ] Terminal (gnome-terminal) opens
- [ ] File Manager (nautilus) opens
- [ ] System Monitor (gnome-system-monitor) opens
- [ ] NeuronVM Manager launches (or shows error if libvirtd not running)
- [ ] NeuronStore launches

**Installation**
- [ ] archinstall launches from desktop icon
- [ ] Installation completes without errors
- [ ] System reboots successfully

**Post-Install**
- [ ] GRUB appears
- [ ] Login screen appears
- [ ] Can log in
- [ ] Desktop loads
- [ ] Firefox opens

**No LXQt Remnants**
- [ ] No references to qterminal, pcmanfm-qt, sddm, or lxqt in airootfs
- [ ] No .config/lxqt/ directories
- [ ] No SDDM configuration files

---

## Troubleshooting

### "GDM doesn't auto-login"
Check `airootfs/etc/gdm/custom.conf` has `AutomaticLoginEnable=True` and `AutomaticLogin=liveuser`.

### "GNOME shows default wallpaper"
Check dconf database at `airootfs/etc/dconf/db/local.d/00-neuronos` and verify the wallpaper path.

### "Desktop shortcuts don't work"
Verify `Exec=` lines use GNOME applications (gnome-terminal, nautilus, gnome-system-monitor).

### "archinstall fails with key errors"
The install script initializes pacman keys first. If it still fails, run manually:
```bash
sudo pacman-key --init
sudo pacman-key --populate archlinux
```

### "No network after install"
Verify NetworkManager service is enabled in the build script.

---

## What This Phase Establishes

- A bootable ISO with GNOME desktop and NeuronOS branding
- GDM auto-login for live session
- Theme selection (Neural / Clarity / Frost)
- Working desktop shortcuts for GNOME apps and NeuronOS tools
- archinstall-based installation
- All NeuronOS Python modules copied to the ISO
- Virtualization, Wine, and GPU driver packages pre-installed

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 2: Hardware Detection](./PHASE_2_HARDWARE_DETECTION.md)**

Phase 2 will add the hardware detection module that identifies GPUs and IOMMU groups.
