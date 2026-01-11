"""
Tests for NeuronOS Hardware Detection - GPU Scanner

These tests are designed to work on any system, mocking hardware
when necessary.
"""

import pytest
from pathlib import Path
import json

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hardware_detect.gpu_scanner import GPUScanner, GPUDevice


class TestGPUDevice:
    """Tests for the GPUDevice dataclass."""

    def test_device_creation(self):
        """Test basic GPUDevice creation."""
        device = GPUDevice(
            pci_address="0000:01:00.0",
            vendor_id="10de",
            device_id="1c03",
            vendor_name="NVIDIA Corporation",
            device_name="GeForce GTX 1060",
            is_boot_vga=False,
            iommu_group=12,
            driver_in_use="nvidia",
        )

        assert device.pci_address == "0000:01:00.0"
        assert device.vendor_id == "10de"
        assert device.vfio_ids == "10de:1c03"
        assert device.is_discrete is True
        assert device.is_integrated is False

    def test_intel_integrated_detection(self):
        """Test Intel iGPU is detected as integrated."""
        device = GPUDevice(
            pci_address="0000:00:02.0",
            vendor_id="8086",
            device_id="3e92",
            vendor_name="Intel Corporation",
            device_name="UHD Graphics 630",
            is_boot_vga=True,
            iommu_group=0,
        )

        assert device.is_integrated is True
        assert device.is_discrete is False

    def test_amd_discrete_detection(self):
        """Test AMD discrete GPU is detected correctly."""
        device = GPUDevice(
            pci_address="0000:03:00.0",
            vendor_id="1002",
            device_id="73bf",
            vendor_name="AMD",
            device_name="RX 6800 XT",
            is_boot_vga=False,
            iommu_group=15,
        )

        assert device.is_discrete is True


class TestGPUScanner:
    """Tests for the GPUScanner class."""

    def test_scanner_initialization(self):
        """Test scanner initializes without error."""
        scanner = GPUScanner()
        assert scanner is not None
        assert scanner.devices == []

    def test_scanner_pci_ids_cache(self):
        """Test that PCI IDs cache has basic vendors."""
        scanner = GPUScanner()

        # Should have at least these common vendors
        vendors = scanner._pci_ids_cache.get("vendors", {})
        assert "10de" in vendors  # NVIDIA
        assert "1002" in vendors  # AMD
        assert "8086" in vendors  # Intel

    def test_get_passthrough_candidate_prefers_non_boot(self):
        """Test that non-boot VGA GPU is preferred for passthrough."""
        scanner = GPUScanner()

        # Simulate detected GPUs
        scanner.devices = [
            GPUDevice(
                pci_address="0000:00:02.0",
                vendor_id="8086",
                device_id="3e92",
                vendor_name="Intel",
                device_name="UHD 630",
                is_boot_vga=True,
                iommu_group=0,
            ),
            GPUDevice(
                pci_address="0000:01:00.0",
                vendor_id="10de",
                device_id="1c03",
                vendor_name="NVIDIA",
                device_name="GTX 1060",
                is_boot_vga=False,
                iommu_group=12,
            ),
        ]

        candidate = scanner.get_passthrough_candidate()
        assert candidate is not None
        assert candidate.pci_address == "0000:01:00.0"
        assert candidate.vendor_id == "10de"

    def test_get_boot_gpu(self):
        """Test getting the boot GPU."""
        scanner = GPUScanner()

        scanner.devices = [
            GPUDevice(
                pci_address="0000:00:02.0",
                vendor_id="8086",
                device_id="3e92",
                vendor_name="Intel",
                device_name="UHD 630",
                is_boot_vga=True,
                iommu_group=0,
            ),
            GPUDevice(
                pci_address="0000:01:00.0",
                vendor_id="10de",
                device_id="1c03",
                vendor_name="NVIDIA",
                device_name="GTX 1060",
                is_boot_vga=False,
                iommu_group=12,
            ),
        ]

        boot = scanner.get_boot_gpu()
        assert boot is not None
        assert boot.is_boot_vga is True
        assert boot.pci_address == "0000:00:02.0"

    def test_to_json(self):
        """Test JSON export."""
        scanner = GPUScanner()
        scanner.devices = [
            GPUDevice(
                pci_address="0000:01:00.0",
                vendor_id="10de",
                device_id="1c03",
                vendor_name="NVIDIA",
                device_name="GTX 1060",
            ),
        ]

        json_output = scanner.to_json()
        parsed = json.loads(json_output)

        assert len(parsed) == 1
        assert parsed[0]["pci_address"] == "0000:01:00.0"
        assert parsed[0]["vendor_id"] == "10de"

    def test_no_passthrough_candidate_when_all_boot_vga(self):
        """Test that None is returned when all GPUs are boot VGA."""
        scanner = GPUScanner()
        scanner.devices = [
            GPUDevice(
                pci_address="0000:00:02.0",
                vendor_id="8086",
                device_id="3e92",
                vendor_name="Intel",
                device_name="UHD 630",
                is_boot_vga=True,  # Only GPU, and it's boot VGA
                iommu_group=0,
            ),
        ]

        # When there's only one GPU and it's integrated boot VGA
        # get_passthrough_candidate returns None because there's
        # no discrete GPU available
        candidate = scanner.get_passthrough_candidate()
        # For single-GPU systems with only iGPU, returns None
        assert candidate is None


class TestGPUScannerOnRealHardware:
    """
    Tests that run on real hardware.
    These are skipped if no GPU hardware is available.
    """

    @pytest.fixture
    def real_scanner(self):
        """Create a scanner and attempt to scan real hardware."""
        scanner = GPUScanner()
        try:
            scanner.scan()
        except Exception:
            pytest.skip("No GPU hardware available for testing")
        return scanner

    def test_scan_returns_list(self, real_scanner):
        """Test that scan returns a list."""
        assert isinstance(real_scanner.devices, list)

    def test_all_devices_have_addresses(self, real_scanner):
        """Test all detected devices have PCI addresses."""
        for device in real_scanner.devices:
            assert device.pci_address is not None
            assert ":" in device.pci_address

    def test_all_devices_have_vendor_ids(self, real_scanner):
        """Test all detected devices have vendor IDs."""
        for device in real_scanner.devices:
            assert device.vendor_id is not None
            assert len(device.vendor_id) == 4  # 4-digit hex


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
