# Phase 4: GPU Passthrough & Looking Glass

**Status:** ALREADY IMPLEMENTED (backend) - Verify end-to-end on real hardware
**Estimated Time:** 3-5 days (requires real multi-GPU hardware)
**Prerequisites:** Phase 3 complete (VM management verified)

---

## Why This Phase is NeuronOS's Key Differentiator

GPU passthrough gives VMs near-native GPU performance (98%+), enabling professional Windows software (Adobe Creative Suite, AutoCAD, SolidWorks) to run at full speed inside a Linux-hosted VM. Combined with Looking Glass for low-latency display, the user experience is seamless - Windows apps appear as if running natively.

This is what separates NeuronOS from ZorinOS, Linux Mint, and other consumer distros.

---

## What Already Exists

### Backend Code (All Production-Ready)

| File | Lines | What It Does |
|------|-------|-------------|
| `src/vm_manager/passthrough/gpu_attach.py` | 322 | Binds/unbinds GPUs to vfio-pci via sysfs |
| `src/vm_manager/core/looking_glass.py` | 430 | Manages Looking Glass client, shared memory |
| `src/vm_manager/core/guest_client.py` | 714 | TLS-encrypted communication with Windows guest agent |
| `src/vm_manager/core/vm_creator.py` | 312 | Creates VMs with IVSHMEM for Looking Glass |
| `src/hardware_detect/config_generator.py` | 469 | Generates VFIO configs, updates bootloader/initramfs |
| `src/guest_agent/` (C#) | 1,253 | Windows-side agent for host-guest communication |

### VM Templates with Passthrough

- `src/vm_manager/templates/windows10-passthrough.xml.j2`
- `src/vm_manager/templates/windows11-passthrough.xml.j2`

These templates include: GPU PCI device, IVSHMEM device for Looking Glass, virtio-serial for guest agent, TPM emulation (swtpm) for Win11.

### ISO Configuration

- `airootfs/etc/tmpfiles.d/10-looking-glass.conf` - Creates `/dev/shm/looking-glass` shared memory
- Looking Glass build dependencies in `packages.x86_64` (cmake, fontconfig, spice-protocol, etc.)

---

## Hardware Requirements

**You MUST have:**
1. **Two GPUs** - one for Linux display (iGPU or secondary), one for VM passthrough
2. **IOMMU enabled** in BIOS (Intel VT-d or AMD-Vi)
3. **Clean IOMMU group** for the passthrough GPU (verify with Phase 2)

```bash
# Quick check
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.config_generator import ConfigGenerator
gen = ConfigGenerator()
config = gen.detect_and_generate()
print(f'Passthrough GPU found: {bool(config.vfio_conf)}')
print(f'Kernel params: {config.kernel_params}')
"
```

---

## Phase 4 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 4.1 | VFIO config applied | GPU bound to vfio-pci after reboot |
| 4.2 | Passthrough VM boots | Windows VM gets dedicated GPU |
| 4.3 | Looking Glass displays VM | Host sees VM display via shared memory |
| 4.4 | Guest agent communicates | Can launch apps, sync clipboard |
| 4.5 | End-to-end workflow | User creates VM → GPU assigned → display works |

---

## Step 4.1: Apply VFIO Configuration

```bash
# Generate config (dry run)
cd /home/user/NeuronOS
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.config_generator import ConfigGenerator
gen = ConfigGenerator()
config = gen.detect_and_generate()
print('=== /etc/modprobe.d/vfio.conf ===')
print(config.vfio_conf)
print('=== mkinitcpio MODULES ===')
print(config.mkinitcpio_modules)
print('=== Kernel params ===')
print(config.kernel_params)
"

# Apply to system (CAUTION: changes bootloader)
sudo python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.config_generator import ConfigGenerator
gen = ConfigGenerator()
config = gen.detect_and_generate()
gen.apply(config, target_root='/')
"

# Regenerate initramfs and update bootloader
sudo mkinitcpio -P
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

### After Reboot, Verify
```bash
# Check GPU is bound to vfio-pci
lspci -nnk | grep -A3 "VGA\|3D"
# The passthrough GPU should show: Kernel driver in use: vfio-pci
```

---

## Step 4.2: Create Passthrough VM

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from vm_manager.core.vm_creator import VMCreator

creator = VMCreator()
# This uses the windows11-passthrough.xml.j2 template
# which includes GPU PCI device, IVSHMEM, virtio-serial
print('VMCreator available')
print(f'Template dir: {creator.template_dir}')
"
```

The passthrough template adds these devices to the VM XML:
- `<hostdev>` for the GPU PCI device
- `<shmem name="looking-glass">` for IVSHMEM (Looking Glass display)
- `<channel type="virtserial">` for guest agent communication
- `<tpm>` for Windows 11 TPM requirement

---

## Step 4.3: Looking Glass Integration

Looking Glass provides near-zero-latency display of the VM's GPU output on the host.

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from vm_manager.core.looking_glass import LookingGlassManager, LookingGlassConfig

config = LookingGlassConfig()
manager = LookingGlassManager(config)
print(f'Shared memory path: {config.shm_path}')
print(f'Default size: {config.shm_size_mb}MB')
print('Manager methods: start, stop, toggle_fullscreen, restart')
"
```

### Looking Glass Setup Requirements
1. **Build looking-glass-client** from source (deps already in packages.x86_64)
2. **Shared memory** created by `10-looking-glass.conf` tmpfiles rule
3. **IVSHMEM** device in VM XML (handled by passthrough template)
4. **Looking Glass Host** application running inside the Windows VM

---

## Step 4.4: Guest Agent

The guest agent (`src/guest_agent/` - C# for Windows) communicates with the host via virtio-serial with TLS encryption.

**Host side:** `src/vm_manager/core/guest_client.py` (714 lines)
- Binary framing protocol (STX/ETX) with JSON payloads
- TLS certificate generation and verification
- Commands: launch apps, manage windows, sync clipboard, sync resolution

**Guest side:** `src/guest_agent/NeuronGuest/` (C# - 1,253 lines)
- Runs as Windows service
- Listens on virtio-serial port
- Executes commands from host

### Building the Guest Agent
```bash
# Requires .NET SDK (build on a Windows machine or cross-compile)
cd src/guest_agent/NeuronGuest
dotnet publish -c Release -r win-x64 --self-contained
```

The compiled agent needs to be installed in the Windows VM during setup.

---

## Step 4.5: VFIO During Installation (Post-Install Hook)

When a user installs NeuronOS via archinstall, GPU passthrough should be configurable during or after installation. Since NeuronOS uses **archinstall** (not Calamares), the VFIO setup happens via:

1. **First-boot onboarding wizard** (Phase 7) detects hardware and offers to configure passthrough
2. **Manual CLI**: `sudo neuron-hardware-detect config --apply`
3. **VM Manager GUI**: detects available GPUs and configures on first VM creation

**Do NOT** create Calamares modules. NeuronOS does not use Calamares.

---

## Verification Checklist

- [ ] VFIO config generator produces correct PCI IDs
- [ ] After applying config and reboot, passthrough GPU shows `vfio-pci` driver
- [ ] Passthrough VM template renders valid XML with GPU device
- [ ] Looking Glass shared memory file exists at `/dev/shm/looking-glass`
- [ ] LookingGlassManager can launch the client
- [ ] Guest agent protocol classes import without error
- [ ] Windows VM boots with dedicated GPU (requires real hardware test)
- [ ] Looking Glass displays VM output on host

---

## Next Phase

Proceed to **[Phase 5: Wine, Proton & App Compatibility](./PHASE_5_WINE_PROTON.md)**
