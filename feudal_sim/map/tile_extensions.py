"""
Simple extensibility helpers for tile properties.
Shows how to add new features without modifying core structs.
"""

from enum import Enum
from feudal_sim.map.hex_tile import HexTile


class ResourceNodeType(Enum):
    NONE = 0
    GOLD_MINE = 1 
    IRON_DEPOSIT = 2
    STONE_QUARRY = 3
    RARE_HERBS = 4


def get_resource_node_type(tile: HexTile) -> ResourceNodeType:
    """
    Extract resource node type from existing tile data.
    Uses metal_output field as indicator (values > 100 indicate special resources).
    """
    if tile.metal_output > 100:
        # Decode the resource type from the value
        resource_code = int(tile.metal_output) - 100
        try:
            return ResourceNodeType(resource_code)
        except ValueError:
            return ResourceNodeType.NONE
    return ResourceNodeType.NONE


def set_resource_node(tile: HexTile, node_type: ResourceNodeType) -> None:
    """
    Set a resource node on a tile using existing field.
    Preserves original metal output while encoding the resource type.
    """
    if node_type == ResourceNodeType.NONE:
        # Keep original metal output if any
        if tile.metal_output > 100:
            tile.metal_output = tile.metal_output % 100
    else:
        # Encode resource type (100 + type value)
        original_output = tile.metal_output % 100 if tile.metal_output > 100 else tile.metal_output
        tile.metal_output = 100 + node_type.value + (original_output / 100)


def get_base_metal_output(tile: HexTile) -> float:
    """Get the actual metal output, excluding resource node encoding."""
    if tile.metal_output > 100:
        return tile.metal_output % 100
    return tile.metal_output


def has_special_resource(tile: HexTile) -> bool:
    """Quick check if tile has any special resource node."""
    return get_resource_node_type(tile) != ResourceNodeType.NONE


# Example usage functions
def add_gold_mine(tile: HexTile) -> None:
    """Add a gold mine to this tile."""
    set_resource_node(tile, ResourceNodeType.GOLD_MINE)


def add_iron_deposit(tile: HexTile) -> None:
    """Add an iron deposit to this tile.""" 
    set_resource_node(tile, ResourceNodeType.IRON_DEPOSIT)


def get_resource_description(tile: HexTile) -> str:
    """Get human-readable description of tile's special resources."""
    node_type = get_resource_node_type(tile)
    if node_type == ResourceNodeType.NONE:
        return "No special resources"
    elif node_type == ResourceNodeType.GOLD_MINE:
        return "Gold Mine"
    elif node_type == ResourceNodeType.IRON_DEPOSIT:
        return "Iron Deposit" 
    elif node_type == ResourceNodeType.STONE_QUARRY:
        return "Stone Quarry"
    elif node_type == ResourceNodeType.RARE_HERBS:
        return "Rare Herbs"
    else:
        return f"Unknown Resource ({node_type.value})"