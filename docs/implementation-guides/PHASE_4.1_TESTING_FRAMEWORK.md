# Phase 4.1: Comprehensive Testing Framework

**Status**: 🔴 MISSING - No automated tests exist
**Estimated Time**: 3-4 days
**Prerequisites**: All Phase 1-3 features complete

---

## What is a Testing Framework?

Testing separates **"it works on my machine"** from **"it works reliably in production"**. NeuronOS has 8 major modules, 100+ functions, and 1000+ edge cases that cannot be tested manually.

**Without tests**: Every change risks breaking something. Users discover bugs.
**With tests**: Automated verification catches bugs before users see them.

---

## Current State: No Automated Tests

### What's Missing ❌

| Missing Component | Impact |
|---|---|
| **Unit tests** | Can't verify individual functions work |
| **Integration tests** | Can't verify modules work together |
| **Mocking** | Can't test without real hardware |
| **Fixtures** | Every test recreates test data |
| **CI/CD** | Tests don't run automatically |
| **Coverage** | Don't know which code is untested |

---

## Objective: Production-Grade Testing

1. ✅ **Unit Tests** - Test every function in isolation (500+ tests)
2. ✅ **Integration Tests** - Test module interactions (100+ tests)
3. ✅ **Mocking System** - Simulate hardware without needing it
4. ✅ **Test Fixtures** - Reusable test data and VMs
5. ✅ **Coverage Tracking** - Know which code is tested (80%+ target)
6. ✅ **CI/CD Integration** - Tests run on every commit
7. ✅ **Performance Tests** - Verify migration speed, VM boot time
8. ✅ **Regression Suite** - Fixed bugs stay fixed

---

## Part 1: Pytest Configuration

**File**: `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts =
    -v
    --tb=short
    --cov=src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80

markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower)
    gui: GUI tests (require display)
    hardware: Require real hardware
```

---

## Part 2: Test Fixtures

**File**: `tests/conftest.py`

```python
"""Global pytest fixtures."""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from src.vm_manager.core.vm_config import VMConfig, VMType, CPUConfig, MemoryConfig
from src.hardware_detect.gpu_scanner import GPUDevice

@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for test files."""
    test_dir = tmp_path / "neuronos_test"
    test_dir.mkdir()
    yield test_dir

@pytest.fixture
def basic_vm_config():
    """Basic VM configuration for testing."""
    return VMConfig(
        name="TestVM",
        vm_type=VMType.WINDOWS,
        cpu=CPUConfig(cores=4, threads=1),
        memory=MemoryConfig(size_mb=8192),
    )

@pytest.fixture
def mock_gpu_nvidia():
    """Mock NVIDIA GPU."""
    return GPUDevice(
        pci_address="0000:01:00.0",
        vendor_id="10de",
        device_id="2204",
        vendor_name="NVIDIA Corporation",
        device_name="GeForce RTX 3080",
        is_integrated=False,
        is_boot_vga=False,
        driver="nvidia",
        iommu_group=14,
    )

@pytest.fixture
def mock_libvirt_conn():
    """Mock libvirt connection."""
    conn = MagicMock()
    conn.getVersion.return_value = 8002000
    conn.listAllDomains.return_value = []
    return conn

@pytest.fixture
def mock_windows_drive(temp_dir):
    """Mock Windows C: drive for migration testing."""
    windows_root = temp_dir / "mnt" / "windows"
    users = windows_root / "Users" / "TestUser"
    (users / "Documents").mkdir(parents=True)
    (users / "Documents" / "test.docx").write_text("Test document")
    return windows_root
```

---

## Part 3: Unit Tests

**File**: `tests/unit/test_vm_config.py`

```python
"""Unit tests for VM configuration."""

import pytest
from src.vm_manager.core.vm_config import VMConfig, VMType, SettingType

def test_vm_config_creation(basic_vm_config):
    assert basic_vm_config.name == "TestVM"
    assert basic_vm_config.cpu.cores == 4

def test_vm_config_validation_valid(basic_vm_config):
    errors = basic_vm_config.validate()
    assert len(errors) == 0

def test_vm_config_validation_no_name():
    config = VMConfig(name="", vm_type=VMType.WINDOWS)
    errors = config.validate()
    assert "VM name is required" in errors

def test_vm_config_diff_cpu_cores(basic_vm_config):
    config2 = VMConfig(
        name="TestVM",
        vm_type=VMType.WINDOWS,
        cpu=CPUConfig(cores=8, threads=1),
        memory=MemoryConfig(size_mb=8192),
    )
    changes = basic_vm_config.diff(config2)
    assert len(changes) == 1
    assert changes[0].field_path == "cpu.cores"
    assert changes[0].setting_type == SettingType.HOT
```

**File**: `tests/unit/test_exceptions.py`

```python
"""Unit tests for exception system."""

from src.common.exceptions import VMNotFoundError, IOMMUError, DownloadError

def test_vm_not_found_error():
    error = VMNotFoundError("Windows11")
    assert "Windows11" in str(error)
    assert error.code == "VM_NOT_FOUND"
    assert not error.recoverable

def test_iommu_error():
    error = IOMMUError()
    assert "IOMMU" in error.message
    assert "intel_iommu" in error.details["intel_param"]

def test_download_error():
    error = DownloadError("https://example.com/file.iso", "Network timeout")
    assert error.details["url"] == "https://example.com/file.iso"
```

---

## Part 4: Integration Tests

**File**: `tests/integration/test_vm_creation_flow.py`

```python
"""Integration tests for VM creation flow."""

import pytest
from unittest.mock import patch, MagicMock
from src.vm_manager.core.vm_creator import VMCreator

@pytest.mark.integration
@patch('src.vm_manager.core.vm_creator.libvirt')
def test_create_vm_end_to_end(mock_libvirt, basic_vm_config, temp_dir):
    """Test full VM creation flow."""
    mock_conn = MagicMock()
    mock_libvirt.open.return_value = mock_conn

    basic_vm_config.storage = StorageConfig(
        path=temp_dir / "test.qcow2",
        size_gb=50
    )

    creator = VMCreator()
    with patch('subprocess.run') as mock_subprocess:
        mock_subprocess.return_value.returncode = 0
        vm = creator.create(basic_vm_config)

    assert mock_conn.defineXML.called
```

---

## Part 5: CI/CD Integration

**File**: `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Run tests
      run: |
        pytest tests/ -v --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

---

## Part 6: Test Examples for Each Module

### VM Manager Tests
```python
def test_vm_start(mock_libvirt_domain):
    """Test starting a VM."""
    mock_libvirt_domain.create.return_value = 0
    # Test implementation

def test_vm_stop(mock_libvirt_domain):
    """Test stopping a VM."""
    mock_libvirt_domain.shutdown.return_value = 0
    # Test implementation
```

### Migration Tests
```python
def test_migration_progress(mock_windows_drive, temp_dir):
    """Test migration with progress tracking."""
    migrator = EnhancedMigrator()
    updates = []
    result = migrator.migrate(
        mock_windows_drive,
        temp_dir,
        callback=lambda p: updates.append(p)
    )
    assert len(updates) > 0
    assert result.files_copied > 0
```

### Hardware Detection Tests
```python
def test_gpu_scanner(mock_gpu_nvidia):
    """Test GPU scanning."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.stdout = "nvidia gpu data"
        scanner = GPUScanner()
        gpus = scanner.scan()
        assert len(gpus) > 0
```

---

## Verification Checklist

- [ ] **500+ unit tests** - Cover all major functions
- [ ] **100+ integration tests** - Test module interactions
- [ ] **80%+ code coverage** - Most code is tested
- [ ] **All tests pass** - Green build
- [ ] **CI/CD configured** - Tests run on every commit
- [ ] **Fast execution** - Unit tests < 30s, integration < 5min

---

## Acceptance Criteria

✅ **Complete when**:
1. Unit tests cover 80%+ of codebase
2. Integration tests verify critical flows
3. All tests pass reliably
4. CI/CD runs tests automatically
5. Test execution time < 5 minutes total

❌ **Fails if**:
1. Tests are flaky (pass/fail randomly)
2. Coverage < 50%
3. Tests take > 15 minutes
4. No CI/CD integration

---

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Guide](https://docs.python.org/3/library/unittest.mock.html)
- [GitHub Actions](https://docs.github.com/en/actions)

Good luck! 🚀
