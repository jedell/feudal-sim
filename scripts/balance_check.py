"""
Headless balance harness — no LLM calls, no renderer.

Runs the simulation with AI disabled for a configurable number of turns and
checks economy/pacing invariants, plus an expansion-pacing scenario where one
house expands every turn like a scripted player. Use this to tune
config/simulation.json constants without burning LLM runs.

Usage:
    uv run python scripts/balance_check.py            # 32 turns (2 years)
    uv run python scripts/balance_check.py --turns 64
"""

import argparse
import asyncio
import os
import sys

# The harness must never call OpenAI: kill the key before any feudal_sim import
os.environ.pop('OPENAI_API_KEY', None)

from feudal_sim.core.config import config  # noqa: E402

config.load_config('simulation')
config.load_config('world')
# Force headless: no agent decisions, no LLM identity generation
config._config_data['simulation']['ai']['enabled'] = False
config._config_data['simulation'].setdefault('ai', {}).setdefault(
    'identity_generation', {})['enabled'] = False

from feudal_sim.components.population import PopulationComponent  # noqa: E402
from feudal_sim.components.resource import ResourceComponent  # noqa: E402
from feudal_sim.components.territory import TerritoryComponent  # noqa: E402
from feudal_sim.core.simulation import Simulation  # noqa: E402
from feudal_sim.map.types import HexTileType  # noqa: E402

DIRECTIONS = ["N", "NE", "SE", "S", "SW", "NW"]


def land_tiles(sim):
    return [t for t in sim.hex_grid.tiles
            if getattr(t, 'terrain_type', None) not in
            {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER}]


def snapshot(sim):
    rows = {}
    for house in sim.houses:
        res = house.get_component(ResourceComponent)
        pop = house.get_component(PopulationComponent)
        terr = house.get_component(TerritoryComponent)
        rows[house.name] = {
            'food': res.resources.food if res else 0,
            'gold': res.resources.gold if res else 0,
            'material': res.resources.material if res else 0,
            'pop': pop.population if pop else 0,
            'loyalty': pop.population_loyalty if pop else 0,
            'tiles': len(terr.territory) if terr else 0,
        }
    return rows


async def run(turns: int) -> int:
    sim = Simulation(debug=True)  # debug=True: no renderer
    start = snapshot(sim)
    expander = sim.houses[0]
    expander_terr = expander.get_component(TerritoryComponent)
    total_land = len(land_tiles(sim))

    expander_pop = expander.get_component(PopulationComponent)
    expander_res = expander.get_component(ResourceComponent)
    feasts_held = 0

    # sim.step() advances ONE PHASE; a game turn is 4 phases
    PHASES_PER_TURN = 4
    for i in range(turns * PHASES_PER_TURN):
        # Scripted expander: house 0 orders expansion in every direction with
        # opportunities each turn (one pending per direction, like the tool
        # allows) — approximates an aggressive expansion-focused player
        # ...but pauses while loyalty is dangerous, as any lord heeding the
        # 'revolt imminent' warnings would
        loyalty_ok = not expander_pop or expander_pop.population_loyalty >= 25
        if expander_terr and loyalty_ok:
            already = {o.direction for o in expander_terr.get_pending_expansions()}
            for direction in DIRECTIONS:
                if direction not in already:
                    expander_terr.create_expansion_order(direction, sim.hex_grid, sim.global_turn)
        # ...who also maintains legitimacy the way agents are instructed to:
        # feast when loyalty sags and the granary allows (emulates hold_feast)
        if expander_pop and expander_res and \
                expander_pop.population_loyalty < 50 and expander_res.resources.food >= 150:
            expander_res.resources.consume('food', 150)
            boost = config.get('simulation.population.feast.base_loyalty_boost', 8) + 3
            expander_pop.adjust_loyalty(boost)
            feasts_held += 1
        await sim.step()
        if sim.game_over:
            print(f"Game over at turn {(i // PHASES_PER_TURN) + 1}: {sim.winner}")
            break

    end = snapshot(sim)
    years = turns / 16.0
    print(f"\n=== Balance report after {turns} turns ({years:.1f} years) ===")
    print(f"{'house':<12}{'tiles':>6}{'Δtiles':>8}{'pop':>7}{'Δpop':>7}"
          f"{'loyalty':>9}{'food':>9}{'Δfood/wk':>10}{'gold':>8}")
    for name, s in end.items():
        s0 = start[name]
        print(f"{name:<12}{s['tiles']:>6}{s['tiles'] - s0['tiles']:>8}"
              f"{s['pop']:>7}{s['pop'] - s0['pop']:>7}{s['loyalty']:>9}"
              f"{s['food']:>9.0f}{(s['food'] - s0['food']) / max(1, turns):>10.1f}"
              f"{s['gold']:>8.0f}")

    failures = []
    # Invariant 1: no house starves out doing nothing on default settings
    for name, s in end.items():
        if s['pop'] <= 0:
            failures.append(f"{name} died out passively (pop 0)")
        if s['loyalty'] <= 10:
            failures.append(f"{name} loyalty collapsed passively ({s['loyalty']})")
    # Invariant 2: PASSIVE food equilibrates — spoilage should hold stocks
    # near the granary cap instead of letting them grow without bound.
    per_capita_storage = config.get('simulation.population.granary_capacity_per_capita', 6)
    for name, s in end.items():
        if s['food'] < 0:
            failures.append(f"{name} food went negative")
        if name != expander.name:
            cap = max(200, s['pop'] * per_capita_storage)
            if s['food'] > cap * 2:
                failures.append(f"{name} food {s['food']:.0f} is >2x its granary cap "
                                f"({cap:.0f}) — spoilage not binding")
    # Invariant 3: expansion pacing. With frontier starts and 6-tile orders an
    # aggressive expander saturates its reachable land fast by design (the
    # land-grab phase should end ~year 2, forcing the conflict phase). Floor
    # catches mechanical breakage; ceiling catches runaway costless expansion.
    share = end[expander.name]['tiles'] / max(1, total_land)
    print(f"\nExpander ({expander.name}) land share: {share:.1%} of {total_land} land tiles "
          f"(loyalty {end[expander.name]['loyalty']}, {feasts_held} feasts held)")
    if turns >= 16 and share < 0.10:
        failures.append(f"expansion too slow: {share:.1%} land after {years:.1f} years "
                        f"(breakage floor 10%)")
    if turns >= 16 and share > 0.60:
        failures.append(f"expansion too fast: {share:.1%} land after {years:.1f} years")

    if failures:
        print("\nFAILED invariants:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nAll balance invariants passed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--turns', type=int, default=32)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.turns)))
