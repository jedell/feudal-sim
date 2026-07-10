"""
Map generation gallery — sample N seeds and report terrain statistics.

Eyeball check for generation changes: biome distribution, water share,
swamp/ice presence, floodplain effect, and resource node placement by
terrain. No renderer, no LLM.

Usage:
    uv run python scripts/map_gallery.py            # 3 maps
    uv run python scripts/map_gallery.py --maps 5
"""

import argparse
import os
import sys
from collections import Counter

os.environ.pop('OPENAI_API_KEY', None)

from feudal_sim.core.config import config  # noqa: E402

config.load_config('simulation')
config.load_config('world')
config._config_data['simulation']['ai']['enabled'] = False
config._config_data['simulation'].setdefault('ai', {}).setdefault(
    'identity_generation', {})['enabled'] = False

from feudal_sim.core.simulation import Simulation  # noqa: E402
from feudal_sim.map.tile_extensions import get_resource_node_type, ResourceNodeType  # noqa: E402


def report(sim, idx: int) -> list:
    tiles = sim.hex_grid.tiles
    total = len(tiles)
    counts = Counter(t.terrain_type.name for t in tiles)
    print(f"\n=== Map {idx}: {total} tiles ===")
    for name, n in counts.most_common():
        print(f"  {name:<18}{n:>5}  {n / total:6.1%}")
    nodes = Counter()
    for t in tiles:
        nt = get_resource_node_type(t)
        if nt != ResourceNodeType.NONE:
            nodes[f"{nt.name} on {t.terrain_type.name}"] += 1
    if nodes:
        print("  Resource nodes:")
        for k, n in nodes.most_common():
            print(f"    {k}: {n}")
    problems = []
    land = sum(n for name, n in counts.items() if name not in ('OCEAN', 'LAKE', 'RIVER'))
    if land / total < 0.4:
        problems.append(f"land share low ({land / total:.0%})")
    if counts.get('RIVER', 0) == 0:
        problems.append("no river tiles generated")
    return problems


def main(n_maps: int) -> int:
    all_problems = []
    for i in range(n_maps):
        sim = Simulation(debug=True)
        all_problems += [f"map {i}: {p}" for p in report(sim, i)]
    if all_problems:
        print("\nWarnings:")
        for p in all_problems:
            print(f"  ! {p}")
    print("\nGallery complete.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--maps', type=int, default=3)
    sys.exit(main(parser.parse_args().maps))
