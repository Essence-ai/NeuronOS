"""
VM State Machine

Manages VM state transitions with proper validation and error handling.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Dict, Set, Callable

logger = logging.getLogger(__name__)


class VMState(Enum):
    """Virtual machine states matching libvirt domain states."""
    NOSTATE = 0
    RUNNING = 1
    BLOCKED = 2
    PAUSED = 3
    SHUTDOWN = 4
    SHUTOFF = 5
    CRASHED = 6
    PMSUSPENDED = 7


class VMTransition(Enum):
    """Possible VM state transitions."""
    START = auto()
    STOP = auto()
    PAUSE = auto()
    RESUME = auto()
    RESET = auto()
    SHUTDOWN = auto()
    FORCE_STOP = auto()


# Valid state transitions map
# Format: {current_state: {transition: target_state}}
VALID_TRANSITIONS: Dict[VMState, Dict[VMTransition, VMState]] = {
    VMState.SHUTOFF: {
        VMTransition.START: VMState.RUNNING,
    },
    VMState.RUNNING: {
        VMTransition.STOP: VMState.SHUTDOWN,
        VMTransition.PAUSE: VMState.PAUSED,
        VMTransition.RESET: VMState.RUNNING,
        VMTransition.SHUTDOWN: VMState.SHUTDOWN,
        VMTransition.FORCE_STOP: VMState.SHUTOFF,
    },
    VMState.PAUSED: {
        VMTransition.RESUME: VMState.RUNNING,
        VMTransition.FORCE_STOP: VMState.SHUTOFF,
    },
    VMState.SHUTDOWN: {
        VMTransition.FORCE_STOP: VMState.SHUTOFF,
    },
    VMState.CRASHED: {
        VMTransition.START: VMState.RUNNING,
        VMTransition.FORCE_STOP: VMState.SHUTOFF,
    },
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class VMStateMachine:
    """
    Manages VM state transitions.
    
    Ensures that only valid state transitions are performed and
    provides hooks for transition events.
    """
    
    def __init__(self, vm_name: str, initial_state: VMState = VMState.SHUTOFF):
        self.vm_name = vm_name
        self._state = initial_state
        self._transition_callbacks: Dict[VMTransition, list[Callable]] = {}
    
    @property
    def state(self) -> VMState:
        """Get current VM state."""
        return self._state
    
    def can_transition(self, transition: VMTransition) -> bool:
        """Check if a transition is valid from current state."""
        if self._state not in VALID_TRANSITIONS:
            return False
        return transition in VALID_TRANSITIONS[self._state]
    
    def get_available_transitions(self) -> Set[VMTransition]:
        """Get all valid transitions from current state."""
        if self._state not in VALID_TRANSITIONS:
            return set()
        return set(VALID_TRANSITIONS[self._state].keys())
    
    def transition(self, transition: VMTransition) -> VMState:
        """
        Perform a state transition.
        
        Args:
            transition: The transition to perform
            
        Returns:
            The new state after transition
            
        Raises:
            StateTransitionError: If transition is not valid
        """
        if not self.can_transition(transition):
            raise StateTransitionError(
                f"Cannot perform {transition.name} from state {self._state.name} "
                f"for VM {self.vm_name}"
            )
        
        old_state = self._state
        new_state = VALID_TRANSITIONS[self._state][transition]
        
        logger.info(
            f"VM {self.vm_name}: {old_state.name} -> {new_state.name} "
            f"(via {transition.name})"
        )
        
        self._state = new_state
        
        # Fire callbacks
        if transition in self._transition_callbacks:
            for callback in self._transition_callbacks[transition]:
                try:
                    callback(self.vm_name, old_state, new_state)
                except Exception as e:
                    logger.warning(f"Transition callback error: {e}")
        
        return new_state
    
    def set_state(self, state: VMState) -> None:
        """
        Forcefully set state (for synchronization with libvirt).
        
        Use with caution - bypasses transition validation.
        """
        _old_state = self._state  # noqa: F841 - kept for debugging
        self._state = state
        logger.debug(f"VM {self.vm_name}: state forced to {state.name}")
    
    def on_transition(
        self,
        transition: VMTransition,
        callback: Callable[[str, VMState, VMState], None],
    ) -> None:
        """
        Register a callback for a transition.
        
        Args:
            transition: The transition to watch
            callback: Function(vm_name, old_state, new_state)
        """
        if transition not in self._transition_callbacks:
            self._transition_callbacks[transition] = []
        self._transition_callbacks[transition].append(callback)


class VMStateMachineRegistry:
    """
    Registry of state machines for all VMs.
    """
    
    _machines: Dict[str, VMStateMachine] = {}
    
    @classmethod
    def get(cls, vm_name: str, initial_state: VMState = VMState.SHUTOFF) -> VMStateMachine:
        """Get or create a state machine for a VM."""
        if vm_name not in cls._machines:
            cls._machines[vm_name] = VMStateMachine(vm_name, initial_state)
        return cls._machines[vm_name]
    
    @classmethod
    def remove(cls, vm_name: str) -> None:
        """Remove a state machine (when VM is deleted)."""
        cls._machines.pop(vm_name, None)
    
    @classmethod
    def clear(cls) -> None:
        """Clear all state machines."""
        cls._machines.clear()
