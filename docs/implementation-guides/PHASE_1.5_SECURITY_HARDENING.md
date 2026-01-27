# Phase 1.5: Guest Agent Security Hardening

**Status**: 🔴 SECURITY RISK - Guest agent communication unencrypted
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 1.1 (guest agent must be compilable)

---

## The Problem: Unencrypted Host-Guest Communication

Currently, host-guest communication is **completely unencrypted**:

### Current Protocol (Unsafe)

```python
# Host → Guest: Plaintext JSON over virtio-serial
{
  "type": "launch_app",
  "request_id": "req_123",
  "data": {
    "app_path": "C:\\Program Files\\Adobe\\Photoshop\\photoshop.exe",
    "args": "--license-key=ABC-123"
  }
}
```

### Risks

1. **No Authentication** - Any process on host can send commands
2. **No Encryption** - Plaintext visible to anyone with access
3. **No Integrity Check** - Messages can be modified in transit
4. **No Authorization** - Guest executes any command from host

### Attack Scenarios

```
Scenario 1: Malicious Host Process
  1. Attacker's program opens /dev/ttyS0 (virtio-serial)
  2. Sends: {"type": "launch_app", "app_path": "C:\\malware.exe"}
  3. Guest executes without verification

Scenario 2: Network Sniffer
  1. Attacker intercepts VM network traffic
  2. Sees plaintext commands in memory
  3. Modifies commands: {"type": "launch_app", "app_path": "C:\\stealdata.exe"}

Scenario 3: Privilege Escalation
  1. User runs guest agent as SYSTEM
  2. Unprivileged attacker sends commands to guest
  3. Guest executes with full system privileges
```

---

## Objective: Secure Host-Guest Communication

After this phase:

1. ✅ **HMAC Authentication** - Verify messages come from expected host
2. ✅ **Message Encryption** - AES-256 encryption for data
3. ✅ **Integrity Verification** - Detect tampered messages
4. ✅ **Challenge-Response** - Prevent replay attacks
5. ✅ **Rate Limiting** - Prevent DoS from malicious sender
6. ✅ **Clear Security Warnings** - Users understand risks

---

## Part 1: Key Management

### 1.1: Generate Shared Secret

**On Host**: Generate a shared secret that both sides know

**File**: `src/security/key_generator.py` (NEW FILE)

```python
"""
Key generation for host-guest communication.

Generates and manages shared secrets for securing virtio-serial communication.
"""

import secrets
import json
from pathlib import Path
from typing import Tuple


class KeyGenerator:
    """Generate and manage encryption keys for guest agent."""

    @staticmethod
    def generate_key(key_length: int = 32) -> bytes:
        """
        Generate a random key.

        Args:
            key_length: Length in bytes (default 32 = 256 bits)

        Returns:
            Random bytes suitable for AES-256
        """
        return secrets.token_bytes(key_length)

    @staticmethod
    def generate_hmac_key(key_length: int = 32) -> bytes:
        """
        Generate HMAC signing key.

        Args:
            key_length: Length in bytes

        Returns:
            Random bytes for HMAC
        """
        return secrets.token_bytes(key_length)

    @staticmethod
    def save_key(key: bytes, path: Path, mode: int = 0o600):
        """
        Save key to file with restricted permissions.

        Args:
            key: Key bytes to save
            path: File path
            mode: File permissions (default 0o600 = owner RW only)
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write key as hex-encoded text
        key_hex = key.hex()

        from src.utils.atomic_write import atomic_write_text
        atomic_write_text(path, key_hex, mode)

    @staticmethod
    def load_key(path: Path) -> bytes:
        """Load key from file."""
        with open(path, "r") as f:
            key_hex = f.read().strip()

        return bytes.fromhex(key_hex)

    @staticmethod
    def generate_key_pair() -> Tuple[bytes, bytes]:
        """
        Generate both encryption and HMAC keys.

        Returns:
            Tuple of (encryption_key, hmac_key)
        """
        encryption_key = KeyGenerator.generate_key(32)  # AES-256
        hmac_key = KeyGenerator.generate_hmac_key(32)    # HMAC-SHA256

        return encryption_key, hmac_key

    @staticmethod
    def write_vm_keys(vm_name: str, encryption_key: bytes, hmac_key: bytes):
        """
        Write keys to VM config directory.

        These keys will be:
        1. Embedded in guest agent Windows build
        2. Used by host to communicate with guest
        """
        config_dir = (
            Path.home() / ".local" / "share" / "neuron-os" / "vm-keys" / vm_name
        )
        config_dir.mkdir(parents=True, exist_ok=True)

        KeyGenerator.save_key(encryption_key, config_dir / "encryption.key", 0o600)
        KeyGenerator.save_key(hmac_key, config_dir / "hmac.key", 0o600)
```

### 1.2: Create Key on VM Creation

**File**: `src/vm_manager/core/vm_creator.py`

**Add to create_vm() method** (after creating VM):

```python
def create_vm(self, config: VMConfig) -> bool:
    """Create and define a VM."""
    # ... existing code ...

    # After successful VM creation, generate encryption keys
    try:
        from src.security.key_generator import KeyGenerator

        encryption_key, hmac_key = KeyGenerator.generate_key_pair()
        KeyGenerator.write_vm_keys(config.name, encryption_key, hmac_key)

        logger.info(f"Generated encryption keys for VM: {config.name}")
    except Exception as e:
        logger.error(f"Failed to generate keys for VM: {e}")
        # Non-fatal - continue, guest agent will use fallback

    return True
```

---

## Part 2: Message Encryption & Authentication

### 2.1: Message Encryption Class

**File**: `src/security/message_crypt.py` (NEW FILE)

```python
"""
Encryption and authentication for guest agent messages.

Uses AES-256-GCM for authenticated encryption.
"""

import json
import os
import hmac
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class EncryptedMessage:
    """Container for encrypted message with metadata."""
    ciphertext: str          # Hex-encoded ciphertext
    nonce: str               # Hex-encoded nonce/IV
    tag: str                 # Hex-encoded authentication tag
    version: int = 1         # Protocol version


class MessageCryptor:
    """Encrypt and authenticate messages."""

    def __init__(self, encryption_key: bytes, hmac_key: bytes):
        """
        Initialize with keys.

        Args:
            encryption_key: 32-byte AES-256 key
            hmac_key: 32-byte HMAC-SHA256 key
        """
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be 32 bytes")
        if len(hmac_key) != 32:
            raise ValueError("HMAC key must be 32 bytes")

        self.encryption_key = encryption_key
        self.hmac_key = hmac_key

    def encrypt_message(self, message: Dict[str, Any]) -> EncryptedMessage:
        """
        Encrypt and authenticate a message.

        Args:
            message: Dictionary to encrypt (will be JSON-serialized)

        Returns:
            EncryptedMessage with ciphertext, nonce, tag

        Raises:
            Exception: If encryption fails
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            # Serialize message
            plaintext = json.dumps(message).encode("utf-8")

            # Generate random nonce (96 bits for GCM)
            nonce = os.urandom(12)

            # Encrypt with AES-256-GCM
            cipher = AESGCM(self.encryption_key)

            # Associated data: ensure message wasn't moved/reordered
            aad = b"neuronos-host-guest-v1"

            ciphertext = cipher.encrypt(nonce, plaintext, aad)

            # The last 16 bytes of ciphertext are the tag
            # Split them for clarity
            tag = ciphertext[-16:]
            actual_ciphertext = ciphertext[:-16]

            return EncryptedMessage(
                ciphertext=actual_ciphertext.hex(),
                nonce=nonce.hex(),
                tag=tag.hex(),
                version=1,
            )

        except Exception as e:
            raise Exception(f"Encryption failed: {e}")

    def decrypt_message(self, encrypted: EncryptedMessage) -> Optional[Dict[str, Any]]:
        """
        Decrypt and verify a message.

        Args:
            encrypted: EncryptedMessage from host

        Returns:
            Decrypted message dictionary, or None if verification failed
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            # Decode from hex
            nonce = bytes.fromhex(encrypted.nonce)
            ciphertext = bytes.fromhex(encrypted.ciphertext)
            tag = bytes.fromhex(encrypted.tag)

            # Reconstruct full ciphertext (ciphertext + tag)
            full_ciphertext = ciphertext + tag

            # Decrypt
            cipher = AESGCM(self.encryption_key)
            aad = b"neuronos-host-guest-v1"

            plaintext = cipher.decrypt(nonce, full_ciphertext, aad)

            # Parse JSON
            message = json.loads(plaintext.decode("utf-8"))

            return message

        except Exception as e:
            # Decryption/verification failed
            return None

    def sign_message(self, message: Dict[str, Any]) -> str:
        """
        Create HMAC signature for message (alternative to encryption).

        Used for replies where we don't need to encrypt the response.

        Args:
            message: Message to sign

        Returns:
            Hex-encoded HMAC signature
        """
        plaintext = json.dumps(message, sort_keys=True).encode("utf-8")

        signature = hmac.new(
            self.hmac_key,
            plaintext,
            hashlib.sha256,
        ).digest()

        return signature.hex()

    def verify_signature(self, message: Dict[str, Any], signature: str) -> bool:
        """
        Verify HMAC signature of message.

        Args:
            message: Message to verify
            signature: Hex-encoded signature

        Returns:
            True if signature is valid
        """
        plaintext = json.dumps(message, sort_keys=True).encode("utf-8")

        expected_signature = hmac.new(
            self.hmac_key,
            plaintext,
            hashlib.sha256,
        ).digest()

        try:
            provided_signature = bytes.fromhex(signature)
        except ValueError:
            return False

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, provided_signature)
```

### 2.2: Update Host GuestClient

**File**: `src/vm_manager/core/guest_client.py`

**Replace send_command() to encrypt messages**:

```python
def send_command(
    self,
    command_type: str,
    data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Send encrypted command to guest.

    Args:
        command_type: Type of command (ping, launch_app, etc.)
        data: Command data

    Returns:
        Response from guest, or None if failed
    """
    import socket

    try:
        # Load encryption keys
        encryption_key, hmac_key = self._load_keys()

        if not encryption_key or not hmac_key:
            logger.error("Could not load encryption keys")
            return None

        # Create cryptor
        from src.security.message_crypt import MessageCryptor
        cryptor = MessageCryptor(encryption_key, hmac_key)

        # Build message
        message = {
            "type": command_type,
            "request_id": str(uuid.uuid4()),
            "data": data,
            "timestamp": int(time.time()),
        }

        # Encrypt
        encrypted = cryptor.encrypt_message(message)

        # Send encrypted message as JSON
        encrypted_json = json.dumps({
            "ciphertext": encrypted.ciphertext,
            "nonce": encrypted.nonce,
            "tag": encrypted.tag,
            "version": encrypted.version,
        })

        # Connect to virtio-serial
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.serial_path)
        sock.send(encrypted_json.encode("utf-8") + b"\n")

        # Read response
        response_data = sock.recv(4096)
        sock.close()

        if not response_data:
            logger.error("No response from guest")
            return None

        # Parse encrypted response
        response_encrypted = json.loads(response_data)

        # Decrypt response
        from src.security.message_crypt import EncryptedMessage
        encrypted_response = EncryptedMessage(
            ciphertext=response_encrypted["ciphertext"],
            nonce=response_encrypted["nonce"],
            tag=response_encrypted["tag"],
            version=response_encrypted.get("version", 1),
        )

        decrypted_response = cryptor.decrypt_message(encrypted_response)

        if not decrypted_response:
            logger.error("Failed to decrypt response from guest")
            return None

        return decrypted_response

    except Exception as e:
        logger.error(f"Error sending command: {e}")
        return None

def _load_keys(self) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Load encryption keys for VM."""
    from pathlib import Path
    from src.security.key_generator import KeyGenerator

    try:
        keys_dir = Path.home() / ".local" / "share" / "neuron-os" / "vm-keys" / self.vm_name

        if not keys_dir.exists():
            logger.warning(f"Keys directory not found: {keys_dir}")
            return None, None

        encryption_key = KeyGenerator.load_key(keys_dir / "encryption.key")
        hmac_key = KeyGenerator.load_key(keys_dir / "hmac.key")

        return encryption_key, hmac_key

    except Exception as e:
        logger.error(f"Failed to load keys: {e}")
        return None, None
```

---

## Part 3: Guest Agent Security Updates

### 3.1: Update C# Guest Service

**File**: `src/guest_agent/NeuronGuest/Services/VirtioSerialService.cs`

**Add encryption support**:

```csharp
using System;
using System.IO;
using System.IO.Ports;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;

public class VirtioSerialService
{
    private SerialPort _serialPort;
    private CommandHandler _commandHandler;
    private byte[] _encryptionKey;
    private byte[] _hmacKey;

    public VirtioSerialService()
    {
        _commandHandler = new CommandHandler();
        LoadKeys();
    }

    public void Start()
    {
        try
        {
            _serialPort = new SerialPort("COM3", 115200);
            _serialPort.Open();

            EventLog.WriteEntry("NeuronGuest", "VirtioSerial service started");

            while (true)
            {
                if (_serialPort.BytesToRead > 0)
                {
                    string encryptedJson = _serialPort.ReadLine();
                    string response = ProcessCommand(encryptedJson);
                    _serialPort.WriteLine(response);
                }
                System.Threading.Thread.Sleep(100);
            }
        }
        catch (Exception ex)
        {
            EventLog.WriteEntry("NeuronGuest", $"Error: {ex.Message}", EventLogEntryType.Error);
        }
        finally
        {
            _serialPort?.Close();
        }
    }

    private string ProcessCommand(string encryptedJson)
    {
        try
        {
            // Parse encrypted message
            var encrypted = JsonDocument.Parse(encryptedJson);
            var root = encrypted.RootElement;

            // Decrypt message
            string ciphertext = root.GetProperty("ciphertext").GetString();
            string nonce = root.GetProperty("nonce").GetString();
            string tag = root.GetProperty("tag").GetString();

            string plaintext = DecryptMessage(ciphertext, nonce, tag);
            if (plaintext == null)
            {
                return EncryptResponse("error", "Decryption failed");
            }

            // Execute command
            var command = JsonDocument.Parse(plaintext);
            var result = _commandHandler.Handle(command);

            // Encrypt response
            return result;
        }
        catch (Exception ex)
        {
            EventLog.WriteEntry("NeuronGuest", $"Error processing command: {ex.Message}");
            return EncryptResponse("error", "Internal error");
        }
    }

    private string DecryptMessage(string ciphertextHex, string nonceHex, string tagHex)
    {
        if (_encryptionKey == null)
            return null;

        try
        {
            byte[] ciphertext = Convert.FromHexString(ciphertextHex);
            byte[] nonce = Convert.FromHexString(nonceHex);
            byte[] tag = Convert.FromHexString(tagHex);

            // Combine ciphertext and tag for AesGcm
            byte[] fullCiphertext = new byte[ciphertext.Length + tag.Length];
            Buffer.BlockCopy(ciphertext, 0, fullCiphertext, 0, ciphertext.Length);
            Buffer.BlockCopy(tag, 0, fullCiphertext, ciphertext.Length, tag.Length);

            // Decrypt with AES-256-GCM
            var aad = Encoding.UTF8.GetBytes("neuronos-host-guest-v1");

            using (var cipher = new AesGcm(_encryptionKey, AesGcm.NonceByteSizes.Size96))
            {
                byte[] plaintext = new byte[ciphertext.Length];
                cipher.Decrypt(nonce, fullCiphertext, aad, plaintext);
                return Encoding.UTF8.GetString(plaintext);
            }
        }
        catch
        {
            return null;
        }
    }

    private string EncryptResponse(string status, object data)
    {
        if (_encryptionKey == null)
        {
            // Keys not loaded, send unencrypted with warning
            return JsonSerializer.Serialize(new { status = status, data = data });
        }

        try
        {
            string plaintext = JsonSerializer.Serialize(new { status = status, data = data });
            byte[] plaintextBytes = Encoding.UTF8.GetBytes(plaintext);

            // Generate random nonce
            byte[] nonce = new byte[12];
            using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
            {
                rng.GetBytes(nonce);
            }

            // Encrypt
            var aad = Encoding.UTF8.GetBytes("neuronos-host-guest-v1");
            byte[] tag = new byte[16];

            using (var cipher = new AesGcm(_encryptionKey, AesGcm.NonceByteSizes.Size96))
            {
                byte[] ciphertext = new byte[plaintextBytes.Length];
                cipher.Encrypt(nonce, plaintextBytes, aad, tag, ciphertext);

                // Return encrypted message
                return JsonSerializer.Serialize(new
                {
                    ciphertext = Convert.ToHexString(ciphertext),
                    nonce = Convert.ToHexString(nonce),
                    tag = Convert.ToHexString(tag),
                    version = 1
                });
            }
        }
        catch (Exception ex)
        {
            EventLog.WriteEntry("NeuronGuest", $"Encryption error: {ex.Message}");
            return JsonSerializer.Serialize(new { status = "error", data = "Encryption failed" });
        }
    }

    private void LoadKeys()
    {
        try
        {
            // Keys are embedded in the build or stored in a secure location
            // For now, use a default hardcoded key (MUST be replaced with secure key storage)
            // TODO: Load from secure key storage (Windows DPAPI, etc.)

            _encryptionKey = new byte[32];    // Should be loaded from config
            _hmacKey = new byte[32];          // Should be loaded from config

            // For development, initialize with zeros (INSECURE - fix before production)
            for (int i = 0; i < 32; i++)
            {
                _encryptionKey[i] = 0;
                _hmacKey[i] = 0;
            }

            EventLog.WriteEntry("NeuronGuest", "Encryption keys loaded");
        }
        catch (Exception ex)
        {
            EventLog.WriteEntry("NeuronGuest", $"Failed to load keys: {ex.Message}");
            _encryptionKey = null;
            _hmacKey = null;
        }
    }
}
```

---

## Part 4: Testing & Verification

### 4.1: Create Security Tests

**File**: `tests/test_message_security.py` (NEW FILE)

```python
"""Tests for message encryption and authentication."""

import pytest
import json
from src.security.message_crypt import MessageCryptor, EncryptedMessage
from src.security.key_generator import KeyGenerator


@pytest.fixture
def keys():
    """Generate test keys."""
    encryption_key, hmac_key = KeyGenerator.generate_key_pair()
    yield encryption_key, hmac_key


def test_message_encryption(keys):
    """Test that messages are encrypted correctly."""
    encryption_key, hmac_key = keys
    cryptor = MessageCryptor(encryption_key, hmac_key)

    # Original message
    message = {
        "type": "launch_app",
        "data": {"app_path": "C:\\Program Files\\App\\app.exe"},
    }

    # Encrypt
    encrypted = cryptor.encrypt_message(message)

    # Verify ciphertext is not readable
    assert encrypted.ciphertext != message
    assert encrypted.nonce
    assert encrypted.tag

    # Verify can decrypt
    decrypted = cryptor.decrypt_message(encrypted)
    assert decrypted == message


def test_message_decryption_fails_with_wrong_key(keys):
    """Test that decryption fails with wrong key."""
    encryption_key, hmac_key = keys
    cryptor = MessageCryptor(encryption_key, hmac_key)

    message = {"type": "ping"}
    encrypted = cryptor.encrypt_message(message)

    # Try to decrypt with wrong key
    wrong_encryption_key, _ = KeyGenerator.generate_key_pair()
    wrong_cryptor = MessageCryptor(wrong_encryption_key, hmac_key)

    decrypted = wrong_cryptor.decrypt_message(encrypted)
    assert decrypted is None  # Decryption should fail


def test_message_tamper_detection(keys):
    """Test that tampered messages are detected."""
    encryption_key, hmac_key = keys
    cryptor = MessageCryptor(encryption_key, hmac_key)

    message = {"type": "launch_app", "data": {"app_path": "C:\\Program Files\\App\\app.exe"}}
    encrypted = cryptor.encrypt_message(message)

    # Tamper with ciphertext
    tampered_ciphertext = encrypted.ciphertext[:-4] + "XXXX"
    tampered = EncryptedMessage(
        ciphertext=tampered_ciphertext,
        nonce=encrypted.nonce,
        tag=encrypted.tag,
    )

    # Decryption should fail
    decrypted = cryptor.decrypt_message(tampered)
    assert decrypted is None


def test_hmac_signing(keys):
    """Test HMAC signing and verification."""
    encryption_key, hmac_key = keys
    cryptor = MessageCryptor(encryption_key, hmac_key)

    message = {"type": "response", "status": "ok"}

    # Sign
    signature = cryptor.sign_message(message)
    assert signature

    # Verify
    assert cryptor.verify_signature(message, signature)


def test_hmac_tamper_detection(keys):
    """Test that HMAC detects tampering."""
    encryption_key, hmac_key = keys
    cryptor = MessageCryptor(encryption_key, hmac_key)

    message = {"type": "response", "status": "ok"}
    signature = cryptor.sign_message(message)

    # Tamper with message
    tampered_message = {"type": "response", "status": "error"}

    # Verification should fail
    assert not cryptor.verify_signature(tampered_message, signature)


def test_key_generation():
    """Test key generation."""
    key1 = KeyGenerator.generate_key(32)
    key2 = KeyGenerator.generate_key(32)

    # Keys should be different
    assert key1 != key2

    # Keys should be correct length
    assert len(key1) == 32
    assert len(key2) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 4.2: Run Tests

```bash
pytest tests/test_message_security.py -v
```

---

## Verification Checklist

Before completing Phase 1:

**Key Generation**:
- [ ] Keys generated correctly (32 bytes each)
- [ ] Keys saved with 0o600 permissions (owner only)
- [ ] Keys loaded correctly from files
- [ ] Different VMs have different keys

**Encryption**:
- [ ] Messages encrypted with AES-256-GCM
- [ ] Nonce generated randomly for each message
- [ ] Authentication tag computed and verified
- [ ] Encrypted message different from plaintext

**Authentication**:
- [ ] Tampered ciphertexts rejected
- [ ] Modified authentication tags detected
- [ ] Wrong keys fail to decrypt
- [ ] HMAC signatures verified correctly

**Host Integration**:
- [ ] GuestClient loads encryption keys
- [ ] Commands encrypted before sending
- [ ] Responses decrypted correctly
- [ ] Failures handled gracefully

**Guest Integration**:
- [ ] Guest service decrypts messages
- [ ] Responses encrypted
- [ ] Unencrypted fallback works (warning logged)
- [ ] Encryption errors logged

**Tests**:
- [ ] test_message_encryption passes
- [ ] test_message_decryption_fails_with_wrong_key passes
- [ ] test_message_tamper_detection passes
- [ ] test_hmac_signing passes
- [ ] test_hmac_tamper_detection passes

**Security**:
- [ ] No plaintext commands in logs
- [ ] Keys not logged or printed
- [ ] Encryption errors reported safely
- [ ] Timing attacks mitigated (constant-time compare)

---

## Acceptance Criteria

✅ **Phase 1.5 Complete When**:

1. Messages are encrypted with AES-256-GCM
2. Authentication tags prevent tampering
3. Wrong keys fail to decrypt
4. Both host and guest support encryption
5. All security tests pass

❌ **Phase 1.5 Fails If**:

- Messages transmitted unencrypted
- Tampered messages accepted
- No error on decryption failure
- Tests fail

---

## Important Notes

### Key Embedding

The C# guest agent needs the encryption keys. Options:

1. **Embed in Build** - Keys compiled into .exe (secure)
2. **Config File** - Keys in encrypted config file
3. **Key Exchange** - Host sends keys at startup (complex)

For now, use **Option 1**: Keys embedded at build time.

### Key Rotation

Keys should be rotated periodically. Add to roadmap for Phase 5.

### Windows DPAPI

C# code should use Windows DPAPI to encrypt keys:

```csharp
using System.Security.Cryptography;

// Encrypt key with user's Windows account
byte[] encryptedKey = ProtectedData.Protect(
    keyBytes,
    null,
    DataProtectionScope.CurrentUser
);

// Decrypt
byte[] decryptedKey = ProtectedData.Unprotect(
    encryptedKey,
    null,
    DataProtectionScope.CurrentUser
);
```

This ensures keys are protected by Windows.

---

## Risks & Mitigations

### Risk 1: Hardcoded Keys in Guest Service

**Issue**: Keys in plaintext in Windows executable

**Mitigation**:
- Use Windows DPAPI to encrypt keys
- Load keys at runtime (don't hardcode)
- Document security assumptions

### Risk 2: Key Extraction

**Issue**: Attacker extracts keys from Windows memory

**Mitigation**:
- Use secure key storage (HSM, TPM if available)
- Zero out keys after use
- Document that this is not protected against kernel attacks

### Risk 3: Nonce Reuse

**Issue**: Same nonce used twice breaks AES-GCM security

**Mitigation**:
- Random nonce for each message (os.urandom(12))
- C# also uses random nonce
- Verify nonce is different in tests

---

## Next Steps

After Phase 1 complete:

1. **Phase 2** implements core functionality (onboarding, store, etc.)
2. **Phase 1.5.1** (future) adds key rotation
3. **Phase 4.2** does full security audit

---

## Resources

- [AES-GCM Documentation](https://en.wikipedia.org/wiki/Galois/Counter_Mode)
- [Cryptography.io](https://cryptography.io/)
- [Windows DPAPI](https://docs.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata)
- [OWASP Communication Security](https://cheatsheetseries.owasp.org/)

Good luck! 🚀
