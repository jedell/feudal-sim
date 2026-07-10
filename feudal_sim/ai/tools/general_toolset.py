"""
General toolset factory — assembles the full set of tools for a general entity's AI agent.
"""

from typing import Dict, List

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401
from feudal_sim.ai.tools.common import _balance_line, hex_distance
from feudal_sim.ai.tools.communication import create_rookery_toolset, end_turn
from feudal_sim.utils.observations import ObservationFormatter


def _home_gloss(sim_context, general_entity, q: int, r: int) -> str:
    """Directional gloss for a raw coordinate — ' (~4 tiles NE of home)'.
    Keeps coordinates usable as handles while grounding them spatially."""
    try:
        em = getattr(sim_context, 'entity_manager', None)
        house_id = getattr(general_entity, 'house_id', None)
        if not em or not house_id:
            return ""
        house = em.get_entity(house_id)
        from feudal_sim.components.territory import TerritoryComponent
        terr = house.get_component(TerritoryComponent) if house else None
        if not terr or not terr.territory:
            return ""
        best_d, best_tile = None, None
        for tile in list(terr.territory)[:20]:
            d = (abs(q - tile.q) + abs(r - tile.r) +
                 abs((-q - r) - (-tile.q - tile.r))) // 2
            if best_d is None or d < best_d:
                best_d, best_tile = d, tile
        if best_d is None or best_d == 0:
            return " (in home territory)"
        from feudal_sim.utils.directions import offset_to_bearing
        bearing = offset_to_bearing(best_tile.q - q, best_tile.r - r)
        return f" (home territory ~{best_d} tile(s) {bearing})"
    except Exception:
        return ""


def create_general_toolset(general_entity) -> list:
    """Create tools for general entities."""
    tools = []

        # Basic movement tool (direction-based for generals)
    from feudal_sim.components.position import PositionComponent

    @function_tool
    def move(ctx: RunContextWrapper["SimulationContext"], direction: str) -> str:
        """
        Move one tile in a direction (N, NE, SE, S, SW, NW).
        Consumes movement points and respects terrain/movement validation.
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Movement failed - map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Movement failed - position unknown"

        # Check if general has pending outpost construction requiring them to stay
        # Generals can move freely — outpost construction completes automatically
        # without requiring the general to remain on-site.
        valid_dirs = ["N", "NE", "SE", "S", "SW", "NW"]
        dir_upper = (direction or "").upper()
        if dir_upper not in valid_dirs:
            return f"Invalid direction '{direction}'. Valid directions: {', '.join(valid_dirs)}"
        q, r = pos.position
        # Find neighbor in the requested direction
        target = None
        for neigh, dirn in sim_context.hex_grid.get_neighbors(q, r):
            if dirn == dir_upper and neigh is not None:
                target = (neigh.q, neigh.r)
                break
        if not target:
            return f"Cannot move {dir_upper.lower()} from current position"
        result = pos.move_to(
            target_position=target,
            hex_grid=sim_context.hex_grid,
            current_turn=getattr(sim_context, 'current_turn', None),
            validate_movement=True,
        )
        return result.get('message', 'Move attempted')
    move.action_description = "**Move (direction)**: Advance one tile N/NE/SE/S/SW/NW (costs movement points)"
    tools.append(move)

    @function_tool
    def move_along(ctx: RunContextWrapper["SimulationContext"], steps: List[str]) -> str:
        """
        Execute a planned multi-step path in a single action.
        After observing the area, provide a list of directions to move through
        sequentially. Each step costs one movement point. Stops automatically
        if blocked by terrain or movement points run out — reports where you stopped.

        Prefer this over multiple move() calls whenever you know your intended path.

        Args:
            steps: Ordered list of directions, e.g. ["NE", "NE"] or ["N", "NW", "W"].
                   Maximum length is your remaining movement points.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Movement failed — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Movement failed — position unknown"

        valid_dirs = {"N", "NE", "SE", "S", "SW", "NW"}
        if not steps:
            return "No steps provided. Pass a list like [\"NE\", \"N\"]."

        completed = []
        stopped_reason = None

        for raw_dir in steps:
            dir_upper = str(raw_dir).upper().strip()
            if dir_upper not in valid_dirs:
                stopped_reason = f"invalid direction '{raw_dir}'"
                break

            neighbors = sim_context.hex_grid.get_neighbors(pos.position[0], pos.position[1])
            target = None
            for neigh, dirn in neighbors:
                if dirn == dir_upper and neigh is not None:
                    target = (neigh.q, neigh.r)
                    break

            if not target:
                stopped_reason = f"no tile in direction {dir_upper}"
                break

            result = pos.move_to(
                target_position=target,
                hex_grid=sim_context.hex_grid,
                current_turn=getattr(sim_context, 'current_turn', None),
                validate_movement=True,
            )

            if not result.get('success'):
                stopped_reason = result.get('message', f"blocked moving {dir_upper}")
                break

            terrain_name = ''
            try:
                tile = sim_context.hex_grid.get_tile(target[0], target[1])
                if tile:
                    raw = getattr(getattr(tile, 'terrain_type', None), 'name', '')
                    mapping = {
                        'GRASSLAND': 'plains', 'STEPPE': 'plains',
                        'TEMPERATE_FOREST': 'forest', 'BOREAL_FOREST': 'forest',
                        'HILL': 'hills', 'MOUNTAIN': 'mountains',
                        'TUNDRA': 'tundra', 'DESERT': 'desert',
                    }
                    terrain_name = mapping.get(raw, raw.lower())
                    owner = getattr(tile, 'owner', None)
                    owner_label = 'unowned' if not owner else (
                        'ours' if getattr(owner, 'id', None) == getattr(general_entity, 'house_id', None)
                        else getattr(owner, 'name', 'foreign')
                    )
                    step_cost = result.get('movement_cost', 1)
                    cost_label = f",{step_cost:g}MP" if step_cost != 1 else ""
                    completed.append(f"{dir_upper}({terrain_name},{owner_label}{cost_label})")
            except Exception:
                completed.append(dir_upper)

            remaining = getattr(pos, 'remaining_movement', '?')
            if isinstance(remaining, (int, float)) and remaining <= 0:
                if steps.index(raw_dir) < len(steps) - 1:
                    stopped_reason = "movement points exhausted"
                break

        path_str = " → ".join(completed) if completed else "no movement"
        q, r = pos.position
        remaining_mp = getattr(pos, 'remaining_movement', '?')
        home_gloss = _home_gloss(sim_context, general_entity, q, r)

        if stopped_reason:
            return (f"Moved {len(completed)}/{len(steps)} step(s): {path_str}. "
                    f"Stopped: {stopped_reason}. "
                    f"Position ({q},{r}){home_gloss}, {remaining_mp} movement point(s) remaining.")
        return (f"Moved {len(completed)}/{len(steps)} step(s): {path_str}. "
                f"Position ({q},{r}){home_gloss}, {remaining_mp} movement point(s) remaining.")
    move_along.action_description = "**Move Along Path**: Execute a planned sequence of steps in one action — prefer this over multiple move() calls"
    tools.append(move_along)

    # One-tile observation for simplicity
    from feudal_sim.components.terrain_observation import TerrainObservation

    @function_tool
    def observe_area(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Observe tiles within 2 tile radius around you and summarize threats, units, and opportunities.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Observation failed - map access not available"
        obs: TerrainObservation = general_entity.get_component(TerrainObservation)
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not obs or not pos or not pos.position:
            return "Observation failed - missing components or position"
        current_turn = getattr(sim_context, 'current_turn', 0)
        obs.observation_range = 2
        obs.observe_current_area(sim_context.hex_grid, pos.position, current_turn)
        # Fetch localized intelligence
        threats = obs.get_threats_in_area(pos.position, search_range=2)
        # Build summaries
        threat_counts: Dict[str, int] = {}
        for t in threats:
            threat_counts[t.threat_level] = threat_counts.get(t.threat_level, 0) + 1

        # Helper: map hex grid direction labels to prose
        dir_prose = {
            "N": "north",
            "NE": "northeast",
            "SE": "southeast",
            "S": "south",
            "SW": "southwest",
            "NW": "northwest",
            "CENTER": "here"
        }

        # Natural language landscape summary within 2 tiles
        hex_grid = sim_context.hex_grid
        from feudal_sim.map.city_extensions import format_city_display, has_city
        q0, r0 = pos.position

        # Ring 1: center + immediate neighbors (directional detail)
        tiles_in_radius = []
        center_tile = hex_grid.get_tile(q0, r0)
        if center_tile:
            tiles_in_radius.append((center_tile, "CENTER"))
        for neigh, dirn in hex_grid.get_neighbors(q0, r0):
            if neigh:
                tiles_in_radius.append((neigh, dirn))

        # Ring 2: tiles at exactly distance 2 (aggregate only)
        seen = {(q0, r0)} | {(t.q, t.r) for t, _ in tiles_in_radius if t}
        ring2_tiles = []
        for neigh1, _ in hex_grid.get_neighbors(q0, r0):
            if not neigh1:
                continue
            for neigh2, _ in hex_grid.get_neighbors(neigh1.q, neigh1.r):
                if neigh2 and (neigh2.q, neigh2.r) not in seen:
                    ring2_tiles.append(neigh2)
                    seen.add((neigh2.q, neigh2.r))

        def friendly_terrain(terr):
            if terr is None:
                return 'unknown'
            name = getattr(terr, 'value', str(terr)).lower()
            if '.' in name:
                name = name.split('.')[-1]
            mapping = {
                'grassland': 'plains',
                'temperate_forest': 'forest',
                'boreal_forest': 'forest',
                'rainforest': 'rainforest',
                'ice_cap': 'ice',
                'tundra': 'tundra',
                'desert': 'desert',
                'steppe': 'grassland',
                'hill': 'hills',
                'mountain': 'mountains',
                'ocean': 'ocean',
                'lake': 'lake',
                'river': 'river'
            }
            return mapping.get(name, name.replace('_', ' '))

        from feudal_sim.map.types import HexTileType as _HTT
        _IMPASSABLE = {_HTT.OCEAN, _HTT.LAKE, _HTT.RIVER, _HTT.ICE_CAP}

        terrain_counts_local: Dict[str, int] = {}
        ownership = {"ours": 0, "unowned": 0, "other": 0}
        owner_dirs: Dict[str, list] = {"ours": [], "unowned": []}
        other_owner_dirs: Dict[str, list] = {}
        city_highlights: list = []
        for tile, dirn in tiles_in_radius:
            terr_name = friendly_terrain(getattr(tile, 'terrain_type', None))
            terrain_counts_local[terr_name] = terrain_counts_local.get(terr_name, 0) + 1
            # Skip impassable tiles — water/ice is not claimable land
            if getattr(tile, 'terrain_type', None) in _IMPASSABLE:
                continue
            owner = getattr(tile, 'owner', None)
            if not owner:
                ownership["unowned"] += 1
                if dirn != "CENTER":
                    owner_dirs.setdefault("unowned", []).append(dir_prose.get(dirn, dirn))
            elif hasattr(owner, 'id') and owner.id == getattr(general_entity, 'house_id', None):
                ownership["ours"] += 1
                if dirn != "CENTER":
                    owner_dirs.setdefault("ours", []).append(dir_prose.get(dirn, dirn))
            else:
                ownership["other"] += 1
                if dirn != "CENTER":
                    name = getattr(owner, 'name', getattr(owner, 'id', 'other'))
                    other_owner_dirs.setdefault(name, []).append(dir_prose.get(dirn, dirn))
            if dirn != "CENTER" and has_city(tile):
                city_text = format_city_display(tile)
                if city_text:
                    city_highlights.append(f"{dirn}: {city_text}")

        terrain_sorted = sorted(terrain_counts_local.items(), key=lambda kv: kv[1], reverse=True)
        if terrain_sorted:
            primary = terrain_sorted[0][0]
            mix_text = f"mostly {primary}"
            if len(terrain_sorted) > 1:
                secondary = terrain_sorted[1][0]
                mix_text += f" with some {secondary}"
        else:
            mix_text = "mixed terrain"

        claims_text = ObservationFormatter.borders_summary(
            owner_dirs.get("ours", []), owner_dirs.get("unowned", []), other_owner_dirs
        )

        # Ring 2 aggregate: ownership and settlements
        ring2_unowned = 0
        ring2_enemy: Dict[str, int] = {}
        ring2_cities: list = []
        for tile in ring2_tiles:
            if getattr(tile, 'terrain_type', None) in _IMPASSABLE:
                continue
            r2_owner = getattr(tile, 'owner', None)
            if not r2_owner:
                ring2_unowned += 1
            elif not (hasattr(r2_owner, 'id') and r2_owner.id == getattr(general_entity, 'house_id', None)):
                name = getattr(r2_owner, 'name', str(r2_owner))
                ring2_enemy[name] = ring2_enemy.get(name, 0) + 1
            if has_city(tile):
                city_text_r2 = format_city_display(tile)
                if city_text_r2:
                    ring2_cities.append(city_text_r2)

        units_text = ""
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            nearby = sim_context.entity_manager.get_positioned_entities_near(pos.position, 2)
            friendly: list[str] = []
            enemy: list[str] = []
            for ent, dist in nearby:
                if ent.id == general_entity.id:
                    continue
                ent_name = getattr(ent, 'name', 'unknown')
                ent_pos = ent.get_component(PositionComponent)
                dist_word = "adjacent" if dist <= 1 else f"{dist} tiles away"
                # Determine rough direction for close units
                dir_label = dist_word
                if dist == 1 and ent_pos and ent_pos.position:
                    for nn, nd in hex_grid.get_neighbors(q0, r0):
                        if nn and (nn.q, nn.r) == ent_pos.position:
                            dir_label = dir_prose.get(nd, nd)
                            break
                house_id = getattr(ent, 'house_id', None) or getattr(ent, 'sender_house_id', None)
                if house_id == getattr(general_entity, 'house_id', None):
                    friendly.append(f"{ent_name} ({dir_label})")
                else:
                    enemy.append(f"{ent_name} ({dir_label})")
            if friendly:
                units_text += f" | Friendly: {', '.join(friendly)}"
            if enemy:
                units_text += f" | Enemy: {', '.join(enemy)}"

        intro = f"Immediate area ({mix_text})."
        own_text = f" Unowned tiles (1 tile): {ownership['unowned']}."
        threat_text = ""
        if threats:
            breakdown = ", ".join(f"{cnt} {lvl}" for lvl, cnt in threat_counts.items())
            threat_text = f" Threats: {breakdown}."

        city_text = ""
        if city_highlights:
            city_text = " | Settlements (1 tile): " + "; ".join(city_highlights[:3])

        dirs_text = f" | Borders: {claims_text}"

        # Extended range summary
        ext_parts = []
        if ring2_unowned:
            ext_parts.append(f"{ring2_unowned} unowned")
        for ename, cnt in ring2_enemy.items():
            ext_parts.append(f"{cnt} {ename} tiles")
        if ring2_cities:
            ext_parts.append("settlements: " + ", ".join(ring2_cities[:2]))
        ext_text = f" | Extended (2 tiles): {', '.join(ext_parts)}" if ext_parts else ""

        # Nearest friendly settlement — critical for outpost planning
        settlement_proximity_text = ""
        try:
            if hasattr(general_entity, 'house_id') and sim_context.entity_manager:
                ph = sim_context.entity_manager.get_entity(general_entity.house_id)
                from feudal_sim.components.city import CityComponent as _CC
                from feudal_sim.core.config import config as _cfg2
                _min_sp = int(_cfg2.get('simulation.settlements.min_spacing_tiles', 3))
                ph_cc = ph.get_component(_CC) if ph else None
                if ph_cc:
                    best_d, best_n = None, None
                    for _city in ph_cc.get_all_cities().values():
                        d2 = hex_distance((q0, r0), _city.position)
                        if best_d is None or d2 < best_d:
                            best_d, best_n = d2, getattr(_city, 'name', 'settlement')
                    if best_d is not None:
                        if best_d < _min_sp:
                            settlement_proximity_text = (
                                f" | Nearest settlement: {best_n} ({best_d} tile(s) away — "
                                f"need {_min_sp - best_d} more to build here)"
                            )
                        else:
                            settlement_proximity_text = (
                                f" | Nearest settlement: {best_n} ({best_d} tile(s) away — "
                                f"outpost spacing OK here)"
                            )
        except Exception:
            pass

        # Distance and direction to nearest friendly territory
        home_text = ""
        try:
            if hasattr(general_entity, 'house_id') and sim_context.entity_manager:
                ph = sim_context.entity_manager.get_entity(general_entity.house_id)
                if ph:
                    from feudal_sim.components.territory import TerritoryComponent as _TComp3
                    ph_terr = ph.get_component(_TComp3)
                    if ph_terr and ph_terr.territory:
                        best_d, best_dir = None, None
                        dir_vecs = {'N':(0,-1),'NE':(1,-1),'SE':(1,0),'S':(0,1),'SW':(-1,1),'NW':(-1,0)}
                        for t in list(ph_terr.territory)[:15]:
                            d = hex_distance((q0, r0), (t.q, t.r))
                            if best_d is None or d < best_d:
                                best_d = d
                                dq, dr = t.q-q0, t.r-r0
                                best_dir = min(dir_vecs, key=lambda k: abs(dir_vecs[k][0]-dq)+abs(dir_vecs[k][1]-dr))
                        if best_d == 0:
                            home_text = " | On friendly territory"
                        elif best_d is not None:
                            home_text = f" | Friendly territory: {best_d} tile(s) {best_dir.lower()}"
        except Exception:
            pass

        nl_report = intro + own_text + threat_text + dirs_text + city_text + ext_text + units_text + settlement_proximity_text + home_text

        return nl_report
    observe_area.action_description = "**Observe (2 tiles)**: Scan immediate surroundings and extended area"
    tools.append(observe_area)

    # Territory is claimed only through settlements (build_outpost).
    # The raw claim_territory tool has been removed — generals must establish
    # structures to bring land under their house's control.
    from feudal_sim.components.territory import TerritoryComponent

    # Establish a small outpost/camp on a controlled tile

    @function_tool
    def build_outpost(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Build an outpost/camp on your current tile (must be controlled by your house).
        Claims all valid, land, unowned tiles within 1 tile radius.
        Consumes house resources (configurable).
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Outpost construction failed - map access not available"
        position_comp: PositionComponent = general_entity.get_component(PositionComponent)
        if not position_comp or not position_comp.position:
            return "Outpost construction failed - position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Outpost construction failed - no parent house connection"
        parent_house = None
        if hasattr(sim_context, 'entity_manager') and sim_context.entity_manager:
            parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Outpost construction failed - cannot find parent house"
        house_territory = parent_house.get_component(TerritoryComponent)
        if not house_territory:
            return "Outpost construction failed - parent house has no territory management"

        # Must be built on a controlled tile
        q0, r0 = position_comp.position

        # Refuse if a pending outpost order already exists at this position for this general
        if house_territory and hasattr(house_territory, 'pending_outposts'):
            for existing in house_territory.pending_outposts:
                if existing.status == "pending" and (existing.q, existing.r) == (q0, r0):
                    turns_left = existing.turn_resolves - (getattr(sim_context, 'current_turn', 0))
                    return (f"Outpost already under construction here — completes in "
                            f"{max(0, turns_left)} turn(s). Stay on this tile.")

        center_tile = sim_context.hex_grid.get_tile(q0, r0)
        if not center_tile:
            return "Outpost construction failed - tile not found"
        # Allow building on unowned land OR already-owned house tiles
        owner = getattr(center_tile, 'owner', None)
        if owner is not None and hasattr(owner, 'id') and owner.id != parent_house.id:
            return "Outpost construction failed - this tile is controlled by another house"
        # Reject water/ice
        from feudal_sim.map.types import HexTileType as _HTT2
        if getattr(center_tile, 'terrain_type', None) in {_HTT2.OCEAN, _HTT2.LAKE, _HTT2.RIVER, _HTT2.ICE_CAP}:
            return "Outpost construction failed - cannot build on water or ice"
        # Cannot build over an existing settlement (city/outpost)
        try:
            from feudal_sim.map.city_extensions import has_city as _tile_has_city
            if _tile_has_city(center_tile):
                return "Outpost construction failed - a settlement already exists on this tile"
        except Exception:
            pass

        # Spacing constraint: enforce minimum distance from this house's settlements (cities/outposts)
        try:
            from feudal_sim.components.city import CityComponent
            from feudal_sim.core.config import config as _cfg
            min_spacing = int(_cfg.get('simulation.settlements.min_spacing_tiles', 3))
            nearest_dist = None
            nearest_name = None
            # Check against this house's existing settlements
            cc: CityComponent = parent_house.get_component(CityComponent)
            if cc:
                for city in cc.get_all_cities().values():
                    cq, cr = city.position
                    s1 = -q0 - r0
                    s2 = -cq - cr
                    dist = (abs(q0 - cq) + abs(r0 - cr) + abs(s1 - s2)) // 2
                    if nearest_dist is None or dist < nearest_dist:
                        nearest_dist = dist
                        nearest_name = getattr(city, 'name', 'settlement')
            # Check against this house's pending outpost orders
            if house_territory and hasattr(house_territory, 'pending_outposts'):
                for pending in house_territory.pending_outposts:
                    cq, cr = pending.q, pending.r
                    s1 = -q0 - r0
                    s2 = -cq - cr
                    dist = (abs(q0 - cq) + abs(r0 - cr) + abs(s1 - s2)) // 2
                    if nearest_dist is None or dist < nearest_dist:
                        nearest_dist = dist
                        nearest_name = 'outpost site'
            if nearest_dist is not None and nearest_dist < min_spacing:
                still_needed = min_spacing - nearest_dist
                return (
                    f"Outpost construction failed — '{nearest_name}' is only {nearest_dist} tile(s) away "
                    f"(minimum {min_spacing}). Advance at least {still_needed} more tile(s) away from "
                    f"'{nearest_name}' before building."
                )
        except Exception:
            pass

        # Costs from config
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.core.config import config
        res_comp: ResourceComponent = parent_house.get_component(ResourceComponent)
        if not res_comp:
            return "Outpost construction failed - parent house cannot manage resources"
        outpost_mat = int(config.get('simulation.settlements.outpost.material_cost', 15))
        outpost_gold = int(config.get('simulation.settlements.outpost.gold_cost', 10))
        costs = {}
        if outpost_mat > 0:
            costs['material'] = outpost_mat
        if outpost_gold > 0:
            costs['gold'] = outpost_gold
        if costs and not res_comp.can_afford_action(costs):
            return f"Outpost construction failed - insufficient resources (need {outpost_mat} material, {outpost_gold} gold)"

        # Identify claimable neighbors within 1 tile radius
        from feudal_sim.map.types import HexTileType
        hex_grid = sim_context.hex_grid
        to_claim = []
        # Include immediate neighbors only (not center)
        for neigh, _dirn in hex_grid.get_neighbors(q0, r0):
            if not neigh:
                continue
            if getattr(neigh, 'owner', None):
                continue  # already owned
            terr = getattr(neigh, 'terrain_type', None)
            if terr in {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}:
                continue  # water tiles and ice caps cannot be claimed
            to_claim.append(neigh)

        # Consume resources, build, and claim
        if costs:
            res_comp.consume_for_action(costs, 'Build Outpost (Order)')

        # Mark tile as pending construction for the renderer
        center_tile._pending_outpost = True

        # Create delayed outpost construction order (resolves next week).
        # Use simulation.global_turn (never resets) so season rollover doesn't strand orders.
        from feudal_sim.components.territory import TerritoryComponent as _Terr
        sim_obj = getattr(sim_context, 'simulation', None)
        current_turn = getattr(sim_obj, 'global_turn', None) or getattr(sim_context, 'current_turn', 0)
        house_territory: _Terr = parent_house.get_component(_Terr)
        delay = int(config.get('simulation.settlements.outpost_delay_turns', 1))
        required_general_id = getattr(general_entity, 'id', '')
        required_general_name = getattr(general_entity, 'name', 'General')
        house_territory.create_outpost_order((q0, r0), current_turn, delay_turns=delay, resource_cost=costs, required_general_id=required_general_id, required_general_name=required_general_name)

        # Group adjustments and observations (order placed)
        try:
            from feudal_sim.components.subagent_group import SubAgentGroup
            grp = general_entity.get_component(SubAgentGroup)
            if grp:
                grp.consume_supplies(2)
                grp.record_action_result(True, experience_gained=1)
        except Exception:
            pass

        # Notify house AI about order timing
        try:
            from feudal_sim.components.ai import AIComponent
            ai = parent_house.get_component(AIComponent)
            if ai:
                ai.add_observation(
                    "Outpost construction ordered at a controlled site; completion expected next week",
                    phase="Actions"
                )
        except Exception:
            pass

        balance = _balance_line(res_comp, ['material', 'gold'])
        return f"Outpost construction ordered; remain on this tile until completion next week. {balance}"
    build_outpost.action_description = "**Build Outpost**: Establish a small camp on controlled land to claim adjacent unowned tiles (costs resources; the ordering general must remain on the tile until completion)"
    tools.append(build_outpost)

    # Find valid outpost site tool
    @function_tool
    def find_outpost_site(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Scan all six directions simultaneously to find valid outpost locations.
        Returns a ranked list of the best options and explains why each blocked
        direction is blocked. Call this ONCE before deciding where to move —
        no need to call it six times.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Cannot scan — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Cannot scan — position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Cannot scan — no parent house"
        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Cannot scan — parent house not found"

        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.territory import TerritoryComponent
        from feudal_sim.core.config import config as _cfg
        from feudal_sim.map.city_extensions import has_city as _has_city
        from feudal_sim.map.types import HexTileType

        IMPASSABLE = {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}
        min_spacing = int(_cfg.get('simulation.settlements.min_spacing_tiles', 3))
        cc = parent_house.get_component(CityComponent)
        terr = parent_house.get_component(TerritoryComponent)

        def _settlement_dist(q, r):
            best = None
            if cc:
                for city in cc.get_all_cities().values():
                    d = hex_distance((q, r), city.position)
                    if best is None or d < best:
                        best = d
            if terr and hasattr(terr, 'pending_outposts'):
                for p in terr.pending_outposts:
                    d = hex_distance((q, r), (p.q, p.r))
                    if best is None or d < best:
                        best = d
            return best

        hex_grid = sim_context.hex_grid
        q, r = pos.position
        ALL_DIRS = ['N', 'NE', 'SE', 'S', 'SW', 'NW']
        valid_options = []   # (steps, direction, terrain_name)
        dir_status = {}      # direction -> brief status string

        for dir_upper in ALL_DIRS:
            current = (q, r)
            found = False
            for steps in range(1, 13):
                neighbor = hex_grid.get_neighbor(current[0], current[1], dir_upper)
                if not neighbor:
                    dir_status[dir_upper] = f"edge of map at {steps} tile(s)"
                    break
                current = (neighbor.q, neighbor.r)
                terrain = getattr(neighbor, 'terrain_type', None)
                if terrain in IMPASSABLE:
                    dir_status[dir_upper] = f"water/ice at {steps} tile(s)"
                    break
                owner = getattr(neighbor, 'owner', None)
                # Can build on unowned OR own land; block only enemy-owned
                if owner is not None and getattr(owner, 'id', None) != general_entity.house_id:
                    dir_status[dir_upper] = f"blocked by {getattr(owner, 'name', 'enemy')} territory"
                    break
                if _has_city(neighbor):
                    continue
                sdist = _settlement_dist(current[0], current[1])
                if sdist is not None and sdist < min_spacing:
                    still_needed = min_spacing - sdist
                    if steps == 12:
                        dir_status[dir_upper] = f"all owned tiles too close to existing settlement (need {still_needed} more)"
                    continue
                terrain_name = terrain.name.lower().replace('_', ' ') if terrain else 'land'
                valid_options.append((steps, dir_upper, terrain_name, current))
                dir_status[dir_upper] = f"✓ valid site at {steps} tile(s) ({terrain_name})"
                found = True
                break
            if not found and dir_upper not in dir_status:
                dir_status[dir_upper] = "no owned territory in range"

        if not valid_options:
            status_lines = "\n".join(f"  {d}: {dir_status.get(d,'?')}" for d in ALL_DIRS)
            return (
                "No valid outpost site found in any direction.\n"
                f"{status_lines}\n"
                "You may be on a coastline or at the edge of your territory. "
                "Consider moving back toward the interior of your territory."
            )

        valid_options.sort()
        best_steps, best_dir, best_terrain, best_coord = valid_options[0]
        route = [best_dir] * best_steps
        # Remember the itinerary — it re-renders in your context each turn
        # until you arrive or the site becomes invalid
        from feudal_sim.components.subagent_group import SubAgentGroup as _SAG
        grp = general_entity.get_component(_SAG)
        if grp:
            grp.active_route = {
                'target': best_coord,
                'purpose': f"outpost site ({best_terrain})",
                'issued_turn': getattr(sim_context, 'current_turn', 0),
            }
        mp_per_turn = getattr(pos, 'movement_points', 2) or 2
        turns_needed = -(-best_steps // mp_per_turn)  # ceil
        lines = [
            f"Best site: {best_steps} tile(s) {best_dir} ({best_terrain}).",
            f"Route: move_along({route}) — ~{turns_needed} turn(s) of marching, then build_outpost().",
            "This route is remembered and will appear in your briefing until you arrive.",
        ]
        if len(valid_options) > 1:
            alts = ", ".join(f"{s} tile(s) {d}" for s, d, _t, _c in valid_options[1:3])
            lines.append(f"Alternatives: {alts}.")
        lines.append("All directions:")
        for d in ALL_DIRS:
            lines.append(f"  {d}: {dir_status.get(d, '?')}")
        return "\n".join(lines)
    find_outpost_site.action_description = "**Find Outpost Site**: Scan all directions at once — call once to get ranked valid build locations"
    tools.append(find_outpost_site)

    # Intercept caravan tool
    @function_tool
    def intercept_caravan(ctx: RunContextWrapper["SimulationContext"], direction: str, action: str) -> str:
        """
        Intercept an enemy trade caravan in the given direction.

        Actions:
          raid          — steal 40% of cargo; caravan continues damaged
          seize         — take all cargo and destroy the caravan entirely
          demand_tribute — take 15% as a toll; caravan continues
          let_pass      — stand aside and allow the caravan to pass

        Args:
            direction: Direction where the caravan was spotted (north, northeast, etc.)
            action: One of: raid, seize, demand_tribute, let_pass
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager or not sim_context.hex_grid:
            return "Cannot intercept — no simulation access"

        action = action.lower().strip()
        valid_actions = ('raid', 'seize', 'demand_tribute', 'let_pass')
        if action not in valid_actions:
            return f"Invalid action '{action}'. Choose from: {', '.join(valid_actions)}"

        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Cannot intercept — position unknown"

        gen_house = getattr(general_entity, 'house_id', None)
        if not gen_house:
            return "Cannot intercept — no parent house"

        # Find the caravan: check current tile and all adjacent tiles
        from feudal_sim.components.cargo import CargoComponent
        em = sim_context.entity_manager
        caravans = em.get_entities_by_type('caravan') or []
        gq, gr = pos.position

        target_caravan = None
        for caravan in caravans:
            car_house = getattr(caravan, 'sender_house_id', None)
            if not car_house or car_house == gen_house:
                continue
            cpos = caravan.get_component(PositionComponent)
            if not cpos or not cpos.position:
                continue
            dist = hex_distance((gq, gr), cpos.position)
            if dist <= 1:
                target_caravan = caravan
                break

        if not target_caravan:
            return "No enemy caravan found nearby to intercept"

        if action == 'let_pass':
            return f"You allow {target_caravan.name} to pass without incident."

        cargo_comp = target_caravan.get_component(CargoComponent)
        if not cargo_comp:
            return "Caravan has no cargo to intercept"

        cargo = cargo_comp.cargo
        total_value = cargo.food + cargo.material + cargo.metal + cargo.gold
        if total_value <= 0:
            return f"Caravan {target_caravan.name} is empty — nothing to take."

        # Determine what fraction to take
        if action == 'seize':
            fraction = 1.0
        elif action == 'raid':
            fraction = 0.40
        else:  # demand_tribute
            fraction = 0.15

        # Transfer goods to general's parent house
        from feudal_sim.components.resource import ResourceComponent
        parent_house = em.get_entity(gen_house)
        house_res = parent_house.get_component(ResourceComponent) if parent_house else None

        taken_parts = []
        for resource in ('food', 'material', 'metal', 'gold'):
            available = getattr(cargo, resource, 0)
            if available <= 0:
                continue
            amount = available * fraction
            setattr(cargo, resource, available - amount)
            if house_res:
                house_res.resources.add(resource, amount)
            taken_parts.append(f"{amount:.0f} {resource}")

        taken_str = ", ".join(taken_parts) if taken_parts else "nothing"

        # Seize: destroy the caravan
        if action == 'seize':
            try:
                em.destroy_entity(target_caravan.id)
            except Exception:
                pass

        # Notify both lords via rookery ravens
        gen_name = general_entity.name
        car_owner_id = getattr(target_caravan, 'sender_house_id', None)
        car_owner = em.get_entity(car_owner_id) if car_owner_id else None
        car_owner_name = car_owner.name if car_owner else "unknown"

        from feudal_sim.components.ai import AIComponent
        from feudal_sim.components.rookery import RookeryComponent

        # Alert the caravan owner's lord
        if car_owner:
            owner_ai: AIComponent = car_owner.get_component(AIComponent)
            if owner_ai:
                action_word = {"raid": "raided", "seize": "seized", "demand_tribute": "levied tribute on"}[action]
                owner_ai.add_observation(
                    f"Your {target_caravan.name} was {action_word} by {gen_name} of House "
                    f"{getattr(parent_house, 'name', gen_house)}. Taken: {taken_str}.",
                    phase="Events"
                )

        # Report to own lord
        gen_rookery = general_entity.get_component(RookeryComponent)
        if gen_rookery and gen_house in gen_rookery.get_known_recipients_list():
            action_word = {"raid": "raided", "seize": "seized", "demand_tribute": "levied tribute on"}[action]
            gen_rookery.send_raven(
                gen_house,
                f"Field report: {action_word} {target_caravan.name} from House {car_owner_name}. "
                f"Taken: {taken_str}."
            )

        action_phrase = {
            'raid':           f"Raid successful — took {taken_str}. Caravan continues.",
            'seize':          f"Caravan seized — took {taken_str}. {target_caravan.name} destroyed.",
            'demand_tribute': f"Tribute collected — took {taken_str}. Caravan allowed to pass.",
        }
        return action_phrase[action]
    intercept_caravan.action_description = "**Intercept Caravan**: Raid, seize, or demand tribute from a nearby enemy caravan"
    tools.append(intercept_caravan)

    # Besiege tool — assault an adjacent enemy settlement
    @function_tool
    def besiege(ctx: RunContextWrapper["SimulationContext"], direction: str) -> str:
        """
        Launch an assault on an enemy settlement (outpost or capital) in the given direction.

        On SUCCESS: the settlement is destroyed, tiles revert to unowned, and your house
        loots a share of the enemy's resources. Massive strategic gain.
        On FAILURE: your forces take heavy casualties and must withdraw.

        Requires: at least 20 soldiers, adjacent to enemy settlement, enemy tile within 1 tile.

        Args:
            direction: Direction of the target settlement (N, NE, SE, S, SW, NW)
        """
        import random as _random
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not sim_context.entity_manager:
            return "Siege failed — no map access"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Siege failed — position unknown"
        from feudal_sim.components.subagent_group import SubAgentGroup
        grp = general_entity.get_component(SubAgentGroup)
        if not grp or grp.assigned_population.soldiers < 20:
            return "Siege requires at least 20 soldiers"

        valid_dirs = {'N', 'NE', 'SE', 'S', 'SW', 'NW'}
        dir_upper = direction.upper().strip()
        if dir_upper not in valid_dirs:
            return f"Invalid direction '{direction}'"

        hex_grid = sim_context.hex_grid
        gq, gr = pos.position
        target_tile = hex_grid.get_neighbor(gq, gr, dir_upper)
        if not target_tile:
            return f"No tile in direction {direction}"

        # Verify there's an enemy settlement there
        from feudal_sim.map.city_extensions import CityType, get_city_info
        city_info, dev_level, _ = get_city_info(target_tile)
        if city_info == CityType.NONE:
            return f"No settlement found to the {direction}. Use observe_area first to confirm target."

        tile_owner = getattr(target_tile, 'owner', None)
        if not tile_owner or getattr(tile_owner, 'id', None) == getattr(general_entity, 'house_id', None):
            return "Cannot besiege your own settlement."

        enemy_house_id = getattr(tile_owner, 'id', None)
        enemy_house_name = getattr(tile_owner, 'name', 'enemy')
        settlement_name = getattr(target_tile, '_city_name', f"{enemy_house_name} settlement")

        # Combat resolution
        equip_mult = 0.30 + 0.70 * (grp.equipment_level / 100.0)
        morale_mult = grp.morale / 100.0
        attacker_power = grp.assigned_population.soldiers * equip_mult * morale_mult

        # Defence: base 20 + 15 per development level, times the tier's
        # fortification multiplier (walls, castle); capitals are much harder
        from feudal_sim.components.city import get_tier as _get_tier
        base_defence = (20 + dev_level * 15) * _get_tier(dev_level).get('defense_mult', 1.0)
        if city_info == CityType.CAPITAL:
            base_defence *= 3
        defender_power = base_defence * _random.uniform(0.8, 1.2)

        success = attacker_power >= defender_power * _random.uniform(0.7, 1.3)

        # --- Outcome ---
        from feudal_sim.components.ai import AIComponent
        from feudal_sim.components.city import CityComponent
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.components.territory import TerritoryComponent

        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        enemy_house  = sim_context.entity_manager.get_entity(enemy_house_id) if enemy_house_id else None

        if success:
            # Loot: steal 30-50 % of enemy's food, material, gold
            loot_parts = []
            if enemy_house:
                enemy_res = enemy_house.get_component(ResourceComponent)
                our_res   = parent_house.get_component(ResourceComponent) if parent_house else None
                if enemy_res and our_res:
                    loot_pct = _random.uniform(0.30, 0.50)
                    for res in ('food', 'material', 'metal', 'gold'):
                        available = getattr(enemy_res.resources, res, 0)
                        if available > 5:
                            amount = available * loot_pct
                            enemy_res.resources.consume(res, amount)
                            our_res.resources.add(res, amount)
                            loot_parts.append(f"+{amount:.0f} {res}")

            # Destroy the settlement: remove city encoding, revert tile
            try:
                if enemy_house:
                    city_comp = enemy_house.get_component(CityComponent)
                    if city_comp:
                        for cname, city in list(city_comp.get_all_cities().items()):
                            if city.position == (target_tile.q, target_tile.r):
                                # Use the public remove path if available, else direct
                                try:
                                    city_comp.remove_city(cname)
                                except Exception:
                                    try:
                                        city_comp._cities.pop(cname, None)
                                    except Exception:
                                        pass
                                break
                # Clear city encoding (restore population_capacity to base)
                if target_tile.population_capacity > 1000:
                    from feudal_sim.map.city_extensions import get_base_population_capacity
                    target_tile.population_capacity = get_base_population_capacity(target_tile)
                if hasattr(target_tile, '_city_name'):
                    del target_tile._city_name
                # Revert tile to unowned
                enemy_terr = enemy_house.get_component(TerritoryComponent) if enemy_house else None
                if enemy_terr:
                    enemy_terr.remove_territory([target_tile], hex_grid)
            except Exception as _e:
                import logging as _lg
                _lg.getLogger('feudal_sim').warning(f"⚠️  Siege settlement removal: {_e}")

            # Attacker takes light casualties (victory)
            casualty_pct = _random.uniform(0.05, 0.15)
            casualties = int(grp.assigned_population.soldiers * casualty_pct)
            grp.assigned_population.soldiers = max(1, grp.assigned_population.soldiers - casualties)
            grp.adjust_morale(10)
            grp.experience += 5

            loot_str = ", ".join(loot_parts) if loot_parts else "minimal loot"
            result_msg = (f"SIEGE SUCCESSFUL: {settlement_name} has fallen! "
                          f"Loot: {loot_str}. Our casualties: {casualties}. "
                          f"The settlement is destroyed and its tiles freed.")

            # A fallen CAPITAL ends the house: lands pass to the conqueror
            from feudal_sim.core.config import config as _victory_cfg
            if city_info == CityType.CAPITAL and _victory_cfg.get('simulation.victory.capital_elimination', True):
                sim = getattr(sim_context, 'simulation', None)
                if sim and enemy_house and parent_house:
                    sim.eliminate_house(
                        enemy_house, parent_house,
                        cause=f"capital {settlement_name} stormed by {general_entity.name}")
                    result_msg += (f" HOUSE {enemy_house_name.upper()} IS DESTROYED — "
                                   f"their remaining lands pass to your house!")
        else:
            # Repulsed — heavy casualties
            casualty_pct = _random.uniform(0.20, 0.40)
            casualties = int(grp.assigned_population.soldiers * casualty_pct)
            grp.assigned_population.soldiers = max(1, grp.assigned_population.soldiers - casualties)
            grp.adjust_morale(-20)
            result_msg = (f"SIEGE REPULSED: Assault on {settlement_name} failed. "
                          f"Our forces took {casualties} casualties and were driven back.")

        # Notify both lords via their AI components
        gen_name = general_entity.name
        if parent_house:
            lord_ai = parent_house.get_component(AIComponent)
            if lord_ai:
                lord_ai.add_observation(
                    f"Field report: {gen_name} {'seized' if success else 'failed to seize'} "
                    f"{settlement_name} of House {enemy_house_name}. {result_msg}",
                    phase="Events"
                )
                lord_ai.record_journal_entry(
                    f"Siege of {settlement_name} ({enemy_house_name}) — "
                    f"{'success, settlement destroyed' if success else 'repulsed'}")
        if enemy_house:
            enemy_ai = enemy_house.get_component(AIComponent)
            if enemy_ai:
                enemy_ai.add_observation(
                    f"SIEGE ALERT: {gen_name} of House "
                    f"{getattr(parent_house, 'name', '?') if parent_house else '?'} "
                    f"has {'destroyed' if success else 'attacked'} {settlement_name}!",
                    phase="Events"
                )
                enemy_ai.record_journal_entry(
                    f"{settlement_name} {'destroyed' if success else 'attacked'} by "
                    f"House {getattr(parent_house, 'name', '?') if parent_house else '?'}")

        return result_msg
    besiege.action_description = "**Besiege**: Assault an adjacent enemy settlement — destroy it and loot their resources"
    tools.append(besiege)

    # Navigate home tool — move toward nearest friendly territory
    @function_tool
    def navigate_home(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Move one step toward the nearest tile of your house's territory.
        Useful when lost, cut off, or returning from a distant operation.
        Costs one movement point.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not sim_context.entity_manager:
            return "Navigation failed — no map access"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Navigation failed — position unknown"
        if not hasattr(general_entity, 'house_id'):
            return "Navigation failed — no parent house"
        parent_house = sim_context.entity_manager.get_entity(general_entity.house_id)
        if not parent_house:
            return "Navigation failed — parent house not found"
        from feudal_sim.components.territory import TerritoryComponent as _TComp4
        ph_terr = parent_house.get_component(_TComp4)
        if not ph_terr or not ph_terr.territory:
            return "Navigation failed — house has no territory"
        gq, gr = pos.position
        # Find nearest friendly tile
        best_tile, best_dist = None, None
        for t in ph_terr.territory:
            d = hex_distance((gq, gr), (t.q, t.r))
            if best_dist is None or d < best_dist:
                best_dist, best_tile = d, t
        if best_dist == 0:
            return "Already on friendly territory."
        if best_tile is None:
            return "No friendly territory found."
        # Step one tile toward the target
        hex_grid = sim_context.hex_grid
        dir_offsets = {'N':(0,-1),'NE':(1,-1),'SE':(1,0),'S':(0,1),'SW':(-1,1),'NW':(-1,0)}
        best_move, best_move_dist = None, best_dist
        for dirn, (dq, dr) in dir_offsets.items():
            nb = hex_grid.get_neighbor(gq, gr, dirn)
            if not nb:
                continue
            d = hex_distance((nb.q, nb.r), (best_tile.q, best_tile.r))
            if d < best_move_dist:
                best_move_dist, best_move = d, (nb.q, nb.r)
        if not best_move:
            return "No clear path toward friendly territory this turn."
        result = pos.move_to(best_move, hex_grid,
                             getattr(sim_context, 'current_turn', None),
                             validate_movement=True)
        if result.get('success'):
            # Remember the homeward itinerary and hand back the full route so
            # the rest of the march is a single move_along next turn
            route_text = ""
            try:
                from feudal_sim.components.pathfinding import PathfindingComponent
                from feudal_sim.utils.directions import path_to_directions
                pf = PathfindingComponent('nav')
                path = pf.find_path(best_move, (best_tile.q, best_tile.r), hex_grid,
                                    entity_house_id=general_entity.house_id)
                if path and len(path) > 1:
                    dirs = path_to_directions(path)
                    if dirs:
                        route_text = f" Remaining route home: move_along({dirs})."
                from feudal_sim.components.subagent_group import SubAgentGroup as _SAG2
                grp = general_entity.get_component(_SAG2)
                if grp:
                    grp.active_route = {
                        'target': (best_tile.q, best_tile.r),
                        'purpose': 'return to friendly territory',
                        'issued_turn': getattr(sim_context, 'current_turn', 0),
                    }
            except Exception as _e:
                import logging as _lg
                _lg.getLogger('feudal_sim').warning(f"navigate_home route computation failed: {_e}")
            return (f"Moved toward friendly territory — now {best_move_dist} tile(s) away. "
                    f"{result.get('message', '')}{route_text}")
        return f"Movement blocked: {result.get('message', 'unknown obstacle')}"
    navigate_home.action_description = "**Navigate Home**: Move one step toward nearest friendly territory — use when lost or returning"
    tools.append(navigate_home)

    # Forage tool — gather supplies from terrain, costs all movement this turn
    @function_tool
    def forage(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Forage for supplies from the surrounding terrain.
        Yield depends on terrain richness. Costs all remaining movement points this turn —
        you cannot move after foraging.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid:
            return "Foraging failed — map access not available"
        pos: PositionComponent = general_entity.get_component(PositionComponent)
        if not pos or not pos.position:
            return "Foraging failed — position unknown"
        from feudal_sim.components.subagent_group import SubAgentGroup
        from feudal_sim.map.types import HexTileType
        grp: SubAgentGroup = general_entity.get_component(SubAgentGroup)
        if not grp:
            return "Foraging failed — no group component"
        if pos.remaining_movement <= 0:
            return "Cannot forage — no movement points remaining this turn"

        # Terrain yield map (supply points per tile)
        FORAGE_YIELD = {
            HexTileType.TEMPERATE_FOREST: 25, HexTileType.RAINFOREST: 25,
            HexTileType.BOREAL_FOREST: 18, HexTileType.GRASSLAND: 14,
            HexTileType.STEPPE: 12, HexTileType.HILL: 8,
            HexTileType.TUNDRA: 6, HexTileType.SWAMP: 5,
            HexTileType.MOUNTAIN: 4, HexTileType.DESERT: 3,
        }
        IMPASSABLE = {HexTileType.OCEAN, HexTileType.LAKE, HexTileType.RIVER, HexTileType.ICE_CAP}

        # Score center tile + immediate neighbors, take the best
        hex_grid = sim_context.hex_grid
        q, r = pos.position
        tiles_to_check = []
        center = hex_grid.get_tile(q, r)
        if center:
            tiles_to_check.append(center)
        for neigh, _ in hex_grid.get_neighbors(q, r):
            if neigh:
                tiles_to_check.append(neigh)

        best_yield = 0
        best_terrain = "unknown"
        for tile in tiles_to_check:
            tt = getattr(tile, 'terrain_type', None)
            if tt in IMPASSABLE:
                continue
            y = FORAGE_YIELD.get(tt, 5)
            if y > best_yield:
                best_yield = y
                best_terrain = tt.name.lower().replace('_', ' ') if tt else "unknown"

        if best_yield == 0:
            return "Nothing to forage here — terrain is water or ice."

        # Consume all movement
        pos.remaining_movement = 0

        old_supplies = grp.supplies
        grp.resupply(best_yield)
        gained = grp.supplies - old_supplies

        return (f"Foraging complete. Gathered from {best_terrain} — "
                f"+{gained} supplies (now {grp.supplies}%). "
                f"All movement used for the day.")
    forage.action_description = "**Forage**: Gather supplies from terrain (costs all movement this turn)"
    tools.append(forage)

    # Shared rookery tools for generals (include send)
    tools.extend(create_rookery_toolset(general_entity, include_send=True))

    # Objective management tools (mirrors house toolset)
    @function_tool
    def set_objective(objective: str) -> str:
        """
        Set a new mission objective to track across turns (max 5).

        Args:
            objective: Description of the objective to add
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp:
            return "Cannot set objective — AI component unavailable"
        if len(ai_comp.current_objectives) >= 5:
            return f"Objective list full (max 5). Current: {ai_comp.current_objectives}"
        ai_comp.current_objectives.append(objective)
        return f"Objective set: '{objective}'"
    set_objective.action_description = "**Set Objective**: Record a mission goal that persists across turns (max 5)"
    tools.append(set_objective)

    @function_tool
    def remove_objective(objective: str) -> str:
        """
        Remove a mission objective by name or partial match.

        Args:
            objective: Objective text or substring to remove
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp:
            return "Cannot remove objective — AI component unavailable"
        before = list(ai_comp.current_objectives)
        ai_comp.current_objectives = [o for o in ai_comp.current_objectives if objective.lower() not in o.lower()]
        removed = [o for o in before if o not in ai_comp.current_objectives]
        if removed:
            return f"Removed: {removed}"
        return f"No match for '{objective}'. Current: {ai_comp.current_objectives}"
    remove_objective.action_description = "**Remove Objective**: Clear a completed or cancelled mission goal"
    tools.append(remove_objective)

    @function_tool
    def list_objectives() -> str:
        """List all current mission objectives."""
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = general_entity.get_component(AIComponent)
        if not ai_comp or not ai_comp.current_objectives:
            return "No objectives currently set."
        return "Current objectives:\n" + "\n".join(f"  - {o}" for o in ai_comp.current_objectives)
    list_objectives.action_description = "**List Objectives**: View all current mission objectives"
    tools.append(list_objectives)

    # Universal tools
    tools.append(end_turn)

    return tools
