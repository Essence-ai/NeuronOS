# Phase 9: Testing & Production Readiness

**Status:** FINAL - Preparing for release
**Estimated Time:** 1-2 weeks
**Prerequisites:** Phases 1-8 complete

---

## Recap: What We Are Building

**NeuronOS** is a consumer-grade Linux distribution. Before release, we must ensure:
- All features work reliably
- No critical bugs or security issues
- ISO builds are reproducible
- Documentation is complete
- Support infrastructure exists

**This Phase's Goal:**
1. Comprehensive testing
2. Security audit
3. Performance optimization
4. Documentation completion
5. Release preparation

---

## Phase 9 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 9.1 | Unit tests pass | pytest runs clean |
| 9.2 | Integration tests pass | End-to-end workflows work |
| 9.3 | Security audit complete | No critical vulnerabilities |
| 9.4 | ISO builds reproducibly | Same inputs = same output |
| 9.5 | Documentation complete | User guide, API docs |
| 9.6 | Release checklist done | Ready for v1.0 |

---

## Step 9.1: Unit Tests

### Run Existing Tests

```bash
cd /home/user/NeuronOS

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Required Test Coverage

Each module should have tests:

```
tests/
├── test_hardware_detect.py    # GPU, CPU, IOMMU detection
├── test_vm_manager.py         # VM creation, lifecycle
├── test_store.py              # App catalog, installers
├── test_migration.py          # File migration
├── test_onboarding.py         # Wizard flow
├── test_security.py           # Security-specific tests
└── conftest.py                # Shared fixtures
```

### Fix Failing Tests

For each failing test:
1. Identify the cause (code bug or test bug)
2. Fix the underlying issue
3. Verify the fix works
4. Ensure no regressions

### Verification Criteria for 9.1
- [ ] All unit tests pass
- [ ] Coverage > 60%
- [ ] No skipped tests without reason
- [ ] Tests run in < 5 minutes

---

## Step 9.2: Integration Tests

Test complete workflows from user perspective.

### Key Integration Tests

1. **ISO Boot Test**
```bash
# Boot ISO in QEMU, verify desktop loads
qemu-system-x86_64 -enable-kvm -m 4G -boot d -cdrom neuronos.iso
# Expected: Desktop appears, responsive
```

2. **Installation Test**
```bash
# Install to virtual disk, verify post-install boot
# Expected: Installed system boots, user can login
```

3. **Hardware Detection Test**
```bash
# Run detection on live system
neuron-hardware-detect check
# Expected: Correct hardware identified
```

4. **VM Creation Test**
```bash
# Create a basic VM
neuron-vm create test-vm --type windows --memory 4 --disk 20
# Expected: VM created, appears in virsh list
```

5. **App Installation Test**
```bash
# Install a native app
neuron-store install cowsay
# Expected: App installed and runnable
```

6. **Wine Test**
```bash
# Run a simple Windows app
wine notepad
# Expected: Notepad opens
```

### Create Integration Test Script

```python
#!/usr/bin/env python3
"""NeuronOS Integration Test Suite."""

import subprocess
import sys
import time

def test_hardware_detection():
    """Test hardware detection module."""
    result = subprocess.run(
        ["python3", "-m", "hardware_detect.cli", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Hardware check failed: {result.stderr}"
    assert "GPU" in result.stdout, "No GPU detected"
    print("Hardware detection: PASS")

def test_vm_manager():
    """Test VM management."""
    result = subprocess.run(
        ["python3", "-m", "vm_manager.cli", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"VM list failed: {result.stderr}"
    print("VM manager: PASS")

def test_store():
    """Test app store."""
    result = subprocess.run(
        ["python3", "-m", "store.cli", "categories"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Store failed: {result.stderr}"
    assert "Categories" in result.stdout, "No categories found"
    print("App store: PASS")

def test_wine():
    """Test Wine availability."""
    result = subprocess.run(
        ["wine", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"Wine: PASS ({result.stdout.strip()})")
    else:
        print("Wine: SKIP (not installed)")

def main():
    print("=" * 50)
    print("NeuronOS Integration Tests")
    print("=" * 50)
    print()

    tests = [
        test_hardware_detection,
        test_vm_manager,
        test_store,
        test_wine,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"{test.__name__}: FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"{test.__name__}: ERROR - {e}")
            failed += 1

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
```

### Verification Criteria for 9.2
- [ ] ISO boots correctly
- [ ] Installation completes
- [ ] Hardware detection works
- [ ] VMs can be created
- [ ] Apps can be installed
- [ ] Wine runs

---

## Step 9.3: Security Audit

### Check for Common Issues

```bash
cd /home/user/NeuronOS

# Check for os.system() calls (command injection risk)
grep -rn "os.system" src/
# Should find: 0 results

# Check for subprocess with shell=True
grep -rn "shell=True" src/
# Review each one

# Check for hardcoded paths
grep -rn '"/etc/' src/ | grep -v ".conf"
# Review for proper permission handling

# Check for unsafe file operations
grep -rn "open(" src/ | grep -v "atomic_write"
# Review for config files
```

### Security Checklist

- [ ] No command injection vulnerabilities
- [ ] All downloads verify checksums
- [ ] File paths validated (no traversal)
- [ ] System files written atomically
- [ ] Sudo used only when necessary
- [ ] No hardcoded credentials
- [ ] HTTPS required for downloads

### Run Security Linter

```bash
# Install bandit
pip install bandit

# Run security scan
bandit -r src/ -ll
# Should report no high-severity issues
```

### Verification Criteria for 9.3
- [ ] No os.system() calls
- [ ] All subprocess uses list args
- [ ] Path traversal protected
- [ ] Atomic writes for configs
- [ ] Bandit shows no high issues

---

## Step 9.4: Reproducible Builds

### Configure Reproducible ISO

Update `iso-profile/profiledef.sh`:

```bash
# Add reproducibility settings
export SOURCE_DATE_EPOCH=$(date +%s)
```

### Pin Package Versions

Create version lock file:

```bash
pacman -Q > package-versions.txt
```

### Verification Criteria for 9.4
- [ ] Same source = same ISO hash
- [ ] Package versions documented
- [ ] Build date embedded
- [ ] No random elements in build

---

## Step 9.5: Documentation

### Required Documentation

1. **User Guide** (`docs/user-guide/`)
   - Installation
   - First boot
   - Using VMs
   - Installing apps
   - Troubleshooting

2. **API Documentation** (`docs/api/`)
   - Module documentation
   - Function signatures
   - Usage examples

3. **Hardware Compatibility** (`docs/hardware-compatibility.md`)
   - Tested hardware
   - Known issues
   - Workarounds

### Generate API Docs

```bash
pip install pdoc3

# Generate docs
pdoc --html -o docs/api src/
```

### Verification Criteria for 9.5
- [ ] User guide complete
- [ ] API docs generated
- [ ] Hardware compatibility documented
- [ ] Troubleshooting section exists
- [ ] README updated

---

## Step 9.6: Release Checklist

### Pre-Release Checklist

**Code Quality**
- [ ] All tests pass
- [ ] Code coverage > 60%
- [ ] No critical bugs open
- [ ] Security audit complete

**Build**
- [ ] ISO builds successfully
- [ ] ISO boots correctly
- [ ] Installation works
- [ ] Post-install boot works

**Features**
- [ ] Hardware detection works
- [ ] VM management works
- [ ] App store works
- [ ] Wine/Proton works
- [ ] GPU passthrough works
- [ ] File migration works
- [ ] Themes work

**Documentation**
- [ ] User guide complete
- [ ] README updated
- [ ] CHANGELOG created
- [ ] LICENSE file present

**Distribution**
- [ ] ISO signed with GPG
- [ ] SHA256 checksum generated
- [ ] Download page ready
- [ ] Release notes written

### Version Numbering

Follow semantic versioning:
- v0.1.0 - Alpha release
- v0.5.0 - Beta release
- v1.0.0 - Stable release

### Create Release

```bash
# Tag the release
git tag -a v0.1.0 -m "NeuronOS Alpha Release"
git push origin v0.1.0

# Generate checksums
sha256sum neuronos-0.1.0.iso > neuronos-0.1.0.iso.sha256

# Sign the ISO
gpg --armor --detach-sign neuronos-0.1.0.iso
```

---

## Verification Checklist

### Phase 9 is COMPLETE when ALL boxes are checked:

**Unit Tests**
- [ ] All tests pass
- [ ] Coverage > 60%
- [ ] Tests documented

**Integration Tests**
- [ ] ISO boot works
- [ ] Installation works
- [ ] All features work end-to-end

**Security**
- [ ] No command injection
- [ ] Downloads verified
- [ ] Path traversal blocked
- [ ] Atomic file writes
- [ ] Bandit clean

**Reproducibility**
- [ ] Builds are reproducible
- [ ] Versions documented

**Documentation**
- [ ] User guide complete
- [ ] API docs generated
- [ ] Hardware list documented

**Release**
- [ ] Version tagged
- [ ] Checksums generated
- [ ] Release notes written
- [ ] ISO signed

---

## Production Ready

Once all verification checks pass, NeuronOS is ready for release!

### Post-Release Tasks

1. Monitor issue tracker for bugs
2. Gather user feedback
3. Plan next version
4. Build community

### Continuous Improvement

After v1.0:
- Regular security updates
- Feature additions based on feedback
- Hardware compatibility expansion
- Community contributions

---

## Congratulations!

You have completed all phases of NeuronOS development. The system should now:

1. Boot and install reliably
2. Detect hardware correctly
3. Create and manage VMs
4. Run Windows apps via Wine/Proton
5. Support GPU passthrough
6. Provide a user-friendly app store
7. Offer a polished first-run experience
8. Look professional with themes
9. Be tested and documented

**Welcome to NeuronOS!**
