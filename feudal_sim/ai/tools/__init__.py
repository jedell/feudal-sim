"""
AI Tools for the feudal simulation.

This module contains tool functions that AI agents can call to interact with the simulation.
Each tool is decorated with @function_tool to make it available to the OpenAI Agents SDK.

Tools need access to the current entity/house context, so they will be created by factory functions
that bind the specific house instance to the tool.
"""

from agents import function_tool, RunContextWrapper
from typing import Callable, Dict, List
from enum import Enum

from feudal_sim.ai.context import SimulationContext
from feudal_sim.utils.observations import ObservationFormatter
from feudal_sim.config.subagents import get_general_cap, get_deploy_costs


def _balance_line(resource_component, keys: list) -> str:
    """Return 'Remaining: X food, Y gold.' for the listed resource keys."""
    parts = [f"{resource_component.resources.get(k):.0f} {k}" for k in keys]
    return "Remaining: " + ", ".join(parts) + "."


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
            if not (0.01 <= tax_rate <= 1.0):
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
        current_generals = len(territory_component.deployed_generals)
        territory_size = len(getattr(territory_component, 'territory', []))
        max_generals = get_general_cap(territory_size)
        if current_generals >= max_generals:
            return (
                f"Cannot deploy another general: cap reached ({current_generals}/{max_generals}). "
                f"Gain more territory to increase your command capacity."
            )
        
        # Costs: base + per-person equipping.
        # Check population AND resources together before consuming either to avoid
        # partial-commit state if one check passes but the other fails.
        resource_component = house_entity.get_component(ResourceComponent)
        if not resource_component:
            return "Cannot deploy general - missing resource management"
        costs = get_deploy_costs(soldiers_assigned, workers_assigned)
        if not resource_component.can_afford_action(costs):
            return (
                "Cannot deploy general - insufficient resources: "
                f"need {costs['gold']} gold and {costs['material']} material"
            )
        if not population_component.can_assign_population(workers_assigned, soldiers_assigned):
            available = population_component.get_available_population()
            return f"Cannot deploy general - only {available} people available"
        resource_component.consume_for_action(costs, "Deploy General")
        
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
        
        # Immediately update renderer to show newly deployed general
        try:
            positioned_entities = sim_context.entity_manager.get_entities_by_type('general') or []
            sim_context.hex_grid.render(sim_context.houses, positioned_entities)
        except Exception:
            pass  # Don't fail deployment if render update fails
        
        total_assigned = soldiers_assigned + workers_assigned
        balance = _balance_line(resource_component, ['gold', 'material'])

        # Outpost spacing advisory — tell the lord how far the general must travel before building
        spacing_note = ""
        try:
            from feudal_sim.components.city import CityComponent as _CC2
            from feudal_sim.core.config import config as _cfg3
            _min_sp2 = int(_cfg3.get('simulation.settlements.min_spacing_tiles', 3))
            _cc2 = house_entity.get_component(_CC2)
            _best_d2, _best_n2 = None, None
            if _cc2:
                for _c2 in _cc2.get_all_cities().values():
                    _cq2, _cr2 = _c2.position
                    _dq2, _dr2 = deployment_position
                    _d2 = (abs(_dq2 - _cq2) + abs(_dr2 - _cr2) + abs((-_dq2 - _dr2) - (-_cq2 - _cr2))) // 2
                    if _best_d2 is None or _d2 < _best_d2:
                        _best_d2, _best_n2 = _d2, getattr(_c2, 'name', 'settlement')
            if _best_d2 is not None and _best_d2 < _min_sp2:
                _need = _min_sp2 - _best_d2
                spacing_note = (f" Note: deployment is {_best_d2} tile(s) from {_best_n2} — "
                                f"general must advance {_need} more tile(s) before outpost spacing allows building.")
        except Exception:
            pass

        return (f"Successfully deployed {general_name} to the {direction} "
                f"(position {deployment_position[0]},{deployment_position[1]}) "
                f"with {total_assigned} people ({soldiers_assigned} soldiers, {workers_assigned} workers). "
                f"Group strength: {group_strength}, {capability_text}. "
                f"Orders: '{orders}'.{spacing_note} "
                f"{balance}")
    
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
        """
        List all known recipients for sending ravens.
        """
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
            """
            Send a raven message to another house or entity.
            """
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


def create_send_trade_caravan_tool(house_entity) -> Callable:
    """
    Factory function to create a send_trade_caravan tool bound to a specific house entity.
    """
    from feudal_sim.components.rookery import RookeryComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.territory import TerritoryComponent
    
    rookery_component = house_entity.get_component(RookeryComponent)
    resource_component = house_entity.get_component(ResourceComponent)
    territory_component = house_entity.get_component(TerritoryComponent)
    
    if not rookery_component:
        @function_tool
        def send_trade_caravan_no_rookery(recipient: str, goods_offered: str, terms: str) -> str:
            """No rookery available for trade communications."""
            return f"House {house_entity.name} has no rookery to coordinate trade caravans"
        return send_trade_caravan_no_rookery
    
    if not resource_component or not territory_component:
        @function_tool
        def send_trade_caravan_missing_components(recipient: str, goods_offered: str, terms: str) -> str:
            """Missing required components for trade caravan dispatch."""
            return f"House {house_entity.name} cannot send trade caravans - missing required components"
        return send_trade_caravan_missing_components
    
    # Get known recipients for trade targets
    known_recipients = rookery_component.get_known_recipients_list()
    
    if not known_recipients:
        @function_tool
        def send_trade_caravan_no_recipients(recipient: str, goods_offered: str, terms: str) -> str:
            """No known recipients for trade."""
            return f"House {house_entity.name} has no known houses to trade with"
        return send_trade_caravan_no_recipients
    
    # Create dynamic enum for recipients
    recipient_dict = {name: name for name in known_recipients}
    RecipientEnum = Enum('TradeRecipient', recipient_dict)
    
    @function_tool
    def send_trade_caravan(ctx: RunContextWrapper["SimulationContext"], 
                          recipient: RecipientEnum, 
                          food_offered: int = 0, 
                          material_offered: int = 0, 
                          metal_offered: int = 0, 
                          gold_offered: int = 0,
                          terms: str = "Standard trade agreement",
                          direction: str = "") -> str:
        """
        Dispatch a trade caravan to another house with specified goods and terms.
        The caravan will physically travel to the recipient and trigger a priority negotiation.
        
        Args:
            recipient: The house to send the trade caravan to (must be known recipient)
            food_offered: Amount of food to offer in trade (default 0)
            material_offered: Amount of material to offer in trade (default 0) 
            metal_offered: Amount of metal to offer in trade (default 0)
            gold_offered: Amount of gold to offer in trade (default 0)
            terms: Description of trade terms and what you want in return
            direction: Optional direction hint for route planning (N, NE, SE, S, SW, NW)
            
        Returns:
            Result of dispatching the trade caravan
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Trade caravan dispatch failed - map access not available"
        
        recipient_name = recipient.value
        
        # Validate that we have goods to trade
        total_goods = food_offered + material_offered + metal_offered + gold_offered
        if total_goods <= 0:
            return "Cannot send empty trade caravan - must offer at least some goods"
        
        # Check if we have the resources to offer
        current_resources = resource_component.resources
        insufficient = []
        if food_offered > current_resources.food:
            insufficient.append(f"food (need {food_offered}, have {current_resources.food:.0f})")
        if material_offered > current_resources.material:
            insufficient.append(f"material (need {material_offered}, have {current_resources.material:.0f})")
        if metal_offered > current_resources.metal:
            insufficient.append(f"metal (need {metal_offered}, have {current_resources.metal:.0f})")
        if gold_offered > current_resources.gold:
            insufficient.append(f"gold (need {gold_offered}, have {current_resources.gold:.0f})")
        
        if insufficient:
            return f"Cannot send trade caravan - insufficient resources: {', '.join(insufficient)}"
        
        # Find recipient house
        if not hasattr(sim_context, 'entity_manager') or not sim_context.entity_manager:
            return "Trade caravan dispatch failed - cannot access entity manager"
        
        recipient_house = None
        for entity in sim_context.entity_manager.get_all_entities():
            if hasattr(entity, 'name') and entity.name == recipient_name:
                recipient_house = entity
                break
        
        if not recipient_house:
            return f"Cannot find recipient house '{recipient_name}'"
        
        # Create trade goods
        from feudal_sim.components.cargo import TradeGoods
        trade_goods = TradeGoods(
            food=float(food_offered),
            material=float(material_offered),
            metal=float(metal_offered),
            gold=float(gold_offered)
        )
        
        # Consume resources from sending house
        costs = {}
        if food_offered > 0:
            costs['food'] = food_offered
        if material_offered > 0:
            costs['material'] = material_offered
        if metal_offered > 0:
            costs['metal'] = metal_offered
        if gold_offered > 0:
            costs['gold'] = gold_offered
        
        resource_component.consume_for_action(costs, "Send Trade Caravan")
        
        # Find starting position (center of our territory)
        starting_position = None
        if territory_component.territory:
            # Convert set to list for calculation
            territory_tiles = list(territory_component.territory)
            
            # Use center of territory as starting position
            total_q = sum(tile.q for tile in territory_tiles)
            total_r = sum(tile.r for tile in territory_tiles)
            center_q = int(total_q / len(territory_tiles))
            center_r = int(total_r / len(territory_tiles))
            
            # Find closest territory tile to centroid
            min_distance = float('inf')
            for tile in territory_tiles:
                distance = abs(tile.q - center_q) + abs(tile.r - center_r)
                if distance < min_distance:
                    min_distance = distance
                    starting_position = (tile.q, tile.r)
        
        if not starting_position:
            return "Cannot determine starting position for trade caravan"
        
        # Create and dispatch trade caravan
        from feudal_sim.entities.caravan import TradeCaravan
        
        caravan = TradeCaravan.create_trade_caravan(
            sender_house_id=house_entity.id,
            recipient_house_id=recipient_house.id,
            cargo=trade_goods,
            proposed_terms=terms,
            starting_position=starting_position,
            caravan_name=f"{house_entity.name} Trade Mission"
        )
        
        caravan.created_turn = sim_context.current_turn
        
        # Plan route to recipient house
        # Clean and validate direction parameter
        preferred_direction = direction.strip().upper() if direction else None
        valid_directions = {'N', 'NE', 'SE', 'S', 'SW', 'NW'}
        if preferred_direction and preferred_direction not in valid_directions:
            preferred_direction = None  # Invalid direction, ignore
        
        route_success = caravan.plan_route_to_house(recipient_house, sim_context.hex_grid, preferred_direction)
        if not route_success:
            return f"Could not plan route to {recipient_name} - no accessible territory found"
        
        # Register caravan with entity manager
        sim_context.entity_manager._entities[caravan.id] = caravan
        
        # Track by type for easy lookup
        if 'caravan' not in sim_context.entity_manager._entities_by_type:
            sim_context.entity_manager._entities_by_type['caravan'] = []
        sim_context.entity_manager._entities_by_type['caravan'].append(caravan)
        
        # Immediately update renderer to show newly dispatched caravan
        try:
            positioned_entities = []
            generals = sim_context.entity_manager.get_entities_by_type('general') or []
            caravans = sim_context.entity_manager.get_entities_by_type('caravan') or []
            positioned_entities.extend(generals)
            positioned_entities.extend(caravans)
            sim_context.hex_grid.render(sim_context.houses, positioned_entities)
        except Exception:
            pass  # Don't fail caravan dispatch if render update fails
        
        # Log the trade mission
        goods_summary = str(trade_goods)
        
        # Estimate arrival: caravan moves 3 tiles/turn; calculate hex distance to recipient
        eta_turns = "unknown"
        try:
            from feudal_sim.components.position import PositionComponent
            caravan_pos = caravan.get_component(PositionComponent)
            if caravan_pos and caravan_pos.position and recipient_house:
                from feudal_sim.components.territory import TerritoryComponent
                r_terr = recipient_house.get_component(TerritoryComponent)
                if r_terr and r_terr.territory:
                    rq = sum(t.q for t in r_terr.territory) // len(r_terr.territory)
                    rr = sum(t.r for t in r_terr.territory) // len(r_terr.territory)
                    sq, sr = caravan_pos.position
                    dist = (abs(sq - rq) + abs(sr - rr) + abs((-sq - sr) - (-rq - rr))) // 2
                    import math as _math
                    eta_turns = _math.ceil(dist / 3)
        except Exception:
            pass

        eta_text = f"~{eta_turns} turn(s)" if isinstance(eta_turns, int) else "a few turns"
        return (f"Trade caravan dispatched to {recipient_name}! "
                f"Carrying: {goods_summary}. "
                f"Terms: '{terms}'. "
                f"Estimated arrival: {eta_text}.")
    
    # Add action description for dynamic prompts
    send_trade_caravan.action_description = "**Send Trade Caravan**: Dispatch goods to another house for negotiation (physical caravan travels across map)"
    
    return send_trade_caravan


def create_declare_war_tool(house_entity):
    """Declare war on another house."""
    @function_tool
    def declare_war(ctx: RunContextWrapper["SimulationContext"], target_house_name: str) -> str:
        """
        Formally declare war on another house. This signals hostile intent and changes how contact events are resolved.
        Use when you want open conflict rather than negotiation.
        """
        sim = getattr(ctx.context, 'simulation', None)
        if not sim or not hasattr(sim, 'war_registry'):
            return "War declaration unavailable."
        # Find target house id by name
        target = next((h for h in sim.houses if h.name == target_house_name), None)
        if not target:
            return f"No house named '{target_house_name}' found."
        if target.id == house_entity.id:
            return "You cannot declare war on yourself."
        success = sim.war_registry.declare_war(house_entity.id, target.id)
        if not success:
            return f"You are already at war with House {target_house_name}."
        msg = f"House {house_entity.name} has declared war on House {target_house_name}!"
        # Notify both parties
        from feudal_sim.components.ai import AIComponent as _AIC
        ai_self = house_entity.get_component(_AIC)
        ai_tgt = target.get_component(_AIC)
        if ai_self:
            ai_self.add_observation(f"You declared war on House {target_house_name}.", "Events")
            ai_self.record_journal_entry(f"War declared against House {target_house_name}")
        if ai_tgt:
            ai_tgt.add_observation(f"House {house_entity.name} has declared war on you!", "Events")
            ai_tgt.record_journal_entry(f"House {house_entity.name} declared war on us")
        print(f"⚔️  {msg}")
        return msg
    return declare_war


def create_sue_for_peace_tool(house_entity):
    """Offer peace to a house you are at war with."""
    @function_tool
    def sue_for_peace(ctx: RunContextWrapper["SimulationContext"], target_house_name: str) -> str:
        """
        Offer peace to a house you are currently at war with.
        If accepted (i.e., you call this), the war ends immediately. Ravens are the diplomatic channel — use this when you want to end a conflict.
        """
        sim = getattr(ctx.context, 'simulation', None)
        if not sim or not hasattr(sim, 'war_registry'):
            return "Peace negotiation unavailable."
        target = next((h for h in sim.houses if h.name == target_house_name), None)
        if not target:
            return f"No house named '{target_house_name}' found."
        success = sim.war_registry.sue_for_peace(house_entity.id, target.id)
        if not success:
            return f"You are not at war with House {target_house_name}."
        msg = f"Peace concluded between House {house_entity.name} and House {target_house_name}."
        from feudal_sim.components.ai import AIComponent as _AIC
        ai_self = house_entity.get_component(_AIC)
        ai_tgt = target.get_component(_AIC)
        if ai_self:
            ai_self.add_observation(f"You made peace with House {target_house_name}.", "Events")
            ai_self.record_journal_entry(f"Peace concluded with House {target_house_name}")
        if ai_tgt:
            ai_tgt.add_observation(f"House {house_entity.name} has offered peace — the war is over.", "Events")
            ai_tgt.record_journal_entry(f"War with House {house_entity.name} ended")
        print(f"🕊️  {msg}")
        return msg
    return sue_for_peace


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

    # assess_all_borders — scan all 6 directions in one call
    from feudal_sim.components.territory import TerritoryComponent as _TerritoryComponent
    territory_component_ab = house.get_component(_TerritoryComponent)

    @function_tool
    def assess_all_borders(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Assess all six border directions in a single call.
        Returns expansion opportunities, terrain, and cost for every direction.
        Use this instead of calling assess_border() six times.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not territory_component_ab:
            return "Border assessment unavailable — missing context or territory."
        hex_grid = sim_context.hex_grid
        DIRECTIONS = ['N', 'NE', 'SE', 'S', 'SW', 'NW']
        lines = []
        for direction in DIRECTIONS:
            analysis = territory_component_ab.calculate_direction_value(direction, hex_grid)
            if not analysis.get('has_opportunities'):
                lines.append(f"  {direction:2s} — no expansion opportunities")
            else:
                opps = analysis.get('opportunities', [])
                terrains = []
                for opp in opps[:3]:
                    t = opp.get('terrain_type', '')
                    if t and t not in terrains:
                        terrains.append(t)
                terrain_str = ', '.join(terrains)
                if analysis['total_opportunities'] > 3:
                    terrain_str += f" (+{analysis['total_opportunities'] - 3} more)"
                costs = analysis.get('expansion_cost_estimate', {})
                lines.append(
                    f"  {direction:2s} — {analysis['total_opportunities']} tiles "
                    f"({terrain_str}). Cost: {costs.get('material', '?')} material, "
                    f"{costs.get('gold', '?')} gold"
                )
        return "Border assessment (all directions):\n" + "\n".join(lines)
    assess_all_borders.action_description = "**Assess All Borders**: Survey all six directions at once — use this instead of calling assess_border() multiple times"
    tools.append(assess_all_borders)
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
        balance = _balance_line(res, ['food', 'gold'])
        return f"Feast held. Loyalty now {pop.loyalty}. {balance}"
    hold_feast.action_description = "**Hold Feast**: Spend food and gold to boost loyalty (cooldown applies)"
    tools.append(hold_feast)
    
    # Population management tools
    tools.append(create_manage_household_tool(house))

    # Resupply general tool (delayed delivery — arrives next turn)
    @function_tool
    def send_resupply(ctx: RunContextWrapper["SimulationContext"], general_name: str, gold: int = 20, food: int = 0) -> str:
        """
        Dispatch a resupply convoy to a deployed general. The convoy arrives next turn,
        restoring their supplies and morale. Costs gold (and optionally food) from your stores.

        Args:
            general_name: Name of the general to resupply
            gold: Gold to spend on supplies (each 10 gold = 20 supply points, max 100)
            food: Food to include in the convoy (each 10 food = 10 supply points)
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send resupply — no access to entity manager"
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not res:
            return "Cannot send resupply — missing resource management"
        costs = {}
        if gold > 0:
            costs['gold'] = gold
        if food > 0:
            costs['food'] = food
        if not costs:
            return "Must spend at least some gold or food to resupply"
        if not res.can_afford_action(costs):
            return f"Insufficient resources to send resupply (need {gold} gold, {food} food)"
        # Find general
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                      if getattr(g, 'house_id', None) == house.id and g.name == general_name]
        if not candidates:
            return f"No general named '{general_name}' found"
        general = candidates[0]
        # Calculate supply points: 10 gold = 20 points, 10 food = 10 points
        supply_points = min(100, (gold // 10) * 20 + (food // 10) * 10)
        if supply_points <= 0:
            return "Not enough resources to provide meaningful supplies (minimum 10 gold)"
        # Deduct resources and schedule delivery
        res.consume_for_action(costs, "Send Resupply")
        current_turn = getattr(sim_context, 'current_turn', 0)
        sim_context.simulation.deferred.schedule_at(
            current_turn + 1, 'resupply_general',
            {'general_id': general.id, 'general_name': general_name,
             'house_id': house.id, 'house_name': house.name,
             'supply_points': supply_points},
            phase='Events', owner_id=house.id
        )
        balance = _balance_line(res, ['gold', 'food'])
        return (f"Resupply convoy dispatched to {general_name} — "
                f"{supply_points} supply points will arrive next turn. "
                f"Cost: {gold} gold, {food} food. {balance}")
    send_resupply.action_description = "**Send Resupply**: Dispatch a supply convoy to a general (arrives next turn, costs gold/food)"
    tools.append(send_resupply)

    # Equip general tool — spend metal to raise equipment level
    @function_tool
    def equip_general(ctx: RunContextWrapper["SimulationContext"], general_name: str, metal: int) -> str:
        """
        Spend metal to equip a deployed general's forces with weapons and armour.
        Every 10 metal raises equipment level by 20 (max 100%).
        Unequipped soldiers fight at only 30% effectiveness; fully equipped at 100%.

        Args:
            general_name: Name of the general to equip
            metal: Metal to spend (minimum 10)
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot equip — no entity manager access"
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not res:
            return "Cannot equip — missing resource management"
        if metal < 10:
            return "Minimum 10 metal required to equip"
        costs = {'metal': metal}
        if not res.can_afford_action(costs):
            return f"Insufficient metal (need {metal}, have {res.resources.metal:.0f})"
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                      if getattr(g, 'house_id', None) == house.id and g.name == general_name]
        if not candidates:
            return f"No general named '{general_name}' found"
        general = candidates[0]
        grp: SubAgentGroup = general.get_component(SubAgentGroup)
        if not grp:
            return "Cannot equip — general missing group component"
        points_gained = (metal // 10) * 20
        old_equip = grp.equipment_level
        grp.equipment_level = min(100, grp.equipment_level + points_gained)
        actually_gained = grp.equipment_level - old_equip
        if actually_gained == 0:
            return f"{general_name} is already fully equipped (100%)"
        res.consume_for_action(costs, "Equip General")
        balance = _balance_line(res, ['metal'])
        return (f"Equipped {general_name}: equipment {old_equip}% → {grp.equipment_level}% "
                f"(+{actually_gained}%). Cost: {metal} metal. {balance}")
    equip_general.action_description = "**Equip General**: Spend metal to arm your forces — critical before combat"
    tools.append(equip_general)

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
        # Schedule disband for Events phase to avoid race conditions via deferred queue
        if hasattr(sim_context, 'simulation') and sim_context.simulation and hasattr(sim_context.simulation, 'deferred'):
            current_turn = getattr(sim_context, 'current_turn', 0)
            sim_context.simulation.deferred.schedule_at(
                current_turn,
                'disband_general',
                {'general_id': g.id, 'general_name': general_name},
                phase='Events',
                owner_id=house.id,
            )
        # Add observation to house AI (scheduled)
        try:
            from feudal_sim.components.ai import AIComponent
            ai: AIComponent = house.get_component(AIComponent)
            if ai:
                ai.add_observation(f"General {general_name} disband scheduled; will complete this week", phase="Actions")
        except Exception:
            pass
        return f"Disband scheduled for '{general_name}'."
    disband_general.action_description = "**Disband General**: Recall a general and return assigned population"
    tools.append(disband_general)
    
    # City management tools
    tools.append(create_view_cities_tool(house))

    # Shared rookery tools (list only; house already has a specialized send tool)
    tools.extend(create_rookery_toolset(house, include_send=False))
    
    # Inbox / message history tool
    from feudal_sim.components.rookery import RookeryComponent as _RookeryComponent

    @function_tool
    def check_inbox(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Read received raven messages from other houses. Shows last 5 messages with sender and turn received.
        """
        rookery: _RookeryComponent = house.get_component(_RookeryComponent)
        if not rookery or not rookery.message_history:
            return "No messages in your raven history."
        recent = rookery.message_history[-5:]
        lines = []
        for msg in reversed(recent):
            preview = msg.message[:100] if hasattr(msg, 'message') else str(msg)[:100]
            turn = getattr(msg, 'turn_received', '?')
            sender = getattr(msg, 'sender_name', 'Unknown')
            lines.append(f"From {sender} (Turn {turn}): '{preview}'")
        return "\n".join(lines)
    check_inbox.action_description = "**Check Inbox**: Read received raven messages from other houses"
    tools.append(check_inbox)

    # General status query tool
    @function_tool
    def query_general_status(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Get a full status report of all your deployed generals including position and readiness.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        mine = sim_context.entity_manager.get_entities_by_house_and_type(house.id, 'general')
        if not mine:
            return "No generals deployed"
        lines = []
        for g in mine:
            pos_comp = g.get_component(PositionComponent)
            grp = g.get_component(SubAgentGroup)
            position = pos_comp.position if pos_comp else "unknown"
            morale = grp.morale if grp else "?"
            supplies = grp.supplies if grp else "?"
            mission_status = grp.mission_status if grp else "unknown"
            mission_type = grp.mission_parameters.mission_type if grp and grp.mission_parameters else "unknown"
            orders = grp.mission_parameters.orders if grp and grp.mission_parameters else "none"
            lines.append(
                f"{g.name} | Position: {position} | Morale: {morale}% | Supplies: {supplies}% "
                f"| Status: {mission_status} | Mission: {mission_type} | Orders: {orders}"
            )
        return "\n".join(lines)
    query_general_status.action_description = "**Query Generals**: Get a full status report of all your deployed generals including position and readiness"
    tools.append(query_general_status)

    # Objective management tools
    @function_tool
    def set_objective(objective: str) -> str:
        """
        Set a new strategic objective. Objectives appear each turn to guide your decisions (max 5).

        Args:
            objective: Description of the objective to add
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot set objective - AI component unavailable"
        if len(ai_comp.current_objectives) >= 5:
            return f"Objective list full (max 5). Remove an objective first. Current: {ai_comp.current_objectives}"
        ai_comp.current_objectives.append(objective)
        return f"Objective added: '{objective}'. Total objectives: {len(ai_comp.current_objectives)}"
    set_objective.action_description = "**Set Objective**: Add a strategic goal that persists across turns (max 5)"
    tools.append(set_objective)

    @function_tool
    def remove_objective(objective: str) -> str:
        """
        Remove a strategic objective by name or partial match.

        Args:
            objective: Objective text or substring to remove
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot remove objective - AI component unavailable"
        before = list(ai_comp.current_objectives)
        ai_comp.current_objectives = [o for o in ai_comp.current_objectives if objective.lower() not in o.lower()]
        removed = [o for o in before if o not in ai_comp.current_objectives]
        if removed:
            return f"Removed: {removed}. Remaining: {ai_comp.current_objectives}"
        return f"No matching objective found for '{objective}'. Current: {ai_comp.current_objectives}"
    remove_objective.action_description = "**Remove Objective**: Remove a strategic goal by name or partial match"
    tools.append(remove_objective)

    @function_tool
    def list_objectives() -> str:
        """List all current strategic objectives."""
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot list objectives - AI component unavailable"
        if not ai_comp.current_objectives:
            return "No objectives currently set."
        return "Current objectives:\n" + "\n".join(f"  - {o}" for o in ai_comp.current_objectives)
    list_objectives.action_description = "**List Objectives**: View all current strategic objectives"
    tools.append(list_objectives)

    # Universal tools
    tools.append(end_turn)

    # Trade caravan tools
    tools.append(create_send_trade_caravan_tool(house))

    # War diplomacy tools
    tools.append(create_declare_war_tool(house))
    tools.append(create_sue_for_peace_tool(house))

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
        
        # Check if general has pending outpost construction requiring them to stay
        # Generals can move freely — outpost construction completes automatically
        # without requiring the general to remain on-site.
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

    @function_tool
    def move_along(ctx: RunContextWrapper["SimulationContext"], steps: List[str]) -> str:
        """
        Execute a planned multi-step path in a single action.
        After observing the area, provide a list of directions to move through
        sequentially. Each step costs one movement point. Stops automatically
        if blocked by terrain or movement points run out — reports where you stopped.

        Prefer this over multiple move() calls whenever you know your intended path.

        Args:
            steps: Ordered list of directions, e.g. ["NE", "NE"] or ["N", "NW", "W"].
                   Maximum length is your remaining movement points.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Movement failed — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Movement failed — position unknown"

        valid_dirs = {"N", "NE", "SE", "S", "SW", "NW"}
        if not steps:
            return "No steps provided. Pass a list like [\"NE\", \"N\"]."

        completed = []
        stopped_reason = None

        for raw_dir in steps:
            dir_upper = str(raw_dir).upper().strip()
            if dir_upper not in valid_dirs:
                stopped_reason = f"invalid direction '{raw_dir}'"
                break

            neighbors = sim_context.hex_grid.get_neighbors(pos.position[0], pos.position[1])
            target = None
            for neigh, dirn in neighbors:
                if dirn == dir_upper and neigh is not None:
                    target = (neigh.q, neigh.r)
                    break

            if not target:
                stopped_reason = f"no tile in direction {dir_upper}"
                break

            result = pos.move_to(
                target_position=target,
                hex_grid=sim_context.hex_grid,
                current_turn=getattr(sim_context, 'current_turn', None),
                validate_movement=True,
            )

            if not result.get('success'):
                stopped_reason = result.get('message', f"blocked moving {dir_upper}")
                break

            terrain_name = ''
            try:
                tile = sim_context.hex_grid.get_tile(target[0], target[1])
                if tile:
                    raw = getattr(getattr(tile, 'terrain_type', None), 'name', '')
                    mapping = {
                        'GRASSLAND': 'plains', 'STEPPE': 'plains',
                        'TEMPERATE_FOREST': 'forest', 'BOREAL_FOREST': 'forest',
                        'HILL': 'hills', 'MOUNTAIN': 'mountains',
                        'TUNDRA': 'tundra', 'DESERT': 'desert',
                    }
                    terrain_name = mapping.get(raw, raw.lower())
                    owner = getattr(tile, 'owner', None)
                    owner_label = 'unowned' if not owner else (
                        'ours' if getattr(owner, 'id', None) == getattr(general_entity, 'house_id', None)
                        else getattr(owner, 'name', 'foreign')
                    )
                    completed.append(f"{dir_upper}({terrain_name},{owner_label})")
            except Exception:
                completed.append(dir_upper)

            remaining = getattr(pos, 'remaining_movement', '?')
            if isinstance(remaining, (int, float)) and remaining <= 0:
                if steps.index(raw_dir) < len(steps) - 1:
                    stopped_reason = "movement points exhausted"
                break

        path_str = " → ".join(completed) if completed else "no movement"
        q, r = pos.position
        remaining_mp = getattr(pos, 'remaining_movement', '?')

        if stopped_reason:
            return (f"Moved {len(completed)}/{len(steps)} step(s): {path_str}. "
                    f"Stopped: {stopped_reason}. "
                    f"Position ({q},{r}), {remaining_mp} movement point(s) remaining.")
        return (f"Moved {len(completed)}/{len(steps)} step(s): {path_str}. "
                f"Position ({q},{r}), {remaining_mp} movement point(s) remaining.")
    move_along.action_description = "**Move Along Path**: Execute a planned sequence of steps in one action — prefer this over multiple move() calls"
    tools.append(move_along)
    
    # One-tile observation for simplicity
    from feudal_sim.components.terrain_observation import TerrainObservation
    
    @function_tool
    def observe_area(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Observe tiles within 2 tile radius around you and summarize threats, units, and opportunities.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Observation failed - map access not available"
        obs: TerrainObservation = general_entity.get_component(TerrainObservation)
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not obs or not pos or not pos.position:
            return "Observation failed - missing components or position"
        current_turn = getattr(sim_context, 'current_turn', 0)
        obs.observation_range = 2
        obs.observe_current_area(sim_context.hex_grid, pos.position, current_turn)
        # Fetch localized intelligence
        threats = obs.get_threats_in_area(pos.position, search_range=2)
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

        # Natural language landscape summary within 2 tiles
        hex_grid = sim_context.hex_grid
        from feudal_sim.map.city_extensions import has_city, format_city_display
        q0, r0 = pos.position

        # Ring 1: center + immediate neighbors (directional detail)
        tiles_in_radius = []
        center_tile = hex_grid.get_tile(q0, r0)
        if center_tile:
            tiles_in_radius.append((center_tile, "CENTER"))
        for neigh, dirn in hex_grid.get_neighbors(q0, r0):
            if neigh:
                tiles_in_radius.append((neigh, dirn))

        # Ring 2: tiles at exactly distance 2 (aggregate only)
        seen = {(q0, r0)} | {(t.q, t.r) for t, _ in tiles_in_radius if t}
        ring2_tiles = []
        for neigh1, _ in hex_grid.get_neighbors(q0, r0):
            if not neigh1:
                continue
            for neigh2, _ in hex_grid.get_neighbors(neigh1.q, neigh1.r):
                if neigh2 and (neigh2.q, neigh2.r) not in seen:
                    ring2_tiles.append(neigh2)
                    seen.add((neigh2.q, neigh2.r))
        
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
        
        from feudal_sim.map.types import HexTileType as _HTT
        _IMPASSABLE = {_HTT.OCEAN, _HTT.LAKE, _HTT.RIVER, _HTT.ICE_CAP}

        terrain_counts_local: Dict[str, int] = {}
        ownership = {"ours": 0, "unowned": 0, "other": 0}
        owner_dirs: Dict[str, list] = {"ours": [], "unowned": []}
        other_owner_dirs: Dict[str, list] = {}
        city_highlights: list = []
        for tile, dirn in tiles_in_radius:
            terr_name = friendly_terrain(getattr(tile, 'terrain_type', None))
            terrain_counts_local[terr_name] = terrain_counts_local.get(terr_name, 0) + 1
            # Skip impassable tiles — water/ice is not claimable land
            if getattr(tile, 'terrain_type', None) in _IMPASSABLE:
                continue
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
        
        # Ring 2 aggregate: ownership and settlements
        ring2_unowned = 0
        ring2_enemy: Dict[str, int] = {}
        ring2_cities: list = []
        for tile in ring2_tiles:
            if getattr(tile, 'terrain_type', None) in _IMPASSABLE:
                continue
            r2_owner = getattr(tile, 'owner', None)
            if not r2_owner:
                ring2_unowned += 1
            elif not (hasattr(r2_owner, 'id') and r2_owner.id == getattr(general_entity, 'house_id', None)):
                name = getattr(r2_owner, 'name', str(r2_owner))
                ring2_enemy[name] = ring2_enemy.get(name, 0) + 1
            if has_city(tile):
                city_text_r2 = format_city_display(tile)
                if city_text_r2:
                    ring2_cities.append(city_text_r2)

        units_text = ""
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            nearby = sim_context.entity_manager.get_positioned_entities_near(pos.position, 2)
            friendly: list[str] = []
            enemy: list[str] = []
            for ent, dist in nearby:
                if ent.id == general_entity.id:
                    continue
                ent_name = getattr(ent, 'name', 'unknown')
                ent_pos = ent.get_component(PositionComponent)
                dist_word = "adjacent" if dist <= 1 else f"{dist} tiles away"
                # Determine rough direction for close units
                dir_label = dist_word
                if dist == 1 and ent_pos and ent_pos.position:
                    for nn, nd in hex_grid.get_neighbors(q0, r0):
                        if nn and (nn.q, nn.r) == ent_pos.position:
                            dir_label = dir_prose.get(nd, nd)
                            break
                house_id = getattr(ent, 'house_id', None) or getattr(ent, 'sender_house_id', None)
                if house_id == getattr(general_entity, 'house_id', None):
                    friendly.append(f"{ent_name} ({dir_label})")
                else:
                    enemy.append(f"{ent_name} ({dir_label})")
            if friendly:
                units_text += f" | Friendly: {', '.join(friendly)}"
            if enemy:
                units_text += f" | Enemy: {', '.join(enemy)}"

        intro = f"Immediate area ({mix_text})."
        own_text = f" Unowned tiles (1 tile): {ownership['unowned']}."
        threat_text = ""
        if threats:
            breakdown = ", ".join(f"{cnt} {lvl}" for lvl, cnt in threat_counts.items())
            threat_text = f" Threats: {breakdown}."

        city_text = ""
        if city_highlights:
            city_text = " | Settlements (1 tile): " + "; ".join(city_highlights[:3])

        dirs_text = f" | Borders: {claims_text}"

        # Extended range summary
        ext_parts = []
        if ring2_unowned:
            ext_parts.append(f"{ring2_unowned} unowned")
        for ename, cnt in ring2_enemy.items():
            ext_parts.append(f"{cnt} {ename} tiles")
        if ring2_cities:
            ext_parts.append("settlements: " + ", ".join(ring2_cities[:2]))
        ext_text = f" | Extended (2 tiles): {', '.join(ext_parts)}" if ext_parts else ""

        # Nearest friendly settlement — critical for outpost planning
        settlement_proximity_text = ""
        try:
            if hasattr(general_entity, 'house_id') and sim_context.entity_manager:
                ph = sim_context.entity_manager.get_entity(general_entity.house_id)
                from feudal_sim.components.city import CityComponent as _CC
                from feudal_sim.core.config import config as _cfg2
                _min_sp = int(_cfg2.get('simulation.settlements.min_spacing_tiles', 3))
                ph_cc = ph.get_component(_CC) if ph else None
                if ph_cc:
                    best_d, best_n = None, None
                    for _city in ph_cc.get_all_cities().values():
                        cq2, cr2 = _city.position
                        d2 = (abs(q0 - cq2) + abs(r0 - cr2) + abs((-q0 - r0) - (-cq2 - cr2))) // 2
                        if best_d is None or d2 < best_d:
                            best_d, best_n = d2, getattr(_city, 'name', 'settlement')
                    if best_d is not None:
                        if best_d < _min_sp:
                            settlement_proximity_text = (
                                f" | Nearest settlement: {best_n} ({best_d} tile(s) away — "
                                f"need {_min_sp - best_d} more to build here)"
                            )
                        else:
                            settlement_proximity_text = (
                                f" | Nearest settlement: {best_n} ({best_d} tile(s) away — "
                                f"outpost spacing OK here)"
                            )
        except Exception:
            pass

        # Distance and direction to nearest friendly territory
        home_text = ""
        try:
            if hasattr(general_entity, 'house_id') and sim_context.entity_manager:
                ph = sim_context.entity_manager.get_entity(general_entity.house_id)
                if ph:
                    from feudal_sim.components.territory import TerritoryComponent as _TComp3
                    ph_terr = ph.get_component(_TComp3)
                    if ph_terr and ph_terr.territory:
                        best_d, best_dir = None, None
                        dir_vecs = {'N':(0,-1),'NE':(1,-1),'SE':(1,0),'S':(0,1),'SW':(-1,1),'NW':(-1,0)}
                        for t in list(ph_terr.territory)[:15]:
                            d = (abs(q0-t.q)+abs(r0-t.r)+abs((-q0-r0)-(-t.q-t.r)))//2
                            if best_d is None or d < best_d:
                                best_d = d
                                dq, dr = t.q-q0, t.r-r0
                                best_dir = min(dir_vecs, key=lambda k: abs(dir_vecs[k][0]-dq)+abs(dir_vecs[k][1]-dr))
                        if best_d == 0:
                            home_text = " | On friendly territory"
                        elif best_d is not None:
                            home_text = f" | Friendly territory: {best_d} tile(s) {best_dir.lower()}"
        except Exception:
            pass

        nl_report = intro + own_text + threat_text + dirs_text + city_text + ext_text + units_text + settlement_proximity_text + home_text

        return nl_report
    observe_area.action_description = "**Observe (2 tiles)**: Scan immediate surroundings and extended area"
    tools.append(observe_area)

    # Territory is claimed only through settlements (build_outpost).
    # The raw claim_territory tool has been removed — generals must establish
    # structures to bring land under their house's control.
    from feudal_sim.components.territory import TerritoryComponent

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

        # Refuse if a pending outpost order already exists at this position for this general
        if house_territory and hasattr(house_territory, 'pending_outposts'):
            for existing in house_territory.pending_outposts:
                if existing.status == "pending" and (existing.q, existing.r) == (q0, r0):
                    turns_left = existing.turn_resolves - (getattr(sim_context, 'current_turn', 0))
                    return (f"Outpost already under construction here — completes in "
                            f"{max(0, turns_left)} turn(s). Stay on this tile.")

        center_tile = sim_context.hex_grid.get_tile(q0, r0)
        if not center_tile:
            return "Outpost construction failed - tile not found"
        # Allow building on unowned land OR already-owned house tiles
        owner = getattr(center_tile, 'owner', None)
        if owner is not None and hasattr(owner, 'id') and owner.id != parent_house.id:
            return "Outpost construction failed - this tile is controlled by another house"
        # Reject water/ice
        from feudal_sim.map.types import HexTileType as _HTT2
        if getattr(center_tile, 'terrain_type', None) in {_HTT2.OCEAN, _HTT2.LAKE, _HTT2.RIVER, _HTT2.ICE_CAP}:
            return "Outpost construction failed - cannot build on water or ice"
        # Cannot build over an existing settlement (city/outpost)
        try:
            from feudal_sim.map.city_extensions import has_city as _tile_has_city
            if _tile_has_city(center_tile):
                return "Outpost construction failed - a settlement already exists on this tile"
        except Exception:
            pass
        
        # Spacing constraint: enforce minimum distance from this house's settlements (cities/outposts)
        try:
            from feudal_sim.components.city import CityComponent
            from feudal_sim.core.config import config as _cfg
            min_spacing = int(_cfg.get('simulation.settlements.min_spacing_tiles', 3))
            nearest_dist = None
            nearest_name = None
            # Check against this house's existing settlements
            cc: CityComponent = parent_house.get_component(CityComponent)
            if cc:
                for city in cc.get_all_cities().values():
                    cq, cr = city.position
                    s1 = -q0 - r0
                    s2 = -cq - cr
                    dist = (abs(q0 - cq) + abs(r0 - cr) + abs(s1 - s2)) // 2
                    if nearest_dist is None or dist < nearest_dist:
                        nearest_dist = dist
                        nearest_name = getattr(city, 'name', 'settlement')
            # Check against this house's pending outpost orders
            if house_territory and hasattr(house_territory, 'pending_outposts'):
                for pending in house_territory.pending_outposts:
                    cq, cr = pending.q, pending.r
                    s1 = -q0 - r0
                    s2 = -cq - cr
                    dist = (abs(q0 - cq) + abs(r0 - cr) + abs(s1 - s2)) // 2
                    if nearest_dist is None or dist < nearest_dist:
                        nearest_dist = dist
                        nearest_name = 'outpost site'
            if nearest_dist is not None and nearest_dist < min_spacing:
                still_needed = min_spacing - nearest_dist
                return (
                    f"Outpost construction failed — '{nearest_name}' is only {nearest_dist} tile(s) away "
                    f"(minimum {min_spacing}). Advance at least {still_needed} more tile(s) away from "
                    f"'{nearest_name}' before building."
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
            if terr in {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}:
                continue  # water tiles and ice caps cannot be claimed
            to_claim.append(neigh)
        
        # Consume resources, build, and claim
        if costs:
            res_comp.consume_for_action(costs, 'Build Outpost (Order)')

        # Mark tile as pending construction for the renderer
        center_tile._pending_outpost = True

        # Create delayed outpost construction order (resolves next week).
        # Use simulation.global_turn (never resets) so season rollover doesn't strand orders.
        from feudal_sim.components.territory import TerritoryComponent as _Terr
        sim_obj = getattr(sim_context, 'simulation', None)
        current_turn = getattr(sim_obj, 'global_turn', None) or getattr(sim_context, 'current_turn', 0)
        house_territory: _Terr = parent_house.get_component(_Terr)
        delay = int(config.get('simulation.settlements.outpost_delay_turns', 1))
        required_general_id = getattr(general_entity, 'id', '')
        required_general_name = getattr(general_entity, 'name', 'General')
        house_territory.create_outpost_order((q0, r0), current_turn, delay_turns=delay, resource_cost=costs, required_general_id=required_general_id, required_general_name=required_general_name)
        
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
        
        balance = _balance_line(res_comp, ['material', 'gold'])
        return f"Outpost construction ordered; remain on this tile until completion next week. {balance}"
    build_outpost.action_description = "**Build Outpost**: Establish a small camp on controlled land to claim adjacent unowned tiles (costs resources; the ordering general must remain on the tile until completion)"
    tools.append(build_outpost)
    
    # Find valid outpost site tool
    @function_tool
    def find_outpost_site(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Scan all six directions simultaneously to find valid outpost locations.
        Returns a ranked list of the best options and explains why each blocked
        direction is blocked. Call this ONCE before deciding where to move —
        no need to call it six times.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Cannot scan — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Cannot scan — position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Cannot scan — no parent house"
        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Cannot scan — parent house not found"

        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.core.config import config as _cfg
        from feudal_sim.map.types import HexTileType
        from feudal_sim.map.city_extensions import has_city as _has_city

        IMPASSABLE = {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}
        min_spacing = int(_cfg.get('simulation.settlements.min_spacing_tiles', 3))
        cc = parent_house.get_component(CityComponent)
        terr = parent_house.get_component(TerritoryComponent)

        def _settlement_dist(q, r):
            best = None
            if cc:
                for city in cc.get_all_cities().values():
                    cq, cr = city.position
                    d = (abs(q - cq) + abs(r - cr) + abs((-q - r) - (-cq - cr))) // 2
                    if best is None or d < best:
                        best = d
            if terr and hasattr(terr, 'pending_outposts'):
                for p in terr.pending_outposts:
                    d = (abs(q - p.q) + abs(r - p.r) + abs((-q - r) - (-p.q - p.r))) // 2
                    if best is None or d < best:
                        best = d
            return best

        hex_grid = sim_context.hex_grid
        q, r = pos.position
        ALL_DIRS = ['N', 'NE', 'SE', 'S', 'SW', 'NW']
        valid_options = []   # (steps, direction, terrain_name)
        dir_status = {}      # direction -> brief status string

        for dir_upper in ALL_DIRS:
            current = (q, r)
            found = False
            for steps in range(1, 13):
                neighbor = hex_grid.get_neighbor(current[0], current[1], dir_upper)
                if not neighbor:
                    dir_status[dir_upper] = f"edge of map at {steps} tile(s)"
                    break
                current = (neighbor.q, neighbor.r)
                terrain = getattr(neighbor, 'terrain_type', None)
                if terrain in IMPASSABLE:
                    dir_status[dir_upper] = f"water/ice at {steps} tile(s)"
                    break
                owner = getattr(neighbor, 'owner', None)
                # Can build on unowned OR own land; block only enemy-owned
                if owner is not None and getattr(owner, 'id', None) != general_entity.house_id:
                    dir_status[dir_upper] = f"blocked by {getattr(owner, 'name', 'enemy')} territory"
                    break
                if _has_city(neighbor):
                    continue
                sdist = _settlement_dist(current[0], current[1])
                if sdist is not None and sdist < min_spacing:
                    still_needed = min_spacing - sdist
                    if steps == 12:
                        dir_status[dir_upper] = f"all owned tiles too close to existing settlement (need {still_needed} more)"
                    continue
                terrain_name = terrain.name.lower().replace('_', ' ') if terrain else 'land'
                valid_options.append((steps, dir_upper, terrain_name))
                dir_status[dir_upper] = f"✓ valid site at {steps} tile(s) ({terrain_name})"
                found = True
                break
            if not found and dir_upper not in dir_status:
                dir_status[dir_upper] = "no owned territory in range"

        if not valid_options:
            status_lines = "\n".join(f"  {d}: {dir_status.get(d,'?')}" for d in ALL_DIRS)
            return (
                "No valid outpost site found in any direction.\n"
                f"{status_lines}\n"
                "You may be on a coastline or at the edge of your territory. "
                "Consider moving back toward the interior of your territory."
            )

        valid_options.sort()
        best_steps, best_dir, best_terrain = valid_options[0]
        lines = [f"Best site: {best_steps} tile(s) {best_dir} ({best_terrain}) — move there then build."]
        if len(valid_options) > 1:
            alts = ", ".join(f"{s} tile(s) {d}" for s, d, _ in valid_options[1:3])
            lines.append(f"Alternatives: {alts}.")
        lines.append("All directions:")
        for d in ALL_DIRS:
            lines.append(f"  {d}: {dir_status.get(d, '?')}")
        return "\n".join(lines)
    find_outpost_site.action_description = "**Find Outpost Site**: Scan all directions at once — call once to get ranked valid build locations"
    tools.append(find_outpost_site)

    # Intercept caravan tool
    @function_tool
    def intercept_caravan(ctx: RunContextWrapper["SimulationContext"], direction: str, action: str) -> str:
        """
        Intercept an enemy trade caravan in the given direction.

        Actions:
          raid          — steal 40% of cargo; caravan continues damaged
          seize         — take all cargo and destroy the caravan entirely
          demand_tribute — take 15% as a toll; caravan continues
          let_pass      — stand aside and allow the caravan to pass

        Args:
            direction: Direction where the caravan was spotted (north, northeast, etc.)
            action: One of: raid, seize, demand_tribute, let_pass
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager or not sim_context.hex_grid:
            return "Cannot intercept — no simulation access"

        action = action.lower().strip()
        valid_actions = ('raid', 'seize', 'demand_tribute', 'let_pass')
        if action not in valid_actions:
            return f"Invalid action '{action}'. Choose from: {', '.join(valid_actions)}"

        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Cannot intercept — position unknown"

        gen_house = getattr(general_entity, 'house_id', None)
        if not gen_house:
            return "Cannot intercept — no parent house"

        # Find the caravan: check current tile and all adjacent tiles
        from feudal_sim.components.cargo import CargoComponent
        em = sim_context.entity_manager
        caravans = em.get_entities_by_type('caravan') or []
        gq, gr = pos.position

        target_caravan = None
        for caravan in caravans:
            car_house = getattr(caravan, 'sender_house_id', None)
            if not car_house or car_house == gen_house:
                continue
            cpos = caravan.get_component(PositionComponent)
            if not cpos or not cpos.position:
                continue
            cq, cr = cpos.position
            dist = (abs(gq - cq) + abs(gr - cr) + abs((-gq - gr) - (-cq - cr))) // 2
            if dist <= 1:
                target_caravan = caravan
                break

        if not target_caravan:
            return f"No enemy caravan found nearby to intercept"

        if action == 'let_pass':
            return f"You allow {target_caravan.name} to pass without incident."

        cargo_comp = target_caravan.get_component(CargoComponent)
        if not cargo_comp:
            return "Caravan has no cargo to intercept"

        cargo = cargo_comp.cargo
        total_value = cargo.food + cargo.material + cargo.metal + cargo.gold
        if total_value <= 0:
            return f"Caravan {target_caravan.name} is empty — nothing to take."

        # Determine what fraction to take
        if action == 'seize':
            fraction = 1.0
        elif action == 'raid':
            fraction = 0.40
        else:  # demand_tribute
            fraction = 0.15

        # Transfer goods to general's parent house
        from feudal_sim.components.resource import ResourceComponent
        parent_house = em.get_entity(gen_house)
        house_res = parent_house.get_component(ResourceComponent) if parent_house else None

        taken_parts = []
        for resource in ('food', 'material', 'metal', 'gold'):
            available = getattr(cargo, resource, 0)
            if available <= 0:
                continue
            amount = available * fraction
            setattr(cargo, resource, available - amount)
            if house_res:
                house_res.resources.add(resource, amount)
            taken_parts.append(f"{amount:.0f} {resource}")

        taken_str = ", ".join(taken_parts) if taken_parts else "nothing"

        # Seize: destroy the caravan
        if action == 'seize':
            try:
                em.destroy_entity(target_caravan.id)
            except Exception:
                pass

        # Notify both lords via rookery ravens
        gen_name = general_entity.name
        car_owner_id = getattr(target_caravan, 'sender_house_id', None)
        car_owner = em.get_entity(car_owner_id) if car_owner_id else None
        car_owner_name = car_owner.name if car_owner else "unknown"

        from feudal_sim.components.rookery import RookeryComponent
        from feudal_sim.components.ai import AIComponent

        # Alert the caravan owner's lord
        if car_owner:
            owner_ai: AIComponent = car_owner.get_component(AIComponent)
            if owner_ai:
                action_word = {"raid": "raided", "seize": "seized", "demand_tribute": "levied tribute on"}[action]
                owner_ai.add_observation(
                    f"Your {target_caravan.name} was {action_word} by {gen_name} of House "
                    f"{getattr(parent_house, 'name', gen_house)}. Taken: {taken_str}.",
                    phase="Events"
                )

        # Report to own lord
        gen_rookery = general_entity.get_component(RookeryComponent)
        if gen_rookery and gen_house in gen_rookery.get_known_recipients_list():
            action_word = {"raid": "raided", "seize": "seized", "demand_tribute": "levied tribute on"}[action]
            gen_rookery.send_raven(
                gen_house,
                f"Field report: {action_word} {target_caravan.name} from House {car_owner_name}. "
                f"Taken: {taken_str}."
            )

        action_phrase = {
            'raid':           f"Raid successful — took {taken_str}. Caravan continues.",
            'seize':          f"Caravan seized — took {taken_str}. {target_caravan.name} destroyed.",
            'demand_tribute': f"Tribute collected — took {taken_str}. Caravan allowed to pass.",
        }
        return action_phrase[action]
    intercept_caravan.action_description = "**Intercept Caravan**: Raid, seize, or demand tribute from a nearby enemy caravan"
    tools.append(intercept_caravan)

    # Besiege tool — assault an adjacent enemy settlement
    @function_tool
    def besiege(ctx: RunContextWrapper["SimulationContext"], direction: str) -> str:
        """
        Launch an assault on an enemy settlement (outpost or capital) in the given direction.

        On SUCCESS: the settlement is destroyed, tiles revert to unowned, and your house
        loots a share of the enemy's resources. Massive strategic gain.
        On FAILURE: your forces take heavy casualties and must withdraw.

        Requires: at least 20 soldiers, adjacent to enemy settlement, enemy tile within 1 tile.

        Args:
            direction: Direction of the target settlement (N, NE, SE, S, SW, NW)
        """
        import random as _random
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not sim_context.entity_manager:
            return "Siege failed — no map access"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Siege failed — position unknown"
        from feudal_sim.components.subagent_group import SubAgentGroup
        grp = general_entity.get_component(SubAgentGroup)
        if not grp or grp.assigned_population.soldiers < 20:
            return "Siege requires at least 20 soldiers"

        valid_dirs = {'N', 'NE', 'SE', 'S', 'SW', 'NW'}
        dir_upper = direction.upper().strip()
        if dir_upper not in valid_dirs:
            return f"Invalid direction '{direction}'"

        hex_grid = sim_context.hex_grid
        gq, gr = pos.position
        target_tile = hex_grid.get_neighbor(gq, gr, dir_upper)
        if not target_tile:
            return f"No tile in direction {direction}"

        # Verify there's an enemy settlement there
        from feudal_sim.map.city_extensions import get_city_info, CityType
        city_info, dev_level, _ = get_city_info(target_tile)
        if city_info == CityType.NONE:
            return f"No settlement found to the {direction}. Use observe_area first to confirm target."

        tile_owner = getattr(target_tile, 'owner', None)
        if not tile_owner or getattr(tile_owner, 'id', None) == getattr(general_entity, 'house_id', None):
            return "Cannot besiege your own settlement."

        enemy_house_id = getattr(tile_owner, 'id', None)
        enemy_house_name = getattr(tile_owner, 'name', 'enemy')
        settlement_name = getattr(target_tile, '_city_name', f"{enemy_house_name} settlement")

        # Combat resolution
        equip_mult = 0.30 + 0.70 * (grp.equipment_level / 100.0)
        morale_mult = grp.morale / 100.0
        attacker_power = grp.assigned_population.soldiers * equip_mult * morale_mult

        # Defence: base 20 + 15 per development level; capitals are much harder
        base_defence = 20 + dev_level * 15
        if city_info == CityType.CAPITAL:
            base_defence *= 3
        defender_power = base_defence * _random.uniform(0.8, 1.2)

        success = attacker_power >= defender_power * _random.uniform(0.7, 1.3)

        # --- Outcome ---
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.ai import AIComponent
        from feudal_sim.components.rookery import RookeryComponent

        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        enemy_house  = sim_context.entity_manager.get_entity(enemy_house_id) if enemy_house_id else None

        if success:
            # Loot: steal 30-50 % of enemy's food, material, gold
            loot_parts = []
            if enemy_house:
                enemy_res = enemy_house.get_component(ResourceComponent)
                our_res   = parent_house.get_component(ResourceComponent) if parent_house else None
                if enemy_res and our_res:
                    loot_pct = _random.uniform(0.30, 0.50)
                    for res in ('food', 'material', 'metal', 'gold'):
                        available = getattr(enemy_res.resources, res, 0)
                        if available > 5:
                            amount = available * loot_pct
                            enemy_res.resources.consume(res, amount)
                            our_res.resources.add(res, amount)
                            loot_parts.append(f"+{amount:.0f} {res}")

            # Destroy the settlement: remove city encoding, revert tile
            try:
                if enemy_house:
                    city_comp = enemy_house.get_component(CityComponent)
                    if city_comp:
                        for cname, city in list(city_comp.get_all_cities().items()):
                            if city.position == (target_tile.q, target_tile.r):
                                # Use the public remove path if available, else direct
                                try:
                                    city_comp.remove_city(cname)
                                except Exception:
                                    try: city_comp._cities.pop(cname, None)
                                    except Exception: pass
                                break
                # Clear city encoding (restore population_capacity to base)
                if target_tile.population_capacity > 1000:
                    from feudal_sim.map.city_extensions import get_base_population_capacity
                    target_tile.population_capacity = get_base_population_capacity(target_tile)
                if hasattr(target_tile, '_city_name'):
                    del target_tile._city_name
                # Revert tile to unowned
                enemy_terr = enemy_house.get_component(TerritoryComponent) if enemy_house else None
                if enemy_terr:
                    enemy_terr.remove_territory([target_tile], hex_grid)
            except Exception as _e:
                import logging as _lg
                _lg.getLogger('feudal_sim').warning(f"⚠️  Siege settlement removal: {_e}")

            # Attacker takes light casualties (victory)
            casualty_pct = _random.uniform(0.05, 0.15)
            casualties = int(grp.assigned_population.soldiers * casualty_pct)
            grp.assigned_population.soldiers = max(1, grp.assigned_population.soldiers - casualties)
            grp.adjust_morale(10)
            grp.experience += 5

            loot_str = ", ".join(loot_parts) if loot_parts else "minimal loot"
            result_msg = (f"SIEGE SUCCESSFUL: {settlement_name} has fallen! "
                          f"Loot: {loot_str}. Our casualties: {casualties}. "
                          f"The settlement is destroyed and its tiles freed.")
        else:
            # Repulsed — heavy casualties
            casualty_pct = _random.uniform(0.20, 0.40)
            casualties = int(grp.assigned_population.soldiers * casualty_pct)
            grp.assigned_population.soldiers = max(1, grp.assigned_population.soldiers - casualties)
            grp.adjust_morale(-20)
            result_msg = (f"SIEGE REPULSED: Assault on {settlement_name} failed. "
                          f"Our forces took {casualties} casualties and were driven back.")

        # Notify both lords via their AI components
        gen_name = general_entity.name
        if parent_house:
            lord_ai = parent_house.get_component(AIComponent)
            if lord_ai:
                lord_ai.add_observation(
                    f"Field report: {gen_name} {'seized' if success else 'failed to seize'} "
                    f"{settlement_name} of House {enemy_house_name}. {result_msg}",
                    phase="Events"
                )
        if enemy_house:
            enemy_ai = enemy_house.get_component(AIComponent)
            if enemy_ai:
                enemy_ai.add_observation(
                    f"SIEGE ALERT: {gen_name} of House "
                    f"{getattr(parent_house, 'name', '?') if parent_house else '?'} "
                    f"has {'destroyed' if success else 'attacked'} {settlement_name}!",
                    phase="Events"
                )

        return result_msg
    besiege.action_description = "**Besiege**: Assault an adjacent enemy settlement — destroy it and loot their resources"
    tools.append(besiege)

    # Navigate home tool — move toward nearest friendly territory
    @function_tool
    def navigate_home(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Move one step toward the nearest tile of your house's territory.
        Useful when lost, cut off, or returning from a distant operation.
        Costs one movement point.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not sim_context.entity_manager:
            return "Navigation failed — no map access"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Navigation failed — position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Navigation failed — no parent house"
        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Navigation failed — parent house not found"
        from feudal_sim.components.territory import TerritoryComponent as _TComp4
        ph_terr = parent_house.get_component(_TComp4)
        if not ph_terr or not ph_terr.territory:
            return "Navigation failed — house has no territory"
        gq, gr = pos.position
        # Find nearest friendly tile
        best_tile, best_dist = None, None
        for t in ph_terr.territory:
            d = (abs(gq-t.q)+abs(gr-t.r)+abs((-gq-gr)-(-t.q-t.r)))//2
            if best_dist is None or d < best_dist:
                best_dist, best_tile = d, t
        if best_dist == 0:
            return "Already on friendly territory."
        if best_tile is None:
            return "No friendly territory found."
        # Step one tile toward the target
        hex_grid = sim_context.hex_grid
        dir_offsets = {'N':(0,-1),'NE':(1,-1),'SE':(1,0),'S':(0,1),'SW':(-1,1),'NW':(-1,0)}
        best_move, best_move_dist = None, best_dist
        for dirn, (dq, dr) in dir_offsets.items():
            nb = hex_grid.get_neighbor(gq, gr, dirn)
            if not nb:
                continue
            d = (abs(nb.q-best_tile.q)+abs(nb.r-best_tile.r)+
                 abs((-nb.q-nb.r)-(-best_tile.q-best_tile.r)))//2
            if d < best_move_dist:
                best_move_dist, best_move = d, (nb.q, nb.r)
        if not best_move:
            return "No clear path toward friendly territory this turn."
        result = pos.move_to(best_move, hex_grid,
                             getattr(sim_context, 'current_turn', None),
                             validate_movement=True)
        if result.get('success'):
            return (f"Moved toward friendly territory — now {best_move_dist} tile(s) away. "
                    f"{result.get('message', '')}")
        return f"Movement blocked: {result.get('message', 'unknown obstacle')}"
    navigate_home.action_description = "**Navigate Home**: Move one step toward nearest friendly territory — use when lost or returning"
    tools.append(navigate_home)

    # Forage tool — gather supplies from terrain, costs all movement this turn
    @function_tool
    def forage(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Forage for supplies from the surrounding terrain.
        Yield depends on terrain richness. Costs all remaining movement points this turn —
        you cannot move after foraging.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Foraging failed — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Foraging failed — position unknown"
        from feudal_sim.components.subagent_group import SubAgentGroup
        from feudal_sim.map.types import HexTileType
        grp: SubAgentGroup = general_entity.get_component(SubAgentGroup)
        if not grp:
            return "Foraging failed — no group component"
        if pos.remaining_movement <= 0:
            return "Cannot forage — no movement points remaining this turn"

        # Terrain yield map (supply points per tile)
        FORAGE_YIELD = {
            HexTileType.TEMPERATE_FOREST: 25, HexTileType.RAINFOREST: 25,
            HexTileType.BOREAL_FOREST: 18, HexTileType.GRASSLAND: 14,
            HexTileType.STEPPE: 12, HexTileType.HILL: 8,
            HexTileType.TUNDRA: 6, HexTileType.SWAMP: 5,
            HexTileType.MOUNTAIN: 4, HexTileType.DESERT: 3,
        }
        IMPASSABLE = {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}

        # Score center tile + immediate neighbors, take the best
        hex_grid = sim_context.hex_grid
        q, r = pos.position
        tiles_to_check = []
        center = hex_grid.get_tile(q, r)
        if center:
            tiles_to_check.append(center)
        for neigh, _ in hex_grid.get_neighbors(q, r):
            if neigh:
                tiles_to_check.append(neigh)

        best_yield = 0
        best_terrain = "unknown"
        for tile in tiles_to_check:
            tt = getattr(tile, 'terrain_type', None)
            if tt in IMPASSABLE:
                continue
            y = FORAGE_YIELD.get(tt, 5)
            if y > best_yield:
                best_yield = y
                best_terrain = tt.name.lower().replace('_', ' ') if tt else "unknown"

        if best_yield == 0:
            return "Nothing to forage here — terrain is water or ice."

        # Consume all movement
        pos.remaining_movement = 0

        old_supplies = grp.supplies
        grp.resupply(best_yield)
        gained = grp.supplies - old_supplies

        return (f"Foraging complete. Gathered from {best_terrain} — "
                f"+{gained} supplies (now {grp.supplies}%). "
                f"All movement used for the day.")
    forage.action_description = "**Forage**: Gather supplies from terrain (costs all movement this turn)"
    tools.append(forage)

    # Shared rookery tools for generals (include send)
    tools.extend(create_rookery_toolset(general_entity, include_send=True))

    # Objective management tools (mirrors house toolset)
    @function_tool
    def set_objective(objective: str) -> str:
        """
        Set a new mission objective to track across turns (max 5).

        Args:
            objective: Description of the objective to add
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp:
            return "Cannot set objective — AI component unavailable"
        if len(ai_comp.current_objectives) >= 5:
            return f"Objective list full (max 5). Current: {ai_comp.current_objectives}"
        ai_comp.current_objectives.append(objective)
        return f"Objective set: '{objective}'"
    set_objective.action_description = "**Set Objective**: Record a mission goal that persists across turns (max 5)"
    tools.append(set_objective)

    @function_tool
    def remove_objective(objective: str) -> str:
        """
        Remove a mission objective by name or partial match.

        Args:
            objective: Objective text or substring to remove
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp:
            return "Cannot remove objective — AI component unavailable"
        before = list(ai_comp.current_objectives)
        ai_comp.current_objectives = [o for o in ai_comp.current_objectives if objective.lower() not in o.lower()]
        removed = [o for o in before if o not in ai_comp.current_objectives]
        if removed:
            return f"Removed: {removed}"
        return f"No match for '{objective}'. Current: {ai_comp.current_objectives}"
    remove_objective.action_description = "**Remove Objective**: Clear a completed or cancelled mission goal"
    tools.append(remove_objective)

    @function_tool
    def list_objectives() -> str:
        """List all current mission objectives."""
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp or not ai_comp.current_objectives:
            return "No objectives currently set."
        return "Current objectives:\n" + "\n".join(f"  - {o}" for o in ai_comp.current_objectives)
    list_objectives.action_description = "**List Objectives**: View all current mission objectives"
    tools.append(list_objectives)

    # Universal tools
    tools.append(end_turn)

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


def create_caravan_toolset(caravan_entity) -> list:
    """Create tools for caravan entities."""
    tools = []
    
    # Movement and status tools
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.pathfinding import PathfindingComponent
    from feudal_sim.components.cargo import CargoComponent
    
    @function_tool
    def caravan_status(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Get current caravan status including position, destination, cargo, and progress.
        """
        position_comp = caravan_entity.get_component(PositionComponent)
        pathfinding_comp = caravan_entity.get_component(PathfindingComponent)
        cargo_comp = caravan_entity.get_component(CargoComponent)
        
        status_parts = [f"Caravan: {caravan_entity.name}"]
        
        # Position info
        if position_comp and position_comp.position:
            pos = position_comp.position
            movement_info = f"Position: ({pos[0]}, {pos[1]}), Movement: {position_comp.remaining_movement}/{position_comp.max_movement_points}"
            status_parts.append(movement_info)
        
        # Destination and progress
        if pathfinding_comp and pathfinding_comp.destination:
            dest = pathfinding_comp.destination
            remaining = pathfinding_comp.get_remaining_distance()
            status_parts.append(f"Destination: ({dest[0]}, {dest[1]}), Distance: {remaining} tiles")
            
            if pathfinding_comp.is_at_destination():
                status_parts.append("STATUS: At destination!")
        
        # Cargo info
        if cargo_comp:
            cargo_summary = cargo_comp.get_cargo_summary()
            trade_summary = cargo_comp.get_trade_summary()
            status_parts.append(f"Cargo: {cargo_summary}")
            status_parts.append(f"Mission: {trade_summary}")
        
        return " | ".join(status_parts)
    
    caravan_status.action_description = "**Caravan Status**: Check position, destination, cargo, and mission progress"
    tools.append(caravan_status)
    
    @function_tool
    def continue_journey(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Continue moving towards the destination (automatic movement handled by simulation).
        """
        pathfinding_comp = caravan_entity.get_component(PathfindingComponent)
        
        if not pathfinding_comp:
            return "Cannot continue journey - no pathfinding capability"
        
        if pathfinding_comp.is_at_destination():
            return "Already at destination - ready for trade negotiations"
        
        remaining_distance = pathfinding_comp.get_remaining_distance()
        return f"Continuing journey to destination. {remaining_distance} tiles remaining."
    
    continue_journey.action_description = "**Continue Journey**: Proceed towards trade destination"
    tools.append(continue_journey)
    
    # Communication with parent house
    @function_tool
    def send_trade_update(ctx: RunContextWrapper["SimulationContext"], message: str) -> str:
        """
        Send a status update back to your sponsoring house.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send update - simulation context unavailable"
        
        sender_house_id = getattr(caravan_entity, 'sender_house_id', None)
        if not sender_house_id:
            return "Cannot send update - no parent house identified"
        
        parent_house = sim_context.entity_manager.get_entity(sender_house_id)
        if not parent_house:
            return "Cannot send update - parent house not found"
        
        # Add observation to parent house AI
        from feudal_sim.components.ai import AIComponent
        ai_comp = parent_house.get_component(AIComponent)
        if ai_comp:
            caravan_update = f"Trade caravan update: {message}"
            ai_comp.add_observation(caravan_update, "Actions")
            return f"Trade update sent to {parent_house.name}: '{message}'"
        
        return "Update sent but parent house has no AI to receive it"
    
    send_trade_update.action_description = "**Send Trade Update**: Report status to sponsoring house"
    tools.append(send_trade_update)
    
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