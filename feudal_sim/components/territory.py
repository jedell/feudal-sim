"""
TerritoryComponent - Territory and border management for entities.

Handles territory control, border calculation, territory expansion,
and tile ownership management.
"""

from typing import Set, List, Dict, Any
from dataclasses import dataclass
from feudal_sim.core.config import config

from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.components.population import PopulationComponent
from feudal_sim.map.types import HexTileType
    
@dataclass
class ExpansionOrder:
    """Represents a pending territory expansion order."""
    entity_id: str
    entity_name: str
    direction: str
    target_tiles: List  # List of tiles to expand into
    turn_ordered: int
    turn_resolves: int
    resource_cost: Dict[str, int]
    population_loyalty_cost: int
    success_probability: float = 1.0  # Base success probability
    status: str = "pending"  # pending, resolved_success, resolved_failure, contested


class TerritoryComponent(Component):
    """
    Manages territory control and borders for an entity.
    
    Core features from House class:
    - Territory tile management (set of controlled tiles)
    - Border tile calculation (neighboring uncontrolled tiles)
    - Territory expansion with ownership assignment
    - Border updates when territory changes
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Core territory data
        self.territory: Set = set()  # Set of hex tiles controlled by this entity
        self.border_tiles: Set = set()  # Set of tiles on the border (neighbors of territory)
        
        # Territory metadata
        self.territory_color = None  # Color to display territory (from entity)
        
        # Expansion order management
        self.pending_expansions: List[ExpansionOrder] = []  # Active expansion orders
        self.expansion_history: List[ExpansionOrder] = []  # Completed expansion orders
    
    def expand_territory(self, new_territory: List, hex_grid, owner_color=None):
        """
        Add new territory to the entity's control.
        
        Args:
            new_territory: List of hex tiles to add to territory
            hex_grid: Hex grid for neighbor calculation
            owner_color: Color to assign to new tiles (optional)
        """
        if not new_territory:
            return
        
        # Filter out non-claimable water tiles
        claimable = []
        for tile in new_territory:
            terrain = getattr(tile, 'terrain_type', None)
            if terrain in {HexTileType.RIVER, HexTileType.LAKE, HexTileType.OCEAN}:
                continue
            claimable.append(tile)
        
        if not claimable:
            return
        
        # Store old territory size for events
        old_territory_size = len(self.territory)
        
        # Add new territory to the entity's control
        self.territory.update(claimable)
        
        # Set ownership and color for new tiles
        for tile in claimable:
            tile.set_owner(self.entity if self.entity else self.entity_id)
            if owner_color:
                tile.owner_color = owner_color
                self.territory_color = owner_color
        
        # Update border tiles
        self._update_borders(hex_grid)
        
        # Emit event for territory expansion
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='territory_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='territory',
                old_value=old_territory_size,
                new_value=len(self.territory),
                change=len(claimable),
                tiles_added=len(claimable)
            )
    
    def remove_territory(self, tiles_to_remove: List, hex_grid):
        """
        Remove tiles from entity's control.
        
        Args:
            tiles_to_remove: List of hex tiles to remove from territory
            hex_grid: Hex grid for neighbor calculation
        """
        if not tiles_to_remove:
            return
        
        # Store old territory size for events
        old_territory_size = len(self.territory)
        
        # Remove tiles from territory
        for tile in tiles_to_remove:
            self.territory.discard(tile)
            tile.set_owner(None)  # Clear ownership
            tile.owner_color = None  # Clear color
        
        # Update border tiles
        self._update_borders(hex_grid)
        
        # Emit event for territory loss
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='territory_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='territory',
                old_value=old_territory_size,
                new_value=len(self.territory),
                change=-len(tiles_to_remove),
                tiles_removed=len(tiles_to_remove)
            )
    
    def is_controlled(self, tile) -> bool:
        """Check if a tile is controlled by this entity."""
        return tile in self.territory
    
    def is_border(self, tile) -> bool:
        """Check if a tile is on the border of this entity's territory."""
        return tile in self.border_tiles
    
    def get_territory_size(self) -> int:
        """Get the number of tiles controlled by this entity."""
        return len(self.territory)
    
    def get_border_size(self) -> int:
        """Get the number of border tiles."""
        return len(self.border_tiles)
    
    def get_neighboring_territories(self, hex_grid) -> Dict[str, int]:
        """
        Get neighboring territories and count of shared border tiles.
        
        Args:
            hex_grid: Hex grid for neighbor calculation
            
        Returns:
            Dictionary mapping entity names to shared border count
        """
        neighboring_entities = {}
        
        for border_tile in self.border_tiles:
            neighbors = hex_grid.get_neighbors(border_tile.q, border_tile.r)
            for neighbor_tile, _ in neighbors:
                if neighbor_tile in self.territory:
                    continue  # Skip our own territory
                
                # Check if neighbor is owned by another entity
                if hasattr(neighbor_tile, 'owner') and neighbor_tile.owner:
                    owner_name = getattr(neighbor_tile.owner, 'name', str(neighbor_tile.owner))
                    neighboring_entities[owner_name] = neighboring_entities.get(owner_name, 0) + 1
        
        return neighboring_entities
    
    def calculate_total_resources(self) -> Dict[str, float]:
        """
        Calculate total resource output from all controlled territories.
        
        Returns:
            Dictionary of resource types to total output
        """
        resources = {'food': 0.0, 'material': 0.0, 'metal': 0.0}
        
        for tile in self.territory:
            resources['food'] += getattr(tile, 'food_output', 0)
            resources['material'] += getattr(tile, 'material_output', 0)
            resources['metal'] += getattr(tile, 'metal_output', 0)
        
        return resources
    
    def get_border_tiles_by_direction(self, direction: str, hex_grid) -> List:
        """
        Get border tiles in a specific direction from the entity's territory.
        
        Args:
            direction: Hex direction (N, NE, SE, S, SW, NW)
            hex_grid: Hex grid for neighbor calculation
            
        Returns:
            List of border tiles in the specified direction
        """
        border_tiles_in_direction = []
        
        for territory_tile in self.territory:
            neighbor = hex_grid.get_neighbor(territory_tile.q, territory_tile.r, direction)
            if neighbor and neighbor not in self.territory:
                border_tiles_in_direction.append(neighbor)
        
        return border_tiles_in_direction
    
    def get_expansion_opportunities(self, direction: str, hex_grid) -> List[Dict[str, Any]]:
        """
        Get detailed information about expansion opportunities in a direction.
        
        Args:
            direction: Hex direction (N, NE, SE, S, SW, NW)
            hex_grid: Hex grid for neighbor calculation
            
        Returns:
            List of dictionaries with tile expansion data
        """
        opportunities = []
        border_tiles = self.get_border_tiles_by_direction(direction, hex_grid)
        
        for tile in border_tiles:
            if not tile or (hasattr(tile, 'owner') and tile.owner):
                continue  # Skip owned or invalid tiles
            
            # Check if tile is land (expandable)
            if hex_grid.is_land(tile):
                opportunity = {
                    'tile': tile,
                    'coordinates': (tile.q, tile.r),
                    'terrain_type': tile.terrain_type.value if hasattr(tile.terrain_type, 'value') else str(tile.terrain_type),
                    'resource_output': {
                        'food': getattr(tile, 'food_output', 0),
                        'material': getattr(tile, 'material_output', 0),
                        'metal': getattr(tile, 'metal_output', 0)
                    },
                    'population_capacity': getattr(tile, 'population_capacity', 0),
                }
                opportunities.append(opportunity)
        
        return opportunities
    
    def calculate_direction_value(self, direction: str, hex_grid) -> Dict[str, Any]:
        """
        Calculate the overall value of expanding in a specific direction.
        
        Args:
            direction: Hex direction (N, NE, SE, S, SW, NW)
            hex_grid: Hex grid for neighbor calculation
            
        Returns:
            Dictionary with direction expansion analysis
        """
        opportunities = self.get_expansion_opportunities(direction, hex_grid)
        
        if not opportunities:
            return {
                'direction': direction,
                'has_opportunities': False,
                'total_opportunities': 0,
                'message': f"No expansion opportunities in {direction} direction"
            }
        
        # Calculate aggregate values
        total_food = sum(op['resource_output']['food'] for op in opportunities)
        total_material = sum(op['resource_output']['material'] for op in opportunities)
        total_metal = sum(op['resource_output']['metal'] for op in opportunities)
        total_population_capacity = sum(op['population_capacity'] for op in opportunities)
        
        return {
            'direction': direction,
            'has_opportunities': True,
            'total_opportunities': len(opportunities),
            'total_resource_output': {
                'food': total_food,
                'material': total_material,
                'metal': total_metal,
                'total': total_food + total_material + total_metal
            },
            'total_population_capacity': total_population_capacity,
            'opportunities': opportunities,
            'expansion_cost_estimate': self._estimate_expansion_cost(len(opportunities)),
            'message': f"Found {len(opportunities)} expansion opportunities in {direction} direction"
        }
    
    def get_territory_status(self) -> Dict[str, Any]:
        """Get current territory status for AI context or debugging."""
        resource_output = self.calculate_total_resources()
        
        return {
            'territory_size': len(self.territory),
            'border_size': len(self.border_tiles),
            'resource_output': resource_output,
            'total_resource_output': sum(resource_output.values()),
            'has_territory': len(self.territory) > 0,
            'pending_expansions': len(self.pending_expansions),
            'expansion_orders': [
                {
                    'direction': order.direction,
                    'turn_resolves': order.turn_resolves,
                    'target_tiles': len(order.target_tiles),
                    'status': order.status
                }
                for order in self.pending_expansions
            ]
        }
    
    def add_observation_for_changes(self, ai_component=None, phase: str = "Events"):
        """
        Add territory change observations to AI component.
        
        Args:
            ai_component: AI component to add observations to
            phase: Current phase name for observation context
        """
        if not ai_component:
            return
        
        # This would be called after territory changes to inform AI
        # For now, we'll keep it simple - actual observations would be added
        # when expand_territory or remove_territory are called
        pass
    
    def _update_borders(self, hex_grid):
        """
        Update border tiles based on current territory.
        
        Args:
            hex_grid: Hex grid for neighbor calculation
        """
        self.border_tiles.clear()
        
        for tile in self.territory:
            neighbors = hex_grid.get_neighbors(tile.q, tile.r)
            for neighbor_tile, _ in neighbors:
                # If neighbor is not in our territory, it's a border tile
                if neighbor_tile not in self.territory:
                    self.border_tiles.add(neighbor_tile)
    
    def get_lore_section(self) -> str:
        """Return lore explanation of territory mechanics for AI prompts."""
        return """
**Territorial Dominion:**
Expansion requires both coin and conviction. Material wealth and gold fund your ambitions, but success depends greatly on your military readiness. A lord with many soldiers at arms finds expansion far more reliable than one who relies on workers alone. 

Territory expansion takes time - orders given this week resolve next week based on your preparation and the gods' favor. Each new territory brings resources and population capacity, but expansion comes at a cost as your people's loyalty may waver when you demand sacrifice for glory.
"""

    def update(self, dt: float, event_bus=None):
        """
        Component update method - not used for main territory logic.
        Territory changes happen via expand_territory/remove_territory methods.
        """
        # Could be used for passive territory effects if needed
        pass
    
    # ---- Sub-agent tracking helpers (generals) ----
    def register_general(self, general_info: Dict[str, Any]):
        """Register a deployed general for this house.
        Expects a dict with keys: entity_id, name, position, direction, orders,
        soldiers_assigned, workers_assigned, deployment_turn
        """
        if not hasattr(self, 'deployed_generals') or not isinstance(getattr(self, 'deployed_generals'), list):
            self.deployed_generals = []
        # Ensure uniqueness by entity_id
        self.deployed_generals = [g for g in self.deployed_generals if g.get('entity_id') != general_info.get('entity_id')]
        self.deployed_generals.append(general_info)
    
    def unregister_general(self, general_entity_id: str):
        """Remove a general from tracking by entity id."""
        if hasattr(self, 'deployed_generals') and isinstance(self.deployed_generals, list):
            self.deployed_generals = [g for g in self.deployed_generals if g.get('entity_id') != general_entity_id]
    
    def sync_generals(self, entity_manager) -> int:
        """Ensure tracked generals exist in the entity manager. Returns remaining count."""
        if not hasattr(self, 'deployed_generals') or not isinstance(self.deployed_generals, list):
            self.deployed_generals = []
            return 0
        existing_ids = set()
        try:
            generals = entity_manager.get_entities_by_type('general') if entity_manager else []
            for g in generals:
                # Keep only those that belong to this house
                if hasattr(g, 'house_id') and g.house_id == (self.entity.id if self.entity else None):
                    existing_ids.add(g.id)
        except Exception:
            pass
        self.deployed_generals = [g for g in self.deployed_generals if g.get('entity_id') in existing_ids]
        return len(self.deployed_generals)

    
    def _estimate_expansion_cost(self, num_tiles: int) -> Dict[str, int]:
        """
        Estimate the resource cost for expanding by a number of tiles.
        
        Args:
            num_tiles: Number of tiles to expand into
            
        Returns:
            Dictionary with estimated costs
        """
        
        # Get costs from config with fallback to original values
        base_material_cost = config.get('simulation.territory.expansion.base_material_cost', 30)
        base_gold_cost = config.get('simulation.territory.expansion.base_gold_cost', 20)
        base_population_cost = config.get('simulation.territory.expansion.base_population_cost', 5)
        
        return {
            'material': base_material_cost * num_tiles,
            'gold': base_gold_cost * num_tiles
        }
    
    def create_expansion_order(self, direction: str, hex_grid, current_turn: int, delay_turns: int = 1) -> ExpansionOrder:
        """
        Create a new expansion order for future resolution.
        
        Args:
            direction: Direction to expand (N, NE, SE, S, SW, NW)
            hex_grid: Hex grid for tile analysis
            current_turn: Current turn number
            delay_turns: Number of turns to delay before resolution
            
        Returns:
            Created ExpansionOrder or None if no opportunities
        """
        # Get expansion opportunities
        opportunities = self.get_expansion_opportunities(direction, hex_grid)
        
        if not opportunities:
            return None
        
        # Calculate costs
        expansion_costs = self._estimate_expansion_cost(len(opportunities))
        base_population_cost = 5  # Population loyalty cost per tile
        loyalty_cost = base_population_cost * len(opportunities)
        
        # Create expansion order
        expansion_order = ExpansionOrder(
            entity_id=self.entity_id,
            entity_name=self.entity.name if self.entity else self.entity_id,
            direction=direction,
            target_tiles=[op['tile'] for op in opportunities],
            turn_ordered=current_turn,
            turn_resolves=current_turn + delay_turns,
            resource_cost=expansion_costs,
            population_loyalty_cost=loyalty_cost,
            success_probability=self._calculate_expansion_success_probability(opportunities, hex_grid)
        )
        
        # Add to pending expansions
        self.pending_expansions.append(expansion_order)
        
        # Emit event for expansion order created
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='territory_component',
                entity_name=expansion_order.entity_name,
                property='expansion_order_created',
                direction=direction,
                target_tiles=len(expansion_order.target_tiles),
                turn_resolves=expansion_order.turn_resolves
            )
        
        return expansion_order
    
    def get_pending_expansions(self) -> List[ExpansionOrder]:
        """Get all pending expansion orders."""
        return [order for order in self.pending_expansions if order.status == "pending"]
    
    def get_expansions_ready_for_resolution(self, current_turn: int) -> List[ExpansionOrder]:
        """Get expansion orders ready for resolution this turn."""
        return [
            order for order in self.pending_expansions 
            if order.status == "pending" and order.turn_resolves <= current_turn
        ]
    
    def resolve_expansion_order(self, expansion_order: ExpansionOrder, success: bool, hex_grid) -> Dict[str, Any]:
        """
        Resolve an expansion order (success or failure).
        
        Args:
            expansion_order: The expansion order to resolve
            success: Whether the expansion succeeded
            hex_grid: Hex grid for territory updates
            
        Returns:
            Dictionary with resolution results
        """
        if success:
            # Execute the expansion
            expansion_order.status = "resolved_success"
            
            # Add tiles to territory
            self.expand_territory(expansion_order.target_tiles, hex_grid, self.territory_color)
            
            # Calculate gains
            total_food = sum(getattr(tile, 'food_output', 0) for tile in expansion_order.target_tiles)
            total_material = sum(getattr(tile, 'material_output', 0) for tile in expansion_order.target_tiles)
            total_metal = sum(getattr(tile, 'metal_output', 0) for tile in expansion_order.target_tiles)
            total_capacity = sum(getattr(tile, 'population_capacity', 0) for tile in expansion_order.target_tiles)
            
            result = {
                'success': True,
                'direction': expansion_order.direction,
                'tiles_gained': len(expansion_order.target_tiles),
                'resource_gains': {
                    'food': total_food,
                    'material': total_material,
                    'metal': total_metal
                },
                'population_capacity_gained': total_capacity,
                'message': f"Expansion {expansion_order.direction} succeeded! Gained {len(expansion_order.target_tiles)} tiles."
            }
        else:
            # Expansion failed
            expansion_order.status = "resolved_failure"
            
            result = {
                'success': False,
                'direction': expansion_order.direction,
                'tiles_gained': 0,
                'resource_gains': {'food': 0, 'material': 0, 'metal': 0},
                'population_capacity_gained': 0,
                'message': f"Expansion {expansion_order.direction} failed!"
            }
        
        # Move to history
        self.expansion_history.append(expansion_order)
        self.pending_expansions.remove(expansion_order)
        
        # Emit resolution event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='territory_component',
                entity_name=expansion_order.entity_name,
                property='expansion_resolved',
                **result
            )
        
        return result
    
    def cancel_expansion_order(self, expansion_order: ExpansionOrder) -> bool:
        """
        Cancel a pending expansion order.
        
        Args:
            expansion_order: The expansion order to cancel
            
        Returns:
            True if cancelled successfully
        """
        if expansion_order in self.pending_expansions and expansion_order.status == "pending":
            expansion_order.status = "cancelled"
            self.expansion_history.append(expansion_order)
            self.pending_expansions.remove(expansion_order)
            return True
        return False
    
    def _calculate_expansion_success_probability(self, opportunities: List[Dict], hex_grid) -> float:
        """
        Calculate base success probability for expansion.
        
        Args:
            opportunities: List of expansion opportunities
            hex_grid: Hex grid for analysis
            
        Returns:
            Success probability (0.0 to 1.0)
        """
        if not opportunities:
            return 0.0
        
        # Base success probability
        base_probability = 0.8
        
        # Get soldier bonus from population component
        soldier_bonus = 0.0
        if self.entity:
            population_component = self.entity.get_component(PopulationComponent)
            if population_component:
                soldier_bonus = population_component.calculate_soldier_expansion_bonus()
        
        # Factors that affect success
        # More tiles = slightly lower success rate
        tile_penalty = min(0.1, len(opportunities) * 0.02)
        
        # Terrain difficulty (mountains, difficult terrain)
        terrain_penalty = 0.0
        for opportunity in opportunities:
            terrain_str = opportunity.get('terrain_type', '')
            if 'MOUNTAIN' in terrain_str:
                terrain_penalty += 0.05
            elif 'HILL' in terrain_str:
                terrain_penalty += 0.02
        
        terrain_penalty = min(0.2, terrain_penalty)  # Cap at 20%
        
        # Calculate final probability with soldier bonus
        final_probability = base_probability + soldier_bonus - tile_penalty - terrain_penalty
        return max(0.1, min(1.0, final_probability))  # Clamp between 10% and 100%