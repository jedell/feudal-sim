"""
Territory, city, and general-deployment tools for the feudal simulation.
"""

from typing import Callable

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401
from feudal_sim.ai.tools.common import _balance_line, hex_distance
from feudal_sim.config.subagents import get_deploy_costs, get_general_cap


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
    from feudal_sim.ai.prompts import AgentType
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.components.population import AssignedPopulation, PopulationComponent
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.components.territory import TerritoryComponent
    from feudal_sim.core.entities import Entity

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
                    _d2 = hex_distance(deployment_position, _c2.position)
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
