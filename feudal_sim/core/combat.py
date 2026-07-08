"""
Combat resolution for general-to-general encounters.

Calculates combat outcomes from raw stats (soldiers, equipment, morale, terrain)
modified by tactical declarations made during the agentic contact event phase.
"""

import random
from dataclasses import dataclass
from typing import Optional

from feudal_sim.map.types import HexTileType


# ── Tactic counter matrix ─────────────────────────────────────────────────────
# (attacker_tactic, defender_tactic) → (attacker_multiplier, defender_multiplier)
# Values > 1.0 favour that side; < 1.0 penalise it.

TACTIC_MATRIX = {
    ('assault',   'defensive'): (0.85, 1.20),
    ('assault',   'flanking'):  (1.15, 0.85),
    ('assault',   'feint'):     (0.90, 1.15),
    ('assault',   'withdraw'):  (1.35, 0.65),
    ('flanking',  'defensive'): (1.30, 0.75),
    ('flanking',  'assault'):   (1.05, 0.95),
    ('flanking',  'feint'):     (0.85, 1.15),
    ('flanking',  'withdraw'):  (1.25, 0.75),
    ('defensive', 'assault'):   (1.15, 0.85),
    ('defensive', 'flanking'):  (0.80, 1.20),
    ('defensive', 'feint'):     (1.05, 0.95),
    ('defensive', 'withdraw'):  (1.10, 0.90),
    ('feint',     'assault'):   (1.20, 0.80),
    ('feint',     'defensive'): (0.90, 1.10),
    ('feint',     'flanking'):  (1.10, 0.90),
    ('feint',     'withdraw'):  (1.15, 0.85),
}

# Terrain gives a defence bonus to whoever holds the ground
TERRAIN_DEFENSE_MULT = {
    HexTileType.MOUNTAIN:         1.45,
    HexTileType.HILL:             1.25,
    HexTileType.TEMPERATE_FOREST: 1.15,
    HexTileType.BOREAL_FOREST:    1.10,
    HexTileType.RAINFOREST:       1.10,
    HexTileType.TUNDRA:           1.05,
    HexTileType.SWAMP:            1.10,
}

VALID_TACTICS = ('assault', 'flanking', 'defensive', 'feint', 'withdraw')


@dataclass
class CombatResult:
    attacker_wins: bool
    attacker_casualties: int
    defender_casualties: int
    attacker_final_soldiers: int
    defender_final_soldiers: int
    was_decisive: bool        # large margin — loser takes heavy losses
    attacker_score: float     # for transparency in narrative generation
    defender_score: float


def _equip_mult(equipment_level: int) -> float:
    """Unequipped soldiers fight at 30 % effectiveness; fully equipped at 100 %."""
    return 0.30 + 0.70 * max(0, min(100, equipment_level)) / 100.0


def calculate_combat_score(
    soldiers: int,
    equipment_level: int,
    morale: int,
    terrain_type: Optional[HexTileType] = None,
    is_defender: bool = False,
) -> float:
    terrain_mult = TERRAIN_DEFENSE_MULT.get(terrain_type, 1.0) if (is_defender and terrain_type) else 1.0
    return soldiers * _equip_mult(equipment_level) * (morale / 100.0) * terrain_mult


def resolve_combat(
    *,
    attacker_soldiers: int,
    attacker_equip: int,
    attacker_morale: int,
    defender_soldiers: int,
    defender_equip: int,
    defender_morale: int,
    attacker_tactic: str = 'assault',
    defender_tactic: str = 'defensive',
    terrain_type: Optional[HexTileType] = None,
    ambush: bool = False,
) -> CombatResult:
    """
    Resolve a combat encounter and return casualties + outcome.

    If ambush=True the defender takes an immediate 20 % pre-battle attrition
    before tactic modifiers are applied.
    """
    a_tactic = attacker_tactic if attacker_tactic in VALID_TACTICS else 'assault'
    d_tactic = defender_tactic if defender_tactic in VALID_TACTICS else 'defensive'

    # Ambush: defender takes shock casualties before the real fight
    if ambush:
        shock = int(defender_soldiers * 0.20)
        defender_soldiers = max(1, defender_soldiers - shock)
        defender_morale = max(10, defender_morale - 20)

    a_score = calculate_combat_score(attacker_soldiers, attacker_equip, attacker_morale)
    d_score = calculate_combat_score(defender_soldiers, defender_equip, defender_morale,
                                     terrain_type, is_defender=True)

    # Tactic interaction
    a_mult, d_mult = TACTIC_MATRIX.get((a_tactic, d_tactic), (1.0, 1.0))
    a_score *= a_mult
    d_score *= d_mult

    # ±10 % random variance — fog of war
    a_score *= random.uniform(0.90, 1.10)
    d_score *= random.uniform(0.90, 1.10)

    attacker_wins = a_score >= d_score

    # Casualty percentages scale with how decisively one side won
    margin = abs(a_score - d_score) / max(a_score + d_score, 1)
    if attacker_wins:
        a_cas_pct = random.uniform(0.04, 0.18)
        d_cas_pct = random.uniform(0.22, 0.42) + margin * 0.10
    else:
        a_cas_pct = random.uniform(0.22, 0.42) + margin * 0.10
        d_cas_pct = random.uniform(0.04, 0.18)

    a_cas = min(attacker_soldiers - 1, max(0, int(attacker_soldiers * a_cas_pct)))
    d_cas = min(defender_soldiers - 1, max(0, int(defender_soldiers * d_cas_pct)))

    max_pop = max(attacker_soldiers, defender_soldiers, 1)
    was_decisive = max(a_cas, d_cas) / max_pop > 0.30

    return CombatResult(
        attacker_wins=attacker_wins,
        attacker_casualties=a_cas,
        defender_casualties=d_cas,
        attacker_final_soldiers=attacker_soldiers - a_cas,
        defender_final_soldiers=defender_soldiers - d_cas,
        was_decisive=was_decisive,
        attacker_score=round(a_score, 1),
        defender_score=round(d_score, 1),
    )
