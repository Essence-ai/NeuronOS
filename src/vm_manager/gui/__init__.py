"""
NeuronOS VM Manager GUI
"""

try:
    from .app import main, VMManagerApp
except ImportError:
    # Handle cases where GTK/Adwaita are missing or classes aren't defined
    main = None
    VMManagerApp = None

__all__ = ["main", "VMManagerApp"]
