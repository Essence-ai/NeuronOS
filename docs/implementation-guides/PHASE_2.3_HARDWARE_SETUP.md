# Phase 2.3: Hardware Setup Auto-Configuration

**Status**: 🟡 PARTIAL - Hardware detection works, application incomplete
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.1-1.5 (detection infrastructure exists)

---

## The Problem

Hardware configuration is **partially automatic** but has gaps:

- ✅ Detects GPUs and IOMMU groups
- ✅ Generates kernel parameters
- ❌ **Doesn't enable IOMMU by default** (requires manual GRUB edit)
- ❌ **Doesn't handle ACS override** (needed on some AMD systems)
- ❌ **Doesn't detect VFIO incompatibilities** (bridges, hotplug, etc.)

### Impact

Users with certain hardware (AMD + Ryzen + IOMMU) see VMs fail silently.

---

## Objective

After Phase 2.3:

1. ✅ Automatic IOMMU detection and enabling
2. ✅ ACS override for problematic chipsets
3. ✅ Hardware compatibility warnings
4. ✅ One-click kernel configuration
5. ✅ Automatic VM creation with detected GPUs

---

## Key Implementation Areas

1. **IOMMU Auto-Detection**
   - Check `/proc/cmdline` for IOMMU settings
   - Detect if already enabled
   - Apply via GRUB without manual editing

2. **VFIO Device Binding**
   - Improved GPU detection
   - Handle multiple GPUs
   - Fallback configurations

3. **Error Recovery**
   - Restore original config on failure
   - Clear instructions for manual fixes
   - Rollback after reboot if problems detected

4. **Hardware Specific**
   - Intel VT-d setup
   - AMD-Vi (IOMMU) setup
   - SR-IOV detection
   - USB controller passthrough

---

## Acceptance Criteria

- [ ] IOMMU automatically enabled
- [ ] No manual GRUB editing needed
- [ ] Hardware warnings displayed clearly
- [ ] Automatic recovery on failure
- [ ] All hardware types supported

Estimated Completion: 2-3 days

[See full implementation guide for technical details - to be created]

---
