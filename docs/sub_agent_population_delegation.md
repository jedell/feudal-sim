# Sub-Agent Population Delegation System

## 🎯 Feature Overview

Implement a system where houses can delegate portions of their population to sub-agents (generals, work crews, settlers) who then operate independently with their assigned group. This enables tactical expansion where sub-agents can move across the map, observe terrain, and execute settlement/expansion actions autonomously.

## 🏗️ Core Workflow

### **Phase 1: Delegation**
1. **Lord creates expansion order** via existing `order_territory_expansion` tool
2. **Lord chooses delegation method**: 
   - Send settlers (civilian group)
   - Send general (military group)
   - Send work crew (construction group)
3. **Lord assigns population** from house to sub-agent group
4. **Sub-agent entity created** with assigned population and mission

### **Phase 2: Independent Operation**
1. **Sub-agent group moves** toward target area independently
2. **Terrain observation** at each position and surrounding tiles
3. **Intel gathering** on tile ownership, resources, threats
4. **Autonomous decision making** based on mission parameters

### **Phase 3: Settlement/Resolution**
1. **Settlement action** if tiles are unclaimed
2. **Conflict detection** if tiles are owned by another house
3. **Territorial claiming** and ownership transfer
4. **Report back** to parent house with results

## 🔧 Architecture Design

### **Population Assignment System**

#### **Modified PopulationComponent**
```python
class PopulationComponent(Component):
    # Existing fields...
    assigned_population: Dict[str, int]  # {sub_agent_id: population_count}
    available_population: int           # population - sum(assigned_population)
    
    def assign_population_to_agent(self, agent_id: str, count: int) -> bool
    def recall_population_from_agent(self, agent_id: str) -> int
    def get_available_population(self) -> int
    def get_assigned_population_total(self) -> int
```

#### **New SubAgentGroup Component**
```python
@dataclass
class AssignedPopulation:
    workers: int = 0
    soldiers: int = 0
    specialists: int = 0  # engineers, scouts, etc.
    
class SubAgentGroup(Component):
    parent_house_id: str
    assigned_population: AssignedPopulation
    group_type: str  # "military", "settler", "construction"
    mission_parameters: Dict[str, Any]
    
    def get_group_strength(self) -> int
    def get_settlement_capability(self) -> float
    def get_combat_strength(self) -> int
    def consume_supplies(self, amount: int) -> bool
```

### **Expansion Delegation System**

#### **Modified TerritoryComponent**
```python
class TerritoryComponent(Component):
    # Existing fields...
    delegated_expansions: List[DelegatedExpansion]
    
@dataclass
class DelegatedExpansion:
    expansion_order: ExpansionOrder
    sub_agent_id: str
    delegation_type: str  # "settler", "military", "construction"
    assigned_population: AssignedPopulation
    status: str  # "dispatched", "in_progress", "completed", "failed"
```

#### **New Terrain Observation Component**
```python
class TerrainObservation(Component):
    observed_tiles: Dict[tuple, Dict]  # {(q,r): tile_info}
    observation_range: int
    last_observation_turn: int
    
    def observe_current_area(self, hex_grid, current_position) -> Dict
    def assess_settlement_viability(self, target_tiles) -> float
    def detect_territorial_conflicts(self, target_tiles) -> List[str]
```

## 📋 Implementation Phases

### **Phase 1: Population Management Foundation** ✅ COMPLETED
- [x] Modify `PopulationComponent` to track assigned vs available population
- [x] Create `SubAgentGroup` component for group management  
- [x] Update population status reporting to show assignments
- [x] Add population validation to prevent over-assignment

### **Phase 2: Sub-Agent Creation & Assignment** ✅ COMPLETED
- [x] Modify `deploy_general` tool to accept population assignment parameters (workers + soldiers)
- [x] Implement population transfer mechanics between house and sub-agent
- [x] Add spatial query system for entity proximity/distance detection
- [x] Enhanced deploy_general with direction-based deployment and natural language orders
- [ ] Create `deploy_settler_group` tool for civilian expansion groups (OPTIONAL)
- [ ] Add sub-agent group visualization (group size indicators on map) (FUTURE)

### **Phase 3: Terrain Observation & Intelligence** ✅ COMPLETED
- [x] **[CRITICAL]** Implement `TerrainObservation` component for sub-agents
- [x] **[CRITICAL]** Add automatic terrain scanning when sub-agents move/act
- [x] Create intelligence reporting back to parent house
- [x] Implement threat detection and assessment using spatial queries

### **Phase 4: Settlement & Claiming Actions** 🚧 CRITICAL PATH
- [ ] **[BLOCKER]** Create `settle_territory` tool for sub-agents  
- [ ] **[BLOCKER]** Implement territorial claiming mechanics
- [ ] **[BLOCKER]** Add TerrainObservation to generals on deployment
- [ ] Add conflict detection for owned tiles (using spatial queries)
- [ ] Create settlement success probability calculations

### **Phase 5: Delegation & Mission System** 📋 PLANNED
- [ ] Create expansion delegation tools for houses
- [ ] Implement mission parameter system for sub-agents (partially done in SubAgentGroup)
- [ ] Add `DelegatedExpansion` tracking to `TerritoryComponent`
- [ ] Create sub-agent mission status reporting

### **Phase 6: Integration & Testing** 📋 PLANNED
- [ ] Full workflow testing: house → delegation → movement → settlement
- [ ] Multi-group coordination testing
- [ ] Edge case handling (group destruction, communication loss)
- [ ] Performance optimization for multiple sub-agents

## 🎯 **CURRENT STATUS (Updated)**

### ✅ **COMPLETED FOUNDATION:**
1. **Population Assignment System** - Houses can assign workers/soldiers to sub-agents
2. **SubAgentGroup Component** - Manages assigned population, supplies, morale, capabilities
3. **Enhanced Deploy System** - Direction-based deployment with natural language orders
4. **Spatial Query System** - EntityManager can find nearby entities, calculate distances, detect conflicts
5. **AI Integration** - Generals have independent AI that can interpret orders
6. **TerrainObservation Component** - Comprehensive terrain scanning, threat detection, opportunity assessment

### 🚧 **IMMEDIATE BLOCKERS FOR EXPANSION:**
1. **Settlement Actions** - Generals need tools to actually claim territory
2. **TerrainObservation Integration** - Add TerrainObservation component to deployed generals

### 📋 **REMAINING FOR FULL SYSTEM:**
3. **Conflict Resolution** - Handle encounters with enemy-owned tiles
4. **Progress Reporting** - Sub-agents report back to parent house
5. **Advanced Delegation** - Houses can delegate specific expansion missions

## 🛠️ Technical Specifications

### **Population Assignment Interface** ✅ IMPLEMENTED
```python
# Current implementation - direction-based deployment
def deploy_general(ctx, direction: str, soldiers_assigned: int, 
                  workers_assigned: int = 0, general_name: str = "General",
                  orders: str = "Patrol the area and await further orders") -> str:
    # ✅ Validates available population
    # ✅ Creates general entity with SubAgentGroup component  
    # ✅ Transfers population from house to sub-agent
    # ✅ Sets mission parameters from natural language orders
    # ✅ Uses spatial positioning (finds deployment position by direction)
```

### **Settlement Action Interface** 🚧 TO BE IMPLEMENTED
```python
# Sub-agent tool (NEXT PRIORITY)
def settle_territory(ctx, target_direction: str = None) -> str:
    # TODO: Assess current position and surrounding tiles (needs TerrainObservation)
    # TODO: Check for territorial conflicts (can use spatial queries)
    # TODO: Calculate settlement success probability (can use SubAgentGroup capabilities)
    # TODO: Execute claiming if successful (needs TerritoryComponent integration)
    # TODO: Report results to parent house (needs communication system)
```

### **Spatial Query Interface** ✅ IMPLEMENTED  
```python
# Available in EntityManager for sub-agent AI decision making
entity_manager.get_positioned_entities_near(position, range_tiles, entity_types)
entity_manager.get_enemy_entities_near(position, range_tiles, friendly_house_id)
entity_manager.get_friendly_entities_near(position, range_tiles, friendly_house_id)
entity_manager.is_position_contested(position, check_range)
entity_manager.find_nearest_entity(position, entity_types, max_range)
```

### **Observation Data Structure**
```python
TerrainObservation = {
    'tiles_observed': {
        (q, r): {
            'terrain_type': str,
            'owner': str | None,
            'resources': Dict[str, float],
            'population_capacity': int,
            'threat_level': str,  # "none", "low", "medium", "high"
            'settlement_viability': float  # 0.0 to 1.0
        }
    },
    'conflicts_detected': [
        {
            'tile': (q, r),
            'owner': str,
            'conflict_type': str  # "territorial", "military"
        }
    ],
    'opportunities_found': [
        {
            'tile': (q, r),
            'opportunity_type': str,  # "resource", "strategic", "expansion"
            'value_assessment': float
        }
    ]
}
```

## 🧪 Testing Scenarios

### **Basic Delegation Workflow**
1. House Stark has 100 population (70 workers, 30 soldiers)
2. Lord deploys general with 15 soldiers, 10 workers
3. Verify house population reduced to 75 available
4. Verify general has SubAgentGroup with 25 assigned population
5. General moves and observes terrain automatically

### **Settlement Success**
1. Sub-agent group reaches target area with unclaimed tiles
2. Agent executes `settle_territory` action
3. Tiles are claimed for parent house
4. Population is established in new territory
5. House receives settlement report

### **Territorial Conflict Detection**
1. Sub-agent group encounters tiles owned by House Lannister
2. Conflict is detected and reported
3. Settlement action is blocked pending combat resolution
4. Intelligence report sent back to parent house

### **Resource Management**
1. Sub-agent group consumes supplies during movement
2. Group strength decreases if undersupplied
3. Settlement capability is reduced with low supplies
4. Group can forage or request resupply from parent

## 🔗 Integration Points

### **With Existing Systems**
- **Territory Expansion**: Delegate existing expansion orders to sub-agents
- **Population Management**: Track assigned population in household tools
- **Communication**: Sub-agents report via raven system
- **Movement**: Enhanced movement with group management
- **AI Decision Making**: Sub-agents make autonomous settlement decisions

### **Future Combat Integration**
- Sub-agent groups have combat strength based on assigned soldiers
- Territorial conflicts trigger combat resolution
- Group casualties affect assigned population
- Combat outcomes determine expansion success/failure

## 📊 Success Metrics

### **Functionality**
- [ ] Houses can successfully delegate population to sub-agents
- [ ] Sub-agents operate independently with assigned groups
- [ ] Terrain observation provides actionable intelligence
- [ ] Settlement actions successfully claim territory
- [ ] Population flows correctly between house and sub-agents

### **User Experience**
- [ ] Clear visualization of sub-agent groups on map
- [ ] Intuitive delegation interface for houses
- [ ] Informative progress reporting during missions
- [ ] Satisfying autonomous behavior from sub-agents

### **System Performance**
- [ ] Efficient handling of multiple concurrent sub-agents
- [ ] Smooth integration with existing expansion system
- [ ] Minimal performance impact from terrain observation
- [ ] Robust error handling for edge cases

---

This system will transform the expansion mechanics from centralized house-level orders into dynamic, tactical operations with autonomous sub-agents managing their assigned populations to achieve strategic objectives.