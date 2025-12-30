"""
NeuronOS Migration Tools

Provides utilities for migrating user data from Windows/macOS installations:
- File discovery and transfer
- Browser profile migration
- Application settings migration
- Drive detection
"""

from .migrator import (
    MigrationSource,
    MigrationTarget,
    FileCategory,
    MigrationProgress,
    Migrator,
    WindowsMigrator,
    MacOSMigrator,
)
from .drive_detector import DriveDetector, DetectedDrive

__all__ = [
    "MigrationSource",
    "MigrationTarget",
    "FileCategory",
    "MigrationProgress",
    "Migrator",
    "WindowsMigrator",
    "MacOSMigrator",
    "DriveDetector",
    "DetectedDrive",
]
