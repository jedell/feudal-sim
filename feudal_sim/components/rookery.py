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
from feudal_sim.utils.observations import ObservationFormatter


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
    sent_date: str = ""  # Full date string (e.g., "Week 3, Spring, Year 1")
    arrival_date: str = ""  # Full arrival date string
    delivered: bool = False


@dataclass
class ReceivedMessage:
    """A message that has been received and processed."""
    sender_id: str
    sender_name: str
    message: str
    turn_received: int
    sent_date: str = ""  # When the message was originally sent


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
    
    def add_known_recipient(self, entity_id: str, entity_name: str = None, discovered: bool = True):
        """
        Add an entity to the list of known recipients.
        
        Args:
            entity_id: The ID of the entity to add
            entity_name: Optional display name (defaults to entity_id)
            discovered: Whether to generate a "discovery" observation (False for initial setup)
        """
        self.known_recipients.add(entity_id)
        
        # Generate observation about learning of new entity (only if discovered during gameplay)
        if discovered:
            name = entity_name or entity_id
            self.current_observations.append(f"📍 Learned about {name} - can now send ravens")
    
    def can_send_to(self, recipient_id: str) -> bool:
        """Check if this entity can send ravens to the specified recipient."""
        return recipient_id in self.known_recipients
    
    def set_current_date_context(self, turn: int, date_string: str):
        """Set the current turn and date context for raven messaging."""
        self._current_turn = turn
        self._current_date = date_string
    
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
        
        # Calculate arrival time (1-2 weeks from now)
        current_turn = getattr(self, '_current_turn', 1)  # Fallback for testing
        current_date = getattr(self, '_current_date', "Week 1, Spring, Year 1")  # Fallback
        arrival_turn = current_turn + 1 # 2 weeks total

        # For now, just update the week number (could be enhanced with proper date calculation)
        arrival_date = current_date.replace(f"Week {current_turn}", f"Week {arrival_turn}") # 2 weeks
        
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
            arrival_turn=arrival_turn,
            sent_date=current_date,
            arrival_date=arrival_date
        )
        
        self.outgoing_ravens.append(raven)
        
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
            turn_received=raven_message.arrival_turn,
            sent_date=raven_message.sent_date
        )
        
        self.inbox.append(received)
        self.message_history.append(received)
        
        # Generate observation for AI
        self.current_observations.append(
            ObservationFormatter.raven_received(raven_message.sender_name, raven_message.message)
        )
        
        # Store reference for delivery notification
        self._delivered_raven = raven_message
        
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
    
    def get_in_transit_ravens(self) -> List[RavenMessage]:
        """
        Get all ravens currently in transit (sent but not yet delivered).
        
        Returns:
            List of ravens currently flying
        """
        return [raven for raven in self.outgoing_ravens if not raven.delivered]
    
    def add_in_transit_observations(self, ai_component=None, phase: str = "Production"):
        """
        Add observations about ravens currently in transit.
        
        Args:
            ai_component: AI component to add observations to
            phase: Current phase name for observation context
        """
        if not ai_component:
            return
        
        in_transit = self.get_in_transit_ravens()
        
        if in_transit:
            # Create observation for each in-transit raven
            for raven in in_transit:
                weeks_remaining = raven.arrival_turn - getattr(self, '_current_turn', 1)
                if weeks_remaining <= 0:
                    status = "arriving this week"
                else:
                    status = f"arriving in {weeks_remaining} week{'s' if weeks_remaining != 1 else ''}"
                
                observation = f"🐦 Raven in transit to {raven.recipient_name}: '{raven.message[:30]}...' ({status})"
                ai_component.add_observation(observation, phase)
    
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
    
    def get_lore_section(self) -> str:
        """Return lore explanation of raven communication mechanics for AI prompts."""
        return """
**The Raven Network:**
Messages between houses travel by raven, taking two weeks to reach their destination. A wise lord sends missives sparingly and waits patiently for replies. Flooding another lord with ravens marks you as desperate or foolish - patience in correspondence is the hallmark of wisdom and proper breeding.

Ravens can only reach known recipients - houses you have discovered or been introduced to through prior correspondence. Each message takes time to compose, dispatch, and receive response."""

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
                
                # Add delivery notification to sender
                sender_entity = entity_manager.get_entity(raven.sender_id)
                if sender_entity and sender_entity.has_component(RookeryComponent):
                    sender_rookery = sender_entity.get_component(RookeryComponent)
                    delivery_notification = ObservationFormatter.raven_delivered(raven.recipient_name)
                    sender_rookery.current_observations.append(delivery_notification)
        
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