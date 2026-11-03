"""
System 1 pre-cognition — fast-path decisions via TypeSafe Jev through Vercel AI Gateway.

Before the full LLM agentic loop runs (System 2), a Jev call evaluates a compact
state snapshot against typed questions (Choice / Noul / Score). If Jev's answer
is confident and routine, the action executes directly — no LLM round-trips.
Low confidence, threats, or complex situations fall through to the LLM.

V1 scope: generals only.
  - continue_route  — execute the standing itinerary's movement steps directly
  - hold_position   — pending outpost construction / explicit hold orders
  - observe         — idle general with no route; run terrain observation

API: POST {base_url}/v1/systemone with {state, questions, model}.
Auth: AI_GATEWAY_API_KEY env var (Vercel AI Gateway key).
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from feudal_sim.core.config import config
from feudal_sim.core.logger import get_logger

log = get_logger(__name__)


# ── Settings ─────────────────────────────────────────────────────────────────


@dataclass
class PrecognitionSettings:
    enabled: bool = False
    # "jev" = TypeSafe System One via Vercel AI Gateway (fast, calibrated,
    # cheap). "llm" = standard chat model as the router (any OpenAI-compatible
    # endpoint — use a small/cheap model or you lose the latency win).
    # "off" = skip pre-cognition entirely; every turn runs the full LLM loop.
    provider: str = "jev"
    model: str = "typesafe-ai/jev"
    base_url: str = "https://ai-gateway.vercel.sh/typesafe"
    api_key_env: str = "AI_GATEWAY_API_KEY"
    confidence_threshold: float = 0.8
    threat_threshold: float = 0.5
    timeout_seconds: float = 3.0
    # provider="llm" settings. Model prefixes: "fireworks/..." routes to
    # Fireworks, "vercel/..." routes to the AI Gateway chat endpoint, plain
    # names go to OpenAI. Empty model falls back to the general's model.
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key_env: str = ""

    @classmethod
    def from_config(cls) -> "PrecognitionSettings":
        prefix = "simulation.ai.precognition"

        def _get(key: str, default: Any) -> Any:
            try:
                val = config.get(f"{prefix}.{key}")
                return default if val is None else val
            except KeyError:
                return default

        return cls(
            enabled=_get("enabled", False),
            provider=_get("provider", "jev"),
            model=_get("model", "typesafe-ai/jev"),
            base_url=_get("base_url", "https://ai-gateway.vercel.sh/typesafe"),
            api_key_env=_get("api_key_env", "AI_GATEWAY_API_KEY"),
            confidence_threshold=float(_get("confidence_threshold", 0.8)),
            threat_threshold=float(_get("threat_threshold", 0.5)),
            timeout_seconds=float(_get("timeout_seconds", 3.0)),
            llm_model=_get("llm_model", ""),
            llm_base_url=_get("llm_base_url", ""),
            llm_api_key_env=_get("llm_api_key_env", ""),
        )


# ── Result ───────────────────────────────────────────────────────────────────


@dataclass
class PrecognitionResult:
    action: str
    confidence: float
    probabilities: Dict[str, float] = field(default_factory=dict)
    threat: float = 0.0
    urgency: float = 0.0
    latency_ms: float = 0.0
    cost_usd: float = 0.0


# ── Jev call ─────────────────────────────────────────────────────────────────

GENERAL_QUESTIONS = {
    "next_action": {
        "type": "choice",
        "instructions": (
            "What should this general do this turn? Judge from the mission, "
            "route status, condition, and surroundings."
        ),
        "criteria": {
            "continue_route": (
                "A valid active route exists and the general should keep "
                "marching along it toward the target"
            ),
            "build_outpost": (
                "The general has ARRIVED at the intended site and should "
                "build the outpost now"
            ),
            "observe": (
                "No active route; the general should scan the surroundings "
                "before committing to a move"
            ),
            "hold_position": (
                "Stay put: outpost construction is pending on this tile, "
                "orders say hold, or waiting is clearly correct"
            ),
            "retreat": (
                "Morale or supplies are critically low, or the mission is "
                "compromised — head back toward friendly territory"
            ),
            "needs_deliberation": (
                "The situation is ambiguous, dangerous, or strategically "
                "important — a senior commander should think it through"
            ),
        },
    },
    "threat_nearby": {
        "type": "noul",
        "instructions": (
            "Is there an immediate military threat to this general within "
            "roughly 2 tiles (enemy forces, hostile territory being entered, "
            "an ambush risk)?"
        ),
    },
}


async def call_jev(
    state: str,
    settings: PrecognitionSettings,
    questions: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Single System One call through the AI Gateway. Returns raw answers dict or None."""
    api_key = os.environ.get(settings.api_key_env)
    if not api_key:
        log.warning(f"⚡ Pre-cognition disabled: {settings.api_key_env} not set")
        return None

    payload = {
        "model": settings.model,
        "state": state,
        "questions": questions or GENERAL_QUESTIONS,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
            resp = await client.post(
                f"{settings.base_url}/v1/systemone",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning(f"⚡ Jev call failed ({e}); falling through to LLM")
        return None


def parse_general_result(raw: Dict[str, Any]) -> Optional[PrecognitionResult]:
    """Extract a PrecognitionResult from the raw gateway response."""
    try:
        answers = raw["answers"]
        action_answer = answers["next_action"]
        threat_answer = answers.get("threat_nearby", {})

        gateway_meta = raw.get("provider_metadata", {}).get("gateway", {})
        routing = gateway_meta.get("routing", {})
        attempts = routing.get("modelAttempts", [])
        latency_ms = 0.0
        if attempts:
            providers = attempts[0].get("providerAttempts", [])
            if providers:
                latency_ms = providers[0].get("endTime", 0) - providers[0].get("startTime", 0)

        return PrecognitionResult(
            action=action_answer["choice"],
            confidence=float(action_answer.get("confidence", 0.0)),
            probabilities=action_answer.get("probabilities", {}),
            threat=float(threat_answer.get("noul", 0.0)),
            latency_ms=latency_ms,
            cost_usd=float(gateway_meta.get("cost", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as e:
        log.warning(f"⚡ Malformed Jev response ({e}); falling through to LLM")
        return None


# ── Standard LLM router (provider="llm") ────────────────────────────────────

_LLM_ROUTER_PROMPT = """\
You are a fast tactical router for a feudal wargame. Given a general's state,
decide their next action. Respond with ONLY a JSON object, no prose:

{
  "next_action": one of [
    "continue_route",      // valid active route exists; keep marching
    "build_outpost",       // arrived at the intended site; build now
    "observe",             // no route; scan surroundings first
    "hold_position",       // stay: pending construction, hold orders, waiting
    "retreat",             // morale/supplies critical; return home
    "needs_deliberation"   // ambiguous/dangerous/strategic; escalate
  ],
  "threat": 0.0-1.0,       // probability of immediate military threat ~2 tiles
  "confidence": 0.0-1.0    // your confidence in next_action
}

Be conservative: when in doubt, lower confidence rather than guessing."""


def _resolve_chat_endpoint(settings: PrecognitionSettings,
                           agent_type_value: str) -> Tuple[str, str, str]:
    """Resolve (model_id, base_url, api_key_env) for the LLM router.

    Explicit precognition.llm_* config wins; otherwise the agent type's own
    model string is reused. Prefixes: "fireworks/" → Fireworks endpoint,
    "vercel/" → AI Gateway, plain → OpenAI.
    """
    model = settings.llm_model
    if not model:
        try:
            model = config.get(f"simulation.ai.models.{agent_type_value}") or \
                    config.get("simulation.ai.model", "")
        except KeyError:
            model = ""

    if model.startswith("fireworks/"):
        return (model.removeprefix("fireworks/"),
                settings.llm_base_url or os.environ.get(
                    "FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
                settings.llm_api_key_env or "FIREWORKS_API_KEY")
    if model.startswith("vercel/"):
        return (model.removeprefix("vercel/"),
                settings.llm_base_url or "https://ai-gateway.vercel.sh/v1",
                settings.llm_api_key_env or "AI_GATEWAY_API_KEY")
    return (model,
            settings.llm_base_url or "https://api.openai.com/v1",
            settings.llm_api_key_env or "OPENAI_API_KEY")


async def call_llm_router(
    state: str,
    settings: PrecognitionSettings,
    agent_type_value: str,
) -> Optional[Dict[str, Any]]:
    """Route via a standard chat model. Returns a raw-answers-shaped dict so
    parse_general_result can consume it unchanged."""
    model_id, base_url, api_key_env = _resolve_chat_endpoint(settings, agent_type_value)
    api_key = os.environ.get(api_key_env)
    if not api_key or not model_id:
        log.warning(f"⚡ LLM router unavailable ({api_key_env} not set or no model)")
        return None

    try:
        import json as _json

        async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": _LLM_ROUTER_PROMPT},
                        {"role": "user", "content": state},
                    ],
                    # reasoning models burn completion tokens on thinking
                    # before the JSON answer — give it headroom
                    "max_tokens": 2000,
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage", {})

        # Robust JSON extraction — models sometimes wrap in ```json fences
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            log.warning(f"⚡ LLM router returned non-JSON: {text[:120]!r}")
            return None
        decision = _json.loads(text[start : end + 1])

        # Shape it like the Jev response for parse_general_result
        return {
            "answers": {
                "next_action": {
                    "type": "choice",
                    "choice": decision.get("next_action", "needs_deliberation"),
                    "confidence": float(decision.get("confidence", 0.0)),
                    "probabilities": {},
                },
                "threat_nearby": {
                    "type": "noul",
                    "noul": float(decision.get("threat", 0.0)),
                },
            },
            "usage": usage,
            "provider_metadata": {"gateway": {}},
        }
    except Exception as e:
        log.warning(f"⚡ LLM router call failed ({e}); falling through to main loop")
        return None





def build_general_state(ai_component) -> Optional[str]:
    """Compact text snapshot of a general's situation for Jev.

    Deliberately terse — Jev prices on input tokens and evaluates best on
    dense, factual state.
    """
    entity = ai_component.entity
    ctx = ai_component.context
    if entity is None or ctx is None:
        return None

    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.components.terrain_observation import TerrainObservation

    pos: PositionComponent = entity.get_component(PositionComponent)
    grp: SubAgentGroup = entity.get_component(SubAgentGroup)
    if not pos or not pos.position or not grp:
        return None

    lines = [
        f"General {ai_component.agent_name} of the realm.",
        f"Week {ctx.current_turn}, {ctx.current_season}, year {ctx.current_year}.",
        f"Forces: {grp.assigned_population.soldiers} soldiers, "
        f"{grp.assigned_population.workers} workers. "
        f"Morale {grp.morale}%, supplies {grp.supplies}%.",
        f"Movement: {pos.remaining_movement:g} of {pos.movement_points:g} points left this turn.",
    ]

    mp = grp.mission_parameters
    if mp:
        lines.append(
            f"Mission: {mp.mission_type}. Orders: {mp.orders or 'none'}. "
            f"Priority: {mp.priority}."
        )

    route = grp.active_route
    if route and route.get("target"):
        target = tuple(route["target"])
        if tuple(pos.position) == target:
            lines.append(
                f"Route: ARRIVED at target ({route.get('purpose', 'destination')})."
            )
        else:
            try:
                from feudal_sim.components.pathfinding import PathfindingComponent
                pf = PathfindingComponent("precognition")
                path = pf.find_path(
                    tuple(pos.position), target, ctx.hex_grid,
                    entity_house_id=getattr(entity, "house_id", None),
                )
                if path and len(path) >= 2:
                    lines.append(
                        f"Route: {len(path) - 1} step(s) remaining to "
                        f"{route.get('purpose', 'target')}; path is clear."
                    )
                else:
                    lines.append("Route: BLOCKED — no path to target.")
            except Exception:
                lines.append(f"Route: heading to {route.get('purpose', 'target')}.")
    else:
        lines.append("Route: none — no standing itinerary.")

    # Pending outpost construction on this tile?
    try:
        em = getattr(ctx, "entity_manager", None)
        house_id = getattr(entity, "house_id", None)
        if em and house_id:
            from feudal_sim.components.territory import TerritoryComponent
            house = em.get_entity(house_id)
            terr = house.get_component(TerritoryComponent) if house else None
            if terr:
                for order in terr.pending_outposts:
                    if order.status == "pending" and (order.q, order.r) == tuple(pos.position):
                        turns_left = order.turn_resolves - getattr(
                            getattr(ctx, "simulation", None), "global_turn", ctx.current_turn
                        )
                        lines.append(
                            f"Outpost under construction on this tile — completes in "
                            f"{max(0, turns_left)} turn(s); the general must remain here."
                        )
                        break
    except Exception:
        pass

    # Known threats from spatial memory
    obs: TerrainObservation = entity.get_component(TerrainObservation)
    if obs:
        try:
            threats = obs.get_threats_in_area(pos.position, search_range=2)
            if threats:
                counts: Dict[str, int] = {}
                for t in threats:
                    counts[t.threat_level] = counts.get(t.threat_level, 0) + 1
                lines.append(
                    "Known threats within 2 tiles: "
                    + ", ".join(f"{n} {lvl}" for lvl, n in counts.items())
                    + "."
                )
            else:
                lines.append("No known threats within 2 tiles.")
        except Exception:
            pass

        passive = obs.get_passive_observation_text()
        if passive:
            lines.append(f"Known ground: {passive[:300]}")

    return "\n".join(lines)


# ── Fast-path executors ──────────────────────────────────────────────────────


def _execute_continue_route(ai_component) -> Optional[str]:
    """March along the active route. Mirrors the move_along tool's core loop."""
    entity = ai_component.entity
    ctx = ai_component.context
    from feudal_sim.components.pathfinding import PathfindingComponent
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.utils.directions import path_to_directions

    grp: SubAgentGroup = entity.get_component(SubAgentGroup)
    pos: PositionComponent = entity.get_component(PositionComponent)
    route = grp.active_route if grp else None
    if not route or not route.get("target") or not pos or not pos.position:
        return None

    target = tuple(route["target"])
    if tuple(pos.position) == target:
        return None  # already there — not a continue

    pf = PathfindingComponent("precognition")
    path = pf.find_path(
        tuple(pos.position), target, ctx.hex_grid,
        entity_house_id=getattr(entity, "house_id", None),
    )
    if not path or len(path) < 2:
        grp.active_route = None
        return "Route blocked — no path from here. Itinerary cleared."

    steps = path_to_directions(path)
    completed: List[str] = []
    stopped: Optional[str] = None

    for direction in steps:
        if pos.remaining_movement <= 0:
            stopped = "movement points exhausted"
            break
        q, r = pos.position
        dest = None
        for neigh, dirn in ctx.hex_grid.get_neighbors(q, r):
            if dirn == direction and neigh is not None:
                dest = (neigh.q, neigh.r)
                break
        if dest is None:
            stopped = f"no tile in direction {direction}"
            break
        result = pos.move_to(
            target_position=dest,
            hex_grid=ctx.hex_grid,
            current_turn=getattr(ctx, "current_turn", None),
            validate_movement=True,
        )
        if not result.get("success"):
            stopped = result.get("message", f"blocked moving {direction}")
            break
        completed.append(direction)

    if not completed:
        return None  # nothing executed — let the LLM handle it

    arrived = tuple(pos.position) == target
    if arrived:
        grp.active_route = None

    path_str = " → ".join(completed)
    msg = f"Marched {len(completed)} step(s): {path_str}."
    if stopped:
        msg += f" Stopped: {stopped}."
    if arrived:
        msg += f" Arrived at {route.get('purpose', 'destination')}."
    return msg


def _execute_hold_position(ai_component) -> Optional[str]:
    """Stay put. Only fast-path when there is a concrete reason to hold."""
    entity = ai_component.entity
    ctx = ai_component.context
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup

    grp: SubAgentGroup = entity.get_component(SubAgentGroup)
    pos: PositionComponent = entity.get_component(PositionComponent)

    # Pending outpost construction on this tile is the canonical hold case
    try:
        em = getattr(ctx, "entity_manager", None)
        house_id = getattr(entity, "house_id", None)
        if em and house_id and pos and pos.position:
            from feudal_sim.components.territory import TerritoryComponent
            house = em.get_entity(house_id)
            terr = house.get_component(TerritoryComponent) if house else None
            if terr:
                for order in terr.pending_outposts:
                    if order.status == "pending" and (order.q, order.r) == tuple(pos.position):
                        return "Holding position — outpost construction underway on this tile."
    except Exception:
        pass

    # Explicit hold orders in the mission
    mp = grp.mission_parameters if grp else None
    orders = (mp.orders or "").lower() if mp else ""
    if any(word in orders for word in ("hold", "stay", "remain", "garrison")):
        return "Holding position per orders."

    return None  # no clear reason to hold — let the LLM decide


def _execute_observe(ai_component) -> Optional[str]:
    """Run terrain observation for an idle general (no route, nothing pending)."""
    entity = ai_component.entity
    ctx = ai_component.context
    from feudal_sim.components.position import PositionComponent
    from feudal_sim.components.subagent_group import SubAgentGroup
    from feudal_sim.components.terrain_observation import TerrainObservation

    grp: SubAgentGroup = entity.get_component(SubAgentGroup)
    if grp and grp.active_route:
        return None  # has a route — observing mid-march wastes movement

    obs: TerrainObservation = entity.get_component(TerrainObservation)
    pos: PositionComponent = entity.get_component(PositionComponent)
    if not obs or not pos or not pos.position:
        return None

    obs.observation_range = 2
    obs.observe_current_area(ctx.hex_grid, pos.position, ctx.current_turn)
    return "Surveyed the surrounding area; observations recorded."


FAST_PATH_EXECUTORS = {
    "continue_route": _execute_continue_route,
    "hold_position": _execute_hold_position,
    "observe": _execute_observe,
}


# ── Entry point ──────────────────────────────────────────────────────────────


async def try_precognition(ai_component) -> Optional[str]:
    """Attempt a System 1 fast-path turn. Returns a result summary string if the
    turn was fully handled without the LLM, else None (fall through).

    Gating:
      1. config disabled / provider "off" / not a general → None
      2. router confidence below threshold → None
      3. threat probability above threshold → None
      4. action not in fast-path executors → None
      5. executor declines (preconditions unmet) → None
    """
    from feudal_sim.ai.prompts import AgentType

    if ai_component.agent_type != AgentType.GENERAL:
        return None

    settings = PrecognitionSettings.from_config()
    if not settings.enabled or settings.provider == "off":
        return None

    state = build_general_state(ai_component)
    if not state:
        return None

    if settings.provider == "llm":
        raw = await call_llm_router(state, settings, ai_component.agent_type.value)
    else:
        raw = await call_jev(state, settings)
    if raw is None:
        return None

    result = parse_general_result(raw)
    if result is None:
        return None

    log.info(
        f"⚡ [{ai_component.agent_name}] precog[{settings.provider}]: {result.action} "
        f"(p={result.confidence:.2f}, threat={result.threat:.2f}, "
        f"{result.latency_ms:.0f}ms, ${result.cost_usd:.6f})"
    )

    if result.threat >= settings.threat_threshold:
        log.info(f"⚡ Threat too high ({result.threat:.2f}) — escalating to LLM")
        return None
    if result.confidence < settings.confidence_threshold:
        log.info(
            f"⚡ Confidence too low ({result.confidence:.2f} < "
            f"{settings.confidence_threshold}) — escalating to LLM"
        )
        return None

    executor = FAST_PATH_EXECUTORS.get(result.action)
    if executor is None:
        return None  # build_outpost / retreat / needs_deliberation → LLM

    outcome = executor(ai_component)
    if outcome is None:
        log.info(f"⚡ Executor declined '{result.action}' — escalating to LLM")
        return None

    # Keep message history coherent: record the fast-path turn so the next
    # full LLM turn sees what happened.
    turn_label = (
        f"Week {ai_component.context.current_turn} — {ai_component.context.current_season.title()}, "
        f"Year {ai_component.context.current_year}"
    )
    ai_component.messages.append({
        "role": "user",
        "content": f"[{turn_label}] [Pre-cognition] {state.splitlines()[0]}",
    })
    ai_component.messages.append({
        "role": "assistant",
        "content": f"{outcome} (decided via fast-path assessment: "
                   f"{result.action}, confidence {result.confidence:.2f})",
    })

    log.info(f"⚡ [{ai_component.agent_name}] Fast-pathed: {outcome}")
    return outcome
