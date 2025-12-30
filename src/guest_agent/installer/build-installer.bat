@echo off
REM NeuronGuest Installer Build Script
REM Builds the Windows installer package
REM
REM Prerequisites:
REM   - Visual Studio 2022 or .NET 8 SDK
REM   - Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
REM   - Looking Glass Host binary
REM   - VirtIO drivers

setlocal EnableDelayedExpansion

echo ========================================
echo NeuronGuest Installer Build Script
echo ========================================
echo.

REM Configuration
set BUILD_CONFIG=Release
set RUNTIME=win-x64
set OUTPUT_DIR=%~dp0output

REM Check for required tools
where dotnet >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: .NET SDK not found. Please install .NET 8 SDK.
    exit /b 1
)

where iscc >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo WARNING: Inno Setup Compiler (iscc) not in PATH.
    echo Please add Inno Setup to PATH or run from Inno Setup directory.
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else (
    set ISCC=iscc
)

REM Step 1: Build NeuronGuest application
echo [1/4] Building NeuronGuest application...
cd /d %~dp0..
dotnet publish NeuronGuest\NeuronGuest.csproj -c %BUILD_CONFIG% -r %RUNTIME% --self-contained true -o "%~dp0bin"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Build failed!
    exit /b 1
)
echo Build complete.
echo.

REM Step 2: Check for dependencies
echo [2/4] Checking dependencies...

if not exist "%~dp0deps\looking-glass-host.exe" (
    echo WARNING: Looking Glass Host not found at deps\looking-glass-host.exe
    echo Download from: https://looking-glass.io/downloads
    echo.
)

if not exist "%~dp0deps\virtio" (
    echo WARNING: VirtIO drivers not found at deps\virtio\
    echo Download from: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/
    echo.
)

REM Step 3: Create asset directories if missing
echo [3/4] Preparing assets...
if not exist "%~dp0assets" mkdir "%~dp0assets"
if not exist "%~dp0docs" mkdir "%~dp0docs"
if not exist "%~dp0deps" mkdir "%~dp0deps"
if not exist "%~dp0deps\virtio" mkdir "%~dp0deps\virtio"

REM Create placeholder files if missing
if not exist "%~dp0assets\neuronguest.ico" (
    echo Creating placeholder icon...
    REM Would need actual icon file
)

if not exist "%~dp0docs\README.txt" (
    echo Creating README...
    (
        echo NeuronGuest - NeuronOS Guest Agent
        echo ==================================
        echo.
        echo This agent enables seamless communication between your Windows VM
        echo and the NeuronOS host system.
        echo.
        echo Features:
        echo   - Host-to-guest command execution
        echo   - Window management and automation
        echo   - USB device coordination
        echo   - Looking Glass integration
        echo.
        echo For more information, visit: https://neuronos.org
    ) > "%~dp0docs\README.txt"
)

if not exist "%~dp0docs\LICENSE.txt" (
    echo Creating LICENSE...
    (
        echo MIT License
        echo.
        echo Copyright (c) 2025 NeuronOS
        echo.
        echo Permission is hereby granted, free of charge, to any person obtaining a copy
        echo of this software and associated documentation files, to use, copy, modify,
        echo merge, publish, distribute, sublicense, and/or sell copies of the Software.
    ) > "%~dp0docs\LICENSE.txt"
)

REM Step 4: Build installer
echo [4/4] Building installer...
%ISCC% /O"%OUTPUT_DIR%" "%~dp0neuron-guest-setup.iss"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Installer build failed!
    exit /b 1
)

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Installer: %OUTPUT_DIR%\NeuronGuest-Setup-*.exe
echo.

endlocal
