# Phase 2: Hardware Detection

**Status:** CORE FEATURE - Enables GPU passthrough capability
**Estimated Time:** 3-5 days
**Prerequisites:** Phase 1 complete (bootable ISO)

---

## Recap: What We Are Building

**NeuronOS** provides seamless Windows/macOS software compatibility through:
- GPU passthrough VMs for professional software (Adobe, AutoCAD)
- Wine/Proton for simpler Windows apps
- Native Linux for everything else

**This Phase's Goal:** Create a working hardware detection system that:
1. Detects all GPUs in the system
2. Parses IOMMU groups correctly
3. Identifies which GPU can be passed through
4. Generates correct VFIO configuration files
5. Can be run from command line AND integrated into ISO

---

## Why This Phase Matters

GPU passthrough requires:
1. Knowing which GPUs exist
2. Understanding IOMMU group isolation
3. Generating correct modprobe.d configs
4. Updating bootloader parameters

If any of these fail, the VM won't get GPU access. This phase ensures the detection is **reliable and tested**.

---

## Phase 2 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 2.1 | GPU Scanner works | Detects GPUs on real hardware |
| 2.2 | IOMMU Parser works | Lists groups correctly |
| 2.3 | CPU Detection works | Detects Intel/AMD, VT-d/Vi |
| 2.4 | Config Generator works | Generates valid modprobe.d |
| 2.5 | CLI works | `neuron-hardware-detect` runs |
| 2.6 | Integrated into ISO | Runs on live system |

---

## Step 2.1: Verify GPU Scanner

First, verify the existing GPU scanner code works correctly.

### Test the Scanner

```bash
cd /home/user/NeuronOS

# Run the GPU scanner directly
python3 -c "
import sys
sys.path.insert(0, 'src')
from hardware_detect.gpu_scanner import GPUScanner

scanner = GPUScanner()
gpus = scanner.scan()

print(f'Found {len(gpus)} GPU(s):')
for gpu in gpus:
    print(f'  - {gpu.vendor_name} {gpu.device_name}')
    print(f'    PCI: {gpu.pci_address}')
    print(f'    Driver: {gpu.driver}')
    print(f'    Boot VGA: {gpu.is_boot_vga}')
    print(f'    IOMMU Group: {gpu.iommu_group}')
    print()
"
```

### Expected Output
- Should list all GPUs in the system
- Each GPU should have vendor, device name, PCI address
- At least one GPU should be marked as boot VGA
- IOMMU groups should be numbers (or None if IOMMU disabled)

### If It Fails

**Common Issue 1: Import error**
- Check that `src/hardware_detect/gpu_scanner.py` exists
- Check for syntax errors in the file

**Common Issue 2: No GPUs found**
- Run `lspci | grep -E "VGA|3D"` to verify GPUs exist
- Check the lspci parsing logic in gpu_scanner.py

### Required Fix (if needed)

If the scanner doesn't work, these are the key components it needs:

```python
# src/hardware_detect/gpu_scanner.py must have:

# 1. GPUInfo dataclass with these fields:
#    - pci_address: str (e.g., "01:00.0")
#    - vendor_id: str (e.g., "10de")
#    - device_id: str (e.g., "2520")
#    - vendor_name: str (e.g., "NVIDIA")
#    - device_name: str (e.g., "RTX 3060")
#    - driver: str (e.g., "nvidia")
#    - iommu_group: Optional[int]
#    - is_boot_vga: bool

# 2. GPUScanner class with:
#    - scan() -> List[GPUInfo]: Parse lspci output
#    - get_passthrough_candidate() -> Optional[GPUInfo]: Get non-boot GPU
#    - _parse_lspci(): Run lspci -nnk and parse output
#    - _get_iommu_group(pci_addr): Read from /sys/kernel/iommu_groups
#    - _is_boot_vga(pci_addr): Check /sys/bus/pci/devices/.../boot_vga
```

### Verification Criteria for 2.1
- [ ] `GPUScanner().scan()` returns a list
- [ ] Each GPU has all required fields populated
- [ ] PCI addresses match `lspci` output
- [ ] Boot VGA detection matches actual primary GPU
- [ ] IOMMU groups are detected (if IOMMU enabled)

---

## Step 2.2: Verify IOMMU Parser

The IOMMU parser reads group information from `/sys/kernel/iommu_groups/`.

### Test the Parser

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from hardware_detect.iommu_parser import IOMMUParser

parser = IOMMUParser()
parser.parse_all()

print(f'Found {len(parser.groups)} IOMMU groups')
for group_id, group in sorted(parser.groups.items()):
    print(f'\nGroup {group_id}:')
    for device in group.devices:
        print(f'  {device.pci_address}: {device.description}')
    print(f'  Clean (single device): {group.is_clean}')
"
```

### Expected Output
- Lists IOMMU groups (typically 0-20+)
- Each group contains one or more devices
- Groups with GPUs are identified
- "Clean" status indicates if GPU is isolated

### If No Groups Found

```bash
# Check if IOMMU is enabled
ls /sys/kernel/iommu_groups/
# Should show numbered directories (0, 1, 2, ...)

# If empty, IOMMU is not enabled
# Check kernel parameters
cat /proc/cmdline | grep iommu
```

### Verification Criteria for 2.2
- [ ] Parser finds IOMMU groups (or gracefully handles when disabled)
- [ ] Each group lists devices correctly
- [ ] GPU can be found in its group
- [ ] `is_clean` correctly identifies groups with single device
- [ ] Audio device in same group as GPU is detected

---

## Step 2.3: Verify CPU Detection

CPU detection determines which IOMMU parameter to use.

### Test CPU Detection

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from hardware_detect.cpu_detect import CPUDetector

detector = CPUDetector()
cpu = detector.detect()

print(f'CPU Vendor: {cpu.vendor}')
print(f'Model: {cpu.model_name}')
print(f'Cores: {cpu.cores}')
print(f'Threads: {cpu.threads}')
print(f'IOMMU Enabled: {cpu.has_iommu}')
print(f'Required Param: {cpu.iommu_param}')
"
```

### Expected Output
- Vendor is "Intel" or "AMD"
- Cores/threads are positive integers
- IOMMU param is `intel_iommu=on` or `amd_iommu=on`

### Verification Criteria for 2.3
- [ ] Vendor detection matches actual CPU
- [ ] Core count is correct
- [ ] IOMMU parameter matches CPU vendor
- [ ] Detection works on both Intel and AMD

---

## Step 2.4: Verify Config Generator

The config generator creates files needed for VFIO passthrough.

### Test Config Generation

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from hardware_detect.config_generator import ConfigGenerator

generator = ConfigGenerator()
try:
    config = generator.detect_and_generate()

    print('=== VFIO Configuration ===')
    print()
    print('--- /etc/modprobe.d/vfio.conf ---')
    print(config.vfio_conf)
    print()
    print('--- mkinitcpio.conf MODULES ---')
    print(config.mkinitcpio_modules)
    print()
    print('--- Kernel Parameters ---')
    print(config.kernel_params)
    print()
    print('--- Bootloader ---')
    print(config.bootloader)
    print()
    if config.warnings:
        print('--- Warnings ---')
        for w in config.warnings:
            print(f'  ! {w}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
"
```

### Expected Output
- vfio.conf content with PCI IDs
- MODULES line for mkinitcpio
- Kernel parameters (intel_iommu=on or amd_iommu=on)
- Bootloader type (grub or systemd-boot)

### Verification Criteria for 2.4
- [ ] vfio.conf contains correct PCI IDs for passthrough GPU
- [ ] vfio.conf includes audio device from same IOMMU group
- [ ] mkinitcpio modules line includes vfio modules
- [ ] Kernel params match CPU vendor
- [ ] Bootloader correctly detected
- [ ] Warnings identify any issues (non-clean IOMMU groups)

---

## Step 2.5: Create CLI Entry Point

Create a command-line tool that users and installers can run.

### Verify CLI Exists

```bash
# Check if the CLI module exists
cat /home/user/NeuronOS/src/hardware_detect/cli.py | head -20

# Try running it
cd /home/user/NeuronOS
python3 -m hardware_detect.cli --help 2>/dev/null || python3 src/hardware_detect/cli.py --help
```

### Expected CLI Commands

The CLI should support:
- `scan` - List all GPUs
- `iommu` - List IOMMU groups
- `config` - Generate VFIO configuration
- `check` - Run compatibility check

### If CLI Missing or Broken

Create/fix `src/hardware_detect/cli.py`:

```python
#!/usr/bin/env python3
"""NeuronOS Hardware Detection CLI."""

import argparse
import sys
import json

def cmd_scan(args):
    """Scan for GPUs."""
    from hardware_detect.gpu_scanner import GPUScanner
    scanner = GPUScanner()
    gpus = scanner.scan()

    if args.json:
        print(json.dumps([{
            'pci_address': g.pci_address,
            'vendor': g.vendor_name,
            'device': g.device_name,
            'driver': g.driver,
            'iommu_group': g.iommu_group,
            'is_boot_vga': g.is_boot_vga,
        } for g in gpus], indent=2))
    else:
        for gpu in gpus:
            boot = " (boot VGA)" if gpu.is_boot_vga else ""
            print(f"{gpu.pci_address}: {gpu.vendor_name} {gpu.device_name}{boot}")
            print(f"  Driver: {gpu.driver}, IOMMU Group: {gpu.iommu_group}")

def cmd_iommu(args):
    """List IOMMU groups."""
    from hardware_detect.iommu_parser import IOMMUParser
    parser = IOMMUParser()
    parser.parse_all()

    for group_id, group in sorted(parser.groups.items()):
        clean = "[CLEAN]" if group.is_clean else "[SHARED]"
        print(f"Group {group_id} {clean}:")
        for dev in group.devices:
            print(f"  {dev.pci_address}: {dev.description}")

def cmd_config(args):
    """Generate VFIO configuration."""
    from hardware_detect.config_generator import ConfigGenerator
    generator = ConfigGenerator()

    try:
        config = generator.detect_and_generate()

        if args.apply:
            print("Applying configuration...")
            generator.apply_to_target(args.target)
            print("Configuration applied. Reboot required.")
        else:
            print("# /etc/modprobe.d/vfio.conf")
            print(config.vfio_conf)
            print()
            print("# Add to /etc/mkinitcpio.conf MODULES:")
            print(config.mkinitcpio_modules)
            print()
            print("# Add to kernel command line:")
            print(config.kernel_params)

            for w in config.warnings:
                print(f"\n# WARNING: {w}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_check(args):
    """Check system compatibility."""
    from hardware_detect.gpu_scanner import GPUScanner
    from hardware_detect.cpu_detect import CPUDetector
    from hardware_detect.iommu_parser import IOMMUParser

    print("NeuronOS Hardware Compatibility Check")
    print("=" * 40)

    # CPU
    cpu = CPUDetector().detect()
    print(f"CPU: {cpu.vendor} - {cpu.model_name}")
    print(f"  IOMMU Support: {'Yes' if cpu.has_iommu else 'No'}")

    # GPUs
    gpus = GPUScanner().scan()
    print(f"\nGPUs: {len(gpus)} found")
    passthrough_candidate = None
    for gpu in gpus:
        role = "Primary" if gpu.is_boot_vga else "Secondary"
        print(f"  [{role}] {gpu.vendor_name} {gpu.device_name}")
        if not gpu.is_boot_vga:
            passthrough_candidate = gpu

    # IOMMU
    parser = IOMMUParser()
    parser.parse_all()
    print(f"\nIOMMU Groups: {len(parser.groups)}")
    if len(parser.groups) == 0:
        print("  WARNING: IOMMU not enabled!")

    # Verdict
    print("\n" + "=" * 40)
    if len(gpus) >= 2 and len(parser.groups) > 0 and passthrough_candidate:
        print("VERDICT: GPU passthrough SUPPORTED")
        print(f"  Recommended for passthrough: {passthrough_candidate.device_name}")
    elif len(gpus) == 1 and len(parser.groups) > 0:
        print("VERDICT: Single-GPU passthrough possible (with limitations)")
    else:
        print("VERDICT: GPU passthrough NOT AVAILABLE")
        if len(parser.groups) == 0:
            print("  - Enable IOMMU in BIOS")
        if len(gpus) < 2:
            print("  - Only one GPU detected")

def main():
    parser = argparse.ArgumentParser(
        prog='neuron-hardware-detect',
        description='NeuronOS Hardware Detection Tool'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for GPUs')
    scan_parser.add_argument('--json', action='store_true', help='Output as JSON')
    scan_parser.set_defaults(func=cmd_scan)

    # iommu command
    iommu_parser = subparsers.add_parser('iommu', help='List IOMMU groups')
    iommu_parser.set_defaults(func=cmd_iommu)

    # config command
    config_parser = subparsers.add_parser('config', help='Generate VFIO config')
    config_parser.add_argument('--apply', action='store_true', help='Apply config')
    config_parser.add_argument('--target', default='/', help='Target root path')
    config_parser.set_defaults(func=cmd_config)

    # check command
    check_parser = subparsers.add_parser('check', help='Check compatibility')
    check_parser.set_defaults(func=cmd_check)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == '__main__':
    main()
```

### Verification Criteria for 2.5
- [ ] `python3 -m hardware_detect.cli scan` works
- [ ] `python3 -m hardware_detect.cli iommu` works
- [ ] `python3 -m hardware_detect.cli config` works
- [ ] `python3 -m hardware_detect.cli check` works
- [ ] `--json` flag produces valid JSON
- [ ] `--help` shows usage

---

## Step 2.6: Integrate into ISO

Add the hardware detection tool to the NeuronOS ISO.

### Copy Source to ISO

Update packages.x86_64 to include Python dependencies:
```text
# Add these to packages.x86_64
python
python-pip
```

### Create Entry Point Script

Create `iso-profile/airootfs/usr/bin/neuron-hardware-detect`:

```bash
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/neuron-os')
from hardware_detect.cli import main
main()
```

### Copy Python Modules

Add a build step to copy src/ to airootfs:

In `iso-profile/profiledef.sh`, add:
```bash
# In file_permissions:
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/usr/bin/neuron-hardware-detect"]="0:0:755"
)
```

Create the directory structure:
```bash
mkdir -p /home/user/NeuronOS/iso-profile/airootfs/usr/lib/neuron-os/
cp -r /home/user/NeuronOS/src/hardware_detect /home/user/NeuronOS/iso-profile/airootfs/usr/lib/neuron-os/
cp -r /home/user/NeuronOS/src/utils /home/user/NeuronOS/iso-profile/airootfs/usr/lib/neuron-os/
```

### Verification Criteria for 2.6
- [ ] neuron-os directory exists in airootfs
- [ ] Entry point script is executable
- [ ] ISO builds successfully with hardware_detect included
- [ ] Running `neuron-hardware-detect check` in live ISO works

---

## Verification Checklist

### Phase 2 is COMPLETE when ALL boxes are checked:

**GPU Scanner**
- [ ] Detects all GPUs on the system
- [ ] Correctly identifies boot VGA
- [ ] Gets IOMMU group for each GPU
- [ ] Handles systems with 1, 2, or 3+ GPUs

**IOMMU Parser**
- [ ] Lists all IOMMU groups
- [ ] Identifies devices in each group
- [ ] Correctly identifies "clean" (single-device) groups
- [ ] Handles systems without IOMMU enabled

**CPU Detector**
- [ ] Detects Intel vs AMD
- [ ] Returns correct IOMMU kernel parameter
- [ ] Reports core/thread count

**Config Generator**
- [ ] Generates valid vfio.conf
- [ ] Includes GPU and audio device IDs
- [ ] Generates correct mkinitcpio MODULES
- [ ] Detects bootloader type

**CLI**
- [ ] `scan` command works
- [ ] `iommu` command works
- [ ] `config` command works
- [ ] `check` command works
- [ ] JSON output valid

**ISO Integration**
- [ ] Hardware detect runs in live ISO
- [ ] No import errors
- [ ] Output is correct

---

## Test Commands Summary

```bash
# Test GPU scanning
python3 -c "from hardware_detect.gpu_scanner import GPUScanner; print(GPUScanner().scan())"

# Test IOMMU parsing
python3 -c "from hardware_detect.iommu_parser import IOMMUParser; p=IOMMUParser(); p.parse_all(); print(len(p.groups))"

# Test CPU detection
python3 -c "from hardware_detect.cpu_detect import CPUDetector; print(CPUDetector().detect())"

# Test config generation
python3 -c "from hardware_detect.config_generator import ConfigGenerator; print(ConfigGenerator().detect_and_generate())"

# Test CLI
python3 -m hardware_detect.cli check
```

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 3: VM Management Core](./PHASE_3_VM_MANAGEMENT.md)**

Phase 3 will implement the libvirt integration for creating and managing VMs.
