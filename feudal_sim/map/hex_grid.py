import random
import numpy as np
import math
try:
    import feudal_sim.renderer as renderer
except (ImportError, OSError):
    # Headless environments ship no renderer .so (or a foreign-arch one).
    # Debug/RL paths never touch it; constructing a RendererWrapper without
    # the module raises a clear error at that point.
    renderer = None
from feudal_sim.map.perlin import fbm2
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.map.types import (
    HexTileType,
    hex_tile_type_to_int,
)
from feudal_sim.houses.house import House
from feudal_sim.map.heightmap import Heightmap
from feudal_sim.map.rivers import RiverSystem
from feudal_sim.map.city_extensions import encode_city_for_rendering
from feudal_sim.core.event_log import EventLog
from feudal_sim.core.logger import get_logger
from feudal_sim.components.rookery import RookeryComponent
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.position import PositionComponent
from feudal_sim.components.subagent_group import SubAgentGroup
from multiprocessing import Process
import multiprocessing.shared_memory as shm

log = get_logger(__name__)

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

def get_positioned_entity_dtype():
    return np.dtype([
        ('q', np.int32),
        ('r', np.int32),
        ('name', '|S50'),
        ('house_name', '|S50'),
        ('color', np.uint8, (4,)),
        ('entity_type', np.int32),        # 0=GENERAL, 1=SCOUT, 2=ARMY, 3=MERCHANT, 4=CARAVAN
        ('assigned_soldiers', np.int32),
        ('movement_points', np.int32),
        ('max_movement', np.int32),
        ('operational_range', np.int32),
        ('morale', np.uint8),             # 0-100 general morale
        ('supplies', np.uint8),           # 0-100 general supplies
        ('equipment_level', np.uint8),    # 0-100 equipment quality
        ('orders', '|S60'),               # current mission/orders summary
    ])

class RendererWrapper:
    """Bridges the hex grid to the renderer subprocess via shared memory."""

    TILE_SHARED_MEMORY_NAME = "psm_hex_grid"
    HOUSE_SHARED_MEMORY_NAME = "psm_houses"
    ENTITIES_SHARED_MEMORY_NAME = "psm_entities"

    def __init__(self, memory_size: int, num_tiles: int, house_memory_size: int, num_houses: int, entities_memory_size: int = 0, num_entities: int = 0):
        self.shared_memory = shm.SharedMemory(name=self.TILE_SHARED_MEMORY_NAME, create=True, size=memory_size)
        self.house_shared_memory = shm.SharedMemory(name=self.HOUSE_SHARED_MEMORY_NAME, create=True, size=house_memory_size)
        
        # Initialize caches
        self.houses_cache = []
        
        # Event log shared memory
        self.event_log = EventLog()

        # Per-agent observability shared memory
        from feudal_sim.core.agent_inspector import AgentInspector
        self.agent_inspector = AgentInspector()

        # Initialize entities shared memory if specified
        self.entities_shared_memory = None
        if entities_memory_size > 0 and num_entities > 0:
            self.entities_shared_memory = shm.SharedMemory(name=self.ENTITIES_SHARED_MEMORY_NAME, create=True, size=entities_memory_size)
            self.entities_memory_size = entities_memory_size
            self.num_entities = num_entities
        else:
            self.entities_memory_size = 0
            self.num_entities = 0
            
        self.memory_size = memory_size
        self.house_memory_size = house_memory_size
        self.renderer = renderer.Renderer()
        self.num_tiles = num_tiles
        self.num_houses = num_houses

    def setup(self, tiles: list[HexTile]):
        self.renderer.setup([tile.get_tile() for tile in tiles])
        # Prime shared memory with initial tile data so the renderer subprocess
        # sees valid (q,r) values when it builds shared_tile_map at startup.
        self.update_tiles(tiles)

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
            encode_city_for_rendering(tile),
            [tile.owner_color.r, tile.owner_color.g, tile.owner_color.b, tile.owner_color.a] if tile.owner_color else [0.5, 0.5, 0.5, 0.0]
        ) for tile in tiles], dtype=get_tile_dtype())
        np_array = np.ndarray((len(tiles),), dtype=get_tile_dtype(), buffer=self.shared_memory.buf)
        np_array[:] = tile_data

    def update_houses(self, houses: list[House]):
        # Cache houses for entity color lookup
        self.houses_cache = houses

        def _house_row(house):
            rookery = house.get_component(RookeryComponent)
            ravens = len(getattr(rookery, 'outgoing_ravens', [])) if rookery else 0
            # war count from simulation war_registry if available
            war_count = 0
            try:
                ai = house.get_component(AIComponent)
                if ai and ai.context and ai.context.simulation:
                    war_count = ai.context.simulation.war_registry.enemy_count(house.id)
            except Exception as e:
                log.warning(f"hex_grid house-row war count failed: {e}")
            return (
                house.name,
                [house.color.r, house.color.g, house.color.b, house.color.a],
                house.resources['food'],
                house.resources['material'],
                house.resources['metal'],
                house.resources['gold'],
                house.population,
                house.population_loyalty,
                house.military_power,
                ravens,
                war_count,
            )

        house_data = np.array([_house_row(h) for h in houses], dtype=House.get_dtype())
        np_array = np.ndarray((len(houses),), dtype=House.get_dtype(), buffer=self.house_shared_memory.buf)
        np_array[:] = house_data

    def update_positioned_entities(self, positioned_entities: list):
        """Update positioned entities (generals, scouts, etc.) in shared memory."""
        if not self.entities_shared_memory:
            return
            
        entity_data = []
        for entity in positioned_entities:
            # Get position component
            pos_comp = entity.get_component(PositionComponent)
            if not pos_comp:
                continue
                
            # Determine entity type (map from agent type or other indicator)
            entity_type = 0  # Default to GENERAL
            if hasattr(entity, 'entity_type'):
                if entity.entity_type == 'scout':
                    entity_type = 1
                elif entity.entity_type == 'army':
                    entity_type = 2
                elif entity.entity_type == 'merchant':
                    entity_type = 3
                elif entity.entity_type == 'caravan':
                    entity_type = 4
            elif 'caravan' in entity.__class__.__name__.lower():
                # TradeCaravan class - detect by class name
                entity_type = 4
            
            # Get house color if available
            house_color = [128, 128, 128, 255]  # Default gray
            if hasattr(entity, 'house_id') or hasattr(entity, 'sender_house_id'):
                # Look up house color from the houses list
                entity_house_id = getattr(entity, 'house_id', None) or getattr(entity, 'sender_house_id', None)
                for house in self.houses_cache or []:
                    if hasattr(house, 'id') and house.id == entity_house_id:
                        try:
                            c = house.color
                            house_color = [c.r, c.g, c.b, c.a]
                        except Exception as e:
                            log.debug(f"hex_grid entity house color lookup failed: {e}")
                        break
                
            # Get military count, morale/supplies/equipment/orders if available
            military_count = getattr(entity, 'assigned_soldiers', 0)
            morale = 100
            supplies = 100
            equipment_level = 0
            orders_bytes = b''
            try:
                grp = entity.get_component(SubAgentGroup)
                if grp:
                    morale = max(0, min(100, int(grp.morale)))
                    supplies = max(0, min(100, int(grp.supplies)))
                    equipment_level = max(0, min(100, int(grp.equipment_level)))
                    mp = grp.mission_parameters
                    if mp:
                        parts = [mp.mission_type or '']
                        if mp.orders:
                            parts.append(mp.orders)
                        orders_text = ': '.join(p for p in parts if p)
                        orders_bytes = orders_text[:59].encode('utf-8')
            except Exception as e:
                log.warning(f"hex_grid entity subagent-group fields read failed: {e}")

            entity_data.append((
                pos_comp.position[0],
                pos_comp.position[1],
                entity.name[:49].encode('utf-8'),
                getattr(entity, 'house_id', '')[:49].encode('utf-8'),
                house_color,
                entity_type,
                military_count,
                pos_comp.remaining_movement,
                pos_comp.movement_points,
                pos_comp.operational_range,
                morale,
                supplies,
                equipment_level,
                orders_bytes,
            ))
        
        # Convert to numpy array and write to shared memory
        # Always create array for the full capacity, not just actual entities
        np_array = np.ndarray((self.num_entities,), dtype=get_positioned_entity_dtype(), buffer=self.entities_shared_memory.buf)
        
        if entity_data:
            entities_array = np.array(entity_data, dtype=get_positioned_entity_dtype())
            np_array[:len(entity_data)] = entities_array
            
            # Zero out remaining slots if we have fewer entities than capacity
            if len(entity_data) < self.num_entities:
                for i in range(len(entity_data), self.num_entities):
                    np_array[i] = (0, 0, b'', b'', [0, 0, 0, 0], 0, 0, 0, 0, 0, 100, 100, 0, b'')
        else:
            for i in range(self.num_entities):
                np_array[i] = (0, 0, b'', b'', [0, 0, 0, 0], 0, 0, 0, 0, 0, 100, 100, 0, b'')


    def run(self):
        if self.entities_shared_memory:
            # Pass positioned entities data to renderer
            self.renderer.run(
                f"/{self.TILE_SHARED_MEMORY_NAME}",
                self.memory_size,
                self.num_tiles,
                f"/{self.HOUSE_SHARED_MEMORY_NAME}",
                self.house_memory_size,
                self.num_houses,
                f"/{self.ENTITIES_SHARED_MEMORY_NAME}",
                self.entities_memory_size,
                self.num_entities
            )
        else:
            # Original call without positioned entities
            self.renderer.run(
                f"/{self.TILE_SHARED_MEMORY_NAME}",
                self.memory_size,
                self.num_tiles,
                f"/{self.HOUSE_SHARED_MEMORY_NAME}",
                self.house_memory_size,
                self.num_houses
            )

    def close(self):
        self.shared_memory.close()
        self.shared_memory.unlink()
        self.house_shared_memory.close()
        self.house_shared_memory.unlink()

        if self.entities_shared_memory:
            self.entities_shared_memory.close()
            self.entities_shared_memory.unlink()

        self.event_log.close()
        self.agent_inspector.close()

class HexGrid:
    """The hexagonal game map: tiles, terrain generation, and rendering."""
    def __init__(self, size: int = 80, num_houses: int = 10, debug=False, max_positioned_entities: int = 50):
        self.debug = debug
        self.size = size
        self.num_houses = num_houses
        self.max_positioned_entities = max_positioned_entities
        self.tile_map = {}
        for q in range(-size, size + 1):
            for r in range(max(-size, -q-size), min(size, -q+size) + 1):
                self.tile_map[(q, r)] = None
        self.tiles = self.create_hex_grid(size)

        if not self.debug: # only render if not in debug mode
            print("Tile dtype: ", get_tile_dtype().itemsize)
            memory_size = len(self.tiles) * get_tile_dtype().itemsize

            print("House dtype: ", House.get_dtype().itemsize)
            house_memory_size = self.num_houses * House.get_dtype().itemsize
            
            # Calculate positioned entities memory size
            print("PositionedEntity dtype: ", get_positioned_entity_dtype().itemsize)
            entities_memory_size = self.max_positioned_entities * get_positioned_entity_dtype().itemsize

            self.renderer = RendererWrapper(
                memory_size, len(self.tiles), 
                house_memory_size, self.num_houses,
                entities_memory_size, self.max_positioned_entities
            )
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

    def render(self, houses: list[House], positioned_entities: list = None):
        self.renderer.update_tiles(self.tiles)
        self.renderer.update_houses(houses)
        
        # Always update positioned entities; send empty list to clear stale slots
        self.renderer.update_positioned_entities(positioned_entities or [])

    def terminate_renderer(self):
        self.renderer_process.terminate()
        self.renderer_process.join()
        self.renderer.close()

    def get_random_noise(self, q, r, scale, octaves, persistence, lacunarity, seed):
        # Seeded Perlin fBm (feudal_sim.map.perlin) — replaces the old
        # noise.pnoise2 C extension that fails to load on Linux.
        return fbm2(q * scale, r * scale, octaves=octaves,
                    persistence=persistence, lacunarity=lacunarity, seed=seed)

    def hex_to_cartesian(self, q, r):
        """ Convert hex coordinates (q, r) to Cartesian coordinates (x, y) for use in the heightmap. """
        x = q + self.size // 2  # Offset by half the grid size to avoid negative indices
        y = r + self.size // 2
        return x, y

    def create_temperature_map(self, size: int):
        """ Creates a temperature gradient from north to south. """
        temperature_map = {}
        seed = random.randint(0, 100)
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
                # refresh_terrain re-derives outputs/capacity — re-typing
                # without it leaves stale yields from the original biome
                tile.refresh_terrain(self.determine_terrain_type(tile.elevation, tile.moisture, tile.temperature))

        from feudal_sim.core.config import config as _cfg
        river_system = RiverSystem(self, 0.00)
        self.tiles = river_system.generate_rivers(_cfg.get('simulation.world_generation.num_rivers', 4))

        # Floodplains: fresh water raises the moisture of nearby lowlands,
        # and biomes (hence food) follow — river valleys become the fertile,
        # contested corridors they were historically
        moisture_bonus = {1: _cfg.get('simulation.world_generation.floodplain_moisture_bonus', 0.25),
                          2: _cfg.get('simulation.world_generation.floodplain_moisture_bonus', 0.25) / 2}
        water_tiles = [t for t in self.tiles
                       if t.terrain_type in {HexTileType.RIVER, HexTileType.LAKE}]
        touched = {}
        for wt in water_tiles:
            for tile in self.tiles:
                d = self.hex_distance(wt.q, wt.r, tile.q, tile.r)
                # is_land() counts RIVER as land — exclude it explicitly or
                # the floodplain pass erases the rivers it flows from
                if d in moisture_bonus and self.is_land(tile) and \
                        tile.terrain_type != HexTileType.RIVER:
                    touched[(tile.q, tile.r)] = max(touched.get((tile.q, tile.r), 0.0),
                                                    moisture_bonus[d])
        for (q, r), bonus in touched.items():
            tile = self.tile_map.get((q, r))
            if tile is None:
                continue
            tile.moisture = min(1.0, tile.moisture + bonus)
            tile.refresh_terrain(self.determine_terrain_type(
                tile.elevation, tile.moisture, tile.temperature))

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
        elif direction == "SW":
            return self.get_tile(q - 1, r + 1)
        elif direction == "NW":
            return self.get_tile(q - 1, r)
        else:
            return None

    def determine_terrain_type(self, elevation, moisture, temperature):
        # Thresholds from config (world_generation.terrain_thresholds), with
        # noise added so biome edges stay organic
        from feudal_sim.core.config import config as _cfg
        th = _cfg.get('simulation.world_generation.terrain_thresholds', {})
        mountain_threshold = th.get('mountain', 0.55)
        hill_threshold = th.get('hill', 0.45)
        land_threshold = th.get('land', 0.05)

        moisture_noise = min(1.0, max(0.0, self.get_random_noise(moisture, moisture, scale=4.0, octaves=12, persistence=0.8, lacunarity=2.0, seed=100)))
        forest_threshold = th.get('forest_base', 0.65) + moisture_noise
        grassland_threshold = th.get('grassland', 0.3)
        desert_threshold = th.get('desert', 0.55)

        # add noise to thresholds
        temperature_noise = self.get_random_noise(temperature, temperature, scale=2, octaves=4, persistence=0.8, lacunarity=2.0, seed=100)
        cold_threshold = th.get('cold_base', 0.4) + temperature_noise
        warm_threshold = th.get('warm_base', 0.65) + temperature_noise

        if elevation > mountain_threshold:
            # Frozen peaks in the far cold
            if temperature < th.get('ice_temp', 0.15):
                return HexTileType.ICE_CAP
            return HexTileType.MOUNTAIN
        elif elevation > hill_threshold:
            return HexTileType.HILL
        elif elevation > land_threshold:
            # Waterlogged lowlands become swamp (any non-frozen climate)
            if elevation < th.get('swamp_elevation', 0.15) and \
                    moisture > th.get('swamp_moisture', 0.75) and \
                    temperature > cold_threshold:
                return HexTileType.SWAMP
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
