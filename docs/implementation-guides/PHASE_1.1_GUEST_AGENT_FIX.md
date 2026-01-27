# Phase 1.1: Guest Agent C# Compilation Fix

**Status**: 🔴 CRITICAL BLOCKER - Prevents host-guest communication
**Estimated Time**: 2 days
**Prerequisites**: None (can work in parallel with other Phase 1 items)

---

## What is the Guest Agent?

The **NeuronGuest** service runs inside Windows VMs as a background service. It:

1. **Listens for commands** from the host via virtio-serial device
2. **Executes commands** like:
   - Set screen resolution when Looking Glass window resizes
   - Launch applications from the host's App Store
   - Sync clipboard between host and guest
   - Get system information (OS version, installed apps)
3. **Returns results** to host via secure encrypted channel

**Without this**: Users cannot launch Windows apps from the NeuronOS App Store, cannot sync clipboard, cannot change VM resolution. The VM becomes isolated.

---

## Current State: Compilation Errors

The C# guest agent (`src/guest_agent/NeuronGuest/`) has **blocking compilation errors**:

```
error CS1069: The type name 'SerialPort' could not be found in the namespace 'System.IO.Ports'.
Are you missing an assembly reference?

error CS0234: The type or namespace name 'Ports' does not exist in the namespace 'System.IO'.
```

**Location**: `src/guest_agent/NeuronGuest/Services/VirtioSerialService.cs` (lines 8, 15)

**Root Cause**: The C# project is missing the `System.IO.Ports` NuGet package reference.

### What This Means

```
VirtioSerialService.cs:
    using System.IO.Ports;      ← This namespace doesn't exist!

    SerialPort serialPort = new SerialPort("COM3");  ← CS1069 error here
```

---

## Objective: Make Guest Agent Compilable

After completing this phase:

1. ✅ Guest agent compiles without errors
2. ✅ Windows Service can be built and installed
3. ✅ Protocol for host-guest communication is defined
4. ✅ Basic command/response framework works
5. ✅ Foundation for Phase 1.5 (security hardening)

**Deliverable**: A Windows Service that:
- Listens on virtio-serial device (COM3)
- Receives JSON-encoded commands
- Routes commands to handlers
- Sends results back to host

---

## Part 1: Fix C# Compilation Errors

### 1.1.1: Add Missing NuGet Package

**File**: `src/guest_agent/NeuronGuest/NeuronGuest.csproj`

**Current Content** (partial):
```xml
<Project Sdk="Microsoft.NET.Sdk.WindowsDesktop">

  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net7.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
  </PropertyGroup>

  <ItemGroup>
    <!-- NO PackageReferences! -->
  </ItemGroup>

</Project>
```

**What To Do**: Add `System.IO.Ports` NuGet reference

**Modified File**:
```xml
<Project Sdk="Microsoft.NET.Sdk.WindowsDesktop">

  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net7.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
  </PropertyGroup>

  <ItemGroup>
    <!-- ADDED: Fix serial port compilation error -->
    <PackageReference Include="System.IO.Ports" Version="4.3.0" />
  </ItemGroup>

</Project>
```

**Why This Version?**
- `System.IO.Ports 4.3.0` is the stable, widely-compatible version
- Works with .NET Framework, .NET Core, and .NET 7
- Alternative: `8.0.0` if needing latest, but 4.3.0 is safer for compatibility

### 1.1.2: Test Compilation

**In Windows or Visual Studio**:

```bash
# Navigate to guest agent directory
cd src/guest_agent/NeuronGuest

# Restore packages
dotnet restore

# Build to check for errors
dotnet build

# Expected output:
# Build succeeded. 0 Warning(s)
```

**What Should Happen**:
- ❌ Before: `error CS1069` - SerialPort not found
- ✅ After: `Build succeeded`

**If Still Fails**:
- Check NuGet package version: `dotnet package search System.IO.Ports`
- Try version 4.5.0 instead
- Ensure .NET SDK is installed: `dotnet --version` (should be 7.0+)

---

## Part 2: Verify Service Structure

The service should have these components. If any are missing, create them.

### 2.1: Check Program.cs (Service Entry Point)

**File**: `src/guest_agent/NeuronGuest/Program.cs`

**Should contain**:
```csharp
using System;
using System.ServiceProcess;

class Program
{
    static void Main()
    {
        ServiceBase[] servicesToRun = new ServiceBase[]
        {
            new NeuronGuestService()
        };
        ServiceBase.Run(servicesToRun);
    }
}

public class NeuronGuestService : ServiceBase
{
    private BackgroundWorker worker;

    public NeuronGuestService()
    {
        ServiceName = "NeuronGuest";
        DisplayName = "NeuronOS Guest Agent";
        CanStop = true;
        CanShutdown = true;
        AutoLog = true;
    }

    protected override void OnStart(string[] args)
    {
        // Start background worker to listen for commands
        worker = new BackgroundWorker();
        worker.DoWork += Worker_DoWork;
        worker.RunWorkerAsync();
    }

    protected override void OnStop()
    {
        worker?.CancelAsync();
    }

    private void Worker_DoWork(object sender, DoWorkEventArgs e)
    {
        // Main service loop
        VirtioSerialService service = new VirtioSerialService();
        service.Start();
    }
}
```

**If Missing**: Create this file with the above content.

### 2.2: Check VirtioSerialService.cs (Communication Handler)

**File**: `src/guest_agent/NeuronGuest/Services/VirtioSerialService.cs`

**Should contain**:
```csharp
using System;
using System.IO.Ports;           // ← This now works after fix!
using System.Text;
using System.Text.Json;

public class VirtioSerialService
{
    private SerialPort _serialPort;
    private CommandHandler _commandHandler;

    public VirtioSerialService()
    {
        _commandHandler = new CommandHandler();
    }

    public void Start()
    {
        try
        {
            // COM3 is the virtio-serial device on Windows guests
            _serialPort = new SerialPort("COM3", 115200);
            _serialPort.Open();

            EventLog.WriteEntry("NeuronGuest", "VirtioSerial service started");

            // Main loop: read commands, execute, send results
            while (true)
            {
                if (_serialPort.BytesToRead > 0)
                {
                    string command = _serialPort.ReadLine();
                    string result = _commandHandler.Handle(command);
                    _serialPort.WriteLine(result);
                }
                System.Threading.Thread.Sleep(100);
            }
        }
        catch (Exception ex)
        {
            EventLog.WriteEntry("NeuronGuest", $"Error: {ex.Message}",
                EventLogEntryType.Error);
        }
        finally
        {
            _serialPort?.Close();
        }
    }
}
```

**If Missing**: Create this with the above content.

### 2.3: Check CommandHandler.cs (Command Router)

**File**: `src/guest_agent/NeuronGuest/Services/CommandHandler.cs`

**Should contain**:
```csharp
using System;
using System.Diagnostics;
using System.Text.Json;

public class CommandHandler
{
    public string Handle(string jsonCommand)
    {
        try
        {
            var cmd = JsonDocument.Parse(jsonCommand);
            var root = cmd.RootElement;

            string commandType = root.GetProperty("type").GetString();
            var data = root.GetProperty("data");

            string result = commandType switch
            {
                "ping" => HandlePing(),
                "get_info" => HandleGetInfo(),
                "set_resolution" => HandleSetResolution(data),
                "launch_app" => HandleLaunchApp(data),
                "clipboard_get" => HandleClipboardGet(),
                "clipboard_set" => HandleClipboardSet(data),
                "shutdown" => HandleShutdown(),
                _ => JsonResponse("error", $"Unknown command: {commandType}")
            };

            return result;
        }
        catch (Exception ex)
        {
            return JsonResponse("error", ex.Message);
        }
    }

    private string HandlePing()
    {
        return JsonResponse("pong", new { timestamp = DateTime.UtcNow });
    }

    private string HandleGetInfo()
    {
        var info = new
        {
            os_version = Environment.OSVersion.VersionString,
            processor_count = Environment.ProcessorCount,
            available_memory_mb = GC.GetTotalMemory(false) / 1024 / 1024
        };
        return JsonResponse("info", info);
    }

    private string HandleSetResolution(JsonElement data)
    {
        // TODO: Implement in Phase 1.5
        return JsonResponse("ok", "Resolution sync not yet implemented");
    }

    private string HandleLaunchApp(JsonElement data)
    {
        // TODO: Implement in Phase 1.5
        return JsonResponse("ok", "App launch not yet implemented");
    }

    private string HandleClipboardGet()
    {
        // TODO: Implement in Phase 1.5
        return JsonResponse("ok", "Clipboard sync not yet implemented");
    }

    private string HandleClipboardSet(JsonElement data)
    {
        // TODO: Implement in Phase 1.5
        return JsonResponse("ok", "Clipboard sync not yet implemented");
    }

    private string HandleShutdown()
    {
        return JsonResponse("ok", "Shutdown initiated");
    }

    private string JsonResponse(string status, object data)
    {
        var response = new { status = status, data = data };
        return JsonSerializer.Serialize(response);
    }
}
```

**If Missing**: Create this with the above content.

---

## Part 3: Build and Package

Once compilation succeeds, the service needs to be installable on Windows.

### 3.1: Create Installation Script

**File**: `src/guest_agent/NeuronGuest/install_service.bat`

```batch
@echo off
REM Installation script for NeuronGuest Windows Service

setlocal enabledelayedexpansion

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This script must be run as Administrator
    pause
    exit /b 1
)

REM Stop existing service if running
net stop "NeuronGuest" 2>nul

REM Uninstall existing service if present
sc delete "NeuronGuest" 2>nul

REM Get the path to the executable
set "SERVICE_PATH=%~dp0bin\Release\net7.0-windows\NeuronGuest.exe"

if not exist "%SERVICE_PATH%" (
    echo Error: NeuronGuest.exe not found at %SERVICE_PATH%
    echo Build the project first with: dotnet build -c Release
    pause
    exit /b 1
)

REM Install service
sc create "NeuronGuest" binPath= "%SERVICE_PATH%" start= auto displayName= "NeuronOS Guest Agent"
if %errorLevel% neq 0 (
    echo Failed to install service
    pause
    exit /b 1
)

REM Start the service
net start "NeuronGuest"
if %errorLevel% neq 0 (
    echo Failed to start service
    pause
    exit /b 1
)

echo NeuronGuest service installed and started successfully
pause
```

### 3.2: Build Release Version

```bash
# From src/guest_agent/NeuronGuest/

# Restore dependencies
dotnet restore

# Build Release version
dotnet build -c Release

# Output should be:
# bin/Release/net7.0-windows/NeuronGuest.exe
```

### 3.3: Test on Windows VM

1. Copy `NeuronGuest.exe` to Windows guest VM
2. Run `install_service.bat` as Administrator
3. Check Windows Event Viewer:
   - Application logs should show "NeuronGuest service started"
4. Verify service is running:
   ```powershell
   Get-Service NeuronGuest
   # Should show: Running
   ```

---

## Part 4: Integration Test (Host Side)

Once the guest agent is running, test that host-side communication works.

### 4.1: Test GuestClient Connection

**File**: `tests/test_guest_client.py` (create if doesn't exist)

```python
import socket
import json
import time
from src.vm_manager.core.guest_client import GuestClient

def test_guest_agent_connection(vm_name="TestVM"):
    """Test that we can communicate with guest agent."""

    # Create client
    client = GuestClient(vm_name)

    # Test 1: Ping guest
    try:
        response = client.send_command("ping", {})
        assert response["status"] == "pong"
        print("✓ Ping successful")
    except Exception as e:
        print(f"✗ Ping failed: {e}")
        return False

    # Test 2: Get guest info
    try:
        response = client.send_command("get_info", {})
        assert response["status"] == "info"
        assert "os_version" in response["data"]
        print(f"✓ Got guest info: {response['data']['os_version']}")
    except Exception as e:
        print(f"✗ Get info failed: {e}")
        return False

    return True

if __name__ == "__main__":
    # First, manually:
    # 1. Create and boot Windows VM named "TestVM"
    # 2. Install NeuronGuest service
    # 3. Run this test

    if test_guest_agent_connection():
        print("\nAll tests passed! Guest agent is working.")
    else:
        print("\nTests failed. Check guest agent service status.")
```

**How to Run**:
```bash
# Make sure Windows VM is running with guest agent installed
pytest tests/test_guest_client.py -v -s
```

---

## Verification Checklist

Before moving to Phase 1.2, verify ALL of these:

**Compilation & Build**:
- [ ] `dotnet build` succeeds with no errors
- [ ] No CS1069 "SerialPort not found" errors
- [ ] Release build creates `bin/Release/net7.0-windows/NeuronGuest.exe`
- [ ] File size > 1 MB (includes dependencies)

**Service Installation**:
- [ ] Service installs without errors: `sc query NeuronGuest` returns `RUNNING`
- [ ] Service auto-starts on Windows boot (check `net start NeuronGuest`)
- [ ] Windows Event Viewer shows "NeuronGuest service started" log

**Command Handling**:
- [ ] Ping command returns pong response
- [ ] Get info command returns OS version and hardware info
- [ ] Unknown commands return error response with message
- [ ] Service handles malformed JSON gracefully (no crash)

**Host-Side Integration**:
- [ ] GuestClient can instantiate: `client = GuestClient("vm_name")`
- [ ] GuestClient.send_command() successfully routes to guest
- [ ] Guest response received and parsed as JSON
- [ ] Error responses handled without crashing host

**Code Quality**:
- [ ] No TODO comments in VirtioSerialService.cs (except planned features)
- [ ] All exception handling catches and logs errors
- [ ] No hardcoded paths except device name (COM3)
- [ ] Command routing is complete and covers all command types

**Documentation**:
- [ ] README.md in guest_agent/ explains how to build and install
- [ ] Command protocol documented (request/response format)
- [ ] COM3 device name documented (configurable in future phases)

---

## Acceptance Criteria

✅ **Phase 1.1 Complete When**:

1. C# project compiles without errors
2. Service installs and runs on Windows
3. Service can be queried for info via host
4. `tests/test_guest_client.py` passes all tests
5. No crashes or exceptions in error paths

❌ **Phase 1.1 Fails If**:

- Compilation errors remain
- Service doesn't start
- Cannot receive responses from guest
- Unhandled exceptions in service

---

## Risks & Mitigations

### Risk 1: NuGet Package Version Incompatibility

**Issue**: System.IO.Ports 4.3.0 might not work on some .NET versions

**Mitigation**:
- If 4.3.0 fails, try 4.5.0
- Check Microsoft docs for your .NET version
- Alternative: Use `SerialPortManager` library (more abstracted)

### Risk 2: COM3 Device Not Available

**Issue**: Virtio-serial device might not be mapped to COM3

**Mitigation**:
- Check Windows Device Manager for actual COM port
- Document actual port in config
- Make port configurable in Phase 2

### Risk 3: Permissions Issues Installing Service

**Issue**: Script runs without admin privileges

**Mitigation**:
- Always run `install_service.bat` as Administrator
- Add UAC elevation check to batch file
- Document clearly in installation guide

### Risk 4: Port Already In Use

**Issue**: Another service using COM3

**Mitigation**:
- Check Device Manager: Ports (COM & LPT)
- Rename conflicting service or reassign port
- Document port allocation in config

---

## Next Steps

Once Phase 1.1 is complete:

1. **Phase 1.2** will implement VM deletion and settings dialog
2. **Phase 1.5** will add encryption and authentication to guest agent
3. **Phase 2.4** will enable Looking Glass to use guest agent for resolution sync

---

## Resources

- [System.IO.Ports Documentation](https://docs.microsoft.com/en-us/dotnet/api/system.io.ports.serialport)
- [.NET 7 Windows Forms](https://docs.microsoft.com/en-us/dotnet/desktop/winforms/overview)
- [Windows Services](https://docs.microsoft.com/en-us/windows/win32/services/services)
- [Virtio Serial Port (QEMU Docs)](https://wiki.qemu.org/Features/VirtioSerial)

---

## Questions?

If stuck:

1. Check the compilation error message carefully - usually indicates exact issue
2. Verify .NET SDK version: `dotnet --version`
3. Check Windows Event Viewer (Applications) for service errors
4. See ARCHITECTURE.md for guest agent design details

Good luck! 🚀
