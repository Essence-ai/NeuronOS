using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Extensions.Logging;

namespace NeuronGuest.Services;

/// <summary>
/// Information about a window.
/// </summary>
public class WindowInfo
{
    public IntPtr Handle { get; set; }
    public string Title { get; set; } = string.Empty;
    public int ProcessId { get; set; }
    public string ProcessName { get; set; } = string.Empty;
    public bool IsVisible { get; set; }
    public int X { get; set; }
    public int Y { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }
}

/// <summary>
/// Interface for window management operations.
/// </summary>
public interface IWindowManager
{
    Task<WindowInfo?> LaunchApplicationAsync(string path, string? args = null, CancellationToken cancellationToken = default);
    Task<bool> CloseWindowAsync(IntPtr handle, CancellationToken cancellationToken = default);
    Task<bool> CloseProcessAsync(int processId, CancellationToken cancellationToken = default);
    Task<List<WindowInfo>> GetAllWindowsAsync(CancellationToken cancellationToken = default);
    Task<bool> FocusWindowAsync(IntPtr handle, CancellationToken cancellationToken = default);
    Task<bool> MinimizeWindowAsync(IntPtr handle, CancellationToken cancellationToken = default);
    Task<bool> MaximizeWindowAsync(IntPtr handle, CancellationToken cancellationToken = default);
}

/// <summary>
/// Manages windows in the Windows VM using Win32 APIs.
/// </summary>
public class WindowManager : IWindowManager
{
    private readonly ILogger<WindowManager> _logger;

    public WindowManager(ILogger<WindowManager> logger)
    {
        _logger = logger;
    }

    #region Win32 Imports

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    private const int SW_MINIMIZE = 6;
    private const int SW_MAXIMIZE = 3;
    private const int SW_RESTORE = 9;
    private const uint WM_CLOSE = 0x0010;

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    #endregion

    public async Task<WindowInfo?> LaunchApplicationAsync(string path, string? args = null, CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Launching application: {Path} {Args}", path, args);

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = path,
                Arguments = args ?? string.Empty,
                UseShellExecute = true
            };

            var process = Process.Start(startInfo);
            if (process == null)
            {
                _logger.LogError("Failed to start process for {Path}", path);
                return null;
            }

            // Wait for main window to appear
            for (int i = 0; i < 50; i++) // Wait up to 5 seconds
            {
                if (cancellationToken.IsCancellationRequested)
                    break;

                process.Refresh();
                if (process.MainWindowHandle != IntPtr.Zero)
                {
                    return CreateWindowInfo(process.MainWindowHandle);
                }

                await Task.Delay(100, cancellationToken);
            }

            // Return process info even without window
            return new WindowInfo
            {
                Handle = process.MainWindowHandle,
                ProcessId = process.Id,
                ProcessName = process.ProcessName,
                Title = process.MainWindowTitle
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error launching application {Path}", path);
            return null;
        }
    }

    public Task<bool> CloseWindowAsync(IntPtr handle, CancellationToken cancellationToken = default)
    {
        try
        {
            SendMessage(handle, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
            return Task.FromResult(true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error closing window {Handle}", handle);
            return Task.FromResult(false);
        }
    }

    public Task<bool> CloseProcessAsync(int processId, CancellationToken cancellationToken = default)
    {
        try
        {
            var process = Process.GetProcessById(processId);
            process.CloseMainWindow();

            // Give it a moment to close gracefully
            if (!process.WaitForExit(3000))
            {
                process.Kill();
            }

            return Task.FromResult(true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error closing process {ProcessId}", processId);
            return Task.FromResult(false);
        }
    }

    public Task<List<WindowInfo>> GetAllWindowsAsync(CancellationToken cancellationToken = default)
    {
        var windows = new List<WindowInfo>();

        EnumWindows((hWnd, lParam) =>
        {
            if (!IsWindowVisible(hWnd))
                return true;

            var info = CreateWindowInfo(hWnd);
            if (!string.IsNullOrEmpty(info.Title))
            {
                windows.Add(info);
            }

            return true;
        }, IntPtr.Zero);

        return Task.FromResult(windows);
    }

    public Task<bool> FocusWindowAsync(IntPtr handle, CancellationToken cancellationToken = default)
    {
        try
        {
            ShowWindow(handle, SW_RESTORE);
            var result = SetForegroundWindow(handle);
            return Task.FromResult(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error focusing window {Handle}", handle);
            return Task.FromResult(false);
        }
    }

    public Task<bool> MinimizeWindowAsync(IntPtr handle, CancellationToken cancellationToken = default)
    {
        try
        {
            var result = ShowWindow(handle, SW_MINIMIZE);
            return Task.FromResult(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error minimizing window {Handle}", handle);
            return Task.FromResult(false);
        }
    }

    public Task<bool> MaximizeWindowAsync(IntPtr handle, CancellationToken cancellationToken = default)
    {
        try
        {
            var result = ShowWindow(handle, SW_MAXIMIZE);
            return Task.FromResult(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error maximizing window {Handle}", handle);
            return Task.FromResult(false);
        }
    }

    private WindowInfo CreateWindowInfo(IntPtr hWnd)
    {
        var info = new WindowInfo
        {
            Handle = hWnd,
            IsVisible = IsWindowVisible(hWnd)
        };

        // Get title
        var titleLength = GetWindowTextLength(hWnd);
        if (titleLength > 0)
        {
            var titleBuffer = new StringBuilder(titleLength + 1);
            GetWindowText(hWnd, titleBuffer, titleBuffer.Capacity);
            info.Title = titleBuffer.ToString();
        }

        // Get process info
        GetWindowThreadProcessId(hWnd, out var processId);
        info.ProcessId = processId;

        try
        {
            var process = Process.GetProcessById(processId);
            info.ProcessName = process.ProcessName;
        }
        catch
        {
            info.ProcessName = "Unknown";
        }

        // Get window rect
        if (GetWindowRect(hWnd, out var rect))
        {
            info.X = rect.Left;
            info.Y = rect.Top;
            info.Width = rect.Right - rect.Left;
            info.Height = rect.Bottom - rect.Top;
        }

        return info;
    }
}
