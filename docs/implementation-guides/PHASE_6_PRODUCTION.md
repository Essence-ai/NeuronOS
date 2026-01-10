# Phase 6: Production Readiness

**Priority:** Required for release
**Estimated Time:** 2 weeks
**Prerequisites:** All previous phases complete

---

## Table of Contents

1. [Overview](#overview)
2. [Documentation](#documentation)
3. [Reproducible Builds](#reproducible-builds)
4. [Security Hardening](#security-hardening)
5. [Performance Optimization](#performance-optimization)
6. [Release Checklist](#release-checklist)

---

## Overview

This final phase prepares NeuronOS for public release with production-grade documentation, security, and build processes.

### Deliverables

| Deliverable | Purpose |
|-------------|---------|
| API Documentation | Developer reference |
| User Guide | End-user instructions |
| Reproducible builds | Verifiable ISO creation |
| Security audit | Final vulnerability check |
| Performance benchmarks | Baseline metrics |
| Release automation | Consistent releases |

---

## Documentation

### API Documentation

Create `docs/api/README.md`:

```markdown
# NeuronOS API Documentation

## Modules

### hardware_detect

Hardware detection for GPU/CPU/IOMMU capabilities.

#### GPUScanner

```python
from hardware_detect.gpu_scanner import GPUScanner

scanner = GPUScanner()
gpus = scanner.scan()

for gpu in gpus:
    print(f"{gpu.vendor_name} {gpu.device_name}")
    print(f"  PCI: {gpu.pci_address}")
    print(f"  IOMMU Group: {gpu.iommu_group}")
    print(f"  Boot VGA: {gpu.is_boot_vga}")
```

### vm_manager

Virtual machine management with GPU passthrough.

#### Creating a VM

```python
from vm_manager.core.vm_creator import VMCreator
from vm_manager.core.vm_config import VMConfig, VMType

config = VMConfig(
    name="windows11",
    vm_type=VMType.WINDOWS,
    memory_mb=16384,
    vcpus=8,
    disk_size_gb=128,
)

creator = VMCreator()
creator.create(config)
```

#### Starting/Stopping VMs

```python
from vm_manager.core.vm_lifecycle import VMLifecycleManager

lifecycle = VMLifecycleManager()
lifecycle.start("windows11")
lifecycle.stop("windows11")
```

### store

Application installation and management.

```python
from store.app_catalog import AppCatalog
from store.installer import AppInstaller

catalog = AppCatalog()
app = catalog.get("firefox")

installer = AppInstaller()
installer.install(app)
```
```

### User Guide

Create `docs/user-guide/README.md`:

```markdown
# NeuronOS User Guide

## Quick Start

1. **Boot from USB** - Create bootable USB with the NeuronOS ISO
2. **Install** - Run the Calamares installer
3. **First Boot** - Complete the onboarding wizard
4. **Install Apps** - Open NeuronStore and install your apps

## Features

### Native Linux Apps

80% of your needs are covered by native Linux applications:
- Firefox for web browsing
- LibreOffice for documents
- GIMP for image editing

### Windows Apps via Wine

Simple Windows apps run directly via Wine:
- Right-click .exe files to run with Wine
- Install via NeuronStore for automatic setup

### Windows Apps via VM

Professional apps requiring full Windows:
1. Create Windows VM in VM Manager
2. Install Windows from ISO
3. Install your apps (Photoshop, AutoCAD, etc.)
4. Launch with near-native performance via Looking Glass

## Troubleshooting

### GPU Passthrough Not Working

1. Verify IOMMU is enabled:
   ```bash
   dmesg | grep -i iommu
   ```

2. Check your GPU is in a separate IOMMU group:
   ```bash
   neuron-hardware-detect iommu
   ```

3. Ensure the GPU is not your boot device

### VM Won't Start

1. Check libvirt logs:
   ```bash
   journalctl -u libvirtd -f
   ```

2. Verify VM configuration:
   ```bash
   virsh dumpxml your-vm-name
   ```
```

### Generate Docstrings

Ensure all public APIs have docstrings:

```python
def scan(self) -> List[GPUInfo]:
    """
    Scan the system for available GPUs.

    Queries lspci and sysfs to identify all VGA and 3D controllers,
    determining which are suitable for passthrough.

    Returns:
        List of GPUInfo objects for each detected GPU.

    Raises:
        HardwareError: If scanning fails due to missing tools.

    Example:
        >>> scanner = GPUScanner()
        >>> gpus = scanner.scan()
        >>> passthrough_gpus = [g for g in gpus if not g.is_boot_vga]
    """
```

---

## Reproducible Builds

### Pin All Dependencies

Create `requirements.lock`:

```bash
# Generate locked requirements
pip-compile --generate-hashes pyproject.toml -o requirements.lock
```

### Fixed ISO Version

Update `iso-profile/profiledef.sh`:

```bash
#!/usr/bin/env bash
# Reproducible build configuration

# Version from git tag or environment
if [ -n "$NEURONOS_VERSION" ]; then
    iso_version="$NEURONOS_VERSION"
elif git describe --tags 2>/dev/null; then
    iso_version="$(git describe --tags)"
else
    iso_version="0.1.0-dev"
fi

# Fixed timestamp for reproducibility
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}"
```

### Build Verification Script

Create `scripts/verify-build.sh`:

```bash
#!/bin/bash
# Verify ISO build reproducibility

set -e

ISO1="$1"
ISO2="$2"

if [ -z "$ISO1" ] || [ -z "$ISO2" ]; then
    echo "Usage: $0 <iso1> <iso2>"
    exit 1
fi

echo "Comparing ISO builds..."

# Extract and compare
mkdir -p /tmp/iso1 /tmp/iso2
sudo mount -o loop "$ISO1" /tmp/iso1
sudo mount -o loop "$ISO2" /tmp/iso2

# Compare file lists
diff <(find /tmp/iso1 -type f | sort) <(find /tmp/iso2 -type f | sort)

# Compare checksums (excluding timestamps)
find /tmp/iso1 -type f -exec sha256sum {} \; | sort > /tmp/iso1.sha
find /tmp/iso2 -type f -exec sha256sum {} \; | sort > /tmp/iso2.sha

if diff /tmp/iso1.sha /tmp/iso2.sha > /dev/null; then
    echo "✓ Builds are reproducible"
else
    echo "✗ Builds differ"
    diff /tmp/iso1.sha /tmp/iso2.sha | head -20
fi

sudo umount /tmp/iso1 /tmp/iso2
```

---

## Security Hardening

### Security Checklist

```markdown
# Pre-Release Security Checklist

## Code Security

- [ ] No `os.system()` calls with string interpolation
- [ ] All subprocess calls use list arguments
- [ ] All user input validated
- [ ] All file paths sanitized
- [ ] All downloads verified (checksums)
- [ ] No hardcoded secrets

## Communication Security

- [ ] Guest agent uses encrypted channel
- [ ] Mutual authentication implemented
- [ ] Rate limiting on all services

## System Security

- [ ] ISO signed with GPG
- [ ] Package signatures verified
- [ ] Minimal attack surface
- [ ] Non-root operation where possible

## Privacy

- [ ] No telemetry without consent
- [ ] No data collection by default
- [ ] Local-first architecture
```

### Security.md

Create `SECURITY.md`:

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, email security@neuronos.org with:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

We will respond within 48 hours and provide:
- Confirmation of receipt
- Assessment timeline
- Disclosure coordination

## Security Measures

### VM Isolation

VMs run with:
- SELinux/AppArmor confinement
- Separate IOMMU groups
- No shared memory (except IVSHMEM for Looking Glass)

### Guest Agent

Communication uses:
- Encrypted channel (AES-GCM)
- Mutual authentication
- Command whitelisting
- Rate limiting

### Updates

- Signed package verification
- Automatic snapshots before updates
- One-click rollback
```

---

## Performance Optimization

### Benchmarks

Create `scripts/benchmark.py`:

```python
#!/usr/bin/env python3
"""
Performance benchmarks for NeuronOS.
"""

import time
import statistics
from pathlib import Path


def benchmark_vm_start():
    """Benchmark VM start time."""
    from vm_manager.core.vm_lifecycle import VMLifecycleManager

    lifecycle = VMLifecycleManager()
    times = []

    for _ in range(5):
        start = time.perf_counter()
        lifecycle.start("benchmark-vm")
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        lifecycle.stop("benchmark-vm")
        time.sleep(2)

    return {
        "mean": statistics.mean(times),
        "stdev": statistics.stdev(times),
        "min": min(times),
        "max": max(times),
    }


def benchmark_hardware_scan():
    """Benchmark hardware scanning."""
    from hardware_detect.gpu_scanner import GPUScanner
    from hardware_detect.iommu_parser import IOMMUParser
    from hardware_detect.cpu_detect import CPUDetector

    times = []

    for _ in range(10):
        start = time.perf_counter()

        GPUScanner().scan()
        IOMMUParser().parse_all()
        CPUDetector().detect()

        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return {
        "mean_ms": statistics.mean(times) * 1000,
        "max_ms": max(times) * 1000,
    }


if __name__ == "__main__":
    print("Hardware Scan Benchmark:")
    print(benchmark_hardware_scan())
```

### Optimization Guidelines

```python
# Use lazy loading for optional modules
def get_looking_glass():
    """Lazy-load Looking Glass manager."""
    global _lg_manager
    if _lg_manager is None:
        from vm_manager.core.looking_glass import LookingGlassManager
        _lg_manager = LookingGlassManager()
    return _lg_manager


# Cache expensive operations
from functools import lru_cache

@lru_cache(maxsize=1)
def get_system_info():
    """Cached system information."""
    return {
        "cpu": CPUDetector().detect(),
        "gpus": GPUScanner().scan(),
    }


# Use generators for large data
def iter_large_file(path: Path):
    """Stream large files without loading into memory."""
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            yield chunk
```

---

## Release Checklist

### Pre-Release

```markdown
# Release Checklist v0.1.0

## Code Freeze

- [ ] All planned features complete
- [ ] All critical bugs fixed
- [ ] All tests passing
- [ ] No security vulnerabilities

## Documentation

- [ ] README updated
- [ ] CHANGELOG written
- [ ] API docs generated
- [ ] User guide complete
- [ ] CONTRIBUTING.md exists

## Build

- [ ] ISO builds successfully
- [ ] Build is reproducible
- [ ] All dependencies pinned
- [ ] Version numbers updated

## Testing

- [ ] Manual testing on 3+ hardware configs
- [ ] Integration tests pass
- [ ] Performance benchmarks run
- [ ] Security scan complete

## Release Assets

- [ ] ISO file
- [ ] SHA256 checksum
- [ ] GPG signature
- [ ] Release notes
```

### Release Script

Create `scripts/release.sh`:

```bash
#!/bin/bash
# NeuronOS Release Script

set -e

VERSION="$1"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

echo "=== Releasing NeuronOS $VERSION ==="

# Verify clean state
if [ -n "$(git status --porcelain)" ]; then
    echo "Error: Working directory not clean"
    exit 1
fi

# Run tests
echo "Running tests..."
pytest tests/ -v

# Build ISO
echo "Building ISO..."
export NEURONOS_VERSION="$VERSION"
sudo make iso

# Generate checksums
ISO_FILE="output/neuronos-$VERSION.iso"
echo "Generating checksums..."
sha256sum "$ISO_FILE" > "$ISO_FILE.sha256"
sha512sum "$ISO_FILE" > "$ISO_FILE.sha512"

# Sign (if GPG key available)
if gpg --list-keys release@neuronos.org > /dev/null 2>&1; then
    echo "Signing release..."
    gpg --armor --detach-sign "$ISO_FILE"
fi

# Create git tag
echo "Creating git tag..."
git tag -s "v$VERSION" -m "Release $VERSION"

echo "=== Release $VERSION prepared ==="
echo "Files:"
ls -la output/neuronos-*

echo ""
echo "Next steps:"
echo "  1. Test the ISO on hardware"
echo "  2. Push tag: git push origin v$VERSION"
echo "  3. Create GitHub release with assets"
echo "  4. Announce release"
```

### CHANGELOG

Create `CHANGELOG.md`:

```markdown
# Changelog

All notable changes to NeuronOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-XX-XX

### Added

- Initial release
- GPU passthrough support for NVIDIA and AMD cards
- Looking Glass integration for low-latency VM display
- NeuronStore with 100+ pre-configured apps
- Windows and macOS VM templates
- File migration from Windows/macOS
- First-boot onboarding wizard
- Automatic VFIO configuration
- Update system with rollback support

### Known Issues

- macOS iMessage may not work (Apple limitation)
- Some anti-cheat games don't work in VMs
- Requires IOMMU-capable hardware
```

---

## Final Verification

### Production Readiness Score

Run through each category and score:

| Category | Requirements | Score |
|----------|-------------|-------|
| **Security** | No critical vulnerabilities | /10 |
| **Stability** | No crashes in normal use | /10 |
| **Features** | All advertised features work | /10 |
| **Documentation** | Complete user/dev docs | /10 |
| **Testing** | >60% coverage, all pass | /10 |
| **Performance** | Meets baseline metrics | /10 |
| **Build** | Reproducible, automated | /10 |
| **Total** | **Minimum 70 to release** | /70 |

---

## Conclusion

Upon completing all phases:

1. **Phase 1:** Security vulnerabilities eliminated
2. **Phase 2:** All features functional
3. **Phase 3:** Feature parity achieved
4. **Phase 4:** Robust error handling
5. **Phase 5:** Comprehensive testing
6. **Phase 6:** Production-ready release

NeuronOS is ready for public release.

---

## Post-Release

After release:

1. Monitor issue tracker
2. Respond to security reports within 48h
3. Plan 0.1.1 patch release for any critical bugs
4. Begin 0.2.0 planning based on feedback
