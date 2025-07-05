#!/usr/bin/env python3
"""
Simple test script to validate the Entity-Component system works correctly.
This demonstrates the basic usage patterns before integrating with the main simulation.
"""

from feudal_sim.core.entities import Entity, Component, EntityManager


# Example components for testing
class TestResourceComponent(Component):
    """Test component that manages resources."""
    
    def __init__(self, initial_food=100, initial_gold=50):
        super().__init__()
        self.food = initial_food
        self.gold = initial_gold
        self.updates_count = 0
    
    def update(self, dt: float, event_bus=None):
        # Simulate resource generation each turn
        self.food += 10 * dt
        self.gold += 5 * dt
        self.updates_count += 1
        print(f"  Resources updated: {self.food:.0f} food, {self.gold:.0f} gold (update #{self.updates_count})")


class TestAIComponent(Component):
    """Test component that simulates AI decision making."""
    
    def __init__(self, personality="neutral"):
        super().__init__()
        self.personality = personality
        self.decisions_made = 0
    
    def update(self, dt: float, event_bus=None):
        self.decisions_made += 1
        if self.decisions_made % 3 == 0:
            print(f"  AI ({self.personality}) made strategic decision #{self.decisions_made}")
    
    def make_decision(self, situation):
        return f"{self.personality} response to {situation}"


class TestMovementComponent(Component):
    """Test component for movement capabilities."""
    
    def __init__(self, x=0, y=0, speed=1):
        super().__init__()
        self.x = x
        self.y = y
        self.speed = speed
        self.target_x = None
        self.target_y = None
    
    def update(self, dt: float, event_bus=None):
        if self.target_x is not None and self.target_y is not None:
            # Move towards target
            if self.x < self.target_x:
                self.x = min(self.x + self.speed * dt, self.target_x)
            elif self.x > self.target_x:
                self.x = max(self.x - self.speed * dt, self.target_x)
            
            if self.y < self.target_y:
                self.y = min(self.y + self.speed * dt, self.target_y)
            elif self.y > self.target_y:
                self.y = max(self.y - self.speed * dt, self.target_y)
            
            if abs(self.x - self.target_x) < 0.1 and abs(self.y - self.target_y) < 0.1:
                print(f"  Reached destination ({self.target_x}, {self.target_y})")
                self.target_x = None
                self.target_y = None
    
    def move_to(self, x, y):
        self.target_x = x
        self.target_y = y
        print(f"  Moving from ({self.x}, {self.y}) to ({x}, {y})")


def test_basic_entity_component_system():
    """Test basic entity and component functionality."""
    print("🧪 Testing Basic Entity-Component System")
    print("=" * 50)
    
    # Create entity manager
    entity_manager = EntityManager()
    
    # Test 1: Create a House entity
    print("\n1️⃣ Creating House entity")
    house = entity_manager.create_entity(name="House Stark", entity_type="house")
    house.add_component(TestResourceComponent(initial_food=200, initial_gold=100))
    house.add_component(TestAIComponent(personality="honorable"))
    
    print(f"Created: {house}")
    
    # Test 2: Create an Army entity
    print("\n2️⃣ Creating Army entity")
    army = entity_manager.create_entity(name="Stark Army", entity_type="army")
    army.add_component(TestAIComponent(personality="military"))
    army.add_component(TestMovementComponent(x=0, y=0, speed=2))
    
    print(f"Created: {army}")
    
    # Test 3: Create a Scout entity
    print("\n3️⃣ Creating Scout entity")
    scout = entity_manager.create_entity(name="Stark Scout", entity_type="scout")
    scout.add_component(TestAIComponent(personality="cautious"))
    scout.add_component(TestMovementComponent(x=5, y=5, speed=3))
    
    print(f"Created: {scout}")
    
    # Test 4: Component interaction
    print("\n4️⃣ Testing Component Interaction")
    house_ai = house.get_component(TestAIComponent)
    house_resources = house.get_component(TestResourceComponent)
    
    print(f"House AI personality: {house_ai.personality}")
    print(f"House initial resources: {house_resources.food} food, {house_resources.gold} gold")
    
    # Test 5: Entity queries
    print("\n5️⃣ Testing Entity Queries")
    all_entities = entity_manager.get_all_entities()
    print(f"Total entities: {len(all_entities)}")
    
    houses = entity_manager.get_entities_by_type("house")
    print(f"Houses: {[e.name for e in houses]}")
    
    ai_entities = entity_manager.get_entities_with_component(TestAIComponent)
    print(f"Entities with AI: {[e.name for e in ai_entities]}")
    
    mobile_entities = entity_manager.get_entities_with_component(TestMovementComponent)
    print(f"Mobile entities: {[e.name for e in mobile_entities]}")
    
    return entity_manager, house, army, scout


def test_simulation_turns(entity_manager, house, army, scout):
    """Test running multiple simulation turns."""
    print("\n🎮 Testing Simulation Turns")
    print("=" * 50)
    
    # Set movement targets
    army_movement = army.get_component(TestMovementComponent)
    army_movement.move_to(10, 5)
    
    scout_movement = scout.get_component(TestMovementComponent)
    scout_movement.move_to(15, 10)
    
    # Run 5 simulation turns
    for turn in range(1, 6):
        print(f"\n🔄 Turn {turn}")
        print("-" * 20)
        
        # Update all entities (dt=1.0 for turn-based)
        entity_manager.update_all_entities(dt=1.0)
        
        # Show positions of mobile entities
        army_pos = army.get_component(TestMovementComponent)
        scout_pos = scout.get_component(TestMovementComponent)
        print(f"  Army position: ({army_pos.x:.1f}, {army_pos.y:.1f})")
        print(f"  Scout position: ({scout_pos.x:.1f}, {scout_pos.y:.1f})")


def test_component_removal():
    """Test removing and adding components dynamically."""
    print("\n🔧 Testing Dynamic Component Management")
    print("=" * 50)
    
    entity_manager = EntityManager()
    test_entity = entity_manager.create_entity(name="Test Entity")
    
    # Add components
    test_entity.add_component(TestAIComponent(personality="test"))
    test_entity.add_component(TestMovementComponent())
    
    print(f"Initial: {test_entity}")
    
    # Remove AI component
    removed_ai = test_entity.remove_component(TestAIComponent)
    print(f"Removed AI component: {removed_ai}")
    print(f"After removal: {test_entity}")
    
    # Try to get removed component
    ai_component = test_entity.get_component(TestAIComponent)
    print(f"AI component after removal: {ai_component}")
    
    # Add it back
    test_entity.add_component(TestAIComponent(personality="restored"))
    print(f"After re-adding AI: {test_entity}")


def main():
    """Run all entity system tests."""
    print("🚀 Entity-Component System Test Suite")
    print("=" * 60)
    
    # Basic functionality test
    entity_manager, house, army, scout = test_basic_entity_component_system()
    
    # Simulation turns test
    test_simulation_turns(entity_manager, house, army, scout)
    
    # Dynamic component management test
    test_component_removal()
    
    # Final stats
    print("\n📊 Final Entity Manager Stats")
    print("=" * 50)
    stats = entity_manager.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n✅ All tests completed successfully!")
    print("Entity-Component system is ready for integration.")


if __name__ == "__main__":
    main()