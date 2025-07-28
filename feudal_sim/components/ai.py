"""
AIComponent - LLM-powered AI agents for entities in the feudal simulation.

Provides intelligent decision-making capabilities using OpenAI's Agents SDK.
Each AI agent maintains a message history that includes observations from
each phase, then makes decisions during the Actions phase.
"""

import os
from typing import List, Optional, Dict, Any
from agents import Agent, Runner, ModelSettings, set_trace_processors
import mlflow
from mlflow.openai._agent_tracer import MlflowOpenAgentTracingProcessor
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.ai.tools import get_tools_for_entity
from feudal_sim.ai.context import SimulationContext
from feudal_sim.ai.prompt_builder import PromptBuilder
from feudal_sim.ai.prompts import AgentType
from feudal_sim.ai.persona_generator import generate_agent_identity

set_trace_processors([MlflowOpenAgentTracingProcessor()])
mlflow.set_experiment("feudal_sim")

class AIComponent(Component):
    """
    AI-powered decision making component using OpenAI's Agents SDK.
    
    Maintains a proper message history that includes:
    - System message with agent instructions
    - Observation messages from production/events phases
    - Assistant responses with decisions
    """
    
    def __init__(self, name: str = None, agent_type: AgentType = AgentType.HOUSE_LORD, 
                 instructions: str = None, persona: str = None, entity_id: str = None,
                 house_name: str = None):
        """
        Initialize the AI component.
        
        Args:
            name: Display name for the AI agent (if None, will be generated)
            agent_type: Type of AI agent (HOUSE_LORD, SCOUT, GENERAL, etc.)
            instructions: Optional static system prompt (if provided, overrides dynamic prompt)
            persona: Optional persona section to include in dynamic prompt (if None, will be generated)
            entity_id: ID of the entity this component belongs to
            house_name: Optional house name for context in generation
        """
        super().__init__(entity_id)
        
        # Agent configuration
        self.agent_name = name  # May be None initially, will be set during initialization
        self.agent_type = agent_type
        self.static_instructions = instructions  # Optional override
        self.persona = persona  # May be None initially, will be set during initialization
        self.house_name = house_name  # For generation context
        
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
        self.messages = []
    
    def _initialize_agent(self):
        """Initialize the OpenAI agent with tools based on available components."""
        if self.agent is not None:
            return  # Already initialized
            
        try:
            # Check for OpenAI API key
            if not os.getenv('OPENAI_API_KEY'):
                print(f"⚠️  Warning: OPENAI_API_KEY not set. AI agent will be disabled.")
                self.is_enabled = False
                return
            
            # Determine house name for generation context
            house_name = self._get_house_name_context()
            
            # Generate name and/or persona if not provided
            self._ensure_name_and_persona(house_name)
            
            # Get available tools based on entity components
            tools = self._get_available_tools()
            
            # Generate instructions using PromptBuilder or use static instructions
            if self.static_instructions:
                instructions = self.static_instructions
                print(f"🤖 Using static instructions for {self.agent_name}")
            else:
                # Use PromptBuilder to generate dynamic instructions
                prompt_builder = PromptBuilder(self.entity, self.agent_type, self.persona)
                instructions = prompt_builder.build_prompt(tools)
                print(f"🤖 Generated dynamic instructions for {self.agent_name} ({self.agent_type.value})")
            
            # Create the agent with tools
            self.agent = Agent[SimulationContext](
                name=self.agent_name,
                instructions=instructions,
                tools=tools,
                model=config.get("simulation.ai.model", "gpt-4o-mini"),
                # DEBUG TOOLS
                model_settings=ModelSettings(
                    tool_choice="required"
                ),
                # tool_use_behavior="stop_on_first_tool",
                # reset_tool_choice=False
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
        Get available tools using the unified toolset registry from tools.py.
        
        Returns:
            List of tool functions available to this AI agent
        """
        if not self.entity:
            print(f"   No entity available for {self.agent_name}")
            return []
        
        # Determine entity type based on agent type and entity characteristics
        entity_type = self._determine_entity_type()
        
        print(f"   {self.agent_name}: Detected entity type '{entity_type}'")
        
        # Get tools using the unified toolset registry
        tools = get_tools_for_entity(self.entity, entity_type)
        
        print(f"   {self.agent_name}: Created {len(tools)} tools via {entity_type} toolset")
        
        # Apply tool filtering from config
        if config.get("simulation.ai.disabled_tools", []):
            disabled_tools = config.get("simulation.ai.disabled_tools", [])
            original_count = len(tools)
            tools = [tool for tool in tools if getattr(tool, 'name', 'unknown') not in disabled_tools]
            if len(tools) != original_count:
                print(f"   {self.agent_name}: Filtered out {original_count - len(tools)} disabled tools")

        return tools
    
    def _determine_entity_type(self) -> str:
        """
        Determine the entity type for tool selection based on agent type and components.
        
        Returns:
            String representing the entity type for tool factory lookup
        """
        # Use agent type as primary indicator
        if self.agent_type == AgentType.HOUSE_LORD:
            return 'house'
        elif self.agent_type == AgentType.GENERAL:
            return 'general'
        elif self.agent_type == AgentType.SCOUT:
            return 'scout'
        elif self.agent_type == AgentType.MERCHANT:
            return 'caravan'  # Map merchant to caravan toolset
        elif self.agent_type == AgentType.DIPLOMAT:
            return 'house'    # Diplomats use house-like tools for now
        
        # Fallback: try to detect based on components
        from feudal_sim.components.position import PositionComponent
        
        if self.entity.has_component(PositionComponent):
            # If entity has position, it's likely a mobile unit
            if (self.entity.has_component(PopulationComponent) and 
                self.entity.has_component(TerritoryComponent)):
                return 'house'  # Has territory and population = house
            else:
                return 'general'  # Positioned but no territory = general/mobile unit
        else:
            # No position component = likely a house
            return 'house'
    
    def _get_house_name_context(self) -> str:
        """Get house name context for generation."""
        # Use explicitly provided house name first
        if self.house_name:
            return self.house_name
        
        # Try to infer from entity name
        if self.entity and hasattr(self.entity, 'name'):
            return self.entity.name
        
        # Fall back to entity_id
        return self.entity_id if self.entity_id else None
    
    def _ensure_name_and_persona(self, house_name: str):
        """Generate name and/or persona if not provided."""
        # Generate both name and persona if neither provided
        if not self.agent_name and not self.persona:
            generated_name, generated_persona = generate_agent_identity(self.agent_type, house_name)
            self.agent_name = generated_name
            self.persona = generated_persona
            print(f"🎲 Generated identity: {self.agent_name} with matching persona")
        
        # Generate only name if needed (fallback approach)  
        elif not self.agent_name:
            from feudal_sim.ai.persona_generator import _get_fallback_name
            self.agent_name = _get_fallback_name(self.agent_type, house_name)
            print(f"🎲 Generated fallback name: {self.agent_name}")
        
        # Generate only persona if needed (fallback approach)
        elif not self.persona:
            from feudal_sim.ai.persona_generator import _get_fallback_persona
            self.persona = _get_fallback_persona(self.agent_name, self.agent_type, house_name)
            print(f"🎲 Generated fallback persona for: {self.agent_name}")
        
        # Fallback name if generation failed
        if not self.agent_name:
            role_name = self.agent_type.value.replace('_', ' ').title()
            house_context = f" of House {house_name}" if house_name else ""
            self.agent_name = f"{role_name}{house_context}"
    
    def add_observation(self, observation: str, phase: str = None, pending: bool = True):
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
            
        if pending:
            self.pending_observations.append(formatted_obs)
        else:
            self.messages.append({
                "role": "user",
                "content": formatted_obs
            })
        
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
                      game_state: Dict[str, Any] = None, hex_grid=None, 
                      entity_manager=None, simulation=None):
        """
        Update the simulation context for the agent.
        
        Args:
            current_turn: Current turn number
            current_phase: Current phase name (production, actions, events, cleanup)
            current_season: Current season name
            current_year: Current year
            game_state: Additional game state information
            hex_grid: HexGrid instance for map operations
            entity_manager: EntityManager for inter-entity operations
            simulation: Reference to main simulation object
        """
        self.context = SimulationContext(
            entity_id=self.entity_id,
            entity_name=self.entity.name if self.entity else self.entity_id,
            current_turn=current_turn,
            current_phase=current_phase,
            current_season=current_season,
            current_year=current_year,
            game_state=game_state or {},
            hex_grid=hex_grid,
            entity_manager=entity_manager,
            simulation=simulation
        )
    
    async def make_decisions(self) -> str:
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
            print(f"👀 [{self.agent_name}] {turn_message}")
            
            # Run the agent with full message history
            if config.get("simulation.ai.enabled", True):
                result = await Runner.run(
                    starting_agent=self.agent,
                    input=self.messages,  # Pass the message list directly
                    context=self.context
                )
            
                # Add the AI's decision to message history
                print("Len of new items: ", len(result.new_items))
                self.messages = result.to_input_list()
            else:
                print(f"🤖 {self.agent_name} is disabled, skipping decision making")
                return "AI is disabled"
            
            # Show only new messages from this turn
            if hasattr(result, 'new_items') and result.new_items:
                for item in result.new_items:
                    # check if has attr
                    if hasattr(item, 'output'):
                        print(f"🤖 {self.agent_name} {item.output}")
                    if hasattr(item.raw_item, 'content'):
                        print(f"🤖 {self.agent_name} {item.raw_item.content[0].text}")
                    if hasattr(item.raw_item, 'arguments'):
                        print(f"🤖 {self.agent_name} {item.raw_item.name} {item.raw_item.arguments}")
            else:
                print(f"🤖 {self.agent_name} decision: {result.final_output}")
            
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

        # print observations
        for obs in self.pending_observations:
            print(f"👀 {self.agent_name} {obs}")

        self.pending_observations.clear()
    
    def _generate_turn_context_message(self) -> str:
        """
        Generate the current turn context message.
        
        Returns:
            Turn context message for the current Actions phase
        """
        if not self.context:
            return "No context available."
        
        # Base turn information
        context_parts = [
            f"Week {self.context.current_turn} - {self.context.current_phase.title()} Phase",
            f"{self.context.current_season.title()}, Year {self.context.current_year}",
            ""
        ]
        
        # Add current resource and population status
        if self.entity:
            # Get resource status
            resource_component: ResourceComponent = self.entity.get_component(ResourceComponent)
            if resource_component:
                resources = resource_component.resources.to_dict()
                context_parts.append(f"Resources: {resources['food']:.1f} food, {resources['material']:.1f} material, {resources['metal']:.1f} metal, {resources['gold']:.1f} gold")
            
            # Get population status
            population_component: PopulationComponent = self.entity.get_component(PopulationComponent)
            if population_component:
                context_parts.append(f"Population: {population_component.population}, Loyalty: {population_component.loyalty:.1f}")
            
            # Get territory status
            territory_component: TerritoryComponent = self.entity.get_component(TerritoryComponent)
            if territory_component:
                territory_status = territory_component.get_territory_status()
                context_parts.append(f"Territory: {territory_status['territory_size']} tiles, {territory_status['pending_expansions']} pending expansions")
            
            context_parts.append("")  # Empty line before question
        
        context_parts.append("What actions do you take this turn?")
        
        return "\n".join(context_parts)
    
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