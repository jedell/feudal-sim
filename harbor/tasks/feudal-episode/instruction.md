# Feudal Sim — Episode Task

Run one episode of the feudal-sim multi-agent strategy simulation and produce
its trajectory artifacts.

## What to do

The simulation is installed at `/app` (Python package `feudal_sim`, virtualenv
at `/app/.venv`).

1. Read the episode task from the `FEUDAL_TASK` environment variable (JSON).
   If unset, use: `{"seed": 1, "max_turns": 4}`

2. Run one episode, writing artifacts to `/logs/episode/`:

```bash
/app/.venv/bin/python -m feudal_sim.rl.episode \
    --task "$FEUDAL_TASK" \
    --out-dir /logs/episode \
    --quiet
```

LLM agent credentials are provided via `OPENAI_API_KEY` / `FIREWORKS_API_KEY`
environment variables when the task enables AI agents. If neither is set, run
with AI disabled (`"ai_enabled": false` in the task JSON) — the episode still
exercises full game mechanics.

## Success criteria

After your run, the verifier expects:

- `/logs/episode/episode_meta.json` — contains `task` and `result` with
  `turns_taken`, `game_over`, `winner`, `final_state`
- `/logs/episode/trajectory.jsonl` — one JSON row per agent per turn plus a
  privileged `global_state` row per turn

Do not modify files outside `/logs/`. Do not fabricate the artifacts — the
verifier checks internal consistency against the task seed.
