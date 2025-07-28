"""
Dynamic prompt builder for AI agents.

Assembles prompts from three sources:
1. Static base template (core lore and rules) - varies by agent type
2. Available actions (from tools)
3. Component mechanics (from entity components)

Supports different AI agent types: House Lords, Scouts, Generals, etc.
"""

from typing import List, Optional, Dict
from feudal_sim.core.entities import Entity
from feudal_sim.ai.prompts import AgentType


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
        from feudal_sim.ai.prompts import get_agent_template
        
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
    
    def _build_mechanics_sections(self) -> str:
        """Build mechanics explanations from entity components."""
        if not self.entity:
            return ""
        
        mechanics = []
        
        # Get lore sections from all components
        for component in self.entity.get_all_components():
            if hasattr(component, 'get_lore_section'):
                lore_section = component.get_lore_section()
                if lore_section:
                    mechanics.append(lore_section.strip())
        
        return "\n\n".join(mechanics) if mechanics else ""
    
    def _build_persona_section(self) -> str:
        """Build the persona section if provided."""
        return self.persona if self.persona else ""