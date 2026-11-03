"""
Reward signal extraction — raw, untuned.

RLVR-style: everything here is computed programmatically from game state.
No LLM judges, no learned reward models. Reward *composition* (weights,
shaping) is deliberately out of scope for now — these are the raw signals
a reward function will combine later.
"""

from typing import Any, Dict

from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.components.territory import TerritoryComponent


def house_signals(simulation) -> Dict[str, Dict[str, Any]]:
    """Per-house observable state — the inputs to any reward function.

    Returns {house_name: {territory, food, material, metal, gold, population,
    loyalty, military_power, generals_deployed, alive}}.
    """
    from feudal_sim.components.ai import AIComponent

    out: Dict[str, Dict[str, Any]] = {}
    alive_ids = {h.id for h in simulation.houses}

    for house in simulation.houses:
        res: ResourceComponent = house.get_component(ResourceComponent)
        pop: PopulationComponent = house.get_component(PopulationComponent)
        terr: TerritoryComponent = house.get_component(TerritoryComponent)

        out[house.name] = {
            "territory": len(terr.territory) if terr else 0,
            "food": res.resources.food if res else 0.0,
            "material": res.resources.material if res else 0.0,
            "metal": res.resources.metal if res else 0.0,
            "gold": res.resources.gold if res else 0.0,
            "population": pop.population if pop else 0,
            "loyalty": pop.loyalty if pop else 0.0,
            "military_power": getattr(house, "military_power", 0),
            "generals_deployed": len(terr.deployed_generals) if terr else 0,
            "alive": True,
        }

    # Eliminated houses stay in the record with alive=False
    eliminated = getattr(simulation, "eliminated_houses", []) or []
    for name in eliminated:
        if name not in out:
            out[name] = {"alive": False}

    return out


def terminal_signals(simulation) -> Dict[str, Any]:
    """Episode-terminal signals."""
    return {
        "game_over": simulation.game_over,
        "winner": simulation.winner,
        "turn": simulation.global_turn,
    }
