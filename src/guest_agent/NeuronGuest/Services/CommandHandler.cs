using Microsoft.Extensions.Logging;

namespace NeuronGuest.Services;

/// <summary>
/// Interface for handling commands from the NeuronOS host.
/// </summary>
public interface ICommandHandler
{
    Task<GuestResponse> HandleAsync(GuestMessage message, CancellationToken cancellationToken = default);
}

/// <summary>
/// Handles commands received from the NeuronOS host.
/// </summary>
public class CommandHandler : ICommandHandler
{
    private readonly ILogger<CommandHandler> _logger;
    private readonly IWindowManager _windowManager;

    public CommandHandler(ILogger<CommandHandler> logger, IWindowManager windowManager)
    {
        _logger = logger;
        _windowManager = windowManager;
    }

    public async Task<GuestResponse> HandleAsync(GuestMessage message, CancellationToken cancellationToken = default)
    {
        _logger.LogDebug("Handling command: {Command}", message.Command);

        try
        {
            return message.Command.ToLowerInvariant() switch
            {
                "launch" => await HandleLaunchAsync(message, cancellationToken),
                "close" => await HandleCloseAsync(message, cancellationToken),
                "list_windows" => await HandleListWindowsAsync(message, cancellationToken),
                "focus" => await HandleFocusAsync(message, cancellationToken),
                "minimize" => await HandleMinimizeAsync(message, cancellationToken),
                "maximize" => await HandleMaximizeAsync(message, cancellationToken),
                "get_info" => await HandleGetInfoAsync(message, cancellationToken),
                "ping" => HandlePing(message),
                // Phase 3: Resolution and clipboard sync
                "set_resolution" => await HandleSetResolutionAsync(message, cancellationToken),
                "clipboard_get" => HandleClipboardGet(message),
                "clipboard_set" => HandleClipboardSet(message),
                "screenshot" => await HandleScreenshotAsync(message, cancellationToken),
                _ => new GuestResponse
                {
                    RequestId = message.Id,
                    Success = false,
                    Error = $"Unknown command: {message.Command}"
                }
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error handling command {Command}", message.Command);
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = ex.Message
            };
        }
    }

    private GuestResponse HandlePing(GuestMessage message)
    {
        return new GuestResponse
        {
            RequestId = message.Id,
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["pong"] = DateTime.UtcNow.ToString("O")
            }
        };
    }

    private async Task<GuestResponse> HandleLaunchAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var path = message.Parameters?.GetValueOrDefault("path")?.ToString();
        var args = message.Parameters?.GetValueOrDefault("args")?.ToString();

        if (string.IsNullOrEmpty(path))
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing 'path' parameter"
            };
        }

        var windowInfo = await _windowManager.LaunchApplicationAsync(path, args, cancellationToken);

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = windowInfo != null,
            Data = windowInfo != null
                ? new Dictionary<string, object>
                {
                    ["process_id"] = windowInfo.ProcessId,
                    ["window_handle"] = windowInfo.Handle.ToInt64(),
                    ["title"] = windowInfo.Title
                }
                : null,
            Error = windowInfo == null ? "Failed to launch application" : null
        };
    }

    private async Task<GuestResponse> HandleCloseAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var handleStr = message.Parameters?.GetValueOrDefault("handle")?.ToString();
        var processIdStr = message.Parameters?.GetValueOrDefault("process_id")?.ToString();

        if (!string.IsNullOrEmpty(handleStr) && long.TryParse(handleStr, out var handle))
        {
            var success = await _windowManager.CloseWindowAsync(new IntPtr(handle), cancellationToken);
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = success,
                Error = success ? null : "Failed to close window"
            };
        }

        if (!string.IsNullOrEmpty(processIdStr) && int.TryParse(processIdStr, out var processId))
        {
            var success = await _windowManager.CloseProcessAsync(processId, cancellationToken);
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = success,
                Error = success ? null : "Failed to close process"
            };
        }

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = false,
            Error = "Missing 'handle' or 'process_id' parameter"
        };
    }

    private async Task<GuestResponse> HandleListWindowsAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var windows = await _windowManager.GetAllWindowsAsync(cancellationToken);

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["windows"] = windows.Select(w => new Dictionary<string, object>
                {
                    ["handle"] = w.Handle.ToInt64(),
                    ["title"] = w.Title,
                    ["process_id"] = w.ProcessId,
                    ["process_name"] = w.ProcessName,
                    ["is_visible"] = w.IsVisible,
                    ["x"] = w.X,
                    ["y"] = w.Y,
                    ["width"] = w.Width,
                    ["height"] = w.Height
                }).ToList()
            }
        };
    }

    private async Task<GuestResponse> HandleFocusAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var handleStr = message.Parameters?.GetValueOrDefault("handle")?.ToString();

        if (string.IsNullOrEmpty(handleStr) || !long.TryParse(handleStr, out var handle))
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing or invalid 'handle' parameter"
            };
        }

        var success = await _windowManager.FocusWindowAsync(new IntPtr(handle), cancellationToken);

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = success
        };
    }

    private async Task<GuestResponse> HandleMinimizeAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var handleStr = message.Parameters?.GetValueOrDefault("handle")?.ToString();

        if (string.IsNullOrEmpty(handleStr) || !long.TryParse(handleStr, out var handle))
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing or invalid 'handle' parameter"
            };
        }

        var success = await _windowManager.MinimizeWindowAsync(new IntPtr(handle), cancellationToken);

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = success
        };
    }

    private async Task<GuestResponse> HandleMaximizeAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var handleStr = message.Parameters?.GetValueOrDefault("handle")?.ToString();

        if (string.IsNullOrEmpty(handleStr) || !long.TryParse(handleStr, out var handle))
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing or invalid 'handle' parameter"
            };
        }

        var success = await _windowManager.MaximizeWindowAsync(new IntPtr(handle), cancellationToken);

        return new GuestResponse
        {
            RequestId = message.Id,
            Success = success
        };
    }

    private Task<GuestResponse> HandleGetInfoAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        return Task.FromResult(new GuestResponse
        {
            RequestId = message.Id,
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["hostname"] = Environment.MachineName,
                ["os_version"] = Environment.OSVersion.ToString(),
                ["processor_count"] = Environment.ProcessorCount,
                ["working_set_mb"] = Environment.WorkingSet / (1024 * 1024),
                ["agent_version"] = "1.0.0",
                ["dotnet_version"] = Environment.Version.ToString()
            }
        });
    }

    // Phase 3: Resolution sync for Looking Glass
    private async Task<GuestResponse> HandleSetResolutionAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        var widthStr = message.Parameters?.GetValueOrDefault("width")?.ToString();
        var heightStr = message.Parameters?.GetValueOrDefault("height")?.ToString();

        if (string.IsNullOrEmpty(widthStr) || string.IsNullOrEmpty(heightStr) ||
            !int.TryParse(widthStr, out var width) || !int.TryParse(heightStr, out var height))
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing or invalid 'width' or 'height' parameter"
            };
        }

        try
        {
            // Use Windows Display API to set resolution
            var success = await Task.Run(() => SetDisplayResolution(width, height), cancellationToken);
            
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = success,
                Data = success ? new Dictionary<string, object>
                {
                    ["width"] = width,
                    ["height"] = height
                } : null,
                Error = success ? null : "Failed to set display resolution"
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to set resolution to {Width}x{Height}", width, height);
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = ex.Message
            };
        }
    }

    private bool SetDisplayResolution(int width, int height)
    {
        // P/Invoke for ChangeDisplaySettingsEx
        var devMode = new DEVMODE();
        devMode.dmSize = (short)System.Runtime.InteropServices.Marshal.SizeOf(devMode);
        devMode.dmPelsWidth = width;
        devMode.dmPelsHeight = height;
        devMode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;

        int result = ChangeDisplaySettingsEx(null, ref devMode, IntPtr.Zero, CDS_UPDATEREGISTRY, IntPtr.Zero);
        return result == DISP_CHANGE_SUCCESSFUL;
    }

    // Phase 3: Clipboard synchronization
    private GuestResponse HandleClipboardGet(GuestMessage message)
    {
        try
        {
            string? text = null;
            
            // Must run on STA thread for clipboard access
            var thread = new System.Threading.Thread(() =>
            {
                if (System.Windows.Forms.Clipboard.ContainsText())
                {
                    text = System.Windows.Forms.Clipboard.GetText();
                }
            });
            thread.SetApartmentState(System.Threading.ApartmentState.STA);
            thread.Start();
            thread.Join(1000);

            return new GuestResponse
            {
                RequestId = message.Id,
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["text"] = text ?? ""
                }
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get clipboard");
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = ex.Message
            };
        }
    }

    private GuestResponse HandleClipboardSet(GuestMessage message)
    {
        var text = message.Parameters?.GetValueOrDefault("text")?.ToString();

        if (text == null)
        {
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = "Missing 'text' parameter"
            };
        }

        try
        {
            // Must run on STA thread for clipboard access
            var thread = new System.Threading.Thread(() =>
            {
                System.Windows.Forms.Clipboard.SetText(text);
            });
            thread.SetApartmentState(System.Threading.ApartmentState.STA);
            thread.Start();
            thread.Join(1000);

            return new GuestResponse
            {
                RequestId = message.Id,
                Success = true
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to set clipboard");
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = ex.Message
            };
        }
    }

    // Phase 3: Screenshot capture
    private async Task<GuestResponse> HandleScreenshotAsync(GuestMessage message, CancellationToken cancellationToken)
    {
        try
        {
            var imageBase64 = await Task.Run(() =>
            {
                // Capture primary screen
                var bounds = System.Windows.Forms.Screen.PrimaryScreen!.Bounds;
                using var bitmap = new System.Drawing.Bitmap(bounds.Width, bounds.Height);
                using var graphics = System.Drawing.Graphics.FromImage(bitmap);
                graphics.CopyFromScreen(bounds.Location, System.Drawing.Point.Empty, bounds.Size);

                using var ms = new System.IO.MemoryStream();
                bitmap.Save(ms, System.Drawing.Imaging.ImageFormat.Png);
                return Convert.ToBase64String(ms.ToArray());
            }, cancellationToken);

            return new GuestResponse
            {
                RequestId = message.Id,
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["image_base64"] = imageBase64
                }
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to capture screenshot");
            return new GuestResponse
            {
                RequestId = message.Id,
                Success = false,
                Error = ex.Message
            };
        }
    }

    // P/Invoke declarations for display settings
    private const int DM_PELSWIDTH = 0x80000;
    private const int DM_PELSHEIGHT = 0x100000;
    private const int CDS_UPDATEREGISTRY = 0x01;
    private const int DISP_CHANGE_SUCCESSFUL = 0;

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct DEVMODE
    {
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 32)]
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
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern int ChangeDisplaySettingsEx(
        string? lpszDeviceName,
        ref DEVMODE lpDevMode,
        IntPtr hwnd,
        int dwflags,
        IntPtr lParam);
}
