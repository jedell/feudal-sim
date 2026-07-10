# Map & Spatial Mechanics — Feature Scope (F9)

**Status: F9a-F9d implemented 2026-07-10** (commits 668c788, abaea2d,
9c31b73, 9bd624e). Notable deviations: generals get 3 MP (not 2) to offset
terrain costs; swamp is passable (2.0 MP) but unclaimable (is_land False);
ICE_CAP generates only on cold-latitude peaks and may be absent on warm
seeds. Validation: scripts/map_gallery.py + balance harness, both green.

Scoped 2026-07-10 from two code surveys plus the grid-simulation spatial-
prompting playbook. Theme: the generator already builds real geography
(elevation, moisture, rivers, biomes) that gameplay then ignores; and agents
already collect spatial knowledge that their context never shows them.
Every item below connects an existing-but-dead pathway rather than building
new simulation depth.

Key diagnoses:
- Generals move at FLAT cost — terrain is cosmetic for maneuver (caravans'
  A* has terrain weights; generals' position.move_to does not).
- TerrainObservation persists observed tiles and even has
  get_passive_observation_text() — but no code path ever injects it. Agents
  forget the map between turns; hence 306 find_outpost_site calls / 28 builds.
- find_outpost_site names a destination but no route — scan, walk, re-scan.
- Lords get border summaries but no realm-shape or neighbor topology.
- elevation/moisture/temperature are generation-only; SWAMP and ICE_CAP never
  generate; resource nodes are placed by uniform random sampling;
  map_manager.py is dead (broken import, zero references).

---

## F9a. Terrain-aware movement (unify the two movement models)

Port the pathfinding cost table into general movement so mountains, forests,
and hills cost real MP (mountain 2.5, hill 1.5, forest 1.3, grassland 0.8 —
same table caravans already use; single source in config). Raise generals'
movement_points 2 -> 3 so effective mobility on open ground stays similar.
Chokepoints and defensible ground now emerge from the existing generator for
free, and the combat terrain-defense bonuses finally have a maneuver
counterpart. Movement tool results state the cost paid ("NE into hills —
1.5 MP"). Expansion cost gains a terrain-harshness multiplier
(mountain 1.5x, desert 1.2x, grassland 0.9x) in _estimate_expansion_cost.

**Files:** position.py, pathfinding.py (share table), general_toolset.py
(result strings), territory.py, config. **Effort:** S-M.

## F9b. Spatial memory + local map briefing (the core fix)

1. **Wire the existing passive observation** into the general's turn context
   (one line in _generate_turn_context_message; renderer already exists).
2. **Local tactical hex map**: a compact ASCII window (radius 2, ~19 tiles)
   with a legend, rendered from TerrainObservation memory + current view in
   every general turn context. Stale tiles lowercase/marked; unknown = "?".
   Terrain letter + ownership overlay (^ mountain, ~ water, F forest, .
   plains; UPPERCASE = enemy-held, * = settlement, @ = you). ~150 tokens.
   Memory semantics per the fog playbook: remembered terrain shows as known;
   remembered ENEMY UNITS are labeled memory, never truth.
3. **Lord neighbor topology**: one sentence per known house computed from
   border-contact directions and centroid bearing ("House Thornwall lies to
   your S and SW, nearest holdings 3 tiles away"), appended to the realm
   overview. No full realm map (125-tile ASCII is token-hostile; revisit
   only if topology sentences prove insufficient).
4. **Coordinate hygiene**: keep (q,r) in tool results (agents need stable
   handles) but make every coordinate mention carry a directional gloss
   ("(15,8) — 4 tiles NE of your capital"), instead of pretending
   coordinates don't exist while leaking them.

**Files:** components/ai.py, terrain_observation.py (map renderer),
territory.py, general_toolset.py. **Effort:** M.

## F9c. Routes, not re-scans

find_outpost_site computes and returns a ready route for its best candidate
using the existing A* ("route: move_along(['SE','SE','NE']) — ~4 MP over 2
turns"), and remembers it: the general's next turn context repeats the
active route and remaining steps until arrival or invalidation (target
claimed, path blocked — then it says so). navigate_home returns its full
multi-turn route the same way. This is the waypoint-compilation pattern:
one-shot targets become persistent itineraries, killing the
scan-walk-rescan loop.

**Files:** general_toolset.py, pathfinding.py (expose route-to-tile for
generals), subagent_group.py or terrain_observation.py (route storage).
**Effort:** S-M.

## F9d. Terrain generation upgrades

1. **Complete the biome set**: SWAMP in wet lowlands (elevation < 0.15,
   moisture > 0.75, temperate), ICE_CAP on cold peaks (elevation > 0.55,
   temp < 0.15). Two threshold branches in determine_terrain_type.
2. **Water-aware moisture**: after river carving, bump moisture on tiles
   within 2 of rivers/lakes and re-derive their biome — fertile river
   valleys emerge, making rivers economically strategic (the natural
   floodplain effect; no new mechanic needed, food follows moisture).
3. **Geological resource placement**: replace uniform random node placement
   with terrain-weighted placement — iron/stone adjacent to mountains, gold
   in hills, rare herbs in forest/swamp. Geography now creates contestable
   prizes and reasons to fight over specific regions.
4. **Config-expose generation knobs**: sea_percent, elevation bands, forest/
   temperature thresholds, heightmap roughness move to
   config world_generation (currently hardcoded).
5. **Delete map_manager.py** (dead: broken import, zero references).

**Files:** hex_grid.py, rivers.py, types.py, tile_extensions.py,
simulation.py (node placement), config. **Effort:** M.

## Explicitly not doing (and why)

- **River fords/bridges**: rivers stay impassable. With terrain-cost movement
  (F9a) and floodplain economies (F9d.2), rivers are already strategic as
  hard barriers + fertile corridors; crossing mechanics add rules without a
  present decision they'd improve. Revisit if maps generate isolated
  subcontinents.
- **Full-realm ASCII maps for lords**: token cost scales with territory;
  topology sentences first.
- **Hybrid tactical orchestrator** (deterministic per-unit controllers +
  low-frequency strategy LLM): the right long-term shape if general
  micro-behavior stays wasteful after F9b/F9c, but not before giving the
  LLM proper spatial context a chance.
- **Weather/terrain interaction, altitude temperature**: generation realism
  with no agent-visible decision attached.

## Sequencing

F9b.1 (one-line memory wire) and F9d.5 (delete dead file) are immediate.
Then F9c -> F9a -> F9b.2-4 -> F9d.1-4. F9a and F9d change balance: re-run
scripts/balance_check.py after each (movement costs slow general logistics;
floodplains shift food geography; the harness's expansion pacing band may
need retuning).

## Validation

- Harness invariants after F9a/F9d (pacing, passive economy).
- A generation gallery script: render N seeds' terrain distributions
  (% per biome, river reach, node placement) to eyeball variety — extends
  balance_check or a small scripts/map_gallery.py.
- Next LLM run metrics: find_outpost_site call count (expect: collapses),
  observe_area frequency, general stationary spans, outposts per deployed
  general — the replay-metrics discipline from the spatial playbook.
