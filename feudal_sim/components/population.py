"""
PopulationComponent - Core population management for entities.

Handles basic population count, capacity, loyalty, and growth mechanics
extracted from the House class.
"""

import math
from typing import Dict, Any, Set
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType


class PopulationComponent(Component):
    """
    Manages basic population for an entity.
    
    Core features from House class:
    - Population count and capacity
    - Population loyalty
    - Food-based population growth
    - Loyalty-based revolt warnings
    """
    
    def __init__(self, entity_id: str = None, starting_population: int = 100, starting_loyalty: int = 100):
        super().__init__(entity_id)
        
        self.population = starting_population
        self.population_capacity = 0  # Calculated from territories
        self.population_loyalty = starting_loyalty
        
        # Track previous values for observations
        self._previous_population = self.population
        self._previous_loyalty = self.population_loyalty

    @property
    def loyalty(self) -> int:
        """Get current population loyalty."""
        return self.population_loyalty

    @loyalty.setter
    def loyalty(self, value: int):
        """Set current population loyalty."""
        self.population_loyalty = value
    
    def calculate_capacity_from_territories(self, territories: Set) -> int:
        """Calculate population capacity from controlled territories."""
        if not territories:
            return 0
        
        capacity = sum(getattr(tile, 'population_capacity', 10) for tile in territories)
        self.population_capacity = capacity
        return capacity
    
    def manage_population_turn(self, total_food: float):
        """
        Manage population for one turn based on food availability.
        This is the core logic from House.manage_population().
        """
        # Store old values
        old_population = self.population
        old_loyalty = self.population_loyalty
        
        # Calculate population growth based on food availability (from House logic)
        population_growth = min(total_food // 2, self.population_capacity - self.population)
        
        # Update population
        self.population = min(self.population + population_growth, self.population_capacity)
        
        # Ensure population doesn't exceed capacity
        if self.population > self.population_capacity:
            self.population = self.population_capacity
        
        # Update population loyalty (from House logic)
        self.population_loyalty = min(self.population_loyalty + 1, 100)
        if total_food < 100:
            self.population_loyalty = max(self.population_loyalty - 1, 0)
        
        # Store for next turn comparison
        self._previous_population = old_population
        self._previous_loyalty = old_loyalty
    
    def check_revolt_risk(self) -> bool:
        """Check if population loyalty is low enough for revolt risk."""
        return self.population_loyalty < 50
    
    def adjust_loyalty(self, amount: int):
        """
        Adjust population loyalty by a given amount.
        
        Args:
            amount: Amount to adjust loyalty (can be positive or negative)
        """
        old_loyalty = self.population_loyalty
        self.population_loyalty = max(0, min(100, self.population_loyalty + amount))
        
        # Emit event for loyalty change
        if event_bus and self.population_loyalty != old_loyalty:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='population_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='loyalty',
                old_value=old_loyalty,
                new_value=self.population_loyalty,
                change=amount
            )
    
    def add_observation_for_changes(self, ai_component=None, phase: str = "Production"):
        """Add population change observations to AI component."""
        if not ai_component:
            return
        
        # Population change observations
        if self.population != self._previous_population:
            change = self.population - self._previous_population
            if change > 0:
                ai_component.add_observation(f"Your population grew by {change} people (now {self.population})", phase)
            elif change < 0:
                ai_component.add_observation(f"Your population decreased by {abs(change)} people (now {self.population})", phase)
        
        # Loyalty change observations
        if abs(self.population_loyalty - self._previous_loyalty) > 0:
            if self.population_loyalty > self._previous_loyalty:
                ai_component.add_observation(f"Population loyalty increased to {self.population_loyalty}", phase)
            else:
                ai_component.add_observation(f"Population loyalty decreased to {self.population_loyalty}", phase)
        
        # Revolt warning
        if self.check_revolt_risk():
            ai_component.add_observation("Your people are on the brink of revolt due to low loyalty!", phase)
    
    def get_population_status(self) -> Dict[str, Any]:
        """Get current population status for AI context or debugging."""
        return {
            'population': self.population,
            'population_capacity': self.population_capacity,
            'population_loyalty': self.population_loyalty,
            'revolt_risk': self.check_revolt_risk()
        }
    
    def update(self, dt: float, event_bus=None):
        """Component update method - not used for main population logic."""
        pass