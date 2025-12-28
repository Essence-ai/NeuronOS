#!/usr/bin/env python3
"""
NeuronOS Hardware Detection - Command Line Interface

Unified CLI for all hardware detection functionality.
"""

import argparse
import sys

from .gpu_scanner import GPUScanner
from .iommu_parser import IOMMUParser
from .cpu_detect import CPUDetector
from .config_generator import ConfigGenerator


def cmd_scan(args):
    """Scan and display hardware."""
    print("=== NeuronOS Hardware Detection ===\n")

    # CPU
    cpu = CPUDetector().detect()
    print(f"CPU: {cpu.vendor} {cpu.model_name}")
    print(f"     {cpu.cores} cores, {cpu.threads} threads")
    virt_status = "✅" if cpu.has_virtualization else "❌"
    iommu_status = "✅" if cpu.iommu_enabled else "⚠️"
    print(f"     Virtualization: {virt_status}  IOMMU: {iommu_status}")
    print()

    # GPUs
    scanner = GPUScanner()
    gpus = scanner.scan()

    print(f"GPUs: {len(gpus)} detected")
    for gpu in gpus:
        boot = " (boot VGA)" if gpu.is_boot_vga else ""
        integrated = " [integrated]" if gpu.is_integrated else ""
        print(f"  • {gpu.pci_address}: {gpu.vendor_name} {gpu.device_name}{boot}{integrated}")
        print(f"    IDs: {gpu.vfio_ids}, IOMMU Group: {gpu.iommu_group}, Driver: {gpu.driver_in_use}")
    print()

    # Passthrough recommendation
    candidate = scanner.get_passthrough_candidate()
    if candidate:
        print(f"✅ Recommended for passthrough: {candidate.pci_address}")
        print(f"   {candidate.vendor_name} {candidate.device_name}")
    else:
        print("⚠️  No suitable GPU for passthrough found")


def cmd_iommu(args):
    """Display IOMMU groups."""
    parser = IOMMUParser()
    try:
        parser.parse_all()
        parser.print_report()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_config(args):
    """Generate VFIO configuration."""
    generator = ConfigGenerator()

    if args.apply:
        from pathlib import Path
        target = Path(args.target)
        success = generator.apply_to_target(target, dry_run=args.dry_run)
        sys.exit(0 if success else 1)
    else:
        generator.print_config()


def cmd_check(args):
    """Quick compatibility check."""
    print("=== NeuronOS Compatibility Check ===\n")

    issues = []
    warnings = []

    # Check CPU
    cpu = CPUDetector().detect()
    if not cpu.has_virtualization:
        issues.append("CPU virtualization not detected (enable VT-x/SVM in BIOS)")
    if not cpu.iommu_enabled:
        warnings.append(f"IOMMU not enabled (add kernel parameter: {cpu.iommu_param})")

    # Check GPUs
    scanner = GPUScanner()
    gpus = scanner.scan()
    if len(gpus) < 2:
        warnings.append("Only one GPU detected - single-GPU passthrough has limitations")

    candidate = scanner.get_passthrough_candidate()
    if not candidate:
        issues.append("No GPU available for passthrough")

    # Check IOMMU
    try:
        iommu = IOMMUParser()
        iommu.parse_all()
        if iommu.check_acs_needed():
            warnings.append("ACS Override Patch may be needed for IOMMU isolation")
    except RuntimeError:
        if cpu.iommu_enabled:
            issues.append("IOMMU groups not found despite IOMMU being enabled")

    # Print results
    if issues:
        print("❌ BLOCKING ISSUES:")
        for issue in issues:
            print(f"   • {issue}")
        print()

    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   • {warning}")
        print()

    if not issues and not warnings:
        print("✅ System is fully compatible with NeuronOS GPU passthrough!")
    elif not issues:
        print("✅ System is compatible (with noted caveats)")

    sys.exit(1 if issues else 0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NeuronOS Hardware Detection Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  neuron-hardware-detect scan       # Full hardware scan
  neuron-hardware-detect check      # Quick compatibility check
  neuron-hardware-detect iommu      # Display IOMMU groups
  neuron-hardware-detect config     # Generate VFIO config
  neuron-hardware-detect config -a  # Apply config to system
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan hardware")
    scan_parser.set_defaults(func=cmd_scan)

    # iommu command
    iommu_parser = subparsers.add_parser("iommu", help="Show IOMMU groups")
    iommu_parser.set_defaults(func=cmd_iommu)

    # config command
    config_parser = subparsers.add_parser("config", help="Generate VFIO config")
    config_parser.add_argument("-a", "--apply", action="store_true",
                               help="Apply configuration")
    config_parser.add_argument("-n", "--dry-run", action="store_true",
                               help="Show what would be done")
    config_parser.add_argument("-t", "--target", default="/",
                               help="Target root path")
    config_parser.set_defaults(func=cmd_config)

    # check command
    check_parser = subparsers.add_parser("check", help="Quick compatibility check")
    check_parser.set_defaults(func=cmd_check)

    args = parser.parse_args()

    if args.command is None:
        # Default to scan
        cmd_scan(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
