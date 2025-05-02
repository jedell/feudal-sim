import random
import numpy as np
import math
import feudal_sim.renderer as renderer
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.map.types import (
    HexTileType,
    hex_tile_type_to_int,
)
from feudal_sim.houses.house import House
from feudal_sim.map.heightmap import Heightmap
from feudal_sim.map.rivers import RiverSystem
from multiprocessing import Process
import noise
import multiprocessing.shared_memory as shm

def get_tile_dtype():
    return np.dtype([
        ('q', np.int32),
        ('r', np.int32),
        ('terrain_type', np.int32),
        ('elevation', np.float32),
        ('moisture', np.float32),
        ('temperature', np.float32),
        ('food_output', np.float32),
        ('material_output', np.float32),
        ('metal_output', np.float32),
        ('population_capacity', np.int32),
        ('owner', '|S50'),
        ('owner_color', np.uint8, (4,))
    ])

class RendererWrapper:

    TILE_SHARED_MEMORY_NAME = "psm_hex_grid"
    HOUSE_SHARED_MEMORY_NAME = "psm_houses"

    def __init__(self, memory_size: int, num_tiles: int, house_memory_size: int, num_houses: int):
        self.shared_memory = shm.SharedMemory(name=self.TILE_SHARED_MEMORY_NAME, create=True, size=memory_size)
        self.house_shared_memory = shm.SharedMemory(name=self.HOUSE_SHARED_MEMORY_NAME, create=True, size=house_memory_size)
        self.memory_size = memory_size
        self.house_memory_size = house_memory_size
        self.renderer = renderer.Renderer()
        self.num_tiles = num_tiles
        self.num_houses = num_houses

    def setup(self, tiles: list[HexTile]):
        self.renderer.setup([tile.get_tile() for tile in tiles])

    def update_tiles(self, tiles: list[HexTile]):
        tile_data = np.array([(
            tile.q,
            tile.r,
            hex_tile_type_to_int(tile.terrain_type),
            tile.elevation,
            tile.moisture,
            tile.temperature,
            tile.food_output,
            tile.material_output,
            tile.metal_output,
            tile.population_capacity,
            tile.owner.name if tile.owner else "None",
            [tile.owner_color.r, tile.owner_color.g, tile.owner_color.b, tile.owner_color.a]
        ) for tile in tiles], dtype=get_tile_dtype())
        np_array = np.ndarray((len(tiles),), dtype=get_tile_dtype(), buffer=self.shared_memory.buf)
        np_array[:] = tile_data

    def update_houses(self, houses: list[House]):
        house_data = np.array([(
            house.name,
            [house.color.r, house.color.g, house.color.b, house.color.a],
            house.resources['food'],
            house.resources['material'],
            house.resources['metal'],
            house.population,
            house.military_power
        ) for house in houses], dtype=House.get_dtype())
        np_array = np.ndarray((len(houses),), dtype=House.get_dtype(), buffer=self.house_shared_memory.buf)
        np_array[:] = house_data

    def run(self):
        self.renderer.run(
            f"/{self.TILE_SHARED_MEMORY_NAME}",
            self.memory_size,
            self.num_tiles,
            f"/{self.HOUSE_SHARED_MEMORY_NAME}",
            self.house_memory_size,
            self.num_houses,
        )

    def close(self):
        self.shared_memory.close()
        self.shared_memory.unlink()

class HexGrid:
    def __init__(self, size: int = 80, num_houses: int = 10):
        self.size = size
        self.num_houses = num_houses
        self.tile_map = {}
        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                self.tile_map[(q, r)] = None
        self.tiles = self.create_hex_grid(size)

        print("Tile dtype: ", get_tile_dtype().itemsize)
        memory_size = len(self.tiles) * get_tile_dtype().itemsize

        print("House dtype: ", House.get_dtype().itemsize)
        house_memory_size = self.num_houses * House.get_dtype().itemsize

        self.renderer = RendererWrapper(memory_size, len(self.tiles), house_memory_size, self.num_houses)
        self.renderer.setup(self.tiles)
        self.renderer_process = Process(target=self.renderer.run)
        self.renderer_process.start()

    # function to change tile attributes
    def update_tile_attribute(self, tile: HexTile, attribute: str, value):
        tile.__setattr__(attribute, value)

    def update_tile(self, tile: HexTile):
        self.tile_map[(tile.q, tile.r)] = tile
        self.tiles[self.tiles.index(tile)] = tile

    def update_tiles(self, tiles: list[HexTile]):
        for tile in tiles:
            self.update_tile(tile)

    def render(self, houses: list[House]):
        self.renderer.update_tiles(self.tiles)
        self.renderer.update_houses(houses)

    def terminate_renderer(self):
        self.renderer_process.terminate()
        self.renderer_process.join()
        self.renderer.close()

    def get_random_noise(self, q, r, scale, octaves, persistence, lacunarity, seed):
        return noise.pnoise2(q * scale, r * scale, octaves=octaves, persistence=persistence, lacunarity=lacunarity, repeatx=1024, repeaty=1024, base=seed)

    def hex_to_cartesian(self, q, r):
        """ Convert hex coordinates (q, r) to Cartesian coordinates (x, y) for use in the heightmap. """
        x = q + self.size // 2  # Offset by half the grid size to avoid negative indices
        y = r + self.size // 2
        return x, y

    def create_temperature_map(self, size: int):
        """ Creates a temperature gradient from north to south. """
        temperature_map = {}
        seed = random.randint(0, 100)
        max_distance = np.sqrt(3 * (size // 2) ** 2)
        noise_scale = 3.0
        noise_intensity = 0.2

        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                latitude_factor = (r / size)  # Latitude effect; more northern areas have colder temperatures
                noise_value = self.get_random_noise(q/size + 100, r/size + 100, scale=noise_scale, octaves=4, persistence=0.5, lacunarity=12.0, seed=seed)
                noise_value = (noise_value) * noise_intensity
                temperature = latitude_factor + noise_value
                temperature_map[(q, r)] = temperature

        # normalize temperature map
        min_temp = min(temperature_map.values())
        max_temp = max(temperature_map.values())
        for (q, r), temperature in temperature_map.items():
            temperature_map[(q, r)] = (temperature - min_temp) / (max_temp - min_temp)

        return temperature_map

    def create_elevation_map(self, size: int):
        elevation_map = {}
        # Instantiate heightmap
        heightmap_params = {'size': size * 2, 'roughness': 3, 'sea_percent': 30, 'height_range': (0, 255), 'sea_level': 0.1}
        heightmap = Heightmap(heightmap_params)

        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                x, y = self.hex_to_cartesian(q, r)
                # Get the height from the heightmap (assuming some normalization)
                elevation = heightmap.height_at(x, y)

                # Store the elevation in the map
                elevation_map[(q, r)] = elevation

        elevation_map = self.apply_radial_falloff(elevation_map, size)

        return elevation_map

    def apply_radial_falloff(self, elevation_map, size, falloff_power=0.25):
        """ Applies a radial falloff to create a continent shape, with ocean at the edges. """
        center_x, center_y = 0, 0
        # max radial distance
        max_distance = np.sqrt(3 * (size // 2) ** 2)
        noise_scale = 4
        noise_intensity = 0.8
        seed = random.randint(0, 100)

        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                distance = self.hex_distance(q, r, center_x, center_y) / max_distance
                if 1.0 - distance > 0:
                    falloff = math.pow(1.0 - distance, falloff_power)
                else:
                    falloff = 0.0
                noise = self.get_random_noise(q/size + 100, r/size + 100, scale=noise_scale, octaves=5, persistence=0.5, lacunarity=2.0, seed=seed)
                noise = (noise - 0.5) * noise_intensity
                falloff += noise
                falloff = falloff
                elevation_map[(q, r)] *= falloff

        return elevation_map

    def generate_moisture_map(self, size):
        moisture_map = {}
        seed = random.randint(0, 100)
        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                moisture = self.get_random_noise(q/size + 100, r/size + 100, scale=2.0, octaves=4, persistence=0.5, lacunarity=2.0, seed=seed)
                moisture_map[(q, r)] = moisture

        min_moisture = min(moisture_map.values())
        max_moisture = max(moisture_map.values())
        for (q, r), moisture in moisture_map.items():
            moisture_map[(q, r)] = (moisture - min_moisture) / (max_moisture - min_moisture)
            # moisture_map[(q, r)] = 0.4
        return moisture_map

    def is_land(self, tile):
        return (
            tile.terrain_type != HexTileType.OCEAN
            and tile.terrain_type != HexTileType.LAKE
            and tile.terrain_type != HexTileType.SWAMP
            and tile.terrain_type != HexTileType.ICE_CAP
        )

    def set_ocean(self, tile):
        # flood fill algorithm to set all adjacent tiles to ocean if they are not land
        visited = set()
        stack = [tile]

        while stack:
            current_tile = stack.pop()
            if current_tile in visited or self.is_land(current_tile):
                continue

            visited.add(current_tile)
            current_tile.terrain_type = HexTileType.OCEAN

            neighbors = self.get_neighbors(current_tile.q, current_tile.r)
            for neighbor, _ in neighbors:
                if neighbor not in visited and not self.is_land(neighbor):
                    stack.append(neighbor)

    def create_hex_grid(self, size: int):
        tiles = []
        elevation_map = self.create_elevation_map(size)
        moisture_map = self.generate_moisture_map(size)
        temperature_map = self.create_temperature_map(size)

        for (q, r), elevation in elevation_map.items():
            moisture = moisture_map[(q, r)]
            temperature = temperature_map[(q, r)]
            terrain_type = self.determine_terrain_type(elevation, moisture, temperature)
            self.tile_map[(q, r)] = HexTile(
                q,
                r,
                terrain_type,
                elevation=elevation,
                moisture=moisture,
                temperature=temperature,
            )
            tiles.append(self.tile_map[(q, r)])

        self.tiles = tiles
        for tile in tiles:
            self.tile_map[(tile.q, tile.r)] = tile

        start_tile = self.tiles[0]
        self.set_ocean(start_tile)

        # if tile is land, apply some more elevation noise
        elevation_seed = random.randint(0, 100)                     
        for tile in tiles:
            if self.is_land(tile):
                tile.elevation += max(0.0, self.get_random_noise(tile.q/size + 100, tile.r/size + 100, scale=6, octaves=8, persistence=0.5, lacunarity=2.0, seed=elevation_seed))
                tile.elevation = min(1.0, tile.elevation)
                tile.terrain_type = self.determine_terrain_type(tile.elevation, tile.moisture, tile.temperature)

        river_system = RiverSystem(self, 0.00)
        self.tiles = river_system.generate_rivers(4)

        return tiles

    def hex_distance(self, q1, r1, q2, r2):
        x1, y1, z1 = q1, -q1-r1, r1
        x2, y2, z2 = q2, -q2-r2, r2
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))

    def get_tile(self, q: int, r: int):
        return self.tile_map.get((q, r), None)

    def get_neighbors(self, q: int, r: int) -> list[tuple[HexTile, str]]:
        neighbors = []
        directions = ["N", "NE", "SE", "S", "SW", "NW"]
        for (q_offset, r_offset), direction in zip(
            [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)],
            directions
        ):
            if (q + q_offset, r + r_offset) in self.tile_map:
                neighbor = self.get_tile(q + q_offset, r + r_offset)
                neighbors.append((neighbor, direction))
        return neighbors
    
    def get_neighbor(self, q: int, r: int, direction: str):
        if direction == "N":
            return self.get_tile(q, r - 1)
        elif direction == "NE":
            return self.get_tile(q + 1, r - 1)
        elif direction == "SE":
            return self.get_tile(q + 1, r)
        elif direction == "S":
            return self.get_tile(q, r + 1)

    def determine_terrain_type(self, elevation, moisture, temperature):
        # Add noise to thresholds
        mountain_threshold = 0.55
        hill_threshold = 0.45
        land_threshold = 0.05

        moisture_noise = min(1.0, max(0.0, self.get_random_noise(moisture, moisture, scale=4.0, octaves=12, persistence=0.8, lacunarity=2.0, seed=100)))
        forest_threshold = 0.65 + moisture_noise
        grassland_threshold = 0.3
        desert_threshold = 0.55

        # add noise to thresholds
        temperature_noise = self.get_random_noise(temperature, temperature, scale=2, octaves=4, persistence=0.8, lacunarity=2.0, seed=100)
        cold_threshold = 0.4 + temperature_noise
        warm_threshold = 0.65 + temperature_noise

        if elevation > mountain_threshold:
            return HexTileType.MOUNTAIN
        elif elevation > hill_threshold:
            return HexTileType.HILL
        elif elevation > land_threshold:
            if temperature < cold_threshold:
                if moisture > forest_threshold:
                    return HexTileType.BOREAL_FOREST
                else:
                    return HexTileType.TUNDRA
            elif temperature < warm_threshold:
                if moisture > forest_threshold:
                    return HexTileType.TEMPERATE_FOREST
                elif moisture > grassland_threshold:
                    return HexTileType.GRASSLAND
                else:
                    return HexTileType.STEPPE
            else:
                if moisture > forest_threshold:
                    return HexTileType.RAINFOREST
                elif moisture > desert_threshold:
                    return HexTileType.STEPPE
                else:
                    return HexTileType.DESERT
        else:
            return HexTileType.LAKE

    def get_tile_by_coords(self, tiles, q, r):
        for tile in tiles:
            if tile.q == q and tile.r == r:
                return tile
        return None

    def get_tiles_in_range(self, q: int, r: int, range: int):
        tiles = []
        for q_offset in range(-range, range + 1):
            for r_offset in range(-range, range + 1):
                tiles.append(self.get_tile(q + q_offset, r + r_offset))
        return tiles
    
    def get_random_tile(self, n: int) -> list[HexTile]:
        indices = random.sample(list(range(len(self.tiles))), n)
        return [self.tiles[i] for i in indices]
