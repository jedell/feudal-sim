"""
Event Oracle — async background LLM that reads simulation state and generates
contextualised random events injected into the simulation on a schedule.

Architecture:
  - Runs as background asyncio tasks; never blocks the main simulation loop
  - Maintains a queue of 3 pre-generated events
  - Each event has a deploy_turn; fires automatically when due
  - Randomly decides chaos (challenge the leader) or balance (help the weakest)
    before constructing the prompt — the LLM executes a directed brief, not neutral
  - Returns structured JSON validated against GeneratedEvent schema
"""

import asyncio
import json
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from feudal_sim.core.logger import get_logger

log = get_logger(__name__)

ORACLE_MODEL = "gpt-4.1-mini"
QUEUE_TARGET = 3
MAX_DEPLOY_DELAY = 4   # events fire 2-4 turns after generation
MIN_DEPLOY_DELAY = 2

VALID_EFFECT_TYPES = (
    "resource_change",
    "stat_change",
    "spawn_general",
    "spawn_caravan",
    "territory_event",
    "situation_inject",
)

EVENT_SCHEMA = {
    "title": "string — short dramatic name",
    "narrative": "string — 2-3 sentence story description for agents",
    "target": "string — house name, 'all', or 'weakest' / 'strongest'",
    "effect_type": f"one of: {', '.join(VALID_EFFECT_TYPES)}",
    "effect_params": "object — parameters specific to effect_type (see below)",
    "agent_notification": "string — what affected agents are told (2 sentences max)",
    "deploy_in_turns": "integer 2-4 — how many turns until this fires",
}

EFFECT_PARAM_GUIDE = """
effect_params by effect_type:
  resource_change:  {"food": ±N, "material": ±N, "metal": ±N, "gold": ±N}
  stat_change:      {"loyalty": ±N}  (for house targets) OR {"morale": ±N, "supplies": ±N} (for generals)
  spawn_general:    {"name": str, "soldiers": N, "equipment": 0-100, "orders": str, "house": str or null}
                    — house null = neutral/hostile wanderer; house = "HouseName" = joins that house
  spawn_caravan:    {"sender_house": str, "recipient_house": str, "food": N, "metal": N, "gold": N, "terms": str}
  territory_event:  {"action": "grant" or "revoke", "tile_count": N, "direction": "N/NE/SE/S/SW/NW"}
  situation_inject: {"situation_id": str, "text": str, "expires_turns": 2}
                    — pure narrative pressure, no mechanical effect
"""


@dataclass
class GeneratedEvent:
    id: str
    title: str
    narrative: str
    target: str
    effect_type: str
    effect_params: Dict[str, Any]
    agent_notification: str
    deploy_turn: int
    purpose: str   # "chaos" or "balance"
    raw: Dict = field(default_factory=dict)


class EventOracle:
    """
    Background LLM oracle that generates contextualised random events.
    Call refill_queue() as a fire-and-forget task each Events phase.
    """

    def __init__(self, simulation):
        self.simulation = simulation
        self.queue: List[GeneratedEvent] = []
        self._busy = False

    # ── Public API ─────────────────────────────────────────────────────────

    def pop_due_events(self, current_turn: int) -> List[GeneratedEvent]:
        """Return at most one event whose deploy_turn has arrived."""
        due = [e for e in self.queue if e.deploy_turn <= current_turn]
        self.queue = [e for e in self.queue if e.deploy_turn > current_turn]
        return due[:1]

    async def refill_queue(self):
        """
        Top up the queue to QUEUE_TARGET in the background.
        Safe to call as asyncio.create_task() — swallows all errors to avoid
        crashing the main simulation loop.
        """
        if self._busy:
            return
        self._busy = True
        try:
            while len(self.queue) < QUEUE_TARGET:
                event = await self._generate_event()
                if event:
                    self.queue.append(event)
                    log.info(f"🌍 Oracle queued: '{event.title}' "
                             f"[{event.purpose}] fires turn {event.deploy_turn}")
                else:
                    break   # generation failed; try next cycle
        except Exception as e:
            log.warning(f"⚠️  Oracle refill failed: {e}")
        finally:
            self._busy = False

    def queue_summary(self) -> str:
        """Human-readable queue state for debugging / realm overview."""
        if not self.queue:
            return "No events pending."
        return " | ".join(f"'{e.title}' (T{e.deploy_turn})" for e in self.queue)

    # ── Generation ─────────────────────────────────────────────────────────

    async def _generate_event(self) -> Optional[GeneratedEvent]:
        import os
        if not os.getenv("OPENAI_API_KEY"):
            return None

        try:
            import openai
            client = openai.AsyncOpenAI()

            state = self._build_state_snapshot()
            purpose = random.choice(["chaos", "balance"])
            prompt = self._build_prompt(state, purpose)

            response = await client.chat.completions.create(
                model=ORACLE_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Generate the event now."},
                ],
                temperature=0.9,
                max_tokens=600,
            )

            raw = json.loads(response.choices[0].message.content)
            return self._parse_event(raw, purpose)

        except Exception as e:
            log.warning(f"⚠️  Oracle generation error: {e}")
            return None

    def _build_state_snapshot(self) -> str:
        try:
            from feudal_sim.components.resource import ResourceComponent
            from feudal_sim.components.population import PopulationComponent
            from feudal_sim.components.territory import TerritoryComponent

            status = self.simulation.time_manager.get_current_status()
            lines = [f"Turn {status['turn']}, {status['season'].title()}, Year {status['year']}"]
            lines.append("")

            house_data = []
            for house in self.simulation.houses:
                res = house.get_component(ResourceComponent)
                pop = house.get_component(PopulationComponent)
                terr = house.get_component(TerritoryComponent)
                generals = self.simulation.entity_manager.get_entities_by_type('general') or []
                n_gen = sum(1 for g in generals if getattr(g, 'house_id', None) == house.id)

                food = res.resources.food if res else 0
                gold = res.resources.gold if res else 0
                material = res.resources.material if res else 0
                metal = res.resources.metal if res else 0
                loyalty = pop.loyalty if pop else 100
                population = pop.population if pop else 0
                tiles = len(terr.territory) if terr else 0

                house_data.append({
                    'name': house.name, 'tiles': tiles, 'pop': population,
                    'loyalty': loyalty, 'food': food, 'gold': gold,
                    'material': material, 'metal': metal, 'generals': n_gen,
                })
                lines.append(
                    f"  House {house.name}: {tiles} tiles, {population} pop, "
                    f"loyalty {loyalty:.0f}, food {food:.0f}, gold {gold:.0f}, "
                    f"material {material:.0f}, metal {metal:.0f}, {n_gen} generals"
                )

            if house_data:
                strongest = max(house_data, key=lambda h: h['tiles'])
                weakest_food = min(house_data, key=lambda h: h['food'])
                weakest_tiles = min(house_data, key=lambda h: h['tiles'])
                lines.append("")
                lines.append(f"Territorial leader: House {strongest['name']} ({strongest['tiles']} tiles)")
                lines.append(f"Food-critical house: House {weakest_food['name']} ({weakest_food['food']:.0f} food)")
                lines.append(f"Smallest realm: House {weakest_tiles['name']} ({weakest_tiles['tiles']} tiles)")

            return "\n".join(lines)
        except Exception as e:
            return f"State snapshot unavailable: {e}"

    def _build_prompt(self, state: str, purpose: str) -> str:
        if purpose == "chaos":
            directive = (
                "Generate a CHAOS event that creates hardship, crisis, or threat for "
                "the current territorial leader or most powerful house. "
                "Make life harder for whoever is winning."
            )
        else:
            directive = (
                "Generate a BALANCE event that provides meaningful relief, opportunity, "
                "or advantage to whichever house is most struggling (lowest food, territory, "
                "or loyalty). Help the underdog without making it trivial."
            )

        house_names = [h.name for h in self.simulation.houses]

        return f"""You are the Oracle of the Realm — a force that shapes the world of a feudal medieval simulation.
Three houses compete: {', '.join(house_names)}.

Current simulation state:
{state}

Your task: {directive}

Rules:
- The event must feel narratively grounded and medieval (no anachronisms)
- Effects should be significant and tangible but not instantly game-ending
- For spawn_general: soldiers between 20-80, equipment 30-90
- For resource_change: changes between ±20 and ±150 per resource
- For stat_change: loyalty changes ±5 to ±20
- Target can be a specific house name, "all", or describe the situation naturally
- agent_notification should be written in second person ("Your...")
- Keep narrative to 2-3 vivid sentences

{EFFECT_PARAM_GUIDE}

Return valid JSON with exactly these keys:
{json.dumps(EVENT_SCHEMA, indent=2)}"""

    def _parse_event(self, raw: Dict, purpose: str) -> Optional[GeneratedEvent]:
        try:
            effect_type = raw.get("effect_type", "")
            if effect_type not in VALID_EFFECT_TYPES:
                log.warning(f"⚠️  Oracle returned unknown effect_type: {effect_type}")
                effect_type = "situation_inject"

            status = self.simulation.time_manager.get_current_status()
            delay = max(MIN_DEPLOY_DELAY, min(MAX_DEPLOY_DELAY,
                        int(raw.get("deploy_in_turns", MIN_DEPLOY_DELAY))))

            return GeneratedEvent(
                id=f"oracle_{uuid.uuid4().hex[:8]}",
                title=str(raw.get("title", "Unknown Event")),
                narrative=str(raw.get("narrative", "")),
                target=str(raw.get("target", "all")),
                effect_type=effect_type,
                effect_params=raw.get("effect_params", {}),
                agent_notification=str(raw.get("agent_notification", "")),
                deploy_turn=status['turn'] + delay,
                purpose=purpose,
                raw=raw,
            )
        except Exception as e:
            log.warning(f"⚠️  Oracle event parse failed: {e} — raw: {raw}")
            return None
