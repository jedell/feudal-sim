"""
Priority Action System - Core Implementation

Enables urgent multi-agent interactions (trade arrivals, diplomatic summits, crises)
to be seamlessly handled within the existing AI message flow without breaking
conversation history continuity.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod

from feudal_sim.components.ai import AIComponent


@dataclass
class PriorityActionEvent:
    """
    Represents a priority action that requires immediate agent attention.
    
    Priority actions are events that interrupt normal turn flow to allow
    agents to handle urgent situations using specialized tools while
    maintaining their conversation history.
    """
    event_id: str
    event_type: str  # "trade_caravan_arrival", "diplomatic_summit", "enemy_encounter", etc.
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    # Participants
    involved_agents: List[str] = field(default_factory=list)  # Entity IDs
    allows_conversation: bool = False
    max_conversation_rounds: int = 3
    
    # Resolution
    resolution_tools: Dict[str, List[str]] = field(default_factory=dict)  # agent_id -> [tool_names]
    is_resolved: bool = False
    resolution_outcome: str = ""
    created_turn: int = 0
    
    def __post_init__(self):
        """Validate event data after initialization."""
        if not self.event_id:
            raise ValueError("PriorityActionEvent must have a valid event_id")
        if not self.event_type:
            raise ValueError("PriorityActionEvent must have a valid event_type")
        if not self.involved_agents:
            raise ValueError("PriorityActionEvent must have at least one involved agent")


class PriorityActionHandler(ABC):
    """
    Abstract base class for handling specific types of priority actions.
    
    Each priority action type (trade, diplomacy, crisis) should have its own
    handler that defines the context messages, tools, and resolution mechanics.
    """
    
    @abstractmethod
    def generate_context_message(self, event: PriorityActionEvent, agent_id: str) -> str:
        """
        Generate the context message that will be added to the agent's message history.
        
        Args:
            event: The priority action event
            agent_id: ID of the agent receiving the context
            
        Returns:
            Context message explaining the urgent situation
        """
        pass
    
    @abstractmethod
    def create_conversation_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """
        Create conversation tools (like speak()) for multi-agent discussions.
        
        Args:
            event: The priority action event
            agent_id: ID of the agent receiving the tools
            
        Returns:
            List of conversation tools for this agent
        """
        pass
    
    @abstractmethod
    def create_resolution_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """
        Create resolution tools that agents can use to conclude the priority action.
        
        Args:
            event: The priority action event
            agent_id: ID of the agent receiving the tools
            
        Returns:
            List of resolution tools for this agent
        """
        pass
    
    def get_situation_guidance(self, event: PriorityActionEvent, agent_id: str) -> str:
        """
        Return situation-specific guidance text to inject into the agent's turn context
        while this event is active. Return empty string for no injection.
        Subclasses override this to provide targeted behavioural guidance.
        """
        return ""

    @abstractmethod
    def execute_resolution(self, event: PriorityActionEvent, resolution_data: Dict[str, Any]) -> str:
        """
        Execute the resolution of the priority action based on agent decisions.
        
        Args:
            event: The priority action event being resolved
            resolution_data: Data from agent resolution tool usage
            
        Returns:
            Resolution outcome message
        """
        pass


class PriorityActionEventProcessor:
    """
    Main processor for handling priority action events.
    
    Integrates seamlessly with existing AI components by adding messages
    to their conversation history and providing specialized tools during
    priority action resolution.
    """
    
    def __init__(self, simulation):
        """
        Initialize the priority action event processor.
        
        Args:
            simulation: Reference to the main simulation object
        """
        self.simulation = simulation
        self.active_events: List[PriorityActionEvent] = []
        self.resolution_handlers: Dict[str, PriorityActionHandler] = {}
        
        # Track conversation managers for active events
        self._conversation_managers: Dict[str, 'ConversationManager'] = {}
    
    def register_handler(self, event_type: str, handler: PriorityActionHandler):
        """
        Register a handler for a specific event type.
        
        Args:
            event_type: The event type this handler processes
            handler: The handler instance
        """
        self.resolution_handlers[event_type] = handler
        print(f"🎯 Registered priority action handler for '{event_type}'")
    
    def add_event(self, event: PriorityActionEvent):
        """
        Add a new priority action event to the processing queue.
        
        Args:
            event: The priority action event to add
        """
        self.active_events.append(event)
        print(f"🚨 Priority action event added: {event.event_type} ({event.event_id})")
    
    async def process_all_events(self) -> List[str]:
        """
        Process all active priority action events.

        Events whose involved_agents sets are disjoint are independent and run
        concurrently. Events that share an agent are serialised to prevent
        concurrent mutation of the same message history.
        """
        if not self.active_events:
            return []

        # Partition events into parallel batches.
        # Each batch is a maximal set of mutually independent events;
        # within a batch all events can run concurrently.
        batches: List[List[PriorityActionEvent]] = []
        for event in self.active_events:
            placed = False
            for batch in batches:
                # Can add to this batch if no agent overlap with any event already in it
                batch_agents = set()
                for e in batch:
                    batch_agents.update(e.involved_agents)
                if not batch_agents.intersection(event.involved_agents):
                    batch.append(event)
                    placed = True
                    break
            if not placed:
                batches.append([event])

        all_results: List[str] = []
        events_to_remove: List[PriorityActionEvent] = []

        for batch in batches:
            async def _run(ev):
                try:
                    return await self.process_single_event(ev), ev
                except Exception as exc:
                    msg = f"Error processing priority action {ev.event_id}: {exc}"
                    print(f"❌ {msg}")
                    ev.is_resolved = True
                    return msg, ev

            batch_outcomes = await asyncio.gather(*[_run(e) for e in batch])
            for result, ev in batch_outcomes:
                all_results.append(result)
                if ev.is_resolved:
                    events_to_remove.append(ev)

        for event in events_to_remove:
            if event in self.active_events:
                self.active_events.remove(event)
            if event.event_id in self._conversation_managers:
                del self._conversation_managers[event.event_id]

        return all_results
    
    async def process_single_event(self, event: PriorityActionEvent) -> str:
        """
        Process a single priority action event.
        
        Args:
            event: The priority action event to process
            
        Returns:
            Result message from processing the event
        """
        # Get handler for this event type
        handler = self.resolution_handlers.get(event.event_type)
        if not handler:
            event.is_resolved = True
            event.resolution_outcome = f"No handler registered for event type: {event.event_type}"
            return event.resolution_outcome
        
        # Add context messages to all involved agents
        self._add_context_to_agents(event, handler)
        
        # Handle conversation if enabled
        if event.allows_conversation and not event.is_resolved:
            await self._handle_conversation(event, handler)
        
        # Get resolution decisions from agents if not already resolved
        if not event.is_resolved:
            await self._get_resolution_decisions(event, handler)
        
        # Execute final resolution
        if event.is_resolved and handler:
            try:
                outcome = handler.execute_resolution(event, event.context_data)
                event.resolution_outcome = outcome
                
                # Add resolution outcome to all involved agents
                self._add_resolution_outcome_to_agents(event)
                
                return f"Resolved {event.event_type}: {outcome}"
            except Exception as e:
                error_msg = f"Failed to execute resolution: {e}"
                event.resolution_outcome = error_msg
                return error_msg
        
        return f"Processing {event.event_type} (ongoing)"
    
    def _add_context_to_agents(self, event: PriorityActionEvent, handler: PriorityActionHandler):
        """
        Add context messages to all involved agents' message histories.
        
        Args:
            event: The priority action event
            handler: The handler for this event type
        """
        for agent_id in event.involved_agents:
            entity = self.simulation.entity_manager.get_entity(agent_id)
            if not entity:
                continue
            
            ai_component = entity.get_component(AIComponent)
            if not ai_component:
                continue
            
            # Generate context message for this agent
            context_message = handler.generate_context_message(event, agent_id)

            # Add to message history
            ai_component.messages.append({
                "role": "user",
                "content": context_message
            })

            # Inject situation-specific guidance if the handler provides it
            situation_guidance = handler.get_situation_guidance(event, agent_id)
            if situation_guidance:
                ai_component.inject_situation(
                    event.event_type,
                    situation_guidance,
                    expires_after_turns=0,  # manual clear on resolution
                )
    
    async def _handle_conversation(self, event: PriorityActionEvent, handler: PriorityActionHandler):
        """
        Handle multi-agent conversation for the priority action.
        
        Args:
            event: The priority action event
            handler: The handler for this event type
        """
        from feudal_sim.core.conversation_manager import ConversationManager
        
        # Create conversation manager for this event
        conversation_manager = ConversationManager(event, self.simulation)
        self._conversation_managers[event.event_id] = conversation_manager
        
        # Run conversation rounds
        for round_num in range(event.max_conversation_rounds):
            if event.is_resolved:
                break
            
            print(f"🗣️ Starting conversation round {round_num + 1}/{event.max_conversation_rounds} for {event.event_type}")
            
            # Each agent gets a turn to speak in this round
            continue_conversation = await self._handle_conversation_round(
                event, handler, conversation_manager, round_num
            )
            
            if not continue_conversation or event.is_resolved:
                break
    
    async def _handle_conversation_round(self, event: PriorityActionEvent, 
                                       handler: PriorityActionHandler,
                                       conversation_manager, round_num: int) -> bool:
        """
        Handle one round of multi-agent conversation.
        
        Args:
            event: The priority action event
            handler: The handler for this event type
            conversation_manager: The conversation manager instance
            round_num: Current round number (0-indexed)
            
        Returns:
            True if conversation should continue, False otherwise
        """
        conversation_manager.round_counter = round_num
        
        # Each agent gets a turn to speak in this round
        for agent_id in event.involved_agents:
            if event.is_resolved:
                break
            
            entity = self.simulation.entity_manager.get_entity(agent_id)
            if not entity:
                continue
            
            ai_component = entity.get_component(AIComponent)
            if not ai_component:
                continue
            
            # Create conversation tools (speak + resolution)
            conversation_tools = []
            conversation_tools.extend(handler.create_conversation_tools(event, agent_id))
            conversation_tools.extend(handler.create_resolution_tools(event, agent_id))
            
            # Add conversation tools to the conversation manager's speak tool
            speak_tool = conversation_manager.create_speak_tool(agent_id)
            conversation_tools.insert(0, speak_tool)  # Add speak tool first
            
            # Add turn prompt
            ai_component.messages.append({
                "role": "user",
                "content": f"Your turn to speak in the negotiation (Round {round_num + 1}/{event.max_conversation_rounds}). Use speak() to communicate or a resolution tool to conclude."
            })
            
            # Stop as soon as any resolution tool fires — prevents post-declaration spam
            resolution_tool_names = [
                t.name for t in handler.create_resolution_tools(event, agent_id)
                if hasattr(t, 'name')
            ]
            await self._get_agent_response_with_tools(
                ai_component, conversation_tools, stop_at=resolution_tool_names
            )
            
            if event.is_resolved:
                break
        
        return not event.is_resolved
    
    async def _get_resolution_decisions(self, event: PriorityActionEvent, handler: PriorityActionHandler):
        """
        Get resolution decisions from agents if no conversation or conversation ended.
        
        Args:
            event: The priority action event
            handler: The handler for this event type
        """
        # If no conversation was held, give agents resolution tools directly
        for agent_id in event.involved_agents:
            if event.is_resolved:
                break
            
            entity = self.simulation.entity_manager.get_entity(agent_id)
            if not entity:
                continue
            
            ai_component = entity.get_component(AIComponent)
            if not ai_component:
                continue
            
            # Create resolution tools
            resolution_tools = handler.create_resolution_tools(event, agent_id)
            
            # Add resolution prompt
            ai_component.messages.append({
                "role": "user",
                "content": "Make your decision regarding this urgent matter."
            })
            
            # Get agent response with resolution tools
            await self._get_agent_response_with_tools(ai_component, resolution_tools)
    
    async def _get_agent_response_with_tools(self, ai_component: AIComponent, tools: List,
                                              stop_at: List[str] = None):
        """
        Get agent response with specialized tools temporarily added.
        Stops as soon as any tool in `stop_at` is called (in addition to end_turn).
        """
        if not ai_component.agent or not ai_component.is_enabled:
            return

        from agents.agent import StopAtTools

        original_tools = ai_component.agent.tools
        original_behavior = ai_component.agent.tool_use_behavior

        stop_names = list({'end_turn'} | set(stop_at or []))
        ai_component.agent.tools = tools
        ai_component.agent.tool_use_behavior = StopAtTools(stop_at_tool_names=stop_names)

        try:
            await ai_component.make_decisions()
        finally:
            ai_component.agent.tools = original_tools
            ai_component.agent.tool_use_behavior = original_behavior
    
    def _add_resolution_outcome_to_agents(self, event: PriorityActionEvent):
        """
        Add the resolution outcome to all involved agents' message histories.
        
        Args:
            event: The resolved priority action event
        """
        resolution_message = f"RESOLUTION: {event.resolution_outcome}"
        
        for agent_id in event.involved_agents:
            entity = self.simulation.entity_manager.get_entity(agent_id)
            if not entity:
                continue
            
            ai_component = entity.get_component(AIComponent)
            if not ai_component:
                continue
            
            # Clear the situation context now that the event is resolved
            ai_component.clear_situation(event.event_type)

            # Add resolution to message history
            ai_component.messages.append({
                "role": "user",
                "content": resolution_message
            })
    
    def get_active_event_count(self) -> int:
        """Get the number of active priority action events."""
        return len(self.active_events)
    
    def get_active_events(self) -> List[PriorityActionEvent]:
        """Get a copy of the active events list."""
        return self.active_events.copy()