"""
FeudalEnv — gym-style wrapper around Simulation for RL rollouts and evals.

Model:
  - One episode = one simulation run, bounded by task.max_turns (weeks) or victory.
  - step_turn() advances one full week (Production → Actions → Events → Cleanup).
  - Determinism: the global RNG is seeded at reset() before any worldgen, so a
    given TaskConfig reproduces the same world and the same stochastic events.
    (LLM agent decisions remain non-deterministic unless the policy is.)
  - Parallelism: subprocess-per-env (gym AsyncVectorEnv pattern). The config
    module is a process-global singleton, so in-process parallel envs are NOT
    supported — run workers as subprocesses (see scripts/rl_rollout.py).

TaskConfig is the curriculum knob: vary seeds, map size, house count, and the
policy model per episode.
"""

import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from feudal_sim.core.config import config
from feudal_sim.core.logger import get_logger

log = get_logger(__name__)


@dataclass
class TaskConfig:
    """One episode's initial conditions."""

    seed: int = 0
    map_size: int = 20
    num_houses: int = 4
    max_turns: int = 16  # weeks; 16 = one in-game year
    simulation_config: str = "simulation"
    world_config: str = "world"
    model: Optional[str] = None  # overrides simulation.ai.model for this episode
    # Eval ladder: per-house model overrides, e.g.
    # {"Stark": "fireworks/accounts/fireworks/models/glm-5p3"} — lets one
    # policy model face different opponent models. Applied post-construction
    # to each house's agent.
    house_models: Optional[Dict[str, str]] = None
    ai_enabled: bool = True
    # RL training rollouts must be pure policy-driven: the pre-cognition
    # fast-path would silently remove decisions from the trajectory. Off by
    # default; opt in only for non-training evals of the precog system itself.
    allow_precognition: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeudalEnv:
    """Headless, seedable episode driver."""

    def __init__(self, task: TaskConfig):
        self.task = task
        self.simulation = None
        self.turns_taken = 0

    # ── gym surface ──────────────────────────────────────────────────────────

    def reset(self):
        """Seed, load configs, apply task overrides, build a fresh Simulation."""
        random.seed(self.task.seed)

        config.load_config(self.task.simulation_config)
        config.load_config(self.task.world_config)
        config.set("simulation.world_generation.map_size", self.task.map_size)
        config.set("simulation.world_generation.num_houses", self.task.num_houses)
        config.set("simulation.ai.enabled", self.task.ai_enabled)
        config.set("simulation.ai.precognition.enabled", self.task.allow_precognition)
        if self.task.model:
            config.set("simulation.ai.model", self.task.model)

        from feudal_sim.core.simulation import Simulation

        self.simulation = Simulation(debug=True)  # headless: no renderer
        self._apply_house_models()
        self.turns_taken = 0
        log.info(
            f"🌍 Episode reset: seed={self.task.seed} map={self.task.map_size} "
            f"houses={self.task.num_houses} max_turns={self.task.max_turns}"
        )
        return self.observe()

    def _apply_house_models(self) -> None:
        """Apply per-house policy model overrides (eval ladder support)."""
        if not self.task.house_models or not self.simulation:
            return
        from feudal_sim.components.ai import AIComponent, resolve_model

        for house in self.simulation.houses:
            model_name = self.task.house_models.get(house.name)
            if not model_name:
                continue
            ai = house.get_component(AIComponent)
            if ai and ai.agent is not None:
                ai.agent.model = resolve_model(model_name)
                log.info(f"🎭 {house.name} policy model → {model_name}")

    @property
    def done(self) -> bool:
        if self.simulation is None:
            return False
        return self.simulation.game_over or self.turns_taken >= self.task.max_turns

    async def step_turn(self) -> Dict[str, Any]:
        """Advance one full week (4 phases). Returns the turn summary."""
        if self.simulation is None:
            raise RuntimeError("reset() must be called before step_turn()")
        if self.done:
            raise RuntimeError("step_turn() called on a finished episode")

        for _ in range(4):
            await self.simulation.step()
            if self.simulation.game_over:
                break
        self.turns_taken += 1

        return {
            "turn": self.simulation.global_turn,
            "game_over": self.simulation.game_over,
            "winner": self.simulation.winner,
        }

    def observe(self) -> Dict[str, Any]:
        """Per-house state snapshot — the raw material for reward signals."""
        from feudal_sim.rl.rewards import house_signals

        if self.simulation is None:
            return {}
        return house_signals(self.simulation)

    def result(self) -> Dict[str, Any]:
        """Terminal episode summary."""
        sim = self.simulation
        return {
            "task": self.task.to_dict(),
            "turns_taken": self.turns_taken,
            "game_over": sim.game_over if sim else False,
            "winner": sim.winner if sim else None,
            "final_state": self.observe(),
        }
