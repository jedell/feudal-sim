import random
import click

from feudal_sim.map.hex_grid import HexGrid
from feudal_sim.houses.house import House
from feudal_sim.map.types import HexTileType, Color
from feudal_sim.core.time import GameTime
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.map.tile_extensions import add_gold_mine, add_iron_deposit
from feudal_sim.extensions.resource_monitor import resource_monitor

ALPHA = 120

class Simulation:
    def __init__(self):
        # Use config for world generation
        map_size = config.get('simulation.world_generation.map_size', 80)
        num_houses = config.get('simulation.world_generation.num_houses', 2)
        
        self.hex_grid = HexGrid(size=map_size, num_houses=num_houses)
        self.houses = self.create_houses()
        self.game_time = GameTime()
        self.step_count = 0
        self.add_resource_nodes()
        
        # Set up extensible event listeners
        self.setup_event_listeners()
        
        # Emit simulation start event for extensibility
        event_bus.emit(EventType.SIMULATION_STARTED, self, 
                      houses=[h.name for h in self.houses], 
                      step_count=self.step_count)

    def create_houses(self) -> list[House]:
        starting_territories = self._assign_starting_territories(2)
        house_stark = House("Stark", color=Color(0, 0, 255, ALPHA))
        house_stark.expand_territory(starting_territories[0], self.hex_grid)
        house_lannister = House("Lannister", color=Color(255, 0, 0, ALPHA))
        house_lannister.expand_territory(starting_territories[1], self.hex_grid)
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
        
        event_bus.subscribe(EventType.VALUE_CHANGED, log_resource_changes)

    def render(self):
        # call hex grid render to update the tiles
        self.hex_grid.render(self.houses)

    def step(self):
        # Emit step start event (enables extensibility)
        event_bus.emit(EventType.SIMULATION_STEP, self, 
                      step_count=self.step_count, 
                      season=self.game_time.season.value)
        
        # simulate
        farming_modifier = self.game_time.get_seasonal_modifier('farming')
        for house in self.houses:
            house.gather_resources(farming_modifier)  # Events are emitted automatically
            house.manage_population()

        # observe
        for house in self.houses:
            house.collect_observations(self.hex_grid, self.step_count)

        print(f"\n{self.game_time}")
        print(f"House {self.houses[0].name} Resources: {self.houses[0].resources}")
        print(f"House {self.houses[1].name} Resources: {self.houses[1].resources}")
        
        # act (placeholder for now)

        self.step_count += 1
        self.game_time.advance_turn()
            
@click.command()
@click.option('--simulation_config', type=str, default='simulation', help='Name of simulation config json file (in config folder)')
@click.option('--world_config', type=str, default='world', help='Name of world config json file (in config folder)')
def main(simulation_config, world_config):
    config.load_config(simulation_config)
    config.load_config(world_config)
    simulation = Simulation()
    try:
        while True:
            simulation.step()
            simulation.render()
            input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Demonstrate extensibility: get analytics from extension
        print("\n📈 Resource Monitor Summary:")
        summary = resource_monitor.get_summary()
        for house_name, resources in summary.items():
            print(f"  {house_name}:")
            for resource_type, stats in resources.items():
                print(f"    {resource_type}: {stats['total_gained']:.0f} gained, {stats['current_amount']:.0f} current")
        
        # Emit simulation end event for extensions
        event_bus.emit(EventType.SIMULATION_ENDED, simulation)
        
        # Clean up shared memory resources
        simulation.hex_grid.terminate_renderer()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()