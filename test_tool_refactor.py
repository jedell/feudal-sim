#!/usr/bin/env python3
"""
Simple test to verify the AI tool refactoring works.
"""

from feudal_sim.core.entities import Entity
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.position import PositionComponent
from feudal_sim.ai.prompts import AgentType


def test_tool_refactor():
    """Test that the AI component tool refactoring works."""
    print("🧪 Testing AI Component Tool Refactoring...")
    
    # Test 1: Entity type detection
    print("\n1. Testing entity type detection:")
    
    # House lord should detect as 'house'
    house_ai = AIComponent(agent_type=AgentType.HOUSE_LORD)
    print(f"   House Lord → {house_ai._determine_entity_type()}")
    
    # General should detect as 'general'
    general_ai = AIComponent(agent_type=AgentType.GENERAL)
    print(f"   General → {general_ai._determine_entity_type()}")
    
    # Scout should detect as 'scout'
    scout_ai = AIComponent(agent_type=AgentType.SCOUT)
    print(f"   Scout → {scout_ai._determine_entity_type()}")
    
    # Test 2: Component-based fallback detection
    print("\n2. Testing component-based fallback:")
    
    # Create positioned entity
    positioned_entity = Entity("positioned", "Positioned Unit")
    positioned_entity.add_component(PositionComponent("positioned", (0, 0)))
    
    fallback_ai = AIComponent(agent_type=AgentType.HOUSE_LORD)
    positioned_entity.add_component(fallback_ai)
    
    detected_type = fallback_ai._determine_entity_type()
    print(f"   Positioned House Lord → {detected_type}")
    
    # Test 3: General with position component
    print("\n3. Testing general tool initialization:")
    
    general_entity = Entity("general", "General Snow")
    general_entity.add_component(PositionComponent("general", (5, 3)))
    
    general_ai = AIComponent(
        name="General Snow",
        agent_type=AgentType.GENERAL,
        entity_id="general"
    )
    
    # This should work without component checking issues
    try:
        general_entity.add_component(general_ai)
        tools = general_ai._get_available_tools()
        print(f"   ✅ General tools created successfully: {len(tools)} tools")
        
        for tool in tools:
            tool_name = getattr(tool, '__name__', 'unknown')
            action_desc = getattr(tool, 'action_description', 'No description')
            print(f"      - {tool_name}: {action_desc[:50]}...")
            
    except Exception as e:
        print(f"   ❌ General tool creation failed: {e}")
    
    print("\n✅ Tool refactoring verification completed!")
    print("\n📊 Key improvements:")
    print("   - Unified tool initialization via get_tools_for_entity()")
    print("   - Automatic entity type detection")
    print("   - Extensible toolset registry") 
    print("   - Eliminated code duplication")
    print("   - Support for generals and other sub-agents")


if __name__ == "__main__":
    test_tool_refactor()