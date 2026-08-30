"""event_bus.py - Central nervous system for MUSKU Realtime Core.

Provides a loosely coupled way for modules to broadcast and listen to events.
Events include: USER_SPEECH_START, INTERRUPT, STATE_CHANGE, TOOL_CALL, etc.
"""

import threading
import logging
from collections import defaultdict
from typing import Callable, Any, Dict, List

logger = logging.getLogger("MUSKU.EventBus")

class EventBus:
    """A thread-safe Event Bus for pub/sub communication across MUSKU components."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        
    def subscribe(self, event_name: str, callback: Callable[[Any], None]):
        """Subscribe to an event. Callback should accept exactly one argument (payload)."""
        with self._lock:
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)
                logger.debug(f"Subscribed {callback.__name__} to event '{event_name}'")
                
    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]):
        """Unsubscribe from an event."""
        with self._lock:
            if event_name in self._subscribers and callback in self._subscribers[event_name]:
                self._subscribers[event_name].remove(callback)
                logger.debug(f"Unsubscribed {callback.__name__} from event '{event_name}'")
                
    def publish(self, event_name: str, payload: Any = None):
        """Publish an event with an optional payload to all subscribers.
        Callbacks are executed synchronously in the publisher's thread."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))
            
        for callback in callbacks:
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Error in subscriber {callback.__name__} for event '{event_name}': {e}", exc_info=True)

# Global singleton event bus
bus = EventBus()
