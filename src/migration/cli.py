#!/usr/bin/env python3
"""
NeuronOS Migration CLI

Command-line interface for migrating files from Windows/macOS.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .drive_detector import DriveDetector, DriveType
from .migrator import (
    create_migrator,
    FileCategory,
    MigrationSource,
    MigrationTarget,
    MigrationProgress,
)

logger = logging.getLogger(__name__)


def format_size(bytes_val: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


def progress_callback(progress: MigrationProgress):
    """Display progress during migration."""
    bar_width = 40
    filled = int(bar_width * progress.percent / 100)
    bar = "=" * filled + "-" * (bar_width - filled)

    print(
        f"\r[{bar}] {progress.percent:.1f}% "
        f"({progress.files_done}/{progress.files_total}) "
        f"{progress.current_file[:30]:30s}",
        end="",
        flush=True,
    )


def cmd_scan(args):
    """Scan for available drives."""
    print("Scanning for drives...\n")

    detector = DriveDetector()
    drives = detector.scan()

    # Group by type
    windows_drives = [d for d in drives if d.drive_type == DriveType.WINDOWS]
    macos_drives = [d for d in drives if d.drive_type == DriveType.MACOS]
    other_drives = [d for d in drives if d.drive_type not in (DriveType.WINDOWS, DriveType.MACOS)]

    if windows_drives:
        print("Windows Installations:")
        for drive in windows_drives:
            users = ", ".join(drive.users) if drive.users else "No users found"
            print(f"  {drive.device} ({drive.size_display})")
            print(f"    Mount: {drive.mount_point}")
            print(f"    Users: {users}")
        print()

    if macos_drives:
        print("macOS Installations:")
        for drive in macos_drives:
            users = ", ".join(drive.users) if drive.users else "No users found"
            print(f"  {drive.device} ({drive.size_display})")
            print(f"    Mount: {drive.mount_point}")
            print(f"    Users: {users}")
        print()

    if other_drives and args.all:
        print("Other Drives:")
        for drive in other_drives:
            print(f"  {drive.device} ({drive.size_display}) - {drive.filesystem}")
        print()

    if not windows_drives and not macos_drives:
        print("No Windows or macOS installations found.")
        print("Make sure the drives are mounted and try again.")
        return 1

    return 0


def cmd_migrate(args):
    """Perform file migration."""
    source_path = Path(args.source)
    target_path = Path(args.target) if args.target else Path.home()

    if not source_path.exists():
        print(f"Error: Source path does not exist: {source_path}")
        return 1

    # Detect OS type
    os_type = args.type
    if not os_type:
        detector = DriveDetector()
        detector.scan()
        # Try to detect from path
        if (source_path / "AppData").exists():
            os_type = "windows"
        elif (source_path / "Library").exists():
            os_type = "macos"
        else:
            print("Could not detect OS type. Use --type windows or --type macos")
            return 1

    # Parse categories
    categories = None
    if args.categories:
        categories = []
        for cat in args.categories.split(","):
            try:
                categories.append(FileCategory(cat.strip().lower()))
            except ValueError:
                print(f"Unknown category: {cat}")
                print(f"Valid categories: {', '.join(c.value for c in FileCategory)}")
                return 1

    # Get username from path
    user = source_path.name

    # Create migrator
    source = MigrationSource(path=source_path, user=user, os_type=os_type)
    target = MigrationTarget(path=target_path)
    migrator = create_migrator(source, target, categories)

    print(f"Migration: {os_type.title()} -> NeuronOS")
    print(f"Source: {source_path}")
    print(f"Target: {target_path}")
    print()

    # Scan first
    print("Scanning files...")
    migrator.scan()
    print(f"Found {migrator.progress.files_total} files ({format_size(migrator.progress.bytes_total)})")
    print()

    if migrator.progress.files_total == 0:
        print("No files to migrate.")
        return 0

    # Confirm
    if not args.yes:
        response = input("Proceed with migration? [y/N] ")
        if response.lower() != "y":
            print("Migration cancelled.")
            return 0

    # Migrate
    print("\nMigrating files...")
    migrator.set_progress_callback(progress_callback)
    success = migrator.migrate()
    print()  # New line after progress bar

    # Report results
    print()
    print(f"Migration complete: {migrator.progress.files_done} files copied")

    if migrator.progress.errors:
        print(f"\nWarnings ({len(migrator.progress.errors)}):")
        for error in migrator.progress.errors[:10]:
            print(f"  - {error}")
        if len(migrator.progress.errors) > 10:
            print(f"  ... and {len(migrator.progress.errors) - 10} more")

    return 0 if success else 1


def cmd_list_categories(args):
    """List available file categories."""
    print("Available file categories:\n")
    for cat in FileCategory:
        print(f"  {cat.value}")
    print("\nUse with: neuron-migrate migrate --categories documents,pictures,music")
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NeuronOS Migration Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  neuron-migrate scan                              # Find Windows/macOS drives
  neuron-migrate migrate /mnt/windows/Users/John   # Migrate from Windows
  neuron-migrate migrate /mnt/mac/Users/John --type macos
  neuron-migrate migrate /mnt/windows/Users/John --categories documents,pictures
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for drives")
    scan_parser.add_argument("-a", "--all", action="store_true", help="Show all drives")
    scan_parser.set_defaults(func=cmd_scan)

    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Migrate files")
    migrate_parser.add_argument("source", help="Source user directory (e.g., /mnt/windows/Users/John)")
    migrate_parser.add_argument("-t", "--target", help="Target directory (default: home)")
    migrate_parser.add_argument("--type", choices=["windows", "macos"], help="Source OS type")
    migrate_parser.add_argument("-c", "--categories", help="Comma-separated list of categories")
    migrate_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    migrate_parser.set_defaults(func=cmd_migrate)

    # categories command
    cat_parser = subparsers.add_parser("categories", help="List file categories")
    cat_parser.set_defaults(func=cmd_list_categories)

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
