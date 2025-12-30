using System.IO.Ports;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace NeuronGuest.Services;

/// <summary>
/// Handles communication with the NeuronOS host via virtio-serial.
///
/// On Windows, virtio-serial devices appear as COM ports.
/// The NeuronOS host creates a virtio-serial channel that Windows
/// sees as a serial port (typically COM3 or similar).
/// </summary>
public class VirtioSerialService : IVirtioSerialService, IDisposable
{
    private readonly ILogger<VirtioSerialService> _logger;
    private SerialPort? _serialPort;
    private readonly SemaphoreSlim _sendLock = new(1, 1);
    private readonly SemaphoreSlim _receiveLock = new(1, 1);

    // Virtio-serial typically appears as COMx on Windows
    // We scan common ports to find it
    private static readonly string[] PossiblePorts = { "COM3", "COM4", "COM5", "COM6" };

    // Protocol constants
    private const int BAUD_RATE = 115200;
    private const byte MESSAGE_START = 0x02; // STX
    private const byte MESSAGE_END = 0x03;   // ETX

    public bool IsConnected => _serialPort?.IsOpen ?? false;

    public VirtioSerialService(ILogger<VirtioSerialService> logger)
    {
        _logger = logger;
    }

    public async Task ConnectAsync(CancellationToken cancellationToken = default)
    {
        if (IsConnected)
            return;

        // Find the virtio-serial port
        var portName = await FindVirtioPortAsync(cancellationToken);

        if (string.IsNullOrEmpty(portName))
        {
            throw new InvalidOperationException(
                "Could not find virtio-serial port. Is the VM configured correctly?");
        }

        _serialPort = new SerialPort(portName, BAUD_RATE)
        {
            ReadTimeout = 1000,
            WriteTimeout = 1000,
            Encoding = Encoding.UTF8,
            NewLine = "\n"
        };

        try
        {
            _serialPort.Open();
            _logger.LogInformation("Connected to host via {Port}", portName);

            // Send hello message
            var hello = new GuestResponse
            {
                RequestId = "init",
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["agent_version"] = "1.0.0",
                    ["os"] = Environment.OSVersion.ToString(),
                    ["hostname"] = Environment.MachineName
                }
            };
            await SendResponseAsync(hello, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to open serial port {Port}", portName);
            _serialPort?.Dispose();
            _serialPort = null;
            throw;
        }
    }

    private async Task<string?> FindVirtioPortAsync(CancellationToken cancellationToken)
    {
        // Check available ports
        var availablePorts = SerialPort.GetPortNames();
        _logger.LogDebug("Available COM ports: {Ports}", string.Join(", ", availablePorts));

        foreach (var portName in PossiblePorts)
        {
            if (cancellationToken.IsCancellationRequested)
                break;

            if (!availablePorts.Contains(portName))
                continue;

            try
            {
                using var testPort = new SerialPort(portName, BAUD_RATE)
                {
                    ReadTimeout = 500,
                    WriteTimeout = 500
                };

                testPort.Open();

                // Try to identify as virtio-serial by sending probe
                // The host should respond to this
                testPort.Write("NEURON_PROBE\n");
                await Task.Delay(100, cancellationToken);

                if (testPort.BytesToRead > 0)
                {
                    var response = testPort.ReadLine();
                    if (response.Contains("NEURON_ACK"))
                    {
                        testPort.Close();
                        return portName;
                    }
                }

                testPort.Close();
            }
            catch
            {
                // Port busy or not suitable, try next
            }
        }

        // If no port identified, return first available that matches pattern
        foreach (var port in availablePorts)
        {
            if (PossiblePorts.Contains(port))
                return port;
        }

        return null;
    }

    public Task DisconnectAsync()
    {
        if (_serialPort != null)
        {
            if (_serialPort.IsOpen)
                _serialPort.Close();
            _serialPort.Dispose();
            _serialPort = null;
        }
        return Task.CompletedTask;
    }

    public async Task SendHeartbeatAsync(CancellationToken cancellationToken = default)
    {
        if (!IsConnected)
            return;

        var heartbeat = new GuestResponse
        {
            RequestId = "heartbeat",
            Success = true,
            Data = new Dictionary<string, object>
            {
                ["uptime_seconds"] = Environment.TickCount64 / 1000,
                ["memory_mb"] = GC.GetTotalMemory(false) / (1024 * 1024)
            }
        };

        await SendResponseAsync(heartbeat, cancellationToken);
    }

    public async Task<GuestMessage?> ReceiveMessageAsync(CancellationToken cancellationToken = default)
    {
        if (!IsConnected || _serialPort == null)
            return null;

        await _receiveLock.WaitAsync(cancellationToken);
        try
        {
            if (_serialPort.BytesToRead == 0)
                return null;

            var buffer = new StringBuilder();
            var inMessage = false;

            while (_serialPort.BytesToRead > 0)
            {
                var b = _serialPort.ReadByte();

                if (b == MESSAGE_START)
                {
                    inMessage = true;
                    buffer.Clear();
                }
                else if (b == MESSAGE_END && inMessage)
                {
                    // Complete message received
                    var json = buffer.ToString();
                    return JsonSerializer.Deserialize<GuestMessage>(json);
                }
                else if (inMessage)
                {
                    buffer.Append((char)b);
                }
            }

            return null;
        }
        catch (TimeoutException)
        {
            return null;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error receiving message");
            return null;
        }
        finally
        {
            _receiveLock.Release();
        }
    }

    public async Task SendResponseAsync(GuestResponse response, CancellationToken cancellationToken = default)
    {
        if (!IsConnected || _serialPort == null)
            return;

        await _sendLock.WaitAsync(cancellationToken);
        try
        {
            var json = JsonSerializer.Serialize(response);
            var data = new byte[json.Length + 2];
            data[0] = MESSAGE_START;
            Encoding.UTF8.GetBytes(json, 0, json.Length, data, 1);
            data[^1] = MESSAGE_END;

            _serialPort.Write(data, 0, data.Length);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error sending response");
        }
        finally
        {
            _sendLock.Release();
        }
    }

    public void Dispose()
    {
        _serialPort?.Dispose();
        _sendLock.Dispose();
        _receiveLock.Dispose();
    }
}
