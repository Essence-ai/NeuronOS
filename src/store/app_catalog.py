"""
App Catalog - Application database and compatibility information.

Manages the catalog of applications with their compatibility ratings
and recommended installation methods.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class CompatibilityLayer(Enum):
    """How an application runs on NeuronOS."""
    NATIVE = "native"           # Native Linux application
    WINE = "wine"               # Wine compatibility layer
    PROTON = "proton"           # Steam Proton
    VM_WINDOWS = "vm_windows"   # Windows VM required
    VM_MACOS = "vm_macos"       # macOS VM required
    FLATPAK = "flatpak"         # Flatpak package
    APPIMAGE = "appimage"       # AppImage


class CompatibilityRating(Enum):
    """How well an application works."""
    PERFECT = "perfect"         # Works flawlessly
    GOOD = "good"               # Minor issues
    PLAYABLE = "playable"       # Works with workarounds
    RUNS = "runs"               # Starts but has issues
    BROKEN = "broken"           # Does not work


class AppCategory(Enum):
    """Application categories."""
    PRODUCTIVITY = "productivity"
    CREATIVE = "creative"
    GAMING = "gaming"
    DEVELOPMENT = "development"
    COMMUNICATION = "communication"
    MEDIA = "media"
    UTILITIES = "utilities"
    SYSTEM = "system"


@dataclass
class AppInfo:
    """Information about an application."""
    id: str
    name: str
    description: str
    category: AppCategory
    layer: CompatibilityLayer
    rating: CompatibilityRating

    # Optional fields
    version: Optional[str] = None
    publisher: Optional[str] = None
    website: Optional[str] = None
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None

    # Installation info
    package_name: Optional[str] = None  # For native/flatpak
    wine_prefix: Optional[str] = None   # Wine prefix path
    proton_app_id: Optional[int] = None # Steam app ID
    installer_url: Optional[str] = None # Download URL

    # Compatibility notes
    notes: List[str] = field(default_factory=list)
    workarounds: List[str] = field(default_factory=list)
    known_issues: List[str] = field(default_factory=list)

    # Tags for search
    tags: List[str] = field(default_factory=list)

    # Requirements
    requires_gpu_passthrough: bool = False
    min_ram_gb: int = 2
    min_vram_gb: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "layer": self.layer.value,
            "rating": self.rating.value,
            "version": self.version,
            "publisher": self.publisher,
            "website": self.website,
            "icon_url": self.icon_url,
            "package_name": self.package_name,
            "proton_app_id": self.proton_app_id,
            "installer_url": self.installer_url,
            "notes": self.notes,
            "workarounds": self.workarounds,
            "known_issues": self.known_issues,
            "tags": self.tags,
            "requires_gpu_passthrough": self.requires_gpu_passthrough,
            "min_ram_gb": self.min_ram_gb,
            "min_vram_gb": self.min_vram_gb,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppInfo":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            category=AppCategory(data.get("category", "utilities")),
            layer=CompatibilityLayer(data.get("layer", "native")),
            rating=CompatibilityRating(data.get("rating", "good")),
            version=data.get("version"),
            publisher=data.get("publisher"),
            website=data.get("website"),
            icon_url=data.get("icon_url"),
            package_name=data.get("package_name"),
            proton_app_id=data.get("proton_app_id"),
            installer_url=data.get("installer_url"),
            notes=data.get("notes", []),
            workarounds=data.get("workarounds", []),
            known_issues=data.get("known_issues", []),
            tags=data.get("tags", []),
            requires_gpu_passthrough=data.get("requires_gpu_passthrough", False),
            min_ram_gb=data.get("min_ram_gb", 2),
            min_vram_gb=data.get("min_vram_gb", 0),
        )


class AppCatalog:
    """
    Application catalog management.

    Loads and provides access to the app database with search
    and filtering capabilities.
    """

    def __init__(self, catalog_path: Optional[Path] = None):
        """
        Initialize AppCatalog.

        Args:
            catalog_path: Path to apps.json catalog file
        """
        if catalog_path:
            self.catalog_path = catalog_path
        else:
            # Check installed location first, then development location
            installed_path = Path("/usr/share/neuron-os/apps.json")
            dev_path = Path(__file__).parent.parent.parent / "data" / "apps.json"

            if installed_path.exists():
                self.catalog_path = installed_path
            else:
                self.catalog_path = dev_path

        self._apps: Dict[str, AppInfo] = {}
        self._loaded = False

    def load(self) -> bool:
        """
        Load the catalog from disk.

        Returns:
            True if loaded successfully.
        """
        if not self.catalog_path.exists():
            logger.warning(f"Catalog not found: {self.catalog_path}")
            return False

        try:
            with open(self.catalog_path, "r") as f:
                data = json.load(f)

            self._apps = {}
            for app_data in data.get("apps", []):
                try:
                    app = AppInfo.from_dict(app_data)
                    self._apps[app.id] = app
                except Exception as e:
                    logger.warning(f"Failed to load app: {e}")

            self._loaded = True
            logger.info(f"Loaded {len(self._apps)} apps from catalog")
            return True

        except Exception as e:
            logger.error(f"Failed to load catalog: {e}")
            return False

    def save(self) -> bool:
        """
        Save the catalog to disk.

        Returns:
            True if saved successfully.
        """
        try:
            self.catalog_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0",
                "apps": [app.to_dict() for app in self._apps.values()],
            }

            with open(self.catalog_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(self._apps)} apps to catalog")
            return True

        except Exception as e:
            logger.error(f"Failed to save catalog: {e}")
            return False

    def get(self, app_id: str) -> Optional[AppInfo]:
        """Get app by ID."""
        return self._apps.get(app_id)

    def add(self, app: AppInfo) -> None:
        """Add or update an app in the catalog."""
        self._apps[app.id] = app

    def remove(self, app_id: str) -> bool:
        """Remove an app from the catalog."""
        if app_id in self._apps:
            del self._apps[app_id]
            return True
        return False

    def all(self) -> List[AppInfo]:
        """Get all apps."""
        return list(self._apps.values())

    def search(
        self,
        query: str = "",
        category: Optional[AppCategory] = None,
        layer: Optional[CompatibilityLayer] = None,
        min_rating: Optional[CompatibilityRating] = None,
    ) -> List[AppInfo]:
        """
        Search the catalog.

        Args:
            query: Text search in name, description, tags
            category: Filter by category
            layer: Filter by compatibility layer
            min_rating: Minimum compatibility rating

        Returns:
            List of matching apps.
        """
        results = []
        query_lower = query.lower()

        # Rating order for comparison
        rating_order = {
            CompatibilityRating.PERFECT: 5,
            CompatibilityRating.GOOD: 4,
            CompatibilityRating.PLAYABLE: 3,
            CompatibilityRating.RUNS: 2,
            CompatibilityRating.BROKEN: 1,
        }

        min_rating_value = rating_order.get(min_rating, 0) if min_rating else 0

        for app in self._apps.values():
            # Text search
            if query:
                searchable = f"{app.name} {app.description} {' '.join(app.tags)}".lower()
                if query_lower not in searchable:
                    continue

            # Category filter
            if category and app.category != category:
                continue

            # Layer filter
            if layer and app.layer != layer:
                continue

            # Rating filter
            if min_rating_value > 0:
                app_rating_value = rating_order.get(app.rating, 0)
                if app_rating_value < min_rating_value:
                    continue

            results.append(app)

        return results

    def by_category(self, category: AppCategory) -> List[AppInfo]:
        """Get all apps in a category."""
        return [app for app in self._apps.values() if app.category == category]

    def by_layer(self, layer: CompatibilityLayer) -> List[AppInfo]:
        """Get all apps using a specific compatibility layer."""
        return [app for app in self._apps.values() if app.layer == layer]

    def native_apps(self) -> List[AppInfo]:
        """Get all native Linux apps."""
        return self.by_layer(CompatibilityLayer.NATIVE)

    def wine_apps(self) -> List[AppInfo]:
        """Get all Wine-compatible apps."""
        return [
            app for app in self._apps.values()
            if app.layer in (CompatibilityLayer.WINE, CompatibilityLayer.PROTON)
        ]

    def vm_required_apps(self) -> List[AppInfo]:
        """Get apps that require a VM."""
        return [
            app for app in self._apps.values()
            if app.layer in (CompatibilityLayer.VM_WINDOWS, CompatibilityLayer.VM_MACOS)
        ]
