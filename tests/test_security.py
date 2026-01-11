import pytest
import sys
import hashlib
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from store.installer import _safe_filename, _ensure_within_directory, _verify_download
from vm_manager.gui.app import _validate_vm_name
from utils.atomic_write import atomic_write_text, atomic_write_json
from migration.migrator import Migrator, FileCategory
from unittest.mock import MagicMock, patch

def test_safe_filename_protection():
    """Verify SEC-002: _safe_filename prevents path traversal."""
    # Traversal attempts
    assert _safe_filename("http://example.com/../../etc/passwd") == "passwd"
    assert "cmd.exe" in _safe_filename("http://example.com/C:\\Windows\\System32\\cmd.exe")
    assert _safe_filename("http://example.com/../../../foo.exe") == "foo.exe"
    
    # Empty or dots only
    assert _safe_filename("http://example.com/..") == "download"
    assert _safe_filename("http://example.com/") == "download"
    
    # Normal usage
    assert _safe_filename("http://example.com/installer.msi") == "installer.msi"
    assert _safe_filename("https://github.com/user/repo/releases/download/v1/app.exe") == "app.exe"

def test_ensure_within_directory(tmp_path):
    """Verify SEC-002: _ensure_within_directory prevents breakout."""
    base = tmp_path / "downloads"
    base.mkdir()
    
    # Safe paths
    safe_file = base / "file.exe"
    assert _ensure_within_directory(base, safe_file) == safe_file
    
    subdir_file = base / "subdir" / "file.exe"
    assert _ensure_within_directory(base, subdir_file) == subdir_file
    
    # Unsafe paths
    # Outside base
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    unsafe_file = other_dir / "secret.txt"
    with pytest.raises(ValueError, match="Path traversal detected"):
        _ensure_within_directory(base, unsafe_file)
    
    # Traversal breakout
    traversal_file = base / ".." / "other" / "secret.txt"
    with pytest.raises(ValueError, match="Path traversal detected"):
        _ensure_within_directory(base, traversal_file)

def test_vm_name_validation():
    """Verify SEC-001: VM name validation."""
    # Valid names
    assert _validate_vm_name("Windows11") is True
    assert _validate_vm_name("gaming-vm") is True
    assert _validate_vm_name("my.vm.123") is True
    
    # Invalid names (injection attempts)
    assert _validate_vm_name("vm; rm -rf /") is False
    assert _validate_vm_name("vm & calc.exe") is False
    assert _validate_vm_name("$(id)") is False
    assert _validate_vm_name("`ls`") is False
    
    # Invalid formats
    assert _validate_vm_name("-start-with-dash") is False
    assert _validate_vm_name("too_" + "long_" * 20) is False
    assert _validate_vm_name("") is False

def test_verify_download(tmp_path):
    """Verify SEC-003: SHA256 download verification."""
    test_file = tmp_path / "test.exe"
    content = b"fake-installer-content"
    test_file.write_bytes(content)
    
    expected_hash = hashlib.sha256(content).hexdigest()
    
    # Correct hash
    assert _verify_download(test_file, expected_hash) is True
    # Incorrect hash
    assert _verify_download(test_file, "wrong-hash") is False
    # No hash (allowed for now)
    assert _verify_download(test_file, None) is True

def test_atomic_write(tmp_path):
    """Verify DATA-002: Atomic write utility."""
    test_file = tmp_path / "config.json"
    data = {"version": 1, "settings": "active"}
    
    # Write JSON
    atomic_write_json(test_file, data)
    assert test_file.exists()
    assert json.loads(test_file.read_text()) == data
    
    # Update text
    atomic_write_text(test_file, "plain text")
    assert test_file.read_text() == "plain text"
    
    # Verify temp file cleanup
    assert len(list(tmp_path.glob("*.tmp"))) == 0

def test_migration_logic(tmp_path):
    """Verify DATA-001: File vs Directory handling in migration."""
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    
    # 1. Setup a directory source (e.g., .ssh)
    ssh_dir = source_root / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_rsa").write_text("private-key")
    
    # 2. Setup a file source (e.g., .gitconfig) - The bug-triggering case
    gitconfig = source_root / ".gitconfig"
    gitconfig.write_text("[user]\nname=Neuron")
    
    migrator = Migrator(source_root, target_root)
    # Mock categories to only test these two
    migrator.categories = [FileCategory.SSH_KEYS, FileCategory.GIT_CONFIG] 
    
    # We need to mock _get_source_path and _get_target_path because they rely on fixed logic
    with patch.object(migrator, '_get_source_path') as m_src, \
         patch.object(migrator, '_get_target_path') as m_tgt:
        
        m_src.side_effect = [ssh_dir, gitconfig]
        m_tgt.side_effect = [target_root / ".ssh", target_root / ".gitconfig"]
        
        success = migrator.migrate()
        
        assert success is True
        # Verify directory migrated
        assert (target_root / ".ssh" / "id_rsa").exists()
        # Verify single file migrated correctly (SEC-001 fix)
        assert (target_root / ".gitconfig").exists()
        assert (target_root / ".gitconfig").read_text() == "[user]\nname=Neuron"
