import random
import asyncio

from feudal_sim.core.logger import get_logger
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
from feudal_sim.core.priority_actions import PriorityActionEventProcessor
from feudal_sim.core.war_registry import WarRegistry
from feudal_sim.core.priority_action_handlers import (
    TradeCaravanHandler, DiplomaticSummitHandler, EnemyEncounterHandler,
    GeneralContactHandler,
)
from feudal_sim.core.event_oracle import EventOracle
from feudal_sim.core.random_events import apply_event

log = get_logger(__name__)

ALPHA = 120

class Simulation:
    """
    Top-level game state and turn loop for the feudal simulation.

    Owns the hex grid, houses, entity manager, time manager, and priority
    action processor, and drives each turn phase (production, actions, events,
    cleanup) via step().
    """

    def __init__(self, debug=False):
        self.deferred = DeferredActionQueue()
        # Lock for multi-step resource/population mutations from concurrent agents
        self._resource_lock = asyncio.Lock()
        # Use config for world generation
        map_size = config.get('simulation.world_generation.map_size', 80)
        
        # Define house names first to get accurate count
        house_names = ["Stark", "Lannister", "Baratheon", "Targaryen"]
        num_houses = len(house_names)
        
        self.hex_grid = HexGrid(size=map_size, num_houses=num_houses, debug=debug)
        self.entity_manager = EntityManager()
        self.entity_manager._simulation_ref = self  # Add simulation reference for priority actions
        self.houses = self.create_houses(house_names)
        self.time_manager = TimeManager(event_bus)
        self.step_count = 0
        self.global_turn = 0   # monotonically increasing, never resets
        self.game_over = False
        self.winner: str | None = None

        # Shared registries
        self.war_registry = WarRegistry()
        self.add_resource_nodes()
        
        # Initialize intelligence reports after all houses have territories
        self.initialize_house_intelligence()
        
        # Houses now set up their own communications during initialization
        # No need for separate setup step
        
        # Set up extensible event listeners
        self.setup_event_listeners()
        
        # Initialize priority action processor
        self.priority_processor = PriorityActionEventProcessor(self)
        self._register_priority_action_handlers()
        
        # Emit simulation start event for extensibility
        event_bus.emit(EventType.SIMULATION_STARTED, self, 
                      houses=[h.name for h in self.houses], 
                      step_count=self.step_count)

    def create_houses(self, house_names: list[str]) -> list[House]:
        """Create the starting houses, assign their territories and capitals,
        and register them with the entity manager."""
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

        house_targaryen = House("Targaryen", color=Color(160, 0, 160, ALPHA), known_recipients=house_names)
        house_targaryen.expand_territory(starting_territories[3], self.hex_grid)
        house_targaryen.establish_capital_city("Dragonstone")

        # Register houses with entity manager
        self.entity_manager._entities[house_stark.id] = house_stark
        self.entity_manager._entities[house_lannister.id] = house_lannister
        self.entity_manager._entities[house_baratheon.id] = house_baratheon
        self.entity_manager._entities[house_targaryen.id] = house_targaryen

        return [house_stark, house_lannister, house_baratheon, house_targaryen]
    
    def _register_priority_action_handlers(self):
        """Register default priority action handlers."""
        # Register built-in handlers
        self.priority_processor.register_handler("trade_caravan_arrival", TradeCaravanHandler())
        self.priority_processor.register_handler("diplomatic_summit", DiplomaticSummitHandler())
        self.priority_processor.register_handler("enemy_encounter", EnemyEncounterHandler())
        self.priority_processor.register_handler("general_contact", GeneralContactHandler())

        # Event oracle — generates contextualised random events in the background
        self.event_oracle = EventOracle(self)
        
        log.info("✅ Priority action handlers registered")
    
    
    def _assign_starting_territories(self, n: int):
        # Pick starting tiles with a guaranteed minimum separation so houses
        # don't spawn adjacent or overlapping.
        map_size = config.get('simulation.world_generation.map_size', 20)
        min_separation = max(8, map_size // n)  # scale with map and house count

        def _hex_dist(t1, t2):
            return (abs(t1.q - t2.q) + abs(t1.r - t2.r) +
                    abs((-t1.q - t1.r) - (-t2.q - t2.r))) // 2

        random_tiles = []
        max_attempts = 500
        attempts = 0
        while len(random_tiles) < n and attempts < max_attempts:
            attempts += 1
            tile = self.hex_grid.get_random_tile(1)[0]
            if tile.terrain_type in {HexTileType.RIVER, HexTileType.LAKE, HexTileType.OCEAN}:
                continue
            if all(_hex_dist(tile, existing) >= min_separation for existing in random_tiles):
                random_tiles.append(tile)

        # Fallback: if we couldn't place all houses with full separation, relax
        # progressively until enough positions are found
        if len(random_tiles) < n:
            relaxed = min_separation
            while len(random_tiles) < n and relaxed > 3:
                relaxed -= 1
                for _ in range(200):
                    tile = self.hex_grid.get_random_tile(1)[0]
                    if tile.terrain_type in {HexTileType.RIVER, HexTileType.LAKE, HexTileType.OCEAN}:
                        continue
                    if all(_hex_dist(tile, existing) >= relaxed for existing in random_tiles):
                        random_tiles.append(tile)
                    if len(random_tiles) >= n:
                        break
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
        log.info("🏗️  Adding resource nodes to the map...")
        
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
                log.info(f"   💰 Added gold mine at ({tile.q}, {tile.r})")
            else:
                add_iron_deposit(tile)  
                log.info(f"   ⛏️  Added iron deposit at ({tile.q}, {tile.r})")
        
        log.info(f"✅ Added {len(selected_tiles)} resource nodes")
    
    def initialize_house_intelligence(self):
        """Initialize intelligence reports for all houses after territories are assigned."""        
        log.info("🔍 Initializing house intelligence reports...")
        
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
                log.info(f"📊 {house_name} gained {change:+.0f} {resource_type}")
        
        def log_time_changes(event):
            change_type = event.data.get('change_type')
            if change_type == 'season':
                old_season = event.data['old_season']
                new_season = event.data['new_season']
                log.info(f"🌅 Season changed: {old_season} → {new_season}")
            elif change_type == 'year':
                old_year = event.data['old_year']
                new_year = event.data['new_year']
                log.info(f"📅 New Year! {old_year} → {new_year}")
        
        event_bus.subscribe(EventType.VALUE_CHANGED, log_resource_changes)
        event_bus.subscribe(EventType.STATE_CHANGED, log_time_changes)

    def render(self):
        """Collect positioned entities and a turn/season HUD sentinel, then
        hand them to the hex grid renderer."""
        # Collect positioned entities (generals, scouts, etc.)
        positioned_entities = []
        
        # Add generals
        generals = self.entity_manager.get_entities_by_type('general')
        log.info(f"🧠 Found {len(generals)} generals")
        if generals:
            positioned_entities.extend(generals)
        
        # Add caravans
        caravans = self.entity_manager.get_entities_by_type('caravan')
        log.info(f"🚚 Found {len(caravans)} caravans")
        if caravans:
            positioned_entities.extend(caravans)
        
        # Inject a sentinel meta-entity carrying turn/season for the HUD.
        # Uses q=turn, r=season_index (0=spring,1=summer,2=autumn,3=winter),
        # movement_points=year. The C++ renderer identifies it by name "__meta__".
        try:
            from feudal_sim.core.entities import Entity
            from feudal_sim.components.position import PositionComponent
            status = self.time_manager.get_current_status()
            season_map = {'spring': 0, 'summer': 1, 'autumn': 2, 'winter': 3}
            season_idx = season_map.get(status.get('season', 'spring'), 0)
            meta = Entity('__meta__', '__meta__')
            meta_pos = PositionComponent(entity_id='__meta__',
                                         position=(status['turn'], season_idx),
                                         movement_points=status.get('year', 1))
            meta.add_component(meta_pos)
            positioned_entities.append(meta)
        except Exception:
            pass

        # call hex grid render to update the tiles and entities
        self.hex_grid.render(self.houses, positioned_entities)

    async def step(self):
        """Execute one phase of the simulation."""
        current_phase = self.time_manager.game_time.phase
        
        log.info(f"\n⚙️  {current_phase.value.title()} Phase - {self.time_manager.game_time}")
        
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
        """Handle AI decisions and actions, including priority action events."""
        from feudal_sim.components.position import PositionComponent

        status = self.time_manager.get_current_status()

        # Process priority action events BEFORE normal decisions
        log.info("🎯 Processing priority action events...")
        priority_results = await self.priority_processor.process_all_events()
        for result in priority_results:
            log.info(f"   {result}")
        
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
        
        # Get all caravans and handle their movement
        caravans = self.entity_manager.get_entities_by_type('caravan')
        
        # Process caravan movement first (before AI decisions)
        caravans_to_remove = []
        for caravan in caravans:
            # Reset movement points for new turn
            caravan.reset_movement_points(status['turn'])
            
            # Move caravan towards destination, consuming all movement points.
            # Arrival triggers as soon as the caravan steps onto any tile owned
            # by the recipient house — not just the exact destination coordinate.
            recipient_id = getattr(caravan, 'recipient_house_id', None)

            def _on_recipient_tile(pos_tuple):
                if not recipient_id or not pos_tuple:
                    return False
                tile = self.hex_grid.get_tile(pos_tuple[0], pos_tuple[1])
                if not tile:
                    return False
                owner = getattr(tile, 'owner', None)
                return owner is not None and getattr(owner, 'id', None) == recipient_id

            if not caravan.is_at_destination() and not _on_recipient_tile(
                    getattr(caravan.get_component(PositionComponent), 'position', None)):
                arrived = False
                while not arrived:
                    movement_result = caravan.move_towards_destination(self.hex_grid, status['turn'])
                    if not movement_result.get('success', False):
                        log.info(f"🚚 {caravan.name}: {movement_result['message']}")
                        break
                    log.info(f"🚚 {caravan.name}: {movement_result['message']}")
                    new_pos = movement_result.get('new_position')
                    if movement_result.get('arrived', False) or _on_recipient_tile(new_pos):
                        arrived = True
                        arrival_event = caravan.on_arrival(self, status['turn'])
                        self.priority_processor.add_event(arrival_event)
                        caravans_to_remove.append(caravan)
            else:
                if _on_recipient_tile(
                        getattr(caravan.get_component(PositionComponent), 'position', None)):
                    # Already on recipient territory from a prior turn — fire arrival
                    if caravan not in caravans_to_remove:
                        arrival_event = caravan.on_arrival(self, status['turn'])
                        self.priority_processor.add_event(arrival_event)
                        caravans_to_remove.append(caravan)
                        log.info(f"🎯 {caravan.name}: on recipient territory, triggering arrival")
                else:
                    log.info(f"🚚 {caravan.name}: Already at destination")
        
        # Remove arrived caravans from tracking
        for caravan in caravans_to_remove:
            # Don't destroy the entity yet - the priority action handler will manage it
            log.info(f"🎯 Trade caravan {caravan.name} has arrived and triggered priority negotiation")
        
        for general in generals:
            # Reset movement points for new turn
            position_comp = general.get_component(PositionComponent)
            if position_comp:
                position_comp.reset_movement(status['turn'])
            
            # NOTE: update_turn() (upkeep, supplies, morale) runs in execute_events_phase()
            # so generals act with accurate current-turn state and get one full turn
            # before upkeep is settled and disband decisions are made.
            
            # Add basic observations for generals
            ai_comp = general.get_component(AIComponent)
            if ai_comp and position_comp:
                position_comp.add_movement_observation(ai_comp, "Actions")

                # Terrain observation is on-demand via observe_area tool — not auto-injected.
                
                # Add automatic construction status observations
                try:
                    if hasattr(general, 'house_id'):
                        parent_house = self.entity_manager.get_entity(general.house_id)
                        if parent_house:
                            territory_comp = parent_house.get_component(TerritoryComponent)
                            if territory_comp and position_comp.position:
                                current_turn = self.time_manager.get_current_status()['turn']
                                
                                # Check for pending outpost construction (general must stay within 1 tile)
                                gq, gr = position_comp.position
                                for order in territory_comp.pending_outposts:
                                    if order.status != "pending":
                                        continue
                                    if order.required_general_id != general.id:
                                        continue
                                    dist = (abs(gq - order.q) + abs(gr - order.r) +
                                            abs((-gq - gr) - (-order.q - order.r))) // 2
                                    if dist <= 1:
                                        remaining_turns = order.turn_resolves - current_turn
                                        if remaining_turns > 0:
                                            ai_comp.add_observation(
                                                f"CONSTRUCTION: Outpost in progress {remaining_turns} turn(s) away. "
                                                f"Stay within 1 tile of the build site ({order.q},{order.r}).",
                                                "Actions"
                                            )
                                        else:
                                            ai_comp.add_observation(
                                                "CONSTRUCTION: Outpost completes this turn — stay within 1 tile.",
                                                "Actions"
                                            )
                                        break
                except Exception as _e:
                    log.warning(f"⚠️  {_e}") # Don't fail simulation if observation fails
            
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
        log.info(f"🧠 All entities ({len(self.houses)} houses, {len(generals)} generals) making decisions concurrently...")
        
        async def make_entity_decision(entity):
            entity_name = entity.get_name() if hasattr(entity, 'get_name') else entity.name
            log.info(f"🧠 {entity_name} AI is thinking...")
            
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
            
            log.info(f"✅ {entity_name} AI finished thinking")
            return result
        
        # Execute all entity decisions concurrently
        await asyncio.gather(*[make_entity_decision(entity) for entity in all_ai_entities])

        # After actions, refresh positioned entities in the renderer to clear any disbanded units
        try:
            positioned = []
            generals = self.entity_manager.get_entities_by_type('general') or []
            caravans = self.entity_manager.get_entities_by_type('caravan') or []
            positioned.extend(generals)
            positioned.extend(caravans)
            self.hex_grid.render(self.houses, positioned)
        except Exception as _e:
            log.warning(f"⚠️  {_e}")
    
    def execute_events_phase(self):
        """Handle random events and diplomacy."""
        status = self.time_manager.get_current_status()
        self.global_turn += 1

        # Process outpost construction orders BEFORE upkeep — so a general who ran out
        # of supplies this turn can still complete an outpost they were holding.
        # Uses global_turn (never resets) to avoid seasonal week-rollover bug.
        self.process_outpost_orders(self.global_turn)

        # Apply general upkeep and handle disbands AFTER generals have had their turn
        from feudal_sim.components.subagent_group import SubAgentGroup as _SAG
        generals_this_turn = self.entity_manager.get_entities_by_type('general') or []
        for general in generals_this_turn:
            group_comp: _SAG = general.get_component(_SAG)
            if not group_comp:
                continue
            group_comp.update_turn(self.hex_grid, status['turn'], self.entity_manager)
            if getattr(group_comp, 'should_disband', False):
                parent = self.entity_manager.get_entity(getattr(group_comp, 'parent_house_id', None))
                if parent:
                    pop_comp: PopulationComponent = parent.get_component(PopulationComponent)
                    if pop_comp:
                        pop_comp.recall_population_from_agent(general.id)
                self.entity_manager.destroy_entity(general.id)
                try:
                    if parent:
                        ai: AIComponent = parent.get_component(AIComponent)
                        if ai:
                            gen_name = getattr(general, 'name', general.id)
                            people = group_comp.assigned_population.total
                            ai.add_observation(
                                f"General {gen_name} disbanded — upkeep/morale failure "
                                f"({people} people returned to the realm).",
                                phase="Events"
                            )
                            ai.record_journal_entry(f"General {gen_name} disbanded (upkeep/morale failure)")
                except Exception as _e:
                    log.warning(f"⚠️  {_e}")
                log.info(f"🛑 Disbanded {getattr(general, 'name', general.id)} — upkeep/morale failure")

        # Deliver ravens
        delivered_ravens = RavenDeliverySystem.deliver_ravens_for_turn(
            self.entity_manager, 
            status['turn']
        )
        
        if delivered_ravens > 0:
            log.info(f"📬 {delivered_ravens} ravens delivered this turn")
        
        # Collect rookery observations for AI components
        self.collect_rookery_observations()
        
        # Process expansion orders
        self.process_expansion_orders(status['turn'])
        
        # Process scheduled disbands
        self.process_scheduled_disbands(status['turn'])

        # Process generic deferred actions for Events
        self.process_deferred_actions(status['turn'], 'Events')
        
        # Detect general-to-general contact for next turn's Actions phase
        self._detect_general_contacts(status['turn'])

        # Notify generals of nearby enemy caravans so they can act next turn
        self._detect_caravan_proximity()

        # Inject / refresh situational context for lords and generals
        self._update_situation_contexts(status)

        # Fire any oracle events whose deploy_turn has arrived
        for event in self.event_oracle.pop_due_events(status['turn']):
            result = apply_event(event, self)
            log.info(f"🌍 Event resolved: {result}")

        # Refill oracle queue asynchronously (fire-and-forget)
        if len(self.event_oracle.queue) < 3:
            asyncio.create_task(self.event_oracle.refill_queue())

        # Settlement tier progression
        self.process_settlement_upgrades(self.global_turn)

        # Check victory conditions
        self.check_victory_conditions(self.global_turn)

        # Process population revolts
        self.process_population_revolts(status['turn'])

        # After events, refresh positioned entities as well
        try:
            positioned = []
            generals = self.entity_manager.get_entities_by_type('general') or []
            caravans = self.entity_manager.get_entities_by_type('caravan') or []
            positioned.extend(generals)
            positioned.extend(caravans)
            self.hex_grid.render(self.houses, positioned)
        except Exception as _e:
            log.warning(f"⚠️  {_e}")
            
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
                log.info(f"🏰 Resolving expansion order for {house.get_name()} ({order.direction}) - {order.success_probability:.0%} base chance")
                
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
                        log.info(f"✅ {result['message']} (rolled {roll:.2f} vs {order.success_probability:.2f})")
                        
                        # Add detailed AI observation
                        if ai_component:
                            observation = f"Expansion {order.direction} succeeded! {result['message']} Your forces proved capable despite the challenges."
                            ai_component.add_observation(observation, "Events")
                            ai_component.record_journal_entry(
                                f"Expansion {order.direction} succeeded: +{len(order.target_tiles)} tile(s)")
                    else:
                        # Expansion failed despite having resources
                        result = territory_component.resolve_expansion_order(order, False, self.hex_grid)
                        
                        # Generate detailed failure reasoning
                        failure_reason = self._generate_expansion_failure_reason(order, roll)
                        log.info(f"❌ {result['message']} - {failure_reason} (rolled {roll:.2f} vs {order.success_probability:.2f})")
                        
                        # Add detailed AI observation
                        if ai_component:
                            observation = f"Expansion {order.direction} failed! {result['message']} {failure_reason}"
                            ai_component.add_observation(observation, "Events")
                            ai_component.record_journal_entry(
                                f"Expansion {order.direction} failed (costs paid, no land gained)")
                else:
                    # Expansion failed due to insufficient resources - no costs applied
                    result = territory_component.resolve_expansion_order(order, False, self.hex_grid)
                    failure_reason = f"Insufficient resources: {', '.join(insufficient_resources)}"
                    log.info(f"❌ {result['message']} - {failure_reason}")
                    
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
        for tile in order.target_tiles:
            terrain_str = str(tile.terrain_type) if hasattr(tile, 'terrain_type') else ''
            if 'MOUNTAIN' in terrain_str:
                specific_factors.append("the mountainous terrain required specialized equipment you lacked")
            elif 'HILL' in terrain_str:
                specific_factors.append("the hilly landscape complicated supply routes")
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
    
    def process_settlement_upgrades(self, global_turn: int):
        """Upgrade settlements that meet age and resource requirements."""
        UPGRADE_RULES = {
            1: {'turns_required': 5,  'food': 50,  'material': 0,   'to_name': 'Village'},
            2: {'turns_required': 10, 'food': 100, 'material': 50,  'to_name': 'Town'},
        }
        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.resource import ResourceComponent
        for house in self.houses:
            city_comp = house.get_component(CityComponent)
            res_comp = house.get_component(ResourceComponent)
            ai = house.get_component(AIComponent)
            if not city_comp or not res_comp:
                continue
            for city_name, city in list(city_comp.get_all_cities().items()):
                dev = getattr(city, 'development_level', 1)
                if dev not in UPGRADE_RULES:
                    continue
                rule = UPGRADE_RULES[dev]
                founded = getattr(city, 'founded_turn', global_turn)
                if global_turn - founded < rule['turns_required']:
                    continue
                if res_comp.resources.food < rule['food']:
                    continue
                if rule['material'] > 0 and res_comp.resources.material < rule['material']:
                    continue
                costs = {k: v for k, v in [('food', rule['food']), ('material', rule['material'])] if v > 0}
                if not res_comp.consume_for_action(costs, f"Settlement Upgrade ({city_name})"):
                    continue
                # Upgrade in CityComponent and on tile
                city.development_level = dev + 1
                tile = self.hex_grid.get_tile(*city.position)
                if tile:
                    try:
                        from feudal_sim.map.city_extensions import upgrade_city
                        upgrade_city(tile)
                        tile.food_output = min(tile.food_output * 1.5, 20.0)
                        tile.material_output = min(tile.material_output * 1.5, 20.0)
                    except Exception as _e:
                        log.warning(f"⚠️  upgrade_city: {_e}")
                new_name = rule['to_name']
                log.info(f"🏘️  {city_name} in House {house.name} upgraded to {new_name}")
                self._log_event(f"{house.name}: '{city_name}' upgraded to {new_name}")
                if ai:
                    ai.add_observation(
                        f"Settlement '{city_name}' has grown into a {new_name}! Its output improves.", "Events"
                    )
                    ai.record_journal_entry(f"'{city_name}' upgraded to {new_name}")

    def check_victory_conditions(self, global_turn: int) -> bool:
        """Check if any house has achieved a victory condition. Returns True if game should end."""
        if self.game_over:
            return True
        from feudal_sim.map.types import HexTileType
        land_tiles = [t for t in self.hex_grid.tiles
                      if getattr(t, 'terrain_type', None) not in
                      {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER}]
        total_land = len(land_tiles)
        if total_land == 0:
            return False
        # Count tiles per house
        tile_counts: dict[str, int] = {}
        for tile in land_tiles:
            owner = getattr(tile, 'owner', None)
            owner_name = owner.name if (owner and hasattr(owner, 'name')) else None
            if owner_name and owner_name != 'None':
                tile_counts[owner_name] = tile_counts.get(owner_name, 0) + 1
        # Territorial dominance: configured share of land tiles
        dominance_pct = config.get('simulation.victory.territorial_dominance_pct', 0.60)
        if dominance_pct:
            for house_name, count in tile_counts.items():
                if count / total_land > dominance_pct:
                    self._trigger_victory(house_name, "territorial dominance", global_turn)
                    return True
        # Last survivor: only one house has living population
        if config.get('simulation.victory.last_survivor', True):
            living = [h for h in self.houses
                      if (h.get_component(PopulationComponent) and
                          h.get_component(PopulationComponent).population > 0)]
            if len(living) == 1:
                self._trigger_victory(living[0].name, "last survivor", global_turn)
                return True
        return False

    def _trigger_victory(self, winner_name: str, condition: str, global_turn: int):
        self.game_over = True
        self.winner = winner_name
        msg = (f"VICTORY! House {winner_name} has achieved {condition} "
               f"and now rules the realm! (Turn {global_turn})")
        log.info(f"🏆 {msg}")
        self._log_event(msg)
        for house in self.houses:
            ai = house.get_component(AIComponent)
            if ai:
                ai.inject_situation('victory', msg, expires_after_turns=0)

    def _log_event(self, text: str) -> None:
        """Write to the renderer's event log shared memory."""
        try:
            if hasattr(self, 'hex_grid') and hasattr(self.hex_grid, 'renderer'):
                self.hex_grid.renderer.event_log.log_event(text)
        except Exception:
            pass

    def process_population_revolts(self, current_turn: int):
        """Process population revolts that may cause territory loss."""
        
        for house in self.houses:
            population_component: PopulationComponent = house.get_component(PopulationComponent)
            ai_component: AIComponent = house.get_component(AIComponent)
            
            if not population_component:
                continue
            
            # Check if a revolt should occur
            if population_component.check_for_revolt(current_turn):
                log.info(f"🔥 Population revolt occurring in {house.get_name()}!")
                
                # Execute the revolt
                revolt_result = population_component.execute_revolt(self.hex_grid)
                
                if revolt_result['success']:
                    log.info(f"💥 {revolt_result['message']}")
                    
                    # Display resource losses if any
                    if revolt_result.get('resource_losses'):
                        losses = revolt_result['resource_losses']
                        loss_details = []
                        for resource, amount in losses.items():
                            if amount > 0:
                                loss_details.append(f"{amount} {resource}")
                        if loss_details:
                            log.info(f"🔴 Resource losses: {', '.join(loss_details)}")
                    
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
                        ai_component.record_journal_entry(
                            "Revolt! Territory and resources lost to unrest")
                    
                    # Update population capacity after territory loss
                    territory_component: TerritoryComponent = house.get_component(TerritoryComponent)
                    if territory_component:
                        new_capacity = population_component.calculate_capacity_from_territories(territory_component.territory)
                        log.info(f"📉 {house.get_name()} population capacity reduced to {new_capacity}")
                        
                        # If population exceeds new capacity, reduce it
                        if population_component.population > new_capacity:
                            excess = population_component.population - new_capacity
                            population_component.population = new_capacity
                            log.info(f"👥 {house.get_name()} population reduced by {excess} due to lost territory")
                            
                            if ai_component:
                                ai_component.add_observation(
                                    f"Population reduced by {excess} due to insufficient territory capacity after revolt.",
                                    "Events"
                                )
                else:
                    log.warning(f"⚠️ Revolt attempted in {house.get_name()}, but {revolt_result['message']}")
                    
                    if ai_component:
                        ai_component.add_observation(
                            f"⚠️ Your people attempted to revolt, but {revolt_result['message']}",
                            "Events"
                        )
    
    def execute_cleanup_phase(self):
        """Handle end-of-turn cleanup and display."""
        status = self.time_manager.get_current_status()
        log.info(f"📊 Turn Summary - {status['season']} Year {status['year']}")
        
        for house in self.houses:
            resources = house.resources
            log.info(f"House {house.get_name()} Resources: {resources}")
            log.info(f"House {house.get_name()} Population: {house.population}, Loyalty: {house.population_loyalty}")
        
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
                    # Allow completion on tiles owned by this house OR unowned land
                    owner = getattr(tile, 'owner', None)
                    tile_is_valid = (owner is None or
                                     (hasattr(owner, 'id') and owner.id == house.id))
                    if tile_is_valid:
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
                        except Exception as _e:
                            log.warning(f"⚠️  {_e}")
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
                        except Exception as _e:
                            log.warning(f"⚠️  {_e}")
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
                        # Claim the outpost site itself if still unowned
                        # (generals can build on unowned land; the center tile must be
                        # claimed so owner_color is set and the sprite renders visibly)
                        if not getattr(tile, 'owner', None):
                            house.expand_territory([tile], self.hex_grid)
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
                        except Exception as _e:
                            log.warning(f"⚠️  {_e}")
                        success = True
                # Clear pending construction marker regardless of outcome
                if tile:
                    tile._pending_outpost = False
                terr.resolve_outpost_order(order, success)
                # Notify AI
                ai: AIComponent = house.get_component(AIComponent)
                if ai:
                    if success:
                        ai.add_observation(
                            f"Outpost completed at our controlled site; {claimed} nearby tiles brought into our domain",
                            "Events",
                        )
                        ai.record_journal_entry(f"Outpost established at ({order.q},{order.r}), {claimed} tiles claimed")
                        self._log_event(f"{house.name}: Outpost built at ({order.q},{order.r})")
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
                    except Exception as _e:
                        log.warning(f"⚠️  {_e}")
                # Notify AI
                ai: AIComponent = house.get_component(AIComponent)
                if ai:
                    ai.add_observation(
                        f"General {disband.general_name} has been disbanded and assigned population recalled",
                        "Events",
                    )

    def process_deferred_actions(self, current_turn: int, phase: str):
        """Process generic deferred actions for the given phase."""
        for action in self.deferred.pop_due(current_turn, phase):
            if action.action_type == 'resupply_general':
                self._process_resupply_delivery(action)

    def _update_situation_contexts(self, status: dict):
        """
        Evaluate simulation state each Events phase and inject / clear
        situation-specific guidance on relevant agents.
        """
        current_turn = status['turn']
        season = status.get('season', '').lower()
        week = status.get('week', current_turn)

        for house in self.houses:
            ai: AIComponent = house.get_component(AIComponent)
            if not ai:
                continue

            # Situation: food_crisis_with_generals
            # Connects food scarcity to the cost of deployed forces
            from feudal_sim.components.resource import ResourceComponent
            from feudal_sim.components.territory import TerritoryComponent
            res = house.get_component(ResourceComponent)
            terr = house.get_component(TerritoryComponent)
            if res and terr and terr.deployed_generals:
                food = res.resources.food
                total_deployed = sum(
                    g.get('soldiers_assigned', 0) + g.get('workers_assigned', 0)
                    for g in terr.deployed_generals
                )
                from feudal_sim.core.config import config as _cfg
                upkeep_food = total_deployed * _cfg.get('simulation.subagents.upkeep.food_per_soldier', 0.25)
                if food < 100 and upkeep_food > 0:
                    ai.inject_situation(
                        'food_crisis_with_generals',
                        f"FOOD SHORTAGE + DEPLOYED FORCES: You have {food:.0f} food and "
                        f"{len(terr.deployed_generals)} general(s) with {total_deployed} people "
                        f"consuming ~{upkeep_food:.1f} food/turn in upkeep.\n"
                        f"If food reaches 0 your population starves and generals begin disbanding.\n"
                        f"Consider: disband_general to free upkeep, forage() orders, "
                        f"or secure food-producing territory urgently.",
                        expires_after_turns=2,
                    )
                else:
                    ai.clear_situation('food_crisis_with_generals')

            # Situation: siege_opportunity — flag when a general is adjacent to an enemy settlement
            try:
                from feudal_sim.map.city_extensions import get_city_info, CityType as _CT
                from feudal_sim.components.position import PositionComponent as _PC2
                generals_of_house = [
                    g for g in (self.entity_manager.get_entities_by_type('general') or [])
                    if getattr(g, 'house_id', None) == house.id
                ]
                siege_alerts = []
                for gen in generals_of_house:
                    gen_pos = gen.get_component(_PC2)
                    if not gen_pos or not gen_pos.position:
                        continue
                    gq, gr = gen_pos.position
                    for dirn in ['N', 'NE', 'SE', 'S', 'SW', 'NW']:
                        nb = self.hex_grid.get_neighbor(gq, gr, dirn)
                        if not nb:
                            continue
                        nb_owner = getattr(nb, 'owner', None)
                        if not nb_owner or getattr(nb_owner, 'id', None) == house.id:
                            continue
                        city_t, dev, _ = get_city_info(nb)
                        if city_t != _CT.NONE:
                            cname = getattr(nb, '_city_name', f"{nb_owner.name} settlement")
                            siege_alerts.append(
                                f"{gen.name} is adjacent ({dirn}) to {cname} of House {nb_owner.name}"
                            )
                if siege_alerts:
                    alert_text = "\n".join(f"  • {a}" for a in siege_alerts[:3])
                    ai.inject_situation(
                        'siege_opportunity',
                        f"SIEGE OPPORTUNITY — your generals are adjacent to enemy settlements:\n"
                        f"{alert_text}\n"
                        f"Use besiege(direction) to assault and loot these settlements. "
                        f"Success destroys the settlement and transfers their resources to your house.",
                        expires_after_turns=2,
                    )
                else:
                    ai.clear_situation('siege_opportunity')
            except Exception as _e:
                log.warning(f"⚠️  siege_opportunity: {_e}")

            # Situation: neighbor_proximity — warn when another house is very close
            if self.entity_manager:
                try:
                    from feudal_sim.components.territory import TerritoryComponent as _TComp2
                    our_terr = house.get_component(_TComp2)
                    if our_terr and our_terr.territory:
                        closest_house = None
                        closest_dist = None
                        for other in self.houses:
                            if other.id == house.id:
                                continue
                            other_terr = other.get_component(_TComp2)
                            if not other_terr or not other_terr.territory:
                                continue
                            for ot in list(other_terr.territory)[:8]:
                                for mt in list(our_terr.territory)[:8]:
                                    d = (abs(mt.q - ot.q) + abs(mt.r - ot.r) +
                                         abs((-mt.q - mt.r) - (-ot.q - ot.r))) // 2
                                    if closest_dist is None or d < closest_dist:
                                        closest_dist, closest_house = d, other.name
                        if closest_dist is not None and closest_dist <= 3:
                            ai.inject_situation(
                                'neighbor_proximity',
                                f"PROXIMITY ALERT: House {closest_house} is only ~{closest_dist} tile(s) "
                                f"from your territory. This is extremely close.\n"
                                f"• Consider defensive posture or diplomatic contact\n"
                                f"• Any general you deploy may quickly encounter enemy forces\n"
                                f"• Expansion toward {closest_house} will likely trigger contact events",
                                expires_after_turns=2,
                            )
                        else:
                            ai.clear_situation('neighbor_proximity')
                except Exception as _e:
                    log.warning(f"⚠️  neighbor_proximity: {_e}")

            # Situation: winter_approaching — inject in Autumn Week 3+
            if season == 'autumn' and week >= 3:
                ai.inject_situation(
                    'winter_approaching',
                    "WINTER IS COMING: Food production will drop ~70% next season.\n"
                    "• Stock at least 3× your current weekly food consumption before winter\n"
                    "• Consider disbanding generals to reduce upkeep burden\n"
                    "• Ensure resupply convoys are dispatched before the season changes",
                    expires_after_turns=3,
                )
            elif season != 'autumn':
                ai.clear_situation('winter_approaching')

        # Situation: outpost_guidance for generals (inject on first turn deployed)
        generals = self.entity_manager.get_entities_by_type('general') or []
        for general in generals:
            gen_ai: AIComponent = general.get_component(AIComponent)
            if not gen_ai:
                continue
            from feudal_sim.components.subagent_group import SubAgentGroup as _SAG
            grp = general.get_component(_SAG)
            if not grp:
                continue
            # Only inject early in deployment; let it expire naturally
            if grp.turns_deployed <= 2:
                from feudal_sim.core.config import config as _cfg2
                min_sp = int(_cfg2.get('simulation.settlements.min_spacing_tiles', 3))
                gen_ai.inject_situation(
                    'outpost_guidance',
                    f"OUTPOST BUILDING GUIDE:\n"
                    f"• Call find_outpost_site() first — scans all 6 directions and returns "
                    f"the nearest valid tile before you waste turns moving\n"
                    f"• You can build on UNOWNED land OR your house's territory — "
                    f"the outpost will claim the tile and surrounding land on completion\n"
                    f"• You CANNOT build on enemy-owned tiles or water/ice\n"
                    f"• Minimum {min_sp} tiles from any existing settlement\n"
                    f"• Use move_along([...]) to navigate in one action rather than move() × N",
                    expires_after_turns=4,
                )

    def _detect_caravan_proximity(self):
        """
        For each general, check if any enemy caravans are within 1 tile.
        If so, inject an observation so the general can choose to intercept next turn.
        """
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.ai import AIComponent as _AI

        generals  = self.entity_manager.get_entities_by_type('general')  or []
        caravans  = self.entity_manager.get_entities_by_type('caravan')  or []

        if not generals or not caravans:
            return

        dir_names = {
            (0, -1): "north", (1, -1): "northeast", (1, 0): "southeast",
            (0, 1): "south", (-1, 1): "southwest", (-1, 0): "northwest",
        }

        for general in generals:
            gen_house = getattr(general, 'house_id', None)
            pos = general.get_component(PositionComponent)
            ai  = general.get_component(_AI)
            if not pos or not pos.position or not ai or not gen_house:
                continue
            gq, gr = pos.position

            for caravan in caravans:
                car_house = getattr(caravan, 'sender_house_id', None)
                if not car_house or car_house == gen_house:
                    continue  # friendly caravan
                cpos = caravan.get_component(PositionComponent)
                if not cpos or not cpos.position:
                    continue
                cq, cr = cpos.position
                dist = (abs(gq - cq) + abs(gr - cr) + abs((-gq - gr) - (-cq - cr))) // 2
                if dist > 1:
                    continue

                # Direction label
                dq, dr = cq - gq, cr - gr
                direction = dir_names.get((dq, dr), "nearby")

                # Cargo summary
                from feudal_sim.components.cargo import CargoComponent
                cargo_comp = caravan.get_component(CargoComponent)
                cargo_str = str(cargo_comp.cargo) if cargo_comp else "unknown goods"

                owner_name = car_house
                owner_entity = self.entity_manager.get_entity(car_house)
                if owner_entity:
                    owner_name = owner_entity.name

                ai.add_observation(
                    f"Enemy caravan spotted {direction} — {caravan.name} from House {owner_name}, "
                    f"carrying {cargo_str}. You may intercept_caravan('{direction}', action) "
                    f"with action: raid, seize, demand_tribute, or let_pass.",
                    phase="Actions"
                )

    def _detect_general_contacts(self, current_turn: int):
        """
        Scan all opposing general pairs. When two are within 1 tile, create a
        GeneralContactEvent to be resolved next turn. Ambush condition: one
        general is stationary 2+ turns and the other is not.
        """
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        from feudal_sim.core.priority_actions import PriorityActionEvent

        generals = self.entity_manager.get_entities_by_type('general') or []
        contacted_pairs: set = set()

        for i, g1 in enumerate(generals):
            for g2 in generals[i + 1:]:
                h1 = getattr(g1, 'house_id', None)
                h2 = getattr(g2, 'house_id', None)
                if not h1 or not h2 or h1 == h2:
                    continue

                pos1 = g1.get_component(PositionComponent)
                pos2 = g2.get_component(PositionComponent)
                if not pos1 or not pos2 or not pos1.position or not pos2.position:
                    continue

                q1, r1 = pos1.position
                q2, r2 = pos2.position
                dist = (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2
                if dist > 1:
                    continue

                pair_key = tuple(sorted([g1.id, g2.id]))
                if pair_key in contacted_pairs:
                    continue
                contacted_pairs.add(pair_key)

                grp1 = g1.get_component(SubAgentGroup)
                grp2 = g2.get_component(SubAgentGroup)

                # Skip if either is already in a contact event
                if (grp1 and grp1.in_contact_event) or (grp2 and grp2.in_contact_event):
                    continue

                # Determine ambush: one side stationary 2+ turns, the other not
                g1_ambush = grp1 and grp1.ambush_ready
                g2_ambush = grp2 and grp2.ambush_ready
                is_ambush = (g1_ambush and not g2_ambush) or (g2_ambush and not g1_ambush)

                # Attacker = moving party; defender = stationary (ambusher) or g1 default
                if is_ambush and g2_ambush:
                    attacker, defender = g1, g2
                else:
                    attacker, defender = g1, g2

                a_grp = attacker.get_component(SubAgentGroup)
                d_grp = defender.get_component(SubAgentGroup)
                a_pos = attacker.get_component(PositionComponent)

                # Terrain at contact point
                terrain_name = ''
                try:
                    tile = self.hex_grid.get_tile(a_pos.position[0], a_pos.position[1]) if a_pos else None
                    if tile:
                        terrain_name = tile.terrain_type.name
                except Exception as _e:
                    log.warning(f"⚠️  {_e}")

                def _house_name(house_id):
                    h = self.entity_manager.get_entity(house_id)
                    return h.name if h else house_id

                event = PriorityActionEvent(
                    event_id=f"contact_{attacker.id}_{defender.id}_{current_turn}",
                    event_type="general_contact",
                    context_data={
                        'attacker_id':         attacker.id,
                        'attacker_name':       attacker.name,
                        'attacker_house_id':   getattr(attacker, 'house_id', ''),
                        'attacker_house_name': _house_name(getattr(attacker, 'house_id', '')),
                        'attacker_soldiers':   a_grp.assigned_population.soldiers if a_grp else 0,
                        'attacker_equip':      a_grp.equipment_level if a_grp else 0,
                        'attacker_morale':     a_grp.morale if a_grp else 100,
                        'defender_id':         defender.id,
                        'defender_name':       defender.name,
                        'defender_house_id':   getattr(defender, 'house_id', ''),
                        'defender_house_name': _house_name(getattr(defender, 'house_id', '')),
                        'defender_soldiers':   d_grp.assigned_population.soldiers if d_grp else 0,
                        'defender_equip':      d_grp.equipment_level if d_grp else 0,
                        'defender_morale':     d_grp.morale if d_grp else 100,
                        'terrain_type':        terrain_name,
                        'is_ambush':           is_ambush,
                        'entity_manager':      self.entity_manager,
                        'hex_grid':            self.hex_grid,
                    },
                    involved_agents=[attacker.id, defender.id],
                    allows_conversation=True,
                    max_conversation_rounds=2,
                    created_turn=current_turn,
                )
                self.priority_processor.add_event(event)

                # Mark both generals as in a contact event
                if a_grp:
                    a_grp.in_contact_event = True
                if d_grp:
                    d_grp.in_contact_event = True

                log.info(f"⚔️  Contact detected: {attacker.name} vs {defender.name}"
                      f"{' (AMBUSH)' if is_ambush else ''}")

    def _process_resupply_delivery(self, action):
        """Deliver a resupply convoy to a general — called from deferred queue."""
        from feudal_sim.components.subagent_group import SubAgentGroup as _SubAgentGroup
        payload = action.payload
        general = self.entity_manager.get_entity(payload['general_id'])
        if not general:
            return
        try:
            grp: _SubAgentGroup = general.get_component(_SubAgentGroup)
            if grp:
                points = payload['supply_points']
                grp.resupply(points)
                gen_ai: AIComponent = general.get_component(AIComponent)
                if gen_ai:
                    gen_ai.add_observation(
                        f"Resupply convoy from {payload['house_name']} arrived: +{points} supplies.",
                        "Events"
                    )
            house = self.entity_manager.get_entity(payload['house_id'])
            if house:
                lord_ai: AIComponent = house.get_component(AIComponent)
                if lord_ai:
                    lord_ai.add_observation(
                        f"Resupply reached {payload['general_name']}: +{payload['supply_points']} supplies delivered.",
                        "Events"
                    )
        except Exception as e:
            log.warning(f"⚠️ Resupply delivery failed for {payload.get('general_name')}: {e}")
            