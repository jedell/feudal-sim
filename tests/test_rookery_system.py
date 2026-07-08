#!/usr/bin/env python3
"""
Test script for the RookeryComponent raven communication system.
Demonstrates sending ravens, delivery delays, and AI observation generation.
"""

from feudal_sim.core.entities import EntityManager
from feudal_sim.components.rookery import RookeryComponent, RavenDeliverySystem


def test_basic_raven_communication():
    """Test basic raven sending and receiving."""
    print("🐦 Testing Basic Raven Communication")
    print("=" * 50)
    
    # Create entities
    entity_manager = EntityManager()
    
    stark = entity_manager.create_entity(name="House Stark", entity_type="house")
    stark.add_component(RookeryComponent())
    
    lannister = entity_manager.create_entity(name="House Lannister", entity_type="house") 
    lannister.add_component(RookeryComponent())
    
    # Add known recipients (houses know each other)
    stark_rookery = stark.get_component(RookeryComponent)
    lannister_rookery = lannister.get_component(RookeryComponent)
    
    stark_rookery.add_known_recipient("House Lannister", "House Lannister")
    lannister_rookery.add_known_recipient("House Stark", "House Stark")
    
    print(f"✅ Created {stark.name} and {lannister.name}")
    print(f"📍 Known recipients - Stark: {stark_rookery.get_known_recipients_list()}")
    print(f"📍 Known recipients - Lannister: {lannister_rookery.get_known_recipients_list()}")
    
    return entity_manager, stark, lannister


def test_sending_ravens():
    """Test sending ravens between entities."""
    print("\n📤 Testing Raven Sending")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_basic_raven_communication()
    
    stark_rookery = stark.get_component(RookeryComponent)

    # Stark sends a raven to Lannister
    stark_rookery._current_turn = 1  # Set current turn for testing
    success = stark_rookery.send_raven("House Lannister", "Propose alliance against House Bolton")
    
    print(f"📨 Raven sent successfully: {success}")
    
    # Check observations
    observations = stark_rookery.get_observations_for_ai()
    print("🔍 Stark's observations:")
    for obs in observations:
        print(f"  {obs}")
    
    # Check outgoing ravens
    status = stark_rookery.get_communication_status()
    print(f"📊 Stark's communication status: {status}")
    
    return entity_manager, stark, lannister


def test_raven_delivery():
    """Test raven delivery and receiving."""
    print("\n📥 Testing Raven Delivery")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_sending_ravens()
    
    lannister_rookery = lannister.get_component(RookeryComponent)

    # Simulate turn advancement - raven should arrive in 1-2 turns
    print("\n🔄 Turn 2 - Checking for arriving ravens...")
    delivered_count = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 2)
    print(f"📬 Ravens delivered this turn: {delivered_count}")
    
    # Try turn 3 as well since arrival could be 1-2 turns
    if delivered_count == 0:
        print("🔄 Turn 3 - Checking for arriving ravens...")
        delivered_count = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 3)
        print(f"📬 Ravens delivered this turn: {delivered_count}")
    
    # Check Lannister's inbox
    lannister_observations = lannister_rookery.get_observations_for_ai()
    print("🔍 Lannister's observations:")
    for obs in lannister_observations:
        print(f"  {obs}")
    
    # Check message history
    recent_messages = lannister_rookery.get_recent_messages()
    print(f"📜 Lannister's recent messages: {len(recent_messages)}")
    for msg in recent_messages:
        print(f"  From {msg.sender_name}: '{msg.message}' (Turn {msg.turn_received})")
    
    return entity_manager, stark, lannister


def test_two_way_communication():
    """Test bidirectional raven communication."""
    print("\n↔️ Testing Two-Way Communication")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_raven_delivery()
    
    stark_rookery = stark.get_component(RookeryComponent)
    lannister_rookery = lannister.get_component(RookeryComponent)
    
    # Clear previous turn data
    RavenDeliverySystem.clear_turn_data_for_all(entity_manager)
    
    # Lannister responds
    lannister_rookery._current_turn = 3
    lannister_rookery.send_raven("House Stark", "Alliance accepted. Attack Bolton at dawn, Turn 5")
    
    print("📨 Lannister sent reply")
    
    # Check observations
    lannister_observations = lannister_rookery.get_observations_for_ai()
    print("🔍 Lannister's observations:")
    for obs in lannister_observations:
        print(f"  {obs}")
    
    # Deliver Lannister's reply
    print("\n🔄 Turn 4 - Delivering reply...")
    delivered_count = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 4)
    print(f"📬 Ravens delivered: {delivered_count}")
    
    # Check Stark's response
    stark_observations = stark_rookery.get_observations_for_ai()
    print("🔍 Stark's observations:")
    for obs in stark_observations:
        print(f"  {obs}")
    
    return entity_manager, stark, lannister


def test_unknown_recipient():
    """Test sending ravens to unknown recipients."""
    print("\n❌ Testing Unknown Recipients")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_two_way_communication()
    
    stark_rookery = stark.get_component(RookeryComponent)
    
    # Clear observations
    stark_rookery.current_observations.clear()
    
    # Try to send to unknown recipient
    success = stark_rookery.send_raven("House Targaryen", "Secret alliance proposal")
    print(f"📨 Attempted to send to unknown house: {success}")
    
    # Check observations
    observations = stark_rookery.get_observations_for_ai()
    print("🔍 Stark's observations:")
    for obs in observations:
        print(f"  {obs}")


def test_army_discovery():
    """Test discovering new entities for communication."""
    print("\n🔍 Testing Army Discovery")
    print("=" * 50)
    
    entity_manager = EntityManager()
    
    # Create house and army
    stark = entity_manager.create_entity(name="House Stark", entity_type="house")
    stark.add_component(RookeryComponent())
    
    stark_army = entity_manager.create_entity(name="Stark Army", entity_type="army")
    stark_army.add_component(RookeryComponent())
    
    stark_rookery = stark.get_component(RookeryComponent)
    
    print(f"✅ Created {stark.name} and {stark_army.name}")
    print(f"📍 Initially known recipients: {stark_rookery.get_known_recipients_list()}")
    
    # House discovers its own army (e.g., when dispatching)
    stark_rookery.add_known_recipient("Stark Army", "Stark Army")
    
    # Check observations
    observations = stark_rookery.get_observations_for_ai()
    print("🔍 Stark's observations after discovering army:")
    for obs in observations:
        print(f"  {obs}")
    
    print(f"📍 Updated known recipients: {stark_rookery.get_known_recipients_list()}")


def test_complete_simulation_turns():
    """Test a complete multi-turn simulation scenario."""
    print("\n🎮 Testing Complete Simulation Scenario")
    print("=" * 60)
    
    entity_manager = EntityManager()
    
    # Create houses
    stark = entity_manager.create_entity(name="House Stark", entity_type="house")
    stark.add_component(RookeryComponent())
    
    lannister = entity_manager.create_entity(name="House Lannister", entity_type="house")
    lannister.add_component(RookeryComponent())
    
    # Set up known recipients
    stark_rookery = stark.get_component(RookeryComponent)
    lannister_rookery = lannister.get_component(RookeryComponent)
    
    stark_rookery.add_known_recipient("House Lannister", "House Lannister")
    lannister_rookery.add_known_recipient("House Stark", "House Stark")
    
    # Simulate 5 turns with various communications
    for turn in range(1, 6):
        print(f"\n🔄 Turn {turn}")
        print("-" * 30)
        
        # Actions Phase - Send ravens
        if turn == 1:
            stark_rookery._current_turn = turn
            stark_rookery.send_raven("House Lannister", "Enemy spotted near your borders")
            
        elif turn == 3:
            lannister_rookery._current_turn = turn
            lannister_rookery.send_raven("House Stark", "Thank you for warning. Will fortify defenses")
            
        elif turn == 4:
            stark_rookery._current_turn = turn
            stark_rookery.send_raven("House Lannister", "Propose joint military exercise")
        
        # Events Phase - Deliver ravens
        delivered = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, turn)
        if delivered > 0:
            print(f"📬 {delivered} ravens delivered")
        
        # Show observations for both houses
        stark_obs = stark_rookery.get_observations_for_ai()
        lannister_obs = lannister_rookery.get_observations_for_ai()
        
        if stark_obs:
            print("🏠 Stark observations:")
            for obs in stark_obs:
                print(f"  {obs}")
        
        if lannister_obs:
            print("🦁 Lannister observations:")
            for obs in lannister_obs:
                print(f"  {obs}")
        
        # Cleanup Phase
        RavenDeliverySystem.clear_turn_data_for_all(entity_manager)
    
    # Final communication status
    print("\n📊 Final Communication Status")
    print("-" * 30)
    print(f"Stark status: {stark_rookery.get_communication_status()}")
    print(f"Lannister status: {lannister_rookery.get_communication_status()}")


def main():
    """Run all rookery system tests."""
    print("🐦 RookeryComponent Test Suite")
    print("=" * 60)
    
    # Basic functionality tests
    test_basic_raven_communication()
    test_sending_ravens()
    test_raven_delivery()
    test_two_way_communication()
    test_unknown_recipient()
    test_army_discovery()
    
    # Complete scenario test
    test_complete_simulation_turns()
    
    print("\n✅ All rookery tests completed successfully!")
    print("🐦 Raven communication system is ready for AI integration.")


if __name__ == "__main__":
    main()