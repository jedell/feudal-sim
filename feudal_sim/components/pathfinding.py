"""
PathfindingComponent - Handles route planning and navigation for moving entities.

Provides pathfinding capabilities using A* algorithm optimized for hex grids.
Used by trade caravans and other entities that need to navigate across the map.
"""

import heapq
from typing import List, Tuple, Optional, Dict, Set
from feudal_sim.core.entities import Component
from feudal_sim.map.types import HexTileType
from feudal_sim.components.position import PositionComponent


class PathfindingComponent(Component):
    """
    Component that handles pathfinding and navigation for moving entities.
    
    Uses A* algorithm to find optimal paths across the hex grid, taking into
    account terrain types, ownership, and movement costs.
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Current path and navigation state
        self.current_path: List[Tuple[int, int]] = []
        self.destination: Optional[Tuple[int, int]] = None
        self.path_index: int = 0  # Current position in the path
        
        # Pathfinding preferences
        self.avoid_water: bool = True
        self.avoid_enemy_territory: bool = True
        self.prefer_roads: bool = False  # Future expansion
        self.movement_cost_multiplier: float = 1.0
    
    def find_path(self, start: Tuple[int, int], goal: Tuple[int, int], 
                  hex_grid, entity_house_id: str = None) -> List[Tuple[int, int]]:
        """
        Find optimal path from start to goal using A* algorithm.
        
        Args:
            start: Starting position (q, r)
            goal: Goal position (q, r)
            hex_grid: HexGrid instance for terrain and ownership data
            entity_house_id: House ID of the entity (for territory avoidance)
            
        Returns:
            List of positions forming the path, empty if no path found
        """
        if start == goal:
            return [start]
        
        # A* algorithm implementation
        open_set = [(0, start)]  # Priority queue: (f_score, position)
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        
        g_score: Dict[Tuple[int, int], float] = {start: 0}
        f_score: Dict[Tuple[int, int], float] = {start: self._heuristic(start, goal)}
        
        visited: Set[Tuple[int, int]] = set()
        
        while open_set:
            current_f, current = heapq.heappop(open_set)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Check if we've reached the goal
            if current == goal:
                return self._reconstruct_path(came_from, current)
            
            # Explore neighbors
            neighbors = self._get_valid_neighbors(current, hex_grid, entity_house_id)
            
            for neighbor_pos, movement_cost in neighbors:
                if neighbor_pos in visited:
                    continue
                
                tentative_g_score = g_score[current] + movement_cost
                
                if neighbor_pos not in g_score or tentative_g_score < g_score[neighbor_pos]:
                    came_from[neighbor_pos] = current
                    g_score[neighbor_pos] = tentative_g_score
                    f_score[neighbor_pos] = tentative_g_score + self._heuristic(neighbor_pos, goal)
                    heapq.heappush(open_set, (f_score[neighbor_pos], neighbor_pos))
        
        # No path found
        return []
    
    def set_destination(self, destination: Tuple[int, int], hex_grid, entity_house_id: str = None):
        """
        Set destination and calculate path.
        
        Args:
            destination: Target position (q, r)
            hex_grid: HexGrid instance
            entity_house_id: House ID of the entity
        """
        if not self.entity:
            return
        
        # Get current position from position component
        position_comp = self.entity.get_component(PositionComponent)
        if not position_comp:
            return

        current_pos = position_comp.position
        self.destination = destination
        self.current_path = self.find_path(current_pos, destination, hex_grid, entity_house_id)
        self.path_index = 0
        
        if self.current_path:
            print(f"🗺️ Path calculated: {len(self.current_path)} steps to destination")
        else:
            print(f"❌ No path found to destination {destination}")
    
    def get_next_position(self) -> Optional[Tuple[int, int]]:
        """
        Get the next position to move to along the current path.
        
        Returns:
            Next position to move to, or None if at destination or no path
        """
        if not self.current_path or self.path_index >= len(self.current_path):
            return None
        
        # Skip the first position if it's our current position
        if self.path_index == 0 and len(self.current_path) > 1:
            self.path_index = 1
        
        if self.path_index >= len(self.current_path):
            return None
        
        return self.current_path[self.path_index]
    
    def advance_path(self):
        """Advance to the next position in the path."""
        self.path_index += 1
    
    def is_at_destination(self) -> bool:
        """Check if we've reached the destination."""
        if not self.destination or not self.entity:
            return True

        position_comp = self.entity.get_component(PositionComponent)
        if not position_comp:
            return True
        
        return position_comp.position == self.destination
    
    def get_remaining_distance(self) -> int:
        """Get remaining distance to destination."""
        if not self.current_path or not self.entity:
            return 0

        position_comp = self.entity.get_component(PositionComponent)
        if not position_comp or not self.destination:
            return 0
        
        return self._hex_distance(position_comp.position, self.destination)
    
    def clear_path(self):
        """Clear the current path and destination."""
        self.current_path = []
        self.destination = None
        self.path_index = 0
    
    def _heuristic(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate heuristic distance between two hex positions."""
        return float(self._hex_distance(pos1, pos2))
    
    def _hex_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        """Calculate hex grid distance between two positions."""
        q1, r1 = pos1
        q2, r2 = pos2
        s1, s2 = -q1 - r1, -q2 - r2
        return (abs(q1 - q2) + abs(r1 - r2) + abs(s1 - s2)) // 2
    
    def _get_valid_neighbors(self, position: Tuple[int, int], hex_grid, 
                           entity_house_id: str) -> List[Tuple[Tuple[int, int], float]]:
        """
        Get valid neighboring positions with movement costs.
        
        Args:
            position: Current position (q, r)
            hex_grid: HexGrid instance
            entity_house_id: House ID for territory considerations
            
        Returns:
            List of (neighbor_position, movement_cost) tuples
        """
        neighbors = []
        
        # Get hex grid neighbors
        hex_neighbors = hex_grid.get_neighbors(position[0], position[1])
        
        for neighbor_tile, direction in hex_neighbors:
            if not neighbor_tile:
                continue
            
            neighbor_pos = (neighbor_tile.q, neighbor_tile.r)
            movement_cost = self._calculate_movement_cost(neighbor_tile, entity_house_id)
            
            # Skip if movement cost is prohibitive (e.g., water for land units)
            if movement_cost < float('inf'):
                neighbors.append((neighbor_pos, movement_cost))
        
        return neighbors
    
    def _calculate_movement_cost(self, tile, entity_house_id: str) -> float:
        """
        Calculate movement cost for entering a tile.
        
        Args:
            tile: HexTile to evaluate
            entity_house_id: House ID of the moving entity
            
        Returns:
            Movement cost (float('inf') means impassable)
        """
        base_cost = 1.0 * self.movement_cost_multiplier

        # Water tiles
        if tile.terrain_type in {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER}:
            if self.avoid_water:
                return float('inf')  # Impassable for trade caravans
            else:
                return base_cost * 3.0  # High cost if water travel allowed

        # Terrain-based costs — shared config table with general movement
        from feudal_sim.components.position import terrain_step_cost
        cost = base_cost * terrain_step_cost(tile)

        # Territory-based costs
        if self.avoid_enemy_territory and hasattr(tile, 'owner') and tile.owner:
            if hasattr(tile.owner, 'id') and tile.owner.id != entity_house_id:
                cost *= 2.0  # Higher cost to cross enemy territory

        return cost
    
    def _reconstruct_path(self, came_from: Dict[Tuple[int, int], Tuple[int, int]], 
                         current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Reconstruct path from A* came_from dictionary."""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
    
    def get_path_summary(self) -> str:
        """Get human-readable path summary."""
        if not self.current_path:
            return "No active path"
        
        progress = f"{self.path_index}/{len(self.current_path)}"
        destination_str = f"to {self.destination}" if self.destination else "unknown destination"
        
        return f"Following path {progress} {destination_str}"
    
    def update(self, dt: float, event_bus=None):
        """Update pathfinding component (no regular updates needed)."""
        pass
    
    def get_lore_section(self) -> Optional[str]:
        """Return lore explanation of pathfinding mechanics."""
        return (
            "Trade caravans employ experienced guides who know the safest routes "
            "between territories. They navigate carefully around dangerous terrain "
            "and hostile lands, balancing speed with safety. The success of trade "
            "depends not just on the goods carried, but on choosing the right path."
        )