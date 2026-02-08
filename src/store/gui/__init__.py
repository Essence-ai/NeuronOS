"""
NeuronOS Store GUI

GTK4/Adwaita application for browsing and installing applications.
"""

try:
    from .app import main, NeuronStoreApp
except ImportError:
    # Handle cases where GTK/Adwaita are missing or classes aren't defined
    main = None
    NeuronStoreApp = None

__all__ = ["main", "NeuronStoreApp"]
