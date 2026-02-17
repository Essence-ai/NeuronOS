"""
Tests for NeuronOS Updater module.

Covers UpdateVerifier, UpdateInfo/PackageUpdate dataclasses, UpdateStatus
and SnapshotType enums, Snapshot dataclass, UpdateManager init, and
RollbackManager._linux_to_grub_device() conversions.

All subprocess and system calls are mocked -- no real system commands run.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Tests: UpdateVerifier.CRITICAL_SERVICES
# ---------------------------------------------------------------------------

class TestUpdateVerifierConstants:
    """Verify important constants in UpdateVerifier."""

    @pytest.mark.unit
    def test_critical_services_contains_gdm(self):
        """GDM must be in CRITICAL_SERVICES (NeuronOS uses GNOME, not SDDM)."""
        from updater.verifier import UpdateVerifier
        assert "gdm" in UpdateVerifier.CRITICAL_SERVICES

    @pytest.mark.unit
    def test_critical_services_does_not_contain_sddm(self):
        """SDDM should NOT be in CRITICAL_SERVICES (project uses GNOME/GDM)."""
        from updater.verifier import UpdateVerifier
        for svc in UpdateVerifier.CRITICAL_SERVICES:
            assert "sddm" not in svc.lower()

    @pytest.mark.unit
    def test_critical_services_contains_network_manager(self):
        from updater.verifier import UpdateVerifier
        assert "NetworkManager" in UpdateVerifier.CRITICAL_SERVICES

    @pytest.mark.unit
    def test_critical_services_contains_libvirtd(self):
        from updater.verifier import UpdateVerifier
        assert "libvirtd" in UpdateVerifier.CRITICAL_SERVICES

    @pytest.mark.unit
    def test_critical_binaries_list(self):
        from updater.verifier import UpdateVerifier
        assert "/usr/bin/bash" in UpdateVerifier.CRITICAL_BINARIES
        assert "/usr/bin/python3" in UpdateVerifier.CRITICAL_BINARIES
        assert "/usr/bin/systemctl" in UpdateVerifier.CRITICAL_BINARIES


# ---------------------------------------------------------------------------
# Tests: UpdateVerifier._check_binaries
# ---------------------------------------------------------------------------

class TestUpdateVerifierCheckBinaries:
    """Test _check_binaries with mocked filesystem."""

    @pytest.mark.unit
    def test_check_binaries_all_present(self):
        from updater.verifier import UpdateVerifier

        verifier = UpdateVerifier()
        # All binaries "exist"
        with patch.object(Path, "exists", return_value=True):
            verifier._check_binaries()

        assert len(verifier._issues) == 0

    @pytest.mark.unit
    def test_check_binaries_missing_binary(self):
        from updater.verifier import UpdateVerifier

        verifier = UpdateVerifier()
        # All binaries "missing"
        with patch.object(Path, "exists", return_value=False):
            verifier._check_binaries()

        assert len(verifier._issues) == len(UpdateVerifier.CRITICAL_BINARIES)
        for issue in verifier._issues:
            assert "Missing critical binary" in issue


# ---------------------------------------------------------------------------
# Tests: UpdateVerifier._check_services
# ---------------------------------------------------------------------------

class TestUpdateVerifierCheckServices:
    """Test _check_services with mocked subprocess."""

    @pytest.mark.unit
    def test_check_services_all_active(self):
        from updater.verifier import UpdateVerifier

        verifier = UpdateVerifier()
        mock_result = MagicMock(returncode=0, stdout="active\n")
        with patch("subprocess.run", return_value=mock_result):
            verifier._check_services()

        assert len(verifier._issues) == 0

    @pytest.mark.unit
    def test_check_services_one_failed(self):
        from updater.verifier import UpdateVerifier

        verifier = UpdateVerifier()

        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[-1] == "gdm":
                result.returncode = 3
                result.stdout = "failed\n"
            else:
                result.returncode = 0
                result.stdout = "active\n"
            return result

        with patch("subprocess.run", side_effect=side_effect):
            verifier._check_services()

        assert len(verifier._issues) == 1
        assert "gdm" in verifier._issues[0]

    @pytest.mark.unit
    def test_check_services_inactive_not_treated_as_failure(self):
        """An 'inactive' service is not the same as 'failed'."""
        from updater.verifier import UpdateVerifier

        verifier = UpdateVerifier()
        mock_result = MagicMock(returncode=3, stdout="inactive\n")
        with patch("subprocess.run", return_value=mock_result):
            verifier._check_services()

        # "inactive" should not produce issues (it is just stopped)
        assert len(verifier._issues) == 0


# ---------------------------------------------------------------------------
# Tests: PackageUpdate dataclass
# ---------------------------------------------------------------------------

class TestPackageUpdate:
    """Test the PackageUpdate dataclass."""

    @pytest.mark.unit
    def test_basic_creation(self):
        from updater.updater import PackageUpdate

        pkg = PackageUpdate(
            name="linux",
            old_version="6.6.1",
            new_version="6.6.2",
            size_bytes=52428800,
            is_security=True,
        )
        assert pkg.name == "linux"
        assert pkg.is_security is True

    @pytest.mark.unit
    def test_size_str_megabytes(self):
        from updater.updater import PackageUpdate

        pkg = PackageUpdate(name="pkg", old_version="1", new_version="2", size_bytes=5242880)
        assert "MB" in pkg.size_str

    @pytest.mark.unit
    def test_size_str_kilobytes(self):
        from updater.updater import PackageUpdate

        pkg = PackageUpdate(name="pkg", old_version="1", new_version="2", size_bytes=5120)
        assert "KB" in pkg.size_str

    @pytest.mark.unit
    def test_size_str_bytes(self):
        from updater.updater import PackageUpdate

        pkg = PackageUpdate(name="pkg", old_version="1", new_version="2", size_bytes=512)
        assert "B" in pkg.size_str

    @pytest.mark.unit
    def test_defaults(self):
        from updater.updater import PackageUpdate

        pkg = PackageUpdate(name="pkg", old_version="1", new_version="2")
        assert pkg.size_bytes == 0
        assert pkg.is_security is False


# ---------------------------------------------------------------------------
# Tests: UpdateInfo dataclass
# ---------------------------------------------------------------------------

class TestUpdateInfo:
    """Test the UpdateInfo dataclass."""

    @pytest.mark.unit
    def test_empty_update_info(self):
        from updater.updater import UpdateInfo

        info = UpdateInfo()
        assert info.package_count == 0
        assert info.total_download_size == 0
        assert info.has_security_updates is False

    @pytest.mark.unit
    def test_package_count(self):
        from updater.updater import UpdateInfo, PackageUpdate

        pkgs = [
            PackageUpdate(name="a", old_version="1", new_version="2"),
            PackageUpdate(name="b", old_version="1", new_version="2"),
        ]
        info = UpdateInfo(packages=pkgs)
        assert info.package_count == 2

    @pytest.mark.unit
    def test_download_size_str_megabytes(self):
        from updater.updater import UpdateInfo

        info = UpdateInfo(total_download_size=10 * 1024 * 1024)
        assert "MB" in info.download_size_str

    @pytest.mark.unit
    def test_download_size_str_gigabytes(self):
        from updater.updater import UpdateInfo

        info = UpdateInfo(total_download_size=2 * 1024 * 1024 * 1024)
        assert "GB" in info.download_size_str


# ---------------------------------------------------------------------------
# Tests: UpdateStatus enum
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    """Test UpdateStatus enum values."""

    @pytest.mark.unit
    def test_all_expected_values_exist(self):
        from updater.updater import UpdateStatus

        expected = [
            "idle", "checking", "downloading", "creating_snapshot",
            "installing", "verifying", "complete", "failed", "rollback_needed",
        ]
        actual = [s.value for s in UpdateStatus]
        for val in expected:
            assert val in actual, f"Missing UpdateStatus value: {val}"

    @pytest.mark.unit
    def test_enum_member_access(self):
        from updater.updater import UpdateStatus

        assert UpdateStatus.IDLE.value == "idle"
        assert UpdateStatus.FAILED.value == "failed"
        assert UpdateStatus.ROLLBACK_NEEDED.value == "rollback_needed"


# ---------------------------------------------------------------------------
# Tests: SnapshotType enum
# ---------------------------------------------------------------------------

class TestSnapshotType:
    """Test SnapshotType enum values."""

    @pytest.mark.unit
    def test_all_expected_values_exist(self):
        from updater.snapshot import SnapshotType

        expected = [
            "ondemand", "boot", "hourly", "daily",
            "weekly", "monthly", "pre_update",
        ]
        actual = [s.value for s in SnapshotType]
        for val in expected:
            assert val in actual, f"Missing SnapshotType value: {val}"

    @pytest.mark.unit
    def test_pre_update_type(self):
        from updater.snapshot import SnapshotType

        assert SnapshotType.PRE_UPDATE.value == "pre_update"


# ---------------------------------------------------------------------------
# Tests: Snapshot dataclass
# ---------------------------------------------------------------------------

class TestSnapshot:
    """Test Snapshot dataclass and its properties."""

    @pytest.mark.unit
    def test_basic_creation(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="2025-12-29_10-30-45",
            timestamp=datetime(2025, 12, 29, 10, 30, 45),
            snapshot_type=SnapshotType.PRE_UPDATE,
            description="Pre-update snapshot",
        )
        assert snap.name == "2025-12-29_10-30-45"
        assert snap.snapshot_type == SnapshotType.PRE_UPDATE

    @pytest.mark.unit
    def test_age_str_days(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="old",
            timestamp=datetime.now() - timedelta(days=5),
            snapshot_type=SnapshotType.DAILY,
        )
        assert "5 days ago" in snap.age_str

    @pytest.mark.unit
    def test_age_str_just_now(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="recent",
            timestamp=datetime.now() - timedelta(seconds=10),
            snapshot_type=SnapshotType.ONDEMAND,
        )
        assert snap.age_str == "Just now"

    @pytest.mark.unit
    def test_size_str_megabytes(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="s", timestamp=datetime.now(),
            snapshot_type=SnapshotType.ONDEMAND, size_mb=500,
        )
        assert snap.size_str == "500 MB"

    @pytest.mark.unit
    def test_size_str_gigabytes(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="s", timestamp=datetime.now(),
            snapshot_type=SnapshotType.ONDEMAND, size_mb=2048,
        )
        assert "GB" in snap.size_str

    @pytest.mark.unit
    def test_default_fields(self):
        from updater.snapshot import Snapshot, SnapshotType

        snap = Snapshot(
            name="s", timestamp=datetime.now(),
            snapshot_type=SnapshotType.ONDEMAND,
        )
        assert snap.description == ""
        assert snap.tags == []
        assert snap.size_mb == 0
        assert snap.path is None


# ---------------------------------------------------------------------------
# Tests: UpdateManager initialization
# ---------------------------------------------------------------------------

class TestUpdateManager:
    """Test UpdateManager init and initial state."""

    @pytest.mark.unit
    def test_init_sets_idle_status(self):
        from updater.updater import UpdateManager, UpdateStatus

        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            manager = UpdateManager()

        assert manager.status == UpdateStatus.IDLE
        assert manager.current_info is None
        assert manager.pre_update_snapshot is None

    @pytest.mark.unit
    def test_init_creates_snapshot_manager(self):
        from updater.updater import UpdateManager

        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            manager = UpdateManager()

        assert manager.snapshot_manager is not None


# ---------------------------------------------------------------------------
# Tests: _linux_to_grub_device conversions
# ---------------------------------------------------------------------------

class TestLinuxToGrubDevice:
    """Test the _linux_to_grub_device() conversion function in rollback.py."""

    @pytest.mark.unit
    def test_sda1(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/sda1")
        assert result == "hd0,gpt1"

    @pytest.mark.unit
    def test_sda2(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/sda2")
        assert result == "hd0,gpt2"

    @pytest.mark.unit
    def test_sdb1(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/sdb1")
        assert result == "hd1,gpt1"

    @pytest.mark.unit
    def test_nvme0n1p2(self):
        """nvme0n1p2: hdnum = 0*10 + 1 = 1, partition 2 -> hd1,gpt2."""
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/nvme0n1p2")
        assert result == "hd1,gpt2"

    @pytest.mark.unit
    def test_nvme0n1p1(self):
        """nvme0n1p1: hdnum = 0*10 + 1 = 1, partition 1 -> hd1,gpt1."""
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/nvme0n1p1")
        assert result == "hd1,gpt1"

    @pytest.mark.unit
    def test_nvme0n0p2(self):
        """nvme0n0p2: hdnum = 0*10 + 0 = 0, partition 2 -> hd0,gpt2."""
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/nvme0n0p2")
        assert result == "hd0,gpt2"

    @pytest.mark.unit
    def test_vda2(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/vda2")
        assert result == "hd0,gpt2"

    @pytest.mark.unit
    def test_vda3(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/vda3")
        assert result == "hd0,gpt3"

    @pytest.mark.unit
    def test_unknown_device_returns_none(self):
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/loop0")
        assert result is None

    @pytest.mark.unit
    def test_sdc5(self):
        """Third disk, fifth partition."""
        from updater.rollback import _linux_to_grub_device

        result = _linux_to_grub_device("/dev/sdc5")
        assert result == "hd2,gpt5"


# ---------------------------------------------------------------------------
# Tests: RollbackManager
# ---------------------------------------------------------------------------

class TestRollbackManager:
    """Test RollbackManager initialization."""

    @pytest.mark.unit
    def test_init(self):
        from updater.rollback import RollbackManager, RollbackStatus

        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            manager = RollbackManager()

        assert manager.status == RollbackStatus.IDLE
        assert manager.snapshot_manager is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
