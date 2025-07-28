"""
ResourceComponent - Resource storage, gathering, and consumption system.

Handles all resource-related operations including storage, gathering from territories,
consumption for actions, tax collection, and event emission for AI decision-making.
"""

import math
from typing import Dict, Set, Any
from dataclasses import dataclass, field
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config


@dataclass
class ResourceStore:
    """Container for all resource types with helper methods."""
    food: float = 100.0
    material: float = 100.0
    metal: float = 100.0
    gold: float = 100.0
    
    def add(self, resource_type: str, amount: float):
        """Add resources to the store."""
        if hasattr(self, resource_type):
            current = getattr(self, resource_type)
            setattr(self, resource_type, current + amount)
            return True
        return False
    
    def consume(self, resource_type: str, amount: float) -> bool:
        """Consume resources from the store. Returns True if successful."""
        if hasattr(self, resource_type):
            current = getattr(self, resource_type)
            if current >= amount:
                setattr(self, resource_type, current - amount)
                return True
        return False
    
    def get(self, resource_type: str) -> float:
        """Get current amount of a resource type."""
        return getattr(self, resource_type, 0.0)
    
    def can_afford(self, costs: Dict[str, float]) -> bool:
        """Check if all costs can be afforded."""
        for resource_type, amount in costs.items():
            if self.get(resource_type) < amount:
                return False
        return True
    
    def consume_multiple(self, costs: Dict[str, float]) -> bool:
        """Consume multiple resource types. Returns True if successful."""
        if not self.can_afford(costs):
            return False
        
        for resource_type, amount in costs.items():
            self.consume(resource_type, amount)
        return True
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization/AI context."""
        return {
            'food': self.food,
            'material': self.material,
            'metal': self.metal,
            'gold': self.gold
        }


class ResourceComponent(Component):
    """
    Manages resource storage, gathering, and consumption for an entity.
    
    Features:
    - Resource storage (food, material, metal, gold)
    - Territory-based resource gathering
    - Resource consumption for actions
    - Tax collection mechanisms
    - Event emission for AI observation
    - Efficiency calculations based on population
    """
    
    def __init__(self, entity_id: str = None, starting_resources: Dict[str, float] = None):
        super().__init__(entity_id)
        
        # Initialize resource store
        if starting_resources:
            self.resources = ResourceStore(**starting_resources)
        else:
            self.resources = ResourceStore()
        
        # Resource gathering efficiency modifier
        self.gathering_efficiency = 1.0
        
        # Track resource changes for observations
        self._previous_resources = self.resources.to_dict()
    
    def gather_resources_from_territories(self, territories: Set, population_ratio: float = 1.0, seasonal_modifier: float = 1.0, worker_efficiency: float = 1.0):
        """
        Gather resources from controlled territories.
        
        Args:
            territories: Set of hex tiles controlled by this entity
            population_ratio: Population to capacity ratio for efficiency calculation (deprecated, use worker_efficiency)
            seasonal_modifier: Seasonal multiplier for resource production
            worker_efficiency: Efficiency multiplier based on worker ratio in population
        """
        # Store old values for event emission
        old_resources = self.resources.to_dict()
        
        # Use worker efficiency instead of old population ratio method
        # Keep population_ratio for backward compatibility but prioritize worker_efficiency
        if worker_efficiency != 1.0:
            efficiency = self.gathering_efficiency * worker_efficiency
        else:
            # Fallback to old method for backward compatibility
            efficiency = self._calculate_efficiency(population_ratio)
        
        # Gather from each territory
        for hex_tile in territories:
            # Apply seasonal modifier to farming output
            food_modifier = seasonal_modifier if 'food' in ['food'] else 1.0
            gathering_multiplier = config.get('simulation.resources.gathering_multiplier', 1.0)
            
            # Gather resources with efficiency and modifiers
            self.resources.add('food', math.ceil(
                hex_tile.food_output * gathering_multiplier * efficiency * food_modifier
            ))
            self.resources.add('material', math.ceil(
                hex_tile.material_output * gathering_multiplier * efficiency
            ))
            self.resources.add('metal', math.ceil(
                hex_tile.metal_output * gathering_multiplier * efficiency
            ))
        
        # Generate observations and emit events for changes
        self._process_resource_changes(old_resources)
    
    def collect_taxes(self, population: int, tax_rate: float) -> float:
        """
        Collect taxes from population.
        
        Args:
            population: Total population to tax
            tax_rate: Tax rate (0.0 to 1.0)
            
        Returns:
            Amount of gold collected
        """
        if not (0 < tax_rate <= 1):
            raise ValueError("Tax rate must be between 0 and 1")
        
        old_gold = self.resources.gold
        tax_collected = math.ceil(population * tax_rate)
        self.resources.add('gold', tax_collected)
        
        # Emit event for tax collection
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='resource_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='resources',
                resource_type='gold',
                old_value=old_gold,
                new_value=self.resources.gold,
                change=tax_collected,
                action_type='tax_collection',
                tax_rate=tax_rate
            )
        
        return tax_collected
    
    def consume_for_action(self, resource_costs: Dict[str, float], action_name: str = "action") -> bool:
        """
        Consume resources for an action.
        
        Args:
            resource_costs: Dictionary of resource_type -> amount
            action_name: Name of the action for events/observations
            
        Returns:
            True if resources were consumed successfully, False if insufficient
        """
        if not self.resources.can_afford(resource_costs):
            return False
        
        # Store old values
        old_resources = self.resources.to_dict()
        
        # Consume resources
        self.resources.consume_multiple(resource_costs)
        
        # Emit events for resource consumption
        for resource_type, amount in resource_costs.items():
            if event_bus:
                event_bus.emit(
                    EventType.VALUE_CHANGED,
                    self,
                    entity_type='resource_component',
                    entity_name=self.entity.name if self.entity else self.entity_id,
                    property='resources',
                    resource_type=resource_type,
                    old_value=old_resources[resource_type],
                    new_value=self.resources.get(resource_type),
                    change=-amount,
                    action_type=action_name
                )
        
        return True
    
    def can_afford_action(self, resource_costs: Dict[str, float]) -> bool:
        """Check if entity can afford an action with given resource costs."""
        return self.resources.can_afford(resource_costs)
    
    def get_resource_status(self) -> Dict[str, Any]:
        """Get current resource status for AI context or debugging."""
        return {
            'resources': self.resources.to_dict(),
            'gathering_efficiency': self.gathering_efficiency,
            'total_value': sum(self.resources.to_dict().values())
        }
    
    def add_observation_for_changes(self, ai_component=None, phase: str = "Production"):
        """
        Add resource change observations to AI component.
        
        Args:
            ai_component: AI component to add observations to
            phase: Current phase name for observation context
        """
        if not ai_component:
            return
        
        current_resources = self.resources.to_dict()
        resource_changes = {}
        
        for resource_type in ['food', 'material', 'metal', 'gold']:
            old_value = self._previous_resources.get(resource_type, 0)
            new_value = current_resources[resource_type]
            change = new_value - old_value
            if change > 0:
                resource_changes[resource_type] = change
        
        if resource_changes:
            # Create natural language observation for AI
            changes_text = ", ".join([f"+{amount} {resource}" for resource, amount in resource_changes.items()])
            ai_component.add_observation(f"Your territories produced {changes_text} this turn", phase)
        
        # Update previous resources for next comparison
        self._previous_resources = current_resources.copy()
    
    def _calculate_efficiency(self, population_ratio: float) -> float:
        """
        Calculate resource gathering efficiency based on population ratio.
        
        Args:
            population_ratio: Population to capacity ratio (0.0 to 1.0+)
            
        Returns:
            Efficiency multiplier
        """
        # As population nears capacity, efficiency decreases
        # Formula: 1 + 1/exp(population_ratio)
        return self.gathering_efficiency * (1 + 1/math.exp(population_ratio))
    
    def _process_resource_changes(self, old_resources: Dict[str, float]):
        """Process resource changes and emit events."""
        current_resources = self.resources.to_dict()
        
        # Emit events for resource changes (makes system extensible)
        for resource_type in ['food', 'material', 'metal', 'gold']:
            old_value = old_resources[resource_type]
            new_value = current_resources[resource_type]
            if new_value != old_value:
                if event_bus:
                    event_bus.emit(
                        EventType.VALUE_CHANGED,
                        self,
                        entity_type='resource_component',
                        entity_name=self.entity.name if self.entity else self.entity_id,
                        property='resources',
                        resource_type=resource_type,
                        old_value=old_value,
                        new_value=new_value,
                        change=new_value - old_value
                    )
    
    def get_lore_section(self) -> str:
        """Return lore explanation of resource mechanics for AI prompts."""
        return """
**The Taxman's Burden:**
When gold runs low, you may levy taxes upon your subjects. Higher rates fill your treasury quickly but breed resentment among your people. A lord who taxes too heavily may face their subjects' loyalty cracking like ice in spring.

Your lands produce four types of wealth: food to sustain your people, materials for construction, metals for arms and trade, and gold for purchasing power. The efficiency of your workers determines how much your territories yield each season.
"""

    def update(self, dt: float, event_bus=None):
        """
        Component update method - not used for main resource logic.
        Resource gathering happens during Production phase via specific methods.
        """
        # Could be used for passive resource generation if needed
        pass