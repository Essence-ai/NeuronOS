# Phase 5: GPU Passthrough & Looking Glass

**Status:** ADVANCED FEATURE - The key differentiator
**Estimated Time:** 5-7 days
**Prerequisites:** Phase 4 complete (Wine/Proton working)

---

## Recap: What We Are Building

**NeuronOS** is differentiated by its ability to run Windows professional software (Adobe, AutoCAD) at near-native performance through GPU passthrough. This phase makes that possible.

**This Phase's Goal:**
1. Apply VFIO configuration to bind GPU to vfio-pci
2. Create VMs with GPU passthrough enabled
3. Install and configure Looking Glass for low-latency display
4. Enable seamless integration between Linux host and Windows guest

---

## Why This Phase Matters

GPU passthrough is NeuronOS's **unique selling point**. Unlike Wine (limited compatibility) or standard VMs (poor graphics performance), GPU passthrough provides:
- 98%+ native performance
- Full DirectX 11/12 support
- CUDA/OpenCL support
- Professional software certification

---

## Phase 5 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 5.1 | VFIO configuration applied | GPU bound to vfio-pci |
| 5.2 | Passthrough VM template works | VM boots with GPU |
| 5.3 | Looking Glass installed | looking-glass-client runs |
| 5.4 | IVSHMEM configured | Shared memory device works |
| 5.5 | Guest agent works | Host-guest communication |
| 5.6 | End-to-end test | Windows VM with GPU displays |

---

## Important Prerequisites

Before starting this phase, you MUST have:

1. **Two GPUs**: One for Linux (iGPU or secondary), one for VM
2. **IOMMU enabled**: Verified in Phase 2
3. **Passthrough candidate GPU**: Identified by Phase 2 hardware detection

Run this verification:
```bash
cd /home/user/NeuronOS
python3 -m hardware_detect.cli check
```

Expected: "VERDICT: GPU passthrough SUPPORTED"

---

## Step 5.1: Apply VFIO Configuration

Configure the system to bind the passthrough GPU to vfio-pci.

### Generate Configuration

```bash
cd /home/user/NeuronOS

# Generate VFIO config
python3 -m hardware_detect.cli config
```

This outputs:
- `/etc/modprobe.d/vfio.conf` content
- mkinitcpio.conf MODULES line
- Kernel parameters

### Apply Configuration (Development Machine)

**WARNING**: This changes your bootloader. Test on a VM first if unsure.

```bash
# View what will be applied
python3 -m hardware_detect.cli config

# Apply to system
sudo python3 -m hardware_detect.cli config --apply --target /

# Regenerate initramfs
sudo mkinitcpio -P

# Update bootloader
sudo grub-mkconfig -o /boot/grub/grub.cfg
# OR for systemd-boot:
# Edit /boot/loader/entries/*.conf and add kernel params
```

### Reboot and Verify

```bash
sudo reboot

# After reboot, check GPU driver
lspci -nnk | grep -A3 "VGA\|3D"

# The passthrough GPU should show:
#   Kernel driver in use: vfio-pci
```

### ISO Integration

Add VFIO configuration to the Calamares installer so it's applied during installation.

Create `iso-profile/airootfs/etc/calamares/modules/vfio-setup/`:

1. **module.desc**:
```yaml
---
type: job
name: vfio-setup
interface: python
script: main.py
```

2. **main.py**:
```python
#!/usr/bin/env python3
"""Calamares module to configure VFIO for GPU passthrough."""

import os
import subprocess
import sys

def run():
    """Configure VFIO for GPU passthrough."""
    # Get install target
    root_mount = os.environ.get("ROOT_MOUNT_POINT", "/tmp/calamares-root")

    # Add neuron-os to Python path
    sys.path.insert(0, f"{root_mount}/usr/lib/neuron-os")

    try:
        from hardware_detect.config_generator import ConfigGenerator
        from pathlib import Path

        generator = ConfigGenerator()
        config = generator.detect_and_generate()

        # Only apply if GPU passthrough is possible
        if not config.warnings or "IOMMU not detected" not in str(config.warnings):
            target = Path(root_mount)

            # Write vfio.conf
            vfio_path = target / "etc/modprobe.d/vfio.conf"
            vfio_path.parent.mkdir(parents=True, exist_ok=True)
            vfio_path.write_text(config.vfio_conf)

            # Update mkinitcpio.conf
            mkinit_path = target / "etc/mkinitcpio.conf"
            if mkinit_path.exists():
                content = mkinit_path.read_text()
                import re
                content = re.sub(
                    r'MODULES=\([^)]*\)',
                    config.mkinitcpio_modules,
                    content
                )
                mkinit_path.write_text(content)

            return ("VFIO configuration applied", "")
        else:
            return ("VFIO skipped - IOMMU not available", "")

    except Exception as e:
        return (f"VFIO setup warning: {e}", "")

    return ("VFIO setup complete", "")
```

### Verification Criteria for 5.1
- [ ] Config generator produces valid output
- [ ] vfio.conf has correct PCI IDs
- [ ] mkinitcpio.conf updated
- [ ] After reboot, GPU shows vfio-pci driver
- [ ] Linux desktop still works (using other GPU)

---

## Step 5.2: Passthrough VM Template

Create a VM template that includes GPU passthrough.

### Check Passthrough Template

```bash
cat /home/user/NeuronOS/templates/windows11-passthrough.xml.j2 | head -50
```

The template should include:
- GPU PCI device passthrough
- GPU audio device passthrough
- IVSHMEM device for Looking Glass
- UEFI boot with OVMF

### Key Template Sections

```xml
<!-- GPU Passthrough Device -->
<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x{{ gpu_pci_domain }}' bus='0x{{ gpu_pci_bus }}'
             slot='0x{{ gpu_pci_slot }}' function='0x{{ gpu_pci_function }}'/>
  </source>
  <address type='pci' domain='0x0000' bus='0x06' slot='0x00' function='0x0'/>
</hostdev>

<!-- IVSHMEM for Looking Glass -->
<shmem name='looking-glass'>
  <model type='ivshmem-plain'/>
  <size unit='M'>{{ ivshmem_size_mb }}</size>
</shmem>
```

### Create Passthrough VM

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager
from vm_manager.core.vm_config import VMConfig, VMType, GPUPassthroughConfig, LookingGlassConfig
from hardware_detect.gpu_scanner import GPUScanner

# Get passthrough GPU
scanner = GPUScanner()
gpus = scanner.scan()
passthrough_gpu = scanner.get_passthrough_candidate()

if not passthrough_gpu:
    print("No passthrough GPU available!")
    sys.exit(1)

print(f"Using GPU for passthrough: {passthrough_gpu.vendor_name} {passthrough_gpu.device_name}")

# Create VM config with passthrough
config = VMConfig(
    name='windows-passthrough-test',
    vm_type=VMType.WINDOWS,
    memory_mb=16384,
    vcpus=8,
    disk_size_gb=128,
    gpu_passthrough=GPUPassthroughConfig(
        enabled=True,
        pci_address=passthrough_gpu.pci_address,
        vendor_id=passthrough_gpu.vendor_id,
        device_id=passthrough_gpu.device_id,
    ),
    looking_glass=LookingGlassConfig(
        enabled=True,
        ivshmem_size_mb=64,
    ),
)

# Create VM
manager = LibvirtManager()
manager.connect()

try:
    # Delete if exists
    try:
        manager.destroy_vm('windows-passthrough-test')
        manager.delete_vm('windows-passthrough-test', delete_disk=True)
    except:
        pass

    success = manager.create_vm(config)
    if success:
        print("Passthrough VM created!")
        print("\nVerify with: virsh dumpxml windows-passthrough-test | grep -A5 'hostdev'")
    else:
        print("Failed to create VM")
finally:
    manager.disconnect()
EOF
```

### Verify Passthrough in XML

```bash
virsh dumpxml windows-passthrough-test | grep -A10 "hostdev"
# Should show your GPU's PCI address

virsh dumpxml windows-passthrough-test | grep -A3 "shmem"
# Should show looking-glass shared memory
```

### Verification Criteria for 5.2
- [ ] Passthrough template renders correctly
- [ ] VM created with GPU hostdev
- [ ] VM created with IVSHMEM device
- [ ] GPU PCI address matches actual GPU
- [ ] Template supports both NVIDIA and AMD

---

## Step 5.3: Install Looking Glass

Looking Glass provides low-latency display from the VM to the Linux host.

### Add Looking Glass to ISO

Add to packages.x86_64:
```text
# Looking Glass
looking-glass
looking-glass-module-dkms
```

If not in repos, build from source during ISO build or use AUR helper.

### Configure Looking Glass Shared Memory

Create `/dev/shm/looking-glass` with correct permissions.

Add to `iso-profile/airootfs/etc/tmpfiles.d/10-looking-glass.conf`:
```
f /dev/shm/looking-glass 0660 root kvm -
```

### Test Looking Glass Client

```bash
# Check if installed
looking-glass-client --help

# Basic test (will fail without VM running)
looking-glass-client
```

### Create Looking Glass Manager

Update `src/vm_manager/core/looking_glass.py`:

```python
"""Looking Glass integration for NeuronOS."""

import subprocess
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import threading

@dataclass
class LookingGlassConfig:
    """Looking Glass configuration."""
    shmem_path: str = "/dev/shm/looking-glass"
    shmem_size_mb: int = 64
    spice_socket: Optional[str] = None

class LookingGlassManager:
    """Manages Looking Glass client for VMs."""

    SHMEM_PATH = Path("/dev/shm/looking-glass")
    CLIENT_BINARY = "looking-glass-client"

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._vm_name: Optional[str] = None

    def is_available(self) -> bool:
        """Check if Looking Glass is installed."""
        try:
            result = subprocess.run(
                [self.CLIENT_BINARY, "--help"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def setup_shmem(self, size_mb: int = 64) -> bool:
        """Create and configure shared memory file."""
        try:
            # Remove old if exists
            if self.SHMEM_PATH.exists():
                self.SHMEM_PATH.unlink()

            # Create with correct size
            with open(self.SHMEM_PATH, 'wb') as f:
                f.truncate(size_mb * 1024 * 1024)

            # Set permissions (needs root or correct group)
            os.chmod(self.SHMEM_PATH, 0o660)

            return True
        except Exception as e:
            print(f"Failed to setup shmem: {e}")
            return False

    def wait_for_shmem(self, timeout: int = 60) -> bool:
        """Wait for shared memory to be ready (VM writing to it)."""
        start = time.time()
        while time.time() - start < timeout:
            if self.SHMEM_PATH.exists():
                # Check if VM is writing to it
                try:
                    stat = self.SHMEM_PATH.stat()
                    if stat.st_size > 0:
                        return True
                except:
                    pass
            time.sleep(0.5)
        return False

    def start(
        self,
        vm_name: str,
        wait_for_shmem: bool = True,
        fullscreen: bool = False,
        spice_socket: Optional[str] = None,
    ) -> bool:
        """Start Looking Glass client for a VM."""
        if self._process is not None:
            self.stop()

        if wait_for_shmem:
            if not self.wait_for_shmem():
                print("Timeout waiting for shared memory")
                return False

        cmd = [self.CLIENT_BINARY]

        # Add options
        cmd.extend(["-f", str(self.SHMEM_PATH)])

        if fullscreen:
            cmd.append("-F")

        if spice_socket:
            cmd.extend(["-c", spice_socket])

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._vm_name = vm_name
            return True
        except Exception as e:
            print(f"Failed to start Looking Glass: {e}")
            return False

    def stop(self) -> bool:
        """Stop Looking Glass client."""
        if self._process is None:
            return True

        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        finally:
            self._process = None
            self._vm_name = None

        return True

    def toggle_fullscreen(self):
        """Toggle fullscreen mode (send SIGUSR1)."""
        if self._process is not None:
            import signal
            self._process.send_signal(signal.SIGUSR1)

    def is_running(self) -> bool:
        """Check if client is running."""
        if self._process is None:
            return False
        return self._process.poll() is None


# Global singleton
_looking_glass_manager: Optional[LookingGlassManager] = None

def get_looking_glass_manager() -> LookingGlassManager:
    """Get the global Looking Glass manager."""
    global _looking_glass_manager
    if _looking_glass_manager is None:
        _looking_glass_manager = LookingGlassManager()
    return _looking_glass_manager
```

### Verification Criteria for 5.3
- [ ] Looking Glass client installed
- [ ] looking-glass-client --help works
- [ ] Shared memory setup works
- [ ] LookingGlassManager class works

---

## Step 5.4: IVSHMEM Configuration

IVSHMEM (Inter-VM Shared Memory) is how Looking Glass transfers frames.

### Verify IVSHMEM in VM XML

```bash
virsh dumpxml windows-passthrough-test | grep -A5 shmem
```

Should show:
```xml
<shmem name='looking-glass'>
  <model type='ivshmem-plain'/>
  <size unit='M'>64</size>
</shmem>
```

### Configure Shared Memory Permissions

The shared memory file must be accessible by both QEMU and Looking Glass.

Add user to kvm group:
```bash
sudo usermod -aG kvm $USER
```

Create udev rule for shared memory:
```bash
echo 'SUBSYSTEM=="kvmfr", OWNER="root", GROUP="kvm", MODE="0660"' | sudo tee /etc/udev/rules.d/99-kvmfr.rules
sudo udevadm control --reload-rules
```

### Verification Criteria for 5.4
- [ ] IVSHMEM device in VM XML
- [ ] Shared memory file created
- [ ] Correct permissions on shmem file
- [ ] QEMU can access shmem

---

## Step 5.5: Guest Agent Setup

The Looking Glass host application runs in Windows and sends frames to the shared memory.

### Windows Guest Components

These must be installed in the Windows VM:
1. VirtIO drivers
2. Looking Glass host application
3. IVSHMEM driver

### Create Guest Setup Instructions

Document in `data/guest-setup/looking-glass-windows.md`:

```markdown
# Looking Glass Windows Setup

## 1. Download Components

- Looking Glass Host: https://looking-glass.io/downloads
- VirtIO Drivers: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/
- IVSHMEM Driver: Included with Looking Glass or download from above

## 2. Install VirtIO Drivers

1. Open Device Manager
2. Find "PCI Device" (unknown)
3. Right-click > Update Driver > Browse > Navigate to virtio-win ISO
4. Install all drivers

## 3. Install IVSHMEM Driver

1. Download ivshmem-driver from Looking Glass
2. Extract to C:\ivshmem
3. Open Device Manager
4. Find "PCI standard RAM Controller" (unknown)
5. Update driver, browse to C:\ivshmem
6. Install the driver

## 4. Install Looking Glass Host

1. Run looking-glass-host-setup.exe
2. Accept defaults
3. Service will start automatically

## 5. Verify

- Looking Glass Host should show in system tray
- Status should show "Connected" when client runs on host
```

### Verification Criteria for 5.5
- [ ] Guest setup documentation exists
- [ ] VirtIO drivers install correctly
- [ ] IVSHMEM driver installs correctly
- [ ] Looking Glass host runs in Windows

---

## Step 5.6: End-to-End Test

Complete test of GPU passthrough with Looking Glass.

### Test Procedure

1. **Ensure VFIO is configured and GPU bound**:
```bash
lspci -nnk | grep -A3 "VGA" | grep vfio-pci
# Should show your passthrough GPU using vfio-pci
```

2. **Start the passthrough VM**:
```bash
virsh start windows-passthrough-test
```

3. **Wait for VM to boot** (check with virt-manager or monitor console)

4. **In Windows VM, install Looking Glass host**

5. **On Linux host, start Looking Glass client**:
```bash
looking-glass-client -f /dev/shm/looking-glass
```

6. **Expected result**: Windows desktop appears in Looking Glass window

### Automated Test Script

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
import time
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager
from vm_manager.core.looking_glass import get_looking_glass_manager

manager = LibvirtManager()
manager.connect()

vm_name = "windows-passthrough-test"

try:
    # Check VM exists
    vms = manager.list_vms()
    vm = next((v for v in vms if v.name == vm_name), None)

    if not vm:
        print(f"VM {vm_name} not found!")
        sys.exit(1)

    print(f"VM State: {vm.state}")

    # Start VM if not running
    if vm.state.value != "running":
        print("Starting VM...")
        manager.start_vm(vm_name)
        print("Waiting for VM to boot (60 seconds)...")
        time.sleep(60)

    # Check Looking Glass
    lg = get_looking_glass_manager()

    if not lg.is_available():
        print("Looking Glass client not installed!")
        sys.exit(1)

    print("Setting up shared memory...")
    lg.setup_shmem()

    print("Starting Looking Glass client...")
    print("(Waiting for Windows to initialize Looking Glass host...)")

    # In a real test, you would wait for the host to connect
    # For now, just try to start
    if lg.start(vm_name, wait_for_shmem=True):
        print("Looking Glass started!")
        print("\nPress Ctrl+C to stop test...")
        try:
            while lg.is_running():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        lg.stop()
    else:
        print("Looking Glass failed to start")
        print("Ensure Looking Glass host is running in Windows VM")

finally:
    manager.disconnect()
EOF
```

### Verification Criteria for 5.6
- [ ] VM starts successfully
- [ ] GPU is passed through (visible in Windows Device Manager)
- [ ] Looking Glass host runs in Windows
- [ ] Looking Glass client shows Windows desktop
- [ ] Performance is smooth (60+ FPS)
- [ ] Audio works (if configured)

---

## Verification Checklist

### Phase 5 is COMPLETE when ALL boxes are checked:

**VFIO Configuration**
- [ ] vfio.conf generated correctly
- [ ] GPU bound to vfio-pci after reboot
- [ ] Linux desktop works on other GPU
- [ ] mkinitcpio.conf updated

**Passthrough VM**
- [ ] VM template includes GPU hostdev
- [ ] VM template includes IVSHMEM
- [ ] VM boots with GPU visible
- [ ] GPU shows in Windows Device Manager

**Looking Glass**
- [ ] looking-glass-client installed
- [ ] Shared memory configured
- [ ] Client can connect to host
- [ ] Display is smooth

**Guest Agent**
- [ ] VirtIO drivers installed in Windows
- [ ] IVSHMEM driver installed
- [ ] Looking Glass host running
- [ ] Host-guest communication works

**End-to-End**
- [ ] Complete workflow tested
- [ ] Can run GPU-accelerated apps in VM
- [ ] Can toggle fullscreen
- [ ] Performance is acceptable

---

## Troubleshooting

### GPU still shows nvidia/amdgpu driver after reboot
- Check vfio.conf has correct PCI IDs
- Ensure softdep lines prevent driver loading
- Regenerate initramfs: `sudo mkinitcpio -P`

### VM fails to start with GPU
- Check IOMMU group isolation
- May need ACS override patch
- Verify GPU is available: `lspci -nnk`

### Looking Glass shows black screen
- Ensure Looking Glass host is running in Windows
- Check shared memory permissions
- Verify IVSHMEM device in VM XML

### Poor performance
- Ensure CPU pinning in VM config
- Check hugepages configuration
- Verify GPU driver installed in Windows

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 6: App Store](./PHASE_6_APP_STORE.md)**

Phase 6 will create the NeuronOS App Store for installing applications across all compatibility layers.
