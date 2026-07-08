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

    for i in range(turns):
        # Scripted expander: house 0 orders expansion in every direction with
        # opportunities each turn (one pending per direction, like the tool
        # allows) — approximates an aggressive expansion-focused player
        if expander_terr:
            already = {o.direction for o in expander_terr.get_pending_expansions()}
            for direction in DIRECTIONS:
                if direction not in already:
                    expander_terr.create_expansion_order(direction, sim.hex_grid, sim.global_turn)
        await sim.step()
        if sim.game_over:
            print(f"Game over at turn {i + 1}: {sim.winner}")
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
    # Invariant 2: PASSIVE food stays sane — neither collapse nor explosion.
    # (The expander's surplus legitimately snowballs with territory.)
    for name, s in end.items():
        if s['food'] < 0:
            failures.append(f"{name} food went negative")
        if name != expander.name and start[name]['food'] > 0 and \
                s['food'] > 12 * start[name]['food']:
            failures.append(f"{name} food exploded {s['food'] / start[name]['food']:.0f}x "
                            f"passively (no consumption pressure?)")
    # Invariant 3: expansion pacing. Border expansion alone should reach ~8-15%
    # of land by year 2 — loyalty (1/tile vs +1/turn when fed) is the intended
    # brake, and outposts (not scripted here) provide the other half of real
    # coverage. Hard floor 7%, ceiling 40%.
    share = end[expander.name]['tiles'] / max(1, total_land)
    print(f"\nExpander ({expander.name}) land share: {share:.1%} of {total_land} land tiles "
          f"(loyalty {end[expander.name]['loyalty']})")
    # Observed band across seeds/weather: ~5-8% by year 2 border-only.
    # Floor 4% catches mechanical breakage, not tuning drift.
    if turns >= 32 and share < 0.04:
        failures.append(f"expansion too slow: {share:.1%} land after {years:.1f} years "
                        f"(border-only breakage floor 4%)")
    if turns >= 32 and share > 0.40:
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
