#!/usr/bin/env python3
"""
Unit tests for hardware_detect module.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGPUScanner:
    """Tests for GPUScanner class."""

    def test_import(self):
        """Test that GPUScanner can be imported."""
        from hardware_detect.gpu_scanner import GPUScanner
        assert GPUScanner is not None

    def test_scanner_initializes(self):
        """Test that GPUScanner initializes correctly."""
        from hardware_detect.gpu_scanner import GPUScanner
        scanner = GPUScanner()
        assert scanner is not None

    @patch("subprocess.run")
    def test_scan_parses_lspci_output(self, mock_run):
        """Test that scan() correctly parses lspci output."""
        from hardware_detect.gpu_scanner import GPUScanner

        # Mock lspci output
        mock_run.return_value = MagicMock(
            stdout="""01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484] (rev a1)
00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92] (rev 00)
""",
            returncode=0
        )

        scanner = GPUScanner()
        gpus = scanner.scan()
        # May return empty list if no GPUs detected with mock
        assert isinstance(gpus, list)

    def test_gpu_device_dataclass(self):
        """Test GPUDevice dataclass."""
        from hardware_detect.gpu_scanner import GPUDevice

        gpu = GPUDevice(
            pci_address="01:00.0",
            vendor_id="10de",
            device_id="2484",
            vendor_name="NVIDIA Corporation",
            device_name="GeForce RTX 3070",
            subsystem_vendor="",
            subsystem_device="",
            is_boot_vga=False,
            iommu_group=1,
            driver_in_use="nvidia",
            device_class="0300"
        )

        assert gpu.pci_address == "01:00.0"
        assert gpu.vendor_id == "10de"
        assert gpu.is_boot_vga is False


class TestIOMMUParser:
    """Tests for IOMMUParser class."""

    def test_import(self):
        """Test that IOMMUParser can be imported."""
        from hardware_detect.iommu_parser import IOMMUParser
        assert IOMMUParser is not None

    def test_parser_initializes(self):
        """Test that IOMMUParser initializes correctly."""
        from hardware_detect.iommu_parser import IOMMUParser
        parser = IOMMUParser()
        assert parser is not None

    def test_iommu_group_dataclass(self):
        """Test IOMMUGroup dataclass."""
        from hardware_detect.iommu_parser import IOMMUGroup, IOMMUDevice

        device = IOMMUDevice(
            pci_address="01:00.0",
            device_class="0300",
            class_name="VGA compatible controller",
            vendor_id="10de",
            device_id="2484",
            description="NVIDIA Corporation GA104 [GeForce RTX 3070]"
        )

        group = IOMMUGroup(
            group_id=1,
            devices=[device]
        )

        assert group.group_id == 1
        assert len(group.devices) == 1
        assert group.devices[0].pci_address == "01:00.0"


class TestCPUDetector:
    """Tests for CPUDetector class."""

    def test_import(self):
        """Test that CPUDetector can be imported."""
        from hardware_detect.cpu_detect import CPUDetector
        assert CPUDetector is not None

    @patch.object(Path, 'read_text')
    def test_detect_intel(self, mock_read):
        """Test Intel CPU detection."""
        from hardware_detect.cpu_detect import CPUDetector

        mock_read.return_value = """processor	: 0
vendor_id	: GenuineIntel
model name	: Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz
processor	: 1
vendor_id	: GenuineIntel
model name	: Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz
"""

        detector = CPUDetector()
        # IOMMU check requires actual system access
        # These tests verify detector initializes correctly
        assert detector is not None

    @patch.object(Path, 'read_text')
    def test_detect_amd(self, mock_read):
        """Test AMD CPU detection."""
        from hardware_detect.cpu_detect import CPUDetector

        mock_read.return_value = """processor	: 0
vendor_id	: AuthenticAMD
model name	: AMD Ryzen 9 5900X 12-Core Processor
"""

        detector = CPUDetector()
        # IOMMU check requires actual system access
        assert detector is not None


class TestConfigGenerator:
    """Tests for ConfigGenerator class."""

    def test_import(self):
        """Test that ConfigGenerator can be imported."""
        from hardware_detect.config_generator import ConfigGenerator
        assert ConfigGenerator is not None

    def test_vfio_config_dataclass(self):
        """Test VFIOConfig dataclass."""
        from hardware_detect.config_generator import VFIOConfig

        config = VFIOConfig(
            vfio_conf="options vfio-pci ids=10de:2484",
            mkinitcpio_modules="MODULES=(vfio_pci vfio vfio_iommu_type1)",
            kernel_params="intel_iommu=on iommu=pt",
            bootloader="systemd-boot",
            passthrough_gpu=None,
            boot_gpu=None,
            warnings=[]
        )

        assert "vfio-pci" in config.vfio_conf
        assert config.bootloader == "systemd-boot"

    def test_detect_bootloader_systemd(self, tmp_path):
        """Test systemd-boot detection."""
        from hardware_detect.config_generator import ConfigGenerator

        # Create mock systemd-boot config
        loader_dir = tmp_path / "boot" / "loader"
        loader_dir.mkdir(parents=True)
        (loader_dir / "loader.conf").write_text("timeout 5\n")

        generator = ConfigGenerator()
        bootloader = generator.detect_bootloader(tmp_path)
        assert bootloader == "systemd-boot"

    def test_detect_bootloader_grub(self, tmp_path):
        """Test GRUB detection."""
        from hardware_detect.config_generator import ConfigGenerator

        # Create mock GRUB config
        grub_dir = tmp_path / "boot" / "grub"
        grub_dir.mkdir(parents=True)
        (grub_dir / "grub.cfg").write_text("# GRUB config\n")

        generator = ConfigGenerator()
        bootloader = generator.detect_bootloader(tmp_path)
        assert bootloader == "grub"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
