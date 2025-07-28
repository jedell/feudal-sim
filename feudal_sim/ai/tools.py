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

from feudal_sim.ai.context import SimulationContext


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
    
    # Add action description for dynamic prompts
    send_raven.action_description = "**Send Ravens**: Dispatch messages to other lords (ravens take 2 weeks to deliver)"
    
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
    def assess_border(ctx: RunContextWrapper["SimulationContext"], direction: DirectionEnum) -> str:
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
    
    # Add action description for dynamic prompts
    assess_border.action_description = "**Assess Borders**: Scout a border direction to gather intelligence before expansion"
    
    return assess_border


def create_expand_territory_tool(house_entity) -> Callable:
    """
    Factory function to create an expand_territory tool that creates expansion orders.
    """
    from feudal_sim.components.territory import TerritoryComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.population import PopulationComponent
    
    territory_component: TerritoryComponent = house_entity.get_component(TerritoryComponent)
    resource_component: ResourceComponent = house_entity.get_component(ResourceComponent)
    population_component: PopulationComponent = house_entity.get_component(PopulationComponent)
    
    if not all([territory_component, resource_component, population_component]):
        @function_tool
        def expand_territory_unavailable(direction: str) -> str:
            """Territory expansion unavailable - missing required components."""
            return f"House {house_entity.name} cannot expand territory - missing required components"
        return expand_territory_unavailable
    
    # Create enum for valid directions
    DirectionEnum = Enum('Direction', {'N': 'N', 'NE': 'NE', 'SE': 'SE', 'S': 'S', 'SW': 'SW', 'NW': 'NW'})
    
    @function_tool
    def expand_territory(ctx: RunContextWrapper["SimulationContext"], direction: DirectionEnum) -> str:
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
    
    # Add action description for dynamic prompts
    expand_territory.action_description = "**Order Expansion**: Command your forces to claim new territory (resolves next week, costs material and gold)"
    
    return expand_territory


def create_read_intelligence_tool(house_entity) -> Callable:
    """
    Factory function to create a read_intelligence_report tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent
    
    intelligence_component = house_entity.get_component(IntelligenceComponent)

    # house name enum, except for the current house
    house_name_dict = {house: house for house in intelligence_component.get_neighbors()}
    HouseNameEnum = Enum('HouseName', house_name_dict)
    
    if not intelligence_component:
        @function_tool
        def read_intelligence_unavailable(house_name: HouseNameEnum) -> str:
            """No intelligence system available."""
            return f"House {house_entity.name} has no intelligence gathering capability"
        return read_intelligence_unavailable
    
    @function_tool
    def read_intelligence_report(house_name: HouseNameEnum) -> str:
        """
        Read the intelligence report on a specific house. Shows distance, direction, territory size, and any notes you have made on this house.
        
        Args:
            house_name: The name of the house to get intelligence on (e.g. "Stark", "Lannister")
            
        Returns:
            Formatted intelligence report with distance, direction, territory size, and any notes you have made on this house.
        """
        return intelligence_component.format_intelligence_report(house_name.value)
    
    # Add action description for dynamic prompts
    read_intelligence_report.action_description = "**Read Intelligence**: Review detailed intelligence reports on specific rival houses"
    
    return read_intelligence_report


def create_read_all_intelligence_tool(house_entity) -> Callable:
    """
    Factory function to create a read_all_intelligence tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent
    
    intelligence_component = house_entity.get_component(IntelligenceComponent)
    
    if not intelligence_component:
        @function_tool
        def read_all_intelligence_unavailable() -> str:
            """No intelligence system available."""
            return f"House {house_entity.name} has no intelligence gathering capability"
        return read_all_intelligence_unavailable
    
    @function_tool
    def read_all_intelligence() -> str:
        """
        Read a summary of all intelligence reports on other houses. Shows basic information on all known neighbors.
        Call this every once in a while to get a sense of the world.
        
        Returns:
            Summary of all neighbor intelligence including distances, directions, and territory sizes
        """
        return intelligence_component.format_all_intelligence_summary()
    
    # Add action description for dynamic prompts  
    read_all_intelligence.action_description = "**Survey All Intelligence**: Review summary of intelligence on all known rival houses"
    
    return read_all_intelligence


def create_update_intelligence_tool(house_entity) -> Callable:
    """
    Factory function to create an update_intelligence_notes tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent
    
    intelligence_component = house_entity.get_component(IntelligenceComponent)
    
    # house name enum, except for the current house
    house_name_dict = {house: house for house in intelligence_component.get_neighbors()}
    HouseNameEnum = Enum('HouseName', house_name_dict)
        
    if not intelligence_component:
        @function_tool
        def update_intelligence_unavailable(house_name: HouseNameEnum, notes: str) -> str:
            """No intelligence system available."""
            return f"House {house_entity.name} has no intelligence gathering capability"
        return update_intelligence_unavailable
    
    @function_tool
    def update_intelligence_notes(house_name: HouseNameEnum, notes: str) -> str:
        """
        Update your intelligence notes on a specific house. Add observations, assessments, or strategic thoughts.
        
        Args:
            house_name: The name of the house to update notes for
            notes: Your assessment or observations about this house
            
        Returns:
            Confirmation of the intelligence update
        """
        intelligence_component.update_notes(house_name.value, notes)
        return f"Intelligence notes updated for House {house_name.value}: {notes}"
    
    # Add action description for dynamic prompts
    update_intelligence_notes.action_description = "**Update Intelligence**: Add strategic notes and observations about rival houses"
    
    return update_intelligence_notes


def create_collect_taxes_tool(house_entity) -> Callable:
    """
    Factory function to create a collect_taxes tool bound to a specific house entity.
    """
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.population import PopulationComponent
    
    resource_component = house_entity.get_component(ResourceComponent)
    population_component = house_entity.get_component(PopulationComponent)
    
    if not resource_component or not population_component:
        @function_tool
        def collect_taxes_unavailable(tax_rate: float) -> str:
            """Tax collection unavailable - missing required components."""
            return f"House {house_entity.name} cannot collect taxes - missing required components"
        return collect_taxes_unavailable
    
    @function_tool
    def collect_taxes(tax_rate: float) -> str:
        """
        Collect taxes from your population to raise gold. Higher tax rates collect more gold but reduce population loyalty.
        
        Args:
            tax_rate: Tax rate as a decimal (0.1 = 10% taxes, 0.2 = 20% taxes, etc.). Must be between 0.1 and 1.0.
            
        Returns:
            Result of tax collection including gold gained and loyalty impact
        """
        try:
            if not (0.1 <= tax_rate <= 1.0):
                return "Tax rate must be between 0.1 (10%) and 1.0 (100%)"
            
            # Get current values for comparison
            old_gold = resource_component.resources.gold
            old_loyalty = population_component.loyalty
            population = population_component.population
            
            # Collect taxes using the house method
            tax_collected = house_entity.collect_taxes(tax_rate)
            
            # Get new values
            new_gold = resource_component.resources.gold
            new_loyalty = population_component.loyalty
            loyalty_lost = old_loyalty - new_loyalty
            
            # Format tax rate as percentage
            tax_percentage = int(tax_rate * 100)
            
            return (f"Collected {tax_collected} gold from {population} population with {tax_percentage}% tax rate. "
                   f"Gold: {old_gold:.0f} → {new_gold:.0f} (+{tax_collected}). "
                   f"Population loyalty: {old_loyalty:.0f} → {new_loyalty:.0f} (-{loyalty_lost:.0f})")
            
        except Exception as e:
            return f"Failed to collect taxes: {str(e)}"
    
    # Add action description for dynamic prompts
    collect_taxes.action_description = "**Collect Taxes**: Levy tribute from your subjects to raise gold (reduces population loyalty)"
    
    return collect_taxes


def create_view_cities_tool(house_entity) -> Callable:
    """
    Factory function to create a view_cities tool bound to a specific house entity.
    """
    from feudal_sim.components.city import CityComponent
    
    city_component = house_entity.get_component(CityComponent)
    
    if not city_component:
        @function_tool
        def view_cities_unavailable() -> str:
            """No city system available."""
            return f"House {house_entity.name} has no cities to manage"
        return view_cities_unavailable
    
    @function_tool
    def view_cities() -> str:
        """
        View information about all your cities including their positions, bonuses, and development levels.
        
        Returns:
            Summary of all cities controlled by your house
        """
        return city_component.get_cities_summary()
    
    # Add action description for dynamic prompts
    view_cities.action_description = "**Review Cities**: Examine your urban settlements and their development levels"
    
    return view_cities


def create_deploy_general_tool(house_entity) -> Callable:
    """
    Factory function to create a deploy_general tool bound to a specific house entity.
    """
    from feudal_sim.components.territory import TerritoryComponent
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.core.entities import Entity
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.ai.prompts import AgentType
    
    territory_component = house_entity.get_component(TerritoryComponent)
    population_component = house_entity.get_component(PopulationComponent)
    
    if not territory_component or not population_component:
        @function_tool
        def deploy_general_unavailable(position_q: int, position_r: int, soldiers_assigned: int, general_name: str) -> str:
            """General deployment unavailable - missing required components."""
            return f"House {house_entity.name} cannot deploy generals - missing required components"
        return deploy_general_unavailable
    
    @function_tool
    def deploy_general(ctx: RunContextWrapper["SimulationContext"], position_q: int, position_r: int, soldiers_assigned: int, general_name: str) -> str:
        """
        Deploy a general to a specific position with assigned military forces.
        Generals can act independently within their operational range and make tactical decisions.
        
        Args:
            position_q: Q coordinate for general's starting position (must be within your territory)
            position_r: R coordinate for general's starting position (must be within your territory) 
            soldiers_assigned: Number of soldiers to assign to this general (from your available military)
            general_name: Name for the general (e.g., "General Snow", "Commander Stark")
            
        Returns:
            Result of general deployment
        """
        # Get simulation context
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "General deployment failed - map access not available"
        
        hex_grid = sim_context.hex_grid
        target_position = (position_q, position_r)
        
        # Validate position is within house territory
        target_tile = hex_grid.get_tile(position_q, position_r)
        if not target_tile:
            return f"Cannot deploy general to ({position_q}, {position_r}) - position outside map bounds"
        
        if target_tile not in territory_component.territory:
            return f"Cannot deploy general to ({position_q}, {position_r}) - position not within your territory"
        
        # Validate soldier assignment
        available_soldiers = population_component.get_soldier_count()
        if soldiers_assigned <= 0:
            return "Must assign at least 1 soldier to the general"
        
        if soldiers_assigned > available_soldiers:
            return f"Cannot assign {soldiers_assigned} soldiers - only {available_soldiers} available"
        
        # Check if we already have a general at this position
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            existing_entities = sim_context.entity_manager.get_all_entities()
            for entity in existing_entities:
                pos_comp = entity.get_component(PositionComponent)
                if pos_comp and pos_comp.position == target_position:
                    if hasattr(entity, 'house_id') and entity.house_id == house_entity.id:
                        return f"You already have a unit positioned at ({position_q}, {position_r})"
        
        # Create general entity
        general_id = f"{house_entity.id}_general_{len(territory_component.deployed_generals) + 1}"
        general_entity = Entity(general_id, general_name)
        general_entity.house_id = house_entity.id  # Link back to parent house
        
        # Add components to general
        position_comp = PositionComponent(
            entity_id=general_id,
            position=target_position,
            operational_range=3,  # Generals have 3-tile operational range
            movement_points=2     # Can move 2 tiles per turn
        )
        general_entity.add_component(position_comp)
        
        # Add AI component for independent decision making
        ai_comp = AIComponent(
            name=general_name,
            agent_type=AgentType.GENERAL,
            entity_id=general_id,
            house_name=house_entity.name
        )
        general_entity.add_component(ai_comp)
        
        # TODO: Add MilitaryComponent with assigned soldiers when we create it
        # For now, just track in a simple way
        general_entity.assigned_soldiers = soldiers_assigned
        
        # Register general with entity manager
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            sim_context.entity_manager._entities[general_id] = general_entity
            
            # Track by type for easy lookup
            if 'general' not in sim_context.entity_manager._entities_by_type:
                sim_context.entity_manager._entities_by_type['general'] = []
            sim_context.entity_manager._entities_by_type['general'].append(general_entity)
        
        # Track deployed generals in territory component
        if not hasattr(territory_component, 'deployed_generals'):
            territory_component.deployed_generals = []
        territory_component.deployed_generals.append({
            'entity_id': general_id,
            'name': general_name,
            'position': target_position,
            'soldiers_assigned': soldiers_assigned,
            'deployment_turn': sim_context.current_turn if sim_context else -1
        })
        
        # TODO: Reduce available soldiers in population component
        # For now, this is just a deployment without affecting house totals
        
        return (f"Successfully deployed {general_name} at ({position_q}, {position_r}) with {soldiers_assigned} soldiers. "
                f"The general has operational range of 3 tiles and can move 2 tiles per turn. "
                f"They will make independent tactical decisions within their area of operations.")
    
    # Add action description for dynamic prompts
    deploy_general.action_description = "**Deploy General**: Position a military commander with assigned forces to act independently in a specific area"
    
    return deploy_general


def create_manage_household_tool(house_entity) -> Callable:
    """
    Factory function to create a manage_household tool bound to a specific house entity.
    """
    from feudal_sim.components.population import PopulationComponent
    
    population_component = house_entity.get_component(PopulationComponent)
    
    if not population_component:
        @function_tool
        def manage_household_unavailable(worker_ratio: float, soldier_ratio: float) -> str:
            """No population management available."""
            return f"House {house_entity.name} has no population to manage"
        return manage_household_unavailable
    
    @function_tool
    def manage_household(worker_ratio: float, soldier_ratio: float) -> str:
        """
        Manage your household by allocating your population between workers and soldiers.
        Workers improve resource production efficiency. Soldiers improve territorial expansion success rates.
        The ratios must add up to 1.0 (e.g., 0.7 workers + 0.3 soldiers = 1.0).
        
        Args:
            worker_ratio: Percentage of population allocated to work (0.0 to 1.0, e.g., 0.7 = 70%)
            soldier_ratio: Percentage of population allocated to military service (0.0 to 1.0, e.g., 0.3 = 30%)
            
        Returns:
            Result of the household management including efficiency changes
        """
        # Validate ratios
        if worker_ratio < 0 or soldier_ratio < 0:
            return "Ratios cannot be negative"
        
        if abs((worker_ratio + soldier_ratio) - 1.0) > 0.001:
            return f"Ratios must add up to 1.0. Current total: {worker_ratio + soldier_ratio:.3f}"
        
        # Get current status for comparison
        old_status = population_component.get_population_status()
        
        # Set the new ratios
        success = population_component.set_population_ratios(worker_ratio, soldier_ratio)
        
        if not success:
            return "Failed to set population ratios - invalid values"
        
        # Get new status
        new_status = population_component.get_population_status()
        
        # Calculate the effects
        worker_count = new_status['worker_count']
        soldier_count = new_status['soldier_count']
        worker_efficiency = new_status['worker_efficiency']
        soldier_expansion_bonus = new_status['soldier_expansion_bonus']
        
        # Format efficiency changes
        old_efficiency = old_status['worker_efficiency']
        efficiency_change = worker_efficiency - old_efficiency
        efficiency_change_text = f"+{efficiency_change:.2f}" if efficiency_change > 0 else f"{efficiency_change:.2f}"
        
        old_expansion_bonus = old_status['soldier_expansion_bonus']
        expansion_change = soldier_expansion_bonus - old_expansion_bonus
        expansion_change_text = f"+{expansion_change:.2f}" if expansion_change > 0 else f"{expansion_change:.2f}"
        
        return (f"Household management updated: {worker_count} workers ({worker_ratio*100:.0f}%), "
                f"{soldier_count} soldiers ({soldier_ratio*100:.0f}%). "
                f"Resource efficiency: {worker_efficiency:.2f} ({efficiency_change_text}), "
                f"Expansion bonus: +{soldier_expansion_bonus:.1%} ({expansion_change_text})")
    
    # Add action description for dynamic prompts
    manage_household.action_description = "**Manage Household**: Allocate your people between labor (improves resources) and military service (improves expansion)"
    
    return manage_household


@function_tool
def end_turn() -> str:
    """
    End your current turn.
    
    Returns:
        Confirmation of the turn ending
    """
    return "Turn ended"


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
    
    # Intelligence tools
    tools.append(create_read_intelligence_tool(house))
    tools.append(create_read_all_intelligence_tool(house))
    tools.append(create_update_intelligence_tool(house))
    
    # Population management tools
    tools.append(create_manage_household_tool(house))
    
    # Military deployment tools
    tools.append(create_deploy_general_tool(house))
    
    # Resource management tools
    tools.append(create_collect_taxes_tool(house))
    
    # City management tools
    tools.append(create_view_cities_tool(house))
    
    # Future tools can be added here:
    # tools.append(create_dispatch_army_tool(house))
    # tools.append(create_dispatch_scout_tool(house))
    
    return tools


def create_move_tool(entity) -> Callable:
    """
    Factory function to create a move tool for positioned entities (generals, scouts, etc.).
    """
    from feudal_sim.components.position import PositionComponent
    
    position_component = entity.get_component(PositionComponent)
    
    if not position_component:
        @function_tool
        def move_unavailable(target_q: int, target_r: int) -> str:
            """Movement unavailable - no position component."""
            return f"{entity.name} cannot move - no position component"
        return move_unavailable
    
    @function_tool
    def move(ctx: RunContextWrapper["SimulationContext"], target_q: int, target_r: int) -> str:
        """
        Move to a target position on the map.
        Movement consumes movement points and is limited by terrain.
        
        Args:
            target_q: Target Q coordinate
            target_r: Target R coordinate
            
        Returns:
            Result of movement attempt
        """
        # Get simulation context
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Movement failed - map access not available"
        
        hex_grid = sim_context.hex_grid
        target_position = (target_q, target_r)
        current_turn = sim_context.current_turn if sim_context else None
        
        # Attempt movement
        result = position_component.move_to(
            target_position=target_position,
            hex_grid=hex_grid,
            current_turn=current_turn,
            validate_movement=True
        )
        
        return result['message']
    
    # Add action description for dynamic prompts
    move.action_description = "**Move**: Travel to a different position on the map (costs movement points)"
    
    return move


def create_general_toolset(general_entity) -> list:
    """Create tools for general entities."""
    tools = []
    
    # Basic movement tool
    tools.append(create_move_tool(general_entity))
    
    # Future general-specific tools:
    # tools.append(create_local_expansion_tool(general_entity))
    # tools.append(create_fortify_position_tool(general_entity))
    # tools.append(create_scout_area_tool(general_entity))
    
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