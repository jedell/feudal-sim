#!/usr/bin/env python3
"""
Verifier for the feudal-episode task.

Reads /logs/episode/{episode_meta.json, trajectory.jsonl} and writes a
multi-dimensional reward to /logs/verifier/reward.json.

Dimensions (0..1 each, plus weighted total):
  completed        — episode ran to a terminal state (game_over or max turns)
  artifacts        — both artifact files exist and parse
  trajectory       — agent rows exist and cover every house in final_state
  consistency      — episode seed matches the requested task seed
"""

import json
import sys
from pathlib import Path

EPISODE_DIR = Path("/logs/episode")
VERIFIER_DIR = Path("/logs/verifier")


def main() -> int:
    reward = {
        "completed": 0.0,
        "artifacts": 0.0,
        "trajectory": 0.0,
        "consistency": 0.0,
    }
    detail = {}

    meta_path = EPISODE_DIR / "episode_meta.json"
    traj_path = EPISODE_DIR / "trajectory.jsonl"

    # --- artifacts ---
    meta = None
    rows = []
    try:
        meta = json.loads(meta_path.read_text())
        rows = [
            json.loads(line)
            for line in traj_path.read_text().splitlines()
            if line.strip()
        ]
        reward["artifacts"] = 1.0
    except Exception as e:
        detail["error"] = f"artifact parse failed: {e}"
        return _write(reward, detail)

    result = meta.get("result", {})
    task = meta.get("task", {})

    # --- completed ---
    max_turns = task.get("max_turns", 16)
    turns_taken = result.get("turns_taken", 0)
    if result.get("game_over") or turns_taken >= max_turns:
        reward["completed"] = 1.0
    elif turns_taken > 0:
        reward["completed"] = round(turns_taken / max_turns, 3)
    detail["turns_taken"] = turns_taken
    detail["winner"] = result.get("winner")

    # --- trajectory ---
    agent_rows = [r for r in rows if r.get("row_type") == "agent"]
    global_rows = [r for r in rows if r.get("row_type") == "global_state"]
    if task.get("ai_enabled") is False:
        # AI-free run: no agent rows exist by design. Credit the global
        # (critic) rows covering every turn instead.
        reward["trajectory"] = 1.0 if len(global_rows) >= max(1, turns_taken) else 0.5
    else:
        houses = [
            h for h, s in (result.get("final_state") or {}).items() if s.get("alive")
        ]
        houses_with_rows = {r.get("house") for r in agent_rows}
        if agent_rows and houses and set(houses) <= houses_with_rows:
            reward["trajectory"] = 1.0
        elif agent_rows:
            reward["trajectory"] = 0.5
    detail["agent_rows"] = len(agent_rows)
    detail["global_rows"] = len(global_rows)

    # --- consistency ---
    meta_seed = task.get("seed")
    row_seeds = {r.get("episode_id") for r in rows if r.get("episode_id")}
    if meta_seed is not None and (
        not row_seeds or row_seeds == {f"seed-{meta_seed}"}
    ):
        reward["consistency"] = 1.0

    # Weighted total
    reward["total"] = round(
        0.3 * reward["completed"]
        + 0.2 * reward["artifacts"]
        + 0.3 * reward["trajectory"]
        + 0.2 * reward["consistency"],
        3,
    )
    return _write(reward, detail)


def _write(reward: dict, detail: dict) -> int:
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    # Harbor requires reward.json to be strictly numeric — diagnostics go in
    # a separate file.
    (VERIFIER_DIR / "verifier-detail.json").write_text(json.dumps(detail, indent=2))
    numeric = {k: v for k, v in reward.items() if isinstance(v, (int, float))}
    (VERIFIER_DIR / "reward.json").write_text(json.dumps(numeric, indent=2))
    (VERIFIER_DIR / "reward.txt").write_text(str(reward["total"]))
    print(json.dumps({**numeric, "detail": detail}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
