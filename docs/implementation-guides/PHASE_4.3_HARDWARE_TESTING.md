# Phase 4.3: Hardware Compatibility Testing

**Status**: 🔴 NOT STARTED
**Estimated Time**: 2-3 days ongoing
**Prerequisites**: All Phases 1-4.2 complete

---

## What is Hardware Compatibility Testing?

NeuronOS runs on diverse hardware configurations. Testing ensures:
- **GPU passthrough** works across NVIDIA, AMD, Intel
- **IOMMU grouping** handles different chipset layouts
- **Storage** supports SATA, NVMe, RAID
- **Network** works on various adapters

**Without testing**: Users with untested hardware encounter failures.
**With testing**: Known compatibility matrix guides users.

---

## Test Matrix

### GPU Configurations

| GPU Type | Models to Test | Critical Tests |
|---|---|---|
| **NVIDIA** | RTX 4090, 4070, 3080, 2060, GTX 1660 | VFIO bind, reset, dual-GPU |
| **AMD** | RX 7900XT, 6600XT, 5700XT, Vega 64 | Vendor-reset, reset bug workarounds |
| **Intel** | Arc A770, UHD 770, Iris Xe | iGPU passthrough, SR-IOV |

### System Configurations

| Config | Hardware | Expected Result |
|---|---|---|
| Single GPU + iGPU | Desktop: Ryzen + RX 6600XT + Vega iGPU | dGPU passthrough, iGPU for host |
| Dual discrete GPU | Intel + RTX 3080 + GTX 1660 | Either GPU passthrough |
| Laptop (MUX switch) | Gaming laptop with MUX | Detect and warn |
| Shared IOMMU group | Old AMD chipset | ACS override required |

### Storage

| Type | Test Scenario |
|---|---|
| SATA SSD | VM disk on SATA |
| NVMe | VM disk on NVMe (PCIe 3.0, 4.0, 5.0) |
| RAID | VM disk on mdadm RAID 0/1/5 |
| Network | iSCSI/NFS storage |

---

## Part 1: GPU Testing Procedure

**File**: `tests/hardware/test_gpu_passthrough.sh`

```bash
#!/bin/bash
# GPU passthrough compatibility test

echo "=== NeuronOS GPU Passthrough Test ==="

# 1. Detect GPUs
echo "Detecting GPUs..."
lspci | grep -E "(VGA|3D controller)"

# 2. Check IOMMU
echo "Checking IOMMU..."
if dmesg | grep -q "IOMMU enabled"; then
    echo "✅ IOMMU enabled"
else
    echo "❌ IOMMU disabled"
    exit 1
fi

# 3. Check IOMMU groups
echo "IOMMU Groups:"
for d in /sys/kernel/iommu_groups/*/devices/*; do
    n=${d#*/iommu_groups/*}; n=${n%%/*}
    printf 'IOMMU Group %s ' "$n"
    lspci -nns "${d##*/}"
done

# 4. Test VFIO binding
echo "Testing VFIO binding..."
GPU_PCI="0000:01:00.0"  # Adjust for your GPU
echo "$GPU_PCI" > /sys/bus/pci/drivers/vfio-pci/bind 2>&1 && echo "✅ VFIO bind success" || echo "❌ VFIO bind failed"

# 5. Create test VM
echo "Creating test VM..."
neuronos-cli vm create --name HardwareTest --gpu $GPU_PCI

# 6. Start VM
echo "Starting VM..."
neuronos-cli vm start HardwareTest && echo "✅ VM started" || echo "❌ VM start failed"

# 7. Check GPU in guest
echo "Verifying GPU in guest..."
# Check Windows Device Manager or lspci in Linux guest

echo "=== Test Complete ==="
```

---

## Part 2: Compatibility Database

**File**: `docs/HARDWARE_COMPATIBILITY.md`

```markdown
# Hardware Compatibility List

## ✅ Verified Compatible

### GPUs

| Model | Status | Notes |
|---|---|---|
| NVIDIA RTX 4090 | ✅ Works | Requires 850W PSU |
| NVIDIA RTX 3080 | ✅ Works | Reset works reliably |
| AMD RX 6600 XT | ✅ Works | Requires vendor-reset |
| Intel Arc A770 | ✅ Works | Beta drivers needed |

### Motherboards

| Model | Chipset | IOMMU | ACS Override |
|---|---|---|---|
| ASUS ROG X570 | AMD X570 | ✅ | Not needed |
| MSI B550 Tomahawk | AMD B550 | ✅ | Required |
| Gigabyte Z790 | Intel Z790 | ✅ | Not needed |

## ⚠️ Known Issues

### AMD Reset Bug

**Affected**: RX 5700 XT, Vega 64
**Symptom**: GPU doesn't reset after VM shutdown
**Workaround**: Install vendor-reset module

```bash
sudo modprobe vendor-reset
```

### Shared IOMMU Groups

**Affected**: Old AMD chipsets (X370, B350)
**Symptom**: GPU in same group as USB controller
**Workaround**: Enable ACS override

```bash
# Add to GRUB: pcie_acs_override=downstream
```

## ❌ Not Compatible

| Hardware | Reason |
|---|---|
| Laptops without MUX | Can't disable iGPU |
| Single-GPU systems | No GPU for host display |
| Pre-2010 CPUs | No VT-d/AMD-Vi support |
```

---

## Part 3: Automated Hardware Detection Tests

**File**: `tests/hardware/test_detection.py`

```python
"""Automated hardware detection tests."""

import pytest
from src.hardware_detect.gpu_scanner import GPUScanner
from src.hardware_detect.iommu_parser import IOMMUParser

def test_detect_gpus():
    """Test that GPU scanner finds at least one GPU."""
    scanner = GPUScanner()
    gpus = scanner.scan()
    assert len(gpus) > 0, "No GPUs detected"

def test_iommu_enabled():
    """Test that IOMMU is enabled."""
    parser = IOMMUParser()
    assert parser.is_iommu_enabled(), "IOMMU not enabled in kernel"

def test_gpu_iommu_groups():
    """Test that GPUs have valid IOMMU groups."""
    scanner = GPUScanner()
    gpus = scanner.scan()

    for gpu in gpus:
        assert gpu.iommu_group is not None, f"GPU {gpu.pci_address} has no IOMMU group"

def test_passthrough_candidate():
    """Test that a passthrough candidate is identified."""
    scanner = GPUScanner()
    candidate = scanner.get_passthrough_candidate()

    # Should find non-boot discrete GPU
    if candidate:
        assert not candidate.is_boot_vga, "Candidate GPU is driving display"
        assert not candidate.is_integrated, "Candidate is integrated GPU"
```

---

## Part 4: Performance Benchmarks

**File**: `tests/hardware/benchmark.py`

```python
"""Performance benchmarking for hardware configurations."""

import time
from pathlib import Path

def benchmark_vm_boot_time(vm_name: str) -> float:
    """Measure VM boot time."""
    from src.vm_manager.core.vm_lifecycle import VMLifecycleManager

    manager = VMLifecycleManager()

    start = time.time()
    manager.start_vm(vm_name)

    # Wait for guest agent connection
    timeout = 60
    elapsed = 0
    while elapsed < timeout:
        if manager.is_guest_agent_connected(vm_name):
            break
        time.sleep(1)
        elapsed += 1

    boot_time = time.time() - start
    return boot_time

def benchmark_file_migration(source: Path, dest: Path) -> float:
    """Measure migration speed."""
    from src.migration.migrator import EnhancedMigrator

    migrator = EnhancedMigrator()

    start = time.time()
    result = migrator.migrate(source, dest)
    elapsed = time.time() - start

    speed_mbps = (result.bytes_copied / (1024**2)) / elapsed
    return speed_mbps

# Expected benchmarks:
# - VM boot time: < 30 seconds
# - Migration speed: > 50 MB/s (SSD), > 200 MB/s (NVMe)
# - GPU passthrough: <5% performance loss vs bare metal
```

---

## Verification Checklist

- [ ] **Test on 5+ hardware configs** - Diverse motherboards, GPUs
- [ ] **All GPU types work** - NVIDIA, AMD, Intel
- [ ] **Edge cases documented** - Shared IOMMU groups, reset bugs
- [ ] **Known issues listed** - Compatibility database updated
- [ ] **Workarounds provided** - ACS override, vendor-reset
- [ ] **Performance acceptable** - Boot <30s, migration >50MB/s

---

## Acceptance Criteria

✅ **Complete when**:
1. Tested on 5+ different hardware configurations
2. Compatibility database covers common hardware
3. Known issues documented with workarounds
4. Performance benchmarks meet targets
5. Edge cases have clear error messages

❌ **Fails if**:
1. Untested hardware fails silently
2. No compatibility database
3. Performance significantly worse than expected
4. Common hardware doesn't work

---

## Resources

- [PCI Passthrough Wiki](https://wiki.archlinux.org/title/PCI_passthrough_via_OVMF)
- [VFIO Discord](https://discord.gg/f63cXwH)
- [r/VFIO](https://reddit.com/r/VFIO)

Good luck! 🚀
