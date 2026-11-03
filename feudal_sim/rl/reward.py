"""
Reward functions for TRL GRPO training.

TRL's environment contract (see examples/grpo_echo): the environment object
accumulates state during the rollout; after the rollout, reward_funcs receive
the list of environment instances and return one float per rollout.

The v0 reward is terminal-outcome RLVR — computed programmatically from the
episode result, no judges:
  win      → +1.0
  loss     → -1.0
  timeout  → territory_share - fair_share  (continuous, in [-fair, 1-fair])

Shaped per-turn rewards (signal deltas) stay parked until reward composition
is designed — the raw signals are already in trajectory.jsonl for that work.
"""

from typing import Any, Dict, List


def terminal_reward_for_result(
    result: Dict[str, Any], focal_house: str, num_houses: int
) -> float:
    """Competitive terminal reward for one agent's episode result."""
    winner = result.get("winner")
    final_state = result.get("final_state") or {}

    if winner:
        return 1.0 if winner.lower() == focal_house.lower() else -1.0

    # Timeout: how much of the map did the focal house hold vs. an even split?
    total_tiles = sum(s.get("territory", 0) for s in final_state.values())
    focal_tiles = (final_state.get(focal_house) or {}).get("territory", 0)
    if total_tiles <= 0:
        return 0.0
    fair_share = 1.0 / max(1, num_houses)
    return (focal_tiles / total_tiles) - fair_share


def terminal_outcome_reward(environments: List[Any], **kwargs) -> List[float]:
    """TRL reward_funcs entry point: one float per rollout environment.

    Each environment is expected to expose a `reward` attribute set during
    its rollout (per the TRL environment_factory contract).
    """
    return [float(getattr(env, "reward", 0.0)) for env in environments]
