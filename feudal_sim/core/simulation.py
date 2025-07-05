import random

from feudal_sim.map.hex_grid import HexGrid
from feudal_sim.houses.house import House
from feudal_sim.map.types import HexTileType, Color
from feudal_sim.core.time import TimeManager, TurnPhase
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.core.entities import EntityManager
from feudal_sim.components.rookery import RookeryComponent, RavenDeliverySystem
from feudal_sim.map.tile_extensions import add_gold_mine, add_iron_deposit

ALPHA = 120

class Simulation:
    def __init__(self):
        # Use config for world generation
        map_size = config.get('simulation.world_generation.map_size', 80)
        num_houses = config.get('simulation.world_generation.num_houses', 2)
        
        self.hex_grid = HexGrid(size=map_size, num_houses=num_houses)
        self.entity_manager = EntityManager()
        self.houses = self.create_houses()
        self.time_manager = TimeManager(event_bus)
        self.step_count = 0
        self.add_resource_nodes()
        
        # Houses now set up their own communications during initialization
        # No need for separate setup step
        
        # Set up extensible event listeners
        self.setup_event_listeners()
        
        # Emit simulation start event for extensibility
        event_bus.emit(EventType.SIMULATION_STARTED, self, 
                      houses=[h.name for h in self.houses], 
                      step_count=self.step_count)

    def create_houses(self) -> list[House]:
        starting_territories = self._assign_starting_territories(2)
        
        # Define all house names for known recipients
        house_names = ["Stark", "Lannister"]
        
        # Create houses with known recipients from the start
        house_stark = House("Stark", color=Color(0, 0, 255, ALPHA), known_recipients=house_names)
        house_stark.expand_territory(starting_territories[0], self.hex_grid)
        house_lannister = House("Lannister", color=Color(255, 0, 0, ALPHA), known_recipients=house_names)
        house_lannister.expand_territory(starting_territories[1], self.hex_grid)
        # Register houses with entity manager
        self.entity_manager._entities[house_stark.id] = house_stark
        self.entity_manager._entities[house_lannister.id] = house_lannister
        
        return [house_stark, house_lannister]
    
    
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
        # call hex grid render to update the tiles
        self.hex_grid.render(self.houses)

    def step(self):
        """Execute one phase of the simulation."""
        current_phase = self.time_manager.game_time.phase
        
        print(f"\n⚙️  {current_phase.value.title()} Phase - {self.time_manager.game_time}")
        
        # Execute phase-specific logic
        if current_phase == TurnPhase.PRODUCTION:
            self.execute_production_phase()
        elif current_phase == TurnPhase.ACTIONS:
            self.execute_actions_phase()
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
    
    def execute_actions_phase(self):
        """Handle AI decisions and actions."""
        status = self.time_manager.get_current_status()
        
        for house in self.houses:
            house.collect_observations(self.hex_grid, self.step_count)
            
            # AI decision making
            print(f"🧠 {house.name} AI is making decisions...")
            decision = house.make_ai_decisions(
                current_turn=status['turn'],
                current_phase=status['phase'],
                current_season=status['season'],
                current_year=status['year']
            )
            print(f"🎯 {house.name} Decision: {decision}")
            print()
    
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
            
        # Placeholder for other random events
    
    def execute_cleanup_phase(self):
        """Handle end-of-turn cleanup and display."""
        status = self.time_manager.get_current_status()
        print(f"📊 Turn Summary - {status['season']} Year {status['year']}")
        print(f"House {self.houses[0].name} Resources: {self.houses[0].resources}")
        print(f"House {self.houses[1].name} Resources: {self.houses[1].resources}")
        
        # Clear raven turn data
        RavenDeliverySystem.clear_turn_data_for_all(self.entity_manager)
            