"""
Random event executors — apply the mechanical effects of oracle-generated events.

Each effect_type has a dedicated executor. The oracle describes intent in JSON;
these functions translate that intent into actual simulation state changes.
"""

from feudal_sim.core.logger import get_logger

log = get_logger(__name__)


def apply_event(event, simulation) -> str:
    """
    Apply a GeneratedEvent to the simulation. Returns a summary string.
    Notifies affected agents via observation injection.
    """
    log.info(f"🌍 [{event.purpose.upper()}] {event.title}: {event.narrative}")

    try:
        summary = _dispatch(event, simulation)
        _notify_agents(event, simulation)
        return summary
    except Exception as e:
        log.warning(f"⚠️  Event '{event.title}' execution failed: {e}")
        return f"Event '{event.title}' could not be applied."


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _dispatch(event, simulation) -> str:
    executors = {
        "resource_change":  _apply_resource_change,
        "stat_change":      _apply_stat_change,
        "spawn_general":    _apply_spawn_general,
        "spawn_caravan":    _apply_spawn_caravan,
        "territory_event":  _apply_territory_event,
        "situation_inject": _apply_situation_inject,
    }
    fn = executors.get(event.effect_type)
    if not fn:
        return f"Unknown effect type: {event.effect_type}"
    return fn(event, simulation)


# ── Target resolution ─────────────────────────────────────────────────────────

def _resolve_targets(event, simulation):
    """Return the list of house entities this event targets."""
    from feudal_sim.components.territory import TerritoryComponent

    target = (event.target or '').strip().lower()

    if target in ('all', 'everyone', 'all houses'):
        return list(simulation.houses)

    if target in ('weakest', 'smallest'):
        by_tiles = sorted(
            simulation.houses,
            key=lambda h: len((h.get_component(TerritoryComponent) or _empty()).territory)
        )
        return [by_tiles[0]] if by_tiles else []

    if target in ('strongest', 'largest', 'leader'):
        by_tiles = sorted(
            simulation.houses,
            key=lambda h: len((h.get_component(TerritoryComponent) or _empty()).territory),
            reverse=True
        )
        return [by_tiles[0]] if by_tiles else []

    # Try exact name match
    for house in simulation.houses:
        if house.name.lower() == target or house.name.lower() in target:
            return [house]

    # Fallback: all houses
    return list(simulation.houses)


class _empty:
    territory = set()


# ── Executors ─────────────────────────────────────────────────────────────────

def _apply_resource_change(event, simulation) -> str:
    from feudal_sim.components.resource import ResourceComponent

    targets = _resolve_targets(event, simulation)
    params = event.effect_params
    applied = []

    for house in targets:
        res = house.get_component(ResourceComponent)
        if not res:
            continue
        for resource in ('food', 'material', 'metal', 'gold'):
            delta = float(params.get(resource, 0))
            if delta == 0:
                continue
            res.resources.add(resource, delta) if delta > 0 else res.resources.consume(resource, abs(delta))
            applied.append(f"{house.name}: {resource} {delta:+.0f}")

    return f"Resources changed — {'; '.join(applied) or 'no changes'}"


def _apply_stat_change(event, simulation) -> str:
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.subagent_group import SubAgentGroup

    targets = _resolve_targets(event, simulation)
    params = event.effect_params
    applied = []

    loyalty_delta = int(params.get('loyalty', 0))
    morale_delta = int(params.get('morale', 0))
    supplies_delta = int(params.get('supplies', 0))

    for house in targets:
        if loyalty_delta:
            pop = house.get_component(PopulationComponent)
            if pop:
                pop.adjust_loyalty(loyalty_delta)
                applied.append(f"{house.name} loyalty {loyalty_delta:+d}")

        if morale_delta or supplies_delta:
            generals = simulation.entity_manager.get_entities_by_type('general') or []
            for g in generals:
                if getattr(g, 'house_id', None) == house.id:
                    grp = g.get_component(SubAgentGroup)
                    if grp:
                        if morale_delta:
                            grp.adjust_morale(morale_delta)
                        if supplies_delta:
                            grp.resupply(supplies_delta) if supplies_delta > 0 else grp.consume_supplies(abs(supplies_delta))
                        applied.append(f"{g.name} morale/supplies adjusted")

    return f"Stats changed — {'; '.join(applied) or 'no changes'}"


def _apply_spawn_general(event, simulation) -> str:
    from feudal_sim.core.entities import Entity
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup, MissionParameters
    from feudal_sim.components.population import AssignedPopulation
    from feudal_sim.components.rookery import RookeryComponent
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.components.terrain_observation import TerrainObservation
    from feudal_sim.ai.prompts import AgentType
    import random as _rand

    params = event.effect_params
    name = params.get('name', 'Wandering Commander')
    soldiers = max(10, min(150, int(params.get('soldiers', 30))))
    equipment = max(0, min(100, int(params.get('equipment', 50))))
    orders = params.get('orders', 'Wander the realm and seek opportunity.')
    target_house_name = params.get('house')

    # Find target house or pick random map edge tile
    target_house = None
    if target_house_name:
        for h in simulation.houses:
            if h.name.lower() == str(target_house_name).lower():
                target_house = h
                break

    # Place near map edge if no target, otherwise near target's border
    spawn_position = (simulation.hex_grid.size - 2, 0)
    if target_house:
        from feudal_sim.components.territory import TerritoryComponent
        terr = target_house.get_component(TerritoryComponent)
        if terr and terr.border_tiles:
            tile = _rand.choice(list(terr.border_tiles))
            spawn_position = (tile.q, tile.r)

    gen_id = f"oracle_general_{event.id}"
    general = Entity(gen_id, name)
    house_id = target_house.id if target_house else 'neutral'
    general.house_id = house_id

    pos = PositionComponent(entity_id=gen_id, position=spawn_position,
                             operational_range=3, movement_points=2)
    general.add_component(pos)

    assigned = AssignedPopulation(workers=0, soldiers=soldiers)
    grp = SubAgentGroup(entity_id=gen_id, parent_house_id=house_id,
                         group_type='military', assigned_population=assigned)
    grp.equipment_level = equipment
    grp.mission_parameters = MissionParameters(mission_type='patrol', orders=orders)
    general.add_component(grp)

    terrain_obs = TerrainObservation(entity_id=gen_id, observation_range=2)
    general.add_component(terrain_obs)

    rookery = RookeryComponent(entity_id=gen_id)
    general.add_component(rookery)

    ai = AIComponent(name=name, agent_type=AgentType.GENERAL,
                     entity_id=gen_id,
                     house_name=target_house.name if target_house else 'Wanderer')
    # Seed the oracle's narrative as mission context
    ai.add_observation(f"[Oracle] {event.narrative} {orders}", phase="Actions", pending=False)
    general.add_component(ai)

    simulation.entity_manager._entities[gen_id] = general
    if 'general' not in simulation.entity_manager._entities_by_type:
        simulation.entity_manager._entities_by_type['general'] = []
    simulation.entity_manager._entities_by_type['general'].append(general)

    if target_house:
        from feudal_sim.components.territory import TerritoryComponent
        terr = target_house.get_component(TerritoryComponent)
        if terr:
            terr.register_general({
                'entity_id': gen_id, 'name': name, 'position': spawn_position,
                'direction': 'oracle', 'orders': orders,
                'soldiers_assigned': soldiers, 'workers_assigned': 0,
                'deployment_turn': simulation.time_manager.get_current_status()['turn'],
            })

    log.info(f"🌍 Spawned oracle general: {name} ({soldiers} soldiers) at {spawn_position}")
    return f"Spawned {name} ({soldiers} soldiers, {equipment}% equipped) at {spawn_position}"


def _apply_spawn_caravan(event, simulation) -> str:
    from feudal_sim.entities.caravan import TradeCaravan
    from feudal_sim.components.cargo import TradeGoods
    from feudal_sim.components.territory import TerritoryComponent

    params = event.effect_params
    sender_name = params.get('sender_house', simulation.houses[0].name)
    recipient_name = params.get('recipient_house', simulation.houses[-1].name)

    sender = next((h for h in simulation.houses if h.name == sender_name), simulation.houses[0])
    recipient = next((h for h in simulation.houses if h.name == recipient_name), simulation.houses[-1])

    cargo = TradeGoods(
        food=float(params.get('food', 0)),
        material=float(params.get('material', 0)),
        metal=float(params.get('metal', 0)),
        gold=float(params.get('gold', 0)),
    )
    # Starting position: centre of sender territory or map edge
    start_pos = (simulation.hex_grid.size // 2, 0)
    terr = sender.get_component(TerritoryComponent)
    if terr and terr.territory:
        tiles = list(terr.territory)
        t = tiles[len(tiles) // 2]
        start_pos = (t.q, t.r)

    caravan = TradeCaravan.create_trade_caravan(
        sender_house_id=sender.id,
        recipient_house_id=recipient.id,
        cargo=cargo,
        proposed_terms=params.get('terms', 'Oracle gift'),
        starting_position=start_pos,
        caravan_name=f"Oracle Caravan ({event.title})",
    )
    caravan.plan_route_to_house(recipient, simulation.hex_grid)
    simulation.entity_manager._entities[caravan.id] = caravan
    simulation.entity_manager._entities_by_type.setdefault('caravan', []).append(caravan)

    return f"Oracle caravan dispatched: {sender.name} → {recipient.name} carrying {cargo}"


def _apply_territory_event(event, simulation) -> str:
    from feudal_sim.components.territory import TerritoryComponent
    import random as _rand

    targets = _resolve_targets(event, simulation)
    params = event.effect_params
    action = params.get('action', 'grant')
    count = max(1, min(5, int(params.get('tile_count', 1))))
    direction = params.get('direction', 'N').upper()
    applied = []

    for house in targets:
        terr = house.get_component(TerritoryComponent)
        if not terr:
            continue

        if action == 'revoke' and terr.territory:
            to_remove = _rand.sample(list(terr.border_tiles or terr.territory),
                                      min(count, len(terr.territory) - 1))
            terr.remove_territory(to_remove, simulation.hex_grid)
            applied.append(f"{house.name} lost {len(to_remove)} tiles")

        elif action == 'grant':
            opps = terr.get_expansion_opportunities(direction, simulation.hex_grid)
            if opps:
                tiles = [o['tile'] for o in opps[:count]]
                house.expand_territory(tiles, simulation.hex_grid)
                applied.append(f"{house.name} gained {len(tiles)} tiles ({direction})")

    return f"Territory event — {'; '.join(applied) or 'no changes'}"


def _apply_situation_inject(event, simulation) -> str:
    from feudal_sim.components.ai import AIComponent

    targets = _resolve_targets(event, simulation)
    params = event.effect_params
    situation_id = params.get('situation_id', f"oracle_{event.id}")
    text = params.get('text', event.narrative)
    expires = int(params.get('expires_turns', 2))

    for house in targets:
        ai = house.get_component(AIComponent)
        if ai:
            ai.inject_situation(situation_id, f"[Oracle Event: {event.title}]\n{text}", expires)

    return f"Situation injected to {len(targets)} house(s): '{situation_id}'"


# ── Agent notification ────────────────────────────────────────────────────────

def _notify_agents(event, simulation):
    """Push an observation to all affected agents describing the event."""
    from feudal_sim.components.ai import AIComponent

    if not event.agent_notification:
        return

    targets = _resolve_targets(event, simulation)
    msg = f"[World Event: {event.title}] {event.agent_notification}"

    for house in targets:
        ai = house.get_component(AIComponent)
        if ai:
            ai.add_observation(msg, phase="Events")

    # Also notify generals of targeted houses
    generals = simulation.entity_manager.get_entities_by_type('general') or []
    target_ids = {h.id for h in targets}
    for g in generals:
        if getattr(g, 'house_id', None) in target_ids:
            ai = g.get_component(AIComponent)
            if ai:
                ai.add_observation(msg, phase="Events")
