"""
Feudal env server — HTTP wrapper around FeudalEnv.

One active episode per process (the sim's config module is process-global;
horizontal scale comes from running multiple server processes/containers,
e.g. Modal). This is the substrate for:
  - TRL GRPO environment clients (reset/step per rollout)
  - Modal rollout workers
  - Remote eval drivers

Run:
  uv run --extra rl python -m feudal_sim.rl.server --port 8100

Endpoints:
  POST /episodes              {task: TaskConfig}  → {episode_id, observation}
  POST /episodes/{id}/step                          → turn summary + observation
  GET  /episodes/{id}/state                       → per-house signals
  GET  /episodes/{id}/result                      → terminal summary
  DELETE /episodes/{id}                           → teardown
"""

import argparse
import asyncio
import uuid
from typing import Any, Dict

from feudal_sim.core.logger import get_logger

log = get_logger(__name__)


def create_app():
    from fastapi import FastAPI, HTTPException

    from feudal_sim.rl.env import FeudalEnv, TaskConfig

    app = FastAPI(title="feudal-sim env server")
    app.state.env = None
    app.state.episode_id = None
    app.state.lock = asyncio.Lock()

    @app.post("/episodes")
    async def create_episode(body: Dict[str, Any]):
        async with app.state.lock:
            if app.state.env is not None and not app.state.env.done:
                raise HTTPException(
                    409, "an episode is already active on this server process"
                )
            task = TaskConfig(**body.get("task", {}))
            env = FeudalEnv(task)
            observation = env.reset()
            app.state.env = env
            app.state.episode_id = uuid.uuid4().hex[:12]
            return {
                "episode_id": app.state.episode_id,
                "task": task.to_dict(),
                "observation": observation,
            }

    @app.post("/episodes/{episode_id}/step")
    async def step(episode_id: str):
        async with app.state.lock:
            env = _get_env(app, episode_id)
            if env.done:
                return {"done": True, "result": env.result()}
            summary = await env.step_turn()
            return {
                "done": env.done,
                "turn": summary["turn"],
                "game_over": summary["game_over"],
                "winner": summary["winner"],
                "observation": env.observe(),
            }

    @app.get("/episodes/{episode_id}/state")
    async def state(episode_id: str):
        env = _get_env(app, episode_id)
        return {"done": env.done, "observation": env.observe()}

    @app.get("/episodes/{episode_id}/result")
    async def result(episode_id: str):
        env = _get_env(app, episode_id)
        return env.result()

    @app.delete("/episodes/{episode_id}")
    async def teardown(episode_id: str):
        async with app.state.lock:
            _get_env(app, episode_id)
            app.state.env = None
            app.state.episode_id = None
            return {"ok": True}

    def _get_env(app, episode_id: str) -> FeudalEnv:
        if app.state.env is None or app.state.episode_id != episode_id:
            raise HTTPException(404, f"no active episode '{episode_id}'")
        return app.state.env

    return app


def main():
    parser = argparse.ArgumentParser(description="feudal-sim env server")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
