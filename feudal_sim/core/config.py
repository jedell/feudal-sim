"""
Configuration system for the feudal simulation.
Provides centralized, extensible configuration management.
"""

import json
import os
from typing import Any, Dict, Optional
from pathlib import Path


class Config:
    """
    Centralized configuration management with dot notation access.
    Loads configuration from JSON files and provides easy access.
    """
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            # Default to config/ directory relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_dir = project_root / "config"
        
        self.config_dir = Path(config_dir)
        self._config_data = {}
        self.load_all_configs()

    def load_config(self, config_name: str):
        """Load a specific configuration file from the config directory."""
        config_file = self.config_dir / f"{config_name}.json"
        if not config_file.exists():
            print(f"⚠️  Config file {config_file} not found, using defaults")
            self._config_data = self._get_default_config()
            return
    
    def load_all_configs(self):
        """Load all JSON configuration files from the config directory."""
        if not self.config_dir.exists():
            print(f"⚠️  Config directory {self.config_dir} not found, using defaults")
            self._config_data = self._get_default_config()
            return
        
        self._config_data = {}
        
        # Load all .json files in config directory
        for config_file in self.config_dir.glob("*.json"):
            config_name = config_file.stem
            try:
                with open(config_file, 'r') as f:
                    file_data = json.load(f)
                    self._config_data[config_name] = file_data
                    print(f"📄 Loaded config: {config_name}")
            except Exception as e:
                print(f"⚠️  Failed to load {config_file}: {e}")
        
        # If no configs loaded, use defaults
        if not self._config_data:
            print("📄 No config files found, using defaults")
            self._config_data = self._get_default_config()
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        Examples: config.get('population.birth_rate'), config.get('resources.gathering_multiplier')
        """
        keys = key_path.split('.')
        current = self._config_data
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            if default is not None:
                return default
            raise KeyError(f"Configuration key '{key_path}' not found")
    
    def get_section(self, section_name: str) -> Dict[str, Any]:
        """Get an entire configuration section."""
        return self._config_data.get(section_name, {})
    
    def set(self, key_path: str, value: Any):
        """Set configuration value (for runtime modifications)."""
        keys = key_path.split('.')
        current = self._config_data
        
        # Navigate to parent of target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final key
        current[keys[-1]] = value
    
    def save_config(self, filename: str):
        """Save current configuration to a file."""
        output_path = self.config_dir / f"{filename}.json"
        self.config_dir.mkdir(exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self._config_data, f, indent=2)
        print(f"💾 Saved config to {output_path}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration if no files are found."""
        return {
            "simulation": {
                "population": {
                    "birth_rate": 0.035,
                    "death_rate": 0.030,
                    "loyalty_decay_rate": 1.0,
                    "efficiency_curve_steepness": 1.0
                },
                "resources": {
                    "gathering_multiplier": 10,
                    "seasonal_modifiers": {
                        "spring": {"farming": 1.2, "trade": 1.0, "military": 1.0},
                        "summer": {"farming": 1.5, "trade": 1.3, "military": 1.2},
                        "autumn": {"farming": 1.8, "trade": 1.1, "military": 1.0},
                        "winter": {"farming": 0.3, "trade": 0.7, "military": 0.8}
                    }
                },
                "time": {
                    "turns_per_season": 4,
                    "starting_year": 1,
                    "starting_season": "spring"
                },
                "world_generation": {
                    "map_size": 80,
                    "num_houses": 2,
                    "num_rivers": 4,
                    "resource_nodes": {
                        "count_multiplier": 0.05,
                        "gold_mine_ratio": 0.5
                    }
                }
            },
            "world": {
                "tile_size": 30,
                "resource_indicators": {
                    "radius_multiplier": 0.3,
                    "font_size_multiplier": 0.25,
                    "min_font_size": 8,
                    "max_font_size": 16
                },
                "colors": {
                    "gold_mine": [255, 215, 0, 200],
                    "iron_deposit": [169, 169, 169, 200],
                    "stone_quarry": [105, 105, 105, 200],
                    "rare_herbs": [0, 255, 127, 200]
                }
            }
        }
    
    def print_config(self):
        """Print current configuration for debugging."""
        print("📋 Current Configuration:")
        print(json.dumps(self._config_data, indent=2))


# Global config instance
config = Config()