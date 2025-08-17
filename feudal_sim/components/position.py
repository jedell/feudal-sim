"""
PositionComponent - Manages entity position and movement on the hex grid.

This component handles positioning for entities that exist at specific locations
on the map, such as generals, scouts, armies, and other mobile units.
It provides movement validation, distance calculations, and area of influence.
"""

from typing import Tuple, Set, List, Optional, Dict, Any
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.utils.directions import neighbor_delta_to_dir
from feudal_sim.utils.observations import ObservationFormatter


class PositionComponent(Component):
    """
    Manages position and movement for entities on the hex grid.
    
    Key features:
    - Current hex position (q, r coordinates)
    - Movement tracking and validation
    - Area of influence/operational range
    - Movement history for AI observations
    """
    
    def __init__(self, entity_id: str = None, position: Tuple[int, int] = None, 
                 operational_range: int = 3, movement_points: int = 2):
        super().__init__(entity_id)
        
        # Core position data
        self.q, self.r = position if position else (0, 0)
        self.previous_position: Optional[Tuple[int, int]] = None
        
        # Movement capabilities
        self.operational_range = operational_range  # Hex radius for influence/actions
        self.movement_points = movement_points  # How far can move per turn
        self.remaining_movement = movement_points  # Current turn remaining movement
        
        # Movement history for AI observations
        self.movement_history: List[Dict[str, Any]] = []
        self.turn_moved = -1  # Last turn this entity moved
    
    @property
    def position(self) -> Tuple[int, int]:
        """Get current position as (q, r) tuple."""
        return (self.q, self.r)
    
    @position.setter
    def position(self, new_position: Tuple[int, int]):
        """Set position with history tracking."""
        old_position = (self.q, self.r)
        self.q, self.r = new_position
        self.previous_position = old_position
        
        # Emit position change event
        if event_bus and old_position != new_position:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='position_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='position',
                old_value=old_position,
                new_value=new_position
            )
    
    def move_to(self, target_position: Tuple[int, int], hex_grid=None, 
                current_turn: int = None, validate_movement: bool = True) -> Dict[str, Any]:
        """
        Move to a target position with validation and cost calculation.
        
        Args:
            target_position: Target (q, r) coordinates
            hex_grid: HexGrid instance for movement validation
            current_turn: Current turn number for tracking
            validate_movement: Whether to validate movement rules
            
        Returns:
            Dictionary with movement result and details
        """
        target_q, target_r = target_position
        
        # Calculate movement distance
        distance = self.hex_distance(self.position, target_position)
        
        # Validate movement if requested
        if validate_movement:
            validation_result = self.validate_movement(target_position, hex_grid)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'message': f"Cannot move to ({target_q}, {target_r}): {validation_result['reason']}",
                    'distance': distance,
                    'movement_cost': distance
                }
        
        # Check movement points
        if distance > self.remaining_movement:
            return {
                'success': False,
                'message': f"Insufficient movement points: need {distance}, have {self.remaining_movement}",
                'distance': distance,
                'movement_cost': distance
            }
        
        # Execute movement
        old_position = self.position
        self.position = target_position
        self.remaining_movement -= distance
        
        # Record movement in history
        movement_record = {
            'turn': current_turn or -1,
            'from': old_position,
            'to': target_position,
            'distance': distance,
            'movement_cost': distance
        }
        self.movement_history.append(movement_record)
        self.turn_moved = current_turn or -1
        
        # Keep movement history manageable
        if len(self.movement_history) > 10:
            self.movement_history.pop(0)
        
        return {
            'success': True,
            'message': f"Moved from ({old_position[0]}, {old_position[1]}) to ({target_q}, {target_r})",
            'distance': distance,
            'movement_cost': distance,
            'remaining_movement': self.remaining_movement
        }
    
    def validate_movement(self, target_position: Tuple[int, int], hex_grid=None) -> Dict[str, Any]:
        """
        Validate if movement to target position is legal.
        
        Args:
            target_position: Target (q, r) coordinates
            hex_grid: HexGrid instance for terrain validation
            
        Returns:
            Dictionary with validation result and reason
        """
        target_q, target_r = target_position
        
        # Basic validation - can be extended for terrain, obstacles, etc.
        if hex_grid:
            # Check if target tile exists
            target_tile = hex_grid.get_tile(target_q, target_r)
            if not target_tile:
                return {
                    'valid': False,
                    'reason': 'Target position is outside map bounds'
                }
            
            # Check if tile is passable (not water for land units)
            from feudal_sim.map.types import HexTileType
            if target_tile.terrain_type in {HexTileType.OCEAN, HexTileType.LAKE}:
                return {
                    'valid': False,
                    'reason': 'Cannot move into water tiles'
                }
        
        return {
            'valid': True,
            'reason': 'Movement is valid'
        }
    
    def get_tiles_in_range(self, hex_grid=None, range_override: int = None) -> List[Tuple[int, int]]:
        """
        Get all tiles within operational range of current position.
        
        Args:
            hex_grid: HexGrid instance for boundary checking
            range_override: Use different range than operational_range
            
        Returns:
            List of (q, r) coordinates within range
        """
        search_range = range_override if range_override is not None else self.operational_range
        tiles_in_range = []
        
        # Generate all positions within range
        for dq in range(-search_range, search_range + 1):
            for dr in range(max(-search_range, -dq - search_range), 
                           min(search_range, -dq + search_range) + 1):
                tile_q = self.q + dq
                tile_r = self.r + dr
                
                # Skip center position (current position)
                if dq == 0 and dr == 0:
                    continue
                
                # Check if tile exists on the map
                if hex_grid:
                    if hex_grid.get_tile(tile_q, tile_r):
                        tiles_in_range.append((tile_q, tile_r))
                else:
                    # No hex_grid provided, return all calculated positions
                    tiles_in_range.append((tile_q, tile_r))
        
        return tiles_in_range
    
    def can_reach_tile(self, target_position: Tuple[int, int], 
                      range_override: int = None) -> bool:
        """
        Check if a tile is within operational range.
        
        Args:
            target_position: Target (q, r) coordinates
            range_override: Use different range than operational_range
            
        Returns:
            True if tile is reachable, False otherwise
        """
        search_range = range_override if range_override is not None else self.operational_range
        distance = self.hex_distance(self.position, target_position)
        return distance <= search_range
    
    def can_move_to_tile(self, target_position: Tuple[int, int]) -> bool:
        """
        Check if entity can move to a tile this turn (movement points).
        
        Args:
            target_position: Target (q, r) coordinates
            
        Returns:
            True if entity has enough movement points
        """
        distance = self.hex_distance(self.position, target_position)
        return distance <= self.remaining_movement
    
    @staticmethod
    def hex_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        """
        Calculate distance between two hex positions using cube coordinates.
        
        Args:
            pos1: First position (q, r)
            pos2: Second position (q, r)
            
        Returns:
            Distance in hex tiles
        """
        q1, r1 = pos1
        q2, r2 = pos2
        
        # Convert axial to cube coordinates
        s1 = -q1 - r1
        s2 = -q2 - r2
        
        # Calculate cube distance
        return (abs(q1 - q2) + abs(r1 - r2) + abs(s1 - s2)) // 2
    
    def reset_movement(self, current_turn: int = None):
        """
        Reset movement points at the start of a new turn.
        
        Args:
            current_turn: Current turn number for tracking
        """
        self.remaining_movement = self.movement_points
        
        # Emit event for movement reset
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='position_component',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='movement_reset',
                turn=current_turn,
                movement_points=self.movement_points
            )
    
    def get_movement_status(self) -> Dict[str, Any]:
        """Get current movement and position status for AI context."""
        return {
            'position': self.position,
            'previous_position': self.previous_position,
            'operational_range': self.operational_range,
            'movement_points': self.movement_points,
            'remaining_movement': self.remaining_movement,
            'can_move': self.remaining_movement > 0,
            'last_moved_turn': self.turn_moved
        }
    
    def add_movement_observation(self, ai_component=None, phase: str = "Actions"):
        """Add movement-related observations to AI component."""
        if not ai_component:
            return
        
        # Only add observation if entity moved this turn
        if self.previous_position and self.previous_position != self.position:
            old_q, old_r = self.previous_position
            new_q, new_r = self.position
            distance = self.hex_distance(self.previous_position, self.position)
            
            if distance == 1:
                dq = new_q - old_q
                dr = new_r - old_r
                dir_code = neighbor_delta_to_dir((dq, dr))
                msg = ObservationFormatter.movement_single_step(dir_code, self.remaining_movement)
            else:
                msg = ObservationFormatter.movement_multi_step(distance, self.remaining_movement)
            
            ai_component.add_observation(msg, phase)
        
        # Add operational range context (no raw coordinates)
        if hasattr(self.entity, 'name'):
            ai_component.add_observation(
                f"Can act within {self.operational_range} tiles this turn",
                phase
            )
    
    def get_lore_section(self) -> str:
        """Return lore explanation of position mechanics for AI prompts."""
        return """
**Positioning and Movement:**
Your agents operate from specific locations on the map and can move across the realm each turn. Each agent has an operational range - the area around their position where they can effectively act and exert influence. 

Movement is strategic: advancing positions allows access to new territories and opportunities, but may leave other areas vulnerable. Consider the placement of your forces carefully - a well-positioned general can control key territories, while a poorly placed one may find their influence limited.

Movement points refresh each turn, but moving consumes these points based on distance traveled. Plan your movements to maximize strategic advantage while maintaining operational flexibility.
"""
    
    def update(self, dt: float, event_bus=None):
        """Component update method - could be used for movement automation if needed."""
        # For now, position is only updated through explicit move_to() calls
        # Could be extended for autonomous movement, patrol routes, etc.
        pass