import random
from feudal_sim.map.hex_tile import HexTile, HexTileType

class RiverSystem:
    """Generates rivers by tracing downhill flow across the hex grid."""
    def __init__(self, hex_grid, sealevel: float):
        self.hex_grid = hex_grid
        self.sealevel: float = sealevel
        self.rivers_sources: list[HexTile] = []

    def generate_rivers(self, num_rivers: int):
        print(f"Making {num_rivers} rivers")
        for _ in range(num_rivers):
            source_tile = self._select_river_source()
            if source_tile:
                self._flow_river(source_tile)

        return self.hex_grid.tiles

    def _select_river_source(self):
        # Select a random high-elevation tile to be a river source
        potential_sources = []
        for tile in self.hex_grid.tiles:
            if tile.elevation > 0.44:  # Start rivers in high-elevation areas
                potential_sources.append(tile)

        if potential_sources:
            return random.choice(potential_sources)
        return None

    def _flow_river(self, start_tile: HexTile):
        current_tile = start_tile
        path = [current_tile]
        max_iterations = 600000  # Set a maximum number of iterations

        # If we've reached a hill, start weighted random walk towards the ocean
        ocean_direction = self._find_closest_ocean_direction(current_tile)
            
        for _ in range(max_iterations):
            neighbors = self._get_neighbors_in_direction(current_tile, ocean_direction)
                
            if not neighbors:
                break
                
        # Calculate weights based on elevation difference
            weights = []
            for neighbor in neighbors:
                elevation_diff = current_tile.elevation - neighbor.elevation
                weight = max(0.1, elevation_diff)  # Ensure a minimum weight
                weights.append(weight)
            
            # Normalize weights
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            
            # Choose next tile based on weighted probabilities
            next_tile = random.choices(neighbors, weights=normalized_weights, k=1)[0]
            
            if next_tile.terrain_type in [HexTileType.OCEAN] or next_tile.elevation <= self.sealevel:
                break
            
            if next_tile in path:  # Prevent loops
                break
            
            path.append(next_tile)
            current_tile = next_tile

        for tile in path:
            if tile.terrain_type != HexTileType.LAKE:
                tile.terrain_type = HexTileType.RIVER

        return path  # Return the path for potential further use or analysis

    def _find_closest_ocean_direction(self, tile: HexTile):
        directions = ["N", "NE", "SE", "S", "SW", "NW"]
        shortest_distance = float('inf')
        best_direction = None

        for direction in directions:
            distance = self._shoot_ray(tile, direction)
            if distance < shortest_distance:
                shortest_distance = distance
                best_direction = direction

        return best_direction

    def _get_neighbors_in_direction(self, tile: HexTile, direction: str):
        neighbors = self.hex_grid.get_neighbors(tile.q, tile.r)
        return [n for n, d in neighbors if d == direction or d == self._get_adjacent_direction(direction)]

    def _get_adjacent_direction(self, direction: str):
        directions = ["N", "NE", "SE", "S", "SW", "NW"]
        idx = directions.index(direction)
        return directions[(idx + 1) % 6]

    def _find_closest_edge(self, tile: HexTile):
        directions = ["N", "NE", "SE", "S", "SW", "NW"]
        closest_edge = None
        shortest_distance = float('inf')

        for direction in directions:
            distance = 0
            current_tile = tile
            while current_tile:
                distance += 1
                next_tile = self._get_neighbor_in_direction(current_tile, direction)
                if not next_tile:
                    if distance < shortest_distance:
                        shortest_distance = distance
                        closest_edge = current_tile
                    break
                current_tile = next_tile

        return closest_edge

    def _shoot_ray(self, tile: HexTile, direction: str):
        # Shoot a probabilistic ray in the given direction and return the distance to the ocean
        current_tile = tile
        distance = 0
        while current_tile.terrain_type != HexTileType.OCEAN:
            neighbors = self._get_neighbors_in_direction(current_tile, direction)
            if not neighbors:
                return float('inf')
            
            # Choose the next tile probabilistically based on elevation
            elevations = [1 / (n.elevation + 0.1) for n in neighbors]  # Add 0.1 to avoid division by zero
            total = sum(elevations)
            probabilities = [e / total for e in elevations]
            
            current_tile = random.choices(neighbors, weights=probabilities, k=1)[0]
            distance += 1

        return distance
    
    def _get_neighbor_in_direction(self, tile: HexTile, direction: str):
        # Get the neighboring tile in the given direction
        return self.hex_grid.get_neighbor(tile.q, tile.r, direction)

    def _find_lowest_neighbor(self, tile: HexTile):
        # Find the neighboring tile with the lowest elevation
        neighbors_with_direction = self.hex_grid.get_neighbors(tile.q, tile.r)
        return min(neighbors_with_direction, key=lambda t: t[0].elevation)
    
    def _all_neighbors_by_elevation(self, tile: HexTile):
        # Find the neighboring tile with the lowest elevation, sorted by distance
        # exclude rivers
        neighbors_with_direction = self.hex_grid.get_neighbors(tile.q, tile.r)
        return sorted(
            neighbors_with_direction,
            key=lambda t: t[0].elevation
        )
        
