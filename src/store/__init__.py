"""
NeuronOS Store

Application catalog and compatibility layer management.
"""

from .app_catalog import AppCatalog, AppInfo, CompatibilityLayer
from .installer import AppInstaller
from .wine_manager import WineManager, WinePrefixInfo, WineVersionInfo
from .steam_detect import SteamDetector, ProtonVersion, SteamGameInfo

__all__ = [
    "AppCatalog",
    "AppInfo",
    "CompatibilityLayer",
    "AppInstaller",
    "WineManager",
    "WinePrefixInfo",
    "WineVersionInfo",
    "SteamDetector",
    "ProtonVersion",
    "SteamGameInfo",
]
