# Component-Based Entity System Vision

## 🎯 **Core Vision**

The feudal simulation will feature **autonomous AI entities** that can operate independently while coordinating through communication. A House serves as the central command with an AI Lord/Lady, but can dispatch specialized entities (armies, scouts, caravans, laborers) that make their own decisions each turn while maintaining strategic coordination.

## 🏛️ **Entity Hierarchy**

### **Primary Entity: House**
- **Role**: Central command and resource base
- **AI Personality**: Strategic leadership (honorable, cunning, diplomatic, etc.)
- **Capabilities**: 
  - Controls territory and population
  - Manages resources and production
  - Dispatches specialized entities for missions
  - Receives intelligence and makes strategic decisions

### **Dispatched Entities**

#### **Army**
- **Role**: Military operations and territorial control
- **AI Personality**: Military leadership (aggressive, defensive, tactical)
- **Capabilities**:
  - Independent movement and positioning
  - Combat decision making
  - Supply management
  - Reporting back to House

#### **Scout**
- **Role**: Information gathering and reconnaissance  
- **AI Personality**: Cautious and observant
- **Capabilities**:
  - Fast movement across terrain
  - Intelligence gathering on enemy positions
  - Risk assessment and evasion
  - Real-time reporting to command

#### **Caravan**
- **Role**: Trade and resource transport
- **AI Personality**: Merchant-focused and profit-driven
- **Capabilities**:
  - Route planning and optimization
  - Trade negotiation with other entities
  - Resource transportation
  - Market intelligence gathering

#### **Laborers/Work Crews**
- **Role**: Construction and resource extraction
- **AI Personality**: Task-focused and efficient
- **Capabilities**:
  - Building fortifications or infrastructure
  - Establishing new resource extraction sites
  - Terrain modification
  - Progress reporting

## 🔧 **Component Architecture**

### **Core Components**

#### **AIComponent**
```python
class AIComponent(Component):
    personality: str        # "honorable", "cunning", "merchant", "military"
    decision_tree: dict     # Personality-specific decision patterns
    current_orders: list    # Active missions/objectives
    home_entity: str        # Which entity this reports to (if any)
    
    def make_decisions(world_state) -> list[Action]
    def execute_actions(action_list)
    def receive_message(message)
    def send_message(recipient, content)
```

#### **CommunicationComponent**
```python
class CommunicationComponent(Component):
    message_queue: list     # Incoming messages
    communication_range: int # How far messages can be sent
    contacts: list          # Known entities for communication
    
    def send_message(recipient, message_type, content)
    def receive_message(sender, message)
    def broadcast_to_allies(message)
```

#### **MovementComponent**
```python
class MovementComponent(Component):
    current_position: tuple  # (x, y) coordinates
    movement_speed: int      # Tiles per turn
    movement_type: str       # "ground", "water", "flying"
    current_path: list       # Planned movement route
    
    def plan_route(destination, avoid_enemies=True)
    def move_towards_target()
    def can_reach(destination) -> bool
```

### **Specialized Components**

#### **TerritoryComponent** (Houses)
```python
class TerritoryComponent(Component):
    controlled_tiles: set
    border_tiles: set
    territorial_claims: set
    
    def expand_territory(direction)
    def defend_borders()
    def calculate_control_strength()
```

#### **CombatComponent** (Armies)
```python
class CombatComponent(Component):
    unit_composition: dict   # Different unit types and counts
    combat_strength: int
    morale: float
    battle_experience: int
    
    def engage_enemy(target)
    def assess_battle_odds(enemy)
    def retreat_if_necessary()
```

#### **TradeComponent** (Caravans)
```python
class TradeComponent(Component):
    trade_goods: dict       # What goods are being carried
    trade_routes: list      # Known profitable routes
    market_knowledge: dict  # Price information
    
    def negotiate_trade(other_entity)
    def find_profitable_routes()
    def assess_trade_opportunity()
```

#### **ReconnaissanceComponent** (Scouts)
```python
class ReconnaissanceComponent(Component):
    scouting_range: int
    stealth_ability: float
    discovered_info: dict
    
    def scout_area(target_location)
    def observe_enemy_movements()
    def assess_threat_levels()
```

## 🔄 **Turn-Based Execution Flow**

### **Actions Phase: Independent Decision Making**
```python
def execute_actions_phase():
    all_entities = entity_manager.get_all_entities()
    
    # Each entity makes decisions independently
    for entity in all_entities:
        ai_component = entity.get_component(AIComponent)
        if ai_component:
            # 1. Assess current situation
            world_state = ai_component.gather_intelligence()
            
            # 2. Make decisions based on personality and orders
            decisions = ai_component.make_decisions(world_state)
            
            # 3. Execute actions
            for decision in decisions:
                ai_component.execute_action(decision)
            
            # 4. Communicate results if necessary
            ai_component.send_status_updates()
```

### **Communication Flow Example**
```
Turn 1:
├── House Stark AI: "Need intelligence on enemy positions"
├── Dispatches Scout to explore eastern border
├── Scout AI: Plans reconnaissance route
└── Scout begins movement

Turn 2:  
├── Scout discovers enemy army
├── Scout AI: Sends urgent message to House Stark
├── House Stark AI: Receives intelligence report
├── House Stark AI: Decides to dispatch army
└── Creates Army entity with combat mission

Turn 3:
├── Army AI: Receives orders to engage
├── Army AI: Plans approach to enemy position
├── Scout AI: Continues surveillance  
├── House Stark AI: Monitors both units
└── Caravan AI: Avoids conflict area in trade route
```

## 🎮 **Entity Dispatch System**

### **House Dispatch Interface**
```python
class AIComponent(Component):
    def dispatch_army(self, mission_type, target_location, force_size):
        army = entity_manager.create_entity(f"{self.entity.name}_army")
        army.add_component(AIComponent(personality="military", orders=mission_type))
        army.add_component(MovementComponent())
        army.add_component(CombatComponent(force_size=force_size))
        army.add_component(CommunicationComponent())
        
        # Army knows its home and mission
        army_ai = army.get_component(AIComponent)
        army_ai.home_entity = self.entity.id
        army_ai.mission_target = target_location
        
        return army
    
    def dispatch_scout(self, scouting_area):
        scout = entity_manager.create_entity(f"{self.entity.name}_scout")
        scout.add_component(AIComponent(personality="cautious"))
        scout.add_component(MovementComponent(speed=2))  # Faster than army
        scout.add_component(ReconnaissanceComponent())
        scout.add_component(CommunicationComponent())
        
        return scout
    
    def dispatch_caravan(self, destination, trade_goods):
        caravan = entity_manager.create_entity(f"{self.entity.name}_caravan")
        caravan.add_component(AIComponent(personality="merchant"))
        caravan.add_component(MovementComponent())
        caravan.add_component(TradeComponent())
        caravan.add_component(ResourceComponent(starting_resources=trade_goods))
        caravan.add_component(CommunicationComponent())
        
        return caravan
```

## 📡 **Inter-Entity Communication Examples**

### **Intelligence Sharing**
```python
# Scout spots enemy
scout_ai.send_message("House Stark", "INTELLIGENCE_REPORT", {
    "enemy_position": (45, 30),
    "enemy_strength": "large army",
    "threat_level": "high",
    "recommended_action": "dispatch_army"
})

# House receives and acts
house_ai.process_message(message)
if message.content["threat_level"] == "high":
    army = house_ai.dispatch_army("defend", message.content["enemy_position"])
```

### **Coordination Between Units**
```python
# Army requests scout support
army_ai.send_message("Stark_scout", "REQUEST_SUPPORT", {
    "mission": "flank_reconnaissance", 
    "target_area": (50, 35),
    "timing": "before_attack"
})

# Scout responds and coordinates
scout_ai.receive_message(message)
scout_ai.modify_orders(message.content["mission"])
```

### **Resource Coordination**
```python
# Caravan reports trade opportunities
caravan_ai.send_message("House Stark", "TRADE_REPORT", {
    "available_goods": {"iron": 100, "grain": 200},
    "asking_price": {"gold": 50},
    "location": "Free City of Braavos",
    "expires_in_turns": 3
})
```

## 🌟 **Key Benefits Achieved**

### **1. Emergent Strategic Behavior**
- Multiple AI entities creating complex, coordinated strategies
- Unexpected tactical combinations emerging from simple rules
- Dynamic adaptation to changing battlefield conditions

### **2. Scalable Complexity**
- Easy to add new entity types (siege engines, diplomats, spies)
- Component reuse across different entity types
- Modular AI personalities and behaviors

### **3. Rich Simulation Depth**
- Simultaneous multiple operations (war, trade, diplomacy, construction)
- Information warfare and intelligence gathering
- Realistic command and control challenges

### **4. Player/AI Interaction**
- Clear command structure (House → Dispatched Units)
- Observable decision-making process
- Strategic depth through entity coordination

## 🚀 **Implementation Roadmap**

### **Phase 1: Foundation** (Week 1)
- Basic Entity and Component system
- AIComponent with simple decision making
- CommunicationComponent for message passing

### **Phase 2: Movement and Basic Dispatch** (Week 2)  
- MovementComponent for mobile entities
- Basic dispatch system (House creates Scout)
- Simple communication between House and Scout

### **Phase 3: Military Operations** (Week 3)
- CombatComponent for armies
- Army dispatch and coordination
- Scout-Army communication

### **Phase 4: Economic Operations** (Week 4)
- TradeComponent for caravans
- Resource transportation
- Economic intelligence gathering

### **Phase 5: Advanced Coordination** (Week 5+)
- Complex multi-entity missions
- Advanced AI personalities
- Inter-house entity interactions

This component-based architecture provides the foundation for rich, autonomous AI behavior while maintaining clear command structures and enabling emergent strategic gameplay.