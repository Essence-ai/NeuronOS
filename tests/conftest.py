"""
Pytest configuration and shared fixtures for NeuronOS tests.

Provides mocks for hardware and system-level functionality.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Generator
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============ Environment Fixtures ============

@pytest.fixture
def temp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary home directory for tests."""
    old_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)

    # Create common directories
    (tmp_path / ".config/neuronos").mkdir(parents=True)
    (tmp_path / ".local/share/neuronos").mkdir(parents=True)

    yield tmp_path

    if old_home:
        os.environ['HOME'] = old_home
    else:
        os.environ.pop('HOME', None)


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Provide temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


# ============ Libvirt Fixtures ============

@pytest.fixture
def mock_libvirt():
    """Mock libvirt for tests that don't need real VMs."""
    with patch('libvirt.open') as mock_open:
        mock_conn = MagicMock()
        mock_conn.getVersion.return_value = 8000000
        mock_conn.listAllDomains.return_value = []
        mock_conn.lookupByName.return_value = MagicMock()
        mock_conn.isAlive.return_value = True
        mock_open.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def mock_domain():
    """Mock libvirt domain."""
    domain = MagicMock()
    domain.name.return_value = "test-vm"
    domain.UUIDString.return_value = "12345678-1234-1234-1234-123456789abc"
    domain.state.return_value = (1, 0)  # Running
    domain.maxMemory.return_value = 4194304  # 4GB in KB
    domain.maxVcpus.return_value = 4
    domain.isActive.return_value = True
    return domain


# ============ GPU/Hardware Fixtures ============

@pytest.fixture
def mock_gpu_info():
    """Create mock GPU information."""
    from hardware_detect.gpu_scanner import GPUDevice

    return GPUDevice(
        pci_address="01:00.0",
        vendor_id="10de",
        device_id="2484",
        vendor_name="NVIDIA Corporation",
        device_name="GeForce RTX 3070",
        device_class="0300",
        is_boot_vga=False,
        driver="nvidia",
    )


@pytest.fixture
def mock_gpu_scan(mock_gpu_info):
    """Mock GPU scanning for tests."""
    with patch('hardware_detect.gpu_scanner.GPUScanner.scan') as mock_scan:
        mock_scan.return_value = [mock_gpu_info]
        yield [mock_gpu_info]


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


# ============ Subprocess Fixtures ============

@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for tests."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_subprocess_popen():
    """Mock subprocess.Popen for tests."""
    with patch('subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("", "")
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        yield mock_popen


# ============ VM Config Fixtures ============

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
def windows_vm_config():
    """Provide Windows VM configuration."""
    from vm_manager.core.vm_config import VMConfig, VMType

    return VMConfig(
        name="windows-test",
        vm_type=VMType.WINDOWS,
        memory_mb=4096,
        vcpus=4,
        disk_size_gb=60,
    )


# ============ App Store Fixtures ============

@pytest.fixture
def sample_app_info():
    """Create a sample AppInfo for testing."""
    from store.app_catalog import AppInfo, AppCategory, CompatibilityLayer, CompatibilityRating

    return AppInfo(
        id="test_app",
        name="Test Application",
        description="A test application for unit tests",
        category=AppCategory.UTILITIES,
        layer=CompatibilityLayer.NATIVE,
        rating=CompatibilityRating.PERFECT,
    )


@pytest.fixture
def proton_app_info():
    """Create a Proton-layer AppInfo for testing."""
    from store.app_catalog import AppInfo, AppCategory, CompatibilityLayer, CompatibilityRating

    return AppInfo(
        id="test_game",
        name="Test Game",
        description="A test Proton game",
        category=AppCategory.GAMING,
        layer=CompatibilityLayer.PROTON,
        rating=CompatibilityRating.GOOD,
        proton_app_id=12345,
    )


@pytest.fixture
def mock_steam_installed(temp_home):
    """Mock Steam as installed."""
    steam_path = temp_home / ".steam" / "steam.sh"
    steam_path.parent.mkdir(parents=True, exist_ok=True)
    steam_path.touch()
    return steam_path


# ============ Marker Configuration ============

def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "requires_root: marks tests that need root privileges"
    )
    config.addinivalue_line(
        "markers", "requires_libvirt: marks tests that need libvirt running"
    )
    config.addinivalue_line(
        "markers", "unit: fast unit tests with no external deps"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests that may need VMs"
    )
    config.addinivalue_line(
        "markers", "hardware: hardware-dependent tests"
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
        if "requires_root" in item.keywords:
            try:
                if os.getuid() != 0:
                    item.add_marker(skip_root)
            except AttributeError:
                # Windows doesn't have getuid
                item.add_marker(skip_root)

        # Skip libvirt tests if daemon not running
        if "requires_libvirt" in item.keywords:
            try:
                import libvirt
                conn = libvirt.open("qemu:///system")
                if conn:
                    conn.close()
            except Exception:
                item.add_marker(skip_libvirt)
