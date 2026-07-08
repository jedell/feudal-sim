import random
from enum import Enum
from dataclasses import dataclass


class TurnPhase(Enum):
    PRODUCTION = "production"    # Resource gathering, population growth
    ACTIONS = "actions"         # AI decisions, movements, construction
    EVENTS = "events"           # Random events, diplomacy, trade
    CLEANUP = "cleanup"         # End-of-turn processing, maintenance

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
    phase: TurnPhase = TurnPhase.PRODUCTION
    weather: str = "normal"  # season-long weather state, rolled each season
    
    def advance_phase(self):
        """Advance to the next phase within the current turn."""
        phases = list(TurnPhase)
        current_index = phases.index(self.phase)
        
        if current_index + 1 < len(phases):
            # Move to next phase
            self.phase = phases[current_index + 1]
        else:
            # End of turn - advance turn and reset to first phase
            self.phase = TurnPhase.PRODUCTION
            self.advance_turn()
    
    def advance_turn(self):
        """Advance to the next turn within the season."""
        self.turn += 1
        from feudal_sim.core.config import config
        turns_per_season = config.get('simulation.time.turns_per_season', 4)
        if self.turn > turns_per_season:
            self.turn = 1
            self.advance_season()
        
    def advance_season(self):
        """Advance to the next season and roll its weather."""
        seasons = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
        current_index = seasons.index(self.season)

        if current_index + 1 < len(seasons):
            self.season = seasons[current_index + 1]
        else:
            self.season = Season.SPRING
            self.year += 1
        self.weather = self._roll_weather()

    def _roll_weather(self) -> str:
        """Pick a season-long weather state from the config table."""
        from feudal_sim.core.config import config
        # NB: config.get raises on missing key when default is None — use {}
        states = config.get('simulation.weather.states', {})
        if not states:
            return "normal"
        names = list(states.keys())
        weights = [states[n].get('probability', 0.0) for n in names]
        if not any(w > 0 for w in weights):
            return "normal"
        return random.choices(names, weights=weights, k=1)[0]

    def get_weather_announcement(self) -> str:
        """The herald's word on this season's weather ('' for nothing notable)."""
        from feudal_sim.core.config import config
        try:
            return config.get(f'simulation.weather.states.{self.weather}.announcement', "")
        except KeyError:
            return ""

    def get_seasonal_modifier(self, activity: str) -> float:
        """Get seasonal modifiers for different activities, shifted by the
        season's weather (drought, bounty, storms)."""
        from feudal_sim.core.config import config

        # Get modifiers from config with fallback to defaults
        season_name = self.season.value
        config_path = f'simulation.resources.seasonal_modifiers.{season_name}.{activity}'
        base = config.get(config_path, 1.0)
        try:
            delta = config.get(f'simulation.weather.states.{self.weather}.{activity}_delta', 0.0)
        except KeyError:
            delta = 0.0
        return max(0.05, base + delta or 0.0)
    
    def __str__(self):
        return f"Year {self.year}, {self.season.value.title()}, Week {self.turn}, {self.phase.value.title()} Phase"
    
    def get_date_string(self):
        """Get a formatted date string for messaging (e.g., 'Week 3, Spring, Year 1')."""
        return f"Week {self.turn}, {self.season.value.title()}, Year {self.year}"


class TimeManager:
    """
    Event-driven time management system.
    Coordinates game time progression and emits events for temporal changes.
    """
    
    def __init__(self, event_bus=None):
        self.game_time = GameTime()
        self.event_bus = event_bus
        
    def advance_phase(self):
        """Advance to next phase and emit appropriate events."""
        old_phase = self.game_time.phase
        old_season = self.game_time.season
        old_year = self.game_time.year

        self.game_time.advance_phase()
        
        # Emit phase change event
        if self.event_bus:
            from feudal_sim.core.events import EventType
            self.event_bus.emit(
                EventType.STATE_CHANGED,
                self,
                change_type='phase',
                old_phase=old_phase.value,
                new_phase=self.game_time.phase.value,
                year=self.game_time.year,
                season=self.game_time.season.value,
                turn=self.game_time.turn
            )
        
        # Check for season change
        if self.game_time.season != old_season:
            if self.event_bus:
                self.event_bus.emit(
                    EventType.STATE_CHANGED,
                    self,
                    change_type='season',
                    old_season=old_season.value,
                    new_season=self.game_time.season.value,
                    year=self.game_time.year
                )
                
        # Check for year change
        if self.game_time.year != old_year:
            if self.event_bus:
                self.event_bus.emit(
                    EventType.STATE_CHANGED,
                    self,
                    change_type='year',
                    old_year=old_year,
                    new_year=self.game_time.year
                )
    
    def get_current_status(self) -> dict:
        """Get current time status for display."""
        return {
            'year': self.game_time.year,
            'season': self.game_time.season.value,
            'turn': self.game_time.turn,
            'phase': self.game_time.phase.value
        }
    
    def get_current_date_string(self) -> str:
        """Get current date as formatted string for messaging."""
        return self.game_time.get_date_string()