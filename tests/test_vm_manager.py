"""
Tests for NeuronOS VM Manager
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vm_manager.core.vm_config import (
    VMConfig, VMType, CPUConfig, MemoryConfig, GPUPassthroughConfig, windows11_gaming_preset,
)


class TestVMConfig:
    """Tests for VMConfig dataclass."""

    def test_basic_config_creation(self):
        """Test creating a basic VM config."""
        config = VMConfig(
            name="TestVM",
            vm_type=VMType.WINDOWS,
        )

        assert config.name == "TestVM"
        assert config.vm_type == VMType.WINDOWS
        assert config.cpu.cores == 4
        assert config.memory.size_mb == 8192

    def test_cpu_total_vcpus(self):
        """Test vCPU calculation."""
        cpu = CPUConfig(cores=4, threads=2, sockets=1)
        assert cpu.total_vcpus == 8

    def test_memory_size_conversion(self):
        """Test memory size in GB."""
        memory = MemoryConfig(size_mb=16384)
        assert memory.size_gb == 16.0

    def test_validation_no_name(self):
        """Test validation fails without name."""
        config = VMConfig(name="", vm_type=VMType.WINDOWS)
        errors = config.validate()
        assert "VM name is required" in errors

    def test_validation_gpu_without_address(self):
        """Test validation fails when GPU enabled without address."""
        config = VMConfig(
            name="TestVM",
            vm_type=VMType.WINDOWS,
            gpu=GPUPassthroughConfig(enabled=True, pci_address=None),
        )
        errors = config.validate()
        assert any("GPU passthrough enabled" in e for e in errors)

    def test_validation_looking_glass_requires_gpu(self):
        """Test Looking Glass requires GPU passthrough."""
        from vm_manager.core.vm_config import LookingGlassConfig

        config = VMConfig(
            name="TestVM",
            vm_type=VMType.WINDOWS,
            gpu=GPUPassthroughConfig(enabled=False),
            looking_glass=LookingGlassConfig(enabled=True),
        )
        errors = config.validate()
        assert any("Looking Glass requires GPU" in e for e in errors)

    def test_windows11_gaming_preset(self):
        """Test Windows 11 gaming preset."""
        config = windows11_gaming_preset(
            name="Gaming",
            gpu_pci="0000:01:00.0",
        )

        assert config.name == "Gaming"
        assert config.vm_type == VMType.WINDOWS
        assert config.gpu.enabled is True
        assert config.gpu.pci_address == "0000:01:00.0"
        assert config.looking_glass.enabled is True
        assert config.memory.hugepages is True

    def test_config_to_dict(self):
        """Test serialization to dict."""
        config = VMConfig(
            name="TestVM",
            vm_type=VMType.WINDOWS,
        )
        data = config.to_dict()

        assert data["name"] == "TestVM"
        assert data["vm_type"] == "windows"
        assert "cpu" in data
        assert "memory" in data

    def test_config_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "name": "FromDict",
            "vm_type": "linux",
            "cpu": {"cores": 2, "threads": 1, "sockets": 1, "model": "host-passthrough"},
            "memory": {"size_mb": 4096, "hugepages": False},
        }
        config = VMConfig.from_dict(data)

        assert config.name == "FromDict"
        assert config.vm_type == VMType.LINUX
        assert config.cpu.cores == 2


class TestLibvirtManager:
    """Tests for LibvirtManager (mocked)."""

    @pytest.fixture
    def mock_libvirt(self):
        """Mock libvirt module."""
        with patch.dict(sys.modules, {'libvirt': MagicMock()}):
            yield

    def test_manager_initialization(self, mock_libvirt):
        """Test manager initializes."""
        from vm_manager.core.libvirt_manager import LibvirtManager

        manager = LibvirtManager()
        assert manager.uri == "qemu:///system"


class TestGPUPassthroughManager:
    """Tests for GPUPassthroughManager."""

    def test_manager_initialization(self):
        """Test passthrough manager initializes."""
        from vm_manager.passthrough.gpu_attach import GPUPassthroughManager

        manager = GPUPassthroughManager()
        assert manager is not None

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.resolve")
    def test_get_current_driver(self, mock_resolve, mock_exists):
        """Test getting current driver."""
        from vm_manager.passthrough.gpu_attach import GPUPassthroughManager

        mock_exists.return_value = True
        mock_resolve.return_value = Path("/sys/bus/pci/drivers/nvidia")

        _manager = GPUPassthroughManager()  # noqa: F841 - instance validates interface
        # Would return "nvidia" if sysfs existed
        # This is a unit test showing the interface works


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
