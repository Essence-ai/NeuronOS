# Phase 4.2: Security Audit & Hardening

**Status**: 🟡 PARTIAL - Guest agent encrypted (Phase 1.5), other areas need review
**Estimated Time**: 2-3 days
**Prerequisites**: All Phases 1-3 complete

---

## What is a Security Audit?

A security audit identifies vulnerabilities that attackers could exploit. NeuronOS handles:
- **Privileged operations** (VM creation, VFIO binding)
- **User data** (file migration, credentials)
- **System configuration** (kernel parameters, services)
- **Guest communication** (Windows VM ↔ Linux host)

**Without audit**: Security vulnerabilities go unnoticed until exploited.
**With audit**: Proactive identification and mitigation of risks.

---

## Current State

### What Works ✅
- ✅ Guest agent encryption (Phase 1.5) - AES-256 for VM communication
- ✅ Basic file validation in migration

### What Needs Review ❌

| Area | Risk | Example Vulnerability |
|---|---|---|
| **Privilege Escalation** | High | sudo without password for VFIO binding |
| **Input Validation** | High | VM name "../../../etc/passwd" |
| **Path Traversal** | High | Migration reads /etc/shadow |
| **Command Injection** | Critical | VM name "test; rm -rf /" |
| **Race Conditions** | Medium | Temp files readable by other users |
| **Cryptography** | High | Keys stored in plaintext |
| **File Permissions** | Medium | Config files world-readable |

---

## Objective: Production Security

1. ✅ **No Critical Vulnerabilities** - OWASP Top 10 checked
2. ✅ **Input Validation** - All user input sanitized
3. ✅ **Privilege Minimization** - Least-privilege principle
4. ✅ **Secure Storage** - Keys encrypted at rest
5. ✅ **Audit Logging** - Security events logged
6. ✅ **File Permissions** - Restrictive by default
7. ✅ **Code Review** - Security-focused review

---

## Part 1: Input Validation Checklist

### 1.1: VM Name Validation

**File**: `src/vm_manager/core/vm_config.py`

```python
import re

def validate_vm_name(name: str) -> List[str]:
    """
    Validate VM name for security.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Length check
    if len(name) == 0:
        errors.append("VM name cannot be empty")
    if len(name) > 64:
        errors.append("VM name too long (max 64 characters)")

    # Character whitelist
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        errors.append("VM name can only contain letters, numbers, dash, underscore")

    # Path traversal prevention
    if '..' in name or '/' in name or '\\' in name:
        errors.append("VM name cannot contain path separators")

    # Reserved names
    RESERVED = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1']  # Windows reserved
    if name.upper() in RESERVED:
        errors.append(f"VM name '{name}' is reserved")

    return errors
```

### 1.2: File Path Validation

**File**: `src/migration/migrator.py`

```python
from pathlib import Path

def validate_migration_path(path: Path, allowed_base: Path) -> bool:
    """
    Validate that migration path doesn't escape allowed directory.

    Prevents path traversal attacks.
    """
    try:
        # Resolve to absolute path
        resolved = path.resolve()
        allowed_resolved = allowed_base.resolve()

        # Check if path is within allowed base
        return resolved.is_relative_to(allowed_resolved)
    except (ValueError, OSError):
        return False

# Usage in migration
def migrate_file(source: Path, dest_base: Path):
    if not validate_migration_path(source, allowed_source_base):
        raise SecurityError(f"Path traversal attempt: {source}")

    if not validate_migration_path(dest_base, allowed_dest_base):
        raise SecurityError(f"Invalid destination: {dest_base}")

    # Proceed with migration...
```

---

## Part 2: Privilege Escalation Review

### 2.1: Audit Sudo Usage

**File**: `audit/sudo_usage.md`

```markdown
# Sudo Usage Audit

## Current Sudo Requirements

1. **VFIO GPU Binding** (`src/vm_manager/passthrough/gpu_attach.py`)
   - Command: `sudo bash -c "echo '0000:01:00.0' > /sys/bus/pci/drivers/vfio-pci/bind"`
   - Risk: Command injection if PCI address not validated
   - Mitigation: Use Python `os.write()` instead of shell

2. **GRUB Configuration** (`src/hardware_detect/grub_config.py`)
   - Command: `sudo grub-mkconfig -o /boot/grub/grub.cfg`
   - Risk: File overwrite vulnerability
   - Mitigation: Use pkexec with PolicyKit policy

3. **Systemd Service Management** (`src/common/service_manager.py`)
   - Command: `sudo systemctl start libvirtd`
   - Risk: Service manipulation
   - Mitigation: Restrict to specific services

## Recommended Changes

### Replace Sudo with PolicyKit

**File**: `/usr/share/polkit-1/actions/org.neuronos.privileged.policy`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <action id="org.neuronos.vfio.bind">
    <description>Bind GPU to VFIO driver</description>
    <message>Authentication required to bind GPU</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/lib/neuronos/vfio-bind</annotate>
  </action>
</policyconfig>
```
```

---

## Part 3: Cryptography Review

### 3.1: Key Storage Audit

**Current**: Keys stored in `~/.config/neuronos/keys/` (plaintext)
**Risk**: Attackers can read encryption keys

**Recommended**: Use system keyring

```python
import keyring

class SecureKeyStorage:
    """Store encryption keys securely."""

    @staticmethod
    def store_key(key_name: str, key_value: bytes):
        """Store key in system keyring."""
        # Convert bytes to base64 for storage
        import base64
        encoded = base64.b64encode(key_value).decode('ascii')
        keyring.set_password("neuronos", key_name, encoded)

    @staticmethod
    def retrieve_key(key_name: str) -> bytes:
        """Retrieve key from keyring."""
        import base64
        encoded = keyring.get_password("neuronos", key_name)
        if not encoded:
            raise KeyError(f"Key not found: {key_name}")
        return base64.b64decode(encoded)
```

### 3.2: Random Number Generation

**File**: `src/common/crypto.py`

```python
import secrets

def generate_key(length: int = 32) -> bytes:
    """
    Generate cryptographically secure random key.

    Uses secrets module (not random!)
    """
    return secrets.token_bytes(length)

def generate_token() -> str:
    """Generate secure token for sessions."""
    return secrets.token_urlsafe(32)
```

---

## Part 4: File Operation Security

### 4.1: Atomic File Writes

```python
import os
import tempfile
from pathlib import Path

def atomic_write(path: Path, content: str, mode: int = 0o600):
    """
    Write file atomically with secure permissions.

    Prevents race conditions and data loss.
    """
    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True
    )

    try:
        # Set restrictive permissions
        os.fchmod(fd, mode)

        # Write content
        with os.fdopen(fd, 'w') as f:
            f.write(content)

        # Atomic rename
        os.rename(temp_path, path)
    except:
        # Cleanup on error
        try:
            os.unlink(temp_path)
        except:
            pass
        raise
```

### 4.2: Secure Temp Files

```python
import tempfile

# Bad: Predictable temp file
temp_file = f"/tmp/neuronos_{vm_name}.tmp"  # Race condition!

# Good: Secure temp file
with tempfile.NamedTemporaryFile(
    mode='w',
    prefix='neuronos_',
    suffix='.tmp',
    delete=True  # Auto-delete
) as temp_file:
    temp_file.write(data)
    # File automatically deleted when closed
```

---

## Part 5: Command Injection Prevention

### 5.1: Subprocess Safety

```python
import subprocess
import shlex

# Bad: Shell injection vulnerability
def bad_example(vm_name: str):
    subprocess.run(f"qemu-img create {vm_name}.qcow2 50G", shell=True)
    # Injection: vm_name = "test; rm -rf /"

# Good: Argument list (no shell)
def good_example(vm_name: str):
    # Validate first
    if not re.match(r'^[a-zA-Z0-9_-]+$', vm_name):
        raise ValueError("Invalid VM name")

    subprocess.run([
        "qemu-img",
        "create",
        "-f", "qcow2",
        f"{vm_name}.qcow2",
        "50G"
    ], check=True)  # No shell=True!
```

---

## Part 6: Security Testing

**File**: `tests/security/test_input_validation.py`

```python
import pytest
from src.vm_manager.core.vm_config import validate_vm_name

def test_path_traversal_prevention():
    """Test that path traversal is blocked."""
    assert "path separators" in validate_vm_name("../../../etc/passwd")[0]
    assert "path separators" in validate_vm_name("test/../admin")[0]

def test_command_injection_prevention():
    """Test that command injection characters are blocked."""
    assert len(validate_vm_name("test; rm -rf /")) > 0
    assert len(validate_vm_name("test`whoami`")) > 0
    assert len(validate_vm_name("test$(whoami)")) > 0

def test_sql_injection_prevention():
    """Test SQL injection patterns blocked."""
    assert len(validate_vm_name("test' OR '1'='1")) > 0
    assert len(validate_vm_name("test'; DROP TABLE users--")) > 0
```

---

## Verification Checklist

- [ ] **Input validation** - All user input sanitized
- [ ] **No shell=True** - All subprocess calls use argument lists
- [ ] **Atomic writes** - Critical files written atomically
- [ ] **Secure temp files** - No predictable temp paths
- [ ] **Key storage** - Keys in system keyring, not plaintext
- [ ] **File permissions** - Config files 0o600, directories 0o700
- [ ] **PolicyKit** - Sudo replaced with PolicyKit where possible
- [ ] **Security tests** - Automated tests for common vulnerabilities
- [ ] **Code review** - Security-focused peer review complete
- [ ] **Penetration test** - External security audit passed

---

## Acceptance Criteria

✅ **Complete when**:
1. No critical vulnerabilities (OWASP Top 10)
2. All input validated
3. Privilege escalation minimized
4. Keys stored securely
5. Security tests passing

❌ **Fails if**:
1. Path traversal possible
2. Command injection possible
3. Keys stored in plaintext
4. Sudo without validation
5. Security tests don't exist

---

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [Linux Privilege Escalation](https://book.hacktricks.xyz/linux-hardening/privilege-escalation)

Good luck! 🚀
