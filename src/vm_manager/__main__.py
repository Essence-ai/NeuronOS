#!/usr/bin/env python3
"""NeuronOS VM Manager - Module entry point."""
import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from vm_manager.gui.app import main

if __name__ == "__main__":
    main()
