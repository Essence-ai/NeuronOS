"""
NeuronOS Update and Rollback System

Provides safe system updates with automatic snapshots:
- Integration with Timeshift for btrfs/rsync snapshots
- Pre-update snapshots for easy rollback
- Update verification and health checks
- Rollback UI
"""

from .updater import (
    UpdateManager,
    UpdateInfo,
    UpdateStatus,
    UpdateError,
)
from .snapshot import (
    SnapshotManager,
    Snapshot,
    SnapshotType,
)
from .rollback import (
    RollbackManager,
    RollbackStatus,
)

__all__ = [
    "UpdateManager",
    "UpdateInfo",
    "UpdateStatus",
    "UpdateError",
    "SnapshotManager",
    "Snapshot",
    "SnapshotType",
    "RollbackManager",
    "RollbackStatus",
]
