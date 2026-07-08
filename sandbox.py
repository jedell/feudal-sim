"""
Sandbox runner for auditing priority action events in isolation.

Lets you instantiate any scenario (contact, trade arrival, diplomatic summit)
and run the full agentic interaction without running a complete simulation.

Usage:
    uv run python sandbox.py contact          # general vs general contact
    uv run python sandbox.py trade            # trade caravan arrival
    uv run python sandbox.py --help

Each scenario prints the full agent conversation, tool calls, and resolution.
"""

import asyncio
import click
import logging
from feudal_sim.core.logger import setup_logging, get_logger

log = get_logger(__name__)


# ── Minimal entity / component stubs ──────────────────────────────────────────

STANCE_SEEDS = {
    'aggressive': (
        "You are a battle-hardened commander who believes conflict is inevitable and strength "
        "earns respect. Your lord has ordered you to secure this territory by force if necessary. "
        "You distrust diplomatic overtures — the enemy only understands strength. "
        "Attack decisively unless overwhelmingly outmatched."
    ),
    'diplomatic': (
        "You are a measured commander who prefers negotiated outcomes. Your lord values "
        "alliances over bloodshed and has instructed you to seek terms before engaging. "
        "Propose ceasefire, offer mutual benefit, and withdraw if terms are agreed."
    ),
    'cautious': (
        "You are a careful commander who prioritises preserving your forces. "
        "Your lord needs these soldiers alive for a larger campaign ahead. "
        "Hold a defensive position, avoid unnecessary risk, and withdraw if the odds are against you."
    ),
    'unpredictable': (
        "You are a volatile commander — fierce, proud, and easily provoked. "
        "You may parley if it suits you, but any hint of disrespect or weakness from the enemy "
        "will be met with immediate assault. Act on instinct."
    ),
}


def _make_general(name: str, house_id: str, house_name: str,
                  soldiers: int = 50, equipment: int = 60, morale: int = 100,
                  position: tuple = (0, 0), stance: str = None):
    """Create a minimal general entity with all components needed for contact events."""
    from feudal_sim.core.entities import Entity, EntityManager
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup, MissionParameters
    from feudal_sim.components.population import AssignedPopulation
    from feudal_sim.components.rookery import RookeryComponent
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.ai.prompts import AgentType

    general = Entity(f"{house_id}_general", name)
    general.house_id = house_id

    pos = PositionComponent(entity_id=general.id, position=position, movement_points=2)
    general.add_component(pos)

    grp = SubAgentGroup(
        entity_id=general.id,
        parent_house_id=house_id,
        assigned_population=AssignedPopulation(workers=10, soldiers=soldiers),
    )
    grp.equipment_level = equipment
    grp.morale = morale
    grp.mission_parameters = MissionParameters(
        mission_type="patrol",
        orders="Patrol the area and report back.",
    )
    general.add_component(grp)

    rookery = RookeryComponent(entity_id=general.id)
    general.add_component(rookery)

    ai = AIComponent(
        name=name,
        agent_type=AgentType.GENERAL,
        entity_id=general.id,
        house_name=house_name,
    )
    general.add_component(ai)

    # Inject stance/personality seed into message history
    seed_text = STANCE_SEEDS.get(stance or '', '')
    if seed_text:
        ai.add_observation(f"[Commander Profile] {seed_text}", phase="Actions", pending=False)

    return general


def _make_house(name: str):
    """Create a minimal house entity."""
    from feudal_sim.core.entities import Entity
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.ai.prompts import AgentType
    from feudal_sim.components.rookery import RookeryComponent

    house = Entity(name, name)

    rookery = RookeryComponent(entity_id=house.id)
    house.add_component(rookery)

    ai = AIComponent(name=f"Lord of {name}", agent_type=AgentType.HOUSE_LORD,
                     entity_id=house.id, house_name=name)
    house.add_component(ai)

    return house


def _make_entity_manager(entities):
    from feudal_sim.core.entities import EntityManager
    em = EntityManager()
    for e in entities:
        em._entities[e.id] = e
    return em


# ── Scenario runners ───────────────────────────────────────────────────────────

async def run_contact_scenario(
    attacker_name="Ser Jaime",
    attacker_house="Lannister",
    attacker_soldiers=50,
    attacker_equip=80,
    attacker_stance=None,
    defender_name="Ser Rodrik",
    defender_house="Stark",
    defender_soldiers=40,
    defender_equip=60,
    defender_stance=None,
    terrain="GRASSLAND",
    is_ambush=False,
):
    """Run a general contact event in isolation."""
    from feudal_sim.core.config import config
    config.load_config('simulation')
    config.load_config('world')

    from feudal_sim.core.priority_actions import PriorityActionEvent, PriorityActionEventProcessor
    from feudal_sim.core.priority_action_handlers import GeneralContactHandler

    log.info(f"\n{'='*60}")
    log.info(f"CONTACT SANDBOX: {attacker_name} ({attacker_house}) vs {defender_name} ({defender_house})")
    log.info(f"Terrain: {terrain} | Ambush: {is_ambush}")
    log.info(f"Attacker: {attacker_soldiers} soldiers, {attacker_equip}% equipped, 100% morale")
    log.info(f"Defender: {defender_soldiers} soldiers, {defender_equip}% equipped, 100% morale")
    log.info('='*60)

    # Build entities
    attacker = _make_general(attacker_name, attacker_house, attacker_house,
                              soldiers=attacker_soldiers, equipment=attacker_equip,
                              position=(0, 0), stance=attacker_stance)
    defender = _make_general(defender_name, defender_house, defender_house,
                              soldiers=defender_soldiers, equipment=defender_equip,
                              position=(1, 0), stance=defender_stance)
    house_a = _make_house(attacker_house)
    house_b = _make_house(defender_house)

    em = _make_entity_manager([attacker, defender, house_a, house_b])
    em._entities_by_type['general'] = [attacker, defender]

    # Create the event
    event = PriorityActionEvent(
        event_id=f"sandbox_contact_{attacker.id}_{defender.id}",
        event_type="general_contact",
        context_data={
            'attacker_id':         attacker.id,
            'attacker_name':       attacker_name,
            'attacker_house_id':   attacker_house,
            'attacker_house_name': attacker_house,
            'attacker_soldiers':   attacker_soldiers,
            'attacker_equip':      attacker_equip,
            'attacker_morale':     100,
            'defender_id':         defender.id,
            'defender_name':       defender_name,
            'defender_house_id':   defender_house,
            'defender_house_name': defender_house,
            'defender_soldiers':   defender_soldiers,
            'defender_equip':      defender_equip,
            'defender_morale':     100,
            'terrain_type':        terrain,
            'is_ambush':           is_ambush,
            'entity_manager':      em,
            'hex_grid':            None,
        },
        involved_agents=[attacker.id, defender.id],
        allows_conversation=True,
        max_conversation_rounds=2,
        created_turn=1,
    )

    # Wire up AI context for both generals
    from feudal_sim.ai.context import SimulationContext
    for gen, house_id in [(attacker, attacker_house), (defender, defender_house)]:
        ai = gen.get_component(__import__('feudal_sim.components.ai', fromlist=['AIComponent']).AIComponent)
        if ai:
            ai.update_context(
                current_turn=1, current_phase='actions',
                current_season='spring', current_year=1,
                entity_manager=em, simulation=None,
            )

    # Process
    class MinimalSimulation:
        entity_manager = em
        hex_grid = None

    processor = PriorityActionEventProcessor(MinimalSimulation())
    processor.register_handler("general_contact", GeneralContactHandler())
    processor.add_event(event)

    log.info("\n⚔️  Starting contact event...\n")
    results = await processor.process_all_events()

    log.info(f"\n{'='*60}")
    log.info("RESOLUTION:")
    for r in results:
        log.info(f"  {r}")
    log.info('='*60)

    # Show final state
    from feudal_sim.components.subagent_group import SubAgentGroup
    for gen, label in [(attacker, "Attacker"), (defender, "Defender")]:
        grp = gen.get_component(SubAgentGroup)
        if grp:
            log.info(f"\n{label} ({gen.name}): {grp.assigned_population.soldiers} soldiers, "
                     f"morale {grp.morale}%, supplies {grp.supplies}%")


async def run_trade_scenario(
    sender_house="Lannister",
    recipient_house="Stark",
    metal=30,
    terms="30 metal for 60 food",
):
    """Stub — extend as needed for trade caravan arrival auditing."""
    log.info(f"\n[TRADE SANDBOX] {sender_house} → {recipient_house}: {terms}")
    log.info("Trade sandbox not yet fully wired — coming soon.")


# ── CLI ────────────────────────────────────────────────────────────────────────

@click.group()
@click.option('--debug', is_flag=True, help='Verbose debug output')
def cli(debug):
    setup_logging(logging.DEBUG if debug else logging.INFO)


@cli.command()
@click.option('--attacker', default='Ser Jaime', help='Attacker general name')
@click.option('--attacker-house', default='Lannister')
@click.option('--attacker-soldiers', default=50, type=int)
@click.option('--attacker-equip', default=80, type=int, help='Equipment level 0-100')
@click.option('--attacker-stance', default=None,
              type=click.Choice(['aggressive', 'diplomatic', 'cautious', 'unpredictable']),
              help='Personality stance for attacker')
@click.option('--defender', default='Ser Rodrik', help='Defender general name')
@click.option('--defender-house', default='Stark')
@click.option('--defender-soldiers', default=40, type=int)
@click.option('--defender-equip', default=60, type=int)
@click.option('--defender-stance', default=None,
              type=click.Choice(['aggressive', 'diplomatic', 'cautious', 'unpredictable']),
              help='Personality stance for defender')
@click.option('--terrain', default='GRASSLAND', help='Tile terrain type')
@click.option('--ambush', is_flag=True, help='Attacker springs ambush')
def contact(attacker, attacker_house, attacker_soldiers, attacker_equip, attacker_stance,
            defender, defender_house, defender_soldiers, defender_equip, defender_stance,
            terrain, ambush):
    """Run a general contact event in isolation."""
    asyncio.run(run_contact_scenario(
        attacker_name=attacker, attacker_house=attacker_house,
        attacker_soldiers=attacker_soldiers, attacker_equip=attacker_equip,
        attacker_stance=attacker_stance,
        defender_name=defender, defender_house=defender_house,
        defender_soldiers=defender_soldiers, defender_equip=defender_equip,
        defender_stance=defender_stance,
        terrain=terrain, is_ambush=ambush,
    ))


@cli.command()
@click.option('--sender', default='Lannister')
@click.option('--recipient', default='Stark')
@click.option('--metal', default=30, type=int)
@click.option('--terms', default='30 metal for 60 food')
def trade(sender, recipient, metal, terms):
    """Run a trade caravan arrival in isolation."""
    asyncio.run(run_trade_scenario(
        sender_house=sender, recipient_house=recipient,
        metal=metal, terms=terms,
    ))


if __name__ == '__main__':
    cli()
