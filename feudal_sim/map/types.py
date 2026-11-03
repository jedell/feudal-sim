from enum import Enum
from typing import Dict
try:
    from feudal_sim.renderer import (
        HexTileType as _HexTileType,
        HexResourceType as _HexResourceType,
    )
except ModuleNotFoundError:
    # Headless build (FEUDAL_SIM_NO_RENDERER=1): the pybind enums are only
    # needed by the render-bridge converters below, which headless RL/CI
    # paths never call.
    _HexTileType = None
    _HexResourceType = None

class Color:
    """An RGBA color."""
    def __init__(self, r: int, g: int, b: int, a: int):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

class HexTileType(Enum):
    """Terrain type of a hex tile."""
    GRASSLAND = "grassland"
    TUNDRA = "tundra"
    RIVER = "river"
    LAKE = "lake"
    OCEAN = "ocean"
    MOUNTAIN = "mountain"
    HILL = "hill"
    DESERT = "desert"
    TEMPERATE_FOREST = "temperate_forest"
    SWAMP = "swamp"
    BOREAL_FOREST = "boreal_forest"
    STEPPE = "steppe"
    RAINFOREST = "rainforest"
    ICE_CAP = "ice_cap"

class HexResourceType(Enum):
    """Primary resource a hex tile yields."""
    NONE = "none"
    FOOD = "food"
    MATERIAL = "material"
    METAL = "metal"
    GOLD = "gold"

def hex_tile_type_to_int(hex_tile_type: HexTileType):
    if _HexTileType is None:
        raise RuntimeError("renderer module unavailable (headless build)")
    return {
        HexTileType.GRASSLAND: _HexTileType.GRASSLAND,
        HexTileType.TUNDRA: _HexTileType.TUNDRA,
        HexTileType.RIVER: _HexTileType.RIVER,
        HexTileType.LAKE: _HexTileType.LAKE,
        HexTileType.OCEAN: _HexTileType.OCEAN,
        HexTileType.MOUNTAIN: _HexTileType.MOUNTAIN,
        HexTileType.HILL: _HexTileType.HILL,
        HexTileType.DESERT: _HexTileType.DESERT,
        HexTileType.TEMPERATE_FOREST: _HexTileType.TEMPERATE_FOREST,
        HexTileType.SWAMP: _HexTileType.SWAMP,
        HexTileType.BOREAL_FOREST: _HexTileType.BOREAL_FOREST,
        HexTileType.STEPPE: _HexTileType.STEPPE,
        HexTileType.RAINFOREST: _HexTileType.RAINFOREST,
        HexTileType.ICE_CAP: _HexTileType.ICE_CAP
    }[hex_tile_type]

def hex_resource_type_to_int(hex_resource_type: HexResourceType):
    if _HexResourceType is None:
        raise RuntimeError("renderer module unavailable (headless build)")
    return {
        HexResourceType.NONE: _HexResourceType.NONE,
        HexResourceType.FOOD: _HexResourceType.FOOD,
        HexResourceType.MATERIAL: _HexResourceType.MATERIAL,
        HexResourceType.METAL: _HexResourceType.METAL,
        HexResourceType.GOLD: _HexResourceType.GOLD
    }[hex_resource_type]

RESOURCE_DISTRIBUTION: Dict[HexTileType, Dict[HexResourceType, float]] = {
    HexTileType.GRASSLAND: {
        HexResourceType.FOOD: 0.7,
        HexResourceType.MATERIAL: 0.2,
        HexResourceType.METAL: 0.1
    },
    HexTileType.TUNDRA: {
        HexResourceType.FOOD: 0.1,
        HexResourceType.MATERIAL: 0.3,
        HexResourceType.METAL: 0.6
    },
    HexTileType.RIVER: {
        HexResourceType.FOOD: 0.4,
        HexResourceType.MATERIAL: 0.3,
        HexResourceType.METAL: 0.3
    },
    HexTileType.LAKE: {
        HexResourceType.FOOD: 0.4,
        HexResourceType.MATERIAL: 0.2,
        HexResourceType.METAL: 0.3
    },
    HexTileType.OCEAN: {
        HexResourceType.FOOD: 0.0,
        HexResourceType.MATERIAL: 0.0,
        HexResourceType.METAL: 0.0
    },
    HexTileType.MOUNTAIN: {
        HexResourceType.FOOD: 0.1,
        HexResourceType.MATERIAL: 0.2,
        HexResourceType.METAL: 0.7
    },
    HexTileType.HILL: {
        HexResourceType.FOOD: 0.3,
        HexResourceType.MATERIAL: 0.4,
        HexResourceType.METAL: 0.3
    },
    HexTileType.DESERT: {
        HexResourceType.FOOD: 0.2,
        HexResourceType.MATERIAL: 0.2,
        HexResourceType.METAL: 0.6
    },
    HexTileType.TEMPERATE_FOREST: {
        HexResourceType.FOOD: 0.3,
        HexResourceType.MATERIAL: 0.6,
        HexResourceType.METAL: 0.1
    },
    HexTileType.SWAMP: {
        HexResourceType.FOOD: 0.2,
        HexResourceType.MATERIAL: 0.5,
        HexResourceType.METAL: 0.3
    },
    HexTileType.BOREAL_FOREST: {
        HexResourceType.FOOD: 0.1,
        HexResourceType.MATERIAL: 0.7,
        HexResourceType.METAL: 0.2
    },
    HexTileType.STEPPE: {
        HexResourceType.FOOD: 0.6,
        HexResourceType.MATERIAL: 0.1,
        HexResourceType.METAL: 0.3
    },
    HexTileType.RAINFOREST: {
        HexResourceType.FOOD: 0.2,
        HexResourceType.MATERIAL: 0.6,
        HexResourceType.METAL: 0.2
    },
    HexTileType.ICE_CAP: {
        HexResourceType.FOOD: 0.1,
        HexResourceType.MATERIAL: 0.1,
        HexResourceType.METAL: 0.8
    }
}

POPULATION_CAPACITY: Dict[HexTileType, int] = {
    HexTileType.OCEAN: 0,
    HexTileType.RIVER: 0,
    HexTileType.LAKE: 0,
    HexTileType.GRASSLAND: 100,
    HexTileType.MOUNTAIN: 50,
    HexTileType.HILL: 60,
    HexTileType.DESERT: 40,
    HexTileType.TEMPERATE_FOREST: 90,
    HexTileType.SWAMP: 40,
    HexTileType.BOREAL_FOREST: 60,
    HexTileType.STEPPE: 75,
    HexTileType.RAINFOREST: 75,
    HexTileType.TUNDRA: 60,
    HexTileType.ICE_CAP: 10
}
