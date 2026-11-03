#!/usr/bin/env python3
"""
Eval ladder — policy model vs opponent model(s) with positional rotation.

For a 4-house game, raw win rates are confounded by spawn position. The ladder
rotates the policy through every house seat across episodes, so each model
plays each position equally:

  matchup = policy P vs opponent O
  episode i (of 4k): P plays house[i % 4], O plays the other three

Usage:
  uv run scripts/rl_ladder.py \
      --policy fireworks/accounts/fireworks/models/glm-5p3 \
      --opponent fireworks/accounts/fireworks/models/glm-5p3 \
      --rotations 1 --turns 16 --workers 2

Output: <run-dir>/ladder.json + a win-rate table. Multiple --opponent flags
produce one matchup section each.
"""

import argparse
import concurrent.futures
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path

HOUSE_SEATS = ["Stark", "Lannister", "Baratheon", "Targaryen"]


def run_episode(task: dict, out_dir: Path) -> dict:
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
    tail = "\n".join((proc.stderr or proc.stdout).splitlines()[-10:])
    return {"error": f"exit {proc.returncode}", "stderr_tail": tail,
            "_elapsed_s": round(elapsed, 1)}


def run_matchup(policy: str, opponent: str, args, run_dir: Path, tag: str) -> dict:
    """Rotate the policy through every seat, `rotations` times."""
    seats = HOUSE_SEATS[: args.num_houses]
    episodes = []
    for rotation in range(args.rotations):
        for seat_idx, seat in enumerate(seats):
            seed = args.base_seed + len(episodes)
            house_models = {s: opponent for s in seats}
            house_models[seat] = policy
            episodes.append({
                "seed": seed,
                "policy_seat": seat,
                "task": {
                    "seed": seed,
                    "map_size": args.map_size,
                    "num_houses": args.num_houses,
                    "max_turns": args.turns,
                    "house_models": house_models,
                    "ai_enabled": True,
                },
            })

    matchup_dir = run_dir / tag
    matchup_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_episode,
                ep["task"],
                matchup_dir / f"seed-{ep['seed']}-policy-{ep['policy_seat'].lower()}",
            ): ep
            for ep in episodes
        }
        for fut in concurrent.futures.as_completed(futures):
            ep = futures[fut]
            res = fut.result()
            res["_policy_seat"] = ep["policy_seat"]
            results.append(res)
            if "error" in res:
                print(f"  ❌ seed {ep['seed']} ({ep['policy_seat']}): {res['error']}")
            else:
                winner = res.get("winner") or "—"
                policy_won = winner and winner.lower() == ep["policy_seat"].lower()
                print(
                    f"  ✅ seed {ep['seed']}: policy={ep['policy_seat']} "
                    f"winner={winner} {'🏆' if policy_won else ''} "
                    f"({res['_elapsed_s']}s)"
                )

    # Aggregate
    n = len([r for r in results if "error" not in r])
    wins = sum(
        1 for r in results
        if "error" not in r and r.get("winner")
        and r["winner"].lower() == r["_policy_seat"].lower()
    )
    decided = sum(1 for r in results if "error" not in r and r.get("winner"))

    # Mean final territory share for the policy's seat (works even when no
    # winner emerges — a continuous strength signal)
    shares = []
    for r in results:
        if "error" in r:
            continue
        final = r.get("final_state") or {}
        total_tiles = sum(s.get("territory", 0) for s in final.values())
        policy_tiles = (final.get(r["_policy_seat"]) or {}).get("territory", 0)
        if total_tiles:
            shares.append(policy_tiles / total_tiles)

    return {
        "policy": policy,
        "opponent": opponent,
        "episodes": n,
        "errors": len(results) - n,
        "policy_wins": wins,
        "decided_games": decided,
        "policy_win_rate": round(wins / n, 3) if n else 0.0,
        "policy_win_rate_decided": round(wins / decided, 3) if decided else None,
        "policy_mean_territory_share": (
            round(sum(shares) / len(shares), 3) if shares else None
        ),
        "expected_fair_share": round(1.0 / args.num_houses, 3),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="feudal-sim eval ladder")
    parser.add_argument("--policy", required=True, help="Model under evaluation")
    parser.add_argument("--opponent", action="append", required=True,
                        help="Opponent model (repeatable)")
    parser.add_argument("--rotations", type=int, default=1,
                        help="Times the policy plays every seat (episodes = "
                             "rotations × num_houses per matchup)")
    parser.add_argument("--turns", type=int, default=16)
    parser.add_argument("--map-size", type=int, default=20)
    parser.add_argument("--num-houses", type=int, default=4)
    parser.add_argument("--base-seed", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--out-dir", type=str, default=None)
    args = parser.parse_args()

    run_dir = Path(args.out_dir or f"runs/ladder-{time.strftime('%Y%m%d-%H%M%S')}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "ladder_config.json").write_text(json.dumps(vars(args), indent=2))

    ladder = []
    for opp_idx, opponent in enumerate(args.opponent):
        print(f"\n⚔️  matchup: {args.policy}  vs  {opponent}")
        seed_base = args.base_seed + opp_idx * 1000
        m_args = argparse.Namespace(**{**vars(args), "base_seed": seed_base})
        summary = run_matchup(args.policy, opponent, m_args, run_dir,
                              tag=f"matchup-{opp_idx}")
        ladder.append(summary)

    print("\n=== Ladder ===")
    print(f"{'policy':<40} {'opponent':<40} {'win%':>6} {'win%(dec)':>9} {'terr share':>10}")
    for m in ladder:
        wr = f"{m['policy_win_rate'] * 100:.0f}%"
        wrd = f"{m['policy_win_rate_decided'] * 100:.0f}%" if m["policy_win_rate_decided"] is not None else "—"
        share = f"{m['policy_mean_territory_share']:.3f}" if m["policy_mean_territory_share"] is not None else "—"
        print(f"{m['policy']:<40.40} {m['opponent']:<40.40} {wr:>6} {wrd:>9} {share:>10}")

    (run_dir / "ladder.json").write_text(json.dumps(ladder, indent=2, default=str))
    print(f"\n📁 {run_dir}/ladder.json")


if __name__ == "__main__":
    main()
