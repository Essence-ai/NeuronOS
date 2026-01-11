#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - CPU Detection Module

Detects CPU capabilities for VFIO configuration, specifically:
- CPU vendor (Intel/AMD)
- IOMMU support (VT-d/AMD-Vi)
- Required kernel parameters
"""

import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CPUInfo:
    """CPU information for VFIO configuration."""

    vendor: str              # "Intel" or "AMD"
    model_name: str          # Full model name
    cores: int               # Physical cores
    threads: int             # Total threads
    has_virtualization: bool # VT-x / AMD-V
    has_iommu_support: bool  # VT-d / AMD-Vi capability
    iommu_enabled: bool      # Currently enabled in kernel
    iommu_param: str         # Kernel parameter needed

    @property
    def is_intel(self) -> bool:
        """Check if Intel CPU."""
        return self.vendor == "Intel"

    @property
    def is_amd(self) -> bool:
        """Check if AMD CPU."""
        return self.vendor == "AMD"


class CPUDetector:
    """Detects CPU capabilities for VFIO configuration."""

    CPUINFO_PATH = Path("/proc/cpuinfo")
    DMESG_PATH = Path("/var/log/dmesg")

    def detect(self) -> CPUInfo:
        """Detect CPU information."""
        # Parse /proc/cpuinfo
        cpuinfo = self._parse_cpuinfo()

        # Determine vendor
        vendor = "Unknown"
        vendor_id = cpuinfo.get("vendor_id", "")
        if "GenuineIntel" in vendor_id:
            vendor = "Intel"
        elif "AuthenticAMD" in vendor_id:
            vendor = "AMD"

        # Model name
        model_name = cpuinfo.get("model name", "Unknown CPU")

        # Count cores and threads
        # 'siblings' = threads per socket, 'cpu cores' = physical cores
        siblings = int(cpuinfo.get("siblings", 1))
        cpu_cores = int(cpuinfo.get("cpu cores", 1))

        # Count total by counting processor entries
        processor_count = cpuinfo.get("_processor_count", 1)

        # Calculate totals (assumes symmetric multiprocessing)
        if siblings > 0 and cpu_cores > 0:
            sockets = processor_count // siblings
            sockets = max(1, sockets)
            total_cores = cpu_cores * sockets
            total_threads = processor_count
        else:
            total_cores = processor_count
            total_threads = processor_count

        # Check CPU flags for virtualization support
        flags = cpuinfo.get("flags", "").split()
        has_virt = "vmx" in flags or "svm" in flags

        # Determine IOMMU kernel parameter
        if vendor == "Intel":
            iommu_param = "intel_iommu=on iommu=pt"
        elif vendor == "AMD":
            iommu_param = "amd_iommu=on iommu=pt"
        else:
            iommu_param = "iommu=pt"

        # Check if IOMMU is enabled
        iommu_enabled = self._check_iommu_enabled()

        # Check IOMMU hardware support (harder to determine without testing)
        has_iommu_support = has_virt  # Assume if virt is supported, IOMMU likely is too

        return CPUInfo(
            vendor=vendor,
            model_name=model_name,
            cores=total_cores,
            threads=total_threads,
            has_virtualization=has_virt,
            has_iommu_support=has_iommu_support,
            iommu_enabled=iommu_enabled,
            iommu_param=iommu_param,
        )

    def _parse_cpuinfo(self) -> dict:
        """Parse /proc/cpuinfo into a dictionary."""
        result = {"_processor_count": 0}

        try:
            content = self.CPUINFO_PATH.read_text()
        except IOError:
            return result

        for line in content.split("\n"):
            if line.startswith("processor"):
                result["_processor_count"] += 1

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Only store first occurrence (all cores have same info)
                if key not in result or key == "_processor_count":
                    result[key] = value

        return result

    def _check_iommu_enabled(self) -> bool:
        """Check if IOMMU is currently enabled in the kernel."""
        # Check kernel command line
        try:
            cmdline = Path("/proc/cmdline").read_text()
            if "intel_iommu=on" in cmdline or "amd_iommu=on" in cmdline:
                # Also verify in dmesg
                return self._verify_iommu_dmesg()
        except IOError:
            pass

        return False

    def _verify_iommu_dmesg(self) -> bool:
        """Verify IOMMU is actually working by checking dmesg."""
        try:
            result = subprocess.run(
                ["dmesg"],
                capture_output=True,
                text=True,
                timeout=10
            )

            output = result.stdout

            # Look for IOMMU initialization messages
            indicators = [
                "IOMMU enabled",
                "AMD-Vi: Interrupt remapping enabled",
                "Intel-IOMMU: enabled",
                "DMAR: IOMMU enabled",
            ]

            for indicator in indicators:
                if indicator in output:
                    return True

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # Fallback: check if iommu_groups exist
        iommu_groups = Path("/sys/kernel/iommu_groups")
        if iommu_groups.exists():
            groups = list(iommu_groups.iterdir())
            return len(groups) > 0

        return False

    def check_bios_settings(self) -> dict:
        """
        Return guidance for BIOS settings.

        This doesn't actually read BIOS, but provides instructions
        based on detected hardware.
        """
        cpu = self.detect()

        settings = {
            "virtualization": {
                "name": "VT-x" if cpu.is_intel else "SVM Mode" if cpu.is_amd else "Virtualization",
                "required": True,
                "status": "enabled" if cpu.has_virtualization else "check BIOS",
            },
            "iommu": {
                "name": "VT-d" if cpu.is_intel else "IOMMU" if cpu.is_amd else "IOMMU",
                "required": True,
                "status": "enabled" if cpu.iommu_enabled else "check BIOS",
            },
            "csm": {
                "name": "CSM/Legacy Boot",
                "required": False,
                "status": "should be DISABLED for UEFI",
            },
            "secure_boot": {
                "name": "Secure Boot",
                "required": False,
                "status": "disable for development, can re-enable later",
            },
        }

        return settings

    def print_summary(self) -> None:
        """Print a summary of CPU capabilities."""
        cpu = self.detect()

        print("=== CPU Detection ===\n")
        print(f"Vendor: {cpu.vendor}")
        print(f"Model:  {cpu.model_name}")
        print(f"Cores:  {cpu.cores} physical, {cpu.threads} threads")
        print()
        print("=== Virtualization Support ===\n")

        virt_status = "✅ Enabled" if cpu.has_virtualization else "❌ Not detected"
        iommu_status = "✅ Enabled" if cpu.iommu_enabled else "⚠️  Not enabled"

        print(f"{'VT-x' if cpu.is_intel else 'SVM'}: {virt_status}")
        print(f"{'VT-d' if cpu.is_intel else 'AMD-Vi'}: {iommu_status}")

        if not cpu.iommu_enabled:
            print()
            print("⚠️  IOMMU is not enabled!")
            print()
            print("To enable, add this to your kernel command line:")
            print(f"    {cpu.iommu_param}")
            print()
            print("For GRUB, edit /etc/default/grub and run grub-mkconfig")
            print("For systemd-boot, edit /boot/loader/entries/*.conf")


def main():
    """Command-line interface for CPU detection."""
    import argparse

    parser = argparse.ArgumentParser(description="NeuronOS CPU Detector")
    parser.add_argument("-p", "--param", action="store_true",
                        help="Only output kernel parameter")
    parser.add_argument("-c", "--check", action="store_true",
                        help="Check if IOMMU is enabled (exit code)")
    args = parser.parse_args()

    detector = CPUDetector()
    cpu = detector.detect()

    if args.param:
        print(cpu.iommu_param)
    elif args.check:
        if cpu.iommu_enabled:
            print("IOMMU is enabled")
            exit(0)
        else:
            print("IOMMU is NOT enabled")
            exit(1)
    else:
        detector.print_summary()


if __name__ == "__main__":
    main()
