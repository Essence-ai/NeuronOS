"""
Integration tests for file migration.
"""

import pytest
from pathlib import Path


@pytest.mark.integration
class TestMigration:
    """Integration tests for file migration."""

    def test_migrate_documents(self, tmp_path: Path):
        """Test document migration from mock Windows to Linux."""
        from migration.migrator import create_migrator, MigrationSource, MigrationTarget, FileCategory

        # Set up source (simulating Windows user folder)
        source_home = tmp_path / "windows_user"
        (source_home / "Documents").mkdir(parents=True)
        (source_home / "Documents/report.docx").write_text("document content")
        (source_home / "Documents/notes.txt").write_text("notes content")
        
        (source_home / "Pictures").mkdir(parents=True)
        (source_home / "Pictures/photo.jpg").write_bytes(b"\xff\xd8\xff\xe0")  # JPEG header

        # Set up target
        target_home = tmp_path / "linux_user"
        target_home.mkdir()

        source = MigrationSource(
            path=source_home,
            user="testuser",
            os_type="windows",
        )
        target = MigrationTarget(path=target_home)

        migrator = create_migrator(source, target, [FileCategory.DOCUMENTS, FileCategory.PICTURES])
        migrator.scan()

        assert migrator.progress.files_total >= 2

        migrator.migrate()

        # Verify files were migrated
        assert (target_home / "Documents/report.docx").exists()
        assert (target_home / "Documents/notes.txt").read_text() == "notes content"
        assert (target_home / "Pictures/photo.jpg").exists()

    def test_migrate_with_size_limit(self, tmp_path: Path):
        """Test migration respects size limits."""
        from migration.migrator import create_migrator, MigrationSource, MigrationTarget

        # Set up source with large file
        source_home = tmp_path / "source"
        (source_home / "Documents").mkdir(parents=True)
        
        # Create files of different sizes
        (source_home / "Documents/small.txt").write_text("small")
        (source_home / "Documents/large.bin").write_bytes(b"x" * 1024 * 1024)  # 1MB

        target_home = tmp_path / "target"
        target_home.mkdir()

        source = MigrationSource(path=source_home, user="test", os_type="windows")
        target = MigrationTarget(path=target_home)

        migrator = create_migrator(source, target)
        migrator.max_file_size = 500 * 1024  # 500KB limit
        
        migrator.scan()
        migrator.migrate()

        # Small file should be migrated
        assert (target_home / "Documents/small.txt").exists()
        # Large file should be skipped
        assert not (target_home / "Documents/large.bin").exists()

    def test_app_settings_migrator(self, tmp_path: Path):
        """Test application settings migration."""
        from migration.migrator import ApplicationSettingsMigrator

        source_home = tmp_path / "windows"
        target_home = tmp_path / "linux"
        
        source_home.mkdir()
        target_home.mkdir()

        # Create mock .gitconfig
        gitconfig = source_home / ".gitconfig"
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@example.com\n")

        # Create mock SSH keys
        ssh_dir = source_home / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_rsa").write_text("PRIVATE KEY")
        (ssh_dir / "id_rsa.pub").write_text("PUBLIC KEY")
        (ssh_dir / "config").write_text("Host github.com\n  User git\n")

        migrator = ApplicationSettingsMigrator()
        results = migrator.migrate_app_settings(source_home, target_home, ["git", "ssh"])

        assert results["git"] is True
        assert results["ssh"] is True

        # Verify files exist
        assert (target_home / ".gitconfig").exists()
        assert "[user]" in (target_home / ".gitconfig").read_text()
        
        assert (target_home / ".ssh/id_rsa").exists()
        assert (target_home / ".ssh/config").exists()


@pytest.mark.integration
class TestBrowserProfileMigration:
    """Integration tests for browser profile migration."""

    def test_chrome_profile_excludes_cache(self, tmp_path: Path):
        """Test Chrome profile migration excludes cache."""
        from migration.migrator import WindowsMigrator, MigrationSource, MigrationTarget

        # Set up mock Chrome profile
        source_home = tmp_path / "source"
        chrome_path = source_home / "AppData/Local/Google/Chrome/User Data/Default"
        chrome_path.mkdir(parents=True)

        # Files to migrate
        (chrome_path / "Bookmarks").write_text('{"bookmarks": []}')
        (chrome_path / "Preferences").write_text('{"prefs": {}}')
        (chrome_path / "History").write_text("history data")

        # Cache directories to exclude (these match BROWSER_CACHE_EXCLUDES)
        (chrome_path / "Cache").mkdir()
        (chrome_path / "Cache/data").write_bytes(b"cache data")
        (chrome_path / "GPUCache").mkdir()
        (chrome_path / "GPUCache/index").write_bytes(b"gpu cache")

        target_home = tmp_path / "target"
        target_home.mkdir()

        source = MigrationSource(path=source_home, user="test", os_type="windows")
        target = MigrationTarget(path=target_home)

        migrator = WindowsMigrator(source, target)
        
        # Migrate browser profile - note: migrating User Data, not User Data/Default
        _result = migrator._migrate_browser_profile(  # noqa: F841 - result verified by assertions
            chrome_path,  # Source is the Default profile folder
            target_home / ".config/google-chrome/Default",  # Target mirrors the structure
            exclude_caches=True,
        )

        # Check important files migrated (now checking correct path)
        assert (target_home / ".config/google-chrome/Default/Bookmarks").exists()
        
        # Check cache excluded (if cache dirs were created, they should be empty or not exist)
        cache_path = target_home / ".config/google-chrome/Default/Cache"
        # Cache directory should not exist at all since it was excluded
        assert not cache_path.exists()
