"""
Modal deployment for feudal-sim ART training.

Image: headless feudal-sim (no renderer) + rl extra (fastapi, openpipe-art).
GPU: A100-80GB — Qwen3-8B full FT + colocated vLLM inference needs the headroom.
Secrets: FIREWORKS_API_KEY / OPENAI_API_KEY flow in from the deploying shell.
Volumes:
  - feudal-art-state: ART's ~/.art (checkpoints, registry) persists across runs
  - feudal-runs:      training outputs (metrics.jsonl, trajectory samples)

Deploy:  modal deploy modal_app.py
Smoke:   modal run modal_app.py::train --smoke
Train:   modal run modal_app.py::train --iterations 10 --groups 4 --turns 16
"""

from pathlib import Path

import modal

REPO_ROOT = Path(__file__).parent

_IGNORE_DIRS = {
    ".git", ".venv", "runs", "logs", "mlruns", "mlartifacts", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".claude", "jobs",
}
_IGNORE_PARTS = {("render", "build"), ("render", "CMakeFiles")}


def _ignore(rel: Path) -> bool:
    parts = rel.parts
    if any(p in _IGNORE_DIRS for p in parts):
        return True
    if any(parts[: len(pair)] == pair for pair in _IGNORE_PARTS):
        return True
    if rel.name.startswith("._") or rel.suffix == ".so":
        return True
    return False


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("procps")  # ART LocalBackend needs pkill
    .pip_install("uv")
    .env({"FEUDAL_SIM_NO_RENDERER": "1", "PYTHONHASHSEED": "0"})
    .add_local_dir(REPO_ROOT, remote_path="/app", ignore=_ignore, copy=True)
    .run_commands("cd /app && uv sync --extra rl")
)

app = modal.App("feudal-sim-rl", image=image)

art_volume = modal.Volume.from_name("feudal-art-state", create_if_missing=True)
runs_volume = modal.Volume.from_name("feudal-runs", create_if_missing=True)
hf_volume = modal.Volume.from_name("feudal-hf-cache", create_if_missing=True)

secrets = modal.Secret.from_local_environ(["FIREWORKS_API_KEY", "OPENAI_API_KEY"])


@app.function(gpu="A100-80GB", timeout=3600, secrets=[secrets],
              volumes={"/root/.art": art_volume,
                       "/root/.cache/huggingface": hf_volume})
def probe():
    """Debug: exercise ART LocalBackend registration with full tracebacks."""
    import subprocess

    code = r'''
import asyncio, traceback

async def _probe():
    import art
    from art.local import LocalBackend
    import torch
    print(f"torch {torch.__version__}, cuda={torch.cuda.is_available()}", flush=True)
    model = art.TrainableModel(name="probe", project="feudal-sim", base_model="Qwen/Qwen3-8B")
    backend = LocalBackend()
    print("registering...", flush=True)
    await model.register(backend)
    print(f"registered; inference name: {model.get_inference_name()}", flush=True)

try:
    asyncio.run(_probe())
except Exception:
    traceback.print_exc()
    raise
'''
    subprocess.run(["/app/.venv/bin/python", "-c", code], cwd="/app", check=True)


@app.function(
    gpu="A100-80GB",
    timeout=6 * 60 * 60,
    secrets=[secrets],
    volumes={
        "/root/.art": art_volume,
        "/app/runs": runs_volume,
        "/root/.cache/huggingface": hf_volume,
    },
)
def train(
    base_model: str = "Qwen/Qwen3-8B",
    iterations: int = 10,
    groups: int = 4,
    turns: int = 16,
    map_size: int = 20,
    num_houses: int = 4,
    opponent_model: str = "",
    smoke: bool = False,
):
    import subprocess

    cmd = [
        "/app/.venv/bin/python", "scripts/art_train.py",
        "--base-model", base_model,
        "--iterations", "1" if smoke else str(iterations),
        "--groups", "1" if smoke else str(groups),
        "--turns", "2" if smoke else str(turns),
        "--map-size", str(map_size),
        "--num-houses", str(num_houses),
        "--out-dir", "/app/runs",
    ]
    if opponent_model:
        cmd += ["--opponent-model", opponent_model]
    if smoke:
        cmd.append("--smoke")

    print(f"🚀 {' '.join(cmd)}")
    subprocess.run(cmd, cwd="/app", check=True)
    runs_volume.commit()
    art_volume.commit()
