# Feudal Sim

A feudal simulation game with hex-based territories, featuring Python game logic and C++ rendering.

## Features

- Hex-based territorial simulation
- Real-time C++ renderer with interactive controls
- Multi-house feudal system with resources and population
- Shared memory communication between Python and C++

## Quick Start

### Prerequisites

- Python 3.8+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)
- System dependencies (installed automatically by build script)

### Installation

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Build the project**:
   ```bash
   ./build.sh
   ```

3. **Run the simulation**:
   ```bash
   uv run python main.py
   ```

## Controls

- **WASD**: Move camera
- **Mouse wheel**: Zoom in/out
- **T**: Toggle territory display
- **Mouse hover**: View tile information
- **Enter**: Step through simulation

## Development

### Manual Build

If you prefer to build manually:

```bash
# Setup Python environment
uv sync --extra dev

# Build C++ renderer
mkdir -p render/build
cd render/build
cmake ..
cmake --build .
cp renderer*.so ../../feudal_sim/renderer.so
```

### Project Structure

```
feudal-sim/
├── feudal_sim/           # Python game logic
│   ├── ai/              # LLM agent tools and prompts
│   ├── components/      # ECS components (position, resources, ...)
│   ├── core/            # Simulation loop, events, combat
│   ├── entities/        # Positioned entities (caravans, ...)
│   ├── houses/          # House management
│   └── map/             # Hex grid and rendering
├── render/              # C++ renderer
│   ├── renderer.cpp     # Main rendering code
│   └── CMakeLists.txt   # Build configuration
├── scripts/             # Manual demo/exploration scripts
├── tests/               # Pytest suite
├── main.py              # Entry point
├── build.sh             # Unified build script
└── pyproject.toml       # Project configuration
```

### Testing

```bash
uv run pytest
```

### Code Formatting

```bash
uv run black .
uv run ruff check .
```

## System Dependencies

The build script automatically installs:

- **macOS**: raylib, cmake (via Homebrew)
- **Ubuntu/Debian**: cmake, build-essential, libraylib-dev, pkg-config
- **Arch Linux**: cmake, raylib, pkg-config
- **CentOS/RHEL**: cmake, gcc-c++, raylib-devel, pkg-config