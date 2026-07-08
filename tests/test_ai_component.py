#!/usr/bin/env python3
"""
Test script for the AIComponent system.
Tests basic AI agent functionality, observation processing, and message history management.
"""

import os
from feudal_sim.core.entities import EntityManager
from feudal_sim.components.ai import AIComponent


def test_ai_component_initialization():
    """Test basic AI component initialization."""
    print("🤖 Testing AI Component Initialization")
    print("=" * 50)
    
    # Create entity with AI component
    entity_manager = EntityManager()
    stark = entity_manager.create_entity(name="House Stark", entity_type="house")
    
    # Create AI component with personality
    ai_component = AIComponent(
        name="Lord Eddard Stark",
        instructions="You are Lord Eddard Stark, honorable ruler of Winterfell. You value honor above all else and protect your family and the North."
    )
    
    stark.add_component(ai_component)
    
    print(f"✅ Created entity: {stark.name}")
    print(f"🧠 AI Agent: {ai_component.agent_name}")
    print(f"📊 AI Status: {ai_component.get_ai_status()}")
    
    # Check initial message history
    messages = ai_component.get_recent_messages()
    print(f"📜 Initial messages: {len(messages)}")
    if messages:
        print(f"   System message: {messages[0]['content'][:100]}...")
    
    return entity_manager, stark, ai_component


def test_observation_management():
    """Test adding observations and message history."""
    print("\n📋 Testing Observation Management")
    print("=" * 50)
    
    entity_manager, stark, ai_component = test_ai_component_initialization()
    
    # Update context for current turn
    ai_component.update_context(
        current_turn=1,
        current_phase="production",
        current_season="spring",
        current_year=1
    )
    
    # Add some observations
    ai_component.add_observation("Gathered 50 food from your territories", "Production")
    ai_component.add_observation("Your population has grown by 5 people", "Production")
    ai_component.add_observation("A raven arrived from House Lannister with a trade proposal", "Events")
    
    print("📨 Added 3 observations")
    print(f"📊 Pending observations: {len(ai_component.pending_observations)}")
    
    # Check status
    status = ai_component.get_ai_status()
    print(f"📈 AI Status: {status}")
    
    return entity_manager, stark, ai_component


def test_ai_decision_making():
    """Test AI decision making process."""
    print("\n🎯 Testing AI Decision Making")
    print("=" * 50)
    
    entity_manager, stark, ai_component = test_observation_management()
    
    # Check if OpenAI API key is available
    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
    print(f"🔑 OpenAI API Key available: {has_api_key}")
    
    if not has_api_key:
        print("⚠️  Skipping actual AI calls - no API key")
        # Test the message preparation instead
        ai_component._process_pending_observations()
        turn_message = ai_component._generate_turn_context_message()
        
        print("📝 Turn context message:")
        print(f"   {turn_message}")
        
        print("📜 Message history after processing observations:")
        for i, msg in enumerate(ai_component.messages):
            role = msg["role"]
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            print(f"   {i+1}. [{role}] {content}")
        
        return entity_manager, stark, ai_component
    
    # Make AI decision
    print("🧠 Calling AI agent for decision...")
    try:
        decision = ai_component.make_decisions()
        print(f"🎯 AI Decision: {decision}")
        
        # Check message history after decision
        messages = ai_component.get_recent_messages()
        print(f"📜 Message history length: {len(messages)}")
        
        # Show recent messages
        summary = ai_component.get_message_summary()
        print("📋 Message Summary:")
        for msg in summary[-5:]:  # Show last 5 messages
            print(f"   {msg}")
            
    except Exception as e:
        print(f"❌ Error during AI decision: {e}")
    
    return entity_manager, stark, ai_component


def test_multiple_turns():
    """Test AI behavior across multiple turns."""
    print("\n🔄 Testing Multiple Turn Simulation")
    print("=" * 50)
    
    entity_manager, stark, ai_component = test_ai_decision_making()
    
    # Simulate a few more turns
    turns_data = [
        {
            "turn": 2,
            "observations": [
                "Your scouts report enemy movement to the south",
                "Trade with House Tully generated 30 gold"
            ]
        },
        {
            "turn": 3, 
            "observations": [
                "Winter is approaching - food consumption will increase",
                "A marriage proposal arrived from House Arryn"
            ]
        }
    ]
    
    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
    
    for turn_data in turns_data:
        print(f"\n🔄 Turn {turn_data['turn']}")
        
        # Update context
        ai_component.update_context(
            current_turn=turn_data['turn'],
            current_phase="actions",
            current_season="spring" if turn_data['turn'] % 4 else "winter",
            current_year=1
        )
        
        # Add observations
        for obs in turn_data['observations']:
            ai_component.add_observation(obs)
        
        if has_api_key:
            try:
                decision = ai_component.make_decisions()
                print(f"   Decision: {decision[:100]}...")
            except Exception as e:
                print(f"   Error: {e}")
        else:
            print(f"   Observations added: {len(turn_data['observations'])}")
            print(f"   Total messages: {len(ai_component.messages)}")
    
    # Final status
    print(f"\n📊 Final AI Status: {ai_component.get_ai_status()}")


def test_message_format():
    """Test that message format is correct for OpenAI."""
    print("\n📝 Testing Message Format")
    print("=" * 50)
    
    # Create a simple AI component
    ai_component = AIComponent(
        name="Test Agent",
        instructions="You are a test agent."
    )
    
    # Add context and observations
    ai_component.update_context(1, "actions", "spring", 1)
    ai_component.add_observation("Test observation 1")
    ai_component.add_observation("Test observation 2")
    
    # Process observations into messages
    ai_component._process_pending_observations()
    turn_message = ai_component._generate_turn_context_message()
    ai_component.messages.append({"role": "user", "content": turn_message})
    
    # Verify message format
    print("🔍 Message format validation:")
    for i, msg in enumerate(ai_component.messages):
        print(f"   Message {i+1}:")
        print(f"     Role: {msg['role']}")
        print(f"     Content: {msg['content'][:80]}{'...' if len(msg['content']) > 80 else ''}")
        
        # Validate required fields
        assert 'role' in msg, f"Message {i+1} missing 'role'"
        assert 'content' in msg, f"Message {i+1} missing 'content'" 
        assert msg['role'] in ['system', 'user', 'assistant'], f"Invalid role: {msg['role']}"
    
    print("✅ All messages have correct format")


def main():
    """Run all AI component tests."""
    print("🤖 AIComponent Test Suite")
    print("=" * 60)
    
    # Run tests
    test_ai_component_initialization()
    test_observation_management()
    test_ai_decision_making()
    test_multiple_turns()
    test_message_format()
    
    print("\n✅ All AI component tests completed!")
    
    # Check for API key and provide guidance
    if not os.getenv('OPENAI_API_KEY'):
        print("\n💡 To test actual AI decisions, set your OpenAI API key:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
    else:
        print("\n🎉 AI component ready for integration with full API functionality!")


if __name__ == "__main__":
    main()