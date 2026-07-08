"""
Trade Caravan Entity - Physical representation of trade missions.

Trade caravans are entities that move across the map carrying goods from
one house to another, creating opportunities for negotiations, encounters,
and emergent gameplay scenarios.
"""

import uuid
from typing import Optional, Tuple, Dict, Any, List
from feudal_sim.core.entities import Entity
from feudal_sim.components.position import PositionComponent
from feudal_sim.components.cargo import CargoComponent, TradeGoods, TradeTerms
from feudal_sim.components.pathfinding import PathfindingComponent
from feudal_sim.components.ai import AIComponent
from feudal_sim.ai.prompts import AgentType
from feudal_sim.core.priority_actions import PriorityActionEvent


class TradeCaravan(Entity):
    """
    A trade caravan entity that physically moves across the map.
    
    Combines PositionComponent (for movement), CargoComponent (for goods),
    and optionally AIComponent (for autonomous decision-making during encounters).
    """
    
    def __init__(self, 
                 sender_house_id: str,
                 recipient_house_id: str,
                 cargo: TradeGoods,
                 trade_terms: TradeTerms,
                 starting_position: Tuple[int, int],
                 caravan_name: str = None,
                 entity_id: str = None):
        """
        Create a new trade caravan.
        
        Args:
            sender_house_id: ID of the house sending the caravan
            recipient_house_id: ID of the house receiving the caravan
            cargo: TradeGoods being transported
            trade_terms: Terms and conditions of the trade
            starting_position: Starting position (q, r) on the hex grid
            caravan_name: Optional custom name for the caravan
            entity_id: Optional specific entity ID
        """
        # Generate name if not provided
        if not caravan_name:
            caravan_name = f"Trade Caravan {str(uuid.uuid4())[:8]}"
        
        super().__init__(entity_id, caravan_name)
        
        # Store house information
        self.sender_house_id = sender_house_id
        self.recipient_house_id = recipient_house_id
        self.house_id = sender_house_id  # For compatibility with existing systems
        
        # Mission tracking
        self.mission_id = str(uuid.uuid4())
        self.created_turn: Optional[int] = None
        self.arrival_turn: Optional[int] = None
        
        # Add core components
        self._setup_position_component(starting_position)
        self._setup_cargo_component(cargo, trade_terms)
        self._setup_pathfinding_component()
        
        # Optional AI component for autonomous caravans
        self.has_ai = False
    
    def _setup_position_component(self, starting_position: Tuple[int, int]):
        """Set up the position component for movement."""
        position_comp = PositionComponent()
        position_comp.position = starting_position
        position_comp.movement_points = 3  # Caravans move slower than military units
        position_comp.max_movement_points = 3
        self.add_component(position_comp)
    
    def _setup_cargo_component(self, cargo: TradeGoods, trade_terms: TradeTerms):
        """Set up the cargo component with trade goods."""
        cargo_comp = CargoComponent()
        cargo_comp.load_cargo(cargo)
        cargo_comp.set_trade_terms(trade_terms)
        cargo_comp.sender_house_id = self.sender_house_id
        cargo_comp.recipient_house_id = self.recipient_house_id
        cargo_comp.trade_mission_id = self.mission_id
        self.add_component(cargo_comp)
    
    def _setup_pathfinding_component(self):
        """Set up pathfinding component for navigation."""
        pathfinding_comp = PathfindingComponent()
        pathfinding_comp.avoid_water = True  # Trade caravans avoid water
        pathfinding_comp.avoid_enemy_territory = True  # Prefer safe routes
        self.add_component(pathfinding_comp)
    
    def add_ai_component(self, entity_manager):
        """
        Add AI component for autonomous caravan behavior.
        
        Args:
            entity_manager: Entity manager to register the AI-enabled caravan
        """
        if self.has_ai:
            return  # Already has AI
        
        # Get sender house for context
        sender_house = entity_manager.get_entity(self.sender_house_id)
        sender_name = sender_house.name if sender_house else "Unknown House"
        
        ai_comp = AIComponent(
            name=f"Caravan Master of {self.name}",
            agent_type=AgentType.MERCHANT,
            entity_id=self.id,
            house_name=sender_name
        )
        self.add_component(ai_comp)
        self.has_ai = True
    
    def get_cargo_summary(self) -> str:
        """Get a summary of the caravan's cargo."""
        cargo_comp = self.get_component(CargoComponent)
        if cargo_comp:
            return cargo_comp.get_cargo_summary()
        return "No cargo information"
    
    def get_trade_summary(self) -> str:
        """Get a summary of the trade mission."""
        cargo_comp = self.get_component(CargoComponent)
        if cargo_comp:
            return cargo_comp.get_trade_summary()
        return "No trade mission information"
    
    def get_position(self) -> Optional[Tuple[int, int]]:
        """Get current position of the caravan."""
        position_comp = self.get_component(PositionComponent)
        if position_comp:
            return position_comp.position
        return None
    
    def set_destination(self, destination: Tuple[int, int], hex_grid):
        """Set the destination for this caravan and calculate path."""
        pathfinding_comp = self.get_component(PathfindingComponent)
        if pathfinding_comp:
            pathfinding_comp.set_destination(destination, hex_grid, self.sender_house_id)
    
    def plan_route_to_house(self, target_house, hex_grid, preferred_direction: str = None):
        """
        Plan route to a target house's territory.
        
        Args:
            target_house: Target house entity
            hex_grid: The game's hex grid
            preferred_direction: Optional direction hint from the lord (N, NE, SE, S, SW, NW)
        """
        from feudal_sim.components.pathfinding import PathfindingComponent
        pathfinding_comp = self.get_component(PathfindingComponent)

        def _try_destination(dest):
            """Set destination and return True only if a valid path was found."""
            self.set_destination(dest, hex_grid)
            return bool(pathfinding_comp and pathfinding_comp.current_path)

        # Method 1: Use IntelligenceComponent's territory center calculation
        from feudal_sim.components.intelligence import IntelligenceComponent
        intelligence_comp = target_house.get_component(IntelligenceComponent)
        if intelligence_comp:
            try:
                center_q, center_r = intelligence_comp._get_our_territory_center()
                destination = (int(round(center_q)), int(round(center_r)))
                dest_tile = hex_grid.get_tile(destination[0], destination[1])
                if dest_tile and hasattr(dest_tile, 'owner') and dest_tile.owner:
                    if hasattr(dest_tile.owner, 'id') and dest_tile.owner.id == target_house.id:
                        if _try_destination(destination):
                            return True
            except Exception:
                pass

        # Method 2: Direction hint border tile
        if preferred_direction:
            destination = self._find_border_tile_in_direction(target_house, preferred_direction)
            if destination and _try_destination(destination):
                return True

        # Method 3: Any tile from target territory, sorted by proximity to sender
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.components.position import PositionComponent
        territory_comp = target_house.get_component(TerritoryComponent)
        if territory_comp and territory_comp.territory:
            pos_comp = self.get_component(PositionComponent)
            tiles = list(territory_comp.territory)
            if pos_comp and pos_comp.position:
                q0, r0 = pos_comp.position
                tiles.sort(key=lambda t: abs(t.q - q0) + abs(t.r - r0))
            for tile in tiles:
                if _try_destination((tile.q, tile.r)):
                    return True

        # Method 4: Last resort — allow crossing any terrain (drop avoid_enemy_territory)
        if pathfinding_comp:
            original_avoid = pathfinding_comp.avoid_enemy_territory
            pathfinding_comp.avoid_enemy_territory = False
            territory_comp = target_house.get_component(TerritoryComponent)
            if territory_comp and territory_comp.territory:
                for tile in list(territory_comp.territory):
                    if _try_destination((tile.q, tile.r)):
                        return True
            pathfinding_comp.avoid_enemy_territory = original_avoid

        return False
    
    def _find_border_tile_in_direction(self, target_house, direction: str) -> Tuple[int, int]:
        """
        Find a border tile of the target house in the specified direction.
        
        Args:
            target_house: Target house entity
            direction: Direction hint (N, NE, SE, S, SW, NW)
            
        Returns:
            Tuple of (q, r) coordinates or None if not found
        """
        from feudal_sim.components.territory import TerritoryComponent
        territory_comp = target_house.get_component(TerritoryComponent)
        if not territory_comp or not territory_comp.territory:
            return None
            
        # Convert territory to list for processing
        territory_tiles = list(territory_comp.territory)
        if not territory_tiles:
            return None
            
        # Direction vectors for hex grid
        direction_vectors = {
            'N': (0, -1),
            'NE': (1, -1), 
            'SE': (1, 0),
            'S': (0, 1),
            'SW': (-1, 1),
            'NW': (-1, 0)
        }
        
        if direction not in direction_vectors:
            return None
            
        # Find the territory tile that's furthest in the specified direction
        dq, dr = direction_vectors[direction]
        best_tile = None
        best_score = float('-inf')
        
        for tile in territory_tiles:
            # Score based on position in the desired direction
            score = tile.q * dq + tile.r * dr
            if score > best_score:
                best_score = score
                best_tile = tile
                
        if best_tile:
            return (best_tile.q, best_tile.r)
            
        return None
    
    def is_at_destination(self, destination: Tuple[int, int] = None) -> bool:
        """Check if caravan has reached its destination."""
        pathfinding_comp = self.get_component(PathfindingComponent)
        if pathfinding_comp:
            return pathfinding_comp.is_at_destination()
        
        # Fallback to manual check
        if destination:
            current_pos = self.get_position()
            return current_pos == destination if current_pos else False
        
        return False
    
    def move_towards_destination(self, hex_grid, current_turn: int) -> Dict[str, Any]:
        """
        Move one step towards the destination.
        
        Args:
            hex_grid: HexGrid instance for movement validation
            current_turn: Current turn number
            
        Returns:
            Movement result dictionary
        """
        position_comp = self.get_component(PositionComponent)
        pathfinding_comp = self.get_component(PathfindingComponent)
        
        if not position_comp or not pathfinding_comp:
            return {'success': False, 'message': 'Missing required components for movement'}
        
        # Check if we have movement points
        if position_comp.remaining_movement <= 0:
            return {'success': False, 'message': 'No movement points remaining'}
        
        # Get next position from pathfinding
        next_position = pathfinding_comp.get_next_position()
        if not next_position:
            # Check if we're at destination
            if pathfinding_comp.is_at_destination():
                return {'success': True, 'message': 'Already at destination', 'arrived': True}
            else:
                return {'success': False, 'message': 'No valid path to destination'}
        
        # Attempt movement
        movement_result = position_comp.move_to(
            next_position, hex_grid, current_turn, validate_movement=True
        )
        
        if movement_result['success']:
            # Advance path index
            pathfinding_comp.advance_path()
            
            # Check if we've arrived at final destination
            arrived = pathfinding_comp.is_at_destination()
            movement_result['arrived'] = arrived
            
            if arrived:
                movement_result['message'] += ' - Arrived at destination!'
        
        return movement_result
    
    def on_arrival(self, simulation, current_turn: int) -> PriorityActionEvent:
        """
        Handle caravan arrival at destination.
        
        Args:
            simulation: Reference to the main simulation
            current_turn: Current turn number
            
        Returns:
            PriorityActionEvent for the trade caravan arrival
        """
        self.arrival_turn = current_turn
        
        # Get house entities for event creation
        sender_house = simulation.entity_manager.get_entity(self.sender_house_id)
        recipient_house = simulation.entity_manager.get_entity(self.recipient_house_id)
        
        cargo_comp = self.get_component(CargoComponent)
        
        # Create priority action event for the trade arrival
        event = PriorityActionEvent(
            event_id=f"trade_arrival_{self.mission_id}",
            event_type="trade_caravan_arrival",
            context_data={
                'caravan': {
                    'id': self.id,
                    'name': self.name,
                    'contents': str(cargo_comp.cargo) if cargo_comp else 'unknown goods',
                    'proposed_terms': str(cargo_comp.trade_terms) if cargo_comp else 'unknown terms'
                },
                'sending_house': {
                    'id': self.sender_house_id,
                    'name': sender_house.name if sender_house else 'Unknown House'
                },
                'receiving_house': {
                    'id': self.recipient_house_id,
                    'name': recipient_house.name if recipient_house else 'Unknown House'
                },
                'arrival_turn': current_turn,
                'entity_manager': simulation.entity_manager,
            },
            involved_agents=[self.recipient_house_id, self.sender_house_id],
            allows_conversation=True,
            max_conversation_rounds=3,
            created_turn=current_turn
        )
        
        return event
    
    def complete_trade(self, outcome: str, turn: int):
        """Complete the trade mission with an outcome."""
        cargo_comp = self.get_component(CargoComponent)
        if cargo_comp:
            cargo_comp.complete_trade(outcome, turn)
    
    def get_movement_points(self) -> int:
        """Get remaining movement points."""
        position_comp = self.get_component(PositionComponent)
        return position_comp.movement_points if position_comp else 0
    
    def can_move(self) -> bool:
        """Check if caravan can move this turn."""
        return self.get_movement_points() > 0
    
    def reset_movement_points(self, current_turn: int):
        """Reset movement points for a new turn."""
        position_comp = self.get_component(PositionComponent)
        if position_comp:
            position_comp.reset_movement(current_turn)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive status summary for debugging/display."""
        position_comp = self.get_component(PositionComponent)
        cargo_comp = self.get_component(CargoComponent)
        
        return {
            'name': self.name,
            'mission_id': self.mission_id,
            'sender_house': self.sender_house_id,
            'recipient_house': self.recipient_house_id,
            'position': position_comp.position if position_comp else None,
            'movement_points': position_comp.movement_points if position_comp else 0,
            'cargo_summary': cargo_comp.get_cargo_summary() if cargo_comp else "No cargo",
            'trade_completed': cargo_comp.is_trade_completed if cargo_comp else False,
            'has_ai': self.has_ai,
            'created_turn': self.created_turn,
            'arrival_turn': self.arrival_turn
        }
    
    @classmethod
    def create_trade_caravan(cls,
                           sender_house_id: str,
                           recipient_house_id: str,
                           cargo: TradeGoods,
                           proposed_terms: str,
                           starting_position: Tuple[int, int],
                           additional_terms: str = "",
                           caravan_name: str = None) -> 'TradeCaravan':
        """
        Factory method to create a trade caravan with standard terms.
        
        Args:
            sender_house_id: ID of sending house
            recipient_house_id: ID of receiving house  
            cargo: Goods being transported
            proposed_terms: Main terms of the trade
            starting_position: Starting hex position
            additional_terms: Additional conditions
            caravan_name: Optional caravan name
            
        Returns:
            Configured TradeCaravan instance
        """
        trade_terms = TradeTerms(
            proposed_by=sender_house_id,
            offered_goods=cargo,
            additional_terms=f"{proposed_terms}. {additional_terms}".strip(". "),
            requires_safe_passage=True
        )
        
        return cls(
            sender_house_id=sender_house_id,
            recipient_house_id=recipient_house_id,
            cargo=cargo,
            trade_terms=trade_terms,
            starting_position=starting_position,
            caravan_name=caravan_name
        )