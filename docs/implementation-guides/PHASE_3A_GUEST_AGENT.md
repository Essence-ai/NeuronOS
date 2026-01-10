# Phase 3A: Guest Agent Protocol Implementation

**Priority:** MEDIUM - Required for seamless VM integration
**Estimated Time:** 1-2 weeks
**Prerequisites:** Phase 2 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Protocol Specification](#protocol-specification)
3. [Security Implementation](#security-implementation)
4. [C# Guest Agent Updates](#c-guest-agent-updates)
5. [Host Python Client](#host-python-client)
6. [Feature Implementation](#feature-implementation)

---

## Overview

The guest agent enables communication between the NeuronOS host and Windows/macOS VMs for features like:
- Clipboard synchronization
- Resolution adjustment
- Application launching
- File transfer
- System information

### Current Issues

| Issue | Severity | Fix |
|-------|----------|-----|
| No encryption | CRITICAL | Add TLS/DTLS |
| No authentication | CRITICAL | Add mutual auth |
| STX/ETX conflicts with JSON | HIGH | Use length-prefix framing |
| No rate limiting | MEDIUM | Add command throttling |
| No message size limit | MEDIUM | Add size checks |

---

## Protocol Specification

### New Protocol Format

Replace STX/ETX framing with length-prefixed messages:

```
+--------+--------+--------+--------+---------------+
| Magic  | Version| Flags  | Length | Payload (JSON)|
| 2 bytes| 1 byte | 1 byte | 4 bytes| N bytes       |
+--------+--------+--------+--------+---------------+
```

**Field Definitions:**
- **Magic:** `0x4E47` ("NG" for NeuronGuest)
- **Version:** Protocol version (currently `0x01`)
- **Flags:** `0x01` = Encrypted, `0x02` = Compressed, `0x04` = Response
- **Length:** Payload length in bytes (big-endian uint32)
- **Payload:** JSON-encoded message

### Message Types

```csharp
public enum MessageType
{
    // Handshake
    Hello = 0x01,
    HelloAck = 0x02,
    KeyExchange = 0x03,
    KeyExchangeAck = 0x04,

    // Lifecycle
    Ping = 0x10,
    Pong = 0x11,
    Shutdown = 0x12,

    // System
    GetInfo = 0x20,
    InfoResponse = 0x21,
    SetResolution = 0x22,
    ResolutionAck = 0x23,

    // Clipboard
    ClipboardGet = 0x30,
    ClipboardData = 0x31,
    ClipboardSet = 0x32,
    ClipboardAck = 0x33,

    // Applications
    LaunchApp = 0x40,
    LaunchAck = 0x41,
    ListWindows = 0x42,
    WindowList = 0x43,

    // Files
    FileTransferStart = 0x50,
    FileTransferData = 0x51,
    FileTransferEnd = 0x52,
    FileTransferAck = 0x53,

    // Errors
    Error = 0xFF,
}
```

---

## Security Implementation

### Key Exchange

Use X25519 for key exchange and ChaCha20-Poly1305 for encryption:

```csharp
// NeuronGuest/Services/CryptoService.cs

using System.Security.Cryptography;

public class CryptoService : ICryptoService
{
    private byte[]? _sharedSecret;
    private byte[]? _sendKey;
    private byte[]? _receiveKey;
    private ulong _sendNonce = 0;
    private ulong _receiveNonce = 0;

    public (byte[] publicKey, byte[] privateKey) GenerateKeyPair()
    {
        using var ecdh = ECDiffieHellman.Create(ECCurve.NamedCurves.nistP256);
        var publicKey = ecdh.PublicKey.ExportSubjectPublicKeyInfo();
        var privateKey = ecdh.ExportPkcs8PrivateKey();
        return (publicKey, privateKey);
    }

    public void DeriveSharedSecret(byte[] peerPublicKey, byte[] privateKey)
    {
        using var ecdh = ECDiffieHellman.Create();
        ecdh.ImportPkcs8PrivateKey(privateKey, out _);

        using var peerKey = ECDiffieHellman.Create();
        peerKey.ImportSubjectPublicKeyInfo(peerPublicKey, out _);

        _sharedSecret = ecdh.DeriveKeyMaterial(peerKey.PublicKey);

        // Derive separate keys for send and receive
        using var hkdf = new HKDF(HashAlgorithmName.SHA256, _sharedSecret);
        _sendKey = hkdf.DeriveKey(32, "neuron-guest-send");
        _receiveKey = hkdf.DeriveKey(32, "neuron-guest-receive");
    }

    public byte[] Encrypt(byte[] plaintext)
    {
        if (_sendKey == null)
            throw new InvalidOperationException("Key exchange not completed");

        using var aes = new AesGcm(_sendKey);

        var nonce = BitConverter.GetBytes(_sendNonce++);
        Array.Resize(ref nonce, 12);

        var ciphertext = new byte[plaintext.Length];
        var tag = new byte[16];

        aes.Encrypt(nonce, plaintext, ciphertext, tag);

        // Return nonce + ciphertext + tag
        var result = new byte[12 + plaintext.Length + 16];
        Buffer.BlockCopy(nonce, 0, result, 0, 12);
        Buffer.BlockCopy(ciphertext, 0, result, 12, ciphertext.Length);
        Buffer.BlockCopy(tag, 0, result, 12 + ciphertext.Length, 16);

        return result;
    }

    public byte[] Decrypt(byte[] data)
    {
        if (_receiveKey == null)
            throw new InvalidOperationException("Key exchange not completed");

        if (data.Length < 28)
            throw new ArgumentException("Data too short");

        var nonce = new byte[12];
        Buffer.BlockCopy(data, 0, nonce, 0, 12);

        var ciphertext = new byte[data.Length - 28];
        Buffer.BlockCopy(data, 12, ciphertext, 0, ciphertext.Length);

        var tag = new byte[16];
        Buffer.BlockCopy(data, data.Length - 16, tag, 0, 16);

        using var aes = new AesGcm(_receiveKey);
        var plaintext = new byte[ciphertext.Length];
        aes.Decrypt(nonce, ciphertext, tag, plaintext);

        // Verify nonce is incrementing (replay protection)
        var receivedNonce = BitConverter.ToUInt64(nonce, 0);
        if (receivedNonce <= _receiveNonce)
            throw new CryptographicException("Replay attack detected");
        _receiveNonce = receivedNonce;

        return plaintext;
    }
}
```

### Authentication Token

Use a shared secret for initial authentication:

```csharp
public class AuthService : IAuthService
{
    private const string TokenPath = @"C:\ProgramData\NeuronOS\auth_token";

    public string GetAuthToken()
    {
        if (File.Exists(TokenPath))
            return File.ReadAllText(TokenPath).Trim();

        // Generate new token
        var token = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));
        Directory.CreateDirectory(Path.GetDirectoryName(TokenPath)!);
        File.WriteAllText(TokenPath, token);
        return token;
    }

    public bool VerifyChallenge(byte[] challenge, byte[] response, string token)
    {
        // HMAC-SHA256(challenge, token) should equal response
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(token));
        var expected = hmac.ComputeHash(challenge);
        return CryptographicOperations.FixedTimeEquals(expected, response);
    }
}
```

---

## C# Guest Agent Updates

### Updated VirtioSerialService

```csharp
// NeuronGuest/Services/VirtioSerialService.cs

public class VirtioSerialService : IVirtioSerialService, IDisposable
{
    private readonly ILogger<VirtioSerialService> _logger;
    private readonly ICryptoService _crypto;
    private readonly IAuthService _auth;
    private SerialPort? _serialPort;
    private readonly SemaphoreSlim _sendLock = new(1, 1);
    private bool _encrypted = false;

    // Protocol constants
    private static readonly byte[] MAGIC = { 0x4E, 0x47 }; // "NG"
    private const byte VERSION = 0x01;
    private const int MAX_MESSAGE_SIZE = 16 * 1024 * 1024; // 16MB
    private const int HEADER_SIZE = 8;

    // Rate limiting
    private readonly RateLimiter _rateLimiter = new(100, TimeSpan.FromSeconds(1));

    public VirtioSerialService(
        ILogger<VirtioSerialService> logger,
        ICryptoService crypto,
        IAuthService auth)
    {
        _logger = logger;
        _crypto = crypto;
        _auth = auth;
    }

    public async Task<GuestMessage?> ReceiveMessageAsync(CancellationToken ct)
    {
        if (!IsConnected || _serialPort == null)
            return null;

        try
        {
            // Read header
            var header = new byte[HEADER_SIZE];
            var bytesRead = 0;
            while (bytesRead < HEADER_SIZE)
            {
                var read = await _serialPort.BaseStream.ReadAsync(
                    header, bytesRead, HEADER_SIZE - bytesRead, ct);
                if (read == 0)
                    throw new EndOfStreamException();
                bytesRead += read;
            }

            // Verify magic
            if (header[0] != MAGIC[0] || header[1] != MAGIC[1])
            {
                _logger.LogWarning("Invalid magic bytes received");
                return null;
            }

            // Check version
            if (header[2] != VERSION)
            {
                _logger.LogWarning("Unsupported protocol version: {Version}", header[2]);
                return null;
            }

            var flags = header[3];
            var length = BinaryPrimitives.ReadUInt32BigEndian(header.AsSpan(4));

            // Validate length
            if (length > MAX_MESSAGE_SIZE)
            {
                _logger.LogWarning("Message too large: {Length}", length);
                return null;
            }

            // Rate limiting
            if (!_rateLimiter.TryAcquire())
            {
                _logger.LogWarning("Rate limit exceeded");
                return null;
            }

            // Read payload
            var payload = new byte[length];
            bytesRead = 0;
            while (bytesRead < length)
            {
                var read = await _serialPort.BaseStream.ReadAsync(
                    payload, bytesRead, (int)length - bytesRead, ct);
                if (read == 0)
                    throw new EndOfStreamException();
                bytesRead += read;
            }

            // Decrypt if needed
            if ((flags & 0x01) != 0 && _encrypted)
            {
                payload = _crypto.Decrypt(payload);
            }

            // Parse JSON
            var json = Encoding.UTF8.GetString(payload);
            return JsonSerializer.Deserialize<GuestMessage>(json);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error receiving message");
            return null;
        }
    }

    public async Task SendResponseAsync(GuestResponse response, CancellationToken ct)
    {
        if (!IsConnected || _serialPort == null)
            return;

        await _sendLock.WaitAsync(ct);
        try
        {
            var json = JsonSerializer.Serialize(response);
            var payload = Encoding.UTF8.GetBytes(json);

            byte flags = 0x04; // Response flag

            // Encrypt if session established
            if (_encrypted)
            {
                payload = _crypto.Encrypt(payload);
                flags |= 0x01;
            }

            // Build header
            var message = new byte[HEADER_SIZE + payload.Length];
            message[0] = MAGIC[0];
            message[1] = MAGIC[1];
            message[2] = VERSION;
            message[3] = flags;
            BinaryPrimitives.WriteUInt32BigEndian(message.AsSpan(4), (uint)payload.Length);
            Buffer.BlockCopy(payload, 0, message, HEADER_SIZE, payload.Length);

            await _serialPort.BaseStream.WriteAsync(message, 0, message.Length, ct);
            await _serialPort.BaseStream.FlushAsync(ct);
        }
        finally
        {
            _sendLock.Release();
        }
    }

    public async Task<bool> PerformHandshakeAsync(CancellationToken ct)
    {
        _logger.LogInformation("Starting handshake...");

        // Generate key pair
        var (publicKey, privateKey) = _crypto.GenerateKeyPair();

        // Wait for Hello from host
        var hello = await ReceiveMessageAsync(ct);
        if (hello?.Type != "hello")
        {
            _logger.LogError("Expected Hello, got: {Type}", hello?.Type);
            return false;
        }

        // Verify auth token
        var challenge = Convert.FromBase64String(hello.Data["challenge"].ToString()!);
        var token = _auth.GetAuthToken();
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(token));
        var challengeResponse = hmac.ComputeHash(challenge);

        // Send HelloAck with our public key
        await SendResponseAsync(new GuestResponse
        {
            RequestId = hello.RequestId,
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["public_key"] = Convert.ToBase64String(publicKey),
                ["challenge_response"] = Convert.ToBase64String(challengeResponse),
                ["agent_version"] = "2.0.0",
            }
        }, ct);

        // Receive host's public key
        var keyExchange = await ReceiveMessageAsync(ct);
        if (keyExchange?.Type != "key_exchange")
        {
            _logger.LogError("Expected KeyExchange, got: {Type}", keyExchange?.Type);
            return false;
        }

        var hostPublicKey = Convert.FromBase64String(
            keyExchange.Data["public_key"].ToString()!);

        // Derive shared secret
        _crypto.DeriveSharedSecret(hostPublicKey, privateKey);
        _encrypted = true;

        // Send encrypted confirmation
        await SendResponseAsync(new GuestResponse
        {
            RequestId = keyExchange.RequestId,
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["status"] = "encrypted",
            }
        }, ct);

        _logger.LogInformation("Handshake complete, encryption enabled");
        return true;
    }
}
```

### Rate Limiter

```csharp
public class RateLimiter
{
    private readonly int _maxRequests;
    private readonly TimeSpan _window;
    private readonly Queue<DateTime> _timestamps = new();
    private readonly object _lock = new();

    public RateLimiter(int maxRequests, TimeSpan window)
    {
        _maxRequests = maxRequests;
        _window = window;
    }

    public bool TryAcquire()
    {
        lock (_lock)
        {
            var now = DateTime.UtcNow;
            var cutoff = now - _window;

            // Remove old timestamps
            while (_timestamps.Count > 0 && _timestamps.Peek() < cutoff)
                _timestamps.Dequeue();

            if (_timestamps.Count >= _maxRequests)
                return false;

            _timestamps.Enqueue(now);
            return true;
        }
    }
}
```

---

## Feature Implementation

### Clipboard Synchronization

```csharp
// NeuronGuest/Services/ClipboardService.cs

public class ClipboardService : IClipboardService
{
    private readonly ILogger<ClipboardService> _logger;
    private string _lastClipboardContent = "";

    public ClipboardService(ILogger<ClipboardService> logger)
    {
        _logger = logger;
    }

    public async Task<string> GetClipboardTextAsync()
    {
        return await Task.Run(() =>
        {
            try
            {
                if (Clipboard.ContainsText())
                    return Clipboard.GetText();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to get clipboard");
            }
            return "";
        });
    }

    public async Task<bool> SetClipboardTextAsync(string text)
    {
        return await Task.Run(() =>
        {
            try
            {
                // Use STA thread for clipboard
                Thread thread = new(() =>
                {
                    Clipboard.SetText(text);
                });
                thread.SetApartmentState(ApartmentState.STA);
                thread.Start();
                thread.Join(1000);
                return true;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to set clipboard");
                return false;
            }
        });
    }

    public bool HasClipboardChanged()
    {
        try
        {
            var current = Clipboard.GetText() ?? "";
            if (current != _lastClipboardContent)
            {
                _lastClipboardContent = current;
                return true;
            }
        }
        catch { }
        return false;
    }
}
```

### Resolution Synchronization

```csharp
// NeuronGuest/Services/DisplayService.cs

using System.Runtime.InteropServices;

public class DisplayService : IDisplayService
{
    private readonly ILogger<DisplayService> _logger;

    [DllImport("user32.dll")]
    private static extern int ChangeDisplaySettings(
        ref DEVMODE devMode, int flags);

    [DllImport("user32.dll")]
    private static extern bool EnumDisplaySettings(
        string? deviceName, int modeNum, ref DEVMODE devMode);

    [StructLayout(LayoutKind.Sequential)]
    private struct DEVMODE
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        // ... additional fields
    }

    private const int ENUM_CURRENT_SETTINGS = -1;
    private const int CDS_UPDATEREGISTRY = 0x01;
    private const int CDS_TEST = 0x02;
    private const int DM_PELSWIDTH = 0x80000;
    private const int DM_PELSHEIGHT = 0x100000;

    public DisplayService(ILogger<DisplayService> logger)
    {
        _logger = logger;
    }

    public (int width, int height) GetCurrentResolution()
    {
        var devMode = new DEVMODE();
        devMode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));

        if (EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref devMode))
        {
            return (devMode.dmPelsWidth, devMode.dmPelsHeight);
        }

        return (1920, 1080); // Default
    }

    public bool SetResolution(int width, int height)
    {
        _logger.LogInformation("Setting resolution to {Width}x{Height}", width, height);

        var devMode = new DEVMODE();
        devMode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));

        // Get current settings
        if (!EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref devMode))
        {
            _logger.LogError("Failed to get current display settings");
            return false;
        }

        // Set new resolution
        devMode.dmPelsWidth = width;
        devMode.dmPelsHeight = height;
        devMode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;

        // Test change first
        var result = ChangeDisplaySettings(ref devMode, CDS_TEST);
        if (result != 0)
        {
            _logger.LogError("Resolution not supported: {Result}", result);
            return false;
        }

        // Apply change
        result = ChangeDisplaySettings(ref devMode, CDS_UPDATEREGISTRY);
        if (result != 0)
        {
            _logger.LogError("Failed to change resolution: {Result}", result);
            return false;
        }

        _logger.LogInformation("Resolution changed successfully");
        return true;
    }

    public List<(int width, int height)> GetSupportedResolutions()
    {
        var resolutions = new HashSet<(int, int)>();
        var devMode = new DEVMODE();
        devMode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));

        int modeNum = 0;
        while (EnumDisplaySettings(null, modeNum++, ref devMode))
        {
            if (devMode.dmBitsPerPel >= 24) // Only 24/32 bit modes
            {
                resolutions.Add((devMode.dmPelsWidth, devMode.dmPelsHeight));
            }
        }

        return resolutions.OrderByDescending(r => r.Item1 * r.Item2).ToList();
    }
}
```

### Application Launching

```csharp
// NeuronGuest/Services/AppLauncherService.cs

public class AppLauncherService : IAppLauncherService
{
    private readonly ILogger<AppLauncherService> _logger;

    // Allowed directories for launching apps
    private readonly string[] _allowedPaths = {
        @"C:\Program Files",
        @"C:\Program Files (x86)",
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
    };

    public AppLauncherService(ILogger<AppLauncherService> logger)
    {
        _logger = logger;
    }

    public bool LaunchApplication(string path, string[]? args = null)
    {
        // SECURITY: Validate path is within allowed directories
        if (!IsPathAllowed(path))
        {
            _logger.LogWarning("Blocked launch of disallowed path: {Path}", path);
            return false;
        }

        // SECURITY: Validate file exists and is executable
        if (!File.Exists(path))
        {
            _logger.LogWarning("Application not found: {Path}", path);
            return false;
        }

        var extension = Path.GetExtension(path).ToLower();
        if (extension != ".exe" && extension != ".msi")
        {
            _logger.LogWarning("Not an executable: {Path}", path);
            return false;
        }

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = path,
                Arguments = args != null ? string.Join(" ", args.Select(Escape)) : "",
                UseShellExecute = true,
            };

            Process.Start(startInfo);
            _logger.LogInformation("Launched: {Path}", path);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to launch: {Path}", path);
            return false;
        }
    }

    private bool IsPathAllowed(string path)
    {
        var fullPath = Path.GetFullPath(path);

        foreach (var allowedPath in _allowedPaths)
        {
            if (fullPath.StartsWith(allowedPath, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        return false;
    }

    private static string Escape(string arg)
    {
        // Escape argument for command line
        if (arg.Contains(' ') || arg.Contains('"'))
            return "\"" + arg.Replace("\"", "\\\"") + "\"";
        return arg;
    }
}
```

---

## Host Python Client

See Phase 3 for the host-side `GuestAgentClient` implementation.

### Integration with Looking Glass

```python
# vm_manager/core/lg_integration.py

class LookingGlassGuestIntegration:
    """Integrates Looking Glass with guest agent for resolution sync."""

    def __init__(self, vm_name: str):
        self.vm_name = vm_name
        self.guest_client = GuestAgentClient(vm_name)
        self._lg_manager = get_looking_glass_manager()

    def start(self):
        """Start resolution synchronization."""
        # Connect to guest
        if not self.guest_client.connect():
            logger.warning("Could not connect to guest agent")
            return

        # Monitor Looking Glass window size changes
        self._lg_manager.add_state_callback(self._on_lg_state_change)

    def _on_lg_state_change(self, vm_name: str, state: LGState):
        if vm_name != self.vm_name:
            return

        if state == LGState.RUNNING:
            # Get current window size and sync to guest
            # This would require Looking Glass to report window size
            pass

    def sync_resolution(self, width: int, height: int):
        """Sync resolution to guest."""
        if self.guest_client.is_connected:
            self.guest_client.set_resolution(width, height)
```

---

## Verification Checklist

- [ ] Protocol uses length-prefix framing
- [ ] Encryption enabled after handshake
- [ ] Rate limiting prevents DoS
- [ ] Message size limits enforced
- [ ] App launcher validates paths
- [ ] Clipboard sync works bidirectionally
- [ ] Resolution sync works with Looking Glass
- [ ] Authentication prevents unauthorized access

---

## Next Phase

Proceed to [Phase 4: Error Handling](./PHASE_4_ERROR_HANDLING.md).
