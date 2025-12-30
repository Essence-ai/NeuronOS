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
}
