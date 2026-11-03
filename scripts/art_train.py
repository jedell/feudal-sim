#!/usr/bin/env python3
"""
ART training loop for feudal-sim — focal-seat GRPO with seat rotation.

Runs anywhere with GPU access (locally with LocalBackend, on Modal as a GPU
job, or OpenPipe's ServerlessBackend). The policy serves all focal-seat calls
through ART's managed client; opponents run a fixed model (default: the sim's
configured Fireworks GLM).

Usage:
  uv run --extra rl scripts/art_train.py \
      --base-model Qwen/Qwen3-8B \
      --turns 16 --groups 4 --iterations 10

Requires OPENAI_API_KEY/FIREWORKS_API_KEY for opponent models. W&B optional
(ART logs there if configured).
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

HOUSE_SEATS = ["Stark", "Lannister", "Baratheon", "Targaryen"]


async def main():
    parser = argparse.ArgumentParser(description="ART GRPO training for feudal-sim")
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--project", default="feudal-sim")
    parser.add_argument("--policy-name", default="feudal-policy")
    parser.add_argument("--opponent-model", default=None,
                        help="Opponent model route (default: sim config)")
    parser.add_argument("--turns", type=int, default=16, help="Weeks per episode")
    parser.add_argument("--map-size", type=int, default=20)
    parser.add_argument("--num-houses", type=int, default=4)
    parser.add_argument("--groups", type=int, default=4,
                        help="Seeds per iteration (each seed × every seat)")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--base-seed", type=int, default=2000)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--smoke", action="store_true",
                        help="Single iteration, then dump one captured trajectory "
                             "(messages_and_choices) for fidelity inspection")
    args = parser.parse_args()

    import art

    from feudal_sim.rl.art_integration import build_trajectory_groups

    out_dir = Path(args.out_dir or f"runs/art-{time.strftime('%Y%m%d-%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train_config.json").write_text(json.dumps(vars(args), indent=2))

    model = art.TrainableModel(
        name=args.policy_name,
        project=args.project,
        base_model=args.base_model,
    )
    from art.local import LocalBackend
    backend = LocalBackend()  # GPU process-local; swap for ServerlessBackend on OpenPipe
    await model.register(backend)
    print(f"🧠 policy: {args.base_model} as {args.policy_name} "
          f"(inference: {model.get_inference_name()})")

    for iteration in range(args.iterations):
        tasks = [
            {
                "seed": args.base_seed + iteration * 100 + g,
                "map_size": args.map_size,
                "num_houses": args.num_houses,
                "max_turns": args.turns,
            }
            for g in range(args.groups)
        ]

        print(f"\n── iteration {iteration + 1}/{args.iterations}: "
              f"{args.groups} seeds × {args.num_houses} seats ──")
        t0 = time.time()
        groups = build_trajectory_groups(
            model, tasks, args.opponent_model, args.num_houses
        )
        gathered = await art.gather_trajectory_groups(groups)
        rewards = [traj.reward for grp in gathered for traj in grp.trajectories]
        mean_r = sum(rewards) / len(rewards) if rewards else 0.0
        print(f"   rollouts: {len(rewards)}  mean reward: {mean_r:+.3f}  "
              f"({time.time() - t0:.0f}s)")

        if args.smoke:
            # Capture-fidelity check: dump one trajectory's raw
            # messages_and_choices for inspection BEFORE any training step.
            sample = gathered[0].trajectories[0]
            sample_path = out_dir / "trajectory-sample.json"
            sample_path.write_text(sample.model_dump_json(indent=2))
            print(f"   🔬 smoke: dumped {sample_path} "
                  f"({len(sample.messages_and_choices)} messages/choices, "
                  f"reward={sample.reward:+.3f})")
            print("   Inspect it, then rerun without --smoke to train.")
            return

        await model.train(gathered, config=art.TrainConfig())

        iter_stats = {
            "iteration": iteration,
            "mean_reward": mean_r,
            "rewards": rewards,
        }
        with open(out_dir / "metrics.jsonl", "a") as f:
            f.write(json.dumps(iter_stats) + "\n")

    print(f"\n📁 {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
