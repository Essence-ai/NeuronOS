# Phase 2.5: Proton Version Management & Configuration

**Status**: 🟡 PARTIAL - Needs detection, version switching UI, compatibility tracking
**Estimated Time**: 2-3 days
**Prerequisites**: Phase 2.1-2.4 complete (VM creation working)

---

## What is Proton?

**Proton** (by Valve) runs Windows games on Linux with near-native performance:

- **Proton 8.x** - Stable, well-tested (most apps work)
- **Proton 9.x** - Latest features, newer game support
- **Experimental** - Cutting-edge, may have issues
- **Compatibility varies** - Some games work better on specific versions

**In NeuronOS context**: While the primary solution is Windows VMs (100% compatibility), some users may want to run games directly on Linux via Proton for better performance than VM overhead.

**Without this phase**:
- Only one Proton version available
- Can't test different versions for compatibility
- Can't optimize per-game settings
- Users stuck if game needs specific version

**With this phase**:
- Multiple Proton versions installed
- Switch per-game
- Compatibility ratings remembered
- Wine prefixes isolated per version

---

## Current State: No Version Management

- ❌ No Proton version detection
- ❌ No version installation UI
- ❌ No per-game version selection
- ❌ No compatibility tracking
- ❌ No prefix management
- ❌ No Wine configuration UI

---

## Objective: Flexible Proton Management

After Phase 2.5:

1. ✅ **Detect installed Proton versions** - Know what's available
2. ✅ **Multi-version support** - Have 8.x, 9.x, experimental available
3. ✅ **Per-game configuration** - Choose version for each game/app
4. ✅ **Wine prefix isolation** - Each version gets own prefix
5. ✅ **Compatibility tracking** - Remember which version works for each game
6. ✅ **Easy version switching** - GUI to change without complexity
7. ✅ **Environment configuration** - Set DXVK, Esync, Fsync per-game

---

## Part 1: Proton Version Detection

**File**: `src/vm_manager/core/proton_manager.py`

```python
"""Proton version detection and management."""

import logging
import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class ProtonSource(Enum):
    """Where Proton is installed."""
    STEAM = "steam"            # ~/.steam/root/compatibilitytools/Proton-*
    LUTRIS = "lutris"          # ~/.lutris/runners/proton-*
    SYSTEM = "system"          # /opt/Proton-* or /usr/local/
    CUSTOM = "custom"          # User-installed


@dataclass
class ProtonVersion:
    """Detected Proton installation."""
    version: str                # "8.3", "9.0", "experimental"
    path: Path                  # Full path to proton executable
    source: ProtonSource        # Where it's from
    size_mb: int               # Installation size
    is_default: bool           # Used by default
    is_experimental: bool      # Pre-release version
    compatibility_count: int   # How many games tested with this
    working_games: int         # How many games work

    def __str__(self) -> str:
        return f"Proton {self.version} ({self.source.value})"


class ProtonManager:
    """Manages Proton versions and per-game configuration."""

    def __init__(self):
        """Initialize Proton manager."""
        self.steam_compat_dir = Path.home() / ".steam/root/compatibilitytools/Proton-*"
        self.lutris_runners = Path.home() / ".lutris/runners"
        self.proton_configs = Path.home() / ".config/neuronos/proton"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create config directories."""
        self.proton_configs.mkdir(parents=True, exist_ok=True)

    def detect_all_versions(self) -> List[ProtonVersion]:
        """Detect all installed Proton versions.

        Searches:
        - Steam compatibility tools
        - Lutris runners
        - System PATH
        - Custom locations

        Returns:
            List of ProtonVersion objects
        """
        versions = []

        # Search Steam directory
        versions.extend(self._detect_steam_proton())

        # Search Lutris
        versions.extend(self._detect_lutris_proton())

        # Search system
        versions.extend(self._detect_system_proton())

        logger.info(f"Found {len(versions)} Proton versions")
        return sorted(versions, key=lambda v: v.version, reverse=True)

    def _detect_steam_proton(self) -> List[ProtonVersion]:
        """Detect Proton from Steam."""
        versions = []
        steam_compat = Path.home() / ".steam/root/compatibilitytools/Proton"

        if not steam_compat.exists():
            return versions

        for proton_dir in steam_compat.parent.glob("Proton-*"):
            proton_exe = proton_dir / "proton"
            if proton_exe.exists():
                size_mb = sum(
                    f.stat().st_size for f in proton_dir.rglob("*") if f.is_file()
                ) // (1024 * 1024)

                version_str = proton_dir.name.replace("Proton-", "")
                version = ProtonVersion(
                    version=version_str,
                    path=proton_exe,
                    source=ProtonSource.STEAM,
                    size_mb=size_mb,
                    is_default=False,
                    is_experimental="experimental" in version_str.lower(),
                    compatibility_count=0,
                    working_games=0,
                )
                versions.append(version)
                logger.info(f"Found Steam Proton: {version}")

        return versions

    def _detect_lutris_proton(self) -> List[ProtonVersion]:
        """Detect Proton from Lutris."""
        versions = []

        if not self.lutris_runners.exists():
            return versions

        for proton_dir in self.lutris_runners.glob("proton-*"):
            proton_exe = proton_dir / "proton"
            if proton_exe.exists():
                size_mb = sum(
                    f.stat().st_size for f in proton_dir.rglob("*") if f.is_file()
                ) // (1024 * 1024)

                version_str = proton_dir.name.replace("proton-", "")
                version = ProtonVersion(
                    version=version_str,
                    path=proton_exe,
                    source=ProtonSource.LUTRIS,
                    size_mb=size_mb,
                    is_default=False,
                    is_experimental=False,
                    compatibility_count=0,
                    working_games=0,
                )
                versions.append(version)
                logger.info(f"Found Lutris Proton: {version}")

        return versions

    def _detect_system_proton(self) -> List[ProtonVersion]:
        """Detect Proton from system."""
        versions = []

        # Try /opt/Proton-*
        opt_proton = Path("/opt")
        for proton_dir in opt_proton.glob("Proton-*"):
            proton_exe = proton_dir / "proton"
            if proton_exe.exists():
                version_str = proton_dir.name.replace("Proton-", "")
                version = ProtonVersion(
                    version=version_str,
                    path=proton_exe,
                    source=ProtonSource.SYSTEM,
                    size_mb=0,
                    is_default=False,
                    is_experimental=False,
                    compatibility_count=0,
                    working_games=0,
                )
                versions.append(version)

        return versions

    def get_default_version(self) -> Optional[ProtonVersion]:
        """Get default Proton version."""
        config_file = self.proton_configs / "default.json"
        if config_file.exists():
            data = json.loads(config_file.read_text())
            versions = self.detect_all_versions()
            for v in versions:
                if str(v.path) == data.get("path"):
                    return v
        return None

    def set_default_version(self, version: ProtonVersion) -> bool:
        """Set default Proton version."""
        config_file = self.proton_configs / "default.json"
        config_file.write_text(
            json.dumps({"version": version.version, "path": str(version.path)}, indent=2)
        )
        logger.info(f"Set default Proton: {version.version}")
        return True

    def get_game_config(self, game_id: str) -> Dict:
        """Get Proton config for specific game.

        Args:
            game_id: Unique game identifier

        Returns:
            Config dict with version, environment, etc.
        """
        config_file = self.proton_configs / f"{game_id}.json"
        if config_file.exists():
            return json.loads(config_file.read_text())

        # Return default config
        return {
            "version": "default",
            "proton_version": None,
            "wine_prefix": str(Path.home() / f".proton-prefixes/{game_id}"),
            "dxvk_enabled": True,
            "vkd3d_enabled": True,
            "esync_enabled": False,
            "fsync_enabled": False,
            "environment": {},
            "compatibility_rating": "unknown",
        }

    def set_game_config(self, game_id: str, config: Dict) -> bool:
        """Save Proton config for game."""
        config_file = self.proton_configs / f"{game_id}.json"
        config_file.write_text(json.dumps(config, indent=2))
        logger.info(f"Saved config for {game_id}")
        return True

    def list_games_by_compatibility(self) -> Dict[str, list]:
        """List games grouped by compatibility rating.

        Returns:
            {"working": [games...], "buggy": [...], "broken": [...]}
        """
        games_by_rating = {"working": [], "buggy": [], "broken": [], "unknown": []}

        for config_file in self.proton_configs.glob("*.json"):
            if config_file.name == "default.json":
                continue

            data = json.loads(config_file.read_text())
            rating = data.get("compatibility_rating", "unknown")

            if rating in games_by_rating:
                games_by_rating[rating].append(config_file.stem)

        return games_by_rating
```

---

## Part 2: GUI for Version Management

**File**: `src/vm_manager/gui/proton_settings.py` (new file)

Provides dialog to:
- List detected Proton versions
- Set default version
- Configure per-game settings
- Track compatibility
- View DXVK/Esync/Fsync options

---

## Part 3: Store Integration

Show "Proton Games" section in App Store:
- Filter games by compatibility
- Show which Proton version recommended
- Allow version override

---

## Part 4: Testing

```python
# tests/test_proton_manager.py
# Test:
# - Version detection (Steam, Lutris, system)
# - Config save/load
# - Compatibility tracking
# - Default version management
```

---

## Verification Checklist

- [ ] Proton versions detected from all sources
- [ ] Default version can be set/get
- [ ] Per-game config saves to disk
- [ ] Compatibility ratings tracked
- [ ] GUI shows available versions
- [ ] Can switch versions per-game
- [ ] Environment variables configurable
- [ ] Tests pass

---

## Acceptance Criteria

✅ **Phase 2.5 Complete When**:

1. Multiple Proton versions detected
2. Users can switch default version
3. Per-game Proton version configuration works
4. Compatibility ratings persist
5. DXVK/Esync/Fsync can be toggled
6. GUI integrates with app launcher
7. All tests pass

---

## Next Steps

- Phase 3.1: Settings UI for per-game advanced options
- Phase 3.2: Better error messages for compatibility issues

---

## Resources

- [Proton GitHub](https://github.com/ValveSoftware/Proton)
- [ProtonDB Compatibility](https://protondb.com/)
- [DXVK Project](https://github.com/doitsujin/dxvk)
- [Wine Documentation](https://wiki.winehq.org)

Good luck! 🚀
