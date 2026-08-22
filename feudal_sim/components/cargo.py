"""
CargoComponent - Manages trade goods and resources being transported.

Used by trade caravans and other transport entities to track what goods
they're carrying and the terms of trade.
"""

from typing import Dict, Optional
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType


@dataclass
class TradeGoods:
    """Represents a collection of trade goods with their quantities."""
    food: float = 0.0
    material: float = 0.0
    metal: float = 0.0
    gold: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {
            'food': self.food,
            'material': self.material,
            'metal': self.metal,
            'gold': self.gold
        }
    
    def from_dict(self, data: Dict[str, float]) -> 'TradeGoods':
        """Create TradeGoods from dictionary."""
        return TradeGoods(
            food=data.get('food', 0.0),
            material=data.get('material', 0.0),
            metal=data.get('metal', 0.0),
            gold=data.get('gold', 0.0)
        )
    
    def total_value(self) -> float:
        """Calculate total value of goods (simple sum)."""
        return self.food + self.material + self.metal + self.gold
    
    def is_empty(self) -> bool:
        """Check if cargo is empty."""
        return self.total_value() == 0.0
    
    def __add__(self, other: 'TradeGoods') -> 'TradeGoods':
        """Add two TradeGoods together."""
        return TradeGoods(
            food=self.food + other.food,
            material=self.material + other.material,
            metal=self.metal + other.metal,
            gold=self.gold + other.gold
        )
    
    def __str__(self) -> str:
        """String representation of trade goods."""
        non_zero = []
        if self.food > 0:
            non_zero.append(f"{self.food:.1f} food")
        if self.material > 0:
            non_zero.append(f"{self.material:.1f} material")
        if self.metal > 0:
            non_zero.append(f"{self.metal:.1f} metal")
        if self.gold > 0:
            non_zero.append(f"{self.gold:.1f} gold")
        
        return ", ".join(non_zero) if non_zero else "empty cargo"


@dataclass
class TradeTerms:
    """Represents the terms and conditions of a trade."""
    proposed_by: str = ""  # House ID that proposed these terms
    requested_goods: Optional[TradeGoods] = None
    offered_goods: Optional[TradeGoods] = None
    additional_terms: str = ""  # Free text for special conditions
    is_gift: bool = False  # True if no payment expected
    requires_safe_passage: bool = True  # Most trades include safe passage
    
    def __post_init__(self):
        if self.requested_goods is None:
            self.requested_goods = TradeGoods()
        if self.offered_goods is None:
            self.offered_goods = TradeGoods()
    
    def __str__(self) -> str:
        """String representation of trade terms."""
        if self.is_gift:
            return f"Gift of {self.offered_goods} from {self.proposed_by}"
        
        terms_str = f"Trade: {self.offered_goods} for {self.requested_goods}"
        if self.additional_terms:
            terms_str += f" ({self.additional_terms})"
        if self.requires_safe_passage:
            terms_str += " with safe passage rights"
        
        return terms_str


class CargoComponent(Component):
    """
    Component for managing trade goods and cargo transport.
    
    Used by trade caravans to track what they're carrying and the
    terms of trade they're operating under.
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Current cargo
        self.cargo: TradeGoods = TradeGoods()
        self.max_capacity: float = 500.0  # Maximum cargo capacity
        
        # Trade information
        self.trade_terms: Optional[TradeTerms] = None
        self.sender_house_id: str = ""
        self.recipient_house_id: str = ""
        self.trade_mission_id: str = ""  # Unique ID for this trade mission
        
        # Status tracking
        self.is_trade_completed: bool = False
        self.trade_outcome: str = ""  # Result of the trade negotiation
        self.delivery_turn: Optional[int] = None  # Turn when delivered
    
    def load_cargo(self, goods: TradeGoods) -> bool:
        """
        Load trade goods into the cargo hold.
        
        Args:
            goods: TradeGoods to load
            
        Returns:
            True if cargo was loaded successfully, False if over capacity
        """
        if goods.total_value() + self.cargo.total_value() > self.max_capacity:
            return False
        
        self.cargo = self.cargo + goods
        
        # Emit cargo loaded event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='cargo_loaded',
                entity_id=self.entity_id,
                cargo=self.cargo.to_dict()
            )
        
        return True
    
    def unload_cargo(self) -> TradeGoods:
        """
        Unload all cargo and return it.
        
        Returns:
            TradeGoods that was unloaded
        """
        unloaded = self.cargo
        self.cargo = TradeGoods()
        
        # Emit cargo unloaded event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                change_type='cargo_unloaded',
                entity_id=self.entity_id,
                unloaded_cargo=unloaded.to_dict()
            )
        
        return unloaded
    
    def set_trade_terms(self, terms: TradeTerms):
        """Set the trade terms for this caravan's mission."""
        self.trade_terms = terms
    
    def complete_trade(self, outcome: str, turn: int):
        """
        Mark the trade as completed with an outcome.
        
        Args:
            outcome: Description of the trade result
            turn: Turn number when trade was completed
        """
        self.is_trade_completed = True
        self.trade_outcome = outcome
        self.delivery_turn = turn
        
        # Emit trade completed event
        if event_bus:
            event_bus.emit(
                EventType.STATE_CHANGED,
                self,
                change_type='trade_completed',
                entity_id=self.entity_id,
                outcome=outcome,
                turn=turn
            )
    
    def get_cargo_summary(self) -> str:
        """Get a human-readable summary of the current cargo."""
        if self.cargo.is_empty():
            return "No cargo"
        
        capacity_used = (self.cargo.total_value() / self.max_capacity) * 100
        return f"{self.cargo} ({capacity_used:.1f}% capacity)"
    
    def get_trade_summary(self) -> str:
        """Get a human-readable summary of the trade mission."""
        if not self.trade_terms:
            return "No active trade mission"
        
        status = "Completed" if self.is_trade_completed else "In Progress"
        return f"{status}: {self.trade_terms}"
    
    def get_remaining_capacity(self) -> float:
        """Get remaining cargo capacity."""
        return self.max_capacity - self.cargo.total_value()
    
    def is_at_capacity(self) -> bool:
        """Check if cargo is at or over capacity."""
        return self.cargo.total_value() >= self.max_capacity
    
    def update(self, dt: float, event_bus=None):
        """Update component state (no regular updates needed for cargo)."""
        pass
    
    def get_lore_section(self) -> Optional[str]:
        """Return lore-friendly explanation of cargo mechanics."""
        return (
            "Trade caravans carry precious goods across the realm, bearing the hopes "
            "and wealth of their lords. Each caravan has limited capacity and operates "
            "under specific trade agreements. The success of these missions can strengthen "
            "alliances or spark conflicts between houses."
        )