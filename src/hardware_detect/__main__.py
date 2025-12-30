#!/usr/bin/env python3
"""NeuronOS Hardware Detection - Module entry point."""
import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from hardware_detect.cli import main

if __name__ == "__main__":
    main()
