"""
City Extensions - Encode city information into existing tile fields.

Uses the extensible shared memory approach by encoding city data into the
population_capacity field of tiles, similar to how resource nodes use metal_output.
"""

from enum import Enum
from typing import Optional, Tuple
from feudal_sim.map.hex_tile import HexTile


class CityType(Enum):
    """City types that can be placed on tiles."""
    NONE = 0
    CAPITAL = 1
    TRADE = 2
    MILITARY = 3
    AGRICULTURAL = 4
    OUTPOST = 5




def set_city_on_tile(tile: HexTile, city_type: CityType, development_level: int = 1, house_id: int = 0, city_name: str = None) -> None:
    """
    Encode city information into a tile's population_capacity field.
    
    Note: This function no longer modifies the owner field directly.
    City name encoding is handled during tile serialization to shared memory.
    
    Encoding scheme: 
    - Normal range: 0-999 (original population capacity)
    - Extended range: 1000+ for city data
    - Format: 1000 + (city_type * 100) + (development_level * 10) + house_id
    - Original capacity preserved as decimal portion
    
    Args:
        tile: The tile to place the city on
        city_type: Type of city (capital, trade, military, agricultural)
        development_level: City development level (1-4)
        house_id: ID of the owning house (0-9)
        city_name: Name of the city (optional)
    """
    if city_type == CityType.NONE:
        # Remove city - restore original population capacity
        if tile.population_capacity > 1000:
            original = get_base_population_capacity(tile)
            tile.population_capacity = original
        # Remove city name from tile if it was stored
        if hasattr(tile, '_city_name'):
            delattr(tile, '_city_name')
    else:
        # Encode city data
        # Preserve original capacity (or use sensible default)
        original = get_base_population_capacity(tile)
        if original == 0:
            original = 50  # Default capacity for city tiles
        
        # Encode: 1000 + (type * 100) + (level * 10) + house_id
        encoded_base = 1000 + (city_type.value * 100) + (development_level * 10) + house_id
        
        # Store original as decimal portion (scaled down to fit)
        tile.population_capacity = encoded_base + (original / 10000.0)
        
        # Store city name directly on the tile object (not in owner field)
        if city_name:
            tile._city_name = city_name


def get_city_info(tile: HexTile) -> Tuple[CityType, int, int]:
    """
    Decode city information from a tile's population_capacity field.
    
    Args:
        tile: The tile to check
        
    Returns:
        Tuple of (city_type, development_level, house_id)
    """
    if tile.population_capacity < 1000:
        return (CityType.NONE, 0, 0)
    
    # Decode the encoded portion
    encoded = int(tile.population_capacity) - 1000
    
    city_type_value = (encoded // 100) % 10
    development_level = (encoded // 10) % 10  
    house_id = encoded % 10
    
    try:
        city_type = CityType(city_type_value)
    except ValueError:
        city_type = CityType.NONE
    
    return (city_type, development_level, house_id)


def get_city_name(tile: HexTile) -> Optional[str]:
    """
    Extract city name from the tile.
    
    Args:
        tile: The tile to check
        
    Returns:
        City name if found, None otherwise
    """
    # First check if city name is stored directly on the tile
    if hasattr(tile, '_city_name'):
        return tile._city_name
    
    # Fallback: check if it's encoded in owner field (for backward compatibility)
    if not hasattr(tile, 'owner') or not tile.owner:
        return None
    
    owner_name = tile.owner.name if hasattr(tile.owner, 'name') else str(tile.owner)
    
    if owner_name.startswith("CITY:"):
        # Extract city name from "CITY:{city_name}#{house_name}" format
        parts = owner_name.split("#")
        if len(parts) > 0:
            city_part = parts[0]
            # Remove "CITY:" prefix
            if city_part.startswith("CITY:"):
                return city_part[5:]  # Remove "CITY:" prefix
    
    return None


def get_city_owner(tile: HexTile) -> Optional[str]:
    """
    Extract the original owner name, handling city encoding properly.
    
    Args:
        tile: The tile to check
        
    Returns:
        Original owner name if found, None otherwise
    """
    if not hasattr(tile, 'owner') or not tile.owner:
        return None
    
    owner_name = tile.owner.name if hasattr(tile.owner, 'name') else str(tile.owner)
    
    # If it's city-encoded in the owner field, extract the original owner
    if owner_name.startswith("CITY:"):
        # Extract original owner from "CITY:{city_name}#{house_name}" format
        parts = owner_name.split("#")
        if len(parts) > 1:
            return parts[1]
    
    # Otherwise return the owner name as-is
    return owner_name


def get_full_city_info(tile: HexTile) -> Tuple[CityType, int, int, Optional[str], Optional[str]]:
    """
    Get complete city information including city name and owner.
    
    Args:
        tile: The tile to check
        
    Returns:
        Tuple of (city_type, development_level, house_id, city_name, owner_name)
    """
    city_type, development_level, house_id = get_city_info(tile)
    city_name = get_city_name(tile)
    owner_name = get_city_owner(tile)
    
    return (city_type, development_level, house_id, city_name, owner_name)


def format_city_display(tile: HexTile) -> str:
    """
    Format city information for display (e.g., in hover tooltips).
    
    Args:
        tile: The tile to format
        
    Returns:
        Formatted string with city information
    """
    city_type, development_level, house_id, city_name, owner_name = get_full_city_info(tile)
    
    if city_type == CityType.NONE:
        return ""
    
    type_name = get_city_type_name(city_type)
    dev_name = get_city_development_name(development_level)
    
    display_parts = []
    
    # Add city name if available
    if city_name:
        display_parts.append(f"{city_name}")
    
    # Add type and development
    display_parts.append(f"{type_name} ({dev_name})")
    
    # Add owner if available
    if owner_name and owner_name != "None":
        display_parts.append(f"Owned by {owner_name}")
    
    return " - ".join(display_parts)


def get_base_population_capacity(tile: HexTile) -> int:
    """
    Get the original population capacity excluding city encoding.
    
    Args:
        tile: The tile to check
        
    Returns:
        Original population capacity
    """
    if tile.population_capacity < 1000:
        return int(tile.population_capacity)
    
    # Extract original capacity from decimal portion
    decimal_portion = tile.population_capacity - int(tile.population_capacity)
    return int(decimal_portion * 10000)


def has_city(tile: HexTile) -> bool:
    """Check if a tile has a city on it."""
    city_type, _, _ = get_city_info(tile)
    return city_type != CityType.NONE


def get_city_type_name(city_type: CityType) -> str:
    """Get human-readable name for city type."""
    names = {
        CityType.NONE: "None",
        CityType.CAPITAL: "Capital",
        CityType.TRADE: "Trade City",
        CityType.MILITARY: "Military Fortress", 
        CityType.AGRICULTURAL: "Agricultural Center",
        CityType.OUTPOST: "Outpost"
    }
    return names.get(city_type, "Unknown")


# Convenience functions for each city type
def add_capital(tile: HexTile, house_id: int = 0, development_level: int = 1, city_name: str = None) -> None:
    """Add a capital city to a tile."""
    set_city_on_tile(tile, CityType.CAPITAL, development_level, house_id, city_name)


def add_trade_city(tile: HexTile, house_id: int = 0, development_level: int = 1, city_name: str = None) -> None:
    """Add a trade city to a tile."""
    set_city_on_tile(tile, CityType.TRADE, development_level, house_id, city_name)


def add_military_city(tile: HexTile, house_id: int = 0, development_level: int = 1, city_name: str = None) -> None:
    """Add a military fortress to a tile."""
    set_city_on_tile(tile, CityType.MILITARY, development_level, house_id, city_name)


def add_agricultural_city(tile: HexTile, house_id: int = 0, development_level: int = 1, city_name: str = None) -> None:
    """Add an agricultural center to a tile."""
    set_city_on_tile(tile, CityType.AGRICULTURAL, development_level, house_id, city_name)


def remove_city(tile: HexTile) -> None:
    """Remove any city from a tile."""
    set_city_on_tile(tile, CityType.NONE)


def upgrade_city(tile: HexTile) -> bool:
    """
    Upgrade a city's development level.
    
    Args:
        tile: The tile with the city to upgrade
        
    Returns:
        True if city was upgraded, False if at max level or no city
    """
    city_type, development_level, house_id, city_name, _ = get_full_city_info(tile)
    
    if city_type == CityType.NONE or development_level >= 4:
        return False
    
    set_city_on_tile(tile, city_type, development_level + 1, house_id, city_name)
    return True


def get_city_development_name(level: int) -> str:
    """Get human-readable name for development level."""
    names = {1: "Village", 2: "Town", 3: "City", 4: "Metropolis"}
    return names.get(level, "Unknown")


def create_house_id_mapping(houses) -> dict:
    """
    Create a mapping from house names to house IDs for encoding.
    
    Args:
        houses: List of house entities
        
    Returns:
        Dictionary mapping house name to ID (0-9)
    """
    mapping = {}
    for i, house in enumerate(houses[:10]):  # Limit to 10 houses for encoding
        mapping[house.get_name()] = i
    return mapping


def encode_city_for_rendering(tile: HexTile) -> str:
    """
    Create the encoded owner string for rendering, only if this tile has a city.
    This should be called when preparing tile data for shared memory.
    
    Args:
        tile: The tile to encode
        
    Returns:
        Encoded owner string if city exists, original owner name otherwise
    """
    # Check for pending outpost construction
    if getattr(tile, '_pending_outpost', False):
        owner_name = (tile.owner.name
                      if (hasattr(tile, 'owner') and tile.owner and hasattr(tile.owner, 'name'))
                      else "None")
        return f"PENDING:outpost#{owner_name}"

    # Only encode if this tile actually has a city
    city_type, _, _ = get_city_info(tile)
    if city_type == CityType.NONE:
        # No city, return normal owner name
        return tile.owner.name if (hasattr(tile, 'owner') and tile.owner and hasattr(tile.owner, 'name')) else "None"
    
    # Has city, create encoded string
    city_name = get_city_name(tile)
    if city_name and hasattr(tile, 'owner') and tile.owner:
        original_owner = tile.owner.name if hasattr(tile.owner, 'name') else str(tile.owner)
        return f"CITY:{city_name}#{original_owner}"
    
    # Fallback to normal owner name
    return tile.owner.name if (hasattr(tile, 'owner') and tile.owner and hasattr(tile.owner, 'name')) else "None"


