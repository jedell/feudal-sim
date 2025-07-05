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
        if self.turn > 4:  # 4 turns per year (one per season)
            self.turn = 1
            self.year += 1
        
        # Update season based on turn
        seasons = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
        self.season = seasons[(self.turn - 1) % 4]
    
    def get_seasonal_modifier(self, activity: str) -> float:
        """Get seasonal modifiers for different activities"""
        modifiers = {
            Season.SPRING: {'farming': 1.1, 'trade': 1.0, 'military': 1.0},
            Season.SUMMER: {'farming': 1.2, 'trade': 1.1, 'military': 1.1}, 
            Season.AUTUMN: {'farming': 1.3, 'trade': 1.0, 'military': 1.0},
            Season.WINTER: {'farming': 0.5, 'trade': 0.8, 'military': 0.8}
        }
        return modifiers.get(self.season, {}).get(activity, 1.0)
    
    def __str__(self):
        return f"Year {self.year}, {self.season.value.title()}, Turn {self.turn}"