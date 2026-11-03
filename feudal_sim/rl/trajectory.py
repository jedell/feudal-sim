"""
Trajectory export — one JSONL row per agent per turn.

Each row is one agent's turn atom: the observation it was shown, the items it
produced (reasoning / tool calls / tool outputs / messages), and the game-state
signals before/after. This is the raw material for RL training and for offline
eval — format is deliberately plain JSONL so any trainer (slime, verl, TRL)
can ingest it with a trivial adapter.

Capture points (set by AIComponent.make_decisions each turn):
  - ai.last_turn_observation: the turn-context user message shown to the agent
  - ai.last_turn_new_items:   the Agents SDK new_items from the run
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _serialize_item(item: Any) -> Dict[str, Any]:
    """Tolerantly convert an Agents SDK result item to plain JSON."""
    raw = getattr(item, "raw_item", item)
    if hasattr(raw, "model_dump"):
        try:
            return raw.model_dump()
        except Exception:
            pass
    if isinstance(raw, dict):
        return raw
    return {"_type": type(item).__name__, "repr": str(raw)[:500]}


class TrajectoryWriter:
    """Writes trajectory.jsonl + episode_meta.json into an episode directory.

    Row types:
      - agent rows: one per AI-carrying entity per turn (houses, generals,
        caravans, and any future agent type — anything with an AIComponent).
        Contains only what that agent could observe (competitive MARL:
        no opponent privileged state in an actor row).
      - one global row per turn ("row_type": "global_state", "privileged": true):
        all houses' signals for centralized-critic (CTDE) training. Training
        pipelines must filter this out of actor data.
    """

    def __init__(self, out_dir: str, task: Dict[str, Any], episode_id: Optional[str] = None):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.episode_id = episode_id or self.dir.name
        self._fp = open(self.dir / "trajectory.jsonl", "a", encoding="utf-8")
        (self.dir / "episode_meta.json").write_text(
            json.dumps({"task": task, "episode_id": self.episode_id}, indent=2))
        self._last_signals: Dict[str, Dict[str, Any]] = {}

    def record_turn(
        self,
        turn: int,
        simulation,
        signals: Dict[str, Dict[str, Any]],
        done: bool = False,
        winner: Optional[str] = None,
    ) -> int:
        """Snapshot every AI agent's turn plus the privileged global row.

        Returns rows written."""
        from feudal_sim.components.ai import AIComponent

        rows = 0

        # Generic coverage: houses live in simulation.houses; generals,
        # caravans (and future scouts/diplomats) live in the entity manager.
        entities = list(simulation.houses)
        try:
            managed = simulation.entity_manager.get_entities_with_component(AIComponent)
            seen = {e.id for e in entities}
            entities.extend(e for e in managed if e.id not in seen)
        except Exception:
            # Fallback: generals + caravans explicitly
            for etype in ("general", "caravan", "scout"):
                entities.extend(simulation.entity_manager.get_entities_by_type(etype) or [])

        for entity in entities:
            ai = entity.get_component(AIComponent)
            if not ai or not ai.is_enabled:
                continue

            observation = getattr(ai, "last_turn_observation", None)
            new_items = getattr(ai, "last_turn_new_items", None)
            if observation is None and not new_items:
                continue  # agent hasn't acted yet this episode

            house_name = getattr(ai, "house_name", None) or getattr(entity, "name", None)

            sig = signals.get(house_name, {}) if house_name else {}
            prev = self._last_signals.get(house_name, {}) if house_name else {}
            deltas = {
                k: round(sig[k] - prev[k], 3)
                for k in ("territory", "food", "material", "metal", "gold",
                          "population", "loyalty")
                if isinstance(sig.get(k), (int, float))
                and isinstance(prev.get(k), (int, float))
            }

            # Competitive outcome from THIS agent's perspective
            outcome = None
            if done:
                if winner is None:
                    outcome = "timeout"
                elif house_name and winner.lower() == str(house_name).lower():
                    outcome = "win"
                else:
                    outcome = "loss"

            row = {
                "row_type": "agent",
                "episode_id": self.episode_id,
                "turn": turn,
                "agent": ai.agent_name,
                "agent_type": ai.agent_type.value if ai.agent_type else None,
                "house": house_name,
                "observation": observation,
                "items": [_serialize_item(i) for i in (new_items or [])],
                "signals": sig,
                "signal_deltas": deltas,
                "done": done,
                "outcome": outcome,
            }
            self._fp.write(json.dumps(row, default=str) + "\n")
            rows += 1

        # Privileged global row — CTDE critic data, never actor input
        global_row = {
            "row_type": "global_state",
            "privileged": True,
            "episode_id": self.episode_id,
            "turn": turn,
            "all_houses": signals,
            "done": done,
            "winner": winner,
        }
        self._fp.write(json.dumps(global_row, default=str) + "\n")
        rows += 1

        self._fp.flush()
        self._last_signals = {k: dict(v) for k, v in signals.items()}
        return rows

    def finish(self, result: Dict[str, Any]) -> None:
        meta_path = self.dir / "episode_meta.json"
        meta = json.loads(meta_path.read_text())
        meta["result"] = result
        meta_path.write_text(json.dumps(meta, indent=2))
        self._fp.close()
