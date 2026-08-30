"""turn_manager.py - Manages conversation turns and context.

Assigns unique IDs to each user interaction (e.g., TURN-001) to prevent
race conditions. If a turn is interrupted, its packets are ignored/flushed.
"""

import threading
import logging
from typing import Optional

logger = logging.getLogger("MUSKU.TurnManager")

class TurnManager:
    def __init__(self):
        self._current_turn_id: int = 0
        self._lock = threading.Lock()
        self._is_active = False

    def new_turn(self) -> str:
        """Starts a new turn and returns its unique ID."""
        with self._lock:
            self._current_turn_id += 1
            self._is_active = True
            turn_str = f"TURN-{self._current_turn_id:03d}"
            logger.info(f"Started {turn_str}")
            return turn_str

    def get_current_turn(self) -> str:
        """Gets the ID of the current turn."""
        with self._lock:
            return f"TURN-{self._current_turn_id:03d}"

    def interrupt_turn(self):
        """Marks the current turn as interrupted/inactive."""
        with self._lock:
            self._is_active = False
            logger.info(f"Interrupted TURN-{self._current_turn_id:03d}")

    def complete_turn(self, reason: str = "normal") -> str:
        """Mark current turn finished (fast-route, speaker-drained, turn_complete)."""
        with self._lock:
            turn_str = f"TURN-{self._current_turn_id:03d}"
            self._is_active = False
            logger.info(f"Completed {turn_str} ({reason})")
            return turn_str

    def is_turn_active(self, turn_id: str) -> bool:
        """Checks if the given turn ID is the current active turn."""
        with self._lock:
            return self._is_active and turn_id == f"TURN-{self._current_turn_id:03d}"

turn_manager = TurnManager()
