#!/usr/bin/env python3
"""NeuronOS Migration Tool - Module entry point."""
import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from migration.cli import main

if __name__ == "__main__":
    main()
