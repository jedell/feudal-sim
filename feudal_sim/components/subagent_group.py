"""
SubAgentGroup Component - Manages population groups assigned to sub-agents.

This component tracks the population assigned to a sub-agent from their parent house,
provides group-specific capabilities, and manages group operations like settlement,
fortification, and resource management.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.components.population import AssignedPopulation


@dataclass
class MissionParameters:
    """Parameters defining the sub-agent's mission."""
    mission_type: str  # "patrol", "expansion", "settlement", "fortification"
    target_area: Optional[tuple] = None  # (q, r) coordinates if applicable
    orders: Optional[str] = None  # Specific orders from parent house
    priority: str = "medium"  # "high", "medium", "low"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'mission_type': self.mission_type,
            'target_area': self.target_area,
            'orders': self.orders,
            'priority': self.priority
        }


class SubAgentGroup(Component):
    """
    Manages a population group assigned to a sub-agent.
    
    This component handles:
    - Tracking assigned population from parent house
    - Group capabilities and strength calculations
    - Supply management and consumption
    - Settlement and construction abilities
    - Mission parameter management
    """
    
    def __init__(self, entity_id: str = None, parent_house_id: str = None, 
                 group_type: str = "military", assigned_population: AssignedPopulation = None):
        super().__init__(entity_id)
        
        # Core group identity
        self.parent_house_id = parent_house_id or entity_id
        self.group_type = group_type  # "military", "settler", "construction", "patrol"
        self.assigned_population = assigned_population or AssignedPopulation()
        
        # Mission management
        self.mission_parameters = MissionParameters(mission_type="patrol")
        self.mission_status = "active"  # "active", "completed", "failed", "recalled"
        
        # Group state tracking
        self.morale = 100  # Group morale (affects performance)
        self.supplies = 100  # Supply level (consumed over time)
        self.experience = 0  # Experience points from successful missions
        
        # Performance tracking
        self.turns_deployed = 0
        self.successful_actions = 0
        self.failed_actions = 0
        
        # Supply consumption rates (configurable)
        self.supply_consumption_per_turn = config.get('simulation.subagents.supply_consumption_per_turn', 5)
        self.low_supply_threshold = config.get('simulation.subagents.low_supply_threshold', 25)
    
    def get_group_strength(self) -> int:
        """
        Calculate overall group strength for combat and challenges.
        
        Returns:
            Group strength value
        """
        base_strength = self.assigned_population.total
        
        # Apply morale modifier
        morale_modifier = self.morale / 100.0
        
        # Apply experience bonus
        experience_bonus = min(0.2, self.experience * 0.01)  # Max 20% bonus
        
        # Apply supply penalty if low
        supply_modifier = 1.0
        if self.supplies < self.low_supply_threshold:
            supply_modifier = max(0.5, self.supplies / 100.0)  # Minimum 50% strength
        
        final_strength = int(base_strength * morale_modifier * (1 + experience_bonus) * supply_modifier)
        return max(1, final_strength)  # Minimum strength of 1
    
    def get_settlement_capability(self) -> float:
        """
        Calculate group's ability to settle new territory.
        
        Returns:
            Settlement capability (0.0 to 1.0)
        """
        # Base capability from workers
        base_capability = min(1.0, self.assigned_population.workers / 20.0)  # 20 workers = 100% capability
        
        # Soldiers provide some settlement capability (security and labor)
        soldier_contribution = min(0.3, self.assigned_population.soldiers / 30.0)  # Max 30% from soldiers
        
        # Apply supply and morale modifiers
        supply_modifier = self.supplies / 100.0
        morale_modifier = self.morale / 100.0
        
        final_capability = (base_capability + soldier_contribution) * supply_modifier * morale_modifier
        return max(0.1, min(1.0, final_capability))  # Clamp between 10% and 100%
    
    def get_combat_strength(self) -> int:
        """
        Calculate group's combat strength for military encounters.
        
        Returns:
            Combat strength value
        """
        # Primarily based on soldiers
        base_combat = self.assigned_population.soldiers * 2
        
        # Workers provide minimal combat support
        worker_support = self.assigned_population.workers * 0.5
        
        # Apply group modifiers
        strength_modifier = self.get_group_strength() / self.assigned_population.total if self.assigned_population.total > 0 else 1.0
        
        final_combat = int((base_combat + worker_support) * strength_modifier)
        return max(1, final_combat)
    
    def get_construction_capability(self) -> float:
        """
        Calculate group's ability to construct fortifications or buildings.
        
        Returns:
            Construction capability (0.0 to 1.0)
        """
        # Primarily based on workers
        base_capability = min(1.0, self.assigned_population.workers / 15.0)  # 15 workers = 100% capability
        
        # Apply supply and morale modifiers
        supply_modifier = self.supplies / 100.0
        morale_modifier = self.morale / 100.0
        
        final_capability = base_capability * supply_modifier * morale_modifier
        return max(0.0, min(1.0, final_capability))
    
    def consume_supplies(self, amount: int = None) -> bool:
        """
        Consume supplies for group operations.
        
        Args:
            amount: Amount of supplies to consume (uses default rate if None)
            
        Returns:
            True if supplies available, False if depleted
        """
        if amount is None:
            # Base consumption plus population-based consumption
            base_consumption = self.supply_consumption_per_turn
            population_consumption = max(1, self.assigned_population.total // 5)  # 1 supply per 5 people
            amount = base_consumption + population_consumption
        
        if self.supplies >= amount:
            old_supplies = self.supplies
            self.supplies = max(0, self.supplies - amount)
            
            # Emit supply consumption event
            if event_bus:
                event_bus.emit(
                    EventType.VALUE_CHANGED,
                    self,
                    entity_type='subagent_group',
                    entity_name=self.entity.name if self.entity else self.entity_id,
                    property='supplies_consumed',
                    old_value=old_supplies,
                    new_value=self.supplies,
                    consumption=amount
                )
            
            return True
        else:
            # Insufficient supplies - consume what's available
            consumed = self.supplies
            self.supplies = 0
            
            # Apply morale penalty for supply shortage
            self.adjust_morale(-5)
            
            if event_bus:
                event_bus.emit(
                    EventType.VALUE_CHANGED,
                    self,
                    entity_type='subagent_group',
                    entity_name=self.entity.name if self.entity else self.entity_id,
                    property='supply_shortage',
                    requested=amount,
                    available=consumed,
                    morale_penalty=-5
                )
            
            return False
    
    def resupply(self, amount: int) -> bool:
        """
        Resupply the group (from parent house or foraging).
        
        Args:
            amount: Amount of supplies to add
            
        Returns:
            True if resupply successful
        """
        old_supplies = self.supplies
        self.supplies = min(100, self.supplies + amount)
        
        # Improve morale if supplies were critically low
        if old_supplies < self.low_supply_threshold and self.supplies >= self.low_supply_threshold:
            self.adjust_morale(10)
        
        # Emit resupply event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='subagent_group',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='resupplied',
                old_value=old_supplies,
                new_value=self.supplies,
                amount_added=amount
            )
        
        return True
    
    def adjust_morale(self, amount: int):
        """
        Adjust group morale.
        
        Args:
            amount: Amount to adjust morale (can be positive or negative)
        """
        old_morale = self.morale
        self.morale = max(0, min(100, self.morale + amount))
        
        # Emit morale change event
        if event_bus and self.morale != old_morale:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='subagent_group',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='morale',
                old_value=old_morale,
                new_value=self.morale,
                change=amount
            )
    
    def set_mission(self, mission_type: str, target_area: tuple = None, orders: str = None, priority: str = "medium"):
        """
        Set new mission parameters for the group.
        
        Args:
            mission_type: Type of mission ("patrol", "expansion", "settlement", "fortification")
            target_area: Target coordinates if applicable
            orders: Specific orders from parent house
            priority: Mission priority level
        """
        old_mission = self.mission_parameters.mission_type
        
        self.mission_parameters = MissionParameters(
            mission_type=mission_type,
            target_area=target_area,
            orders=orders,
            priority=priority
        )
        
        # Reset mission status when new mission assigned
        self.mission_status = "active"
        
        # Emit mission change event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='subagent_group',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='mission_assigned',
                old_mission=old_mission,
                new_mission=mission_type,
                target_area=target_area,
                orders=orders,
                priority=priority
            )
    
    def record_action_result(self, success: bool, experience_gained: int = 1):
        """
        Record the result of a group action for tracking and experience.
        
        Args:
            success: Whether the action was successful
            experience_gained: Experience points to add
        """
        if success:
            self.successful_actions += 1
            self.experience += experience_gained
            self.adjust_morale(2)  # Small morale boost for success
        else:
            self.failed_actions += 1
            self.adjust_morale(-3)  # Small morale penalty for failure
        
        # Emit action result event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='subagent_group',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='action_completed',
                success=success,
                experience_gained=experience_gained,
                total_experience=self.experience,
                successful_actions=self.successful_actions,
                failed_actions=self.failed_actions
            )
    
    def update_turn(self, hex_grid=None, current_turn=None):
        """
        Update group state for a new turn.
        Should be called each turn to handle supply consumption and status updates.
        
        Args:
            hex_grid: Hex grid for terrain observation (optional)
            current_turn: Current turn number for observation tracking (optional)
        """
        self.turns_deployed += 1
        
        # Consume supplies automatically each turn
        had_supplies = self.consume_supplies()
        
        # Auto-observe surroundings if we have the components
        if self.entity and hex_grid and current_turn is not None:
            from feudal_sim.components.terrain_observation import TerrainObservation
            from feudal_sim.components.position import PositionComponent
            
            terrain_obs = self.entity.get_component(TerrainObservation)
            position_comp = self.entity.get_component(PositionComponent)
            
            if terrain_obs and position_comp and position_comp.position:
                # Observe current area (like houses observing their domain)
                observation_result = terrain_obs.observe_current_area(
                    hex_grid, position_comp.position, current_turn
                )
                
                # Optional: Adjust morale based on what we observe
                if observation_result.get('success'):
                    threats = observation_result.get('new_threats', 0)
                    opportunities = observation_result.get('new_opportunities', 0)
                    
                    # Small morale boost for finding opportunities
                    if opportunities > 0:
                        self.adjust_morale(1)
                    
                    # Small morale penalty for detecting threats
                    if threats > 0:
                        self.adjust_morale(-1)
        
        # Check for mission completion conditions
        if not had_supplies and self.supplies == 0:
            # Out of supplies - mission may need to be aborted
            self.mission_status = "supply_critical"
            self.adjust_morale(-5)
    
    def get_group_status(self) -> Dict[str, Any]:
        """Get current group status for AI context or debugging."""
        return {
            'group_type': self.group_type,
            'parent_house_id': self.parent_house_id,
            'assigned_population': self.assigned_population.to_dict(),
            'mission': self.mission_parameters.to_dict(),
            'mission_status': self.mission_status,
            'morale': self.morale,
            'supplies': self.supplies,
            'experience': self.experience,
            'turns_deployed': self.turns_deployed,
            'group_strength': self.get_group_strength(),
            'settlement_capability': self.get_settlement_capability(),
            'combat_strength': self.get_combat_strength(),
            'construction_capability': self.get_construction_capability(),
            'successful_actions': self.successful_actions,
            'failed_actions': self.failed_actions,
            'supply_status': "critical" if self.supplies < self.low_supply_threshold else "adequate"
        }
    
    def get_lore_section(self) -> str:
        """Return lore explanation of group mechanics for AI prompts."""
        return f"""
**Your {self.group_type.title()} Group:**
You command {self.assigned_population.total} souls - {self.assigned_population.workers} workers and {self.assigned_population.soldiers} soldiers assigned to your service by your lord. Their morale stands at {self.morale}%, and your supplies are at {self.supplies}%.

Your group's strength in the field is {self.get_group_strength()}, shaped by their morale, experience, and supply situation. {self.assigned_population.workers} workers grant you the capability to settle new lands or construct fortifications, while {self.assigned_population.soldiers} soldiers provide the martial strength needed for expansion and defense.

Remember: your people consume supplies each turn, and low supplies or repeated failures will damage their morale. Success breeds success - experienced groups with high morale accomplish far more than dispirited bands.
"""

    def update(self, dt: float, event_bus=None):
        """Component update method - not used for main logic."""
        pass