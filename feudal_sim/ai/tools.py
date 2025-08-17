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
        Send a raven message to another house or entity. Ravens take time to deliver — messages sent this week will arrive next week. Consider waiting for a response before sending additional messages.
        
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
            return f"Raven sent to {recipient_name}: '{message}' — message will arrive next week."
        else:
            return f"Failed to send raven to {recipient_name} — unknown recipient or other error"
    
    # Add action description for dynamic prompts
    send_raven.action_description = "**Send Ravens**: Dispatch messages to other lords (ravens arrive next week)"
    
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
        View information about all your cities including their characteristics, bonuses, and development levels.
        
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
            territory_component.get_border_tiles_by_direction(direction_upper, hex_grid)
            
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
            return "Failed to assign population to general - insufficient available population"
        
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

        # Ensure both sides have rookeries and know each other
        try:
            from feudal_sim.components.rookery import RookeryComponent
            # General rookery
            general_rookery = general_entity.get_component(RookeryComponent)
            if not general_rookery:
                general_rookery = RookeryComponent(entity_id=general_id)
                general_entity.add_component(general_rookery)
            # House rookery
            house_rookery = house_entity.get_component(RookeryComponent)
            if not house_rookery:
                house_rookery = RookeryComponent(entity_id=house_entity.id)
                house_entity.add_component(house_rookery)
            # Register each other as known recipients (no discovery spam)
            house_rookery.add_known_recipient(general_id, general_name, discovered=False)
            general_rookery.add_known_recipient(house_entity.id, house_entity.name, discovered=False)
            # Seed current date context if available
            if ctx and ctx.context:
                status_turn = getattr(ctx.context, 'current_turn', 1)
                status_date = getattr(ctx.context, 'current_date', 'Week 1, Spring, Year 1')
                house_rookery.set_current_date_context(status_turn, status_date)
                general_rookery.set_current_date_context(status_turn, status_date)
        except Exception:
            pass
        
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
                f"Deployed to a border position in the {direction}. Group strength: {group_strength}, {capability_text}. "
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


def create_rookery_toolset(entity, include_send: bool = True) -> list:
    """
    Shared rookery tools for any entity with a RookeryComponent.
    - list_known_recipients: list all known recipient IDs
    - send_raven(recipient_id, message): send to any known recipient (optional)
    """
    tools = []
    from feudal_sim.components.rookery import RookeryComponent

    @function_tool
    def list_known_recipients(ctx: RunContextWrapper["SimulationContext"]) -> str:
        rookery: RookeryComponent = entity.get_component(RookeryComponent)
        if not rookery:
            return "No rookery available"
        known = rookery.get_known_recipients_list()
        return ", ".join(known) if known else "No known recipients"
    list_known_recipients.action_description = "**List Known Recipients**: See who you can send ravens to"
    tools.append(list_known_recipients)

    if include_send:
        @function_tool
        def send_raven(ctx: RunContextWrapper["SimulationContext"], recipient_id: str, message: str) -> str:
            sim_context = ctx.context
            rookery: RookeryComponent = entity.get_component(RookeryComponent)
            if not rookery:
                return "Cannot send raven - no rookery"
            if sim_context:
                rookery.set_current_date_context(
                    getattr(sim_context, 'current_turn', 1),
                    getattr(sim_context, 'current_date', 'Week 1, Spring, Year 1')
                )
            ok = rookery.send_raven(recipient_id, message)
            return "Raven dispatched; arrives next week" if ok else "Failed to dispatch raven (unknown recipient)"
        send_raven.action_description = "**Send Raven**: Message any known recipient (arrives next week)"
        tools.append(send_raven)

    return tools


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
    
    # Tax collection tools
    tools.append(create_collect_taxes_tool(house))

    # Feasts / social actions
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.core.config import config
    
    @function_tool
    def hold_feast(ctx: RunContextWrapper["SimulationContext"], food_cost: int = 100, gold_cost: int = 50) -> str:
        """
        Hold a feast to increase population loyalty at the cost of food and gold. Has a short cooldown.
        Default costs can be overridden. Effects scale mildly with spend.
        """
        sim_context = ctx.context
        pop: PopulationComponent = house.get_component(PopulationComponent)
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not pop or not res:
            return "Cannot hold feast - missing population or resource management"
        # Cooldown
        current_turn = getattr(sim_context, 'current_turn', 0) if sim_context else 0
        cooldown = config.get('simulation.population.feast.cooldown_turns', 4)
        if hasattr(pop, 'last_feast_turn') and current_turn - pop.last_feast_turn < cooldown:
            return f"Cannot hold feast yet - available in {cooldown - (current_turn - pop.last_feast_turn)} turns"
        # Validate costs
        food_cost = max(0, int(food_cost))
        gold_cost = max(0, int(gold_cost))
        costs = {}
        if food_cost > 0:
            costs['food'] = food_cost
        if gold_cost > 0:
            costs['gold'] = gold_cost
        if costs and not res.can_afford_action(costs):
            return f"Insufficient resources for feast: need {food_cost} food and {gold_cost} gold"
        # Consume resources
        if costs:
            res.consume_for_action(costs, 'Hold Feast')
        # Loyalty effect (bounded, scaled by spend)
        base_boost = config.get('simulation.population.feast.base_loyalty_boost', 8)
        food_factor = config.get('simulation.population.feast.food_factor', 0.02)
        gold_factor = config.get('simulation.population.feast.gold_factor', 0.03)
        boost = int(base_boost + food_factor * food_cost + gold_factor * gold_cost)
        pop.loyalty = min(100, pop.loyalty + max(1, boost))
        # Set cooldown
        pop.last_feast_turn = current_turn
        # Observation for house AI
        try:
            from feudal_sim.components.ai import AIComponent
            ai: AIComponent = house.get_component(AIComponent)
            if ai:
                ai.add_observation(
                    f"Held a feast: -{food_cost} food, -{gold_cost} gold; loyalty increased to {pop.loyalty}",
                    phase="Actions"
                )
        except Exception:
            pass
        return f"Feast held. Loyalty now {pop.loyalty}."
    hold_feast.action_description = "**Hold Feast**: Spend food and gold to boost loyalty (cooldown applies)"
    tools.append(hold_feast)
    
    # Population management tools
    tools.append(create_manage_household_tool(house))
    
    # Military deployment tools
    tools.append(create_deploy_general_tool(house))
    
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

    # Shared rookery tools (list only; house already has a specialized send tool)
    tools.extend(create_rookery_toolset(house, include_send=False))
    
    # Universal tools
    tools.append(end_turn)
    
    # Future tools can be added here:
    # tools.append(create_dispatch_army_tool(house))
    # tools.append(create_dispatch_scout_tool(house))
    
    return tools


def create_general_toolset(general_entity) -> list:
    """Create tools for general entities."""
    tools = []
    
        # Basic movement tool (direction-based for generals)
    from feudal_sim.components.position import PositionComponent
    
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
            obs.observe_current_area(sim_context.hex_grid, pos.position, current_turn)
        finally:
            obs.observation_range = original
        # Fetch localized intelligence
        threats = obs.get_threats_in_area(pos.position, search_range=1)
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
        from feudal_sim.map.city_extensions import has_city, format_city_display
        tiles_in_radius = []
        center_tile = hex_grid.get_tile(pos.position[0], pos.position[1])
        if center_tile:
            tiles_in_radius.append((center_tile, "CENTER"))
        for neigh, dirn in hex_grid.get_neighbors(pos.position[0], pos.position[1]):
            if neigh:
                tiles_in_radius.append((neigh, dirn))
        
        def friendly_terrain(terr):
            if terr is None:
                return 'unknown'
            name = getattr(terr, 'value', str(terr)).lower()
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
            if dirn != "CENTER" and has_city(tile):
                city_text = format_city_display(tile)
                if city_text:
                    city_highlights.append(f"{dirn}: {city_text}")
        
        terrain_sorted = sorted(terrain_counts_local.items(), key=lambda kv: kv[1], reverse=True)
        if terrain_sorted:
            primary = terrain_sorted[0][0]
            mix_text = f"mostly {primary}"
            if len(terrain_sorted) > 1:
                secondary = terrain_sorted[1][0]
                mix_text += f" with some {secondary}"
        else:
            mix_text = "mixed terrain"
        
        claims_text = ObservationFormatter.borders_summary(
            owner_dirs.get("ours", []), owner_dirs.get("unowned", []), other_owner_dirs
        )
        
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
    def settle_territory(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Settle the tile you are currently standing on for the parent house (if unowned land).
        Consumes house materials per settlement.
        """
        # Context and prerequisites
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Settlement failed - map access not available"
        position_comp: PositionComponent = general_entity.get_component(PositionComponent)
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
        
        # Only current tile
        q0, r0 = position_comp.position
        tile = sim_context.hex_grid.get_tile(q0, r0)
        if not tile:
            return "Settlement failed - tile not found"
        # Must be unowned land
        from feudal_sim.map.types import HexTileType
        if getattr(tile, 'owner', None):
            return "Settlement failed - this tile is already owned"
        terrain = getattr(tile, 'terrain_type', None)
        if terrain in {HexTileType.OCEAN, HexTileType.LAKE}:
            return "Settlement failed - cannot settle water tiles"

        # Costs from config
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.core.config import config
        res_comp: ResourceComponent = parent_house.get_component(ResourceComponent)
        if not res_comp:
            return "Settlement failed - parent house cannot manage resources"
        mat_cost = int(config.get('simulation.subagents.settlement_material_cost', 8))
        costs = {'material': mat_cost} if mat_cost > 0 else {}
        if costs and not res_comp.can_afford_action(costs):
            return f"Settlement failed - insufficient materials (need {mat_cost})"

        # Consume costs and expand
        if costs:
            res_comp.consume_for_action(costs, 'Settle Tile')
        try:
            parent_house.expand_territory([tile], sim_context.hex_grid)
        except Exception:
            # Fallback to direct component
            house_territory.expand_territory([tile], sim_context.hex_grid, house_territory.territory_color)

        # Update group state
        try:
            from feudal_sim.components.subagent_group import SubAgentGroup
            grp = general_entity.get_component(SubAgentGroup)
            if grp:
                grp.consume_supplies(5)
                grp.record_action_result(True, experience_gained=2)
        except Exception:
            pass

        return "Settled current tile for your house"
    settle_territory.action_description = "**Settle Current Tile**: Claim the unowned land tile you are standing on (costs materials)"
    tools.append(settle_territory)
    
    # Establish a small outpost/camp on a controlled tile
    
    @function_tool
    def build_outpost(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Build an outpost/camp on your current tile (must be controlled by your house).
        Claims all valid, land, unowned tiles within 1 tile radius.
        Consumes house resources (configurable).
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Outpost construction failed - map access not available"
        position_comp: PositionComponent = general_entity.get_component(PositionComponent)
        if not position_comp or not position_comp.position:
            return "Outpost construction failed - position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Outpost construction failed - no parent house connection"
        parent_house = None
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Outpost construction failed - cannot find parent house"
        house_territory = parent_house.get_component(TerritoryComponent)
        if not house_territory:
            return "Outpost construction failed - parent house has no territory management"
        
        # Must be built on a controlled tile
        q0, r0 = position_comp.position
        center_tile = sim_context.hex_grid.get_tile(q0, r0)
        if not center_tile:
            return "Outpost construction failed - tile not found"
        owner = getattr(center_tile, 'owner', None)
        if not owner or not hasattr(owner, 'id') or owner.id != parent_house.id:
            return "Outpost construction failed - outposts must be built on your controlled land"

        # Spacing constraint: enforce minimum distance from any existing settlement (cities/outposts)
        try:
            from feudal_sim.components.city import CityComponent
            from feudal_sim.core.config import config as _cfg
            min_spacing = int(_cfg.get('simulation.settlements.min_spacing_tiles', 3))
            # Gather all settlement positions across all houses
            nearest_dist = None
            nearest_name = None
            if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
                all_houses = sim_context.entity_manager.get_entities_by_type('house') or []
                for h in all_houses:
                    cc: CityComponent = h.get_component(CityComponent)
                    if not cc:
                        continue
                    for city in cc.get_all_cities().values():
                        cq, cr = city.position
                        # Hex distance using axial coords
                        s1 = -q0 - r0
                        s2 = -cq - cr
                        dist = (abs(q0 - cq) + abs(r0 - cr) + abs(s1 - s2)) // 2
                        if nearest_dist is None or dist < nearest_dist:
                            nearest_dist = dist
                            nearest_name = getattr(city, 'name', 'settlement')
            if nearest_dist is not None and nearest_dist < min_spacing:
                return (
                    f"Outpost construction failed - too close to existing settlement "
                    f"('{nearest_name}' at {nearest_dist} tiles). Minimum spacing is {min_spacing} tiles."
                )
        except Exception:
            pass
        
        # Costs from config
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.core.config import config
        res_comp: ResourceComponent = parent_house.get_component(ResourceComponent)
        if not res_comp:
            return "Outpost construction failed - parent house cannot manage resources"
        outpost_mat = int(config.get('simulation.settlements.outpost.material_cost', 15))
        outpost_gold = int(config.get('simulation.settlements.outpost.gold_cost', 10))
        costs = {}
        if outpost_mat > 0:
            costs['material'] = outpost_mat
        if outpost_gold > 0:
            costs['gold'] = outpost_gold
        if costs and not res_comp.can_afford_action(costs):
            return f"Outpost construction failed - insufficient resources (need {outpost_mat} material, {outpost_gold} gold)"
        
        # Identify claimable neighbors within 1 tile radius
        from feudal_sim.map.types import HexTileType
        hex_grid = sim_context.hex_grid
        to_claim = []
        # Include immediate neighbors only (not center)
        for neigh, _dirn in hex_grid.get_neighbors(q0, r0):
            if not neigh:
                continue
            if getattr(neigh, 'owner', None):
                continue  # already owned
            terr = getattr(neigh, 'terrain_type', None)
            if terr in {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER}:
                continue  # water cannot be claimed
            to_claim.append(neigh)
        
        # Consume resources, build, and claim
        if costs:
            res_comp.consume_for_action(costs, 'Build Outpost (Order)')
        
        # Create delayed outpost construction order (resolves next week)
        from feudal_sim.components.territory import TerritoryComponent as _Terr
        current_turn = getattr(sim_context, 'current_turn', 0)
        house_territory: _Terr = parent_house.get_component(_Terr)
        delay = int(config.get('simulation.settlements.outpost_delay_turns', 1))
        house_territory.create_outpost_order((q0, r0), current_turn, delay_turns=delay, resource_cost=costs)
        
        # Group adjustments and observations (order placed)
        try:
            from feudal_sim.components.subagent_group import SubAgentGroup
            grp = general_entity.get_component(SubAgentGroup)
            if grp:
                grp.consume_supplies(2)
                grp.record_action_result(True, experience_gained=1)
        except Exception:
            pass
        
        # Notify house AI about order timing
        try:
            from feudal_sim.components.ai import AIComponent
            ai = parent_house.get_component(AIComponent)
            if ai:
                ai.add_observation(
                    f"Outpost construction ordered at a controlled site; completion expected next week",
                    phase="Actions"
                )
        except Exception:
            pass
        
        return "Outpost construction ordered; it will complete next week."
    build_outpost.action_description = "**Build Outpost**: Establish a small camp on controlled land to claim adjacent unowned tiles (costs resources)"
    tools.append(build_outpost)
    
    # Shared rookery tools for generals (include send)
    tools.extend(create_rookery_toolset(general_entity, include_send=True))
    
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