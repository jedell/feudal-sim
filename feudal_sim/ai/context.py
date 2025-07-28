from dataclasses import dataclass, field
from typing import Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from feudal_sim.core.entities import EntityManager
    from feudal_sim.map.hex_grid import HexGrid
    from feudal_sim.core.simulation import Simulation

@dataclass
class SimulationContext:
    """
    Context object passed to OpenAI agents containing current simulation state.
    This context is accessible to AI tools via the Agents SDK context system.
    """
    entity_id: str
    entity_name: str
    current_turn: int
    current_phase: str
    current_season: str
    current_year: int
    game_state: Dict[str, Any] = field(default_factory=dict)
    
    # Simulation objects for tool access
    hex_grid: "HexGrid" = None  # HexGrid instance for map operations
    entity_manager: "EntityManager" = None  # EntityManager for inter-entity operations
    simulation: "Simulation" = None  # Reference to main simulation object
