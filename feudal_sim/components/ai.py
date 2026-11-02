"""
AIComponent - LLM-powered AI agents for entities in the feudal simulation.

Provides intelligent decision-making capabilities using OpenAI's Agents SDK.
Each AI agent maintains a message history that includes observations from
each phase, then makes decisions during the Actions phase.
"""

import os
from collections import deque
from typing import List, Optional, Dict, Any, Deque
from feudal_sim.core.logger import get_logger
from agents import Agent, Runner, set_trace_processors, ModelSettings
from agents.agent import StopAtTools
from agents.model_settings import Reasoning  # type: ignore[attr-defined]
from agents.items import (
    ReasoningItem, MessageOutputItem, ToolCallItem, ToolCallOutputItem
)
import mlflow
from mlflow.openai._agent_tracer import MlflowOpenAgentTracingProcessor
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.components.position import PositionComponent
from feudal_sim.components.subagent_group import SubAgentGroup
from feudal_sim.components.intelligence import IntelligenceComponent
from feudal_sim.ai.tools.registry import get_tools_for_entity
from feudal_sim.ai.context import SimulationContext
from feudal_sim.ai.prompt_builder import PromptBuilder
from feudal_sim.ai.prompts import AgentType
from feudal_sim.ai.persona_generator import (
    generate_agent_identity, _get_fallback_name, _get_fallback_persona
)
from feudal_sim.ai.compaction import (
    CompactionSettings, compact_messages, should_compact, estimate_total_tokens,
)

log = get_logger(__name__)

# mlflow >=3.4 rejects the legacy ./mlruns file store; default to sqlite
# when no tracking destination is configured (run.sh may point at a server)
if not os.environ.get("MLFLOW_TRACKING_URI"):
    mlflow.set_tracking_uri("sqlite:///mlruns.db")
set_trace_processors([MlflowOpenAgentTracingProcessor()])
mlflow.set_experiment("feudal_sim")

MAX_TURNS_HOUSE = config.get("simulation.ai.max_turns_house", 15)
MAX_TURNS_GENERAL = config.get("simulation.ai.max_turns_general", 20)
MAX_TURNS = MAX_TURNS_HOUSE  # default; overridden per agent type in make_decisions()

# Shared client for OpenAI-compatible third-party providers (Fireworks)
_fireworks_client = None


def resolve_model(model_name: str):
    """Resolve a config model string to an Agents SDK model.

    Plain names ("gpt-5-mini-...") pass through to the default OpenAI
    provider. Names prefixed "fireworks/" route through Fireworks'
    OpenAI-compatible Chat Completions endpoint, e.g.
    "fireworks/accounts/fireworks/models/glm-5p2".
    Requires FIREWORKS_API_KEY in the environment.
    """
    if not model_name or not model_name.startswith("fireworks/"):
        return model_name
    global _fireworks_client
    if _fireworks_client is None:
        from openai import AsyncOpenAI
        _fireworks_client = AsyncOpenAI(
            base_url=os.environ.get("FIREWORKS_BASE_URL",
                                    "https://api.fireworks.ai/inference/v1"),
            api_key=os.environ["FIREWORKS_API_KEY"],
        )
    from agents import OpenAIChatCompletionsModel
    return OpenAIChatCompletionsModel(
        model=model_name.removeprefix("fireworks/"),
        openai_client=_fireworks_client,
    )

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

        # Rolling compaction summary — updated (not replaced) each compaction
        self._compaction_summary: Optional[str] = None
        self._compaction_settings: Optional[CompactionSettings] = None

        # Persistent strategic objectives
        self.current_objectives: List[str] = []

        # Persistent realm journal — last 5 significant events
        self.realm_journal: Deque[str] = deque(maxlen=10)

        # Snapshots for delta/trend computation
        self._resource_snapshot: Optional[Dict[str, float]] = None
        self._population_snapshot: Optional[Dict[str, float]] = None

        # Active situation contexts — injected into turn context while conditions hold.
        # Each entry: {'id': str, 'text': str, 'expires_turn': int | None}
        self._active_situations: List[Dict] = []
        
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
                log.warning("⚠️  Warning: OPENAI_API_KEY not set. AI agent will be disabled.")
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
                log.info(f"🤖 Using static instructions for {self.agent_name}")
            else:
                # Use PromptBuilder to generate dynamic instructions
                prompt_builder = PromptBuilder(self.entity, self.agent_type, self.persona)
                instructions = prompt_builder.build_prompt(tools)
                log.info(f"🤖 Generated dynamic instructions for {self.agent_name} ({self.agent_type.value})")
            
            model_name = (config.get(f"simulation.ai.models.{self.agent_type.value}")
                          or config.get("simulation.ai.model", "gpt-4.1-mini"))

            # Build model settings — reasoning effort if configured for this
            # agent type (OpenAI models only; third-party providers reject it)
            effort = config.get(f"simulation.ai.reasoning_effort.{self.agent_type.value}")
            if effort and not model_name.startswith("fireworks/"):
                model_settings = ModelSettings(reasoning=Reasoning(effort=effort))
            else:
                model_settings = ModelSettings()

            # Create the agent with tools
            self.agent = Agent[SimulationContext](
                name=self.agent_name,
                instructions=instructions + "\n\nGrounding: Use directional language (north, NE, etc.) and avoid raw grid coordinates in observations and plans.",
                tools=tools,
                model=resolve_model(model_name),
                model_settings=model_settings,
                tool_use_behavior=StopAtTools(
                    stop_at_tool_names=["end_turn"]
                )
            )
            
            log.info(f"🤖 Initialized AI agent: {self.agent_name} with {len(tools)} tools")
            
            # Seed mission/goal into message history for sub-agents (e.g., generals)
            try:
                group_comp = self.entity.get_component(SubAgentGroup)
                if group_comp and group_comp.mission_parameters:
                    mp = group_comp.mission_parameters
                    mission_text = (
                        f"Mission assigned: {mp.mission_type} | Orders: {mp.orders or 'none'} | "
                        f"Target: {mp.target_area or 'unspecified'} | Priority: {mp.priority}"
                    )
                    # Push as an initial observation so it’s retained in history
                    self.add_observation(mission_text, phase="Actions", pending=False)
            except Exception as e:
                log.warning(f"⚠️ Could not seed mission parameters for {self.agent_name}: {e}")

        except Exception as e:
            log.error(f"❌ Failed to initialize AI agent '{self.agent_name}': {e}")
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
            log.info(f"🎲 Generated identity: {self.agent_name} with matching persona")
        
        # Generate only name if needed (fallback approach)  
        elif not self.agent_name:
            self.agent_name = _get_fallback_name(self.agent_type, house_name)
            log.info(f"🎲 Generated fallback name: {self.agent_name}")
        
        # Generate only persona if needed (fallback approach)
        elif not self.persona:
            self.persona = _get_fallback_persona(self.agent_name, self.agent_type, house_name)
            log.info(f"🎲 Generated fallback persona for: {self.agent_name}")
        
        # Fallback name if generation failed
        if not self.agent_name:
            role_name = self.agent_type.value.replace('_', ' ').title()
            house_context = f" of House {house_name}" if house_name else ""
            self.agent_name = f"{role_name}{house_context}"
    
    def inject_situation(self, situation_id: str, text: str, expires_after_turns: int = 1):
        """
        Inject situation-specific guidance into the agent's turn context.

        The text appears prominently between message history and the state snapshot
        every turn the situation is active, guiding the agent's immediate behaviour.

        Args:
            situation_id: Unique key — re-injecting the same id refreshes/replaces it.
            text: Guidance text (what the situation is, what the agent should do).
            expires_after_turns: Auto-clear after this many turns (0 = manual clear only).
        """
        expires_turn = None
        if expires_after_turns > 0 and self.context:
            expires_turn = self.context.current_turn + expires_after_turns
        # Replace if already present
        self._active_situations = [s for s in self._active_situations if s['id'] != situation_id]
        self._active_situations.append({
            'id': situation_id,
            'text': text,
            'expires_turn': expires_turn,
        })

    def clear_situation(self, situation_id: str):
        """Remove a situation context by id."""
        self._active_situations = [s for s in self._active_situations if s['id'] != situation_id]

    def record_journal_entry(self, text: str) -> None:
        """Append a significant event to the persistent realm journal (max 5 entries)."""
        turn = self.context.current_turn if self.context else 0
        self.realm_journal.append(f"[Turn {turn}] {text}")

    def _expire_situations(self, current_turn: int):
        """Remove any situations that have passed their expiry turn."""
        self._active_situations = [
            s for s in self._active_situations
            if s['expires_turn'] is None or s['expires_turn'] > current_turn
        ]

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
            # Token-aware compaction before processing new observations
            await self._maybe_compact()

            # Add pending observations to message history
            self._process_pending_observations()
            
            # Add current turn context as a user message
            turn_message = self._generate_turn_context_message()
            self.messages.append({
                "role": "user", 
                "content": turn_message
            })
            log.info(f"👀 [{self.agent_name}] {turn_message}")
            
            # Run the agent with full message history
            if config.get("simulation.ai.enabled", True):
                agent_max_turns = MAX_TURNS_GENERAL if self.agent_type == AgentType.GENERAL else MAX_TURNS_HOUSE
                result = await Runner.run(
                    starting_agent=self.agent,
                    input=self.messages,
                    context=self.context,
                    max_turns=agent_max_turns
                )
            
                # Add the AI's decision to message history
                self.messages = result.to_input_list()
            else:
                log.info(f"🤖 {self.agent_name} is disabled, skipping decision making")
                return "AI is disabled"
            
            # Log all new items: reasoning summaries, tool calls, tool outputs, text responses
            if hasattr(result, 'new_items') and result.new_items:
                for item in result.new_items:
                    try:
                        if isinstance(item, ReasoningItem):
                            summaries = getattr(item.raw_item, 'summary', [])
                            if summaries:
                                text = ' '.join(s.text for s in summaries if hasattr(s, 'text'))
                                if text:
                                    log.info(f"💭 {self.agent_name} [thinking] {text[:400]}")
                        elif isinstance(item, ToolCallItem):
                            raw = item.raw_item
                            name = getattr(raw, 'name', '?')
                            args = getattr(raw, 'arguments', '')
                            log.info(f"🔧 {self.agent_name} {name}({args})")
                        elif isinstance(item, ToolCallOutputItem):
                            output = str(getattr(item, 'output', '')).strip()
                            if output:
                                log.info(f"   ↳ {output[:200]}")
                        elif isinstance(item, MessageOutputItem):
                            content = getattr(item.raw_item, 'content', [])
                            if isinstance(content, list) and content:
                                text = getattr(content[0], 'text', '')
                                if text:
                                    log.info(f"💬 {self.agent_name} {text[:400]}")
                    except Exception as _e:
                        log.warning(f"⚠️  Could not format agent output item: {_e}")

            # Always print final output summary if present
            if result.final_output:
                log.info(f"✅ {self.agent_name} turn complete: {str(result.final_output)[:200]}")
            
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
            log.error(f"❌ {error_msg}")
            return error_msg
    
    async def _maybe_compact(self):
        """Token-aware compaction with LLM summarization.

        Replaces the old message-count-based truncation. Estimates token usage,
        compacts only when approaching the model's context window, and uses an
        LLM call to produce a structured summary of dropped context that gets
        injected into the retained history. The summary is rolling — each
        compaction updates the previous one rather than starting over.
        """
        if not self.messages:
            return

        # Lazily build settings (per-agent-type overrides)
        if self._compaction_settings is None:
            agent_key = self.agent_type.value if self.agent_type else ""
            self._compaction_settings = CompactionSettings.from_config(agent_key)

        settings = self._compaction_settings

        if not should_compact(self.messages, settings):
            return

        tokens_before = estimate_total_tokens(self.messages)
        log.info(
            f"📦 [{self.agent_name}] Compaction triggered: "
            f"~{tokens_before:,} tokens (limit {settings.context_window - settings.reserve_tokens:,})"
        )

        # Resolve the model for the summarizer (reuse the agent's model)
        model = None
        if self.agent and hasattr(self.agent, 'model'):
            model = self.agent.model

        self.messages, result = await compact_messages(
            self.messages,
            settings,
            model=model,
            previous_summary=self._compaction_summary,
        )

        # Store rolling summary for next compaction's incremental update
        self._compaction_summary = result.summary

        # Also write to IntelligenceComponent for cross-compaction persistence
        if self.entity:
            try:
                intel = self.entity.get_component(IntelligenceComponent)
                if intel:
                    intel.add_note("Historical Record", result.summary)
            except Exception as e:
                log.warning(f"Failed to write compaction summary to intelligence: {e}")

    def _process_pending_observations(self):
        """
        Group pending observations by phase and emit one user message per phase.
        This produces coherent context blocks rather than disconnected single-line messages.
        """
        if not self.pending_observations:
            return

        # Parse phase prefix — format is "[Phase] content"
        phase_groups: Dict[str, List[str]] = {}
        unphased: List[str] = []

        for obs in self.pending_observations:
            if obs.startswith('[') and ']' in obs:
                bracket_end = obs.index(']')
                phase_name = obs[1:bracket_end]
                content = obs[bracket_end + 2:]  # skip '] '
                phase_groups.setdefault(phase_name, []).append(content)
            else:
                unphased.append(obs)

        # Emit in canonical phase order, then any extras
        for phase in ('Production', 'Events', 'Actions'):
            if phase not in phase_groups:
                continue
            items = phase_groups.pop(phase)
            body = "\n".join(f"• {item}" for item in items)
            message = f"[{phase} Update]\n{body}"
            self.messages.append({"role": "user", "content": message})
            log.info(f"👀 {self.agent_name} [{phase}] {len(items)} observation(s)")

        for phase, items in phase_groups.items():
            body = "\n".join(f"• {item}" for item in items)
            message = f"[{phase} Update]\n{body}"
            self.messages.append({"role": "user", "content": message})
            log.info(f"👀 {self.agent_name} [{phase}] {len(items)} observation(s)")

        if unphased:
            self.messages.append({"role": "user", "content": "\n".join(unphased)})

        self.pending_observations.clear()
    
    def _build_urgency_flags(self) -> List[str]:
        """Build urgency/warning flags based on current entity state."""
        flags = []
        if not self.entity:
            return flags

        # Lord/house flags
        population_component: PopulationComponent = self.entity.get_component(PopulationComponent)
        if population_component:
            loyalty = population_component.loyalty
            if loyalty < 40:
                flags.append(f"⚠️ CRITICAL: Population loyalty at {loyalty:.0f} — revolt imminent")
            elif loyalty < 60:
                flags.append(f"⚠️ WARNING: Population loyalty at {loyalty:.0f} — consider holding a feast")

        resource_component: ResourceComponent = self.entity.get_component(ResourceComponent)
        if resource_component:
            food = resource_component.resources.food
            if food < 50:
                flags.append(f"⚠️ WARNING: Food stores critically low ({food:.0f}) — population may starve")
            # Connect food crisis to deployed forces
            if food < 100:
                territory_component: TerritoryComponent = self.entity.get_component(TerritoryComponent)
                if territory_component and territory_component.deployed_generals:
                    total_deployed = sum(
                        g.get('soldiers_assigned', 0) + g.get('workers_assigned', 0)
                        for g in territory_component.deployed_generals
                    )
                    if total_deployed > 0:
                        flags.append(
                            f"⚠️ {total_deployed} people deployed in the field are not producing food "
                            f"— consider disbanding generals if starvation is imminent"
                        )

        # General flags
        from feudal_sim.components.subagent_group import SubAgentGroup
        group = self.entity.get_component(SubAgentGroup)
        if group:
            if group.morale < 30:
                flags.append(f"⚠️ CRITICAL: Troop morale at {group.morale}% — risk of desertion")
            if group.supplies < 20:
                flags.append(f"⚠️ WARNING: Supplies at {group.supplies}% — resupply needed")

        return flags

    @staticmethod
    def _loyalty_mood(loyalty: float) -> str:
        if loyalty < 40:
            return "revolt imminent"
        if loyalty < 55:
            return "grumbling"
        if loyalty < 70:
            return "content"
        if loyalty < 85:
            return "loyal"
        return "devoted"

    @staticmethod
    def _format_stat_line(label: str, current: float, previous: Optional[float],
                          depletion: bool = False, suffix: str = "") -> str:
        """Format a single stat with trend arrow, net change, and optional depletion estimate."""
        if previous is None:
            return f"{label}: {current:.0f}{suffix}"

        delta = current - previous
        if abs(delta) < 1:
            trend = "→"
            delta_text = " (stable)"
        elif delta > 0:
            trend = "↑"
            delta_text = f" +{delta:.0f}/wk"
        else:
            trend = "↓"
            delta_text = f" {delta:.0f}/wk"

        depletion_text = ""
        if depletion and delta < -0.5 and current > 0:
            weeks = current / abs(delta)
            if weeks <= 6:
                depletion_text = f"  (~{weeks:.0f} wk remaining)"

        return f"{label}: {current:.0f}  {trend}{delta_text}{depletion_text}{suffix}"

    def _render_active_route(self, group_comp) -> str:
        """Render (and validate) the general's standing itinerary. Cleared on
        arrival or when the destination is no longer valid — the general is
        told why instead of marching to a stale target."""
        route = getattr(group_comp, 'active_route', None) if group_comp else None
        if not route or not self.entity or not self.context:
            return ""
        hex_grid = getattr(self.context, 'hex_grid', None)
        pos_comp = self.entity.get_component(PositionComponent)
        if not hex_grid or not pos_comp or not pos_comp.position:
            return ""
        target = tuple(route.get('target') or ())
        purpose = route.get('purpose', 'destination')
        if len(target) != 2:
            group_comp.active_route = None
            return ""
        if tuple(pos_comp.position) == target:
            group_comp.active_route = None
            return (f"ARRIVED at your route target ({purpose}). "
                    f"Take the action you came for (e.g. build_outpost).")
        # Invalidate outpost-site routes whose ground has been taken
        tile = hex_grid.get_tile(*target)
        if 'outpost' in purpose:
            owner = getattr(tile, 'owner', None) if tile else None
            if tile is None or (owner is not None and
                                getattr(owner, 'id', None) != getattr(self.entity, 'house_id', None)) or \
                    getattr(tile, 'population_capacity', 0) >= 1000:
                group_comp.active_route = None
                return (f"Your planned route to the {purpose} is no longer valid — "
                        f"the ground has been claimed. Scan again (find_outpost_site).")
        try:
            from feudal_sim.components.pathfinding import PathfindingComponent
            from feudal_sim.utils.directions import path_to_directions
            pf = PathfindingComponent('route-render')
            path = pf.find_path(tuple(pos_comp.position), target, hex_grid,
                                entity_house_id=getattr(self.entity, 'house_id', None))
            if not path or len(path) < 2:
                group_comp.active_route = None
                return (f"Your route to the {purpose} is blocked — no path from here. "
                        f"Reconsider or scan again.")
            dirs = path_to_directions(path)
            return (f"Active route ({purpose}): {len(dirs)} step(s) remaining — "
                    f"move_along({dirs})")
        except Exception as e:
            log.warning(f"Active route render failed: {e}")
            return ""

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
        
        # Mission block for generals — rendered from component state every turn
        # so orders survive message-history compaction
        if self.agent_type == AgentType.GENERAL and self.entity:
            group_comp = self.entity.get_component(SubAgentGroup)
            mp = group_comp.mission_parameters if group_comp else None
            if mp:
                context_parts.append(f"Mission: {mp.mission_type} — {mp.orders or 'no specific orders'}")
                if mp.strategic_intent:
                    context_parts.append(f"Strategic intent: {mp.strategic_intent}")
                turns_in_field = self.context.current_turn - mp.assigned_turn
                if mp.assigned_turn and turns_in_field > 0:
                    context_parts.append(f"Orders issued turn {mp.assigned_turn} ({turns_in_field} turns ago)")
                context_parts.append("")

            # Active route: re-render the standing itinerary from current
            # position until arrival or invalidation — one-shot targets become
            # persistent marching orders
            route_block = self._render_active_route(group_comp)
            if route_block:
                context_parts.append(route_block)
                context_parts.append("")

            # Spatial memory: what this general already knows of the ground —
            # passive summary + local map from remembered observations, so the
            # field picture survives between turns without re-scanning
            from feudal_sim.components.terrain_observation import TerrainObservation
            terrain_obs = self.entity.get_component(TerrainObservation)
            if terrain_obs:
                passive = terrain_obs.get_passive_observation_text()
                if passive:
                    context_parts.append(passive)
                pos_comp = self.entity.get_component(PositionComponent)
                hex_grid = getattr(self.context, 'hex_grid', None)
                if pos_comp and pos_comp.position and hex_grid:
                    own_house = None
                    em = getattr(self.context, 'entity_manager', None)
                    house_id = getattr(self.entity, 'house_id', None)
                    if em and house_id:
                        parent = em.get_entity(house_id)
                        own_house = getattr(parent, 'name', None)
                    local_map = terrain_obs.render_local_map(
                        pos_comp.position, hex_grid, self.context.current_turn,
                        own_house_name=own_house)
                    if local_map:
                        context_parts.append(local_map)
                context_parts.append("")

        # Expire any stale situations
        self._expire_situations(self.context.current_turn)

        # Inject active situation contexts — highest priority, read before state snapshot
        if self._active_situations:
            for situation in self._active_situations:
                context_parts.append(f"[Situation: {situation['id']}]")
                context_parts.append(situation['text'])
                context_parts.append("")

        # Add urgency flags if any
        urgency_flags = self._build_urgency_flags()
        if urgency_flags:
            context_parts.extend(urgency_flags)
            context_parts.append("")

        # Add current resource and population status
        if self.entity:
            resource_component: ResourceComponent = self.entity.get_component(ResourceComponent)
            if resource_component:
                resources = resource_component.resources.to_dict()
                res_lines = []
                for key in ('food', 'material', 'metal', 'gold'):
                    val = resources[key]
                    prev = self._resource_snapshot.get(key) if self._resource_snapshot else None
                    res_lines.append(self._format_stat_line(key.title(), val, prev, depletion=True))
                context_parts.append("Resources:")
                context_parts.extend(f"  {line}" for line in res_lines)

            population_component: PopulationComponent = self.entity.get_component(PopulationComponent)
            if population_component:
                pop = population_component.population
                loyalty = population_component.loyalty
                prev_pop = self._population_snapshot.get('population') if self._population_snapshot else None
                prev_loyalty = self._population_snapshot.get('loyalty') if self._population_snapshot else None
                mood = self._loyalty_mood(loyalty)
                pop_line = self._format_stat_line("Population", pop, prev_pop, depletion=False)
                loyalty_line = self._format_stat_line("Loyalty", loyalty, prev_loyalty, depletion=False, suffix=f" ({mood})")
                context_parts.append(f"{pop_line}")
                context_parts.append(f"{loyalty_line}")
                food_per_capita = config.get('simulation.population.food_per_capita', 0.05)
                if pop > 0 and food_per_capita:
                    context_parts.append(
                        f"  Subsistence: ~{pop * food_per_capita:.0f} food/wk to feed {pop} subjects")

            territory_component: TerritoryComponent = self.entity.get_component(TerritoryComponent)
            if territory_component:
                hex_grid = self.context.hex_grid if self.context else None
                if hex_grid:
                    entity_mgr = self.context.entity_manager if self.context else None
                    context_parts.append(territory_component.format_realm_overview(hex_grid, entity_mgr))
                else:
                    territory_status = territory_component.get_territory_status()
                    context_parts.append(f"Territory: {territory_status['territory_size']} tiles, {territory_status['pending_expansions']} pending expansions")

            # Recent intelligence from compendium
            try:
                intel = self.entity.get_component(IntelligenceComponent)
                if intel:
                    topics = intel.list_topics()
                    recent_notes = []
                    for topic in topics:
                        raw = intel.read_topic(topic)
                        if raw:
                            # Take last 2 lines per topic to keep it concise
                            lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
                            recent_notes.extend(lines[-2:])
                    if recent_notes:
                        context_parts.append("Recent intelligence:")
                        for note in recent_notes[-4:]:  # cap at 4 total entries
                            context_parts.append(f"  {note}")
            except Exception as e:
                log.warning(f"⚠️ Could not read intelligence for {self.agent_name}: {e}")

            # Feast cooldown status — critical for loyalty planning
            if population_component and hasattr(population_component, 'last_feast_turn') and self.context:
                cooldown = config.get('simulation.population.feast.cooldown_turns', 1)
                turns_since = self.context.current_turn - population_component.last_feast_turn
                if turns_since >= cooldown:
                    context_parts.append("Feast: available now")
                else:
                    context_parts.append(f"Feast: available in {cooldown - turns_since} turn(s)")

            # Deployed generals and estimated upkeep
            if territory_component and territory_component.deployed_generals:
                n_generals = len(territory_component.deployed_generals)
                if n_generals:
                    upkeep_est = n_generals * config.get('simulation.subagents.supply_consumption_per_turn', 3) * 2
                    context_parts.append(f"Generals deployed: {n_generals}  (est. upkeep ~{upkeep_est} gold/turn)")

            context_parts.append("")  # Empty line before question

            # Update snapshots for next turn's delta computation
            if resource_component:
                self._resource_snapshot = dict(resource_component.resources.to_dict())
            if population_component:
                self._population_snapshot = {
                    'population': population_component.population,
                    'loyalty': population_component.loyalty,
                }

        # Inject realm journal (persistent event log)
        if self.realm_journal:
            context_parts.append("Recent History:")
            for entry in self.realm_journal:
                context_parts.append(f"  {entry}")
            context_parts.append("")

        # Inject current objectives if set
        if self.current_objectives:
            context_parts.append("Current Objectives:")
            for obj in self.current_objectives:
                context_parts.append(f"  - {obj}")
            context_parts.append("")

        agent_max_turns = MAX_TURNS_GENERAL if self.agent_type == AgentType.GENERAL else MAX_TURNS_HOUSE
        context_parts.append(f"You may take up to {agent_max_turns} actions this turn. Call end_turn() when done.")
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