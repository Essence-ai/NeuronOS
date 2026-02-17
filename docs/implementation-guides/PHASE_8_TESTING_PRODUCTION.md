# Phase 8: Testing & Production Readiness

**Status:** PARTIAL — Test suite exists, needs expansion and CI setup
**Estimated Time:** 1-2 weeks
**Prerequisites:** Phases 1-7 complete (all features implemented and verified)

---

## What Already Exists

### Test Suite — `tests/` directory

| File | Lines | What It Tests |
|------|-------|--------------|
| `conftest.py` | 7,402 | Pytest fixtures, mock objects |
| `test_audit_suite.py` | 11,054 | Security audit tests |
| `test_common.py` | 9,417 | Common utilities |
| `test_gpu_scanner.py` | 7,114 | GPU detection |
| `test_guest_agent.py` | 3,174 | Guest agent protocol |
| `test_hardware_detect.py` | 6,399 | Hardware detection |
| `test_security.py` | 5,268 | Security functions |
| `test_store.py` | 6,066 | App store/catalog |
| `test_vm_manager.py` | 4,992 | VM lifecycle |
| `integration/test_migration.py` | 6,310 | File migration integration |

### Update System — `src/updater/` (7 files)

| File | Purpose |
|------|---------|
| `updater.py` | System update manager (pacman wrapper) |
| `verifier.py` | Post-update health checks (gdm, NetworkManager, libvirtd) |
| `rollback.py` | Btrfs snapshot rollback |
| `snapshot.py` | Snapshot creation/management |
| `cli.py` | Update CLI interface |
| `__main__.py` | Module entry point |

### What Does NOT Exist

- **No CI/CD pipeline** — No GitHub Actions, no automated builds
- **No ISO build tests** — No automated validation that the ISO builds successfully
- **No end-to-end tests** — No QEMU-based boot testing
- **No test coverage tracking** — No coverage reports
- **No release automation** — No version bumping, changelog, or release scripts

---

## Phase 8 Objectives

| # | Objective | Verification |
|---|-----------|-------------|
| 8.1 | All existing tests pass | `python -m pytest tests/ -v` exits 0 |
| 8.2 | Test coverage measured | Coverage report generated, gaps identified |
| 8.3 | Missing test areas covered | Tests for onboarding, migration, CLI, themes |
| 8.4 | ISO build validation | Script verifies ISO builds correctly |
| 8.5 | Security audit passes | No critical vulnerabilities in codebase |
| 8.6 | Update system verified | Updater, verifier, rollback all functional |
| 8.7 | Release process defined | Version numbering, changelog, build automation |

---

## Step 8.1: Run Existing Tests

### Run Full Test Suite

```bash
cd /home/user/NeuronOS

# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

### Expected Results

All tests should pass. If any fail:

1. Read the failure message carefully
2. Check if the test references outdated code (LXQt, SDDM, Calamares)
3. Fix tests that reference wrong DE/DM — NeuronOS uses **GNOME + GDM**
4. Do NOT delete failing tests — fix them or update expectations

### What to Check

- [ ] `python -m pytest tests/ -v` runs without import errors
- [ ] All tests pass (0 failures)
- [ ] No tests reference SDDM, LXQt, Calamares, or other wrong components
- [ ] Tests can run in a container/VM without requiring real hardware

---

## Step 8.2: Measure Test Coverage

### Generate Coverage Report

```bash
cd /home/user/NeuronOS

python -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# View report
# HTML report at htmlcov/index.html
```

### Coverage Targets

| Module | Current Status | Target |
|--------|---------------|--------|
| `hardware_detect/` | Has tests | 80%+ |
| `vm_manager/` | Has tests | 70%+ |
| `store/` | Has tests | 80%+ |
| `common/` | Has tests | 90%+ |
| `migration/` | Has integration tests | 70%+ |
| `onboarding/` | No tests | 50%+ |
| `updater/` | No tests | 70%+ |

### What to Check

- [ ] Coverage report generates successfully
- [ ] Overall coverage above 60%
- [ ] Critical paths (installer routing, security functions) at 90%+
- [ ] Coverage gaps identified for each module

---

## Step 8.3: Add Missing Tests

### Priority Test Areas

These modules need new tests:

#### Onboarding Wizard Tests

Create `tests/test_onboarding.py`:

- Test wizard page navigation (forward/back/skip)
- Test first-boot detection (`~/.config/neuronos/first-boot-complete`)
- Test preference saving/loading
- Test `_mark_first_boot_complete()` creates flag file
- Mock GTK4 — tests should NOT require a display server

#### Store CLI Tests

Create `tests/test_store_cli.py` (after CLI is created in Phase 6):

- Test `search` command finds apps
- Test `info` command shows app details
- Test `categories` command lists all categories
- Test error handling for missing apps

#### Updater Tests

Create `tests/test_updater.py`:

- Test `UpdateVerifier.CRITICAL_SERVICES` contains "gdm" (NOT "sddm")
- Test `_check_binaries()` for binary existence
- Test `_check_services()` with mock systemctl
- Test rollback creates/restores snapshots

#### Theme Tests

Create `tests/test_themes.py`:

- Test all three theme CSS files exist
- Test CSS is valid (no syntax errors)
- Test theme application copies correct file
- Test theme preference persistence

### What to Check

- [ ] New test files created for uncovered modules
- [ ] Tests use mocks for system calls (no real pacman/flatpak/wine)
- [ ] Tests don't require display server (mock GTK)
- [ ] All new tests pass

---

## Step 8.4: ISO Build Validation

### Create ISO Validation Script

Create `scripts/validate-iso-profile.sh` that checks the ISO profile for common issues:

```bash
#!/usr/bin/env bash
# Validates the ISO profile before building

PROFILE="iso-profile"
ERRORS=0

check() {
    if ! eval "$2"; then
        echo "FAIL: $1"
        ((ERRORS++))
    else
        echo "PASS: $1"
    fi
}

# Structure checks
check "profiledef.sh exists" "[ -f $PROFILE/profiledef.sh ]"
check "packages.x86_64 exists" "[ -f $PROFILE/packages.x86_64 ]"
check "pacman.conf exists" "[ -f $PROFILE/pacman.conf ]"
check "airootfs directory exists" "[ -d $PROFILE/airootfs ]"

# Package checks
check "No duplicate packages" "[ $(sort $PROFILE/packages.x86_64 | grep -v '^#' | grep -v '^$' | uniq -d | wc -l) -eq 0 ]"
check "GNOME included" "grep -q '^gnome$' $PROFILE/packages.x86_64"
check "GDM included" "grep -q '^gdm$' $PROFILE/packages.x86_64"
check "No SDDM" "! grep -q '^sddm$' $PROFILE/packages.x86_64"
check "No LXQt" "! grep -q '^lxqt$' $PROFILE/packages.x86_64"

# Service checks
check "GDM enabled" "[ -L $PROFILE/airootfs/etc/systemd/system/display-manager.service ] || grep -rq 'gdm' $PROFILE/airootfs/etc/systemd/"
check "GDM auto-login configured" "[ -f $PROFILE/airootfs/etc/gdm/custom.conf ]"

# Entry point checks
for ep in neuron-hardware-detect neuron-vm-manager neuron-store neuron-welcome; do
    check "$ep entry point exists" "[ -f $PROFILE/airootfs/usr/bin/$ep ]"
done

# Desktop shortcut checks
check "Desktop shortcuts exist" "ls $PROFILE/airootfs/etc/skel/Desktop/*.desktop >/dev/null 2>&1"
check "No LXQt references in shortcuts" "! grep -rq 'qterminal\|pcmanfm-qt\|lxqt' $PROFILE/airootfs/etc/skel/Desktop/"

# Theme checks
check "NeuronOS theme exists" "[ -f $PROFILE/airootfs/usr/share/neuron-os/themes/neuron.css ]"
check "Win11 theme exists" "[ -f $PROFILE/airootfs/usr/share/neuron-os/themes/win11.css ]"
check "macOS theme exists" "[ -f $PROFILE/airootfs/usr/share/neuron-os/themes/macos.css ]"

# dconf checks
check "GNOME dconf defaults exist" "[ -f $PROFILE/airootfs/etc/dconf/db/local.d/00-neuronos ]"

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "All checks passed!"
    exit 0
else
    echo "$ERRORS check(s) failed"
    exit 1
fi
```

### What to Check

- [ ] Validation script catches common issues
- [ ] No duplicate packages in packages.x86_64
- [ ] No LXQt/SDDM/Calamares references anywhere
- [ ] All entry points exist
- [ ] All theme files exist
- [ ] GDM configured correctly

---

## Step 8.5: Security Audit

### Run Existing Security Tests

```bash
cd /home/user/NeuronOS

python -m pytest tests/test_security.py tests/test_audit_suite.py -v
```

### Manual Security Checks

| Check | What to Verify |
|-------|---------------|
| Path traversal | `_safe_filename()` and `_ensure_within_directory()` in `installer.py` block `../` attacks |
| Download verification | `_verify_download()` checks SHA256 hashes |
| Sudo usage | All `sudo` calls use specific commands, never `sudo bash -c` with user input |
| File permissions | SSH keys get 600, directories get 755, sudoers files get 440 |
| No hardcoded secrets | No API keys, passwords, or tokens in source code |
| Input sanitization | App IDs and package names sanitized before shell commands |
| Wine prefix isolation | Each Wine app gets its own prefix, not shared |

### Security Scan Commands

```bash
cd /home/user/NeuronOS

# Check for hardcoded credentials
grep -rn 'password\|secret\|api_key\|token' src/ --include='*.py' | grep -v 'test\|mock\|example\|comment'

# Check for shell injection risks
grep -rn 'subprocess.*shell=True' src/ --include='*.py'
grep -rn 'os.system(' src/ --include='*.py'

# Check for unsafe file operations
grep -rn 'os.chmod.*777' src/ --include='*.py'

# Check sudoers configuration
cat iso-profile/airootfs/etc/sudoers.d/liveuser
```

### What to Check

- [ ] Security tests pass
- [ ] No `shell=True` in subprocess calls (or properly sanitized)
- [ ] No `os.system()` calls
- [ ] No hardcoded credentials
- [ ] File permissions are restrictive by default
- [ ] Download verification is mandatory for Wine installers
- [ ] Path traversal protection tested

---

## Step 8.6: Verify Update System

### Test Update Verifier

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')
from updater.verifier import UpdateVerifier

verifier = UpdateVerifier()

# Check critical services list
print('Critical services:', verifier.CRITICAL_SERVICES)
assert 'gdm' in verifier.CRITICAL_SERVICES, 'GDM must be in critical services!'
assert 'sddm' not in verifier.CRITICAL_SERVICES, 'SDDM must NOT be in critical services!'
print('Service list: CORRECT')

# Check critical binaries
print('Critical binaries:', verifier.CRITICAL_BINARIES)
print('Verifier configuration: OK')
"
```

### Test Snapshot System

```bash
cd /home/user/NeuronOS

python3 -c "
import sys; sys.path.insert(0, 'src')

# Verify snapshot module loads
from updater.snapshot import *
print('Snapshot module loaded')

# Verify rollback module loads
from updater.rollback import *
print('Rollback module loaded')

# Verify CLI module loads
from updater.cli import *
print('CLI module loaded')
"
```

### What to Check

- [ ] `UpdateVerifier.CRITICAL_SERVICES` contains "gdm" (not "sddm")
- [ ] `verify_system_health()` runs without errors
- [ ] Snapshot creation works (on Btrfs systems)
- [ ] Rollback mechanism exists and is tested
- [ ] Update CLI (`neuron-update`) has help text

---

## Step 8.7: Release Process

### Version Numbering

NeuronOS uses calendar versioning: `YYYY.MM.DD` (matches `profiledef.sh`).

```bash
grep 'iso_version' iso-profile/profiledef.sh
# iso_version="$(date +%Y.%m.%d)"
```

### Release Checklist

For each release:

1. **All tests pass**: `python -m pytest tests/ -v`
2. **ISO profile validates**: `scripts/validate-iso-profile.sh`
3. **ISO builds successfully**: `sudo ./build-iso.sh --clean`
4. **ISO boots in QEMU**: `make test-vm`
5. **GNOME desktop loads**: GDM auto-login works, desktop appears
6. **Entry points work**: `neuron-welcome`, `neuron-store`, `neuron-vm-manager`, `neuron-hardware-detect`
7. **Theme applied**: NeuronOS default theme visible
8. **No LXQt/SDDM artifacts**: Grep confirms no wrong DE references

### Build Automation

The release build process:

```bash
# 1. Validate profile
./scripts/validate-iso-profile.sh

# 2. Run tests
python -m pytest tests/ -v

# 3. Build ISO
sudo ./build-iso.sh --clean

# 4. Test ISO boots
make test-vm

# 5. Generate checksums
cd out/
sha256sum neuronos-*.iso > SHA256SUMS
```

### What to Check

- [ ] Version numbering is consistent
- [ ] Release checklist covers all critical areas
- [ ] Build script handles errors gracefully
- [ ] SHA256 checksums generated for ISO
- [ ] ISO size is reasonable (under 4GB for a full desktop)

---

## Summary of Work Required

| Item | Status | Effort |
|------|--------|--------|
| Existing test suite | EXISTS — run and fix | 2 hours |
| Test coverage measurement | NOT SET UP | 2 hours |
| Missing tests (onboarding, updater, themes) | NOT STARTED | 2-3 days |
| ISO validation script | NOT STARTED | 4 hours |
| Security audit | TESTS EXIST — verify | 4 hours |
| Update system verification | CODE EXISTS — verify | 2 hours |
| Release process documentation | NOT STARTED | 4 hours |
| CI/CD pipeline (optional) | NOT STARTED | 1-2 days |

---

## Verification Checklist

### Phase 8 is COMPLETE when ALL boxes are checked:

**Testing**
- [ ] All existing tests pass
- [ ] Coverage above 60%
- [ ] Critical modules (security, installer) above 90%
- [ ] New tests added for onboarding, updater, themes

**ISO Validation**
- [ ] Validation script passes
- [ ] No duplicate packages
- [ ] No wrong DE/DM references
- [ ] All entry points verified

**Security**
- [ ] Security tests pass
- [ ] No shell injection vectors
- [ ] No hardcoded secrets
- [ ] File permissions correct

**Update System**
- [ ] Verifier references GDM (not SDDM)
- [ ] Health check covers all critical services
- [ ] Rollback mechanism functional

**Release**
- [ ] ISO builds successfully
- [ ] ISO boots to GNOME desktop
- [ ] All NeuronOS features accessible
- [ ] Checksums generated

---

## Production Readiness Definition

NeuronOS is **production ready** when:

1. ISO builds consistently with `./build-iso.sh --clean`
2. QEMU boot test shows GNOME desktop with auto-login
3. All 4 entry points launch without errors
4. App store can search and display catalog
5. Hardware detection reports GPU/IOMMU status
6. VM Manager GUI launches
7. All three themes are selectable
8. Test suite passes with 60%+ coverage
9. No security warnings from audit
10. ISO size under 4GB
