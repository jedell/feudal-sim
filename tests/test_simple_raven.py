#!/usr/bin/env python3
"""
Simple focused test for raven delivery to verify the system works.
"""

from feudal_sim.core.entities import EntityManager
from feudal_sim.components.rookery import RookeryComponent, RavenDeliverySystem


def test_simple_raven_delivery():
    """Test basic raven sending and delivery."""
    print("🐦 Simple Raven Delivery Test")
    print("=" * 40)
    
    # Create entity manager and entities
    entity_manager = EntityManager()
    
    stark = entity_manager.create_entity(entity_id="House Stark", name="House Stark")
    stark.add_component(RookeryComponent())
    
    lannister = entity_manager.create_entity(entity_id="House Lannister", name="House Lannister")
    lannister.add_component(RookeryComponent())
    
    # Get components
    stark_rookery = stark.get_component(RookeryComponent)
    lannister_rookery = lannister.get_component(RookeryComponent)
    
    # Add known recipients
    stark_rookery.add_known_recipient("House Lannister")
    lannister_rookery.add_known_recipient("House Stark")
    
    print("✅ Created houses with rookeries")
    
    # Turn 1: Send raven
    print("\n🔄 Turn 1: Sending raven")
    stark_rookery._current_turn = 1
    success = stark_rookery.send_raven("House Lannister", "Hello from Stark!")
    print(f"📨 Raven sent: {success}")
    
    # Check outgoing ravens
    print(f"📤 Outgoing ravens: {len(stark_rookery.outgoing_ravens)}")
    if stark_rookery.outgoing_ravens:
        raven = stark_rookery.outgoing_ravens[0]
        print(f"📜 Raven details: arrives turn {raven.arrival_turn}, delivered: {raven.delivered}")
    
    # Turn 2: Try delivery  
    print("\n🔄 Turn 2: Attempting delivery")
    
    # Debug: Check entity manager has both entities
    all_entities = entity_manager.get_all_entities()
    print(f"🔍 Entity manager has {len(all_entities)} entities:")
    for entity in all_entities:
        print(f"  ID: {entity.id}, Name: {entity.name}")
    
    # Check if recipient exists
    recipient = entity_manager.get_entity("House Lannister")
    print(f"🔍 Can find recipient 'House Lannister': {recipient is not None}")
    if recipient:
        print(f"  Has rookery: {recipient.has_component(RookeryComponent)}")
    
    delivered = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 2)
    print(f"📬 Ravens delivered: {delivered}")
    
    # Check Lannister's inbox
    lannister_obs = lannister_rookery.get_observations_for_ai()
    print("🔍 Lannister observations:")
    for obs in lannister_obs:
        print(f"  {obs}")
    
    # Turn 3: Try delivery again
    print("\n🔄 Turn 3: Attempting delivery")
    
    # Debug: Check what ravens are ready for delivery
    stark_rookery = stark.get_component(RookeryComponent)
    for i, raven in enumerate(stark_rookery.outgoing_ravens):
        print(f"  Raven {i}: arrives turn {raven.arrival_turn}, current turn 3, ready: {raven.arrival_turn <= 3}")
    
    delivered = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 3)
    print(f"📬 Ravens delivered: {delivered}")
    
    # Check again
    lannister_obs = lannister_rookery.get_observations_for_ai()
    print("🔍 Lannister observations:")
    for obs in lannister_obs:
        print(f"  {obs}")
    
    # Check final status
    print("\n📊 Final status:")
    print(f"  Stark outgoing ravens: {len([r for r in stark_rookery.outgoing_ravens if not r.delivered])}")
    print(f"  Lannister received messages: {len(lannister_rookery.message_history)}")


if __name__ == "__main__":
    test_simple_raven_delivery()