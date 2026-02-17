.PHONY: all iso clean test install-deps format lint help

# Variables
PROFILE_DIR = iso-profile
WORK_DIR = /tmp/neuron-archiso-work
OUTPUT_DIR = output
PYTHON = python3

# Default target
all: help

# Help
help:
	@echo "NeuronOS Build System"
	@echo ""
	@echo "Usage:"
	@echo "  make install-deps  Install development dependencies"
	@echo "  make test          Run test suite"
	@echo "  make format        Format Python code"
	@echo "  make lint          Run linters"
	@echo "  make iso           Build NeuronOS ISO (requires sudo)"
	@echo "  make test-vm       Test ISO in QEMU"
	@echo "  make clean         Clean build artifacts"
	@echo ""

# Install dependencies
install-deps:
	@echo "Installing dependencies..."
	sudo pacman -S --needed python python-pip archiso qemu-full libvirt virt-manager
	pip install -e ".[dev]"

# Run tests
test:
	@echo "Running tests..."
	$(PYTHON) -m pytest tests/ -v --tb=short

# Format code
format:
	@echo "Formatting code..."
	$(PYTHON) -m black src/ tests/
	$(PYTHON) -m ruff check src/ tests/ --fix

# Lint code
lint:
	@echo "Linting..."
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m mypy src/

# Build ISO (preferred: use build-iso.sh directly)
iso:
	@echo "Building NeuronOS ISO..."
	@if [ "$(shell id -u)" != "0" ]; then \
		echo "Error: Building ISO requires root. Run: sudo make iso"; \
		exit 1; \
	fi
	./build-iso.sh --clean

# Test ISO in QEMU
test-vm:
	@echo "Testing ISO in QEMU..."
	@ISO_FILE=$$(ls -1t out/neuron*.iso $(OUTPUT_DIR)/neuron*.iso 2>/dev/null | head -1); \
	if [ -z "$$ISO_FILE" ]; then \
		echo "Error: No ISO found. Run 'sudo make iso' first."; \
		exit 1; \
	fi; \
	qemu-system-x86_64 \
		-enable-kvm \
		-m 4G \
		-cpu host \
		-smp 4 \
		-boot d \
		-cdrom "$$ISO_FILE" \
		-vga virtio

# Clean build artifacts
clean:
	@echo "Cleaning..."
	sudo rm -rf $(WORK_DIR) || true
	rm -rf $(OUTPUT_DIR)/*.iso out/*.iso
	rm -rf $(PROFILE_DIR)/airootfs/usr/lib/neuron-os
	rm -rf $(PROFILE_DIR)/airootfs/home/liveuser
	rm -rf __pycache__ src/**/__pycache__ tests/__pycache__
	rm -rf *.egg-info build dist
	rm -rf .pytest_cache .mypy_cache .ruff_cache

# Hardware detection (development helper)
detect-hardware:
	@echo "Detecting GPU hardware..."
	$(PYTHON) -c "from src.hardware_detect import GPUScanner; s = GPUScanner(); print(s.to_json())" 2>/dev/null || \
	$(PYTHON) -c "import sys; sys.path.insert(0, 'src'); from hardware_detect import GPUScanner; s = GPUScanner(); gpus = s.scan(); print(f'Found {len(gpus)} GPUs')"
