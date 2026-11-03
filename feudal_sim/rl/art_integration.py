"""
ART (OpenPipe Agent Reinforcement Trainer) integration.

Shape: focal-seat training. One house seat runs the policy under training via
ART's managed OpenAI client (so every policy call is auto-captured into the
trajectory); the other seats run a fixed opponent model through their own
provider client and are NOT captured. Rotating the focal seat across rollouts
cancels spawn-position bias — same trick as the eval ladder.

The captured trajectory contains only the focal agent's calls → clean
per-agent attribution → one competitive terminal reward per trajectory.

Usage (see scripts/art_train.py):
    model = art.TrainableModel(name="feudal-policy", project="feudal-sim",
                               base_model="Qwen/Qwen3-8B")
    backend = art.LocalBackend(...)        # or ServerlessBackend
    await model.register(backend)
    groups = await art.gather_trajectory_groups(
        art.TrajectoryGroup(
            art_rollout(model, task, seat) for seat in SEATS
        ) for task in tasks
    )
    await model.train(groups, config=art.TrainConfig(...))
"""

from typing import Any, Dict, Optional

from feudal_sim.core.logger import get_logger

log = get_logger(__name__)

HOUSE_SEATS = ["Stark", "Lannister", "Baratheon", "Targaryen"]


async def art_rollout(
    model,
    task_overrides: Optional[Dict[str, Any]] = None,
    focal_seat: str = "Stark",
    opponent_model: Optional[str] = None,
    num_houses: int = 4,
) -> "object":
    """Run one episode with the ART policy on the focal seat.

    Returns an art.Trajectory with the focal agent's auto-captured calls and
    the competitive terminal reward from the focal seat's perspective.
    """
    import art

    from feudal_sim.components.ai import clear_policy_client, set_policy_client
    from feudal_sim.rl.env import FeudalEnv, TaskConfig
    from feudal_sim.rl.reward import terminal_reward_for_result

    seats = HOUSE_SEATS[:num_houses]
    if focal_seat not in seats:
        raise ValueError(f"focal_seat {focal_seat!r} not in seats {seats}")

    inference_name = model.get_inference_name()
    policy_route = f"local/{inference_name}"

    house_models = {seat: opponent_model for seat in seats}
    house_models[focal_seat] = policy_route

    task = TaskConfig(
        house_models=house_models,
        **(task_overrides or {}),
    )
    env = FeudalEnv(task)

    # Inject ART's managed client BEFORE reset() — agents bind their client
    # at construction time.
    set_policy_client(model.openai_client())
    try:
        env.reset()

        async def _run_episode():
            while not env.done:
                await env.step_turn()

        trajectory = await art.capture_auto_trajectory(_run_episode())
    finally:
        clear_policy_client()

    result = env.result()
    trajectory.reward = terminal_reward_for_result(result, focal_seat, num_houses)
    trajectory.metrics.update(
        {
            "turns": result["turns_taken"],
            "game_over": bool(result["game_over"]),
            "winner_emerged": bool(result["winner"]),
        }
    )
    trajectory.metadata.update(
        {
            "focal_seat": focal_seat,
            "seed": str(task.seed),
            "opponent_model": opponent_model or "config-default",
        }
    )
    log.info(
        f"🎯 rollout done: seat={focal_seat} reward={trajectory.reward:.3f} "
        f"turns={result['turns_taken']} winner={result['winner']}"
    )
    return trajectory.finish()


def build_trajectory_groups(
    model,
    tasks: list[Dict[str, Any]],
    opponent_model: Optional[str] = None,
    num_houses: int = 4,
) -> list:
    """One TrajectoryGroup per task; within a group, the policy rotates through
    every seat (GRPO compares across seats sharing a seed)."""
    import art

    seats = HOUSE_SEATS[:num_houses]
    return [
        art.TrajectoryGroup(
            art_rollout(model, task, seat, opponent_model, num_houses)
            for seat in seats
        )
        for task in tasks
    ]
