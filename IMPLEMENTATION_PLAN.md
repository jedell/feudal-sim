# 🏗️ Feudal Simulation Implementation Plan

## Phase 0: Foundation Fixes (Week 1) - CRITICAL

### 1. Fix Resource Accumulation Bug
**File**: `feudal_sim/houses/house.py:91-93`
**Issue**: Resources are overwritten instead of accumulated
**Fix**: Change `=` to `+=` in `gather_resources()` method

### 2. Enable Action Execution
**File**: `main.py:64`
**Issue**: Action phase is commented out
**Fix**: Implement basic action dispatcher

### 3. Clean Architecture Setup
**Goal**: Establish solid foundation for simulation systems

## Software Architecture Foundation

### Core Design Principles

1. **Event-Driven System**: Central event bus for inter-system communication
2. **Component-Based Entities**: Houses, Territories, and Resources as composable components
3. **Time Management**: Centralized time system with seasons, years, and turn phases
4. **Configuration-Driven**: Data files for easy tuning without code changes
5. **Observable Systems**: All changes emit events for AI decision-making
6. **Modular AI**: Pluggable AI components that can be swapped and tested

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Layer                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ AI Agents   │ │ Decision    │ │ Goal & Strategy         ││
│  │ (Lords)     │ │ Trees       │ │ Management              ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                 Game Systems Layer                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Economic    │ │ Population  │ │ Military &              ││
│  │ System      │ │ System      │ │ Diplomacy               ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Agricultural│ │ Environment │ │ Events &                ││
│  │ System      │ │ & Weather   │ │ Disasters               ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                   Core Engine Layer                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Event Bus   │ │ Time        │ │ Data Management         ││
│  │ System      │ │ Management  │ │ (Config, Save/Load)     ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Entity      │ │ Component   │ │ Resource                ││
│  │ Management  │ │ System      │ │ Management              ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                  Foundation Layer                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Hex Grid    │ │ Territory   │ │ Renderer                ││
│  │ System      │ │ Management  │ │ (C++ via SharedMemory)  ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Implementation Strategy

### Step 1: Core Engine Foundation (Week 1-2)

#### A. Event Bus System
Central nervous system for simulation communication

```python
# feudal_sim/core/events.py
from typing import Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum

class EventType(Enum):
    # Time Events
    SEASON_CHANGED = "season_changed"
    YEAR_CHANGED = "year_changed"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    
    # Resource Events
    RESOURCE_CHANGED = "resource_changed"
    HARVEST_COMPLETED = "harvest_completed"
    TRADE_COMPLETED = "trade_completed"
    
    # Population Events
    POPULATION_CHANGED = "population_changed"
    MIGRATION_OCCURRED = "migration_occurred"
    BIRTH_DEATH_UPDATE = "birth_death_update"
    
    # Military Events
    ARMY_MOVED = "army_moved"
    BATTLE_OCCURRED = "battle_occurred"
    FORTIFICATION_BUILT = "fortification_built"
    
    # Environmental Events
    WEATHER_CHANGED = "weather_changed"
    DISASTER_OCCURRED = "disaster_occurred"
    
    # AI Events
    DECISION_MADE = "decision_made"
    GOAL_ACHIEVED = "goal_achieved"
    GOAL_FAILED = "goal_failed"

@dataclass
class Event:
    type: EventType
    source: Any
    data: Dict[str, Any]
    timestamp: float

class EventBus:
    def __init__(self):
        self._listeners: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
    
    def subscribe(self, event_type: EventType, callback: Callable):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
    
    def emit(self, event: Event):
        self._event_history.append(event)
        if event.type in self._listeners:
            for callback in self._listeners[event.type]:
                callback(event)
    
    def get_history(self, event_types: List[EventType] = None, since: float = None):
        filtered = self._event_history
        if event_types:
            filtered = [e for e in filtered if e.type in event_types]
        if since:
            filtered = [e for e in filtered if e.timestamp >= since]
        return filtered
```

#### B. Time Management System
Centralized time control with seasons and phases

```python
# feudal_sim/core/time.py
from enum import Enum
from dataclasses import dataclass

class Season(Enum):
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"

class TurnPhase(Enum):
    PRODUCTION = "production"      # Resources generated
    POPULATION = "population"      # Birth/death, migration
    ACTIONS = "actions"           # AI decisions executed
    EVENTS = "events"             # Random events, disasters
    CLEANUP = "cleanup"           # End of turn processing

@dataclass
class GameTime:
    year: int = 1
    season: Season = Season.SPRING
    turn: int = 1
    phase: TurnPhase = TurnPhase.PRODUCTION
    
    def advance_phase(self):
        phases = list(TurnPhase)
        current_index = phases.index(self.phase)
        
        if current_index + 1 < len(phases):
            self.phase = phases[current_index + 1]
        else:
            self.phase = TurnPhase.PRODUCTION
            self.advance_season()
    
    def advance_season(self):
        seasons = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
        current_index = seasons.index(self.season)
        
        if current_index + 1 < len(seasons):
            self.season = seasons[current_index + 1]
        else:
            self.season = Season.SPRING
            self.year += 1

class TimeManager:
    def __init__(self, event_bus):
        self.game_time = GameTime()
        self.event_bus = event_bus
        
    def advance_turn(self):
        old_season = self.game_time.season
        old_year = self.game_time.year
        
        self.game_time.advance_phase()
        
        # Emit events for changes
        if self.game_time.season != old_season:
            self.event_bus.emit(Event(
                EventType.SEASON_CHANGED,
                self,
                {"old_season": old_season, "new_season": self.game_time.season}
            ))
            
        if self.game_time.year != old_year:
            self.event_bus.emit(Event(
                EventType.YEAR_CHANGED,
                self,
                {"old_year": old_year, "new_year": self.game_time.year}
            ))
```

#### C. Configuration System
Data-driven parameter management

```python
# feudal_sim/core/config.py
import json
from pathlib import Path
from typing import Dict, Any

class Config:
    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = config_dir
        self._data: Dict[str, Any] = {}
        self.load_all_configs()
    
    def load_all_configs(self):
        config_files = [
            "agriculture.json",
            "population.json", 
            "economy.json",
            "military.json",
            "environment.json",
            "ai.json"
        ]
        
        for file in config_files:
            config_path = self.config_dir / file
            if config_path.exists():
                with open(config_path) as f:
                    section_name = file.replace(".json", "")
                    self._data[section_name] = json.load(f)
    
    def get(self, key: str, default=None):
        keys = key.split(".")
        current = self._data
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        
        return current
```

### Step 2: Enhanced Entity System (Week 2-3)

#### A. Component-Based Architecture
Flexible, composable entities

```python
# feudal_sim/core/entities.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Type
import uuid

class Component(ABC):
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
    
    @abstractmethod
    def update(self, dt: float, event_bus):
        pass

class Entity:
    def __init__(self, entity_id: str = None):
        self.id = entity_id or str(uuid.uuid4())
        self._components: Dict[Type[Component], Component] = {}
    
    def add_component(self, component: Component):
        component.entity_id = self.id
        self._components[type(component)] = component
    
    def get_component(self, component_type: Type[Component]) -> Component:
        return self._components.get(component_type)
    
    def has_component(self, component_type: Type[Component]) -> bool:
        return component_type in self._components
    
    def update(self, dt: float, event_bus):
        for component in self._components.values():
            component.update(dt, event_bus)

class EntityManager:
    def __init__(self):
        self._entities: Dict[str, Entity] = {}
    
    def create_entity(self, entity_id: str = None) -> Entity:
        entity = Entity(entity_id)
        self._entities[entity.id] = entity
        return entity
    
    def get_entity(self, entity_id: str) -> Entity:
        return self._entities.get(entity_id)
    
    def get_entities_with_component(self, component_type: Type[Component]):
        return [entity for entity in self._entities.values() 
                if entity.has_component(component_type)]
```

### Step 3: Core Systems Implementation (Week 3-4)

#### A. Resource System with Proper Accumulation

```python
# feudal_sim/systems/resources.py
from dataclasses import dataclass, field
from typing import Dict
from feudal_sim.core.entities import Component

@dataclass
class ResourceStore:
    grain: float = 0.0
    livestock: float = 0.0
    wood: float = 0.0
    stone: float = 0.0
    iron: float = 0.0
    textiles: float = 0.0
    tools: float = 0.0
    weapons: float = 0.0
    luxury_goods: float = 0.0
    
    def add(self, resource_type: str, amount: float):
        if hasattr(self, resource_type):
            current = getattr(self, resource_type)
            setattr(self, resource_type, current + amount)
    
    def consume(self, resource_type: str, amount: float) -> bool:
        if hasattr(self, resource_type):
            current = getattr(self, resource_type)
            if current >= amount:
                setattr(self, resource_type, current - amount)
                return True
        return False
    
    def get(self, resource_type: str) -> float:
        return getattr(self, resource_type, 0.0)

class ResourceComponent(Component):
    def __init__(self, entity_id: str):
        super().__init__(entity_id)
        self.resources = ResourceStore()
        self.production_rates: Dict[str, float] = {}
        self.consumption_rates: Dict[str, float] = {}
    
    def update(self, dt: float, event_bus):
        # Produce resources
        for resource, rate in self.production_rates.items():
            self.resources.add(resource, rate * dt)
        
        # Consume resources
        for resource, rate in self.consumption_rates.items():
            self.resources.consume(resource, rate * dt)
```

#### B. Population System

```python
# feudal_sim/systems/population.py
from dataclasses import dataclass
from feudal_sim.core.entities import Component

@dataclass
class PopulationDemographics:
    peasants: int = 0
    craftsmen: int = 0
    merchants: int = 0
    nobles: int = 0
    
    @property
    def total(self) -> int:
        return self.peasants + self.craftsmen + self.merchants + self.nobles
    
    def distribute_by_ratios(self, total_pop: int):
        # Historical ratios: 80% peasants, 15% craftsmen, 3% merchants, 2% nobles
        self.peasants = int(total_pop * 0.80)
        self.craftsmen = int(total_pop * 0.15)
        self.merchants = int(total_pop * 0.03)
        self.nobles = int(total_pop * 0.02)

class PopulationComponent(Component):
    def __init__(self, entity_id: str):
        super().__init__(entity_id)
        self.demographics = PopulationDemographics()
        self.birth_rate = 0.035
        self.death_rate = 0.030
        self.loyalty = 100.0
        self.food_security = 1.0
        
    def update(self, dt: float, event_bus):
        # Calculate population change
        net_growth_rate = (self.birth_rate * self.food_security) - self.death_rate
        population_change = int(self.demographics.total * net_growth_rate * dt)
        
        if population_change != 0:
            new_total = max(0, self.demographics.total + population_change)
            self.demographics.distribute_by_ratios(new_total)
            
            event_bus.emit(Event(
                EventType.POPULATION_CHANGED,
                self,
                {"entity_id": self.entity_id, "change": population_change, "new_total": new_total}
            ))
```

### Step 4: Integration with Existing Code (Week 4-5)

#### A. Retrofit House Class

```python
# feudal_sim/houses/enhanced_house.py
from feudal_sim.core.entities import Entity
from feudal_sim.systems.resources import ResourceComponent
from feudal_sim.systems.population import PopulationComponent

class EnhancedHouse(Entity):
    def __init__(self, name: str, color):
        super().__init__(entity_id=name)
        self.name = name
        self.color = color
        
        # Add components
        self.add_component(ResourceComponent(self.id))
        self.add_component(PopulationComponent(self.id))
        
        # Initialize existing territory system
        self.territory = set()
        self.border_tiles = set()
    
    @property 
    def resources(self):
        return self.get_component(ResourceComponent).resources
    
    @property
    def population_info(self):
        return self.get_component(PopulationComponent)
    
    def gather_resources_fixed(self):
        """Fixed version that accumulates instead of overwrites"""
        resource_comp = self.get_component(ResourceComponent)
        
        for hex_tile in self.territory:
            # Accumulate instead of overwrite
            resource_comp.resources.add('grain', hex_tile.food_output * 10)
            resource_comp.resources.add('wood', hex_tile.material_output * 10) 
            resource_comp.resources.add('iron', hex_tile.metal_output * 10)
```

#### B. Enhanced Main Loop

```python
# main.py - Enhanced Version
def main():
    # Initialize core systems
    event_bus = EventBus()
    time_manager = TimeManager(event_bus)
    config = Config()
    entity_manager = EntityManager()
    
    simulation = Simulation(event_bus, time_manager, config, entity_manager)
    
    try:
        while True:
            simulation.step()
            simulation.render()
            
            # Check for win conditions
            if simulation.check_victory_conditions():
                break
                
            input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        simulation.cleanup()

class Simulation:
    def __init__(self, event_bus, time_manager, config, entity_manager):
        self.event_bus = event_bus
        self.time_manager = time_manager
        self.config = config
        self.entity_manager = entity_manager
        
        self.hex_grid = self.create_hex_grid()
        self.houses = self.create_houses()
        
    def step(self):
        # Execute turn phases systematically
        phase = self.time_manager.game_time.phase
        
        if phase == TurnPhase.PRODUCTION:
            self.execute_production_phase()
        elif phase == TurnPhase.POPULATION:
            self.execute_population_phase()
        elif phase == TurnPhase.ACTIONS:
            self.execute_actions_phase()  # NOW IMPLEMENTED!
        elif phase == TurnPhase.EVENTS:
            self.execute_events_phase()
        elif phase == TurnPhase.CLEANUP:
            self.execute_cleanup_phase()
            
        self.time_manager.advance_turn()
    
    def execute_actions_phase(self):
        """AI houses make decisions and take actions"""
        for house in self.houses:
            if hasattr(house, 'ai_agent'):
                house.ai_agent.make_decisions(self.get_world_state())
                house.ai_agent.execute_actions()
```

## Migration Path

### Week 1: Critical Fixes
1. Fix resource accumulation bug
2. Enable action execution
3. Set up event bus
4. Add time management

### Week 2-3: New Architecture
1. Implement component system
2. Create enhanced house class
3. Build resource/population systems

### Week 4-5: Integration
1. Migrate existing houses to new system
2. Connect with rendering
3. Add basic AI decision-making

### Week 6+: Feature Expansion
1. Agricultural systems
2. Economic modeling
3. Environmental events
4. Advanced AI

This foundation provides:
- **Scalability**: Easy to add new systems
- **Modularity**: Components can be tested independently  
- **Observability**: Event system provides rich data for AI
- **Configuration**: Data-driven parameters for easy tuning
- **Maintainability**: Clear separation of concerns

The architecture supports your vision of realistic simulation with straightforward systems that provide rich primitives for AI interaction.