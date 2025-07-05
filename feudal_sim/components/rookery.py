"""
RookeryComponent - Raven-based communication system for medieval entities.

Handles sending and receiving raven messages between entities, with travel time
delays and known recipient tracking for realistic communication constraints.
"""

import random
from typing import List, Dict, Set
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType


@dataclass
class RavenMessage:
    """A message carried by a raven."""
    sender_id: str
    sender_name: str
    recipient_id: str
    recipient_name: str
    message: str
    sent_turn: int
    arrival_turn: int
    delivered: bool = False


@dataclass
class ReceivedMessage:
    """A message that has been received and processed."""
    sender_id: str
    sender_name: str
    message: str
    turn_received: int


class RookeryComponent(Component):
    """
    Manages raven-based communication for an entity.
    
    Features:
    - Send ravens to known recipients
    - Receive incoming ravens during Events phase
    - Track known entities for communication
    - Generate observations for AI context
    - Maintain message history
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Known recipients this entity can send ravens to
        self.known_recipients: Set[str] = set()
        
        # Outgoing ravens currently in flight
        self.outgoing_ravens: List[RavenMessage] = []
        
        # Inbox of received messages this turn
        self.inbox: List[ReceivedMessage] = []
        
        # Complete message history for debugging/AI context
        self.message_history: List[ReceivedMessage] = []
        
        # Observations generated for AI this turn
        self.current_observations: List[str] = []
    
    def add_known_recipient(self, entity_id: str, entity_name: str = None):
        """
        Add an entity to the list of known recipients.
        
        Args:
            entity_id: The ID of the entity to add
            entity_name: Optional display name (defaults to entity_id)
        """
        self.known_recipients.add(entity_id)
        
        # Generate observation about learning of new entity
        name = entity_name or entity_id
        self.current_observations.append(f"📍 Learned about {name} - can now send ravens")
    
    def can_send_to(self, recipient_id: str) -> bool:
        """Check if this entity can send ravens to the specified recipient."""
        return recipient_id in self.known_recipients
    
    def send_raven(self, recipient_id: str, message: str) -> bool:
        """
        Send a raven message to a recipient.
        
        Args:
            recipient_id: The ID of the recipient entity
            message: The message content
            
        Returns:
            True if raven was sent successfully, False if recipient unknown
        """
        if not self.can_send_to(recipient_id):
            self.current_observations.append(f"❌ Cannot send raven to unknown recipient: {recipient_id}")
            return False
        
        # Calculate arrival time (1-2 turns from now)
        from feudal_sim.core.time import GameTime
        current_turn = getattr(self, '_current_turn', 1)  # Fallback for testing
        arrival_turn = current_turn + random.choice([1, 2])
        
        # Get recipient name for display
        recipient_name = recipient_id  # Could be enhanced with entity lookup
        
        # Create raven message
        raven = RavenMessage(
            sender_id=self.entity_id,
            sender_name=self.entity.name if self.entity else self.entity_id,
            recipient_id=recipient_id,
            recipient_name=recipient_name,
            message=message,
            sent_turn=current_turn,
            arrival_turn=arrival_turn
        )
        
        self.outgoing_ravens.append(raven)
        
        # Generate observation for sender
        self.current_observations.append(
            f"🐦 Sent raven to {recipient_name}: '{message}' (arriving turn {arrival_turn})"
        )
        
        # Emit event for global raven tracking
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='raven_sent',
                sender=self.entity.name if self.entity else self.entity_id,
                recipient=recipient_name,
                message=message,
                arrival_turn=arrival_turn
            )
        
        return True
    
    def deliver_raven(self, raven_message: RavenMessage):
        """
        Deliver an incoming raven message to this entity's inbox.
        
        Args:
            raven_message: The raven message being delivered
        """
        received = ReceivedMessage(
            sender_id=raven_message.sender_id,
            sender_name=raven_message.sender_name,
            message=raven_message.message,
            turn_received=raven_message.arrival_turn
        )
        
        self.inbox.append(received)
        self.message_history.append(received)
        
        # Generate observation for AI
        self.current_observations.append(
            f"📜 Raven arrived from {raven_message.sender_name}: '{raven_message.message}'"
        )
        
        # Emit event for global message tracking
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='raven_received',
                sender=raven_message.sender_name,
                recipient=self.entity.name if self.entity else self.entity_id,
                message=raven_message.message
            )
    
    def process_arriving_ravens(self, current_turn: int) -> List[RavenMessage]:
        """
        Check for ravens that should arrive this turn.
        Called during Events phase.
        
        Args:
            current_turn: The current turn number
            
        Returns:
            List of ravens ready for delivery
        """
        self._current_turn = current_turn
        
        # Find ravens that should arrive this turn
        arriving_ravens = [
            raven for raven in self.outgoing_ravens 
            if raven.arrival_turn <= current_turn and not raven.delivered
        ]
        
        return arriving_ravens
    
    def get_observations_for_ai(self) -> List[str]:
        """
        Get all communication observations for AI context.
        
        Returns:
            List of observation strings for the current turn
        """
        observations = self.current_observations.copy()
        
        # Add inbox summary if no specific messages
        if not any("Raven arrived" in obs for obs in observations):
            if not self.inbox:
                observations.append("📬 No ravens received this turn")
        
        return observations
    
    def clear_turn_data(self):
        """Clear turn-specific data at end of turn."""
        self.inbox.clear()
        self.current_observations.clear()
        
        # Clean up delivered ravens
        self.outgoing_ravens = [r for r in self.outgoing_ravens if not r.delivered]
    
    def get_recent_messages(self, num_messages: int = 5) -> List[ReceivedMessage]:
        """Get the most recent received messages for AI context."""
        return self.message_history[-num_messages:] if self.message_history else []
    
    def get_known_recipients_list(self) -> List[str]:
        """Get list of all known recipients for AI tool use."""
        return list(self.known_recipients)
    
    def get_communication_status(self) -> Dict[str, any]:
        """Get current communication status for debugging/display."""
        return {
            'known_recipients': len(self.known_recipients),
            'outgoing_ravens': len([r for r in self.outgoing_ravens if not r.delivered]),
            'inbox_count': len(self.inbox),
            'total_messages_received': len(self.message_history),
            'current_observations': len(self.current_observations)
        }
    
    def update(self, dt: float, event_bus=None):
        """
        Component update - currently used for turn tracking.
        Main raven processing happens during Events phase via process_arriving_ravens.
        """
        # This could be used for periodic maintenance if needed
        pass


# Global raven delivery system for coordinating between entities
class RavenDeliverySystem:
    """
    Coordinates raven delivery between entities during Events phase.
    """
    
    @staticmethod
    def deliver_ravens_for_turn(entity_manager, current_turn: int):
        """
        Process all raven deliveries for the current turn.
        Should be called during Events phase.
        
        Args:
            entity_manager: The EntityManager containing all entities
            current_turn: Current turn number
        """
        # Get all entities with rookery components
        entities_with_rookeries = entity_manager.get_entities_with_component(RookeryComponent)
        
        # Collect all ravens that should arrive this turn
        ravens_to_deliver = []
        
        for entity in entities_with_rookeries:
            rookery = entity.get_component(RookeryComponent)
            
            # Get ravens ready for delivery from this entity
            arriving_ravens = rookery.process_arriving_ravens(current_turn)
            ravens_to_deliver.extend(arriving_ravens)
        
        # Deliver ravens to their recipients
        for raven in ravens_to_deliver:
            recipient_entity = entity_manager.get_entity(raven.recipient_id)
            if recipient_entity and recipient_entity.has_component(RookeryComponent):
                recipient_rookery = recipient_entity.get_component(RookeryComponent)
                recipient_rookery.deliver_raven(raven)
                # Mark as delivered
                raven.delivered = True
        
        return len(ravens_to_deliver)
    
    @staticmethod
    def clear_turn_data_for_all(entity_manager):
        """
        Clear turn-specific data for all rookery components.
        Should be called during Cleanup phase.
        """
        entities_with_rookeries = entity_manager.get_entities_with_component(RookeryComponent)
        
        for entity in entities_with_rookeries:
            rookery = entity.get_component(RookeryComponent)
            rookery.clear_turn_data()