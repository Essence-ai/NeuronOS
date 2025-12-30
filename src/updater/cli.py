#!/usr/bin/env python3
"""
NeuronOS Update CLI

Command-line interface for system updates and rollback.
"""

import argparse
import logging
import sys
from typing import Optional

from .updater import UpdateManager, UpdateStatus, UpdateInfo
from .snapshot import SnapshotManager, Snapshot
from .rollback import RollbackManager, RollbackStatus

logger = logging.getLogger(__name__)


def format_size(bytes_val: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def progress_callback(status: UpdateStatus, message: str, percent: float):
    """Display update progress."""
    bar_width = 30
    filled = int(bar_width * percent / 100)
    bar = "=" * filled + "-" * (bar_width - filled)
    print(f"\r[{bar}] {percent:.0f}% {message[:40]:40s}", end="", flush=True)
    if percent >= 100:
        print()


def cmd_check(args):
    """Check for available updates."""
    print("Checking for updates...")

    manager = UpdateManager()
    info = manager.check_for_updates()

    if not info.packages:
        print("\nSystem is up to date.")
        return 0

    print(f"\n{info.package_count} packages can be upgraded:\n")

    for pkg in info.packages[:20]:  # Show first 20
        print(f"  {pkg.name}: {pkg.old_version} -> {pkg.new_version}")

    if len(info.packages) > 20:
        print(f"  ... and {len(info.packages) - 20} more")

    print(f"\nDownload size: {info.download_size_str}")

    if info.has_security_updates:
        print("\n[!] Security updates are available!")

    return 0


def cmd_update(args):
    """Install system updates."""
    manager = UpdateManager()

    # Check first
    print("Checking for updates...")
    info = manager.check_for_updates()

    if not info.packages:
        print("System is up to date.")
        return 0

    print(f"\n{info.package_count} packages will be upgraded.")

    if not args.yes:
        response = input("\nProceed with update? [y/N] ")
        if response.lower() != "y":
            print("Update cancelled.")
            return 0

    print()
    manager.set_progress_callback(progress_callback)

    success = manager.install_updates(
        create_snapshot=not args.no_snapshot,
        verify_after=not args.no_verify,
    )

    if success:
        print("\nUpdates installed successfully!")
        return 0
    else:
        print("\nUpdate failed!")
        if manager.get_rollback_snapshot():
            print("A rollback snapshot is available. Run 'neuron-update rollback' to restore.")
        return 1


def cmd_snapshot(args):
    """Manage system snapshots."""
    manager = SnapshotManager()

    if not manager.is_available:
        print("Timeshift is not installed or configured.")
        print("Install with: sudo pacman -S timeshift")
        return 1

    if args.action == "list":
        snapshots = manager.get_snapshots()
        if not snapshots:
            print("No snapshots found.")
            return 0

        print("System Snapshots:\n")
        for snap in snapshots:
            print(f"  {snap.name}")
            print(f"    Created: {snap.timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({snap.age_str})")
            print(f"    Type: {snap.snapshot_type.value}")
            if snap.description:
                print(f"    Description: {snap.description}")
            print()

    elif args.action == "create":
        desc = args.description or f"Manual snapshot at {args.description}"
        print(f"Creating snapshot: {desc}")
        snapshot = manager.create_snapshot(desc)
        if snapshot:
            print(f"Snapshot created: {snapshot.name}")
        else:
            print("Failed to create snapshot")
            return 1

    elif args.action == "delete":
        if not args.name:
            print("Please specify snapshot name with --name")
            return 1

        snapshots = manager.get_snapshots()
        target = None
        for snap in snapshots:
            if snap.name == args.name:
                target = snap
                break

        if not target:
            print(f"Snapshot not found: {args.name}")
            return 1

        if not args.yes:
            response = input(f"Delete snapshot '{args.name}'? [y/N] ")
            if response.lower() != "y":
                return 0

        if manager.delete_snapshot(target):
            print("Snapshot deleted.")
        else:
            print("Failed to delete snapshot")
            return 1

    return 0


def cmd_rollback(args):
    """Rollback to a previous snapshot."""
    manager = RollbackManager()

    if not manager.snapshot_manager.is_available:
        print("Timeshift is not installed or configured.")
        return 1

    if args.snapshot:
        # Rollback to specific snapshot
        snapshots = manager.get_available_snapshots()
        target = None
        for snap in snapshots:
            if snap.name == args.snapshot:
                target = snap
                break

        if not target:
            print(f"Snapshot not found: {args.snapshot}")
            return 1
    else:
        # Rollback to last pre-update snapshot
        target = manager.snapshot_manager.get_latest_pre_update_snapshot()
        if not target:
            print("No pre-update snapshot found.")
            print("Use --snapshot NAME to specify a snapshot.")
            return 1

    print(f"Target snapshot: {target.name}")
    print(f"  Created: {target.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if target.description:
        print(f"  Description: {target.description}")

    print("\n[WARNING] This will restore your system to this snapshot.")
    print("All changes since this snapshot will be lost!")

    if not args.yes:
        response = input("\nProceed with rollback? [y/N] ")
        if response.lower() != "y":
            print("Rollback cancelled.")
            return 0

    result = manager.rollback_to_snapshot(target)

    if result.success:
        print(f"\n{result.message}")
        if result.requires_reboot:
            if args.yes or input("Reboot now? [y/N] ").lower() == "y":
                manager.reboot_system()
        return 0
    else:
        print(f"\nRollback failed: {result.message}")
        return 1


def cmd_configure(args):
    """Configure automatic snapshots."""
    manager = SnapshotManager()

    success = manager.configure(
        schedule_boot=args.boot,
        schedule_daily=args.daily,
        schedule_weekly=args.weekly,
        schedule_monthly=args.monthly,
        keep_boot=args.keep_boot,
        keep_daily=args.keep_daily,
        keep_weekly=args.keep_weekly,
        keep_monthly=args.keep_monthly,
    )

    if success:
        print("Snapshot configuration saved.")
        print("\nCurrent schedule:")
        print(f"  Boot snapshots: {'Yes' if args.boot else 'No'} (keep {args.keep_boot})")
        print(f"  Daily snapshots: {'Yes' if args.daily else 'No'} (keep {args.keep_daily})")
        print(f"  Weekly snapshots: {'Yes' if args.weekly else 'No'} (keep {args.keep_weekly})")
        print(f"  Monthly snapshots: {'Yes' if args.monthly else 'No'} (keep {args.keep_monthly})")
    else:
        print("Failed to save configuration")
        return 1

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NeuronOS Update and Rollback System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  neuron-update check                    # Check for updates
  neuron-update update                   # Install updates with snapshot
  neuron-update update --no-snapshot     # Update without snapshot
  neuron-update snapshot list            # List snapshots
  neuron-update snapshot create -d "Before changes"
  neuron-update rollback                 # Rollback to last pre-update
  neuron-update rollback --snapshot NAME # Rollback to specific snapshot
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # check command
    check_parser = subparsers.add_parser("check", help="Check for updates")
    check_parser.set_defaults(func=cmd_check)

    # update command
    update_parser = subparsers.add_parser("update", help="Install updates")
    update_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    update_parser.add_argument("--no-snapshot", action="store_true",
                               help="Don't create snapshot before update")
    update_parser.add_argument("--no-verify", action="store_true",
                               help="Don't verify system after update")
    update_parser.set_defaults(func=cmd_update)

    # snapshot command
    snap_parser = subparsers.add_parser("snapshot", help="Manage snapshots")
    snap_parser.add_argument("action", choices=["list", "create", "delete"],
                             help="Snapshot action")
    snap_parser.add_argument("-d", "--description", help="Snapshot description")
    snap_parser.add_argument("-n", "--name", help="Snapshot name (for delete)")
    snap_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    snap_parser.set_defaults(func=cmd_snapshot)

    # rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback system")
    rollback_parser.add_argument("-s", "--snapshot", help="Specific snapshot to restore")
    rollback_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    rollback_parser.set_defaults(func=cmd_rollback)

    # configure command
    config_parser = subparsers.add_parser("configure", help="Configure automatic snapshots")
    config_parser.add_argument("--boot", action="store_true", default=True,
                               help="Enable boot snapshots")
    config_parser.add_argument("--no-boot", dest="boot", action="store_false")
    config_parser.add_argument("--daily", action="store_true", default=True)
    config_parser.add_argument("--no-daily", dest="daily", action="store_false")
    config_parser.add_argument("--weekly", action="store_true", default=True)
    config_parser.add_argument("--no-weekly", dest="weekly", action="store_false")
    config_parser.add_argument("--monthly", action="store_true", default=True)
    config_parser.add_argument("--no-monthly", dest="monthly", action="store_false")
    config_parser.add_argument("--keep-boot", type=int, default=5)
    config_parser.add_argument("--keep-daily", type=int, default=5)
    config_parser.add_argument("--keep-weekly", type=int, default=3)
    config_parser.add_argument("--keep-monthly", type=int, default=2)
    config_parser.set_defaults(func=cmd_configure)

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.command is None:
        # Default to check
        return cmd_check(args)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
