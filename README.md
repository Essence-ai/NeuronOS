# NeuronOS

A consumer-grade Linux distribution with seamless Windows & macOS software compatibility.

## Overview

NeuronOS is designed to eliminate the complexity barrier preventing mainstream Linux adoption by:

- **Native Linux Experience** for 80% of use cases
- **Wine/Proton Compatibility** for Windows apps and games
- **GPU Passthrough VMs** for professional software (Adobe, AutoCAD)
- **One-click Installation** - no terminal required

## Project Status

**Current Phase:** Phase 0 - Proof of Concept
**Timeline to MVP:** 6-9 months

## Repository Structure

```
neuron-os/
├── src/                    # Python source code
│   ├── hardware_detect/    # GPU/IOMMU detection
│   ├── vm_manager/         # NeuronVM Manager GUI
│   └── store/              # NeuronStore app marketplace
├── iso-profile/            # Archiso custom profile
├── scripts/                # Build and utility scripts
├── templates/              # VM XML templates
├── data/                   # Static data (app catalog, etc.)
├── docs/                   # Documentation
└── tests/                  # Test suite
```

## Quick Start (Development)

### Prerequisites

- Arch Linux or derivative
- Python 3.11+
- Hardware with IOMMU support (Intel VT-d or AMD-Vi)
- Two GPUs (integrated + discrete)

### Setup

```bash
# Clone repository
git clone https://github.com/neuronos/neuron-os.git
cd neuron-os

# Install dependencies
sudo pacman -S python python-pip archiso qemu-full libvirt virt-manager
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Build ISO (requires root)
sudo make iso
```

## Development Phases

| Phase | Duration | Description |
|-------|----------|-------------|
| **Phase 0** | 2 weeks | Manual GPU passthrough PoC |
| **Phase 1** | 6 weeks | Auto-configuring ISO |
| **Phase 2** | 8 weeks | NeuronVM Manager GUI |
| **Phase 3** | 8 weeks | NeuronStore + System Polish |
| **Phase 4** | 8 weeks | Enterprise Features |
| **Phase 5** | 8 weeks | Testing & Launch |

## Documentation

- [Implementation Guide](IMPLEMENTATION_GUIDE.md) - Start here for development
- [NeuronOS Report](NeuronOS_Report.md) - Technical feasibility analysis
- [Phase Guides](dev_guide_phase_0.md) - Detailed development guides

## Hardware Requirements

### Minimum (Light Users)
- CPU: Intel Core i3-10100 / AMD Ryzen 5 3600
- RAM: 16GB DDR4
- GPU: Integrated graphics
- Storage: 128GB SSD

### Recommended (Professional Users)
- CPU: Intel Core i7-13700 / AMD Ryzen 7 7700X
- RAM: 64GB DDR4/DDR5
- GPU: Integrated + Nvidia RTX 3080 / AMD RX 6800
- Storage: 1TB NVMe SSD

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## Acknowledgments

NeuronOS is built on the shoulders of giants:
- [Arch Linux](https://archlinux.org/)
- [QEMU/KVM](https://www.qemu.org/)
- [Looking Glass](https://looking-glass.io/)
- [Wine/Proton](https://www.winehq.org/)
- [libvirt](https://libvirt.org/)
