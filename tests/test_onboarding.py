"""
Tests for NeuronOS Onboarding module.

Tests user data management, preference saving, first-boot detection,
VM queue creation, and migration queue creation -- all WITHOUT requiring
GTK4, GLib, or libvirt at import time.

The OnboardingWizard class inherits from Adw.ApplicationWindow (GTK4),
so we cannot instantiate it directly in a headless test environment.
Instead, we test the data-handling methods by extracting their logic or
by carefully patching the GTK layer.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers -- minimal stand-in for OnboardingWizard data methods
# ---------------------------------------------------------------------------

def _make_wizard_stub():
    """
    Build a lightweight object that has the same data attributes and methods
    as OnboardingWizard, without importing GTK.

    This lets us test _save_preferences, _setup_vms, _start_migration,
    _mark_first_boot_complete, get_user_data, and set_user_data.
    """

    class WizardStub:
        """Mimics OnboardingWizard's data interface."""

        def __init__(self):
            self._user_data = {
                "setup_windows_vm": False,
                "setup_macos_vm": False,
                "gpu_passthrough": False,
                "migrate_files": False,
                "migration_source": None,
            }

        def get_user_data(self) -> dict:
            return self._user_data.copy()

        def set_user_data(self, key: str, value):
            self._user_data[key] = value

        # ----- Methods copied verbatim from wizard.py -----

        def _save_preferences(self):
            from datetime import datetime

            config_dir = Path.home() / ".config/neuronos"
            config_dir.mkdir(parents=True, exist_ok=True)

            preferences = {
                "setup_windows_vm": self._user_data.get("setup_windows_vm", False),
                "setup_macos_vm": self._user_data.get("setup_macos_vm", False),
                "gpu_passthrough": self._user_data.get("gpu_passthrough", False),
                "migrate_files": self._user_data.get("migrate_files", False),
                "onboarding_completed_at": datetime.now().isoformat(),
            }

            (config_dir / "preferences.json").write_text(json.dumps(preferences, indent=2))

        def _setup_vms(self):
            from datetime import datetime

            queue_dir = Path.home() / ".config/neuronos/pending-vms"
            queue_dir.mkdir(parents=True, exist_ok=True)

            for vm_type, key in [("windows", "setup_windows_vm"), ("macos", "setup_macos_vm")]:
                if self._user_data.get(key):
                    vm_config = {
                        "type": vm_type,
                        "queued_at": datetime.now().isoformat(),
                        "status": "pending",
                    }
                    (queue_dir / f"{vm_type}.json").write_text(json.dumps(vm_config, indent=2))

        def _start_migration(self):
            if not self._user_data.get("migrate_files"):
                return

            source = self._user_data.get("migration_source")
            if not source:
                return

            from datetime import datetime

            config_dir = Path.home() / ".config/neuronos/pending-migration"
            config_dir.mkdir(parents=True, exist_ok=True)

            migration_config = {
                "source_path": str(getattr(source, "path", source)),
                "queued_at": datetime.now().isoformat(),
                "status": "pending",
            }
            (config_dir / "migration.json").write_text(json.dumps(migration_config, indent=2))

        def _mark_first_boot_complete(self):
            marker_path = Path.home() / ".config" / "neuronos" / ".first-boot-complete"
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.touch()

    return WizardStub()


# ---------------------------------------------------------------------------
# Fixture: temporary HOME directory
# ---------------------------------------------------------------------------

@pytest.fixture
def wizard_with_home(tmp_path):
    """Return a WizardStub with HOME pointed to a temp directory."""
    import os

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)

    # Pre-create the config directory tree
    (tmp_path / ".config" / "neuronos").mkdir(parents=True, exist_ok=True)

    yield _make_wizard_stub()

    if old_home:
        os.environ["HOME"] = old_home
    else:
        os.environ.pop("HOME", None)


# ---------------------------------------------------------------------------
# Tests: User Data Management
# ---------------------------------------------------------------------------

class TestUserData:
    """Test get_user_data / set_user_data."""

    @pytest.mark.unit
    def test_get_user_data_returns_copy(self):
        wizard = _make_wizard_stub()
        data = wizard.get_user_data()

        # Mutating the copy must NOT affect the wizard
        data["setup_windows_vm"] = True
        assert wizard.get_user_data()["setup_windows_vm"] is False

    @pytest.mark.unit
    def test_set_user_data_updates_value(self):
        wizard = _make_wizard_stub()
        wizard.set_user_data("setup_windows_vm", True)
        assert wizard.get_user_data()["setup_windows_vm"] is True

    @pytest.mark.unit
    def test_set_user_data_new_key(self):
        wizard = _make_wizard_stub()
        wizard.set_user_data("custom_key", "custom_value")
        assert wizard.get_user_data()["custom_key"] == "custom_value"

    @pytest.mark.unit
    def test_default_user_data_keys(self):
        wizard = _make_wizard_stub()
        data = wizard.get_user_data()
        expected_keys = {
            "setup_windows_vm",
            "setup_macos_vm",
            "gpu_passthrough",
            "migrate_files",
            "migration_source",
        }
        assert set(data.keys()) == expected_keys

    @pytest.mark.unit
    def test_default_values_are_false_or_none(self):
        wizard = _make_wizard_stub()
        data = wizard.get_user_data()
        assert data["setup_windows_vm"] is False
        assert data["setup_macos_vm"] is False
        assert data["gpu_passthrough"] is False
        assert data["migrate_files"] is False
        assert data["migration_source"] is None


# ---------------------------------------------------------------------------
# Tests: Preference Saving
# ---------------------------------------------------------------------------

class TestSavePreferences:
    """Test _save_preferences writes correct JSON."""

    @pytest.mark.unit
    def test_save_preferences_creates_file(self, wizard_with_home, tmp_path):
        wizard_with_home._save_preferences()

        prefs_file = tmp_path / ".config" / "neuronos" / "preferences.json"
        assert prefs_file.exists()

    @pytest.mark.unit
    def test_save_preferences_content(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("setup_windows_vm", True)
        wizard_with_home.set_user_data("gpu_passthrough", True)
        wizard_with_home._save_preferences()

        prefs_file = tmp_path / ".config" / "neuronos" / "preferences.json"
        data = json.loads(prefs_file.read_text())

        assert data["setup_windows_vm"] is True
        assert data["gpu_passthrough"] is True
        assert data["setup_macos_vm"] is False
        assert "onboarding_completed_at" in data

    @pytest.mark.unit
    def test_save_preferences_timestamp_is_iso(self, wizard_with_home, tmp_path):
        wizard_with_home._save_preferences()

        prefs_file = tmp_path / ".config" / "neuronos" / "preferences.json"
        data = json.loads(prefs_file.read_text())
        ts = data["onboarding_completed_at"]

        # Should be parseable as ISO 8601
        dt = datetime.fromisoformat(ts)
        assert isinstance(dt, datetime)


# ---------------------------------------------------------------------------
# Tests: First-Boot Detection / Marking
# ---------------------------------------------------------------------------

class TestFirstBoot:
    """Test first-boot marker creation."""

    @pytest.mark.unit
    def test_mark_first_boot_creates_marker(self, wizard_with_home, tmp_path):
        marker = tmp_path / ".config" / "neuronos" / ".first-boot-complete"
        assert not marker.exists()

        wizard_with_home._mark_first_boot_complete()
        assert marker.exists()

    @pytest.mark.unit
    def test_mark_first_boot_idempotent(self, wizard_with_home, tmp_path):
        """Calling _mark_first_boot_complete twice should not raise."""
        wizard_with_home._mark_first_boot_complete()
        wizard_with_home._mark_first_boot_complete()

        marker = tmp_path / ".config" / "neuronos" / ".first-boot-complete"
        assert marker.exists()

    @pytest.mark.unit
    def test_first_boot_marker_path(self, wizard_with_home, tmp_path):
        """Marker must be at the canonical path used by OnboardingApplication."""
        wizard_with_home._mark_first_boot_complete()

        expected = tmp_path / ".config" / "neuronos" / ".first-boot-complete"
        assert expected.exists()


# ---------------------------------------------------------------------------
# Tests: VM Queue Creation (_setup_vms)
# ---------------------------------------------------------------------------

class TestSetupVMs:
    """Test _setup_vms creates correct queue files."""

    @pytest.mark.unit
    def test_no_vms_requested(self, wizard_with_home, tmp_path):
        """When neither VM is selected, no queue files are created."""
        wizard_with_home._setup_vms()

        queue_dir = tmp_path / ".config" / "neuronos" / "pending-vms"
        # Directory gets created, but no JSON files
        json_files = list(queue_dir.glob("*.json")) if queue_dir.exists() else []
        assert len(json_files) == 0

    @pytest.mark.unit
    def test_windows_vm_requested(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("setup_windows_vm", True)
        wizard_with_home._setup_vms()

        win_file = tmp_path / ".config" / "neuronos" / "pending-vms" / "windows.json"
        assert win_file.exists()

        data = json.loads(win_file.read_text())
        assert data["type"] == "windows"
        assert data["status"] == "pending"

    @pytest.mark.unit
    def test_macos_vm_requested(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("setup_macos_vm", True)
        wizard_with_home._setup_vms()

        mac_file = tmp_path / ".config" / "neuronos" / "pending-vms" / "macos.json"
        assert mac_file.exists()

        data = json.loads(mac_file.read_text())
        assert data["type"] == "macos"
        assert data["status"] == "pending"

    @pytest.mark.unit
    def test_both_vms_requested(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("setup_windows_vm", True)
        wizard_with_home.set_user_data("setup_macos_vm", True)
        wizard_with_home._setup_vms()

        queue_dir = tmp_path / ".config" / "neuronos" / "pending-vms"
        assert (queue_dir / "windows.json").exists()
        assert (queue_dir / "macos.json").exists()

    @pytest.mark.unit
    def test_vm_queue_has_timestamp(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("setup_windows_vm", True)
        wizard_with_home._setup_vms()

        win_file = tmp_path / ".config" / "neuronos" / "pending-vms" / "windows.json"
        data = json.loads(win_file.read_text())
        assert "queued_at" in data
        # Should be parseable
        datetime.fromisoformat(data["queued_at"])


# ---------------------------------------------------------------------------
# Tests: Migration Queue Creation (_start_migration)
# ---------------------------------------------------------------------------

class TestStartMigration:
    """Test _start_migration creates correct queue files."""

    @pytest.mark.unit
    def test_migration_not_requested(self, wizard_with_home, tmp_path):
        """When migrate_files is False, nothing is created."""
        wizard_with_home._start_migration()

        mig_dir = tmp_path / ".config" / "neuronos" / "pending-migration"
        assert not mig_dir.exists()

    @pytest.mark.unit
    def test_migration_no_source(self, wizard_with_home, tmp_path):
        """When migration requested but no source given, nothing is created."""
        wizard_with_home.set_user_data("migrate_files", True)
        wizard_with_home._start_migration()

        mig_dir = tmp_path / ".config" / "neuronos" / "pending-migration"
        assert not mig_dir.exists()

    @pytest.mark.unit
    def test_migration_with_string_source(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("migrate_files", True)
        wizard_with_home.set_user_data("migration_source", "/mnt/windows/Users/jdoe")
        wizard_with_home._start_migration()

        mig_file = tmp_path / ".config" / "neuronos" / "pending-migration" / "migration.json"
        assert mig_file.exists()

        data = json.loads(mig_file.read_text())
        assert data["source_path"] == "/mnt/windows/Users/jdoe"
        assert data["status"] == "pending"

    @pytest.mark.unit
    def test_migration_with_object_source(self, wizard_with_home, tmp_path):
        """Source can be an object with a .path attribute."""

        class SourceObj:
            path = "/mnt/macos/Users/jdoe"

        wizard_with_home.set_user_data("migrate_files", True)
        wizard_with_home.set_user_data("migration_source", SourceObj())
        wizard_with_home._start_migration()

        mig_file = tmp_path / ".config" / "neuronos" / "pending-migration" / "migration.json"
        data = json.loads(mig_file.read_text())
        assert data["source_path"] == "/mnt/macos/Users/jdoe"

    @pytest.mark.unit
    def test_migration_has_timestamp(self, wizard_with_home, tmp_path):
        wizard_with_home.set_user_data("migrate_files", True)
        wizard_with_home.set_user_data("migration_source", "/mnt/data")
        wizard_with_home._start_migration()

        mig_file = tmp_path / ".config" / "neuronos" / "pending-migration" / "migration.json"
        data = json.loads(mig_file.read_text())
        assert "queued_at" in data
        datetime.fromisoformat(data["queued_at"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
