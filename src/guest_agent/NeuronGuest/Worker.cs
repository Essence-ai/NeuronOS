using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using NeuronGuest.Services;

namespace NeuronGuest;

/// <summary>
/// Main background worker that coordinates guest agent operations.
/// </summary>
public class Worker : BackgroundService
{
    private readonly ILogger<Worker> _logger;
    private readonly IVirtioSerialService _virtioSerial;
    private readonly ICommandHandler _commandHandler;

    public Worker(
        ILogger<Worker> logger,
        IVirtioSerialService virtioSerial,
        ICommandHandler commandHandler)
    {
        _logger = logger;
        _virtioSerial = virtioSerial;
        _commandHandler = commandHandler;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("NeuronGuest Agent starting...");

        // Try to connect to host via virtio-serial
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (!_virtioSerial.IsConnected)
                {
                    _logger.LogInformation("Attempting to connect to host...");
                    await _virtioSerial.ConnectAsync(stoppingToken);
                }

                // Send heartbeat
                await _virtioSerial.SendHeartbeatAsync(stoppingToken);

                // Process incoming commands
                var message = await _virtioSerial.ReceiveMessageAsync(stoppingToken);
                if (message != null)
                {
                    _logger.LogDebug("Received command: {Command}", message.Command);
                    var response = await _commandHandler.HandleAsync(message, stoppingToken);
                    await _virtioSerial.SendResponseAsync(response, stoppingToken);
                }

                await Task.Delay(100, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error in main loop");
                await Task.Delay(5000, stoppingToken); // Wait before retry
            }
        }

        _logger.LogInformation("NeuronGuest Agent stopped.");
    }
}
