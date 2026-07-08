"""
Conversation Manager for Priority Actions

Handles agent-to-agent conversations during priority actions, providing
seamless message delivery with asymmetric perspectives where each agent
sees the conversation from their own viewpoint.
"""

from typing import List, Dict, Any
from agents import function_tool

from feudal_sim.components.ai import AIComponent


class ConversationManager:
    """
    Manages multi-agent conversations during priority actions.
    
    Each agent experiences the conversation from their own perspective,
    with messages from other agents appearing as user messages in their
    message history, maintaining the natural conversation flow.
    """
    
    def __init__(self, event, simulation):
        """
        Initialize conversation manager for a priority action event.
        
        Args:
            event: The PriorityActionEvent this conversation is for
            simulation: Reference to the main simulation object
        """
        self.event = event
        self.simulation = simulation
        self.conversation_log = []
        self.round_counter = 0
        self.agents_spoken_this_round = set()
    
    def create_speak_tool(self, speaker_agent_id: str):
        """
        Create agent-specific speak tool for conversations.
        
        Args:
            speaker_agent_id: ID of the agent who will use this speak tool
            
        Returns:
            Function tool that allows the agent to speak to other participants
        """
        @function_tool
        def speak(message: str) -> str:
            """
            Speak to other participants in this negotiation.
            Your message will be delivered to all other parties involved.
            """
            # Get speaker entity for name resolution
            speaker_entity = self._get_entity(speaker_agent_id)
            speaker_name = self._get_entity_display_name(speaker_entity)
            
            # Log conversation entry
            conversation_entry = {
                'speaker_id': speaker_agent_id,
                'speaker_name': speaker_name,
                'message': message,
                'round': self.round_counter
            }
            self.conversation_log.append(conversation_entry)
            
            # Deliver message to other participants
            recipients_notified = 0
            for recipient_id in self.event.involved_agents:
                if recipient_id != speaker_agent_id:
                    success = self._deliver_message_to_agent(recipient_id, speaker_name, message)
                    if success:
                        recipients_notified += 1
            
            # Mark that this agent has spoken this round
            self.agents_spoken_this_round.add(speaker_agent_id)
            
            return f"You said: '{message}' - Message delivered to {recipients_notified} participant(s)."
        
        return speak
    
    def _deliver_message_to_agent(self, recipient_id: str, speaker_name: str, message: str) -> bool:
        """
        Deliver conversation message to recipient's message history.
        
        Args:
            recipient_id: ID of the agent receiving the message
            speaker_name: Display name of the speaker
            message: The message content
            
        Returns:
            True if message was delivered successfully, False otherwise
        """
        recipient_entity = self._get_entity(recipient_id)
        if not recipient_entity:
            return False
        
        ai_component = recipient_entity.get_component(AIComponent)
        if not ai_component:
            return False
        
        # Format message with round context for clarity
        formatted_message = f"{speaker_name} says to you"
        if self.round_counter > 0:
            formatted_message += f" (Round {self.round_counter + 1})"
        formatted_message += f": '{message}'"
        
        # Add to recipient's message history as user message
        ai_component.messages.append({
            "role": "user",
            "content": formatted_message
        })
        
        return True
    
    def _get_entity(self, entity_id: str):
        """Get entity by ID from the simulation's entity manager."""
        return self.simulation.entity_manager.get_entity(entity_id)
    
    def _get_entity_display_name(self, entity) -> str:
        """
        Get display name for an entity.
        
        Args:
            entity: The entity to get name for
            
        Returns:
            Display name string
        """
        if not entity:
            return "Unknown Entity"
        
        # Try to get AI agent name first (more descriptive)
        ai_component = entity.get_component(AIComponent)
        if ai_component and ai_component.agent_name:
            return ai_component.agent_name
        
        # Fall back to entity name
        if hasattr(entity, 'name') and entity.name:
            return entity.name
        
        # Last resort: use entity ID
        return entity.id
    
    def get_conversation_summary(self) -> str:
        """
        Generate conversation summary for context.
        
        Returns:
            Summary of recent conversation messages
        """
        if not self.conversation_log:
            return "No conversation yet."
        
        # Get last 3 messages for summary
        recent_messages = self.conversation_log[-3:]
        summary_parts = []
        
        for entry in recent_messages:
            summary_parts.append(f"{entry['speaker_name']}: {entry['message']}")
        
        return "Recent conversation: " + " | ".join(summary_parts)
    
    def get_conversation_participants(self) -> List[str]:
        """Get list of participant names who have spoken."""
        participants = set()
        for entry in self.conversation_log:
            participants.add(entry['speaker_name'])
        return list(participants)
    
    def has_agent_spoken_this_round(self, agent_id: str) -> bool:
        """Check if an agent has already spoken in the current round."""
        return agent_id in self.agents_spoken_this_round
    
    def reset_round_tracking(self):
        """Reset the tracking for agents who have spoken this round."""
        self.agents_spoken_this_round.clear()
    
    def get_full_conversation_log(self) -> List[Dict[str, Any]]:
        """Get the complete conversation log."""
        return self.conversation_log.copy()
    
    def get_conversation_length(self) -> int:
        """Get the total number of conversation messages."""
        return len(self.conversation_log)
    
    def get_message_count_by_agent(self) -> Dict[str, int]:
        """Get count of messages sent by each agent."""
        counts = {}
        for entry in self.conversation_log:
            agent_name = entry['speaker_name']
            counts[agent_name] = counts.get(agent_name, 0) + 1
        return counts