#!/usr/bin/env python3
"""
NeuronOS Onboarding Wizard - CLI Entry Point

Run with:
    python -m onboarding
    neuron-onboarding

Or as a systemd user service on first boot.
"""

import sys
from .wizard import main

if __name__ == "__main__":
    sys.exit(main())
