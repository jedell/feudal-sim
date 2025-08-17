from typing import Dict, Tuple

from feudal_sim.core.config import config


def get_general_cap(territory_size: int) -> int:
    base_cap = config.get('simulation.subagents.max_generals_base', 1)
    tiles_per_extra = config.get('simulation.subagents.generals_per_tiles', 10)
    return base_cap + (territory_size // tiles_per_extra)


def get_deploy_costs(soldiers: int, workers: int) -> Dict[str, int]:
    base_gold = config.get('simulation.subagents.deploy_general.base_gold', 50)
    base_material = config.get('simulation.subagents.deploy_general.base_material', 30)
    gold_per_soldier = config.get('simulation.subagents.deploy_general.gold_per_soldier', 1)
    material_per_soldier = config.get('simulation.subagents.deploy_general.material_per_soldier', 1)
    gold_per_worker = config.get('simulation.subagents.deploy_general.gold_per_worker', 0)
    material_per_worker = config.get('simulation.subagents.deploy_general.material_per_worker', 1)
    total_gold = base_gold + soldiers * gold_per_soldier + workers * gold_per_worker
    total_material = base_material + soldiers * material_per_soldier + workers * material_per_worker
    return {'gold': total_gold, 'material': total_material}


def get_upkeep_costs(soldiers: int, workers: int) -> Tuple[int, int]:
    gold_per_soldier = config.get('simulation.subagents.upkeep.gold_per_soldier', 1)
    gold_per_worker = config.get('simulation.subagents.upkeep.gold_per_worker', 0)
    food_per_soldier = config.get('simulation.subagents.upkeep.food_per_soldier', 1)
    food_per_worker = config.get('simulation.subagents.upkeep.food_per_worker', 1)
    gold_cost = soldiers * gold_per_soldier + workers * gold_per_worker
    food_cost = soldiers * food_per_soldier + workers * food_per_worker
    return gold_cost, food_cost


def get_upkeep_thresholds() -> Tuple[int, int]:
    max_unpaid = config.get('simulation.subagents.upkeep.max_unpaid_turns', 2)
    morale_thresh = config.get('simulation.subagents.morale_disband_threshold', 10)
    return max_unpaid, morale_thresh 