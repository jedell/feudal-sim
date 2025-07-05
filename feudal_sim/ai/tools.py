"""
AI Tools for the feudal simulation.

This module contains tool functions that AI agents can call to interact with the simulation.
Each tool is decorated with @function_tool to make it available to the OpenAI Agents SDK.

Tools need access to the current entity/house context, so they will be created by factory functions
that bind the specific house instance to the tool.
"""

from agents import function_tool, RunContextWrapper
from typing import Callable
from enum import Enum
from feudal_sim.components.ai import SimulationContext

def create_send_raven_tool(house_entity) -> Callable:
    """
    Factory function to create a send_raven tool bound to a specific house entity.
    
    Args:
        house_entity: The House entity that this tool will operate on
        
    Returns:
        A send_raven tool function bound to the house
    """
    from feudal_sim.components.rookery import RookeryComponent
    
    # Get rookery component to access known recipients
    rookery = house_entity.get_component(RookeryComponent)
    
    if not rookery:
        # If no rookery, create a dummy tool that explains the limitation
        @function_tool
        def send_raven_unavailable(message: str) -> str:
            """No raven communication available - no rookery component."""
            return f"House {house_entity.name} has no rookery to send ravens"
        
        return send_raven_unavailable
    
    # Get known recipients and create dynamic enum
    known_recipients = rookery.get_known_recipients_list()
    
    if not known_recipients:
        # If no known recipients, create tool that explains this
        @function_tool  
        def send_raven_no_recipients(message: str) -> str:
            """No known recipients for raven communication."""
            return f"House {house_entity.name} has no known recipients to send ravens to"
        
        return send_raven_no_recipients
    
    # Create dynamic enum for known recipients
    # Use a safe name format for enum creation - map each name to itself
    recipient_dict = {name: name for name in known_recipients}
    RecipientEnum = Enum('Recipient', recipient_dict)
    
    @function_tool
    def send_raven(recipient: RecipientEnum, message: str) -> str:
        """
        Send a raven message to another house or entity. Ravens take time to deliver - messages sent this week will arrive to the recipient in 2 weeks. Consider waiting for a response before sending additional messages.
        
        Args:
            recipient: The house or entity to send the message to (must be a known recipient)
            message: The message content to send
            
        Returns:
            String indicating success or failure of sending the raven
        """
        # Convert enum value back to original recipient name
        recipient_name = recipient.value
        
        # Use the rookery component to send the raven
        success = rookery.send_raven(recipient_name, message)
        
        if success:
            return f"Raven sent to {recipient_name}: '{message}' - message will arrive in 2 weeks."
        else:
            return f"Failed to send raven to {recipient_name} - unknown recipient or other error"
    
    return send_raven


def create_assess_border_tool(house_entity) -> Callable:
    """
    Factory function to create an assess_border tool bound to a specific house entity.
    """
    from feudal_sim.components.territory import TerritoryComponent
    
    territory_component = house_entity.get_component(TerritoryComponent)
    
    if not territory_component:
        @function_tool
        def assess_border_unavailable(direction: str) -> str:
            """No territory assessment available - no territory component."""
            return f"House {house_entity.name} has no territory to assess"
        return assess_border_unavailable
    
    # Create enum for valid directions
    DirectionEnum = Enum('Direction', {'N': 'N', 'NE': 'NE', 'SE': 'SE', 'S': 'S', 'SW': 'SW', 'NW': 'NW'})
    
    @function_tool
    def assess_border(ctx: RunContextWrapper[SimulationContext], direction: DirectionEnum) -> str:
        """
        Assess border in a specific direction for expansion opportunities. Assess a border direction to gather information before expanding.
        
        Args:
            direction: Direction to assess (N, NE, SE, S, SW, NW)
            
        Returns:
            Detailed border assessment with individual tile information including terrain infomation and cost to expand.
        """
        direction_str = direction.value
        
        # Get simulation context from RunContextWrapper
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return f"Border assessment for {direction_str} direction - map access not available"
        
        hex_grid = sim_context.hex_grid
        
        # Get direction analysis
        direction_analysis = territory_component.calculate_direction_value(direction_str, hex_grid)
        
        if not direction_analysis['has_opportunities']:
            return direction_analysis['message']
        
        # Create simplified observation
        terrain_types = []
        for opportunity in direction_analysis['opportunities'][:3]:  # Show first 3 terrain types
            terrain = opportunity['terrain_type']
            if terrain not in terrain_types:
                terrain_types.append(terrain)
        
        if direction_analysis['total_opportunities'] > 3:
            terrain_summary = f"{', '.join(terrain_types)} (and {direction_analysis['total_opportunities'] - 3} more tiles)"
        else:
            terrain_summary = ', '.join(terrain_types)
        
        costs = direction_analysis['expansion_cost_estimate']
        
        return f"Border assessment: {direction_analysis['total_opportunities']} tiles ({terrain_summary}). Cost: {costs['material']} material, {costs['gold']} gold"
    
    return assess_border


def create_expand_territory_tool(house_entity) -> Callable:
    """
    Factory function to create an expand_territory tool that creates expansion orders.
    """
    from feudal_sim.components.territory import TerritoryComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.population import PopulationComponent
    
    territory_component = house_entity.get_component(TerritoryComponent)
    resource_component = house_entity.get_component(ResourceComponent)
    population_component = house_entity.get_component(PopulationComponent)
    
    if not all([territory_component, resource_component, population_component]):
        @function_tool
        def expand_territory_unavailable(direction: str) -> str:
            """Territory expansion unavailable - missing required components."""
            return f"House {house_entity.name} cannot expand territory - missing required components"
        return expand_territory_unavailable
    
    # Create enum for valid directions
    DirectionEnum = Enum('Direction', {'N': 'N', 'NE': 'NE', 'SE': 'SE', 'S': 'S', 'SW': 'SW', 'NW': 'NW'})
    
    @function_tool
    def expand_territory(ctx: RunContextWrapper[SimulationContext], direction: DirectionEnum) -> str:
        """
        Order territorial expansion in a specific direction. This will resolve next week.
        This will incur a cost in material and gold.
        
        Args:
            direction: Direction to expand into (N, NE, SE, S, SW, NW)
            
        Returns:
            Result of creating the expansion order
        """
        direction_str = direction.value
        
        # Get simulation context from RunContextWrapper
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return f"Expansion order for {direction_str} direction - map access not available"
        
        hex_grid = sim_context.hex_grid
        current_turn = sim_context.current_turn
        
        # Create the expansion order
        expansion_order = territory_component.create_expansion_order(
            direction_str, 
            hex_grid, 
            current_turn
        )
        
        if not expansion_order:
            return f"No expansion opportunities available in {direction_str} direction"
        
        # Return detailed observation about the expansion order
        observation = (f"Expansion order created for {direction_str} direction. "
                      f"Will resolve on week {expansion_order.turn_resolves}. "
                      f"Targeting {len(expansion_order.target_tiles)} tiles.")
        
        return observation
    return expand_territory


def create_house_toolset(house) -> list:
    """
    Create the complete set of tools available to a house's AI agent.
    
    Args:
        house: The House instance to create tools for
        
    Returns:
        List of tool functions bound to the house
    """
    tools = []
    
    # Communication tools
    tools.append(create_send_raven_tool(house))
    
    # Territory management tools
    tools.append(create_assess_border_tool(house))
    tools.append(create_expand_territory_tool(house))
    
    # Future tools can be added here:
    # tools.append(create_dispatch_army_tool(house))
    # tools.append(create_dispatch_scout_tool(house))
    # tools.append(create_manage_resources_tool(house))
    # tools.append(create_collect_taxes_tool(house))
    
    return tools


# Tool categories for different entity types
def create_army_toolset(army_entity) -> list:
    """Create tools for army entities (future implementation)."""
    return []


def create_scout_toolset(scout_entity) -> list:
    """Create tools for scout entities (future implementation).""" 
    return []


def create_caravan_toolset(caravan_entity) -> list:
    """Create tools for caravan entities (future implementation)."""
    return []


# Registry of tool factories by entity type
TOOL_FACTORIES = {
    'house': create_house_toolset,
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