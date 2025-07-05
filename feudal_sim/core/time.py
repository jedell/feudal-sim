from enum import Enum
from dataclasses import dataclass

class Season(Enum):
    SPRING = "spring"
    SUMMER = "summer" 
    AUTUMN = "autumn"
    WINTER = "winter"

@dataclass
class GameTime:
    year: int = 1
    season: Season = Season.SPRING
    turn: int = 1
    
    def advance_turn(self):
        self.turn += 1
        from feudal_sim.core.config import config
        turns_per_season = config.get('simulation.time.turns_per_season', 4)
        if self.turn > turns_per_season:
            self.turn = 1
            self.year += 1
        
        # Update season based on turn
        seasons = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
        self.season = seasons[(self.turn - 1) % 4]
    
    def get_seasonal_modifier(self, activity: str) -> float:
        """Get seasonal modifiers for different activities"""
        from feudal_sim.core.config import config
        
        # Get modifiers from config with fallback to defaults
        season_name = self.season.value
        config_path = f'simulation.resources.seasonal_modifiers.{season_name}.{activity}'
        return config.get(config_path, 1.0)
    
    def __str__(self):
        return f"Year {self.year}, {self.season.value.title()}, Turn {self.turn}"