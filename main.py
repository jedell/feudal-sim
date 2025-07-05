from feudal_sim.map.hex_grid import HexGrid
from feudal_sim.houses.house import House
from feudal_sim.map.types import HexTileType, Color
from feudal_sim.core.time import GameTime

ALPHA = 120

class Simulation:
    def __init__(self):
        self.hex_grid = HexGrid(num_houses=2)
        self.houses = self.create_houses()
        self.game_time = GameTime()
        self.step_count = 0

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
    def render(self):
        # call hex grid render to update the tiles
        self.hex_grid.render(self.houses)

    def step(self):
        # simulate
        farming_modifier = self.game_time.get_seasonal_modifier('farming')
        for house in self.houses:
            house.gather_resources(farming_modifier)  # Add seasonal modifier
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
            
        
    
def main():
    simulation = Simulation()
    try:
        while True:
            simulation.step()
            simulation.render()
            input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up shared memory resources
        simulation.hex_grid.terminate_renderer()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()