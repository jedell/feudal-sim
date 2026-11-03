#!/usr/bin/env python3
"""
Parallel RL rollout runner — fan out N episodes across subprocess workers.

Each episode runs in its own process (the sim's config module is a
process-global singleton, so one episode per process). Collects per-episode
trajectory.jsonl + episode_meta.json under the run directory, then prints a
summary table.

Usage:
  uv run scripts/rl_rollout.py --episodes 4 --workers 2 --turns 16
  uv run scripts/rl_rollout.py --episodes 8 --workers 8 --turns 32 --base-seed 100

Env vars (OPENAI_API_KEY / FIREWORKS_API_KEY / AI_GATEWAY_API_KEY) are
inherited by subprocesses automatically.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def run_one(seed: int, args, run_dir: Path) -> dict:
    task = {
        "seed": seed,
        "map_size": args.map_size,
        "num_houses": args.num_houses,
        "max_turns": args.turns,
        "ai_enabled": not args.no_ai,
    }
    if args.model:
        task["model"] = args.model

    out_dir = run_dir / f"seed-{seed}"
    t0 = time.time()
    proc = subprocess.run(
        [
            "uv", "run", "python", "-m", "feudal_sim.rl.episode",
            "--task", json.dumps(task),
            "--out-dir", str(out_dir),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    elapsed = time.time() - t0

    for line in proc.stdout.splitlines():
        if line.startswith("EPISODE_RESULT "):
            result = json.loads(line[len("EPISODE_RESULT "):])
            result["_elapsed_s"] = round(elapsed, 1)
            return result

    # Episode crashed — surface the tail of stderr for debugging
    tail = "\n".join((proc.stderr or proc.stdout).splitlines()[-15:])
    return {
        "task": task,
        "error": f"exit {proc.returncode}",
        "stderr_tail": tail,
        "_elapsed_s": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Parallel feudal-sim RL rollouts")
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--turns", type=int, default=16, help="Max weeks per episode")
    parser.add_argument("--map-size", type=int, default=20)
    parser.add_argument("--num-houses", type=int, default=4)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--model", type=str, default=None, help="Policy model override")
    parser.add_argument("--no-ai", action="store_true",
                        help="Disable LLM agents (mechanics/determinism smoke test)")
    parser.add_argument("--out-dir", type=str, default=None)
    args = parser.parse_args()

    run_dir = Path(args.out_dir or f"runs/rollout-{time.strftime('%Y%m%d-%H%M%S')}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_config.json").write_text(json.dumps(vars(args), indent=2))

    seeds = [args.base_seed + i for i in range(args.episodes)]
    print(f"🎲 {args.episodes} episodes, {args.workers} workers → {run_dir}")

    results = []
    pending = list(seeds)
    in_flight: dict = {}

    # Simple subprocess pool
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, seed, args, run_dir): seed for seed in seeds}
        for fut in concurrent.futures.as_completed(futures):
            seed = futures[fut]
            res = fut.result()
            results.append(res)
            if "error" in res:
                print(f"  ❌ seed {seed}: {res['error']} ({res['_elapsed_s']}s)")
            else:
                winner = res.get("winner") or "—"
                print(
                    f"  ✅ seed {seed}: {res['turns_taken']} turns, "
                    f"winner={winner} ({res['_elapsed_s']}s)"
                )

    # Summary table
    print("\n=== Rollout summary ===")
    print(f"{'seed':>6} {'turns':>6} {'winner':<14} {'time_s':>7}")
    for res in sorted(results, key=lambda r: r["task"]["seed"]):
        if "error" in res:
            print(f"{res['task']['seed']:>6} {'ERR':>6} {'—':<14} {res['_elapsed_s']:>7}")
            continue
        print(
            f"{res['task']['seed']:>6} {res['turns_taken']:>6} "
            f"{(res.get('winner') or '—'):<14} {res['_elapsed_s']:>7}"
        )

    (run_dir / "summary.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n📁 {run_dir}/summary.json")


if __name__ == "__main__":
    main()
