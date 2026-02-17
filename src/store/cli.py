#!/usr/bin/env python3
"""
NeuronOS Store CLI

Command-line interface for searching, installing, and managing applications.
"""

import argparse
import sys
import logging
from pathlib import Path

# Add module path when running from ISO
if Path("/usr/lib/neuron-os").exists():
    sys.path.insert(0, "/usr/lib/neuron-os")

from store.app_catalog import AppCatalog, AppCategory, CompatibilityLayer
from store.installer import AppInstaller

logger = logging.getLogger(__name__)


def get_catalog() -> AppCatalog:
    """Load and return the app catalog."""
    catalog = AppCatalog()
    if not catalog.load():
        print("Error: Failed to load app catalog.", file=sys.stderr)
        sys.exit(1)
    return catalog


def cmd_search(args):
    """Search for applications."""
    catalog = get_catalog()

    category = None
    if args.category:
        try:
            category = AppCategory(args.category)
        except ValueError:
            print(f"Unknown category: {args.category}", file=sys.stderr)
            print(f"Valid categories: {', '.join(c.value for c in AppCategory)}")
            return 1

    layer = None
    if args.layer:
        try:
            layer = CompatibilityLayer(args.layer)
        except ValueError:
            print(f"Unknown layer: {args.layer}", file=sys.stderr)
            print(f"Valid layers: {', '.join(l.value for l in CompatibilityLayer)}")
            return 1

    results = catalog.search(query=args.query or "", category=category, layer=layer)

    if not results:
        print(f"No apps found for: {args.query or '(all)'}")
        return 0

    print(f"Found {len(results)} app(s):\n")
    for app in results:
        layer_str = app.layer.value
        rating = getattr(app, "compatibility_rating", None)
        rating_str = f" [{rating.value}]" if rating else ""
        print(f"  {app.id}")
        print(f"    {app.name} ({layer_str}{rating_str})")
        if app.description:
            desc = app.description[:80]
            print(f"    {desc}")
        print()

    return 0


def cmd_info(args):
    """Show detailed app information."""
    catalog = get_catalog()
    app = catalog.get(args.app_id)

    if not app:
        print(f"App not found: {args.app_id}", file=sys.stderr)
        return 1

    print(f"Name:        {app.name}")
    print(f"ID:          {app.id}")
    print(f"Category:    {app.category.value}")
    print(f"Layer:       {app.layer.value}")

    rating = getattr(app, "compatibility_rating", None)
    if rating:
        print(f"Rating:      {rating.value}")

    if app.description:
        print(f"Description: {app.description}")

    pkg = getattr(app, "package_name", None)
    if pkg:
        print(f"Package:     {pkg}")

    gpu = getattr(app, "requires_gpu_passthrough", False)
    if gpu:
        print(f"GPU Passthrough: Required")

    min_ram = getattr(app, "min_ram_gb", None)
    if min_ram:
        print(f"Min RAM:     {min_ram} GB")

    # Check installation status
    installer = AppInstaller()
    installed = installer.is_installed(app)
    print(f"Installed:   {'Yes' if installed else 'No'}")

    return 0


def cmd_install(args):
    """Install an application."""
    catalog = get_catalog()
    app = catalog.get(args.app_id)

    if not app:
        print(f"App not found: {args.app_id}", file=sys.stderr)
        return 1

    installer = AppInstaller()

    if installer.is_installed(app):
        print(f"{app.name} is already installed.")
        return 0

    print(f"Installing {app.name} (via {app.layer.value})...")

    def progress_callback(percent, message, status):
        if message:
            print(f"  [{percent}%] {message}")

    installer.set_progress_callback(progress_callback)
    success = installer.install(app)

    if success:
        print(f"Successfully installed {app.name}")
        return 0
    else:
        print(f"Failed to install {app.name}", file=sys.stderr)
        return 1


def cmd_uninstall(args):
    """Uninstall an application."""
    catalog = get_catalog()
    app = catalog.get(args.app_id)

    if not app:
        print(f"App not found: {args.app_id}", file=sys.stderr)
        return 1

    installer = AppInstaller()

    if not installer.is_installed(app):
        print(f"{app.name} is not installed.")
        return 0

    print(f"Uninstalling {app.name}...")
    success = installer.uninstall(app)

    if success:
        print(f"Successfully uninstalled {app.name}")
        return 0
    else:
        print(f"Failed to uninstall {app.name}", file=sys.stderr)
        return 1


def cmd_list(args):
    """List installed applications."""
    catalog = get_catalog()
    installer = AppInstaller()

    installed = []
    for app in catalog.all():
        if installer.is_installed(app):
            installed.append(app)

    if not installed:
        print("No apps installed via NeuronOS Store.")
        return 0

    print(f"Installed apps ({len(installed)}):\n")
    for app in installed:
        print(f"  {app.id}: {app.name} ({app.layer.value})")

    return 0


def cmd_categories(args):
    """List app categories with counts."""
    catalog = get_catalog()

    print("Categories:\n")
    for cat in AppCategory:
        apps = catalog.by_category(cat)
        if apps:
            print(f"  {cat.value}: {len(apps)} app(s)")

    return 0


def cmd_layers(args):
    """Show apps grouped by compatibility layer."""
    catalog = get_catalog()

    for layer in CompatibilityLayer:
        apps = catalog.by_layer(layer)
        if not apps:
            continue

        print(f"\n{layer.value.upper()} ({len(apps)} apps):")
        for app in apps:
            print(f"  {app.id}: {app.name}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="neuron-store",
        description="NeuronOS Application Store",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # search
    search_p = subparsers.add_parser("search", help="Search for apps")
    search_p.add_argument("query", nargs="?", default="", help="Search query")
    search_p.add_argument("-c", "--category", help="Filter by category")
    search_p.add_argument("-l", "--layer", help="Filter by compatibility layer")
    search_p.set_defaults(func=cmd_search)

    # info
    info_p = subparsers.add_parser("info", help="Show app details")
    info_p.add_argument("app_id", help="App ID")
    info_p.set_defaults(func=cmd_info)

    # install
    install_p = subparsers.add_parser("install", help="Install an app")
    install_p.add_argument("app_id", help="App ID")
    install_p.set_defaults(func=cmd_install)

    # uninstall
    uninstall_p = subparsers.add_parser("uninstall", help="Uninstall an app")
    uninstall_p.add_argument("app_id", help="App ID")
    uninstall_p.set_defaults(func=cmd_uninstall)

    # list
    list_p = subparsers.add_parser("list", help="List installed apps")
    list_p.set_defaults(func=cmd_list)

    # categories
    cat_p = subparsers.add_parser("categories", help="List categories")
    cat_p.set_defaults(func=cmd_categories)

    # layers
    layers_p = subparsers.add_parser("layers", help="Show apps by layer")
    layers_p.set_defaults(func=cmd_layers)

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.command is None:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
