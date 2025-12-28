# NeuronOS Dev Guide: Phase 0 — The Proof of Concept

**Duration:** 2 Weeks (Days 1-14)
**Developers Required:** 1
**Goal:** Manually achieve GPU passthrough with Looking Glass on a single test machine.

> [!IMPORTANT]
> **This phase is a GO/NO-GO gate.** If you cannot complete Phase 0 on your target hardware, the project scope must be adjusted. Do not proceed to Phase 1 until all acceptance criteria are met.

---

## Week 1: Hardware & Host Setup (Days 1-7)

---

### Day 1: Hardware Audit & BIOS Configuration

#### 🎫 Story 0.1.1: Hardware Inventory
**As a** Developer,
**I want** to document my exact hardware configuration,
**So that** I can troubleshoot issues and build a compatibility database.

**Acceptance Criteria:**
- [ ] Hardware specs documented in a `hardware_inventory.md` file.
- [ ] All PCI devices identified with their IOMMU group.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📝 Doc | Create `hardware_inventory.md` | Record: CPU Model, Motherboard, iGPU, dGPU, RAM, Storage |
| 2 | ⚙️ BIOS | Enter BIOS/UEFI Setup | Reboot, press DEL/F2 |
| 3 | ⚙️ BIOS | Enable Virtualization | Intel: `VT-x` / AMD: `SVM Mode` → **Enabled** |
| 4 | ⚙️ BIOS | Enable IOMMU | Intel: `VT-d` / AMD: `IOMMU` → **Enabled** |
| 5 | ⚙️ BIOS | Set Primary Display | Set to `IGFX` or `Integrated Graphics` |
| 6 | ⚙️ BIOS | Disable Secure Boot | Set to **Disabled** (temporary for development) |
| 7 | ⚙️ BIOS | Disable CSM/Legacy Boot | Ensure **UEFI Only** mode |
| 8 | 💾 Save | Save & Exit BIOS | F10 → Yes |

**Verification:**
```
After reboot, BIOS changes are persistent. System boots in UEFI mode.
```

---

### Day 2: Arch Linux Base Installation

#### 🎫 Story 0.1.2: Base System Install
**As a** Developer,
**I want** a minimal Arch Linux installation with Btrfs,
**So that** I have a clean slate for testing and future snapshot support.

**Acceptance Criteria:**
- [ ] Arch Linux boots via systemd-boot.
- [ ] Root filesystem is Btrfs with `@` and `@home` subvolumes.
- [ ] Network connectivity works.

**Tasks:**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 📥 Download | Get Arch ISO | https://archlinux.org/download/ |
| 2 | 💿 Boot | Boot from USB | Use Ventoy or `dd` to flash ISO |
| 3 | 🌐 Network | Connect to WiFi (if needed) | `iwctl station wlan0 connect "SSID"` |
| 4 | 💽 Partition | Create GPT partition table | `gdisk /dev/nvme0n1` → `o` (new GPT) |
| 5 | 💽 Partition | Create EFI partition (512MB) | Type `ef00`, Format: `mkfs.fat -F32` |
| 6 | 💽 Partition | Create Swap partition (4-8GB) | Type `8200`, Format: `mkswap` |
| 7 | 💽 Partition | Create Root partition (rest) | Type `8300`, Format: `mkfs.btrfs` |
| 8 | 📁 Subvol | Create Btrfs subvolumes | See code block below |
| 9 | 📁 Mount | Mount subvolumes | See code block below |
| 10 | 📦 Install | Pacstrap base system | `pacstrap -K /mnt base linux linux-firmware` |
| 11 | ⚙️ Config | Generate fstab | `genfstab -U /mnt >> /mnt/etc/fstab` |
| 12 | 🚪 Chroot | Enter chroot | `arch-chroot /mnt` |
| 13 | ⏰ Config | Set timezone | `ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime` |
| 14 | 🔤 Config | Set locale | Edit `/etc/locale.gen`, run `locale-gen` |
| 15 | 🖥️ Config | Set hostname | `echo "neuron-dev" > /etc/hostname` |
| 16 | 🔐 Config | Set root password | `passwd` |
| 17 | 👤 Config | Create user | `useradd -m -G wheel developer && passwd developer` |
| 18 | 📦 Install | Install essentials | `pacman -S sudo networkmanager vim git base-devel` |
| 19 | ⚙️ Config | Enable sudo for wheel | `EDITOR=vim visudo` → uncomment `%wheel ALL=(ALL:ALL) ALL` |
| 20 | 🚀 Boot | Install bootloader | See code block below |

**Btrfs Subvolume Creation:**
```bash
mount /dev/nvme0n1p3 /mnt
btrfs subvolume create /mnt/@
btrfs subvolume create /mnt/@home
btrfs subvolume create /mnt/@snapshots
umount /mnt
```

**Mounting Subvolumes:**
```bash
mount -o noatime,compress=zstd,subvol=@ /dev/nvme0n1p3 /mnt
mkdir -p /mnt/{boot,home,.snapshots}
mount -o noatime,compress=zstd,subvol=@home /dev/nvme0n1p3 /mnt/home
mount -o noatime,compress=zstd,subvol=@snapshots /dev/nvme0n1p3 /mnt/.snapshots
mount /dev/nvme0n1p1 /mnt/boot
```

**Bootloader Installation (systemd-boot):**
```bash
bootctl install
# Create loader entry
cat > /boot/loader/entries/arch.conf << EOF
title   Arch Linux
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=PARTUUID=$(blkid -s PARTUUID -o value /dev/nvme0n1p3) rootflags=subvol=@ rw
EOF
```

**Verification:**
```bash
exit  # Exit chroot
umount -R /mnt
reboot
# System should boot into Arch Linux TTY
```

---

### Day 3: Desktop Environment & IOMMU Verification

#### 🎫 Story 0.1.3: Desktop & IOMMU Enabled
**As a** Developer,
**I want** a graphical desktop running on my iGPU with IOMMU confirmed,
**So that** I can proceed with GPU isolation.

**Acceptance Criteria:**
- [ ] GNOME desktop loads on the integrated GPU.
- [ ] `dmesg | grep -i iommu` shows "IOMMU enabled".
- [ ] IOMMU groups are documented.

**Tasks:**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 🌐 Network | Enable NetworkManager | `systemctl enable --now NetworkManager` |
| 2 | 📦 Install | Install GNOME | `pacman -S gnome gnome-tweaks` |
| 3 | ⚙️ Service | Enable GDM | `systemctl enable gdm` |
| 4 | ⚙️ Kernel | Add IOMMU kernel params | Edit `/boot/loader/entries/arch.conf` |
| 5 | 🔄 Reboot | Reboot system | `reboot` |
| 6 | ✅ Verify | Check IOMMU status | `dmesg \| grep -i iommu` |
| 7 | 📝 Doc | Document IOMMU groups | Run IOMMU script below |

**Kernel Parameter Addition:**
Edit `/boot/loader/entries/arch.conf`, append to `options` line:
```
intel_iommu=on iommu=pt
```
*For AMD:* `amd_iommu=on iommu=pt`

**IOMMU Group Documentation Script:**
```bash
#!/bin/bash
# Save as ~/iommu_groups.sh and run with: bash ~/iommu_groups.sh
shopt -s nullglob
for g in $(find /sys/kernel/iommu_groups/* -maxdepth 0 -type d | sort -V); do
    echo "IOMMU Group ${g##*/}:"
    for d in $g/devices/*; do
        echo -e "\t$(lspci -nns ${d##*/})"
    done
done
```

**Expected Output (Example):**
```
IOMMU Group 1:
    00:02.0 VGA compatible controller [0300]: Intel Corporation ... [8086:3e92]
IOMMU Group 12:
    01:00.0 VGA compatible controller [0300]: NVIDIA Corporation ... [10de:1c03]
    01:00.1 Audio device [0403]: NVIDIA Corporation ... [10de:10f1]
```

> [!TIP]
> **Clean IOMMU Group Check:** If your dGPU shares an IOMMU group with other devices (USB controller, SATA), you may need the ACS Override Patch. This is advanced and should be noted in `hardware_inventory.md`.

---

### Day 4: VFIO Driver Binding

#### 🎫 Story 0.1.4: GPU Isolation
**As a** Developer,
**I want** my discrete GPU to be claimed by the VFIO driver at boot,
**So that** Linux doesn't use it and the VM can claim it later.

**Acceptance Criteria:**
- [ ] `lspci -nnk | grep -A 3 "VGA"` shows `vfio-pci` as the driver for the dGPU.
- [ ] Linux desktop still works on iGPU.
- [ ] No kernel errors related to VFIO.

**Tasks:**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 🔍 Identify | Get dGPU PCI IDs | `lspci -nn \| grep -i nvidia` (or amd) |
| 2 | 📝 Config | Create VFIO modprobe config | `/etc/modprobe.d/vfio.conf` |
| 3 | 📝 Config | Ensure VFIO loads early | `/etc/mkinitcpio.conf` MODULES line |
| 4 | 🔄 Rebuild | Regenerate initramfs | `mkinitcpio -P` |
| 5 | 🔄 Reboot | Reboot system | `reboot` |
| 6 | ✅ Verify | Check driver binding | `lspci -nnk \| grep -A 3 "NVIDIA"` |

**VFIO Modprobe Configuration:**
Create `/etc/modprobe.d/vfio.conf`:
```bash
# Replace with YOUR actual IDs from lspci -nn
options vfio-pci ids=10de:1c03,10de:10f1
softdep nvidia pre: vfio-pci
```

**Mkinitcpio Configuration:**
Edit `/etc/mkinitcpio.conf`:
```bash
# Add vfio modules BEFORE video drivers
MODULES=(vfio_pci vfio vfio_iommu_type1)
```

**Regenerate Initramfs:**
```bash
sudo mkinitcpio -P
```

**Verification After Reboot:**
```bash
lspci -nnk | grep -A 3 "NVIDIA"
# Expected output:
# 01:00.0 VGA compatible controller [0300]: NVIDIA Corporation ...
#     Subsystem: ...
#     Kernel driver in use: vfio-pci
```

---

### Day 5: Virtualization Stack Installation

#### 🎫 Story 0.1.5: QEMU/KVM Ready
**As a** Developer,
**I want** the full virtualization stack installed and configured,
**So that** I can create VMs.

**Acceptance Criteria:**
- [ ] `libvirtd` service is running.
- [ ] Current user can manage VMs without sudo.
- [ ] Virt-Manager launches successfully.

**Tasks:**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 📦 Install | Install virtualization packages | See package list below |
| 2 | ⚙️ Service | Enable libvirtd | `systemctl enable --now libvirtd` |
| 3 | 👤 Groups | Add user to libvirt group | `usermod -aG libvirt,kvm developer` |
| 4 | 🔐 Polkit | Configure polkit for libvirt | Create polkit rule |
| 5 | 🔄 Logout | Log out and back in | For group membership to apply |
| 6 | ✅ Verify | Launch Virt-Manager | `virt-manager` |

**Package Installation:**
```bash
sudo pacman -S qemu-full libvirt virt-manager dnsmasq edk2-ovmf swtpm
```

**Polkit Rule (Optional, for passwordless access):**
Create `/etc/polkit-1/rules.d/50-libvirt.rules`:
```javascript
polkit.addRule(function(action, subject) {
    if (action.id == "org.libvirt.unix.manage" &&
        subject.isInGroup("libvirt")) {
        return polkit.Result.YES;
    }
});
```

---

### Day 6-7: Asset Downloads & Windows VM Creation

#### 🎫 Story 0.1.6: Windows VM Base
**As a** Developer,
**I want** a Windows 11 VM with VirtIO drivers,
**So that** I can test GPU passthrough.

**Acceptance Criteria:**
- [ ] Windows 11 installed in VM.
- [ ] VirtIO drivers installed (network, storage work).
- [ ] VM boots reliably.

**Tasks (Day 6):**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📥 Download | Windows 11 LTSC ISO | https://massgrave.dev/windows_11_links |
| 2 | 📥 Download | VirtIO Drivers ISO | https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso |
| 3 | 📥 Download | Looking Glass Host | https://looking-glass.io/artifact/stable/host |
| 4 | 📁 Organize | Create ISO directory | `mkdir -p ~/ISOs && mv *.iso ~/ISOs/` |

**Tasks (Day 7) - VM Creation in Virt-Manager:**

| Step | Action | Setting |
|------|--------|---------|
| 1 | New VM | Local install media → Select Win11 ISO |
| 2 | Memory | 16384 MB (16 GB) |
| 3 | CPUs | 8 (or 50% of your cores) |
| 4 | Storage | Create 100GB qcow2 disk |
| 5 | ⚠️ Customize | Check "Customize configuration before install" |

**VM Customization (Critical):**

| Component | Change |
|-----------|--------|
| **Overview** | Firmware: `UEFI x86_64: /usr/share/edk2/x64/OVMF_CODE.4m.fd` |
| **Overview** | Chipset: `Q35` |
| **CPUs** | Topology: Manually set (e.g., 1 socket, 4 cores, 2 threads) |
| **CPUs** | Copy host CPU configuration: ✅ |
| **Disk** | Bus: `VirtIO` |
| **NIC** | Device model: `virtio` |
| **Add Hardware** | Storage: Add VirtIO ISO as CDROM |
| **Add Hardware** | TPM: Emulated, TIS, v2.0 |

**Windows Installation Notes:**
1. Boot VM → Windows Setup starts.
2. "I don't have a product key" → Select Windows 11 Pro.
3. Custom Install → No drives visible!
4. Load Driver → Browse to VirtIO CD → `amd64/w11` → Select `viostor` driver.
5. Drive now visible → Install Windows.
6. After install: Install all VirtIO drivers from Device Manager.

---

## Week 2: GPU Passthrough & Looking Glass (Days 8-14)

---

### Day 8-9: GPU Passthrough Configuration

#### 🎫 Story 0.2.1: GPU Passthrough
**As a** Developer,
**I want** to pass my dGPU directly to the Windows VM,
**So that** the VM has native GPU performance.

**Acceptance Criteria:**
- [ ] Windows VM boots with GPU passed through.
- [ ] Display output visible on dGPU's HDMI/DP port (or via dummy plug).
- [ ] GPU-Z in Windows shows correct GPU model.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | ⚙️ VM Config | Remove virtual display | Virt-Manager: Delete "Video QXL" and "Display Spice" |
| 2 | ⚙️ VM Config | Add dGPU Video | Add Hardware → PCI Host Device → Select dGPU VGA |
| 3 | ⚙️ VM Config | Add dGPU Audio | Add Hardware → PCI Host Device → Select dGPU Audio |
| 4 | 📝 XML | Edit VM XML (Critical) | Add vendor_id and hidden state |
| 5 | 🔌 Hardware | Connect display to dGPU | Use real monitor or HDMI dummy plug |
| 6 | ▶️ Boot | Start VM | Should display on dGPU output |
| 7 | ✅ Verify | Install GPU drivers | Download from NVIDIA/AMD in Windows |

**Critical XML Edits:**
Open VM XML: `sudo virsh edit win11`

1. **Add Hyper-V vendor_id (Anti-NVIDIA Code 43):**
```xml
<features>
  <hyperv>
    <vendor_id state='on' value='randomid'/>
  </hyperv>
  <kvm>
    <hidden state='on'/>
  </kvm>
</features>
```

2. **Ensure IOMMU is enabled:**
```xml
<iommu model='intel'/>
<!-- or model='amd' for AMD -->
```

**NVIDIA Code 43 Fix Checklist:**
- [ ] `vendor_id` is set
- [ ] `<hidden state='on'/>` under `<kvm>`
- [ ] Using Q35 chipset with OVMF
- [ ] Latest NVIDIA drivers installed in guest

---

### Day 10-11: Looking Glass Setup

#### 🎫 Story 0.2.2: Low-Latency Display Link
**As a** Developer,
**I want** to view the Windows VM in a Linux window via Looking Glass,
**So that** I don't need to switch monitors.

**Acceptance Criteria:**
- [ ] Looking Glass client shows Windows desktop.
- [ ] Latency < 20ms.
- [ ] Mouse/keyboard input works.

**Tasks (Day 10 - Host Side):**

| # | Type | Task | Command / Details |
|---|------|------|-------------------|
| 1 | 📦 Install | Install Looking Glass client | `yay -S looking-glass` (AUR) |
| 2 | 📝 Config | Create shared memory tmpfile | `/etc/tmpfiles.d/10-looking-glass.conf` |
| 3 | 🔄 Apply | Apply tmpfile config | `sudo systemd-tmpfiles --create` |
| 4 | 📝 XML | Add IVSHMEM device to VM | Edit VM XML |
| 5 | ✅ Verify | Check /dev/shm file exists | `ls -la /dev/shm/looking-glass` |

**Shared Memory Configuration:**
Create `/etc/tmpfiles.d/10-looking-glass.conf`:
```ini
# Type Path              Mode UID      GID  Age Argument
f /dev/shm/looking-glass 0660 developer kvm   -
```

**IVSHMEM Device XML:**
Add to VM XML inside `<devices>`:
```xml
<shmem name='looking-glass'>
  <model type='ivshmem-plain'/>
  <size unit='M'>64</size>
  <address type='pci' domain='0x0000' bus='0x10' slot='0x01' function='0x0'/>
</shmem>
```

**Tasks (Day 11 - Guest Side):**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📁 Copy | Copy Looking Glass Host to VM | Use shared folder or network |
| 2 | 📦 Install | Install IVSHMEM Driver | From VirtIO Drivers: `ivshmem` folder |
| 3 | 📦 Install | Install Looking Glass Host | Run `looking-glass-host-setup.exe` |
| 4 | ⚙️ Service | Verify service is running | Services → `Looking Glass (host)` → Running |
| 5 | ▶️ Boot | Restart VM | Ensure host service auto-starts |

**Testing Looking Glass:**
On Linux host:
```bash
looking-glass-client
```

**Common Issues:**
| Symptom | Solution |
|---------|----------|
| "Failed to open shared memory" | Check `/dev/shm/looking-glass` permissions |
| Black screen | Ensure Windows is sending frames (check host service) |
| High latency | Ensure dGPU is primary display in Windows display settings |

---

### Day 12-13: Performance Tuning & Validation

#### 🎫 Story 0.2.3: Performance Baseline
**As a** Developer,
**I want** to measure and optimize VM performance,
**So that** I can validate the "98%+ native" claim.

**Acceptance Criteria:**
- [ ] CPU pinning configured.
- [ ] Hugepages enabled.
- [ ] Benchmark results documented.

**Tasks:**

| # | Type | Task | Details |
|---|------|------|---------|
| 1 | 📝 XML | Configure CPU pinning | Match VM vCPUs to physical cores |
| 2 | 📝 Config | Enable Hugepages | `/etc/sysctl.d/` and VM XML |
| 3 | 📦 Install | Install benchmarks in Windows | GPU-Z, 3DMark Demo, Cinebench |
| 4 | 📊 Test | Run benchmarks | Document results |
| 5 | 📝 Doc | Compare to native Windows | Calculate overhead percentage |

**CPU Pinning XML:**
```xml
<vcpu placement='static'>8</vcpu>
<cputune>
  <vcpupin vcpu='0' cpuset='0'/>
  <vcpupin vcpu='1' cpuset='1'/>
  <vcpupin vcpu='2' cpuset='2'/>
  <vcpupin vcpu='3' cpuset='3'/>
  <vcpupin vcpu='4' cpuset='4'/>
  <vcpupin vcpu='5' cpuset='5'/>
  <vcpupin vcpu='6' cpuset='6'/>
  <vcpupin vcpu='7' cpuset='7'/>
  <emulatorpin cpuset='8-9'/>
</cputune>
```

**Hugepages Configuration:**
```bash
# /etc/sysctl.d/40-hugepages.conf
vm.nr_hugepages = 8192  # 16GB for VM (8192 * 2MB)
```

**VM XML Hugepages:**
```xml
<memoryBacking>
  <hugepages/>
</memoryBacking>
```

---

### Day 14: Documentation & Phase 0 Sign-off

#### 🎫 Story 0.2.4: Phase Complete
**As a** Project Lead,
**I want** all Phase 0 learnings documented,
**So that** we can proceed to automation.

**Acceptance Criteria:**
- [ ] `phase_0_results.md` created with all configs.
- [ ] All XML configs backed up.
- [ ] GO/NO-GO decision made.

**Deliverables Checklist:**

| Document | Contents |
|----------|----------|
| `hardware_inventory.md` | Full hardware specs, IOMMU groups |
| `vm_config.xml` | Complete VM XML for reference |
| `benchmark_results.md` | Comparative benchmarks |
| `known_issues.md` | Any workarounds needed |

**Phase 0 Exit Criteria:**
- [ ] Windows 11 VM boots with GPU passthrough
- [ ] Looking Glass displays VM with < 20ms latency
- [ ] Adobe Photoshop (trial) runs and is GPU-accelerated
- [ ] Benchmark overhead < 5% compared to bare metal

---

# Phase 0 Complete ✅

**If all criteria are met:** Proceed to [Phase 1 Dev Guide](file:///C:/Users/jasbh/.gemini/antigravity/brain/19c55c70-6e71-40e5-9eed-2f5494130b35/dev_guide_phase_1.md)

**If criteria NOT met:** Document blockers in `known_issues.md` and evaluate:
- Hardware incompatibility → Different test machine needed
- IOMMU group issues → Research ACS Override Patch
- Performance issues → Investigate CPU/RAM bottlenecks
