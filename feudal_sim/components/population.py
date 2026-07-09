"""
PopulationComponent - Core population management for entities.

Handles basic population count, capacity, loyalty, and growth mechanics
extracted from the House class. Also handles population revolts that can
cause territory loss when loyalty falls too low.
"""

import random
from typing import Dict, Any, Set
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config

@dataclass
class AssignedPopulation:
    """Represents population assigned to a sub-agent."""
    workers: int = 0
    soldiers: int = 0
    
    @property
    def total(self) -> int:
        """Get total assigned population."""
        return self.workers + self.soldiers
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for easy serialization."""
        return {
            'workers': self.workers,
            'soldiers': self.soldiers,
            'total': self.total
        }

class PopulationComponent(Component):
    """
    Manages basic population for an entity.
    
    Core features from House class:
    - Population count and capacity
    - Population loyalty
    - Food-based population growth
    - Loyalty-based revolt warnings
    - Sub-agent population assignment tracking
    """
    
    def __init__(self, entity_id: str = None, starting_population: int = 100, starting_loyalty: int = 100):
        super().__init__(entity_id)
        
        self.population = starting_population
        self.population_capacity = 0  # Calculated from territories
        self.population_loyalty = starting_loyalty
        
        # Population ratio system - workers vs soldiers
        default_worker_ratio = config.get('simulation.population.ratios.default_worker_ratio', 0.7)
        default_soldier_ratio = config.get('simulation.population.ratios.default_soldier_ratio', 0.3)
        
        self.worker_ratio = default_worker_ratio
        self.soldier_ratio = default_soldier_ratio
        
        # Sub-agent population assignment tracking
        self.assigned_population: Dict[str, AssignedPopulation] = {}  # {agent_id: AssignedPopulation}
        
        # Track previous values for observations
        self._previous_population = self.population
        self._previous_loyalty = self.population_loyalty
        self._previous_worker_ratio = self.worker_ratio
        self._previous_soldier_ratio = self.soldier_ratio
        
        # Revolt mechanics
        self.last_revolt_turn = -999  # Track when last revolt occurred for cooldown
        self.consecutive_low_loyalty_turns = 0  # Track how long loyalty has been low
        # Social events (e.g., feasts) cooldown tracking
        self.last_feast_turn = -999

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
    
    def manage_population_turn(self, resource_component):
        """
        Manage population for one turn: subsistence consumption, demographics,
        and loyalty. The population eats from the house granary every turn;
        shortfalls cause starvation deaths and unrest, surpluses attract
        settlers. Returns a dict describing what happened for observations.
        """
        # Store old values
        old_population = self.population
        old_loyalty = self.population_loyalty

        # --- Subsistence: the population eats from the granary
        food_per_capita = config.get('simulation.population.food_per_capita', 0.05)
        food_needed = self.population * food_per_capita
        available = resource_component.resources.food if resource_component else 0.0
        consumed = min(food_needed, available)
        if resource_component and consumed > 0:
            resource_component.resources.consume('food', consumed)
        shortfall_ratio = ((food_needed - consumed) / food_needed) if food_needed > 0 else 0.0
        fed = 1.0 - shortfall_ratio

        # --- Demographics: config birth/death rates (annual), scaled per turn
        turns_per_year = config.get('simulation.time.turns_per_season', 4) * 4
        birth_rate = config.get('simulation.population.birth_rate', 0.035)
        death_rate = config.get('simulation.population.death_rate', 0.030)
        births = self.population * (birth_rate / turns_per_year) * fed
        deaths = self.population * (death_rate / turns_per_year) * (2.0 - fed)

        # Starvation kills beyond baseline mortality
        starvation_mortality = config.get('simulation.population.starvation_mortality', 0.10)
        starved = 0
        if shortfall_ratio > 0 and self.population > 0:
            import math
            starved = math.ceil(self.population * shortfall_ratio * starvation_mortality)

        # Prosperity attracts settlers: surplus food draws migrants — but
        # capped per turn as a fraction of current population, or surplus
        # feedback grows settlements exponentially past what tiles can feed
        immigration = 0.0
        if shortfall_ratio == 0 and resource_component:
            surplus = resource_component.resources.food
            per_food = config.get('simulation.population.immigration_per_surplus_food', 0.25)
            max_pct = config.get('simulation.population.immigration_max_pct_per_turn', 0.02)
            immigration = min(surplus * per_food,
                              self.population * max_pct,
                              max(0, self.population_capacity - self.population))

        # Fractional accumulator so sub-1 per-turn changes still add up
        self._growth_residual = getattr(self, '_growth_residual', 0.0) + births - deaths + immigration
        whole_change = int(self._growth_residual)
        self._growth_residual -= whole_change
        self.population = max(0, min(self.population + whole_change - starved,
                                     self.population_capacity))
        self._last_starved = starved

        # --- Loyalty is earned, not automatic: recovery only when fully fed
        if shortfall_ratio == 0:
            self.population_loyalty = min(self.population_loyalty + 1, 100)
        else:
            penalty = int(round(1 + 4 * shortfall_ratio))
            self.population_loyalty = max(self.population_loyalty - penalty, 0)

        # Store for next turn comparison
        self._previous_population = old_population
        self._previous_loyalty = old_loyalty
        return {
            'food_needed': food_needed,
            'consumed': consumed,
            'shortfall_ratio': shortfall_ratio,
            'starved': starved,
        }
    
    def check_revolt_risk(self) -> bool:
        """Check if population loyalty is low enough for revolt risk."""
        loyalty_threshold = config.get('simulation.population.revolt.loyalty_threshold', 30)
        return self.population_loyalty < loyalty_threshold
    
    def check_for_revolt(self, current_turn: int) -> bool:
        """
        Check if a revolt should occur this turn.
        
        Args:
            current_turn: Current turn number for cooldown tracking
            
        Returns:
            True if a revolt occurs, False otherwise
        """
        # Get revolt configuration
        loyalty_threshold = config.get('simulation.population.revolt.loyalty_threshold', 30)
        chance_per_turn = config.get('simulation.population.revolt.chance_per_turn', 0.25)
        cooldown_turns = config.get('simulation.population.revolt.cooldown_turns', 2)
        
        # Check if loyalty is below threshold
        if self.population_loyalty >= loyalty_threshold:
            self.consecutive_low_loyalty_turns = 0
            return False
        
        # Track consecutive turns of low loyalty
        self.consecutive_low_loyalty_turns += 1
        
        # Check cooldown - can't revolt if recently revolted
        if current_turn - self.last_revolt_turn < cooldown_turns:
            return False
        
        # Roll for revolt chance
        if random.random() < chance_per_turn:
            self.last_revolt_turn = current_turn
            return True
        
        return False
    
    def execute_revolt(self, hex_grid) -> Dict[str, Any]:
        """
        Execute a population revolt, causing territory loss and resource damage.
        
        Args:
            hex_grid: Hex grid for territory operations
            
        Returns:
            Dictionary with revolt results
        """
        from feudal_sim.components.territory import TerritoryComponent  # deferred: circular with feudal_sim.components.territory

        # Get territory component
        territory_component: TerritoryComponent = self.entity.get_component(TerritoryComponent) if self.entity else None
        if not territory_component:
            return {
                'success': False,
                'message': 'No territory component found',
                'tiles_lost': 0
            }
        
        # Check if there are border tiles to lose
        if not territory_component.border_tiles:
            return {
                'success': False, 
                'message': 'No border tiles available to lose',
                'tiles_lost': 0
            }
        
        # Get number of tiles to lose from config
        tiles_to_lose = config.get('simulation.population.revolt.tiles_lost_per_revolt', 1)
        tiles_to_lose = min(tiles_to_lose, len(territory_component.territory))  # Can't lose more than we have
        
        if tiles_to_lose <= 0:
            return {
                'success': False,
                'message': 'No territory tiles to lose',
                'tiles_lost': 0
            }
        
        # Choose random border tiles from territory (not border_tiles which are uncontrolled)
        # We want to lose actual territory tiles that are on the border
        border_territory_tiles = []
        for tile in territory_component.territory:
            # Check if this territory tile has neighbors that are not controlled
            neighbors = hex_grid.get_neighbors(tile.q, tile.r)
            for neighbor_tile, _ in neighbors:
                if neighbor_tile not in territory_component.territory:
                    border_territory_tiles.append(tile)
                    break  # This tile is on the border
        
        if not border_territory_tiles:
            # Fallback: lose any territory tile if no clear border
            border_territory_tiles = list(territory_component.territory)
        
        # Randomly select tiles to lose
        tiles_to_remove = random.sample(border_territory_tiles, min(tiles_to_lose, len(border_territory_tiles)))
        
        # Remove the territory
        territory_component.remove_territory(tiles_to_remove, hex_grid)
        
        # Apply resource losses due to revolt
        resource_losses = {}
        if self.entity:
            # Get resource loss configuration
            food_loss_percent = config.get('simulation.population.revolt.resource_loss.food_percent', 0.2)
            material_loss_percent = config.get('simulation.population.revolt.resource_loss.material_percent', 0.15)
            metal_loss_percent = config.get('simulation.population.revolt.resource_loss.metal_percent', 0.1)
            gold_loss_percent = config.get('simulation.population.revolt.resource_loss.gold_percent', 0.25)
            
            # Calculate and apply resource losses
            if hasattr(self.entity, 'resources'):
                # Apply losses
                food_loss = int(self.entity.resources['food'] * food_loss_percent)
                material_loss = int(self.entity.resources['material'] * material_loss_percent)
                metal_loss = int(self.entity.resources['metal'] * metal_loss_percent)
                gold_loss = int(self.entity.resources['gold'] * gold_loss_percent)
                
                # Apply the losses
                self.entity.resources['food'] = max(0, self.entity.resources['food'] - food_loss)
                self.entity.resources['material'] = max(0, self.entity.resources['material'] - material_loss)
                self.entity.resources['metal'] = max(0, self.entity.resources['metal'] - metal_loss)
                self.entity.resources['gold'] = max(0, self.entity.resources['gold'] - gold_loss)
                
                # Store losses for reporting
                resource_losses = {
                    'food': food_loss,
                    'material': material_loss,
                    'metal': metal_loss,
                    'gold': gold_loss
                }
        
        # Emit revolt event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='population_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='revolt',
                action_type='territory_and_resource_loss',
                tiles_lost=len(tiles_to_remove),
                resource_losses=resource_losses,
                loyalty=self.population_loyalty
            )
        
        return {
            'success': True,
            'message': f'Population revolt! Lost {len(tiles_to_remove)} border territory tile(s) and resources',
            'tiles_lost': len(tiles_to_remove),
            'lost_tiles': [(tile.q, tile.r) for tile in tiles_to_remove],
            'resource_losses': resource_losses
        }
    
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
        """Add critical population events to AI component. Population/loyalty deltas
        are already visible in the turn context status block — only revolt risk is injected here."""
        if not ai_component:
            return

        if self.check_revolt_risk():
            chance_per_turn = config.get('simulation.population.revolt.chance_per_turn', 0.25)
            ai_component.add_observation(
                f"REVOLT RISK: Loyalty at {self.population_loyalty} — "
                f"{chance_per_turn*100:.0f}% chance of revolt this turn (territory loss + resource damage).",
                phase
            )
    
    def set_population_ratios(self, worker_ratio: float, soldier_ratio: float) -> bool:
        """
        Set the population allocation between workers and soldiers.
        
        Args:
            worker_ratio: Ratio of population working (0.0 to 1.0)
            soldier_ratio: Ratio of population in military service (0.0 to 1.0)
            
        Returns:
            True if ratios were set successfully, False if invalid
        """
        # Validate ratios
        if worker_ratio < 0 or soldier_ratio < 0:
            return False
        if abs((worker_ratio + soldier_ratio) - 1.0) > 0.001:  # Allow small floating point errors
            return False
        
        # Store old values for events
        old_worker_ratio = self.worker_ratio
        old_soldier_ratio = self.soldier_ratio
        
        # Update ratios
        self.worker_ratio = worker_ratio
        self.soldier_ratio = soldier_ratio
        
        # Emit event for ratio change
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='population_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='population_ratios',
                old_worker_ratio=old_worker_ratio,
                old_soldier_ratio=old_soldier_ratio,
                new_worker_ratio=worker_ratio,
                new_soldier_ratio=soldier_ratio
            )
        
        return True
    
    def get_population_ratios(self) -> Dict[str, float]:
        """Get the current population ratios."""
        return {
            'workers': self.worker_ratio,
            'soldiers': self.soldier_ratio
        }
    
    def get_worker_count(self) -> int:
        """Get the number of workers in the population (excluding assigned)."""
        return int(self.get_available_population() * self.worker_ratio)
    
    def get_soldier_count(self) -> int:
        """Get the number of soldiers in the population (excluding assigned)."""
        return int(self.get_available_population() * self.soldier_ratio)
    
    def calculate_worker_efficiency(self) -> float:
        """
        Calculate resource production efficiency based on worker ratio.
        
        Returns:
            Efficiency multiplier for resource production
        """
        worker_efficiency_power = config.get('simulation.population.ratios.worker_efficiency_power', 1.2)
        return self.worker_ratio ** worker_efficiency_power
    
    def calculate_soldier_expansion_bonus(self) -> float:
        """
        Calculate expansion success bonus based on soldier ratio.
        
        Returns:
            Expansion success probability bonus (0.0 to max_bonus)
        """
        soldier_expansion_bonus_max = config.get('simulation.population.ratios.soldier_expansion_bonus_max', 0.3)
        soldier_expansion_multiplier = config.get('simulation.population.ratios.soldier_expansion_multiplier', 0.5)
        
        bonus = min(soldier_expansion_bonus_max, self.soldier_ratio * soldier_expansion_multiplier)
        return bonus

    def get_available_population(self) -> int:
        """
        Get population available for house operations (excluding assigned to sub-agents).
        
        Returns:
            Available population count
        """
        total_assigned = sum(assignment.total for assignment in self.assigned_population.values())
        return max(0, self.population - total_assigned)
    
    def get_total_assigned_population(self) -> int:
        """
        Get total population assigned to all sub-agents.
        
        Returns:
            Total assigned population count
        """
        return sum(assignment.total for assignment in self.assigned_population.values())
    
    def can_assign_population(self, workers: int = 0, soldiers: int = 0) -> bool:
        """
        Check if the specified population can be assigned to a sub-agent.
        
        Args:
            workers: Number of workers to assign
            soldiers: Number of soldiers to assign
            
        Returns:
            True if assignment is possible, False otherwise
        """
        total_requested = workers + soldiers
        return total_requested <= self.get_available_population()
    
    def assign_population_to_agent(self, agent_id: str, workers: int = 0, soldiers: int = 0) -> bool:
        """
        Assign population to a sub-agent.
        
        Args:
            agent_id: ID of the sub-agent to assign population to
            workers: Number of workers to assign
            soldiers: Number of soldiers to assign
            
        Returns:
            True if assignment successful, False if insufficient population
        """
        # Validate assignment is possible
        if not self.can_assign_population(workers, soldiers):
            return False
        
        # Check if agent already has assignment
        if agent_id in self.assigned_population:
            # Update existing assignment
            old_assignment = self.assigned_population[agent_id]
            self.assigned_population[agent_id] = AssignedPopulation(
                workers=old_assignment.workers + workers,
                soldiers=old_assignment.soldiers + soldiers
            )
        else:
            # Create new assignment
            self.assigned_population[agent_id] = AssignedPopulation(
                workers=workers,
                soldiers=soldiers
            )
        
        # Emit event for population assignment
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='population_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='population_assigned',
                agent_id=agent_id,
                workers_assigned=workers,
                soldiers_assigned=soldiers,
                total_assigned=workers + soldiers,
                available_population=self.get_available_population()
            )
        
        return True
    
    def recall_population_from_agent(self, agent_id: str) -> AssignedPopulation:
        """
        Recall all population from a sub-agent.
        
        Args:
            agent_id: ID of the sub-agent to recall population from
            
        Returns:
            AssignedPopulation object representing recalled population
        """
        if agent_id not in self.assigned_population:
            return AssignedPopulation()  # Empty assignment
        
        # Get the assignment to return
        recalled = self.assigned_population[agent_id]
        
        # Remove the assignment
        del self.assigned_population[agent_id]
        
        # Emit event for population recall
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='population_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='population_recalled',
                agent_id=agent_id,
                workers_recalled=recalled.workers,
                soldiers_recalled=recalled.soldiers,
                total_recalled=recalled.total,
                available_population=self.get_available_population()
            )
        
        return recalled
    
    def get_agent_assignment(self, agent_id: str) -> AssignedPopulation:
        """
        Get population assignment for a specific agent.
        
        Args:
            agent_id: ID of the sub-agent
            
        Returns:
            AssignedPopulation object for the agent
        """
        return self.assigned_population.get(agent_id, AssignedPopulation())

    def get_population_status(self) -> Dict[str, Any]:
        """Get current population status for AI context or debugging."""
        return {
            'population': self.population,
            'population_capacity': self.population_capacity,
            'population_loyalty': self.population_loyalty,
            'available_population': self.get_available_population(),
            'assigned_population': self.get_total_assigned_population(),
            'worker_ratio': self.worker_ratio,
            'soldier_ratio': self.soldier_ratio,
            'worker_count': self.get_worker_count(),
            'soldier_count': self.get_soldier_count(),
            'worker_efficiency': self.calculate_worker_efficiency(),
            'soldier_expansion_bonus': self.calculate_soldier_expansion_bonus(),
            'revolt_risk': self.check_revolt_risk(),
            'assignments': {agent_id: assignment.to_dict() for agent_id, assignment in self.assigned_population.items()}
        }
    
    def get_lore_section(self) -> str:
        """Return lore explanation of population mechanics for AI prompts."""
        return """
**Managing Your Household:**
Your people serve in two capacities - as laborers who work your lands and generate wealth, or as soldiers who secure your borders and enable conquest. This balance defines your house's character:
- **The Merchant's Way**: Many workers, few soldiers - your lands prosper but expansion is perilous
- **The Warrior's Path**: Many soldiers, few workers - your military conquests are swift but your coffers may suffer  
- **The Balanced Rule**: Equal measure of both - moderate prosperity with reliable expansion

When your people's loyalty falls too low, they may revolt, seizing territory and destroying resources. Mind their contentment, for a disloyal population is a lord's greatest weakness.
"""

    def update(self, dt: float, event_bus=None):
        """Component update method - not used for main population logic."""
        pass