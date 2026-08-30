"""state_machine.py - Explicit state management for MUSKU.

Defines the exact states MUSKU can be in to prevent race conditions
and invalid transitions (like speaking and listening simultaneously).
"""

from enum import Enum
import logging
from .event_bus import bus

logger = logging.getLogger("MUSKU.StateMachine")

class SystemState(Enum):
    OFFLINE = "offline"
    STARTING = "starting"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    TOOL_EXECUTING = "tool_executing"
    ERROR = "error"
    RECOVERING = "recovering"
    RECONNECTING = "reconnecting"

class StateMachine:
    def __init__(self):
        self._state = SystemState.OFFLINE
        
    @property
    def current_state(self) -> SystemState:
        return self._state
        
    def set_state(self, new_state: SystemState, context: dict = None):
        """Set a new state and broadcast it via the Event Bus."""
        if self._state == new_state:
            return
            
        old_state = self._state
        self._state = new_state
        logger.info(f"State transition: {old_state.value} -> {new_state.value}")
        
        bus.publish("STATE_CHANGE", {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "context": context or {}
        })

# Global singleton state machine
state_machine = StateMachine()
