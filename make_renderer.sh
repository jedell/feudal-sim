#!/bin/bash

# Set the project directories
# get project root absolute path
PROJECT_ROOT=$(pwd)
BUILD_DIR="$PROJECT_ROOT/render/build"
SOURCE_DIR="$PROJECT_ROOT/render"
TARGET_DIR="$PROJECT_ROOT/feudal_sim/renderer.so"

# Create the build directory if it doesn't exist
mkdir -p $BUILD_DIR

# Navigate to the build directory
cd $BUILD_DIR

# Run CMake to configure the project
cmake $SOURCE_DIR

# Build the project
cmake --build .

# Check if the build was successful
if [ $? -eq 0 ]; then
    echo "Build successful."

    # Find the compiled shared object file
    SHARED_OBJECT=$(find . -name "renderer*.so")

    # Check if the shared object file exists
    if [ -f "$SHARED_OBJECT" ]; then
        echo "Found shared object file: $SHARED_OBJECT"

        # Move the shared object file to the target directory
        mv $SHARED_OBJECT $TARGET_DIR

        echo "Shared object file moved to $TARGET_DIR"
    else
        echo "Shared object file not found."
    fi
else
    echo "Build failed."
fi