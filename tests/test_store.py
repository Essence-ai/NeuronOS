"""
Tests for NeuronOS Store - App Catalog
"""

import pytest
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from store.app_catalog import (
    AppCatalog, AppInfo, AppCategory,
    CompatibilityLayer, CompatibilityRating,
)


class TestAppInfo:
    """Tests for AppInfo dataclass."""

    def test_basic_creation(self):
        """Test creating basic app info."""
        app = AppInfo(
            id="firefox",
            name="Firefox",
            description="Web browser",
            category=AppCategory.PRODUCTIVITY,
            layer=CompatibilityLayer.NATIVE,
            rating=CompatibilityRating.PERFECT,
        )

        assert app.id == "firefox"
        assert app.layer == CompatibilityLayer.NATIVE
        assert app.requires_gpu_passthrough is False

    def test_to_dict(self):
        """Test serialization to dict."""
        app = AppInfo(
            id="test",
            name="Test App",
            description="A test",
            category=AppCategory.UTILITIES,
            layer=CompatibilityLayer.NATIVE,
            rating=CompatibilityRating.GOOD,
            tags=["test", "example"],
        )
        data = app.to_dict()

        assert data["id"] == "test"
        assert data["layer"] == "native"
        assert data["tags"] == ["test", "example"]

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "id": "photoshop",
            "name": "Photoshop",
            "description": "Image editor",
            "category": "creative",
            "layer": "vm_windows",
            "rating": "perfect",
            "requires_gpu_passthrough": True,
        }
        app = AppInfo.from_dict(data)

        assert app.id == "photoshop"
        assert app.layer == CompatibilityLayer.VM_WINDOWS
        assert app.requires_gpu_passthrough is True


class TestAppCatalog:
    """Tests for AppCatalog."""

    @pytest.fixture
    def sample_catalog(self, tmp_path):
        """Create a sample catalog file."""
        catalog_path = tmp_path / "apps.json"
        data = {
            "version": "1.0",
            "apps": [
                {
                    "id": "firefox",
                    "name": "Firefox",
                    "description": "Browser",
                    "category": "productivity",
                    "layer": "native",
                    "rating": "perfect",
                    "tags": ["browser", "web"],
                },
                {
                    "id": "photoshop",
                    "name": "Photoshop",
                    "description": "Image editor",
                    "category": "creative",
                    "layer": "vm_windows",
                    "rating": "perfect",
                    "requires_gpu_passthrough": True,
                },
                {
                    "id": "steam",
                    "name": "Steam",
                    "description": "Gaming platform",
                    "category": "gaming",
                    "layer": "native",
                    "rating": "perfect",
                },
            ],
        }
        catalog_path.write_text(json.dumps(data))
        return catalog_path

    def test_load_catalog(self, sample_catalog):
        """Test loading catalog from file."""
        catalog = AppCatalog(sample_catalog)
        assert catalog.load() is True
        assert len(catalog.all()) == 3

    def test_get_app(self, sample_catalog):
        """Test getting app by ID."""
        catalog = AppCatalog(sample_catalog)
        catalog.load()

        app = catalog.get("firefox")
        assert app is not None
        assert app.name == "Firefox"

    def test_search_by_text(self, sample_catalog):
        """Test text search."""
        catalog = AppCatalog(sample_catalog)
        catalog.load()

        results = catalog.search("browser")
        assert len(results) == 1
        assert results[0].id == "firefox"

    def test_search_by_category(self, sample_catalog):
        """Test category filter."""
        catalog = AppCatalog(sample_catalog)
        catalog.load()

        results = catalog.search(category=AppCategory.CREATIVE)
        assert len(results) == 1
        assert results[0].id == "photoshop"

    def test_search_by_layer(self, sample_catalog):
        """Test layer filter."""
        catalog = AppCatalog(sample_catalog)
        catalog.load()

        results = catalog.by_layer(CompatibilityLayer.NATIVE)
        assert len(results) == 2

    def test_vm_required_apps(self, sample_catalog):
        """Test getting VM-required apps."""
        catalog = AppCatalog(sample_catalog)
        catalog.load()

        results = catalog.vm_required_apps()
        assert len(results) == 1
        assert results[0].id == "photoshop"

    def test_add_app(self, tmp_path):
        """Test adding app to catalog."""
        catalog_path = tmp_path / "new_apps.json"
        catalog = AppCatalog(catalog_path)

        app = AppInfo(
            id="new_app",
            name="New App",
            description="Test",
            category=AppCategory.UTILITIES,
            layer=CompatibilityLayer.NATIVE,
            rating=CompatibilityRating.GOOD,
        )
        catalog.add(app)

        assert catalog.get("new_app") is not None

    def test_save_catalog(self, tmp_path):
        """Test saving catalog."""
        catalog_path = tmp_path / "saved_apps.json"
        catalog = AppCatalog(catalog_path)

        catalog.add(AppInfo(
            id="test",
            name="Test",
            description="Test app",
            category=AppCategory.UTILITIES,
            layer=CompatibilityLayer.NATIVE,
            rating=CompatibilityRating.GOOD,
        ))

        assert catalog.save() is True
        assert catalog_path.exists()

        # Reload and verify
        catalog2 = AppCatalog(catalog_path)
        catalog2.load()
        assert catalog2.get("test") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
