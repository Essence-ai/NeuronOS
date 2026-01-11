#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - VFIO Configuration Generator

Generates all necessary configuration files for GPU passthrough:
- /etc/modprobe.d/vfio.conf (device binding)
- mkinitcpio.conf MODULES line
- Kernel command line parameters
- Bootloader configuration updates
"""

import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

from .gpu_scanner import GPUScanner, GPUDevice
from .iommu_parser import IOMMUParser, IOMMUGroup
from .cpu_detect import CPUDetector


@dataclass
class VFIOConfig:
    """Generated VFIO configuration."""

    # File contents
    vfio_conf: str              # Content for /etc/modprobe.d/vfio.conf
    mkinitcpio_modules: str     # MODULES line for mkinitcpio.conf
    kernel_params: str          # Kernel command line parameters

    # Metadata
    bootloader: str             # Detected bootloader ("grub" or "systemd-boot")
    passthrough_gpu: Optional[GPUDevice]  # GPU selected for passthrough
    boot_gpu: Optional[GPUDevice]         # GPU for host display

    # Issues and warnings
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if configuration is valid and ready to apply."""
        return len(self.errors) == 0 and self.passthrough_gpu is not None


class ConfigGenerator:
    """Generates VFIO configuration files."""

    def __init__(self):
        self.scanner = GPUScanner()
        self.iommu_parser = IOMMUParser()
        self.cpu_detector = CPUDetector()

    def detect_bootloader(self, target_root: Path = Path("/")) -> str:
        """Detect which bootloader is installed."""
        # Check for systemd-boot first (more modern)
        systemd_boot = target_root / "boot/loader/loader.conf"
        if systemd_boot.exists():
            return "systemd-boot"

        # Check for GRUB
        grub_cfg = target_root / "boot/grub/grub.cfg"
        if grub_cfg.exists():
            return "grub"

        # Check EFI directory for clues
        efi_boot = target_root / "boot/EFI"
        if efi_boot.exists():
            if (efi_boot / "systemd").exists():
                return "systemd-boot"
            if (efi_boot / "grub").exists():
                return "grub"

        return "unknown"

    def detect_and_generate(self) -> VFIOConfig:
        """Run full hardware detection and generate configuration."""
        warnings = []
        errors = []
        passthrough_gpu = None
        boot_gpu = None

        # Step 1: Detect CPU and get IOMMU parameter
        cpu = self.cpu_detector.detect()

        if not cpu.has_virtualization:
            errors.append(
                "CPU virtualization (VT-x/SVM) not detected! "
                "Enable in BIOS settings."
            )

        if not cpu.iommu_enabled:
            warnings.append(
                f"IOMMU not currently enabled. After applying config, add kernel parameter: {cpu.iommu_param}"
            )

        # Step 2: Scan GPUs
        gpus = self.scanner.scan()

        if not gpus:
            errors.append("No GPUs detected! Cannot configure passthrough.")
            return VFIOConfig(
                vfio_conf="",
                mkinitcpio_modules="",
                kernel_params=cpu.iommu_param,
                bootloader=self.detect_bootloader(),
                passthrough_gpu=None,
                boot_gpu=None,
                warnings=warnings,
                errors=errors,
            )

        if len(gpus) < 2:
            warnings.append(
                "Only one GPU detected. Single-GPU passthrough is possible but "
                "requires dynamic switching and causes brief screen blackout when launching VMs."
            )

        # Step 3: Identify GPUs for passthrough
        passthrough_gpu = self.scanner.get_passthrough_candidate()
        boot_gpu = self.scanner.get_boot_gpu()

        if not passthrough_gpu:
            errors.append(
                "No suitable GPU found for passthrough. All GPUs are marked as boot VGA. "
                "For single-GPU passthrough, you need to manually configure switching."
            )
            return VFIOConfig(
                vfio_conf="",
                mkinitcpio_modules="",
                kernel_params=cpu.iommu_param,
                bootloader=self.detect_bootloader(),
                passthrough_gpu=None,
                boot_gpu=boot_gpu,
                warnings=warnings,
                errors=errors,
            )

        # Step 4: Parse IOMMU groups
        gpu_group = None
        try:
            self.iommu_parser.parse_all()
            gpu_group = self.iommu_parser.get_gpu_group(passthrough_gpu.pci_address)

            if gpu_group and not gpu_group.is_clean:
                warnings.append(
                    f"IOMMU group {gpu_group.group_id} contains non-GPU devices. "
                    "ACS Override Patch may be required for proper isolation. "
                    "See: https://wiki.archlinux.org/title/PCI_passthrough_via_OVMF#Bypassing_the_IOMMU_groups_(ACS_override_patch)"
                )
        except RuntimeError as e:
            warnings.append(str(e))

        # Step 5: Collect all PCI IDs for VFIO binding
        pci_ids = self._get_vfio_ids(passthrough_gpu, gpu_group)

        # Step 6: Generate configuration files
        vfio_conf = self._generate_vfio_conf(pci_ids, passthrough_gpu)
        mkinitcpio_modules = self._generate_mkinitcpio()
        kernel_params = cpu.iommu_param
        bootloader = self.detect_bootloader()

        return VFIOConfig(
            vfio_conf=vfio_conf,
            mkinitcpio_modules=mkinitcpio_modules,
            kernel_params=kernel_params,
            bootloader=bootloader,
            passthrough_gpu=passthrough_gpu,
            boot_gpu=boot_gpu,
            warnings=warnings,
            errors=errors,
        )

    def _get_vfio_ids(self, gpu: GPUDevice, group: Optional[IOMMUGroup]) -> List[str]:
        """Get all PCI IDs that should be bound to vfio-pci."""
        ids = [gpu.vfio_ids]

        if group:
            for device in group.passthrough_devices:
                # Add audio controllers and other devices in the same group
                if device.pci_address != gpu.pci_address:
                    vfio_id = device.vfio_ids
                    if vfio_id not in ids:
                        ids.append(vfio_id)

        return ids

    def _generate_vfio_conf(self, pci_ids: List[str], gpu: GPUDevice) -> str:
        """Generate /etc/modprobe.d/vfio.conf content."""
        ids_str = ",".join(pci_ids)

        content = f"""# NeuronOS VFIO Configuration
# Auto-generated for GPU passthrough
# Target GPU: {gpu.vendor_name} {gpu.device_name}
# PCI Address: {gpu.pci_address}
#
# This file binds the discrete GPU to the vfio-pci driver at boot,
# making it available for VM passthrough instead of the host.

# Bind these devices to vfio-pci driver
options vfio-pci ids={ids_str}

# Ensure vfio-pci loads before any GPU drivers
# This prevents the GPU driver from claiming the device first
softdep nvidia pre: vfio-pci
softdep nvidia_drm pre: vfio-pci
softdep nvidia_modeset pre: vfio-pci
softdep nouveau pre: vfio-pci
softdep amdgpu pre: vfio-pci
softdep radeon pre: vfio-pci
softdep i915 pre: vfio-pci

# Blacklist the GPU driver for the passthrough device (optional)
# Uncomment if needed:
# blacklist nouveau
# blacklist nvidia
"""
        return content

    def _generate_mkinitcpio(self) -> str:
        """Generate MODULES line for mkinitcpio.conf."""
        return "MODULES=(vfio_pci vfio vfio_iommu_type1)"

    def apply_to_target(self, target_root: Path, dry_run: bool = False) -> bool:
        """
        Apply generated configs to a target installation path.

        Args:
            target_root: Root path of the target system (e.g., "/mnt" during install)
            dry_run: If True, only print what would be done

        Returns:
            True if successful, False if errors occurred
        """
        config = self.detect_and_generate()

        if not config.is_valid:
            print("❌ Configuration is not valid:")
            for error in config.errors:
                print(f"   - {error}")
            return False

        if dry_run:
            print("=== DRY RUN - No changes will be made ===\n")

        # 1. Write vfio.conf
        vfio_path = target_root / "etc/modprobe.d/vfio.conf"
        self._write_file(vfio_path, config.vfio_conf, dry_run)

        # 2. Update mkinitcpio.conf
        mkinitcpio_path = target_root / "etc/mkinitcpio.conf"
        self._update_mkinitcpio(mkinitcpio_path, config.mkinitcpio_modules, dry_run)

        # 3. Update bootloader
        if config.bootloader == "grub":
            self._update_grub(target_root, config.kernel_params, dry_run)
        elif config.bootloader == "systemd-boot":
            self._update_systemd_boot(target_root, config.kernel_params, dry_run)
        else:
            print(f"⚠️  Unknown bootloader. Manually add kernel parameter: {config.kernel_params}")

        # 4. Regenerate initramfs (if not dry run and target is live system)
        if not dry_run and target_root == Path("/"):
            self._regenerate_initramfs()

        # Print warnings
        if config.warnings:
            print("\n⚠️  Warnings:")
            for warning in config.warnings:
                print(f"   - {warning}")

        print("\n✅ VFIO configuration complete!")
        print(f"   Passthrough GPU: {config.passthrough_gpu.pci_address}")
        print(f"   VFIO IDs: {config.passthrough_gpu.vfio_ids}")

        if not dry_run:
            print("\n🔄 Reboot required for changes to take effect.")

        return True

    def _write_file(self, path: Path, content: str, dry_run: bool) -> None:
        """Write a file, creating parent directories if needed."""
        if dry_run:
            print(f"Would write: {path}")
            print(f"Content:\n{content[:200]}...")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"✓ Written: {path}")

    def _update_mkinitcpio(self, path: Path, modules: str, dry_run: bool) -> None:
        """Update mkinitcpio.conf with VFIO modules."""
        if not path.exists():
            print(f"⚠️  {path} not found, skipping")
            return

        content = path.read_text()

        # Replace MODULES line
        if "MODULES=" in content:
            new_content = re.sub(
                r'MODULES=\([^)]*\)',
                modules,
                content
            )

            if dry_run:
                print(f"Would update {path}: MODULES line")
            else:
                path.write_text(new_content)
                print(f"✓ Updated: {path}")
        else:
            print(f"⚠️  MODULES= not found in {path}")

    def _update_grub(self, target_root: Path, params: str, dry_run: bool) -> None:
        """Update GRUB configuration."""
        grub_default = target_root / "etc/default/grub"

        if not grub_default.exists():
            print(f"⚠️  {grub_default} not found")
            return

        content = grub_default.read_text()

        # Check if params already present
        if params in content:
            print("✓ Kernel params already in GRUB config")
            return

        # Add to GRUB_CMDLINE_LINUX_DEFAULT
        if 'GRUB_CMDLINE_LINUX_DEFAULT="' in content:
            new_content = re.sub(
                r'(GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)',
                f'\\1 {params}',
                content
            )

            if dry_run:
                print(f"Would update {grub_default}: add {params}")
            else:
                grub_default.write_text(new_content)
                print(f"✓ Updated: {grub_default}")

                # Regenerate grub.cfg
                grub_cfg = target_root / "boot/grub/grub.cfg"
                if grub_cfg.exists():
                    try:
                        subprocess.run(
                            ["grub-mkconfig", "-o", str(grub_cfg)],
                            check=True,
                            capture_output=True
                        )
                        print(f"✓ Regenerated: {grub_cfg}")
                    except subprocess.CalledProcessError as e:
                        print(f"⚠️  Failed to regenerate grub.cfg: {e}")

    def _update_systemd_boot(self, target_root: Path, params: str, dry_run: bool) -> None:
        """Update systemd-boot configuration."""
        entries_dir = target_root / "boot/loader/entries"

        if not entries_dir.exists():
            print(f"⚠️  {entries_dir} not found")
            return

        for entry in entries_dir.glob("*.conf"):
            content = entry.read_text()

            # Check if params already present
            if params in content:
                print(f"✓ Kernel params already in {entry.name}")
                continue

            # Add to options line
            lines = content.split("\n")
            new_lines = []

            for line in lines:
                if line.strip().startswith("options "):
                    line = f"{line} {params}"
                new_lines.append(line)

            if dry_run:
                print(f"Would update {entry}: add {params}")
            else:
                entry.write_text("\n".join(new_lines))
                print(f"✓ Updated: {entry}")

    def _regenerate_initramfs(self) -> None:
        """Regenerate initramfs after config changes."""
        try:
            subprocess.run(
                ["mkinitcpio", "-P"],
                check=True,
                capture_output=True
            )
            print("✓ Regenerated initramfs")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to regenerate initramfs: {e}")
        except FileNotFoundError:
            print("⚠️  mkinitcpio not found")

    def print_config(self) -> None:
        """Print generated configuration without applying."""
        config = self.detect_and_generate()

        print("=== NeuronOS VFIO Configuration Generator ===\n")

        if config.errors:
            print("❌ ERRORS:")
            for error in config.errors:
                print(f"   - {error}")
            print()

        if config.passthrough_gpu:
            print(f"Passthrough GPU: {config.passthrough_gpu.pci_address}")
            print(f"  {config.passthrough_gpu.vendor_name} {config.passthrough_gpu.device_name}")
            print()

        if config.boot_gpu:
            print(f"Host Display GPU: {config.boot_gpu.pci_address}")
            print(f"  {config.boot_gpu.vendor_name} {config.boot_gpu.device_name}")
            print()

        print(f"Detected Bootloader: {config.bootloader}")
        print()

        print("--- /etc/modprobe.d/vfio.conf ---")
        print(config.vfio_conf)

        print("--- mkinitcpio.conf MODULES ---")
        print(config.mkinitcpio_modules)
        print()

        print("--- Kernel Parameters ---")
        print(config.kernel_params)
        print()

        if config.warnings:
            print("⚠️  WARNINGS:")
            for warning in config.warnings:
                print(f"   - {warning}")


def main():
    """Command-line interface for configuration generation."""
    import argparse

    parser = argparse.ArgumentParser(description="NeuronOS VFIO Config Generator")
    parser.add_argument("-a", "--apply", action="store_true",
                        help="Apply configuration to system")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("-t", "--target", type=str, default="/",
                        help="Target root path (default: /)")
    args = parser.parse_args()

    generator = ConfigGenerator()

    if args.apply or args.dry_run:
        target = Path(args.target)
        generator.apply_to_target(target, dry_run=args.dry_run)
    else:
        generator.print_config()


if __name__ == "__main__":
    main()
