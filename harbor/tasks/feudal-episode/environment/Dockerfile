FROM python:3.11-slim

# Headless feudal-sim: no raylib, no cmake, no renderer .so
ENV FEUDAL_SIM_NO_RENDERER=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1

RUN pip install uv

WORKDIR /app
# Repo tarball is vendored into this build context by prepare.sh
COPY feudal-sim.tar.gz /app/
RUN tar xzf feudal-sim.tar.gz && rm feudal-sim.tar.gz

RUN uv sync --no-dev

# Sanity: package imports and the RL env module loads headless
RUN .venv/bin/python -c "from feudal_sim.rl.env import FeudalEnv, TaskConfig; print('feudal-sim headless OK')"

CMD ["/bin/bash"]
