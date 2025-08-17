import random
import asyncio

from feudal_sim.map.hex_grid import HexGrid
from feudal_sim.houses.house import House
from feudal_sim.map.types import HexTileType, Color
from feudal_sim.core.time import TimeManager, TurnPhase
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.core.entities import EntityManager
from feudal_sim.components.rookery import RavenDeliverySystem, RookeryComponent
from feudal_sim.map.tile_extensions import add_gold_mine, add_iron_deposit
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.components.intelligence import IntelligenceComponent
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.core.deferred import DeferredActionQueue

ALPHA = 120

class Simulation:
    def __init__(self, debug=False):
        self.deferred = DeferredActionQueue()
        # Use config for world generation
        map_size = config.get('simulation.world_generation.map_size', 80)
        
        # Define house names first to get accurate count
        house_names = ["Stark", "Lannister", "Baratheon"]
        num_houses = len(house_names)
        
        self.hex_grid = HexGrid(size=map_size, num_houses=num_houses, debug=debug)
        self.entity_manager = EntityManager()
        self.houses = self.create_houses(house_names)
        self.time_manager = TimeManager(event_bus)
        self.step_count = 0
        self.add_resource_nodes()
        
        # Initialize intelligence reports after all houses have territories
        self.initialize_house_intelligence()
        
        # Houses now set up their own communications during initialization
        # No need for separate setup step
        
        # Set up extensible event listeners
        self.setup_event_listeners()
        
        # Emit simulation start event for extensibility
        event_bus.emit(EventType.SIMULATION_STARTED, self, 
                      houses=[h.name for h in self.houses], 
                      step_count=self.step_count)

    def create_houses(self, house_names: list[str]) -> list[House]:
        # Use provided house names for known recipients
        starting_territories = self._assign_starting_territories(len(house_names))
        
        # Create houses with known recipients from the start
        house_stark = House("Stark", color=Color(0, 0, 255, ALPHA), known_recipients=house_names)
        house_stark.expand_territory(starting_territories[0], self.hex_grid)
        house_stark.establish_capital_city("Winterfell")
        
        house_lannister = House("Lannister", color=Color(255, 0, 0, ALPHA), known_recipients=house_names)
        house_lannister.expand_territory(starting_territories[1], self.hex_grid)
        house_lannister.establish_capital_city("Casterly Rock")
        
        house_baratheon = House("Baratheon", color=Color(0, 255, 0, ALPHA), known_recipients=house_names)
        house_baratheon.expand_territory(starting_territories[2], self.hex_grid)
        house_baratheon.establish_capital_city("Storm's End")
        # Register houses with entity manager
        self.entity_manager._entities[house_stark.id] = house_stark
        self.entity_manager._entities[house_lannister.id] = house_lannister
        self.entity_manager._entities[house_baratheon.id] = house_baratheon
        
        return [house_stark, house_lannister, house_baratheon]
    
    
    def _assign_starting_territories(self, n: int):
        # get random tile and assign neighbors to houses
        random_tiles = []
        while len(random_tiles) < n:
            tile = self.hex_grid.get_random_tile(1)[0]
            if tile.terrain_type not in {HexTileType.RIVER, HexTileType.LAKE, HexTileType.OCEAN}:
                random_tiles.append(tile)
        # create list of random tiles and their surrounding land tiles
        territories = []
        for tile in random_tiles:
            territory = [tile]
            to_check = list(self.hex_grid.get_neighbors(tile.q, tile.r))
            checked = set()

            while len(territory) < 7 and to_check:

                neighbor, _ = to_check.pop(0)
                checked.add(neighbor)
                
                if neighbor.terrain_type not in {HexTileType.RIVER, HexTileType.LAKE, HexTileType.OCEAN}:
                    territory.append(neighbor)
                    
                    # Add this neighbor's neighbors to the to_check set
                    new_neighbors = set(self.hex_grid.get_neighbors(neighbor.q, neighbor.r))
                    to_check.extend(list(new_neighbors - checked))

            territories.append(territory)
        return territories
    
    def add_resource_nodes(self):
        """Add some resource nodes to random tiles on the map."""
        print("🏗️  Adding resource nodes to the map...")
        
        # Get some random land tiles
        land_tiles = [tile for tile in self.hex_grid.tiles 
                      if self.hex_grid.is_land(tile)]
        
        # Use config for resource node generation
        count_multiplier = config.get('simulation.world_generation.resource_nodes.count_multiplier', 0.05)
        gold_ratio = config.get('simulation.world_generation.resource_nodes.gold_mine_ratio', 0.5)
        
        num_resources = max(1, int(len(land_tiles) * count_multiplier))
        selected_tiles = random.sample(land_tiles, num_resources)
        
        for i, tile in enumerate(selected_tiles):
            # Use configured ratio to determine resource type
            if i / len(selected_tiles) < gold_ratio:
                add_gold_mine(tile)
                print(f"   💰 Added gold mine at ({tile.q}, {tile.r})")
            else:
                add_iron_deposit(tile)  
                print(f"   ⛏️  Added iron deposit at ({tile.q}, {tile.r})")
        
        print(f"✅ Added {len(selected_tiles)} resource nodes")
    
    def initialize_house_intelligence(self):
        """Initialize intelligence reports for all houses after territories are assigned."""        
        print("🔍 Initializing house intelligence reports...")
        
        for house in self.houses:
            intelligence_component: IntelligenceComponent = house.get_component(IntelligenceComponent)
            if intelligence_component:
                intelligence_component.generate_initial_intelligence(self.houses)
    
    def setup_event_listeners(self):
        """Demonstrate extensible event system."""
        # Simple logging system - can be moved to separate file
        def log_resource_changes(event):
            if event.data.get('entity_type') == 'house':
                house_name = event.data['entity_name'] 
                resource_type = event.data['resource_type']
                change = event.data['change']
                print(f"📊 {house_name} gained {change:+.0f} {resource_type}")
        
        def log_time_changes(event):
            change_type = event.data.get('change_type')
            if change_type == 'season':
                old_season = event.data['old_season']
                new_season = event.data['new_season']
                print(f"🌅 Season changed: {old_season} → {new_season}")
            elif change_type == 'year':
                old_year = event.data['old_year']
                new_year = event.data['new_year']
                print(f"📅 New Year! {old_year} → {new_year}")
        
        event_bus.subscribe(EventType.VALUE_CHANGED, log_resource_changes)
        event_bus.subscribe(EventType.STATE_CHANGED, log_time_changes)

    def render(self):
        # Collect positioned entities (generals, scouts, etc.) 
        positioned_entities = []
        
        # Add generals
        generals = self.entity_manager.get_entities_by_type('general')
        print(f"🧠 Found {len(generals)} generals")
        if generals:
            positioned_entities.extend(generals)
        
        # Add other positioned entity types as they're implemented
        # scouts = self.entity_manager.get_entities_by_type('scout')
        # positioned_entities.extend(scouts)
        
        # call hex grid render to update the tiles and entities
        self.hex_grid.render(self.houses, positioned_entities)

    async def step(self):
        """Execute one phase of the simulation."""
        current_phase = self.time_manager.game_time.phase
        
        print(f"\n⚙️  {current_phase.value.title()} Phase - {self.time_manager.game_time}")
        
        # Execute phase-specific logic
        if current_phase == TurnPhase.PRODUCTION:
            self.execute_production_phase()
        elif current_phase == TurnPhase.ACTIONS:
            await self.execute_actions_phase()
        elif current_phase == TurnPhase.EVENTS:
            self.execute_events_phase()
        elif current_phase == TurnPhase.CLEANUP:
            self.execute_cleanup_phase()
        
        # Advance to next phase (emits events automatically)
        self.time_manager.advance_phase()
        self.step_count += 1
    
    def execute_production_phase(self):
        """Handle resource production and population."""
        farming_modifier = self.time_manager.game_time.get_seasonal_modifier('farming')
        
        for house in self.houses:
            house.gather_resources(farming_modifier)
            house.manage_population()
    
    async def execute_actions_phase(self):
        """Handle AI decisions and actions."""
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        from feudal_sim.components.ai import AIComponent
        
        status = self.time_manager.get_current_status()
        
        # Prepare all houses for AI decision making (synchronous setup)
        for house in self.houses:
            house.collect_observations(self.hex_grid, self.step_count)
            
            # Set current date context for rookery component
            rookery_component: RookeryComponent = house.get_component(RookeryComponent)
            if rookery_component:
                current_date = self.time_manager.get_current_date_string()
                rookery_component.set_current_date_context(status['turn'], current_date)
        
        # Get all generals and prepare them for AI decision making
        generals = self.entity_manager.get_entities_by_type('general')
        for general in generals:
            # Reset movement points for new turn
            position_comp = general.get_component(PositionComponent)
            if position_comp:
                position_comp.reset_movement(status['turn'])
            
            # Update sub-agent group state (supplies, morale, terrain observation, upkeep)
            group_comp = general.get_component(SubAgentGroup)
            if group_comp:
                group_comp.update_turn(self.hex_grid, status['turn'], self.entity_manager)
                # Auto-disband handling
                if getattr(group_comp, 'should_disband', False):
                    # Return assigned population to parent house
                    from feudal_sim.components.population import PopulationComponent
                    parent = self.entity_manager.get_entity(getattr(group_comp, 'parent_house_id', None))
                    if parent:
                        pop_comp: PopulationComponent = parent.get_component(PopulationComponent)
                        if pop_comp:
                            # remove assignment entry for this general id
                            pop_comp.recall_population_from_agent(general.id)
                    # Remove general entity
                    self.entity_manager.destroy_entity(general.id)
                    # Notify parent house AI via observation
                    try:
                        if parent:
                            ai: AIComponent = parent.get_component(AIComponent)
                            if ai:
                                gen_name = getattr(general, 'name', general.id)
                                people = group_comp.assigned_population.total if group_comp and hasattr(group_comp, 'assigned_population') else None
                                msg = f"General {gen_name} has disbanded due to upkeep/morale issues" + (f" (assigned {people} people returned)" if people is not None else "")
                                ai.add_observation(msg, phase="Actions")
                    except Exception:
                        pass
                    print(f"🛑 Disbanded {getattr(general, 'name', general.id)} due to upkeep/morale failure")
            
            # Add basic observations for generals
            ai_comp = general.get_component(AIComponent)
            if ai_comp and position_comp:
                position_comp.add_movement_observation(ai_comp, "Actions")
                # Rely on explicit observe_area tool for terrain reporting
            
            # Keep territory general list in sync after updates
            for house in self.houses:
                terr = house.get_component(TerritoryComponent)
                if terr:
                    terr.sync_generals(self.entity_manager)
        
        # Collect all AI entities (houses + generals)
        all_ai_entities = []
        all_ai_entities.extend(self.houses)
        all_ai_entities.extend(generals)
        
        # Run all AI decision making concurrently (houses + generals)
        print(f"🧠 All entities ({len(self.houses)} houses, {len(generals)} generals) making decisions concurrently...")
        
        async def make_entity_decision(entity):
            entity_name = entity.get_name() if hasattr(entity, 'get_name') else entity.name
            print(f"🧠 {entity_name} AI is thinking...")
            
            # Different decision making for houses vs generals
            if hasattr(entity, 'make_ai_decisions'):  # House entity
                result = await entity.make_ai_decisions(
                    current_turn=status['turn'],
                    current_phase=status['phase'],
                    current_season=status['season'],
                    current_year=status['year'],
                    hex_grid=self.hex_grid,
                    entity_manager=self.entity_manager,
                    simulation=self
                )
            else:  # General or other sub-agent
                ai_comp = entity.get_component(AIComponent)
                if ai_comp:
                    # Update AI context for general
                    ai_comp.update_context(
                        current_turn=status['turn'],
                        current_phase=status['phase'],
                        current_season=status['season'],
                        current_year=status['year'],
                        hex_grid=self.hex_grid,
                        entity_manager=self.entity_manager,
                        simulation=self
                    )
                    result = await ai_comp.make_decisions()
                else:
                    result = f"{entity_name} has no AI component"
            
            print(f"✅ {entity_name} AI finished thinking")
            return result
        
        # Execute all entity decisions concurrently
        await asyncio.gather(*[make_entity_decision(entity) for entity in all_ai_entities])

        # After actions, refresh positioned entities in the renderer to clear any disbanded units
        try:
            positioned = self.entity_manager.get_entities_by_type('general') or []
            self.hex_grid.render(self.houses, positioned)
        except Exception:
            pass
    
    def execute_events_phase(self):
        """Handle random events and diplomacy."""
        status = self.time_manager.get_current_status()
        
        # Deliver ravens
        delivered_ravens = RavenDeliverySystem.deliver_ravens_for_turn(
            self.entity_manager, 
            status['turn']
        )
        
        if delivered_ravens > 0:
            print(f"📬 {delivered_ravens} ravens delivered this turn")
        
        # Collect rookery observations for AI components
        self.collect_rookery_observations()
        
        # Process expansion orders
        self.process_expansion_orders(status['turn'])
        
        # Process outpost construction orders
        self.process_outpost_orders(status['turn'])
        
        # Process scheduled disbands
        self.process_scheduled_disbands(status['turn'])

        # Process generic deferred actions for Events
        self.process_deferred_actions(status['turn'], 'Events')
        
        # Process population revolts
        self.process_population_revolts(status['turn'])

        # After events, refresh positioned entities as well
        try:
            positioned = self.entity_manager.get_entities_by_type('general') or []
            self.hex_grid.render(self.houses, positioned)
        except Exception:
            pass
            
        # Placeholder for other random events
    
    def collect_rookery_observations(self):
        """Collect rookery observations and pass them to AI components during Events phase."""
        for house in self.houses:
            rookery_component: RookeryComponent = house.get_component(RookeryComponent)
            ai_component: AIComponent = house.get_component(AIComponent)
            
            if rookery_component and ai_component:
                # Get all rookery observations for this turn
                observations = rookery_component.get_observations_for_ai()
                
                # Add each observation to the AI component
                for observation in observations:
                    if "No ravens received" not in observation:  # Skip empty turn messages
                        ai_component.add_observation(observation, "Events")
    
    def process_expansion_orders(self, current_turn: int):
        """Process expansion orders that are ready for resolution."""
        for house in self.houses:
            territory_component: TerritoryComponent = house.get_component(TerritoryComponent)
            resource_component: ResourceComponent = house.get_component(ResourceComponent)
            population_component: PopulationComponent = house.get_component(PopulationComponent)
            ai_component: AIComponent = house.get_component(AIComponent)
            
            if not territory_component:
                continue
                
            # Get expansion orders ready for resolution
            ready_orders = territory_component.get_expansions_ready_for_resolution(current_turn)
            
            for order in ready_orders:
                print(f"🏰 Resolving expansion order for {house.get_name()} ({order.direction}) - {order.success_probability:.0%} base chance")
                
                # Step 1: Check resource and loyalty requirements
                can_afford = True
                insufficient_resources = []
                
                if resource_component:
                    resources = resource_component.resources
                    for resource_type, cost in order.resource_cost.items():
                        current_amount = resources.get(resource_type)
                        if current_amount < cost:
                            can_afford = False
                            insufficient_resources.append(f"{resource_type} (need {cost}, have {current_amount:.0f})")
                
                # Check population loyalty cost
                population_loyalty_ok = True
                if population_component and order.population_loyalty_cost > 0:
                    if population_component.loyalty < order.population_loyalty_cost:
                        population_loyalty_ok = False
                        insufficient_resources.append(f"loyalty (need {order.population_loyalty_cost}, have {population_component.loyalty:.0f})")
                
                # Step 2: If resources are available, roll for success based on probability
                if can_afford and population_loyalty_ok:
                    # Apply resource costs first
                    if resource_component:
                        resource_component.consume_for_action(order.resource_cost, f"Territory Expansion ({order.direction})")
                    
                    # Apply population loyalty cost
                    if population_component and order.population_loyalty_cost > 0:
                        population_component.adjust_loyalty(-order.population_loyalty_cost)
                    
                    # Roll for success using the calculated probability
                    roll = random.random()
                    success = roll <= order.success_probability
                    
                    if success:
                        # Execute successful expansion
                        result = territory_component.resolve_expansion_order(order, True, self.hex_grid)
                        print(f"✅ {result['message']} (rolled {roll:.2f} vs {order.success_probability:.2f})")
                        
                        # Add detailed AI observation
                        if ai_component:
                            observation = f"Expansion {order.direction} succeeded! {result['message']} Your forces proved capable despite the challenges."
                            ai_component.add_observation(observation, "Events")
                    else:
                        # Expansion failed despite having resources
                        result = territory_component.resolve_expansion_order(order, False, self.hex_grid)
                        
                        # Generate detailed failure reasoning
                        failure_reason = self._generate_expansion_failure_reason(order, roll)
                        print(f"❌ {result['message']} - {failure_reason} (rolled {roll:.2f} vs {order.success_probability:.2f})")
                        
                        # Add detailed AI observation
                        if ai_component:
                            observation = f"Expansion {order.direction} failed! {result['message']} {failure_reason}"
                            ai_component.add_observation(observation, "Events")
                else:
                    # Expansion failed due to insufficient resources - no costs applied
                    result = territory_component.resolve_expansion_order(order, False, self.hex_grid)
                    failure_reason = f"Insufficient resources: {', '.join(insufficient_resources)}"
                    print(f"❌ {result['message']} - {failure_reason}")
                    
                    # Add AI observation
                    if ai_component:
                        observation = f"Expansion {order.direction} cancelled! {result['message']} {failure_reason}"
                        ai_component.add_observation(observation, "Events")
    
    def _generate_expansion_failure_reason(self, order, roll: float) -> str:
        """Generate detailed failure reasoning for territorial expansion (non-combat)."""
        # Since we're expanding into unclaimed territory, failures are logistical/administrative
        base_reasons = [
            "Harsh weather conditions disrupted the settlement efforts",
            "Supply lines proved more difficult to establish than expected", 
            "Local wildlife and natural hazards impeded progress",
            "Terrain surveying revealed unsuitable ground for development",
            "Administrative challenges in organizing the expansion slowed progress",
            "Seasonal flooding made the territory temporarily inaccessible"
        ]
        
        # Additional factors based on expansion characteristics
        specific_factors = []
        
        # Large expansions are harder to coordinate
        if len(order.target_tiles) > 3:
            specific_factors.extend([
                "the ambitious scope of the expansion overwhelmed your administrative capacity",
                "coordinating settlement across so many territories proved complex"
            ])
        
        # Terrain-based challenges
        difficult_terrain = False
        for tile in order.target_tiles:
            terrain_str = str(tile.terrain_type) if hasattr(tile, 'terrain_type') else ''
            if 'MOUNTAIN' in terrain_str:
                specific_factors.append("the mountainous terrain required specialized equipment you lacked")
                difficult_terrain = True
            elif 'HILL' in terrain_str:
                specific_factors.append("the hilly landscape complicated supply routes")
                difficult_terrain = True
            elif 'FOREST' in terrain_str:
                specific_factors.append("dense forests required extensive clearing work")
        
        for house in getattr(self, 'houses', []):
            territory_component: TerritoryComponent = house.get_component(TerritoryComponent)
            if territory_component and order in territory_component.expansion_history + territory_component.pending_expansions:
                population_component: PopulationComponent = house.get_component(PopulationComponent)
                if population_component:
                    ratios = population_component.get_population_ratios()
                    worker_ratio = ratios.get('workers', 0.5)
                    if worker_ratio < 0.4:
                        specific_factors.append("insufficient workers to support the expansion effort")
                    elif worker_ratio < 0.6:
                        specific_factors.append("your workforce was stretched thin across multiple projects")
                break
        
        # Choose primary reason and add specific factors
        primary_reason = random.choice(base_reasons)
        
        if specific_factors:
            secondary_factor = random.choice(specific_factors)
            return f"{primary_reason}, compounded by {secondary_factor}."
        else:
            return f"{primary_reason}."
    
    def process_population_revolts(self, current_turn: int):
        """Process population revolts that may cause territory loss."""
        
        for house in self.houses:
            population_component: PopulationComponent = house.get_component(PopulationComponent)
            ai_component: AIComponent = house.get_component(AIComponent)
            
            if not population_component:
                continue
            
            # Check if a revolt should occur
            if population_component.check_for_revolt(current_turn):
                print(f"🔥 Population revolt occurring in {house.get_name()}!")
                
                # Execute the revolt
                revolt_result = population_component.execute_revolt(self.hex_grid)
                
                if revolt_result['success']:
                    print(f"💥 {revolt_result['message']}")
                    
                    # Display resource losses if any
                    if revolt_result.get('resource_losses'):
                        losses = revolt_result['resource_losses']
                        loss_details = []
                        for resource, amount in losses.items():
                            if amount > 0:
                                loss_details.append(f"{amount} {resource}")
                        if loss_details:
                            print(f"🔴 Resource losses: {', '.join(loss_details)}")
                    
                    # Add AI observation about the revolt
                    if ai_component:
                        revolt_message = f"💥 REVOLT! {revolt_result['message']} Your people's anger has cost you territory!"
                        
                        # Add resource loss details to AI observation
                        if revolt_result.get('resource_losses'):
                            losses = revolt_result['resource_losses']
                            loss_details = []
                            for resource, amount in losses.items():
                                if amount > 0:
                                    loss_details.append(f"{amount} {resource}")
                            if loss_details:
                                revolt_message += f" You also lost {', '.join(loss_details)} in the chaos."
                        
                        revolt_message += " Consider improving loyalty to prevent future revolts."
                        ai_component.add_observation(revolt_message, "Events")
                    
                    # Update population capacity after territory loss
                    territory_component: TerritoryComponent = house.get_component(TerritoryComponent)
                    if territory_component:
                        new_capacity = population_component.calculate_capacity_from_territories(territory_component.territory)
                        print(f"📉 {house.get_name()} population capacity reduced to {new_capacity}")
                        
                        # If population exceeds new capacity, reduce it
                        if population_component.population > new_capacity:
                            excess = population_component.population - new_capacity
                            population_component.population = new_capacity
                            print(f"👥 {house.get_name()} population reduced by {excess} due to lost territory")
                            
                            if ai_component:
                                ai_component.add_observation(
                                    f"Population reduced by {excess} due to insufficient territory capacity after revolt.",
                                    "Events"
                                )
                else:
                    print(f"⚠️ Revolt attempted in {house.get_name()}, but {revolt_result['message']}")
                    
                    if ai_component:
                        ai_component.add_observation(
                            f"⚠️ Your people attempted to revolt, but {revolt_result['message']}",
                            "Events"
                        )
    
    def execute_cleanup_phase(self):
        """Handle end-of-turn cleanup and display."""
        status = self.time_manager.get_current_status()
        print(f"📊 Turn Summary - {status['season']} Year {status['year']}")
        
        for house in self.houses:
            resources = house.resources
            print(f"House {house.get_name()} Resources: {resources}")
            print(f"House {house.get_name()} Population: {house.population}, Loyalty: {house.population_loyalty}")
        
        # Clear raven turn data
        RavenDeliverySystem.clear_turn_data_for_all(self.entity_manager)
            
    def process_outpost_orders(self, current_turn: int):
        """Resolve any outpost orders that complete this turn."""
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.ai import AIComponent
        from feudal_sim.map.types import HexTileType
        
        for house in self.houses:
            terr: TerritoryComponent = house.get_component(TerritoryComponent)
            if not terr:
                continue
            ready = terr.get_outposts_ready_for_resolution(current_turn)
            for order in ready:
                tile = self.hex_grid.get_tile(order.q, order.r)
                success = False
                claimed = 0
                if tile:
                    # verify still controlled by house
                    owner = getattr(tile, 'owner', None)
                    if owner and hasattr(owner, 'id') and owner.id == house.id:
                        # Verify required general remains on the site
                        from feudal_sim.components.position import PositionComponent
                        general_present = False
                        try:
                            req_id = getattr(order, 'required_general_id', '')
                            if req_id:
                                gen = self.entity_manager.get_entity(req_id)
                                if gen:
                                    pos = gen.get_component(PositionComponent)
                                    if pos and pos.position == (order.q, order.r):
                                        general_present = True
                            else:
                                # If no id provided, treat as missing
                                general_present = False
                        except Exception:
                            general_present = False
                        if not general_present:
                            terr.resolve_outpost_order(order, False)
                            ai: AIComponent = house.get_component(AIComponent)
                            if ai:
                                ai.add_observation(
                                    f"Outpost cancelled — {getattr(order, 'required_general_name', 'The general')} was not present on the site at completion",
                                    "Events",
                                )
                            continue
                        # Do not build over existing settlement
                        try:
                            from feudal_sim.map.city_extensions import has_city as _tile_has_city
                            if _tile_has_city(tile):
                                terr.resolve_outpost_order(order, False)
                                ai: AIComponent = house.get_component(AIComponent)
                                if ai:
                                    ai.add_observation(
                                        "Outpost cancelled — site already has a settlement",
                                        "Events",
                                    )
                                continue
                        except Exception:
                            pass
                        # Enforce within-house spacing constraint
                        try:
                            from feudal_sim.core.config import config
                            min_spacing = int(config.get('simulation.settlements.min_spacing_tiles', 3))
                        except Exception:
                            min_spacing = 3
                        too_close = False
                        nearest_name = None
                        nearest_dist = None
                        try:
                            from feudal_sim.components.city import CityComponent
                            city: CityComponent = house.get_component(CityComponent)
                            if city:
                                for c in city.get_all_cities().values():
                                    cq, cr = c.position
                                    s1 = -order.q - order.r
                                    s2 = -cq - cr
                                    dist = (abs(order.q - cq) + abs(order.r - cr) + abs(s1 - s2)) // 2
                                    if nearest_dist is None or dist < nearest_dist:
                                        nearest_dist = dist
                                        nearest_name = getattr(c, 'name', 'settlement')
                                    if dist < min_spacing:
                                        too_close = True
                                        break
                            # Also check other pending outposts for this house
                            if not too_close:
                                for other in getattr(terr, 'pending_outposts', []):
                                    if other is order:
                                        continue
                                    cq, cr = other.q, other.r
                                    s1 = -order.q - order.r
                                    s2 = -cq - cr
                                    dist = (abs(order.q - cq) + abs(order.r - cr) + abs(s1 - s2)) // 2
                                    if nearest_dist is None or dist < nearest_dist:
                                        nearest_dist = dist
                                        nearest_name = 'outpost site'
                                    if dist < min_spacing:
                                        too_close = True
                                        break
                        except Exception:
                            pass
                        if too_close:
                            terr.resolve_outpost_order(order, False)
                            ai: AIComponent = house.get_component(AIComponent)
                            if ai:
                                ai.add_observation(
                                    f"Outpost cancelled — too close to existing settlement ('{nearest_name}' at {nearest_dist} tiles). Minimum spacing is {min_spacing} tiles.",
                                    "Events",
                                )
                            continue
                        # Claim adjacent unowned land tiles
                        to_claim = []
                        for neigh, _dirn in self.hex_grid.get_neighbors(order.q, order.r):
                            if not neigh:
                                continue
                            if getattr(neigh, 'owner', None):
                                continue
                            terr_type = getattr(neigh, 'terrain_type', None)
                            if terr_type in {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER}:
                                continue
                            to_claim.append(neigh)
                        if to_claim:
                            house.expand_territory(to_claim, self.hex_grid)
                            claimed = len(to_claim)
                        # Register outpost in CityComponent and encode on tile
                        try:
                            city: CityComponent = house.get_component(CityComponent)
                            if city:
                                outpost_name = f"{house.get_name()} Outpost {len(city.get_all_cities()) + 1}"
                                city.add_city(outpost_name, (order.q, order.r), city_type="outpost", founded_turn=current_turn)
                                house._encode_city_on_tile(tile, "outpost", 1, outpost_name)
                        except Exception:
                            pass
                        success = True
                terr.resolve_outpost_order(order, success)
                # Notify AI
                ai: AIComponent = house.get_component(AIComponent)
                if ai:
                    if success:
                        ai.add_observation(
                            f"Outpost completed at our controlled site; {claimed} nearby tiles brought into our domain",
                            "Events",
                        )
                    else:
                        ai.add_observation(
                            "Outpost construction failed to complete (site lost or invalid)",
                            "Events",
                        )
    
    def process_scheduled_disbands(self, current_turn: int):
        """Process any disband actions scheduled in the Actions phase."""
        from feudal_sim.components.population import PopulationComponent
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.components.ai import AIComponent
        # For each house, handle its pending disbands
        for house in self.houses:
            # New path: read from deferred queue
            for action in [a for a in self.deferred.pop_due(current_turn, 'Events') if a.action_type == 'disband_general' and a.owner_id == house.id]:
                disband = type('X', (), action.payload)
                gen = self.entity_manager.get_entity(disband.general_id)
                # Recall population if available
                pop_comp: PopulationComponent = house.get_component(PopulationComponent)
                if pop_comp and gen:
                    pop_comp.recall_population_from_agent(gen.id)
                # Destroy general entity
                if gen:
                    self.entity_manager.destroy_entity(gen.id)
                # Unregister in territory
                terr: TerritoryComponent = house.get_component(TerritoryComponent)
                if terr:
                    try:
                        terr.unregister_general(disband.general_id)
                    except Exception:
                        pass
                # Notify AI
                ai: AIComponent = house.get_component(AIComponent)
                if ai:
                    ai.add_observation(
                        f"General {disband.general_name} has been disbanded and assigned population recalled",
                        "Events",
                    )

    def process_deferred_actions(self, current_turn: int, phase: str):
        """Process any generic deferred actions for the given phase."""
        # For now, all specific handlers consume the queue themselves; this is a placeholder for future types.
        pass
            