from feudal_sim.renderer import (
    HexTile as _HexTile,
)
from feudal_sim.map.types import (
    HexTileType,
    HexResourceType,
    Color,
    hex_tile_type_to_int,
    RESOURCE_DISTRIBUTION,
    POPULATION_CAPACITY
)

class HexTile:
    """A single hexagonal map tile with terrain, ownership, and features."""

    def __init__(
        self,
        q: int,
        r: int,
        terrain_type: HexTileType,
        owner=None,
        moisture: float = 0,
        elevation: float = 0,
        temperature: float = 0,
        owner_color: Color = Color(0, 0, 0, 0)
    ):
        self.q: int = q
        self.r: int = r
        self.moisture: float = moisture
        self.elevation: float = elevation
        self.temperature: float = temperature
        self.terrain_type: HexTileType = terrain_type
        self.food_output: float = RESOURCE_DISTRIBUTION[terrain_type][HexResourceType.FOOD]
        self.material_output: float = RESOURCE_DISTRIBUTION[terrain_type][HexResourceType.MATERIAL]
        self.metal_output: float = RESOURCE_DISTRIBUTION[terrain_type][HexResourceType.METAL]
        self.population_capacity: int = POPULATION_CAPACITY[terrain_type]
        self.owner = owner

        # render
        self.owner_color: Color = owner_color

    def get_tile(self) -> _HexTile:

        # convert owner name to array of chars, using city encoding if applicable
        from feudal_sim.map.city_extensions import encode_city_for_rendering  # deferred: circular with feudal_sim.map.city_extensions
        owner_name = encode_city_for_rendering(self)
        
        # init array size 50
        owner_name_array = [" "] * 50
        for i, char in enumerate(owner_name):
            owner_name_array[i] = char
        owner_name_array[-1] = '\0'

        return _HexTile(
            self.q,
            self.r,
            hex_tile_type_to_int(self.terrain_type),
            self.elevation,
            self.moisture,
            self.temperature,
            self.food_output,
            self.material_output,
            self.metal_output,
            self.population_capacity,
            owner_name_array,
            [self.owner_color.r, self.owner_color.g, self.owner_color.b, self.owner_color.a]
        )

    def set_owner(self, owner):
        self.owner = owner

    def generate_resources(self) -> dict[HexResourceType, float]:
        return {
            HexResourceType.FOOD: self.food_output,
            HexResourceType.MATERIAL: self.material_output,
            HexResourceType.METAL: self.metal_output
        }

    def __repr__(self):
        return f"HexTile({self.q}, {self.r}, {self.terrain_type.value}, {self.population_capacity})"
