# Phase 5: Testing & Quality Assurance

**Priority:** MEDIUM - Required for release confidence
**Estimated Time:** 2 weeks
**Prerequisites:** Phase 4 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Test Infrastructure](#test-infrastructure)
3. [Unit Tests](#unit-tests)
4. [Integration Tests](#integration-tests)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Code Quality](#code-quality)

---

## Overview

This phase establishes comprehensive testing to ensure reliability and prevent regressions.

### Current State

- Tests exist but many have commented-out assertions
- No CI/CD pipeline
- No integration tests
- No mocking strategy for hardware

### Target State

- 70%+ code coverage
- All tests passing in CI
- Automated linting and type checking
- Integration tests for critical paths

---

## Test Infrastructure

### pytest Configuration

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    -ra
markers =
    unit: Unit tests (fast, no external deps)
    integration: Integration tests (may need VMs)
    hardware: Hardware-dependent tests (skip in CI)
    slow: Slow tests (skip with -m "not slow")
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

### Conftest with Fixtures

Create `tests/conftest.py`:

```python
"""
Pytest configuration and fixtures for NeuronOS tests.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============ Environment Fixtures ============

@pytest.fixture
def temp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide temporary home directory."""
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)

    # Create common directories
    (tmp_path / ".config/neuronos").mkdir(parents=True)
    (tmp_path / ".local/share/neuronos").mkdir(parents=True)

    yield tmp_path

    if old_home:
        os.environ["HOME"] = old_home
    else:
        del os.environ["HOME"]


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Provide temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


# ============ Mock Fixtures ============

@pytest.fixture
def mock_libvirt():
    """Mock libvirt for VM tests."""
    with patch("libvirt.open") as mock_open:
        mock_conn = MagicMock()
        mock_conn.getVersion.return_value = 8000000
        mock_conn.listAllDomains.return_value = []
        mock_open.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for command tests."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_gpu_scan():
    """Mock GPU scanning."""
    from hardware_detect.gpu_scanner import GPUInfo

    gpus = [
        GPUInfo(
            pci_address="00:02.0",
            vendor_id="8086",
            device_id="9a49",
            vendor_name="Intel",
            device_name="UHD Graphics",
            driver="i915",
            iommu_group=0,
            is_boot_vga=True,
        ),
        GPUInfo(
            pci_address="01:00.0",
            vendor_id="10de",
            device_id="2520",
            vendor_name="NVIDIA",
            device_name="RTX 3060",
            driver="nvidia",
            iommu_group=1,
            is_boot_vga=False,
        ),
    ]

    with patch("hardware_detect.gpu_scanner.GPUScanner.scan") as mock:
        mock.return_value = gpus
        yield gpus


@pytest.fixture
def mock_iommu_groups(tmp_path: Path):
    """Mock IOMMU groups filesystem."""
    iommu_path = tmp_path / "iommu_groups"

    # Create mock groups
    for i in range(3):
        group_path = iommu_path / str(i) / "devices"
        group_path.mkdir(parents=True)
        (group_path / f"0000:0{i}:00.0").touch()

    with patch("hardware_detect.iommu_parser.IOMMUParser.IOMMU_PATH", str(iommu_path)):
        yield iommu_path


# ============ Sample Data Fixtures ============

@pytest.fixture
def sample_vm_config():
    """Provide sample VM configuration."""
    from vm_manager.core.vm_config import VMConfig, VMType

    return VMConfig(
        name="test-vm",
        vm_type=VMType.LINUX,
        memory_mb=2048,
        vcpus=2,
        disk_size_gb=20,
    )


@pytest.fixture
def sample_app_info():
    """Provide sample app information."""
    from store.app_catalog import AppInfo, CompatibilityLayer, AppCategory

    return AppInfo(
        id="test-app",
        name="Test Application",
        description="A test application",
        category=AppCategory.UTILITIES,
        layer=CompatibilityLayer.NATIVE,
        package_name="test-app",
    )


# ============ Skip Markers ============

def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "requires_root: marks tests that need root privileges"
    )
    config.addinivalue_line(
        "markers", "requires_libvirt: marks tests that need libvirt running"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests based on environment."""
    skip_hw = pytest.mark.skip(reason="Hardware tests disabled in CI")
    skip_root = pytest.mark.skip(reason="Requires root privileges")
    skip_libvirt = pytest.mark.skip(reason="Requires libvirt daemon")

    for item in items:
        # Skip hardware tests in CI
        if "hardware" in item.keywords and os.environ.get("CI"):
            item.add_marker(skip_hw)

        # Skip root tests if not root
        if "requires_root" in item.keywords and os.getuid() != 0:
            item.add_marker(skip_root)

        # Skip libvirt tests if daemon not running
        if "requires_libvirt" in item.keywords:
            try:
                import libvirt
                conn = libvirt.open("qemu:///system")
                if conn:
                    conn.close()
            except:
                item.add_marker(skip_libvirt)
```

---

## Unit Tests

### Hardware Detection Tests

`tests/test_hardware_detect.py`:

```python
"""Tests for hardware detection module."""

import pytest
from unittest.mock import patch, MagicMock


class TestGPUScanner:
    """Tests for GPU scanning."""

    def test_parse_lspci_output(self, mock_subprocess):
        """Test parsing lspci output."""
        from hardware_detect.gpu_scanner import GPUScanner

        mock_subprocess.return_value.stdout = """
00:02.0 VGA compatible controller: Intel Corporation Device 9a49 (rev 03)
01:00.0 3D controller: NVIDIA Corporation GA106M [GeForce RTX 3060] (rev a1)
"""
        mock_subprocess.return_value.returncode = 0

        scanner = GPUScanner()
        gpus = scanner.scan()

        assert len(gpus) >= 1
        # At least one GPU should be found

    def test_identifies_boot_vga(self, mock_subprocess, tmp_path):
        """Test identification of boot VGA device."""
        from hardware_detect.gpu_scanner import GPUScanner

        # Create mock sysfs
        boot_vga = tmp_path / "0000:00:02.0" / "boot_vga"
        boot_vga.parent.mkdir(parents=True)
        boot_vga.write_text("1")

        with patch.object(GPUScanner, "_get_sysfs_path", return_value=tmp_path):
            scanner = GPUScanner()
            # ... test boot VGA detection

    def test_no_gpus_found(self, mock_subprocess):
        """Test handling when no GPUs found."""
        from hardware_detect.gpu_scanner import GPUScanner

        mock_subprocess.return_value.stdout = ""
        mock_subprocess.return_value.returncode = 0

        scanner = GPUScanner()
        gpus = scanner.scan()

        assert gpus == []


class TestCPUDetector:
    """Tests for CPU detection."""

    def test_detect_cpu_info(self):
        """Test CPU information detection."""
        from hardware_detect.cpu_detect import CPUDetector

        detector = CPUDetector()
        cpu = detector.detect()

        assert cpu is not None
        assert cpu.vendor in ["Intel", "AMD", "Unknown"]
        assert isinstance(cpu.cores, int)
        assert cpu.cores >= 1

    def test_detect_virtualization_flags(self):
        """Test virtualization capability detection."""
        from hardware_detect.cpu_detect import CPUDetector

        detector = CPUDetector()
        cpu = detector.detect()

        # Should detect at least VT-x or SVM (or neither on non-virt hardware)
        assert isinstance(cpu.has_vt_x, bool)
        assert isinstance(cpu.has_svm, bool)


class TestIOMMUParser:
    """Tests for IOMMU parsing."""

    def test_parse_groups(self, mock_iommu_groups):
        """Test IOMMU group parsing."""
        from hardware_detect.iommu_parser import IOMMUParser

        parser = IOMMUParser()
        parser.parse_all()

        assert len(parser.groups) == 3

    def test_empty_iommu(self, tmp_path):
        """Test handling when IOMMU not enabled."""
        from hardware_detect.iommu_parser import IOMMUParser

        iommu_path = tmp_path / "iommu_groups"
        # Don't create any groups

        with patch.object(IOMMUParser, "IOMMU_PATH", str(iommu_path)):
            parser = IOMMUParser()
            parser.parse_all()

            assert len(parser.groups) == 0
```

### VM Manager Tests

`tests/test_vm_manager.py`:

```python
"""Tests for VM manager module."""

import pytest
from unittest.mock import MagicMock, patch


class TestVMConfig:
    """Tests for VM configuration."""

    def test_create_valid_config(self):
        """Test creating valid VM config."""
        from vm_manager.core.vm_config import VMConfig, VMType

        config = VMConfig(
            name="test-vm",
            vm_type=VMType.WINDOWS,
            memory_mb=4096,
            vcpus=4,
        )

        assert config.name == "test-vm"
        assert config.memory_mb == 4096

    def test_invalid_memory(self):
        """Test validation of memory setting."""
        from vm_manager.core.vm_config import VMConfig, VMType

        # Very low memory should still be accepted (validation elsewhere)
        config = VMConfig(
            name="test",
            vm_type=VMType.LINUX,
            memory_mb=256,
            vcpus=1,
        )
        assert config.memory_mb == 256


class TestLibvirtManager:
    """Tests for LibVirt manager."""

    def test_connect(self, mock_libvirt):
        """Test libvirt connection."""
        from vm_manager.core.libvirt_manager import LibvirtManager

        manager = LibvirtManager()
        manager.connect()

        assert manager.is_connected

    def test_list_vms_empty(self, mock_libvirt):
        """Test listing VMs when none exist."""
        from vm_manager.core.libvirt_manager import LibvirtManager

        mock_libvirt.listAllDomains.return_value = []

        manager = LibvirtManager()
        manager.connect()
        vms = manager.list_vms()

        assert vms == []

    def test_list_vms_with_domains(self, mock_libvirt):
        """Test listing VMs with existing domains."""
        from vm_manager.core.libvirt_manager import LibvirtManager

        mock_domain = MagicMock()
        mock_domain.name.return_value = "test-vm"
        mock_domain.UUIDString.return_value = "12345"
        mock_domain.state.return_value = (1, 0)  # Running
        mock_domain.maxMemory.return_value = 4194304  # 4GB in KB
        mock_domain.maxVcpus.return_value = 4

        mock_libvirt.listAllDomains.return_value = [mock_domain]

        manager = LibvirtManager()
        manager.connect()
        vms = manager.list_vms()

        assert len(vms) == 1
        assert vms[0].name == "test-vm"


class TestVMCreator:
    """Tests for VM creation."""

    def test_validate_name(self, mock_libvirt, sample_vm_config):
        """Test VM name validation."""
        from vm_manager.core.vm_creator import VMCreator

        creator = VMCreator()

        # Valid names
        assert creator._validate_name("my-vm")
        assert creator._validate_name("test_vm_123")

        # Invalid names
        assert not creator._validate_name("")
        assert not creator._validate_name("a" * 100)  # Too long
        assert not creator._validate_name("vm with spaces")

    def test_generate_xml(self, mock_libvirt, sample_vm_config, tmp_path):
        """Test XML generation."""
        from vm_manager.core.vm_creator import VMCreator

        sample_vm_config.disk_path = tmp_path / "test.qcow2"

        creator = VMCreator()
        xml = creator._generate_fallback_xml(sample_vm_config)

        assert "<name>test-vm</name>" in xml
        assert "<memory" in xml
        assert "<vcpu" in xml
```

### Store Tests

`tests/test_store.py`:

```python
"""Tests for app store module."""

import pytest
from pathlib import Path


class TestAppCatalog:
    """Tests for app catalog."""

    def test_load_apps_json(self, temp_config_dir):
        """Test loading apps from JSON."""
        from store.app_catalog import AppCatalog

        # Create test apps.json
        apps_json = temp_config_dir / "apps.json"
        apps_json.write_text("""
{
    "apps": [
        {
            "id": "firefox",
            "name": "Firefox",
            "category": "productivity",
            "layer": "native",
            "package_name": "firefox"
        }
    ]
}
""")

        catalog = AppCatalog(apps_json)
        apps = catalog.get_all()

        assert len(apps) == 1
        assert apps[0].id == "firefox"

    def test_search_apps(self, temp_config_dir):
        """Test app search."""
        from store.app_catalog import AppCatalog, AppInfo, CompatibilityLayer, AppCategory

        catalog = AppCatalog()
        catalog._apps = [
            AppInfo(
                id="firefox",
                name="Firefox Browser",
                description="Web browser",
                category=AppCategory.PRODUCTIVITY,
                layer=CompatibilityLayer.NATIVE,
            ),
            AppInfo(
                id="chrome",
                name="Google Chrome",
                description="Web browser",
                category=AppCategory.PRODUCTIVITY,
                layer=CompatibilityLayer.NATIVE,
            ),
        ]

        results = catalog.search("browser")
        assert len(results) == 2

        results = catalog.search("firefox")
        assert len(results) == 1
        assert results[0].id == "firefox"


class TestInstallers:
    """Tests for app installers."""

    def test_pacman_installer(self, mock_subprocess, sample_app_info):
        """Test pacman installer."""
        from store.installer import PacmanInstaller, InstallProgress

        mock_subprocess.return_value.returncode = 0

        installer = PacmanInstaller()
        progress = InstallProgress()

        result = installer.install(sample_app_info, progress)

        assert result is True
        mock_subprocess.assert_called()

    def test_pacman_installer_failure(self, mock_subprocess, sample_app_info):
        """Test pacman installer failure handling."""
        from store.installer import PacmanInstaller, InstallProgress, InstallStatus

        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Package not found"

        installer = PacmanInstaller()
        progress = InstallProgress()

        result = installer.install(sample_app_info, progress)

        assert result is False
        assert progress.status == InstallStatus.FAILED
```

---

## Integration Tests

### VM Lifecycle Test

`tests/integration/test_vm_lifecycle.py`:

```python
"""Integration tests for VM lifecycle."""

import pytest
import time


@pytest.mark.integration
@pytest.mark.requires_libvirt
class TestVMLifecycle:
    """Tests for VM lifecycle operations."""

    @pytest.fixture
    def test_vm_name(self):
        return f"neuronos-test-{int(time.time())}"

    def test_create_start_stop_delete(self, test_vm_name):
        """Test complete VM lifecycle."""
        from vm_manager.core.vm_creator import VMCreator
        from vm_manager.core.vm_lifecycle import VMLifecycleManager
        from vm_manager.core.vm_config import VMConfig, VMType, VMState

        # Create
        config = VMConfig(
            name=test_vm_name,
            vm_type=VMType.LINUX,
            memory_mb=512,
            vcpus=1,
            disk_size_gb=1,
        )

        creator = VMCreator()
        assert creator.create(config)

        # Start
        lifecycle = VMLifecycleManager()
        assert lifecycle.start(test_vm_name)
        assert lifecycle.get_state(test_vm_name) == VMState.RUNNING

        # Stop
        assert lifecycle.stop(test_vm_name)
        time.sleep(2)
        assert lifecycle.get_state(test_vm_name) == VMState.SHUTOFF

        # Delete
        # ... cleanup


@pytest.mark.integration
class TestMigration:
    """Integration tests for file migration."""

    def test_migrate_documents(self, tmp_path):
        """Test document migration."""
        from migration.migrator import create_migrator, MigrationSource, MigrationTarget

        # Set up source
        source_home = tmp_path / "windows_user"
        (source_home / "Documents").mkdir(parents=True)
        (source_home / "Documents/test.txt").write_text("test content")

        # Set up target
        target_home = tmp_path / "linux_user"
        target_home.mkdir()

        source = MigrationSource(
            path=source_home,
            user="testuser",
            os_type="windows",
        )
        target = MigrationTarget(path=target_home)

        migrator = create_migrator(source, target)
        migrator.scan()

        assert migrator.progress.files_total >= 1

        migrator.migrate()

        assert (target_home / "Documents/test.txt").exists()
        assert (target_home / "Documents/test.txt").read_text() == "test content"
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install ruff black mypy

      - name: Run ruff
        run: ruff check src/ tests/

      - name: Run black
        run: black --check src/ tests/

      - name: Run mypy
        run: mypy src/ --ignore-missing-imports

  test:
    name: Test
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y libvirt-dev python3-libvirt

      - name: Install Python dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest tests/ -v --tb=short -m "not integration and not hardware"
        env:
          CI: true

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        if: always()

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install libvirt
        run: |
          sudo apt-get update
          sudo apt-get install -y qemu-kvm libvirt-daemon-system
          sudo systemctl start libvirtd
          sudo usermod -aG libvirt $USER

      - name: Run integration tests
        run: |
          pytest tests/integration/ -v --tb=short
        env:
          CI: true

  build-iso:
    name: Build ISO
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4

      - name: Install archiso
        run: |
          # This would need an Arch-based runner
          echo "ISO build requires Arch Linux"

      - name: Build ISO
        run: |
          # sudo make iso
          echo "Skipping ISO build in CI"
```

### Pre-commit Configuration

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=500']

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports]
```

---

## Code Quality

### Coverage Requirements

Add to `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
fail_under = 60
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

### Ruff Configuration

Add to `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # Pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "ARG",  # flake8-unused-arguments
    "SIM",  # flake8-simplify
]
ignore = [
    "E501",  # line too long (handled by black)
    "B008",  # function call in argument defaults
]

[tool.ruff.per-file-ignores]
"tests/*" = ["ARG", "S101"]
```

---

## Verification Checklist

- [ ] All unit tests pass
- [ ] Code coverage > 60%
- [ ] CI pipeline runs on every PR
- [ ] Pre-commit hooks configured
- [ ] No ruff/mypy errors
- [ ] Integration tests pass locally

---

## Next Phase

Proceed to [Phase 6: Production Readiness](./PHASE_6_PRODUCTION.md).
