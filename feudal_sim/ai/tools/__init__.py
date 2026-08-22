"""
AI Tools for the feudal simulation.

This package contains tool functions that AI agents can call to interact with the
simulation. Each tool is decorated with @function_tool to make it available to the
OpenAI Agents SDK.

Tools need access to the current entity/house context, so they are created by factory
functions that bind the specific entity instance to the tool. The factories are split
into cohesive submodules; this __init__ re-exports the public surface and provides the
entity-type dispatcher.
"""

from feudal_sim.ai.tools.caravan_toolset import (
    create_army_toolset,
    create_caravan_toolset,
    create_scout_toolset,
)
from feudal_sim.ai.tools.common import _balance_line
from feudal_sim.ai.tools.communication import (
    create_assess_border_tool,
    create_read_compendium_tool,
    create_rookery_toolset,
    create_send_raven_tool,
    create_write_compendium_tool,
    end_turn,
)
from feudal_sim.ai.tools.economy import (
    create_collect_taxes_tool,
    create_manage_household_tool,
)
from feudal_sim.ai.tools.general_toolset import create_general_toolset
from feudal_sim.ai.tools.house_toolset import create_house_toolset
from feudal_sim.ai.tools.territory import (
    create_deploy_general_tool,
    create_view_cities_tool,
)
from feudal_sim.ai.tools.trade import (
    create_declare_war_tool,
    create_send_trade_caravan_tool,
    create_sue_for_peace_tool,
)

__all__ = [
    "_balance_line",
    "create_army_toolset",
    "create_assess_border_tool",
    "create_caravan_toolset",
    "create_collect_taxes_tool",
    "create_declare_war_tool",
    "create_deploy_general_tool",
    "create_general_toolset",
    "create_house_toolset",
    "create_manage_household_tool",
    "create_read_compendium_tool",
    "create_rookery_toolset",
    "create_scout_toolset",
    "create_send_raven_tool",
    "create_send_trade_caravan_tool",
    "create_sue_for_peace_tool",
    "create_view_cities_tool",
    "create_write_compendium_tool",
    "end_turn",
    "get_tools_for_entity",
    "TOOL_FACTORIES",
]


# Registry of tool factories by entity type
TOOL_FACTORIES = {
    'house': create_house_toolset,
    'general': create_general_toolset,
    'army': create_army_toolset,
    'scout': create_scout_toolset,
    'caravan': create_caravan_toolset,
}


def get_tools_for_entity(entity, entity_type: str = 'house') -> list:
    """
    Get the appropriate toolset for an entity.
    
    Args:
        entity: The entity to create tools for
        entity_type: Type of entity ('house', 'army', 'scout', 'caravan')
        
    Returns:
        List of tool functions for the entity
    """
    factory = TOOL_FACTORIES.get(entity_type)
    if factory:
        return factory(entity)
    else:
        print(f"Warning: No tool factory found for entity type '{entity_type}'")
        return []
