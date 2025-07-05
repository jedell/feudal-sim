"""
AIComponent - LLM-powered AI agents for entities in the feudal simulation.

Provides intelligent decision-making capabilities using OpenAI's Agents SDK.
Each AI agent maintains a message history that includes observations from
each phase, then makes decisions during the Actions phase.
"""

import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from agents import Agent, Runner, ModelSettings
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType


@dataclass
class SimulationContext:
    """
    Context object passed to OpenAI agents containing current simulation state.
    """
    entity_id: str
    entity_name: str
    current_turn: int
    current_phase: str
    current_season: str
    current_year: int
    game_state: Dict[str, Any] = field(default_factory=dict)


class AIComponent(Component):
    """
    AI-powered decision making component using OpenAI's Agents SDK.
    
    Maintains a proper message history that includes:
    - System message with agent instructions
    - Observation messages from production/events phases
    - Assistant responses with decisions
    """
    
    def __init__(self, name: str, instructions: str, entity_id: str = None):
        """
        Initialize the AI component.
        
        Args:
            name: Display name for the AI agent
            instructions: System prompt/personality for the agent
            entity_id: ID of the entity this component belongs to
        """
        super().__init__(entity_id)
        
        # Agent configuration
        self.agent_name = name
        self.instructions = instructions
        
        # Message history for LLM context (proper OpenAI format)
        self.messages: List[Dict[str, str]] = []
        
        # Current turn observations (added during phases, processed during Actions)
        self.pending_observations: List[str] = []
        
        # AI agent state
        self.agent: Optional[Agent] = None
        self.context: Optional[SimulationContext] = None
        self.is_enabled = True
        
        # Initialize message history with system message
        self._initialize_messages()
        
        # Note: Agent initialization is deferred until entity is set
    
    def _initialize_messages(self):
        """Initialize the message history with the system prompt."""
        self.messages = [
            {
                "role": "system",
                "content": self.instructions
            }
        ]
    
    def _initialize_agent(self):
        """Initialize the OpenAI agent with tools based on available components."""
        if self.agent is not None:
            return  # Already initialized
            
        try:
            # Check for OpenAI API key
            if not os.getenv('OPENAI_API_KEY'):
                print(f"⚠️  Warning: OPENAI_API_KEY not set. AI agent '{self.agent_name}' will be disabled.")
                self.is_enabled = False
                return
            
            # Get available tools based on entity components
            tools = self._get_available_tools()
            
            # Create the agent with tools
            self.agent = Agent(
                name=self.agent_name,
                instructions=self.instructions,
                tools=tools,
                model="gpt-4o-mini",
                model_settings=ModelSettings(
                    tool_choice="required"
                )
            )
            
            print(f"🤖 Initialized AI agent: {self.agent_name} with {len(tools)} tools")
            
        except Exception as e:
            print(f"❌ Failed to initialize AI agent '{self.agent_name}': {e}")
            self.is_enabled = False
    
    def on_added_to_entity(self, entity):
        """Called when this component is added to an entity."""
        super().on_added_to_entity(entity)
        # Now we can initialize the agent with proper tools
        self._initialize_agent()
    
    def _get_available_tools(self):
        """
        Get available tools based on the entity's components.
        
        Returns:
            List of tool functions available to this AI agent
        """
        tools = []
        
        # Only add tools if we have an entity to work with
        if not self.entity:
            print(f"   No entity available for {self.agent_name}")
            return tools
        
        # Check for RookeryComponent and add send_raven tool
        from feudal_sim.components.rookery import RookeryComponent
        if self.entity.has_component(RookeryComponent):
            print(f"   {self.agent_name}: Found RookeryComponent, creating send_raven tool")
            from feudal_sim.ai.tools import create_send_raven_tool
            tool = create_send_raven_tool(self.entity)
            tools.append(tool)
            print(f"   {self.agent_name}: Created send_raven tool: {tool}")
        else:
            print(f"   {self.agent_name}: No RookeryComponent found")
        
        # Future: Check for other components and add relevant tools
        # if self.entity.has_component(MilitaryComponent):
        #     tools.append(create_dispatch_army_tool(self.entity))
        # if self.entity.has_component(EconomyComponent):
        #     tools.append(create_collect_taxes_tool(self.entity))
        
        print(f"   {self.agent_name}: Total tools created: {len(tools)}")
        return tools
    
    def add_observation(self, observation: str, phase: str = None):
        """
        Add an observation from the current phase.
        These will be processed into the message history during Actions phase.
        
        Args:
            observation: Natural language description of what happened
            phase: Which phase this observation came from (production, events, etc.)
        """
        formatted_obs = f"{observation}"
        if phase:
            formatted_obs = f"[{phase.title()}] {observation}"
            
        self.pending_observations.append(formatted_obs)
        
        # Emit event for tracking
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='observation_added',
                entity_name=self.entity.name if self.entity else self.entity_id,
                observation=observation,
                phase=phase
            )
    
    def update_context(self, current_turn: int, current_phase: str, 
                      current_season: str, current_year: int, 
                      game_state: Dict[str, Any] = None):
        """
        Update the simulation context for the agent.
        
        Args:
            current_turn: Current turn number
            current_phase: Current phase name (production, actions, events, cleanup)
            current_season: Current season name
            current_year: Current year
            game_state: Additional game state information
        """
        self.context = SimulationContext(
            entity_id=self.entity_id,
            entity_name=self.entity.name if self.entity else self.entity_id,
            current_turn=current_turn,
            current_phase=current_phase,
            current_season=current_season,
            current_year=current_year,
            game_state=game_state or {}
        )
    
    def make_decisions(self) -> str:
        """
        Have the AI agent process all pending observations and make decisions.
        Called during the Actions phase.
        
        Returns:
            String response from the AI agent describing their decisions
        """
        if not self.is_enabled or not self.agent:
            return f"{self.agent_name} is not available (no API key or initialization failed)"
        
        if not self.context:
            return f"{self.agent_name} has no context - cannot make decisions"
        
        try:
            # Add pending observations to message history
            self._process_pending_observations()
            
            # Add current turn context as a user message
            turn_message = self._generate_turn_context_message()
            self.messages.append({
                "role": "user", 
                "content": turn_message
            })
            
            # Run the agent with full message history
            result = Runner.run_sync(
                starting_agent=self.agent,
                input=self.messages,  # Pass the message list directly
                context=self.context
            )
            
            # Add the AI's decision to message history
            self.messages = result.to_input_list()

            print(f"🤖 {self.agent_name} messages: {self.messages}")
            
            # Clear pending observations since they're now in history
            self.pending_observations.clear()
            
            # Emit event for decision made
            if event_bus:
                event_bus.emit(
                    EventType.VALUE_CHANGED,
                    self,
                    change_type='decision_made',
                    entity_name=self.context.entity_name,
                    decision=result.final_output,
                    turn=self.context.current_turn
                )
            
            return result.final_output
            
        except Exception as e:
            error_msg = f"Error in AI decision making for {self.agent_name}: {e}"
            print(f"❌ {error_msg}")
            return error_msg
    
    def _process_pending_observations(self):
        """
        Add all pending observations to the message history as user messages.
        """
        if not self.pending_observations:
            return
        
        # Add each observation as a separate user message
        for obs in self.pending_observations:
            self.messages.append({
                "role": "user",
                "content": obs
            })
    
    def _generate_turn_context_message(self) -> str:
        """
        Generate the current turn context message.
        
        Returns:
            Turn context message for the current Actions phase
        """
        if not self.context:
            return "No context available."
        
        return (
            f"Turn {self.context.current_turn} - {self.context.current_phase.title()} Phase\n"
            f"{self.context.current_season.title()}, Year {self.context.current_year}\n\n"
            f"What actions do you take this turn?"
        )
    
    def get_recent_messages(self, last_n: int = 10) -> List[Dict[str, str]]:
        """
        Get recent messages from the conversation history.
        
        Args:
            last_n: Number of recent messages to return
            
        Returns:
            List of recent message dictionaries
        """
        return self.messages[-last_n:] if self.messages else []
    
    def get_message_summary(self) -> List[str]:
        """
        Get a human-readable summary of the message history.
        
        Returns:
            List of formatted message summaries
        """
        summary = []
        for i, msg in enumerate(self.messages):
            role = msg["role"]
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            
            if role == "system":
                summary.append(f"[System] {content}")
            elif role == "user":
                summary.append(f"[Observation] {content}")
            elif role == "assistant":
                summary.append(f"[Decision] {content}")
        
        return summary
    
    def get_ai_status(self) -> Dict[str, Any]:
        """
        Get current AI status for debugging/display.
        
        Returns:
            Dictionary with AI component status information
        """
        return {
            'agent_name': self.agent_name,
            'is_enabled': self.is_enabled,
            'has_agent': self.agent is not None,
            'pending_observations': len(self.pending_observations),
            'message_count': len(self.messages),
            'has_context': self.context is not None,
            'current_turn': self.context.current_turn if self.context else None
        }
    
    def update(self, dt: float, event_bus=None):
        """
        Component update method - not used for main AI logic.
        AI decisions happen during Actions phase via make_decisions().
        """
        # Could be used for periodic maintenance if needed
        pass