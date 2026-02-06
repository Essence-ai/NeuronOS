# Phase 2: Hardware Detection

**Status:** ALREADY IMPLEMENTED - Verify and integrate
**Estimated Time:** 1 day (verification only)
**Prerequisites:** Phase 1 complete (bootable ISO)

---

## What Already Exists

The hardware detection module is **production-ready** (~1,500 lines across 5 files). All code is real, tested, and functional. This phase is about **verification**, not implementation.

### Existing Files

| File | Lines | Status |
|------|-------|--------|
| `src/hardware_detect/gpu_scanner.py` | 354 | Complete - scans /sys/bus/pci for GPUs, parses pci.ids |
| `src/hardware_detect/iommu_parser.py` | 407 | Complete - parses IOMMU groups, detects isolation |
| `src/hardware_detect/cpu_detect.py` | 271 | Complete - detects VT-d/AMD-Vi, core counts |
| `src/hardware_detect/config_generator.py` | 469 | Complete - generates VFIO configs, updates bootloader |
| `src/hardware_detect/cli.py` | 179 | Complete - scan/iommu/config/check subcommands |
| `airootfs/usr/bin/neuron-hardware-detect` | 200+ | Complete - detailed CLI with argparse |

---

## Phase 2 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 2.1 | GPU Scanner detects hardware | Returns GPU list on real hardware |
| 2.2 | IOMMU Parser reads groups | Lists groups or handles disabled gracefully |
| 2.3 | CPU Detection works | Identifies Intel/AMD, VT-d/Vi support |
| 2.4 | Config Generator produces valid output | Generates vfio.conf, kernel params |
| 2.5 | CLI entry point works | `neuron-hardware-detect check` runs in ISO |

---

## Step 2.1: Verify GPU Scanner

```bash
cd /home/user/NeuronOS
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.gpu_scanner import GPUScanner

scanner = GPUScanner()
gpus = scanner.scan()
print(f'Found {len(gpus)} GPU(s):')
for gpu in gpus:
    boot = ' (boot VGA)' if gpu.is_boot_vga else ''
    print(f'  {gpu.pci_address}: {gpu.vendor_name} {gpu.device_name}{boot}')
    print(f'    Driver: {gpu.driver}, IOMMU Group: {gpu.iommu_group}')
"
```

**What the scanner does internally:**
- Reads `/sys/bus/pci/devices/*/class` to find VGA controllers (class 0x0300xx)
- Parses `/usr/share/hwdata/pci.ids` for vendor/device names
- Falls back to `lspci -nnk` if sysfs scan fails
- Checks `/sys/bus/pci/devices/*/boot_vga` for primary GPU
- Reads IOMMU group from `/sys/bus/pci/devices/*/iommu_group`
- Identifies passthrough candidates (non-boot GPUs)

### Verification Criteria
- [ ] Returns at least one GPU
- [ ] PCI addresses match `lspci | grep -E "VGA|3D"` output
- [ ] Boot VGA correctly identifies primary display GPU
- [ ] IOMMU groups populated (or None if IOMMU disabled)

---

## Step 2.2: Verify IOMMU Parser

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.iommu_parser import IOMMUParser

parser = IOMMUParser()
groups = parser.parse_all()
print(f'Found {len(groups)} IOMMU groups')
for gid, group in sorted(groups.items())[:10]:
    clean = '[CLEAN]' if group.is_clean else '[SHARED]'
    print(f'  Group {gid} {clean}: {len(group.devices)} devices')
"
```

**What the parser does internally:**
- Reads `/sys/kernel/iommu_groups/*/devices/` directory structure
- Identifies device types via PCI class codes
- Detects "clean" groups (single device or GPU+audio pair only)
- Identifies AMD Navi GPU reset bugs
- Provides ACS override guidance for shared groups

### If IOMMU Not Enabled
The parser handles this gracefully - returns empty dict. To enable:
1. Enter BIOS, enable Intel VT-d or AMD-Vi
2. Add kernel parameter: `intel_iommu=on` or `amd_iommu=on`
3. Reboot

---

## Step 2.3: Verify CPU Detection

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.cpu_detect import CPUDetector

detector = CPUDetector()
cpu = detector.detect()
print(f'Vendor: {cpu.vendor}')
print(f'Model: {cpu.model_name}')
print(f'Cores: {cpu.cores}, Threads: {cpu.threads}')
print(f'IOMMU Support: {cpu.has_iommu}')
print(f'Required Param: {cpu.iommu_param}')
"
```

---

## Step 2.4: Verify Config Generator

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from hardware_detect.config_generator import ConfigGenerator

gen = ConfigGenerator()
try:
    config = gen.detect_and_generate()
    print('=== Generated VFIO Config ===')
    print(f'vfio.conf: {config.vfio_conf[:200]}...')
    print(f'Kernel params: {config.kernel_params}')
    print(f'Bootloader: {config.bootloader}')
    for w in config.warnings:
        print(f'WARNING: {w}')
except Exception as e:
    print(f'Error (expected on single-GPU systems): {e}')
"
```

---

## Step 2.5: Verify CLI Entry Point

```bash
# In the ISO or development environment:
python3 /home/user/NeuronOS/iso-profile/airootfs/usr/bin/neuron-hardware-detect check
```

The CLI in `airootfs/usr/bin/neuron-hardware-detect` is a full 200+ line argparse tool with subcommands: `scan`, `iommu`, `config`, `check`. It's more comprehensive than the module's own `cli.py`.

---

## Verification Checklist

**All boxes must be checked before proceeding:**

- [ ] `gpu_scanner.py` imports without error
- [ ] `GPUScanner().scan()` returns list of GPUs
- [ ] `iommu_parser.py` imports without error
- [ ] `IOMMUParser().parse_all()` returns dict (may be empty)
- [ ] `cpu_detect.py` correctly identifies CPU vendor
- [ ] `config_generator.py` generates valid config (on multi-GPU systems)
- [ ] CLI entry point runs without import errors
- [ ] Hardware detect module is copied to ISO by build script

---

## What NOT to Do

- **Do NOT rewrite** these modules. They are complete and production-quality.
- **Do NOT simplify** the GPU scanner - it handles edge cases (lspci fallback, boot_vga detection) that simpler versions miss.
- **Do NOT remove** the AMD Navi reset bug detection from iommu_parser.py - it prevents users from hitting a known hardware issue.

---

## Next Phase

Proceed to **[Phase 3: VM Management Core](./PHASE_3_VM_MANAGEMENT.md)**
