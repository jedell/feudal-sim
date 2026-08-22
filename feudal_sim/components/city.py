"""
CityComponent - City management and urban development for entities.

Manages cities as strategic centers that boost population, taxation, and 
territorial control. Each city has a specific position on the map and 
provides various bonuses to the controlling house.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType


MAX_TIER = 5


def get_tier(level: int) -> dict:
    """Tier definition (name, cost, bonuses) for a development level."""
    from feudal_sim.core.config import config
    try:
        return config.get(f'simulation.settlements.tiers.{level}', {}) or {}
    except KeyError:
        return {}


def tier_name(level: int) -> str:
    """Display name for a development level (Outpost ... City)."""
    return get_tier(level).get('name', f"Tier {level}")


@dataclass
class City:
    """Represents a city with position and development."""
    name: str
    position: Tuple[int, int]  # (q, r) hex coordinates
    city_type: str = "capital"  # capital, trade, military, agricultural
    development_level: int = 1  # settlement tier: 1=Outpost ... 5=City
    population_bonus: float = 1.5  # Multiplier for population capacity
    tax_efficiency: float = 1.3  # Multiplier for tax collection
    founded_turn: int = 1


class CityComponent(Component):
    """
    Manages cities for a house entity.
    
    Features:
    - City positioning on hex map
    - Population capacity bonuses
    - Tax collection efficiency
    - City development and growth
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Cities controlled by this entity
        self.cities: Dict[str, City] = {}
        
        # City development costs and bonuses
        self.development_costs = {
            2: {"material": 50, "gold": 30},  # village -> town
            3: {"material": 100, "gold": 80},  # town -> city  
            4: {"material": 200, "gold": 150}  # city -> metropolis
        }
    
    def add_city(self, name: str, position: Tuple[int, int], city_type: str = "capital",
                 founded_turn: int = 1, development_level: int = 1) -> bool:
        """
        Add a new city to this entity.

        Args:
            name: Name of the city
            position: (q, r) hex coordinates
            city_type: Type of city (capital, trade, military, agricultural)
            founded_turn: Turn when city was founded
            development_level: Starting tier (1=Outpost ... 5=City)

        Returns:
            True if city was added successfully
        """
        if name in self.cities:
            return False

        # Set bonuses based on city type
        bonuses = self._get_city_type_bonuses(city_type)

        city = City(
            name=name,
            position=position,
            city_type=city_type,
            development_level=development_level,
            population_bonus=max(bonuses["population_bonus"],
                                 get_tier(development_level).get('population_bonus', 0)),
            tax_efficiency=bonuses["tax_efficiency"],
            founded_turn=founded_turn
        )
        
        self.cities[name] = city
        
        # Emit city founded event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='city_founded',
                entity_name=self.entity.name if self.entity else self.entity_id,
                city_name=name,
                city_type=city_type,
                position=position
            )
        
        return True
    
    def _get_city_type_bonuses(self, city_type: str) -> Dict[str, float]:
        """Get bonuses based on city type."""
        bonuses = {
            "capital": {"population_bonus": 2.0, "tax_efficiency": 1.5},
            "trade": {"population_bonus": 1.3, "tax_efficiency": 1.8},
            "military": {"population_bonus": 1.2, "tax_efficiency": 1.1},
            "agricultural": {"population_bonus": 1.8, "tax_efficiency": 1.2}
        }
        return bonuses.get(city_type, {"population_bonus": 1.5, "tax_efficiency": 1.3})
    
    def get_city(self, name: str) -> Optional[City]:
        """Get a city by name."""
        return self.cities.get(name)
    
    def get_all_cities(self) -> Dict[str, City]:
        """Get all cities."""
        return self.cities.copy()
    
    def get_capital_city(self) -> Optional[City]:
        """Get the capital city (first capital type city found)."""
        for city in self.cities.values():
            if city.city_type == "capital":
                return city
        return None
    
    def get_total_population_bonus(self) -> float:
        """Calculate total population capacity bonus from all cities."""
        if not self.cities:
            return 1.0
        
        # Use the highest population bonus (cities don't stack linearly)
        # But add a small bonus for each additional city
        max_bonus = max(city.population_bonus for city in self.cities.values())
        additional_cities = len(self.cities) - 1
        
        return max_bonus + (additional_cities * 0.1)
    
    def get_total_tax_efficiency(self) -> float:
        """Calculate total tax collection efficiency from all cities."""
        if not self.cities:
            return 1.0
        
        # Average tax efficiency across all cities
        total_efficiency = sum(city.tax_efficiency for city in self.cities.values())
        return total_efficiency / len(self.cities)
    
    def upgrade_city(self, city_name: str) -> Dict[str, any]:
        """
        Attempt to upgrade a city to the next development level.
        
        Args:
            city_name: Name of city to upgrade
            
        Returns:
            Dictionary with upgrade result and requirements
        """
        city = self.cities.get(city_name)
        if not city:
            return {"success": False, "message": f"City {city_name} not found"}
        
        if city.development_level >= 4:
            return {"success": False, "message": f"{city_name} is already at maximum development level"}
        
        next_level = city.development_level + 1
        costs = self.development_costs.get(next_level, {})
        
        return {
            "success": False,  # Will be handled by resource check in actual upgrade
            "message": f"Upgrading {city_name} to level {next_level}",
            "costs": costs,
            "current_level": city.development_level,
            "next_level": next_level
        }
    
    def complete_city_upgrade(self, city_name: str) -> bool:
        """
        Complete a city upgrade (called after resources are deducted).
        
        Args:
            city_name: Name of city to upgrade
            
        Returns:
            True if upgrade was successful
        """
        city = self.cities.get(city_name)
        if not city or city.development_level >= 4:
            return False
        
        old_level = city.development_level
        city.development_level += 1
        
        # Improve bonuses with development
        city.population_bonus *= 1.2
        city.tax_efficiency *= 1.15
        
        # Emit upgrade event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='city_upgraded',
                entity_name=self.entity.name if self.entity else self.entity_id,
                city_name=city_name,
                old_level=old_level,
                new_level=city.development_level
            )
        
        return True
    
    def get_city_info(self, city_name: str) -> str:
        """Get formatted information about a specific city."""
        city = self.cities.get(city_name)
        if not city:
            return f"No city named {city_name} found."
        
        level_names = {1: "Village", 2: "Town", 3: "City", 4: "Metropolis"}
        level_name = level_names.get(city.development_level, "Unknown")
        
        info = f"{city.name} ({city.city_type.title()} {level_name})\n"
        info += f"Population Bonus: +{(city.population_bonus - 1) * 100:.0f}%\n"
        info += f"Tax Efficiency: +{(city.tax_efficiency - 1) * 100:.0f}%\n"
        info += f"Founded: Turn {city.founded_turn}"
        
        return info
    
    def get_cities_summary(self) -> str:
        """Get a summary of all cities."""
        if not self.cities:
            return "No cities controlled."
        
        summary = f"Cities Controlled: {len(self.cities)}\n"
        summary += f"Total Population Bonus: +{(self.get_total_population_bonus() - 1) * 100:.0f}%\n"
        summary += f"Tax Efficiency: +{(self.get_total_tax_efficiency() - 1) * 100:.0f}%\n\n"
        
        for city in self.cities.values():
            level_name = tier_name(city.development_level)
            nxt = get_tier(city.development_level + 1)
            upgrade_note = ""
            if nxt:
                cost = ", ".join(f"{v} {k}" for k, v in nxt.get('cost', {}).items())
                upgrade_note = f" — upgradeable to {nxt['name']} ({cost})"
            summary += f"• {city.name} ({city.city_type.title()}, {level_name}){upgrade_note}\n"

        return summary
    
    def get_cities_near_position(self, position: Tuple[int, int], max_distance: float = 5.0) -> List[City]:
        """Get cities within a certain distance of a position."""
        nearby_cities = []
        target_q, target_r = position
        
        for city in self.cities.values():
            city_q, city_r = city.position
            
            # Calculate hex distance
            distance = max(
                abs(city_q - target_q),
                abs(city_r - target_r),
                abs((city_q + city_r) - (target_q + target_r))
            )
            
            if distance <= max_distance:
                nearby_cities.append(city)
        
        return nearby_cities
    
    def get_lore_section(self) -> str:
        """Return lore explanation of city mechanics for AI prompts."""
        return """
**The Great Cities:**
Cities are the jewels in a lord's crown - strategic centers that amplify your house's strength through increased population capacity and more efficient tax collection. Each city type offers different advantages: capitals provide the greatest bonuses to both population and taxation, trade cities excel at gold generation, military cities support your territorial ambitions, while agricultural cities feed your growing realm.

Developing your cities from humble villages to grand metropolises requires significant investment, but each level of development increases both population capacity and tax efficiency. A wise lord invests in their cities for they are the foundation of lasting power.
"""

    def update(self, dt: float, event_bus=None):
        """Component update - not currently used for main city logic."""
        pass