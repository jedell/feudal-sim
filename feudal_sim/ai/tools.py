"""
AI Tools for the feudal simulation.

This module contains tool functions that AI agents can call to interact with the simulation.
Each tool is decorated with @function_tool to make it available to the OpenAI Agents SDK.

Tools need access to the current entity/house context, so they will be created by factory functions
that bind the specific house instance to the tool.
"""

from agents import function_tool, RunContextWrapper
from typing import Callable, Dict
from enum import Enum

from feudal_sim.ai.context import SimulationContext
from feudal_sim.utils.observations import ObservationFormatter
from feudal_sim.config.subagents import get_general_cap, get_deploy_costs


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


def create_read_compendium_tool(house_entity) -> Callable:
    """
    Factory function to create a read_compendium tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent
    
    intelligence_component = house_entity.get_component(IntelligenceComponent)
    
    if not intelligence_component:
        @function_tool
        def read_compendium_unavailable(topic: str = None) -> str:
            """No compendium available."""
            return f"House {house_entity.name} has no compendium to consult"
        return read_compendium_unavailable
    
    @function_tool
    def read_compendium(topic: str = None) -> str:
        """
        Read from your strategic compendium - a journal of intelligence, observations, and strategic notes.
        If no topic is specified, shows a summary of all entries. If a topic is specified, shows detailed information about that house or subject.
        
        Args:
            topic: Optional specific house name or subject to read about (e.g. "Stark", "Lannister"). If not provided, shows all entries.
            
        Returns:
            Your compendium entries - either all summaries or detailed information about the specified topic
        """
        if topic:
            # Try to find specific house intelligence
            neighbors = intelligence_component.get_neighbors()
            if topic in neighbors:
                return intelligence_component.format_intelligence_report(topic)
            else:
                return f"No compendium entry found for '{topic}'. Available topics: {', '.join(neighbors)}"
        else:
            # Show all intelligence summary
            return intelligence_component.format_all_intelligence_summary()
    
    # Add action description for dynamic prompts
    read_compendium.action_description = "**Read Compendium**: Consult your strategic journal of intelligence and observations"
    
    return read_compendium


def create_write_compendium_tool(house_entity) -> Callable:
    """
    Factory function to create a write_compendium tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent
    
    intelligence_component = house_entity.get_component(IntelligenceComponent)
        
    if not intelligence_component:
        @function_tool
        def write_compendium_unavailable(topic: str, entry: str) -> str:
            """No compendium available."""
            return f"House {house_entity.name} has no compendium to write in"
        return write_compendium_unavailable
    
    @function_tool
    def write_compendium(topic: str, entry: str) -> str:
        """
        Write an entry in your strategic compendium - record intelligence, observations, strategic thoughts, or plans.
        Use this to keep track of important information about other houses, diplomatic relations, military assessments, or strategic plans.
        
        Args:
            topic: The subject of your entry (e.g. house name like "Stark" or general topics like "Military Strategy")
            entry: Your strategic notes, observations, or intelligence about this topic
            
        Returns:
            Confirmation of the compendium entry
        """
        # Check if this is a known house - if so, use intelligence system
        neighbors = intelligence_component.get_neighbors()
        if topic in neighbors:
            intelligence_component.update_notes(topic, entry)
            return f"Compendium updated - {topic}: {entry}"
        else:
            # For general topics, we can still record it as intelligence notes 
            # The intelligence system can handle arbitrary topics
            intelligence_component.update_notes(topic, entry)
            return f"Compendium entry recorded - {topic}: {entry}"
    
    # Add action description for dynamic prompts
    write_compendium.action_description = "**Write Compendium**: Record strategic intelligence, observations, and plans in your journal"
    
    return write_compendium


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
    from feudal_sim.components.population import PopulationComponent, AssignedPopulation
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.components.terrain_observation import TerrainObservation
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
    def deploy_general(ctx: RunContextWrapper["SimulationContext"], direction: str, soldiers_assigned: int, workers_assigned: int = 0, general_name: str = "General", orders: str = "Patrol the area and await further orders") -> str:
        """
        Deploy a general in a specific direction from your territory with assigned population forces.
        Generals can act independently and will interpret natural language orders to accomplish their mission.
        They lead their assigned group of soldiers and workers on missions like expansion, patrol, and fortification.
        
        Args:
            direction: Direction to deploy the general (N, NE, SE, S, SW, NW, or "center")
            soldiers_assigned: Number of soldiers to assign to this general (from your available military)
            workers_assigned: Number of workers to assign to this general (for settlement/construction) 
            general_name: Name for the general (e.g., "General snow", "Commander Stark")
            orders: Natural language orders for the general (e.g., "Expand our territory eastward", "Fortify the northern border")
            
        Returns:
            Result of general deployment
        """
        # Get simulation context
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "General deployment failed - map access not available"
        
        hex_grid = sim_context.hex_grid
        
        # Validate direction
        valid_directions = ["N", "NE", "SE", "S", "SW", "NW", "center"]
        direction_upper = direction.upper()
        if direction_upper not in valid_directions:
            return f"Invalid direction '{direction}'. Valid directions: {', '.join(valid_directions)}"
        
        # Find suitable deployment position based on direction
        deployment_position = None
        if direction_upper == "CENTER":
            # Deploy at center of territory
            if territory_component.territory:
                # Find centroid of territory
                total_q = sum(tile.q for tile in territory_component.territory)
                total_r = sum(tile.r for tile in territory_component.territory)
                center_q = int(total_q / len(territory_component.territory))
                center_r = int(total_r / len(territory_component.territory))
                
                # Find closest territory tile to centroid
                min_distance = float('inf')
                for tile in territory_component.territory:
                    distance = abs(tile.q - center_q) + abs(tile.r - center_r)
                    if distance < min_distance:
                        min_distance = distance
                        deployment_position = (tile.q, tile.r)
        else:
            # Deploy at territory border in specified direction
            border_tiles_in_direction = territory_component.get_border_tiles_by_direction(direction_upper, hex_grid)
            
            # Prefer controlled tiles that have an uncontrolled neighbor specifically in the chosen direction
            controlled_border_tiles = []
            for tile in territory_component.territory:
                for neighbor_tile, neighbor_dir in hex_grid.get_neighbors(tile.q, tile.r):
                    if neighbor_dir == direction_upper and neighbor_tile not in territory_component.territory:
                        controlled_border_tiles.append(tile)
                        break
            
            # Fallback: any controlled tile that borders uncontrolled territory (any direction)
            if not controlled_border_tiles:
                for tile in territory_component.territory:
                    if any(neigh not in territory_component.territory for neigh, _d in hex_grid.get_neighbors(tile.q, tile.r)):
                        controlled_border_tiles.append(tile)
            
            if controlled_border_tiles:
                import random
                selected_tile = random.choice(controlled_border_tiles)
                deployment_position = (selected_tile.q, selected_tile.r)
        
        if not deployment_position:
            return f"Cannot find suitable deployment position in direction '{direction}' within your territory"
        
        # Validate population assignment
        if soldiers_assigned <= 0 and workers_assigned <= 0:
            return "Must assign at least 1 person (soldier or worker) to the general"
        
        # Check if enough population is available
        if not population_component.can_assign_population(workers_assigned, soldiers_assigned):
            available_pop = population_component.get_available_population()
            return f"Cannot assign {soldiers_assigned + workers_assigned} people - only {available_pop} available"
        
        # Check if we already have a general at this position
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            existing_entities = sim_context.entity_manager.get_all_entities()
            for entity in existing_entities:
                pos_comp = entity.get_component(PositionComponent)
                if pos_comp and pos_comp.position == deployment_position:
                    if hasattr(entity, 'house_id') and entity.house_id == house_entity.id:
                        return f"You already have a unit positioned at {deployment_position} in the {direction} direction"
        
        # Enforce general cap and deployment costs
        from feudal_sim.components.resource import ResourceComponent
        
        # Cap: base + territory-based scaling
        current_generals = len(getattr(territory_component, 'deployed_generals', []))
        territory_size = len(getattr(territory_component, 'territory', []))
        max_generals = get_general_cap(territory_size)
        if current_generals >= max_generals:
            return (
                f"Cannot deploy another general: cap reached ({current_generals}/{max_generals}). "
                f"Gain more territory to increase your command capacity."
            )
        
        # Costs: base + per-person equipping
        resource_component = house_entity.get_component(ResourceComponent)
        if not resource_component:
            return "Cannot deploy general - missing resource management"
        costs = get_deploy_costs(soldiers_assigned, workers_assigned)
        if not resource_component.can_afford_action(costs):
            return (
                "Cannot deploy general - insufficient resources: "
                f"need {costs['gold']} gold and {costs['material']} material"
            )
        # Consume costs up front
        resource_component.consume_for_action(costs, "Deploy General")
        
        # Ensure tracking list exists before generating ID
        if not hasattr(territory_component, 'deployed_generals'):
            territory_component.deployed_generals = []
        
        # Create general entity
        next_index = len(territory_component.deployed_generals) + 1
        general_id = f"{house_entity.id}_general_{next_index}"
        general_entity = Entity(general_id, general_name)
        general_entity.house_id = house_entity.id  # Link back to parent house
        
        # Add components to general
        position_comp = PositionComponent(
            entity_id=general_id,
            position=deployment_position,
            operational_range=3,  # Generals have 3-tile operational range
            movement_points=2     # Can move 2 tiles per turn
        )
        general_entity.add_component(position_comp)
        
        # Create population assignment and assign from house
        assigned_population = AssignedPopulation(workers=workers_assigned, soldiers=soldiers_assigned)
        success = population_component.assign_population_to_agent(general_id, workers_assigned, soldiers_assigned)
        
        if not success:
            # This shouldn't happen due to earlier validation, but safety check
            return f"Failed to assign population to general - insufficient available population"
        
        # Add SubAgentGroup component to manage the assigned population
        group_comp = SubAgentGroup(
            entity_id=general_id,
            parent_house_id=house_entity.id,
            group_type="military",
            assigned_population=assigned_population
        )
        # Set mission based on natural language orders
        mission_type = "expansion" if "expand" in orders.lower() else "patrol"
        group_comp.set_mission(mission_type, target_area=deployment_position, orders=orders)
        general_entity.add_component(group_comp)
        
        # Add TerrainObservation component for autonomous intelligence gathering
        terrain_obs = TerrainObservation(
            entity_id=general_id,
            observation_range=3  # Generals have 3-tile observation range (matches operational range)
        )
        general_entity.add_component(terrain_obs)
        
        # Provide entity manager to observation component for threat queries
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            try:
                terrain_obs._entity_manager = sim_context.entity_manager
            except Exception:
                pass
        
        # Add AI component for independent decision making (after all required components are present)
        ai_comp = AIComponent(
            name=general_name,
            agent_type=AgentType.GENERAL,
            entity_id=general_id,
            house_name=house_entity.name
        )
        general_entity.add_component(ai_comp)
        
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
        territory_component.register_general({
            'entity_id': general_id,
            'name': general_name,
            'position': deployment_position,
            'direction': direction,
            'orders': orders,
            'soldiers_assigned': soldiers_assigned,
            'workers_assigned': workers_assigned,
            'deployment_turn': sim_context.current_turn if sim_context else -1
        })
        
        # Get group capabilities for reporting
        group_strength = group_comp.get_group_strength()
        settlement_capability = group_comp.get_settlement_capability()
        combat_strength = group_comp.get_combat_strength()
        
        # Build capability description
        capabilities = []
        if soldiers_assigned > 0:
            capabilities.append(f"combat strength {combat_strength}")
        if workers_assigned > 0:
            capabilities.append(f"settlement capability {settlement_capability:.1%}")
        
        capability_text = " and ".join(capabilities) if capabilities else "basic patrol capability"
        
        total_assigned = soldiers_assigned + workers_assigned
        return (f"Successfully deployed {general_name} to the {direction} with {total_assigned} people "
                f"({soldiers_assigned} soldiers, {workers_assigned} workers). "
                f"Position: {deployment_position}. Group strength: {group_strength}, {capability_text}. "
                f"Orders: '{orders}'. "
                f"The general will act independently within 3 tiles operational range and interpret these orders autonomously.")
    
    # Add action description for dynamic prompts
    deploy_general.action_description = "**Deploy General**: Send a military commander with assigned forces in a direction with natural language orders to act independently"
    
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
    # tools.append(create_expand_territory_tool(house))  # Deprecated in favor of sub-agent delegation (deploy_general + settle_territory)
    
    # Compendium tools (strategic journal)
    tools.append(create_read_compendium_tool(house))
    tools.append(create_write_compendium_tool(house))
    
    # Population management tools
    tools.append(create_manage_household_tool(house))
    
    # Military deployment tools
    tools.append(create_deploy_general_tool(house))
    
    # Tax collection tools
    tools.append(create_collect_taxes_tool(house))
    
    # Management: list current generals
    from agents import function_tool, RunContextWrapper
    from feudal_sim.components.subagent_group import SubAgentGroup
    
    @function_tool
    def list_generals(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        List all currently deployed generals for your house with key details.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        mine = sim_context.entity_manager.get_entities_by_house_and_type(house.id, 'general')
        if not mine:
            return "No generals currently deployed"
        reports = []
        for g in mine:
            grp = g.get_component(SubAgentGroup)
            people = grp.assigned_population.total if grp else 0
            morale = grp.morale if grp else None
            supplies = grp.supplies if grp else None
            status = grp.mission_status if grp else "unknown"
            reports.append(f"{g.name} — {people} assigned, morale {morale}%, supplies {supplies}%, status {status}")
        return " | ".join(reports)
    list_generals.action_description = "**List Generals**: See all currently deployed generals and their status"
    tools.append(list_generals)

    # Management: disband a general (recall population and remove unit)
    @function_tool
    def disband_general(ctx: RunContextWrapper["SimulationContext"], general_name: str) -> str:
        """
        Disband a deployed general by name, recalling assigned population.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        # Find general by name and house
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                        if getattr(g, 'house_id', None) == house.id and getattr(g, 'name', '') == general_name]
        if not candidates:
            return f"No general found named '{general_name}'"
        g = candidates[0]
        # Recall population
        from feudal_sim.components.population import PopulationComponent
        from feudal_sim.components.territory import TerritoryComponent
        pop_comp: PopulationComponent = house.get_component(PopulationComponent)
        if pop_comp:
            pop_comp.recall_population_from_agent(g.id)
        # Remove entity
        sim_context.entity_manager.destroy_entity(g.id)
        # Remove tracking entry
        territory_component = house.get_component(TerritoryComponent)
        if territory_component:
            territory_component.unregister_general(g.id)
        # Add observation to house AI
        try:
            from feudal_sim.components.ai import AIComponent
            ai: AIComponent = house.get_component(AIComponent)
            if ai:
                ai.add_observation(f"General {general_name} has been disbanded and assigned population recalled", phase="Actions")
        except Exception:
            pass
        return f"Disbanded general '{general_name}' and recalled assigned population"
    disband_general.action_description = "**Disband General**: Recall a general and return assigned population"
    tools.append(disband_general)
    
    # City management tools
    tools.append(create_view_cities_tool(house))
    
    # Universal tools
    tools.append(end_turn)
    
    # Future tools can be added here:
    # tools.append(create_dispatch_army_tool(house))
    # tools.append(create_dispatch_scout_tool(house))
    
    return tools


def create_observe_area_tool(general_entity) -> Callable:
    """
    Factory function to create an observe_area tool for generals with TerrainObservation.
    """
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.components.position import PositionComponent
    
    observation_comp: TerrainObservation = general_entity.get_component(TerrainObservation)
    position_comp: PositionComponent = general_entity.get_component(PositionComponent)
    
    if not observation_comp or not position_comp:
        @function_tool
        def observe_area_unavailable() -> str:
            """Observation unavailable - missing required components."""
            return f"General {general_entity.name} cannot observe terrain - missing observation capability"
        return observe_area_unavailable
    
    @function_tool
    def observe_area(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Observe the terrain around your current position to gather intelligence.
        Scans surrounding tiles for expansion opportunities, threats, and resources.
        Updates your knowledge of the area for tactical decision-making.
        
        Returns:
            Intelligence report of observed area
        """
        # Get simulation context
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Observation failed - map access not available"
        
        if not position_comp.position:
            return "Cannot observe - position unknown"
        
        current_turn = getattr(sim_context, 'current_turn', 0)
        
        # Perform observation
        result = observation_comp.observe_current_area(
            sim_context.hex_grid, 
            position_comp.position, 
            current_turn
        )
        
        if not result['success']:
            return f"Observation failed: {result.get('message', 'Unknown error')}"
        
        # Get intelligence summary
        status = observation_comp.get_observation_status()
        threats = observation_comp.get_threats_in_area(position_comp.position)
        
        # Build intelligence report
        report_parts = []
        report_parts.append(f"Observed {result['tiles_observed']} tiles around position {position_comp.position}")
        
        if result['new_threats'] > 0:
            report_parts.append(f"⚠️ Detected {result['new_threats']} new threats")
            threat_summary = {}
            for threat in threats[-3:]:  # Show last 3 threats
                threat_summary[threat.threat_level] = threat_summary.get(threat.threat_level, 0) + 1
            if threat_summary:
                threat_text = ", ".join(f"{count} {level}" for level, count in threat_summary.items())
                report_parts.append(f"Threat levels: {threat_text}")
        
        if result['new_opportunities'] > 0:
            report_parts.append(f"🎯 Found {result['new_opportunities']} expansion opportunities")
            
            # Highlight best opportunity
            best_opportunity = observation_comp.get_best_expansion_target()
            if best_opportunity:
                report_parts.append(f"Best target: {best_opportunity.opportunity_type} at {best_opportunity.position} "
                                  f"(value: {best_opportunity.value_assessment:.1%}, difficulty: {best_opportunity.estimated_difficulty})")
        
        # Add knowledge summary
        report_parts.append(f"Total intelligence: {status['tiles_known']} known tiles, "
                          f"{status['active_threats']} tracked threats, "
                          f"{status['known_opportunities']} known opportunities")
        
        return " | ".join(report_parts)
    
    # Add action description for dynamic prompts
    observe_area.action_description = "**Observe Area**: Scan surrounding terrain for threats, opportunities, and tactical intelligence"
    
    return observe_area


def create_assess_expansion_tool(general_entity) -> Callable:
    """
    Factory function to create an assess_expansion tool for generals.
    """
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    
    observation_comp: TerrainObservation = general_entity.get_component(TerrainObservation)
    position_comp: PositionComponent = general_entity.get_component(PositionComponent)
    group_comp: SubAgentGroup = general_entity.get_component(SubAgentGroup)
    
    if not all([observation_comp, position_comp, group_comp]):
        @function_tool
        def assess_expansion_unavailable() -> str:
            """Expansion assessment unavailable - missing required components."""
            return f"General {general_entity.name} cannot assess expansion - missing capabilities"
        return assess_expansion_unavailable
    
    @function_tool  
    def assess_expansion(ctx: RunContextWrapper["SimulationContext"], target_direction: str = None) -> str:
        """
        Assess expansion opportunities in a specific direction or around current position.
        Analyzes terrain viability, resource potential, and settlement requirements.
        
        Args:
            target_direction: Direction to focus assessment (N, NE, SE, S, SW, NW) or None for all directions
            
        Returns:
            Detailed expansion assessment report
        """
        if not position_comp.position:
            return "Cannot assess expansion - position unknown"
        
        # Get opportunities in the area
        opportunities = observation_comp.get_opportunities_in_area(position_comp.position)
        
        if target_direction:
            # Filter opportunities by direction (approximate)
            # This is a simplified directional filter - could be enhanced
            filtered_opportunities = []
            for opp in opportunities:
                opp_q, opp_r = opp.position
                pos_q, pos_r = position_comp.position
                
                # Simple directional filtering based on coordinate differences
                dq, dr = opp_q - pos_q, opp_r - pos_r
                
                direction_matches = {
                    'N': dr < 0,
                    'NE': dq > 0 and dr <= 0,  
                    'SE': dq > 0 and dr > 0,
                    'S': dr > 0,
                    'SW': dq < 0 and dr >= 0,
                    'NW': dq < 0 and dr < 0
                }
                
                if direction_matches.get(target_direction.upper(), False):
                    filtered_opportunities.append(opp)
            
            opportunities = filtered_opportunities
        
        if not opportunities:
            direction_text = f" in {target_direction} direction" if target_direction else ""
            return f"No expansion opportunities detected{direction_text}. Consider observing the area first."
        
        # Get group capabilities
        settlement_capability = group_comp.get_settlement_capability()
        group_strength = group_comp.get_group_strength()
        
        # Analyze opportunities
        report_parts = []
        direction_text = f" in {target_direction} direction" if target_direction else ""
        report_parts.append(f"Expansion assessment{direction_text}: {len(opportunities)} opportunities found")
        
        # Group capabilities
        report_parts.append(f"Your group strength: {group_strength}, settlement capability: {settlement_capability:.1%}")
        
        # Categorize opportunities
        by_type = {}
        for opp in opportunities:
            by_type[opp.opportunity_type] = by_type.get(opp.opportunity_type, 0) + 1
        
        if by_type:
            type_summary = ", ".join(f"{count} {opp_type}" for opp_type, count in by_type.items())
            report_parts.append(f"Opportunity types: {type_summary}")
        
        # Highlight top 3 opportunities
        sorted_opportunities = sorted(opportunities, key=lambda x: x.value_assessment, reverse=True)
        top_opportunities = sorted_opportunities[:3]
        
        for i, opp in enumerate(top_opportunities, 1):
            feasible = "✓" if settlement_capability >= 0.5 else "✗"
            report_parts.append(f"{i}. {opp.opportunity_type.title()} at {opp.position}: "
                              f"value {opp.value_assessment:.1%}, {opp.estimated_difficulty} difficulty {feasible}")
        
        # Assessment recommendation
        if settlement_capability >= 0.7 and top_opportunities:
            best = top_opportunities[0]
            report_parts.append(f"Recommendation: Strong capability to settle {best.opportunity_type} at {best.position}")
        elif settlement_capability >= 0.4:
            report_parts.append("Recommendation: Moderate settlement capability - consider easier targets")
        else:
            report_parts.append("Recommendation: Low settlement capability - need more workers or supplies")
        
        return " | ".join(report_parts)
    
    # Add action description for dynamic prompts
    assess_expansion.action_description = "**Assess Expansion**: Analyze expansion opportunities and group's capability to settle new territory"
    
    return assess_expansion


def create_settle_territory_tool(general_entity) -> Callable:
    """
    Factory function to create a settle_territory tool for generals.
    """
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.components.territory import TerritoryComponent
    
    observation_comp: TerrainObservation = general_entity.get_component(TerrainObservation)
    position_comp: PositionComponent = general_entity.get_component(PositionComponent)
    group_comp: SubAgentGroup = general_entity.get_component(SubAgentGroup)
    
    if not all([observation_comp, position_comp, group_comp]):
        @function_tool
        def settle_territory_unavailable() -> str:
            """Settlement unavailable - missing required components."""
            return f"General {general_entity.name} cannot settle territory - missing capabilities"
        return settle_territory_unavailable
    
    @function_tool
    def settle_territory(ctx: RunContextWrapper["SimulationContext"], target_direction: str = None) -> str:
        """
        Settle all valid unowned land tiles within 1-tile radius around current position for the parent house.
        Ignores target_direction.
        """
        # Context and prerequisites
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Settlement failed - map access not available"
        if not position_comp.position:
            return "Cannot settle - position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Settlement failed - no parent house connection"
        parent_house = None
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Settlement failed - cannot find parent house"
        house_territory = parent_house.get_component(TerritoryComponent)
        if not house_territory:
            return "Settlement failed - parent house has no territory management"
        
        # Collect unowned, non-water tiles in radius 1
        from feudal_sim.map.types import HexTileType
        q0, r0 = position_comp.position
        neighbors = [(0,0), (1,0), (-1,0), (0,1), (0,-1), (1,-1), (-1,1)]
        targets = []
        for dq, dr in neighbors:
            tile = sim_context.hex_grid.get_tile(q0 + dq, r0 + dr)
            if not tile:
                continue
            if getattr(tile, 'owner', None):
                continue
            terrain = getattr(tile, 'terrain_type', None)
            if terrain in {HexTileType.OCEAN, HexTileType.LAKE}:
                continue
            targets.append(tile)
        
        if not targets:
            return ObservationFormatter.settlement_result(0)
        
        # Execute settlement via house wrapper for proper updates
        try:
            parent_house.expand_territory(targets, sim_context.hex_grid)
        except Exception:
            # Fallback to direct component
            house_territory.expand_territory(targets, sim_context.hex_grid, house_territory.territory_color)
        
        # Update group state
        try:
            supply_cost = 10 + max(0, len(targets) - 1) * 5
            group_comp.consume_supplies(supply_cost)
            group_comp.record_action_result(True, experience_gained=2)
        except Exception:
            pass
        
        return ObservationFormatter.settlement_result(len(targets))
    
    # Add action description for dynamic prompts
    settle_territory.action_description = "**Settle Nearby Tiles**: Claim unowned tiles within 1-tile radius for your house"
    
    return settle_territory


def create_general_toolset(general_entity) -> list:
    """Create tools for general entities."""
    tools = []
    
    # Basic movement tool (direction-based for generals)
    from feudal_sim.components.position import PositionComponent
    from agents import function_tool, RunContextWrapper
    from feudal_sim.ai.context import SimulationContext
    
    @function_tool
    def move(ctx: RunContextWrapper["SimulationContext"], direction: str) -> str:
        """
        Move one tile in a direction (N, NE, SE, S, SW, NW).
        Consumes movement points and respects terrain/movement validation.
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Movement failed - map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Movement failed - position unknown"
        valid_dirs = ["N", "NE", "SE", "S", "SW", "NW"]
        dir_upper = (direction or "").upper()
        if dir_upper not in valid_dirs:
            return f"Invalid direction '{direction}'. Valid directions: {', '.join(valid_dirs)}"
        q, r = pos.position
        # Find neighbor in the requested direction
        target = None
        for neigh, dirn in sim_context.hex_grid.get_neighbors(q, r):
            if dirn == dir_upper and neigh is not None:
                target = (neigh.q, neigh.r)
                break
        if not target:
            return f"Cannot move {dir_upper.lower()} from current position"
        result = pos.move_to(
            target_position=target,
            hex_grid=sim_context.hex_grid,
            current_turn=getattr(sim_context, 'current_turn', None),
            validate_movement=True,
        )
        return result.get('message', 'Move attempted')
    move.action_description = "**Move (direction)**: Advance one tile N/NE/SE/S/SW/NW (costs movement points)"
    tools.append(move)
    
    # General → Lord communication via raven (simple)
    from feudal_sim.components.rookery import RookeryComponent
    from agents import function_tool, RunContextWrapper
    
    @function_tool
    def send_raven_to_lord(ctx: RunContextWrapper["SimulationContext"], message: str) -> str:
        """
        Send a raven back to your lord with a short status or request.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send raven - simulation context unavailable"
        if not hasattr(general_entity, 'house_id'):
            return "Cannot send raven - no parent house assigned"
        parent = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent:
            return "Cannot send raven - parent house not found"
        # Ensure both sides have rookeries and know each other
        parent_rookery = parent.get_component(RookeryComponent)
        general_rookery = general_entity.get_component(RookeryComponent)
        if not general_rookery:
            general_rookery = RookeryComponent(entity_id=general_entity.id)
            general_entity.add_component(general_rookery)
        if not parent_rookery:
            parent_rookery = RookeryComponent(entity_id=parent.id)
            parent.add_component(parent_rookery)
        parent_rookery.add_known_recipient(general_entity.id, general_entity.name, discovered=False)
        general_rookery.add_known_recipient(parent.id, parent.name, discovered=False)
        # Date context
        status = {
            'turn': getattr(sim_context, 'current_turn', 1),
            'date': getattr(sim_context, 'current_date', 'Week 1, Spring, Year 1')
        }
        parent_rookery.set_current_date_context(status['turn'], status['date'])
        general_rookery.set_current_date_context(status['turn'], status['date'])
        ok = general_rookery.send_raven(parent.id, message)
        return "Raven dispatched to your lord" if ok else "Failed to dispatch raven"
    send_raven_to_lord.action_description = "**Send Raven to Lord**: Communicate status or requests back to your house"
    tools.append(send_raven_to_lord)
    
    # One-tile observation for simplicity
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.components.position import PositionComponent
    
    @function_tool
    def observe_area(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Observe tiles within 1 tile radius around you and summarize threats/opportunities.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Observation failed - map access not available"
        obs: TerrainObservation = general_entity.get_component(TerrainObservation)
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not obs or not pos or not pos.position:
            return "Observation failed - missing components or position"
        current_turn = getattr(sim_context, 'current_turn', 0)
        # Temporarily limit range to 1
        original = obs.observation_range
        obs.observation_range = 1
        try:
            result = obs.observe_current_area(sim_context.hex_grid, pos.position, current_turn)
        finally:
            obs.observation_range = original
        # Fetch localized intelligence
        threats = obs.get_threats_in_area(pos.position, search_range=1)
        opportunities = obs.get_opportunities_in_area(pos.position, search_range=1)
        # Build summaries
        threat_counts: Dict[str, int] = {}
        for t in threats:
            threat_counts[t.threat_level] = threat_counts.get(t.threat_level, 0) + 1
        
        # Helper: map hex grid direction labels to prose
        dir_prose = {
            "N": "north",
            "NE": "northeast",
            "SE": "southeast",
            "S": "south",
            "SW": "southwest",
            "NW": "northwest",
            "CENTER": "here"
        }

        # Natural language landscape summary within 1 tile
        hex_grid = sim_context.hex_grid
        from feudal_sim.map.types import HexTileType
        from feudal_sim.map.city_extensions import has_city, format_city_display
        tiles_in_radius = []
        center_tile = hex_grid.get_tile(pos.position[0], pos.position[1])
        if center_tile:
            tiles_in_radius.append((center_tile, "CENTER"))
        for neigh, dirn in hex_grid.get_neighbors(pos.position[0], pos.position[1]):
            if neigh:
                tiles_in_radius.append((neigh, dirn))
        
        # Simple human-friendly names for some terrains (moved up for reuse)
        def friendly_terrain(terr):
            if terr is None:
                return 'unknown'
            name = getattr(terr, 'value', str(terr)).lower()
            # Remove the "hextiletype." prefix if present
            if '.' in name:
                name = name.split('.')[-1]
            mapping = {
                'grassland': 'plains',
                'temperate_forest': 'forest',
                'boreal_forest': 'forest',
                'rainforest': 'rainforest',
                'ice_cap': 'ice',
                'tundra': 'tundra',
                'desert': 'desert',
                'steppe': 'grassland',
                'hill': 'hills',
                'mountain': 'mountains',
                'ocean': 'ocean',
                'lake': 'lake',
                'river': 'river'
            }
            return mapping.get(name, name.replace('_', ' '))
        
        terrain_counts_local: Dict[str, int] = {}
        ownership = {"ours": 0, "unowned": 0, "other": 0}
        owner_dirs: Dict[str, list] = {"ours": [], "unowned": []}
        other_owner_dirs: Dict[str, list] = {}
        city_highlights: list = []
        for tile, dirn in tiles_in_radius:
            terr_name = friendly_terrain(getattr(tile, 'terrain_type', None))
            terrain_counts_local[terr_name] = terrain_counts_local.get(terr_name, 0) + 1
            owner = getattr(tile, 'owner', None)
            if not owner:
                ownership["unowned"] += 1
                if dirn != "CENTER":
                    owner_dirs.setdefault("unowned", []).append(dir_prose.get(dirn, dirn))
            elif hasattr(owner, 'id') and owner.id == getattr(general_entity, 'house_id', None):
                ownership["ours"] += 1
                if dirn != "CENTER":
                    owner_dirs.setdefault("ours", []).append(dir_prose.get(dirn, dirn))
            else:
                ownership["other"] += 1
                if dirn != "CENTER":
                    name = getattr(owner, 'name', getattr(owner, 'id', 'other'))
                    other_owner_dirs.setdefault(name, []).append(dir_prose.get(dirn, dirn))
            # City presence
            if dirn != "CENTER" and has_city(tile):
                city_text = format_city_display(tile)
                if city_text:
                    city_highlights.append(f"{dirn}: {city_text}")
        
        # Terrain mix text
        terrain_sorted = sorted(terrain_counts_local.items(), key=lambda kv: kv[1], reverse=True)
        if terrain_sorted:
            primary = terrain_sorted[0][0]
            mix_text = f"mostly {primary}"
            if len(terrain_sorted) > 1:
                secondary = terrain_sorted[1][0]
                mix_text += f" with some {secondary}"
        else:
            mix_text = "mixed terrain"
        
        # Directional ownership summary (compact)
        claims_text = ObservationFormatter.borders_summary(
            owner_dirs.get("ours", []), owner_dirs.get("unowned", []), other_owner_dirs
        )
        
        # Nearby units summary (within 1 tile)
        units_text = ""
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            nearby = sim_context.entity_manager.get_positioned_entities_near(pos.position, 1)
            friendly: list[str] = []
            enemy: list[str] = []
            for ent, _d in nearby:
                if ent.id == general_entity.id:
                    continue
                ent_pos = ent.get_component(PositionComponent)
                ent_dir = None
                if ent_pos and ent_pos.position:
                    for nn, nd in hex_grid.get_neighbors(pos.position[0], pos.position[1]):
                        if nn and (nn.q, nn.r) == ent_pos.position:
                            ent_dir = dir_prose.get(nd, nd)
                            break
                house_id = getattr(ent, 'house_id', None)
                if house_id == getattr(general_entity, 'house_id', None):
                    friendly.append(ent_dir or "adjacent")
                else:
                    enemy.append(ent_dir or "adjacent")
            summary = ObservationFormatter.units_summary(friendly, enemy)
            if summary:
                units_text = " | " + summary
        
        intro = f"From our current position, the immediate surroundings are {mix_text}."
        own_text = f" Unowned tiles nearby: {ownership['unowned']}."
        threat_text = ""
        if threats:
            breakdown = ", ".join(f"{cnt} {lvl}" for lvl, cnt in threat_counts.items())
            threat_text = f" Threats detected: {breakdown}."
        
        # City info
        city_text = ""
        if city_highlights:
            city_text = " | Settlements: " + "; ".join(city_highlights[:3])
        
        dirs_text = f" | Borders: {claims_text}"
        
        nl_report = intro + own_text + threat_text + dirs_text + city_text + units_text
        
        return nl_report
    observe_area.action_description = "**Observe (1 tile)**: Scan the immediate surroundings"
    tools.append(observe_area)
    
    # Simple settle within 1 tile radius
    from feudal_sim.components.territory import TerritoryComponent
    
    @function_tool
    def settle_tiles(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Settle any unowned land tiles within 1 tile radius for your parent house.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not sim_context.entity_manager:
            return "Settlement failed - simulation context unavailable"
        if not hasattr(general_entity, 'house_id'):
            return "Settlement failed - no parent house"
        parent = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent:
            return "Settlement failed - parent house not found"
        pos = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Settlement failed - position unknown"
        q0, r0 = pos.position
        targets = []
        for dq, dr in [(0,0), (1,0), (-1,0), (0,1), (0,-1), (1,-1), (-1,1)]:
            tile = sim_context.hex_grid.get_tile(q0 + dq, r0 + dr)
            if tile and getattr(tile, 'terrain_type', None) is not None:
                from feudal_sim.map.types import HexTileType
                if tile.terrain_type not in {HexTileType.OCEAN, HexTileType.LAKE} and not getattr(tile, 'owner', None):
                    targets.append(tile)
        if not targets:
            return "No unowned tiles within 1 tile to settle"
        # Use house wrapper to expand for proper capacity updates and color
        try:
            parent.expand_territory(targets, sim_context.hex_grid)
        except Exception:
            # Fallback to direct component call if wrapper unavailable
            from feudal_sim.components.territory import TerritoryComponent
            house_territory = parent.get_component(TerritoryComponent)
            if not house_territory:
                return "Settlement failed - parent house has no territory management"
            house_territory.expand_territory(targets, sim_context.hex_grid, house_territory.territory_color)
        return f"Settled {len(targets)} nearby tiles for your house"
    settle_tiles.action_description = "**Settle Nearby Tiles**: Claim unowned tiles within 1 tile radius for your house"
    tools.append(settle_tiles)
    
    # Territory management tools
    tools.append(create_settle_territory_tool(general_entity))
    
    # Universal tools
    tools.append(end_turn)
    
    # Future general-specific tools:
    # tools.append(create_fortify_position_tool(general_entity))
    
    return tools


# Tool categories for different entity types
def create_army_toolset(_army_entity) -> list:
    """Create tools for army entities (future implementation)."""
    tools = []
    
    # Universal tools
    tools.append(end_turn)
    
    return tools


def create_scout_toolset(_scout_entity) -> list:
    """Create tools for scout entities (future implementation).""" 
    tools = []
    
    # Universal tools
    tools.append(end_turn)
    
    return tools


def create_caravan_toolset(_caravan_entity) -> list:
    """Create tools for caravan entities (future implementation)."""
    tools = []
    
    # Universal tools
    tools.append(end_turn)
    
    return tools


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