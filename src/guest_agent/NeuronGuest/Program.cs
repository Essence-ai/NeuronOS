using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using NeuronGuest.Services;

namespace NeuronGuest;

/// <summary>
/// NeuronGuest - Windows Guest Agent for NeuronOS
///
/// This agent runs inside Windows VMs and communicates with the NeuronOS host
/// via virtio-serial. It handles:
/// - Application launching and window management
/// - Clipboard synchronization
/// - File transfer
/// - System information reporting
/// </summary>
public class Program
{
    public static void Main(string[] args)
    {
        var builder = Host.CreateApplicationBuilder(args);

        // Register services
        builder.Services.AddSingleton<IVirtioSerialService, VirtioSerialService>();
        builder.Services.AddSingleton<IWindowManager, WindowManager>();
        builder.Services.AddSingleton<ICommandHandler, CommandHandler>();

        // Add the main worker service
        builder.Services.AddHostedService<Worker>();

        // Configure as Windows Service when appropriate
        builder.Services.AddWindowsService(options =>
        {
            options.ServiceName = "NeuronGuest";
        });

        var host = builder.Build();
        host.Run();
    }
}
