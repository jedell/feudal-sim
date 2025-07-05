#!/usr/bin/env python3
"""
Test script for the send_raven tool functionality.
Tests the AI agent's ability to send ravens using the tool system.
"""

import os
from feudal_sim.core.entities import EntityManager
from feudal_sim.houses.house import House
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.rookery import RookeryComponent, RavenDeliverySystem
from feudal_sim.map.types import Color


def test_send_raven_tool_creation():
    """Test that send_raven tools are created correctly."""
    print("🔧 Testing Send Raven Tool Creation")
    print("=" * 50)
    
    # Create entity manager and houses
    entity_manager = EntityManager()
    
    stark = House("Stark", color=Color(0, 0, 255, 120))
    lannister = House("Lannister", color=Color(255, 0, 0, 120))
    
    # Register with entity manager
    entity_manager._entities[stark.id] = stark
    entity_manager._entities[lannister.id] = lannister
    
    # Set up communications (houses know each other)
    stark_rookery = stark.get_component(RookeryComponent)
    lannister_rookery = lannister.get_component(RookeryComponent)
    
    stark_rookery.add_known_recipient("Lannister", "House Lannister")
    lannister_rookery.add_known_recipient("Stark", "House Stark")
    
    print(f"✅ Created houses: {stark.name} and {lannister.name}")
    print(f"📍 Stark known recipients: {stark_rookery.get_known_recipients_list()}")
    print(f"📍 Lannister known recipients: {lannister_rookery.get_known_recipients_list()}")
    
    # Check AI components have tools
    stark_ai = stark.get_component(AIComponent)
    lannister_ai = lannister.get_component(AIComponent)
    
    print(f"🤖 Stark AI agent: {stark_ai.agent_name}")
    print(f"🤖 Lannister AI agent: {lannister_ai.agent_name}")
    print(f"🔧 Stark AI enabled: {stark_ai.is_enabled}")
    print(f"🔧 Lannister AI enabled: {lannister_ai.is_enabled}")
    
    if stark_ai.agent:
        tools = stark_ai.agent.tools if hasattr(stark_ai.agent, 'tools') else []
        print(f"🔧 Stark AI tools: {len(tools)}")
    
    return entity_manager, stark, lannister


def test_ai_decision_with_ravens():
    """Test AI making decisions that include sending ravens."""
    print("\n🧠 Testing AI Decisions with Raven Communication")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_send_raven_tool_creation()
    
    # Give houses some context
    stark_ai = stark.get_component(AIComponent)
    lannister_ai = lannister.get_component(AIComponent)
    
    # Update context for both houses
    for house in [stark, lannister]:
        ai = house.get_component(AIComponent)
        ai.update_context(
            current_turn=1,
            current_phase="actions",
            current_season="spring",
            current_year=1,
            game_state={
                'population': house.population,
                'resources': house.resources,
                'territory_size': len(house.territory)
            }
        )
    
    # Add some observations to make decisions more interesting
    stark_ai.add_observation("Your scouts report unusual activity near your borders", "Production")
    stark_ai.add_observation("Your population is growing and resources are stable", "Production")
    
    lannister_ai.add_observation("Gold production is higher than expected this turn", "Production")
    lannister_ai.add_observation("Trade routes are secure and profitable", "Production")
    
    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
    print(f"🔑 OpenAI API Key available: {has_api_key}")
    
    if has_api_key:
        # Test Stark making a decision (might include sending a raven)
        print(f"\n🎯 {stark.name} AI making decision...")
        try:
            decision = stark_ai.make_decisions()
            print(f"📜 {stark.name} Decision:")
            print(f"   {decision}")
            
            # Check if any ravens were sent
            stark_rookery = stark.get_component(RookeryComponent)
            outgoing_ravens = len([r for r in stark_rookery.outgoing_ravens if not r.delivered])
            print(f"📤 Ravens sent by {stark.name}: {outgoing_ravens}")
            
        except Exception as e:
            print(f"❌ Error in {stark.name} AI decision: {e}")
        
        # Test Lannister making a decision
        print(f"\n🎯 {lannister.name} AI making decision...")
        try:
            decision = lannister_ai.make_decisions()
            print(f"📜 {lannister.name} Decision:")
            print(f"   {decision}")
            
            # Check if any ravens were sent
            lannister_rookery = lannister.get_component(RookeryComponent)
            outgoing_ravens = len([r for r in lannister_rookery.outgoing_ravens if not r.delivered])
            print(f"📤 Ravens sent by {lannister.name}: {outgoing_ravens}")
            
        except Exception as e:
            print(f"❌ Error in {lannister.name} AI decision: {e}")
        
        # Test raven delivery
        print(f"\n📬 Testing Raven Delivery (Turn 2)...")
        delivered = RavenDeliverySystem.deliver_ravens_for_turn(entity_manager, 2)
        print(f"📨 Ravens delivered: {delivered}")
        
        # Check for received ravens
        for house in [stark, lannister]:
            rookery = house.get_component(RookeryComponent)
            observations = rookery.get_observations_for_ai()
            if observations:
                print(f"📜 {house.name} raven observations:")
                for obs in observations:
                    print(f"   {obs}")
        
    else:
        print("⚠️  Skipping AI decisions - no API key available")
        print("   Set OPENAI_API_KEY to test actual AI raven communication")
    
    return entity_manager, stark, lannister


def test_raven_tool_schema():
    """Test that the raven tool has proper schema with enum recipients."""
    print("\n📋 Testing Raven Tool Schema")
    print("=" * 50)
    
    entity_manager, stark, lannister = test_send_raven_tool_creation()
    
    # Check the tools created for Stark
    stark_ai = stark.get_component(AIComponent)
    
    if stark_ai.agent and hasattr(stark_ai.agent, 'tools'):
        print(f"🔧 Stark has {len(stark_ai.agent.tools)} tools")
        
        for i, tool in enumerate(stark_ai.agent.tools):
            print(f"   Tool {i+1}: {tool.__name__ if hasattr(tool, '__name__') else 'Unknown'}")
            
            # Try to inspect tool signature if possible
            if hasattr(tool, '__annotations__'):
                print(f"     Annotations: {tool.__annotations__}")
    else:
        print("⚠️  No tools found or agent not initialized")


def main():
    """Run all send_raven tool tests."""
    print("🐦 Send Raven Tool Test Suite")
    print("=" * 60)
    
    test_send_raven_tool_creation()
    test_ai_decision_with_ravens()
    test_raven_tool_schema()
    
    print("\n✅ Send raven tool tests completed!")
    
    # Check for API key and provide guidance
    if not os.getenv('OPENAI_API_KEY'):
        print("\n💡 To test actual AI raven sending, set your OpenAI API key:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
    else:
        print("\n🎉 Send raven tool ready for full AI integration!")


if __name__ == "__main__":
    main()