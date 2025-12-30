; NeuronGuest Windows Installer
; Inno Setup Script for NeuronOS Guest Agent
;
; This installer packages:
; - NeuronGuest service (background agent for host communication)
; - Looking Glass Host (for low-latency display)
; - VirtIO drivers (for optimal performance)
; - System tray application
;
; Build with: ISCC neuron-guest-setup.iss

#define MyAppName "NeuronGuest"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "NeuronOS"
#define MyAppURL "https://neuronos.org"
#define MyAppExeName "NeuronGuest.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{7E2B8A3F-4C6D-4E8F-9A1B-3C5D7E9F0A2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output settings
OutputDir=output
OutputBaseFilename=NeuronGuest-Setup-{#MyAppVersion}
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Require admin for service installation
PrivilegesRequired=admin
; Windows version requirements
MinVersion=10.0.17763
; Styling
SetupIconFile=assets\neuronguest.ico
WizardStyle=modern
WizardImageFile=assets\wizard-large.bmp
WizardSmallImageFile=assets\wizard-small.bmp
; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation (recommended)"
Name: "minimal"; Description: "Minimal installation (agent only)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "core"; Description: "NeuronGuest Agent"; Types: full minimal custom; Flags: fixed
Name: "lookingglass"; Description: "Looking Glass Host"; Types: full custom
Name: "virtio"; Description: "VirtIO Drivers"; Types: full custom
Name: "systray"; Description: "System Tray Application"; Types: full custom

[Tasks]
Name: "autostart"; Description: "Start automatically with Windows"; GroupDescription: "Startup:"; Components: core
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "installservice"; Description: "Install as Windows Service"; GroupDescription: "Service:"; Components: core; Flags: checkedonce

[Files]
; Core agent files
Source: "bin\NeuronGuest.exe"; DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "bin\NeuronGuest.dll"; DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "bin\appsettings.json"; DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "bin\*.dll"; DestDir: "{app}"; Components: core; Flags: ignoreversion

; System tray application
Source: "bin\NeuronGuestTray.exe"; DestDir: "{app}"; Components: systray; Flags: ignoreversion

; Looking Glass Host
Source: "deps\looking-glass-host.exe"; DestDir: "{app}"; Components: lookingglass; Flags: ignoreversion

; VirtIO Drivers
Source: "deps\virtio\*"; DestDir: "{app}\drivers\virtio"; Components: virtio; Flags: ignoreversion recursesubdirs

; Assets
Source: "assets\neuronguest.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\logo.png"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "docs\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "docs\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; System tray startup (if selected)
Name: "{userstartup}\NeuronGuest Tray"; Filename: "{app}\NeuronGuestTray.exe"; Tasks: autostart; Components: systray

[Registry]
; Register application
Root: HKLM; Subkey: "Software\NeuronOS\NeuronGuest"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\NeuronOS\NeuronGuest"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

; Looking Glass settings
Root: HKLM; Subkey: "Software\NeuronOS\NeuronGuest\LookingGlass"; ValueType: dword; ValueName: "Enabled"; ValueData: "1"; Components: lookingglass

[Run]
; Install VirtIO drivers
Filename: "{cmd}"; Parameters: "/c pnputil /add-driver ""{app}\drivers\virtio\*.inf"" /install"; StatusMsg: "Installing VirtIO drivers..."; Components: virtio; Flags: runhidden waituntilterminated

; Install Windows Service
Filename: "{app}\{#MyAppExeName}"; Parameters: "install"; StatusMsg: "Installing NeuronGuest service..."; Tasks: installservice; Flags: runhidden waituntilterminated

; Start service
Filename: "sc.exe"; Parameters: "start NeuronGuest"; StatusMsg: "Starting NeuronGuest service..."; Tasks: installservice; Flags: runhidden waituntilterminated

; Launch system tray (after install)
Filename: "{app}\NeuronGuestTray.exe"; Description: "Launch NeuronGuest"; Components: systray; Flags: nowait postinstall skipifsilent

; Schedule Looking Glass Host to run at startup with SYSTEM privileges
Filename: "schtasks.exe"; Parameters: "/create /tn ""NeuronOS\LookingGlassHost"" /tr ""{app}\looking-glass-host.exe"" /sc onlogon /rl highest /f"; StatusMsg: "Configuring Looking Glass..."; Components: lookingglass; Flags: runhidden waituntilterminated

[UninstallRun]
; Stop and remove service
Filename: "sc.exe"; Parameters: "stop NeuronGuest"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "uninstall"; Flags: runhidden waituntilterminated

; Remove Looking Glass scheduled task
Filename: "schtasks.exe"; Parameters: "/delete /tn ""NeuronOS\LookingGlassHost"" /f"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"

[Code]
var
  DependenciesPage: TInputOptionWizardPage;

// Check if .NET 8 Runtime is installed
function IsDotNet8Installed: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('dotnet', '--list-runtimes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  // More thorough check would parse output, but this is a basic check
end;

// Check if VirtIO serial driver is present
function IsVirtIOSerialPresent: Boolean;
begin
  Result := FileExists('C:\Windows\System32\drivers\vioser.sys');
end;

procedure InitializeWizard;
begin
  // Add custom dependencies page
  DependenciesPage := CreateInputOptionPage(wpSelectComponents,
    'Dependencies Check',
    'Checking required dependencies',
    'The installer will check and install required dependencies:',
    False, False);

  DependenciesPage.Add('.NET 8 Runtime');
  DependenciesPage.Add('VirtIO Serial Driver');
  DependenciesPage.Add('IVSHMEM Driver (for Looking Glass)');

  // Check current state
  DependenciesPage.Values[0] := IsDotNet8Installed;
  DependenciesPage.Values[1] := IsVirtIOSerialPresent;
  DependenciesPage.Values[2] := FileExists('C:\Windows\System32\drivers\ivshmem.sys');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  // On dependencies page, offer to install missing deps
  if CurPageID = DependenciesPage.ID then
  begin
    if not DependenciesPage.Values[0] then
    begin
      if MsgBox('.NET 8 Runtime is required. Download and install it now?',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        // Open .NET download page
        ShellExec('open', 'https://dotnet.microsoft.com/download/dotnet/8.0', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
        MsgBox('Please install .NET 8 Runtime and restart the installer.', mbInformation, MB_OK);
        Result := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Create firewall rule for Looking Glass (if component selected)
    if WizardIsComponentSelected('lookingglass') then
    begin
      Exec('netsh', 'advfirewall firewall add rule name="Looking Glass Host" dir=in action=allow program="' + ExpandConstant('{app}') + '\looking-glass-host.exe" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // Configure IVSHMEM if present
    if FileExists('C:\Windows\System32\drivers\ivshmem.sys') then
    begin
      // IVSHMEM configuration would go here
    end;
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  // Stop service before uninstall
  Exec('sc.exe', 'stop NeuronGuest', '', SW_HIDE, ewWaitUntilTerminated, Result);
end;
