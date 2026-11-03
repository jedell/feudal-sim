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
    """Writes trajectory.jsonl + episode_meta.json into an episode directory."""

    def __init__(self, out_dir: str, task: Dict[str, Any]):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.dir / "trajectory.jsonl", "a", encoding="utf-8")
        (self.dir / "episode_meta.json").write_text(json.dumps({"task": task}, indent=2))
        self._last_signals: Dict[str, Dict[str, Any]] = {}

    def record_turn(self, turn: int, simulation, signals: Dict[str, Dict[str, Any]]) -> int:
        """Snapshot every AI agent's turn. Returns rows written."""
        from feudal_sim.components.ai import AIComponent

        rows = 0
        entities = list(simulation.houses) + list(
            simulation.entity_manager.get_entities_by_type("general") or []
        )
        for entity in entities:
            ai = entity.get_component(AIComponent)
            if not ai or not ai.is_enabled:
                continue

            observation = getattr(ai, "last_turn_observation", None)
            new_items = getattr(ai, "last_turn_new_items", None)
            if observation is None and not new_items:
                continue  # agent hasn't acted yet this episode

            house_name = getattr(entity, "name", None)
            if not hasattr(entity, "resources"):  # general — resolve parent house
                house_name = getattr(ai, "house_name", None) or house_name

            sig = signals.get(house_name, {}) if house_name else {}
            prev = self._last_signals.get(house_name, {}) if house_name else {}
            deltas = {
                k: round(sig[k] - prev[k], 3)
                for k in ("territory", "food", "material", "metal", "gold",
                          "population", "loyalty")
                if isinstance(sig.get(k), (int, float))
                and isinstance(prev.get(k), (int, float))
            }

            row = {
                "turn": turn,
                "agent": ai.agent_name,
                "agent_type": ai.agent_type.value if ai.agent_type else None,
                "house": house_name,
                "observation": observation,
                "items": [_serialize_item(i) for i in (new_items or [])],
                "signals": sig,
                "signal_deltas": deltas,
            }
            self._fp.write(json.dumps(row, default=str) + "\n")
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
