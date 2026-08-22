"""
Trade economics — resource valuation with per-house scarcity.

Resources have base values (config: simulation.trade.base_values) and each
house perceives them through a scarcity multiplier: a hungry house values
food at up to 2x base, a hoarder at as little as 0.5x. Surfacing each party's
own valuation of a deal is what makes mutually beneficial trades discoverable:
both sides can profit *in their own terms* on the same exchange.
"""

from typing import Dict

from feudal_sim.core.config import config
from feudal_sim.components.resource import ResourceComponent

BASE_VALUES = {'food': 1.0, 'material': 1.5, 'metal': 3.0, 'gold': 5.0}
SCARCITY_NORMS = {'food': 200.0, 'material': 150.0, 'metal': 60.0, 'gold': 100.0}


def base_value(resource: str) -> float:
    """Realm-wide base value of one unit of a resource."""
    return config.get(f'simulation.trade.base_values.{resource}', BASE_VALUES.get(resource, 1.0))


def scarcity_multiplier(house, resource: str) -> float:
    """How much MORE (or less) this house values a resource given its stocks:
    clamped to [0.5, 2.0] around a config norm stock level."""
    norm = config.get(f'simulation.trade.scarcity_norms.{resource}',
                      SCARCITY_NORMS.get(resource, 100.0))
    res_comp = house.get_component(ResourceComponent) if house else None
    stock = max(1.0, res_comp.resources.get(resource)) if res_comp else norm
    return max(0.5, min(2.0, norm / stock))


def perceived_value(house, goods: Dict[str, float]) -> float:
    """The worth of a bundle of goods in this house's eyes."""
    total = 0.0
    for resource, amount in (goods or {}).items():
        if amount and amount > 0:
            total += amount * base_value(resource) * scarcity_multiplier(house, resource)
    return total


def format_valuation(house, goods: Dict[str, float]) -> str:
    """One-line valuation summary for agent-facing messages."""
    value = perceived_value(house, goods)
    parts = [f"{amt:.0f} {res}" for res, amt in (goods or {}).items() if amt and amt > 0]
    bundle = ", ".join(parts) if parts else "nothing"
    return f"{bundle} (worth ~{value:.0f} to you at current stocks)"
