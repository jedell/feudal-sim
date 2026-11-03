"""
Single-episode entry point — run one RL episode in this process.

Usage:
  uv run python -m feudal_sim.rl.episode --task '{"seed": 1, "max_turns": 16}' \
      --out-dir runs/2026-11-02/seed-1

Designed to be spawned as a subprocess by scripts/rl_rollout.py (the config
module is process-global, so one episode per process).
"""

import argparse
import asyncio
import json
import logging
import sys

from feudal_sim.core.config import config
from feudal_sim.core.logger import setup_logging, get_logger

log = get_logger(__name__)


async def run_episode(task_dict: dict, out_dir: str) -> dict:
    from feudal_sim.rl.env import FeudalEnv, TaskConfig
    from feudal_sim.rl.trajectory import TrajectoryWriter

    task = TaskConfig(**task_dict)
    env = FeudalEnv(task)
    writer = TrajectoryWriter(out_dir, task.to_dict())

    env.reset()
    try:
        while not env.done:
            summary = await env.step_turn()
            signals = env.observe()
            rows = writer.record_turn(
                env.simulation.global_turn,
                env.simulation,
                signals,
                done=env.done,
                winner=summary.get("winner"),
            )
            log.info(
                f"📍 turn {summary['turn']} done "
                f"({rows} rows, game_over={summary['game_over']})"
            )
    finally:
        result = env.result()
        writer.finish(result)

    return result


def main():
    parser = argparse.ArgumentParser(description="Run one feudal-sim RL episode")
    parser.add_argument("--task", required=True, help="TaskConfig as JSON")
    parser.add_argument("--out-dir", required=True, help="Episode output directory")
    parser.add_argument("--quiet", action="store_true", help="Reduce log noise")
    args = parser.parse_args()

    setup_logging(logging.WARNING if args.quiet else logging.INFO)

    task = json.loads(args.task)
    result = asyncio.run(run_episode(task, args.out_dir))

    # Machine-readable result on the last stdout line for the parent process
    print("EPISODE_RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
