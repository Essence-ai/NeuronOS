#!/usr/bin/env python3
"""
NeuronOS Looking Glass Integration

Manages Looking Glass client for seamless VM display.
Looking Glass allows near-native display performance by sharing
GPU framebuffer via IVSHMEM (Inter-VM Shared Memory).
"""

import os
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum
import json
import time


class LookingGlassState(Enum):
    """State of Looking Glass client."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class LookingGlassConfig:
    """Configuration for Looking Glass client."""
    # Display settings
    fullscreen: bool = False
    borderless: bool = True
    always_on_top: bool = False
    minimize_on_focus_loss: bool = False

    # Performance settings
    fps_limit: int = 0  # 0 = unlimited
    show_fps: bool = False
    vsync: bool = False

    # Input settings
    capture_mouse: bool = True
    capture_keyboard: bool = True
    escape_key: str = "KEY_SCROLLLOCK"  # Key to release input

    # Audio settings
    audio_enabled: bool = True
    audio_buffer_ms: int = 20

    # IVSHMEM settings
    shmem_path: str = "/dev/shm/looking-glass"
    shmem_size_mb: int = 128

    # Window settings
    window_title: str = "NeuronOS - {vm_name}"
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    window_width: Optional[int] = None
    window_height: Optional[int] = None


class LookingGlassManager:
    """
    Manages Looking Glass client instances for VMs.

    Looking Glass is used to display VM output with minimal latency
    by directly sharing the GPU framebuffer through shared memory.
    """

    LOOKING_GLASS_BIN = "looking-glass-client"
    CONFIG_DIR = Path.home() / ".config" / "looking-glass"
    SHMEM_BASE_PATH = Path("/dev/shm")

    def __init__(self):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._states: Dict[str, LookingGlassState] = {}
        self._configs: Dict[str, LookingGlassConfig] = {}

        # Ensure config directory exists
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def is_installed(self) -> bool:
        """Check if Looking Glass client is installed."""
        return shutil.which(self.LOOKING_GLASS_BIN) is not None

    def get_version(self) -> Optional[str]:
        """Get Looking Glass client version."""
        if not self.is_installed():
            return None

        try:
            result = subprocess.run(
                [self.LOOKING_GLASS_BIN, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Parse version from output
            for line in result.stdout.split("\n"):
                if "Looking Glass" in line:
                    return line.strip()
            return result.stdout.strip().split("\n")[0]
        except Exception:
            return None

    def create_shmem_file(self, vm_name: str, size_mb: int = 128) -> Path:
        """
        Create or verify the shared memory file for a VM.

        The IVSHMEM device in QEMU will use this file.
        """
        shmem_path = self.SHMEM_BASE_PATH / f"looking-glass-{vm_name}"

        if not shmem_path.exists():
            # Create the file with correct size
            with open(shmem_path, "wb") as f:
                f.truncate(size_mb * 1024 * 1024)

        # Set permissions (user must be in 'kvm' group typically)
        os.chmod(shmem_path, 0o660)

        return shmem_path

    def get_shmem_path(self, vm_name: str) -> Path:
        """Get the shared memory path for a VM."""
        return self.SHMEM_BASE_PATH / f"looking-glass-{vm_name}"

    def configure(self, vm_name: str, config: LookingGlassConfig) -> None:
        """Store configuration for a VM."""
        self._configs[vm_name] = config

        # Also write to config file for persistence
        config_file = self.CONFIG_DIR / f"{vm_name}.json"
        config_dict = {
            "fullscreen": config.fullscreen,
            "borderless": config.borderless,
            "always_on_top": config.always_on_top,
            "fps_limit": config.fps_limit,
            "show_fps": config.show_fps,
            "capture_mouse": config.capture_mouse,
            "capture_keyboard": config.capture_keyboard,
            "escape_key": config.escape_key,
            "shmem_path": config.shmem_path,
            "shmem_size_mb": config.shmem_size_mb,
            "window_title": config.window_title,
        }

        with open(config_file, "w") as f:
            json.dump(config_dict, f, indent=2)

    def get_config(self, vm_name: str) -> LookingGlassConfig:
        """Get configuration for a VM."""
        if vm_name in self._configs:
            return self._configs[vm_name]

        # Try to load from file
        config_file = self.CONFIG_DIR / f"{vm_name}.json"
        if config_file.exists():
            with open(config_file) as f:
                data = json.load(f)
                config = LookingGlassConfig(**data)
                self._configs[vm_name] = config
                return config

        # Return default config
        return LookingGlassConfig()

    def build_command(self, vm_name: str, config: Optional[LookingGlassConfig] = None) -> List[str]:
        """Build the Looking Glass client command."""
        if config is None:
            config = self.get_config(vm_name)

        shmem_path = self.get_shmem_path(vm_name)

        cmd = [self.LOOKING_GLASS_BIN]

        # Shared memory file
        cmd.extend(["-f", str(shmem_path)])

        # Display mode
        if config.fullscreen:
            cmd.append("-F")
        if config.borderless:
            cmd.extend(["-w", "-b"])  # Window mode, borderless

        # Input
        if not config.capture_mouse:
            cmd.extend(["-m", "0"])  # Disable mouse capture
        if config.escape_key:
            cmd.extend(["-k", config.escape_key])

        # Performance
        if config.fps_limit > 0:
            cmd.extend(["-K", str(config.fps_limit)])
        if config.show_fps:
            cmd.append("-s")

        # Window title
        title = config.window_title.format(vm_name=vm_name)
        cmd.extend(["-T", title])

        # Window position/size
        if config.window_x is not None and config.window_y is not None:
            cmd.extend(["-x", str(config.window_x), "-y", str(config.window_y)])
        if config.window_width is not None and config.window_height is not None:
            cmd.extend(["-W", str(config.window_width), "-H", str(config.window_height)])

        return cmd

    def start(
        self,
        vm_name: str,
        config: Optional[LookingGlassConfig] = None,
        wait_for_shmem: bool = True
    ) -> bool:
        """
        Start Looking Glass client for a VM.

        Args:
            vm_name: Name of the VM
            config: Optional configuration override
            wait_for_shmem: Wait for shared memory file to be ready

        Returns:
            True if started successfully
        """
        if not self.is_installed():
            self._states[vm_name] = LookingGlassState.ERROR
            return False

        if vm_name in self._processes and self._processes[vm_name].poll() is None:
            # Already running
            return True

        self._states[vm_name] = LookingGlassState.STARTING

        shmem_path = self.get_shmem_path(vm_name)

        # Wait for shared memory file if requested
        if wait_for_shmem:
            max_wait = 30  # seconds
            waited = 0
            while not shmem_path.exists() and waited < max_wait:
                time.sleep(0.5)
                waited += 0.5

            if not shmem_path.exists():
                self._states[vm_name] = LookingGlassState.ERROR
                return False

        cmd = self.build_command(vm_name, config)

        try:
            # Start Looking Glass client
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Detach from terminal
            )

            self._processes[vm_name] = process

            # Give it a moment to start
            time.sleep(0.5)

            if process.poll() is None:
                self._states[vm_name] = LookingGlassState.RUNNING
                return True
            else:
                # Process exited immediately
                self._states[vm_name] = LookingGlassState.ERROR
                return False

        except Exception:
            self._states[vm_name] = LookingGlassState.ERROR
            return False

    def stop(self, vm_name: str, force: bool = False) -> bool:
        """
        Stop Looking Glass client for a VM.

        Args:
            vm_name: Name of the VM
            force: Use SIGKILL instead of SIGTERM

        Returns:
            True if stopped successfully
        """
        if vm_name not in self._processes:
            self._states[vm_name] = LookingGlassState.STOPPED
            return True

        process = self._processes[vm_name]

        if process.poll() is not None:
            # Already stopped
            del self._processes[vm_name]
            self._states[vm_name] = LookingGlassState.STOPPED
            return True

        try:
            if force:
                process.kill()
            else:
                process.terminate()

            # Wait for process to end
            process.wait(timeout=5)

            del self._processes[vm_name]
            self._states[vm_name] = LookingGlassState.STOPPED
            return True

        except subprocess.TimeoutExpired:
            process.kill()
            del self._processes[vm_name]
            self._states[vm_name] = LookingGlassState.STOPPED
            return True
        except Exception:
            return False

    def get_state(self, vm_name: str) -> LookingGlassState:
        """Get the state of Looking Glass for a VM."""
        if vm_name not in self._states:
            return LookingGlassState.STOPPED

        # Verify process is still running
        if vm_name in self._processes:
            if self._processes[vm_name].poll() is not None:
                self._states[vm_name] = LookingGlassState.STOPPED
                del self._processes[vm_name]

        return self._states[vm_name]

    def is_running(self, vm_name: str) -> bool:
        """Check if Looking Glass is running for a VM."""
        return self.get_state(vm_name) == LookingGlassState.RUNNING

    def toggle_fullscreen(self, vm_name: str) -> bool:
        """
        Toggle fullscreen mode for Looking Glass.
        
        Since Looking Glass doesn't expose IPC for fullscreen toggle,
        we restart it with the opposite fullscreen setting.
        
        Args:
            vm_name: Name of the VM
            
        Returns:
            True if toggle succeeded
        """
        if not self.is_running(vm_name):
            return False
        
        # Get current config and toggle fullscreen
        config = self.get_config(vm_name)
        config.fullscreen = not config.fullscreen
        
        # Save updated config
        self.configure(vm_name, config)
        
        # Restart with new config
        return self.restart(vm_name, config)

    def restart(self, vm_name: str, config: Optional[LookingGlassConfig] = None) -> bool:
        """
        Restart Looking Glass for a VM.
        
        Args:
            vm_name: Name of the VM
            config: Optional new configuration
            
        Returns:
            True if restart succeeded
        """
        self.stop(vm_name)
        time.sleep(0.3)  # Brief pause for cleanup
        return self.start(vm_name, config, wait_for_shmem=False)

    def cleanup_shmem(self, vm_name: str) -> None:
        """Remove shared memory file for a VM."""
        shmem_path = self.get_shmem_path(vm_name)
        if shmem_path.exists():
            shmem_path.unlink()

    def cleanup_all(self) -> None:
        """Stop all Looking Glass instances and clean up."""
        for vm_name in list(self._processes.keys()):
            self.stop(vm_name, force=True)

        # Clean up any orphaned shmem files
        for shmem_file in self.SHMEM_BASE_PATH.glob("looking-glass-*"):
            try:
                shmem_file.unlink()
            except Exception:
                pass


# Singleton instance
_manager: Optional[LookingGlassManager] = None


def get_looking_glass_manager() -> LookingGlassManager:
    """Get the singleton Looking Glass manager instance."""
    global _manager
    if _manager is None:
        _manager = LookingGlassManager()
    return _manager


if __name__ == "__main__":
    # Quick test
    manager = get_looking_glass_manager()

    print(f"Looking Glass installed: {manager.is_installed()}")
    if manager.is_installed():
        print(f"Version: {manager.get_version()}")

    # Show example command
    config = LookingGlassConfig(
        borderless=True,
        capture_mouse=True,
        show_fps=True
    )
    cmd = manager.build_command("test-vm", config)
    print(f"Example command: {' '.join(cmd)}")
