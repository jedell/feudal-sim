"""
Simple event system for making the simulation more extensible.
Enables loose coupling between components via publish-subscribe pattern.
"""

from typing import Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum
import time


class EventType(Enum):
    # Core system events
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_STEP = "simulation_step"
    SIMULATION_ENDED = "simulation_ended"
    
    # Extensibility events - generic types that can be used for any purpose
    ENTITY_CREATED = "entity_created"
    ENTITY_UPDATED = "entity_updated" 
    ENTITY_DESTROYED = "entity_destroyed"
    
    VALUE_CHANGED = "value_changed"
    STATE_CHANGED = "state_changed"
    ACTION_PERFORMED = "action_performed"


@dataclass
class Event:
    """Simple event data structure."""
    type: EventType
    source: Any
    data: Dict[str, Any]
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class EventBus:
    """
    Lightweight event bus for extensible communication.
    Components can subscribe to events without tight coupling.
    """
    
    def __init__(self):
        self._listeners: Dict[EventType, List[Callable]] = {}
        
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Subscribe to an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
        
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Unsubscribe from an event type."""
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(callback)
            except ValueError:
                pass
    
    def emit(self, event_type: EventType, source: Any, **data):
        """Emit an event with data."""
        event = Event(
            type=event_type,
            source=source,
            data=data
        )
        
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                try:
                    callback(event)
                except Exception as e:
                    print(f"⚠️  Error in event listener: {e}")
    
    def get_listener_count(self, event_type: EventType) -> int:
        """Get number of listeners for debugging."""
        return len(self._listeners.get(event_type, []))


# Global event bus instance for easy access
event_bus = EventBus()