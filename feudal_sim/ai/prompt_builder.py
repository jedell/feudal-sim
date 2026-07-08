"""
Dynamic prompt builder for AI agents.

Assembles prompts from three sources:
1. Static base template (core lore and rules) - varies by agent type
2. Available actions (from tools)
3. Component mechanics (from entity components)

Supports different AI agent types: House Lords, Scouts, Generals, etc.
"""

from typing import List
from feudal_sim.core.config import config
from feudal_sim.core.entities import Entity
from feudal_sim.core.logger import get_logger
from feudal_sim.ai.prompts import AgentType, get_agent_template
from feudal_sim.components.subagent_group import SubAgentGroup
from feudal_sim.components.position import PositionComponent

log = get_logger(__name__)


class PromptBuilder:
    """Builds dynamic AI prompts based on entity type, capabilities, and components."""
    
    def __init__(self, entity: Entity, agent_type: AgentType = AgentType.HOUSE_LORD, persona: str = None):
        self.entity = entity
        self.agent_type = agent_type
        self.persona = persona
    
    def build_prompt(self, tools: List = None) -> str:
        """Build complete prompt for this entity and agent type.
        
        Args:
            tools: List of available tools for this entity (optional)
        """
        base_template = self._get_base_template()
        available_actions = self._build_available_actions(tools)
        mechanics_sections = self._build_mechanics_sections()
        
        # Add persona if provided
        persona_section = self._build_persona_section()
        
        return base_template.format(
            available_actions=available_actions,
            mechanics_sections=mechanics_sections,
            persona_section=persona_section
        )
    
    def _get_base_template(self) -> str:
        """Get the base template for this agent type."""

        try:
            return get_agent_template(self.agent_type)
        except KeyError:
            # Fallback to house lord template if agent type not found
            return get_agent_template(AgentType.HOUSE_LORD)
    
    def _build_available_actions(self, tools: List = None) -> str:
        """Build the available actions section from provided tools.
        
        Args:
            tools: List of available tools for this entity
        """
        if not tools:
            return "No specific actions available this turn"
        
        # Extract action descriptions from tools
        actions = []
        for tool in tools:
            if hasattr(tool, 'action_description'):
                actions.append(tool.action_description)
        
        if not actions:
            return "No specific actions available this turn"
        
        return "\n".join(f"- {action}" for action in actions)
    
    def _build_victory_section(self) -> str:
        """Render the realm's victory conditions from config — the rules of
        the game are public knowledge; live standings are not."""
        conditions = []
        dominance_pct = config.get('simulation.victory.territorial_dominance_pct', 0.60)
        if dominance_pct:
            conditions.append(
                f"a house that controls more than {dominance_pct:.0%} of all land rules the realm")
        if config.get('simulation.victory.last_survivor', True):
            conditions.append(
                "a house that stands alone — the last with living subjects — rules by default")
        if not conditions:
            return ""
        return (
            "**How the Realm Is Won:**\n"
            f"The great game has an end: {'; or '.join(conditions)}. "
            "A year is 16 weeks — four turns to a season, four seasons to a year. "
            "Every season you do not advance toward victory, another house does."
        )

    def _build_mechanics_sections(self) -> str:
        """Build mechanics explanations from entity components."""
        if not self.entity:
            return ""

        mechanics = []

        # Victory conditions lead the universal laws — agents must know
        # what winning means
        victory_section = self._build_victory_section()
        if victory_section:
            mechanics.append(victory_section)

        # Get lore sections from all components
        for component in self.entity.get_all_components():
            if hasattr(component, 'get_lore_section'):
                lore_section = component.get_lore_section()
                if lore_section:
                    mechanics.append(lore_section.strip())
        
        # Add mission brief for sub-agents (e.g., generals) if available
        try:
            group_comp = self.entity.get_component(SubAgentGroup)
            pos_comp = self.entity.get_component(PositionComponent)
            if group_comp:
                mp = group_comp.mission_parameters
                mission_lines = [
                    "**Mission Brief:**",
                    f"- Mission: {mp.mission_type if mp else 'unspecified'}",
                    f"- Priority: {mp.priority if mp else 'medium'}",
                    f"- Orders: {mp.orders if mp and mp.orders else 'none provided'}",
                    f"- Target Area: {mp.target_area if mp and mp.target_area else 'unspecified'}",
                    f"- Assigned Forces: {group_comp.assigned_population.total} ("
                    f"{group_comp.assigned_population.soldiers} soldiers, {group_comp.assigned_population.workers} workers)",
                ]
                if pos_comp:
                    mission_lines.append(
                        f"- Current Position: {pos_comp.position} | Operational Range: {pos_comp.operational_range} tiles"
                    )
                mission_lines.append(
                    f"- Readiness: morale {group_comp.morale}%, supplies {group_comp.supplies}%"
                )
                mechanics.append("\n".join(mission_lines))
        except Exception as e:
            # If component classes unavailable or any error occurs, skip mission section
            log.warning(f"Prompt mission-brief section build failed: {e}")
        
        return "\n\n".join(mechanics) if mechanics else ""
    
    def _build_persona_section(self) -> str:
        """Build the persona section if provided."""
        return self.persona if self.persona else ""