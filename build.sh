#!/bin/bash

set -e

echo "🏗️  Building Feudal Sim..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}❌ uv is not installed. Please install it first:${NC}"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Detect OS and install system dependencies
echo -e "${YELLOW}📦 Checking system dependencies...${NC}"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if ! command -v brew &> /dev/null; then
        echo -e "${RED}❌ Homebrew is required on macOS${NC}"
        exit 1
    fi
    
    if ! brew list raylib &> /dev/null; then
        echo -e "${YELLOW}Installing raylib via Homebrew...${NC}"
        brew install raylib
    fi
    
    if ! brew list cmake &> /dev/null; then
        echo -e "${YELLOW}Installing cmake via Homebrew...${NC}"
        brew install cmake
    fi
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v apt-get &> /dev/null; then
        # Ubuntu/Debian
        echo -e "${YELLOW}Installing dependencies via apt...${NC}"
        sudo apt-get update
        sudo apt-get install -y cmake build-essential libraylib-dev pkg-config
    elif command -v yum &> /dev/null; then
        # CentOS/RHEL
        echo -e "${YELLOW}Installing dependencies via yum...${NC}"
        sudo yum install -y cmake gcc-c++ raylib-devel pkg-config
    elif command -v pacman &> /dev/null; then
        # Arch Linux
        echo -e "${YELLOW}Installing dependencies via pacman...${NC}"
        sudo pacman -S --needed cmake raylib pkg-config
    else
        echo -e "${RED}❌ Unsupported Linux distribution${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

# Setup Python environment with uv
echo -e "${YELLOW}🐍 Setting up Python environment...${NC}"
uv sync --extra dev

# Build C++ renderer
echo -e "${YELLOW}⚙️  Building C++ renderer...${NC}"
mkdir -p render/build
cd render/build
cmake ..
cmake --build .

# Find and copy the built library
SHARED_OBJECT=$(find . -name "renderer*.so" | head -1)
if [ -f "$SHARED_OBJECT" ]; then
    echo -e "${GREEN}📦 Found renderer library: $SHARED_OBJECT${NC}"
    cp "$SHARED_OBJECT" ../../feudal_sim/renderer.so
    echo -e "${GREEN}✅ Renderer library copied to feudal_sim/renderer.so${NC}"
else
    echo -e "${RED}❌ Renderer library not found${NC}"
    exit 1
fi

cd ../..

echo -e "${GREEN}✅ Build completed successfully!${NC}"
echo -e "${YELLOW}🚀 To run the simulation:${NC}"
echo "   uv run python main.py"
echo ""
echo -e "${YELLOW}🧪 To run tests:${NC}"
echo "   uv run pytest"