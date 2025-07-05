"""Custom build hook for compiling C++ renderer with CMake."""
import os
import subprocess
import shutil
from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        """Build the C++ renderer during wheel build."""
        print("Building C++ renderer...")
        
        project_root = Path(self.root)
        build_dir = project_root / "render" / "build"
        source_dir = project_root / "render"
        
        # Create build directory
        build_dir.mkdir(parents=True, exist_ok=True)
        
        # Run CMake
        subprocess.run(["cmake", str(source_dir)], cwd=build_dir, check=True)
        subprocess.run(["cmake", "--build", "."], cwd=build_dir, check=True)
        
        # Find and copy the built library
        for lib_file in build_dir.glob("renderer*.so"):
            target = project_root / "feudal_sim" / "renderer.so"
            shutil.copy2(lib_file, target)
            print(f"Copied {lib_file} to {target}")
            break
        else:
            raise RuntimeError("Could not find built renderer library")