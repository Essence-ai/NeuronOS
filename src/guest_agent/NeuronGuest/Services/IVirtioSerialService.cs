namespace NeuronGuest.Services;

/// <summary>
/// Interface for virtio-serial communication with the NeuronOS host.
/// </summary>
public interface IVirtioSerialService
{
    bool IsConnected { get; }
    Task ConnectAsync(CancellationToken cancellationToken = default);
    Task DisconnectAsync();
    Task SendHeartbeatAsync(CancellationToken cancellationToken = default);
    Task<GuestMessage?> ReceiveMessageAsync(CancellationToken cancellationToken = default);
    Task SendResponseAsync(GuestResponse response, CancellationToken cancellationToken = default);
}

/// <summary>
/// Message received from the NeuronOS host.
/// </summary>
public class GuestMessage
{
    public string Id { get; set; } = string.Empty;
    public string Command { get; set; } = string.Empty;
    public Dictionary<string, object>? Parameters { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
}

/// <summary>
/// Response sent back to the NeuronOS host.
/// </summary>
public class GuestResponse
{
    public string RequestId { get; set; } = string.Empty;
    public bool Success { get; set; }
    public string? Error { get; set; }
    public Dictionary<string, object>? Data { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
}
