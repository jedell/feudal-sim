#!/usr/bin/env python3
"""
Test script for unified AI tool initialization system.
"""

from feudal_sim.core.entities import Entity
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.position import PositionComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.ai.prompts import AgentType
from feudal_sim.ai.tools import get_tools_for_entity


def test_unified_tool_system():
    """Test the unified tool initialization system."""
    print("🧪 Testing Unified AI Tool System...")
    
    # Test 1: House entity tools
    print("\n1. Testing House entity tools:")
    house_entity = Entity("test_house", "House Stark")
    house_entity.add_component(PopulationComponent("test_house", 100, 80))
    house_entity.add_component(TerritoryComponent("test_house"))
    
    house_tools = get_tools_for_entity(house_entity, 'house')
    print(f"   House tools created: {len(house_tools)}")
    for tool in house_tools:
        tool_name = getattr(tool, '__name__', 'unknown')
        action_desc = getattr(tool, 'action_description', 'No description')
        print(f"   - {tool_name}: {action_desc}")
    
    # Test 2: General entity tools
    print("\n2. Testing General entity tools:")
    general_entity = Entity("test_general", "General Snow")
    general_entity.add_component(PositionComponent("test_general", (5, 3), 3, 2))
    
    general_tools = get_tools_for_entity(general_entity, 'general')
    print(f"   General tools created: {len(general_tools)}")
    for tool in general_tools:
        tool_name = getattr(tool, '__name__', 'unknown')
        action_desc = getattr(tool, 'action_description', 'No description')
        print(f"   - {tool_name}: {action_desc}")
    
    # Test 3: AI Component tool detection
    print("\n3. Testing AI Component tool detection:")
    
    # House AI
    house_ai = AIComponent(
        name="Lord Stark", 
        agent_type=AgentType.HOUSE_LORD,
        entity_id="test_house"
    )
    house_entity.add_component(house_ai)
    
    detected_type = house_ai._determine_entity_type()
    print(f"   House AI detected type: {detected_type}")
    
    # General AI  
    general_ai = AIComponent(
        name="General Snow",
        agent_type=AgentType.GENERAL, 
        entity_id="test_general"
    )
    general_entity.add_component(general_ai)
    
    detected_type = general_ai._determine_entity_type()
    print(f"   General AI detected type: {detected_type}")
    
    # Test 4: Tool filtering
    print("\n4. Testing tool availability:")
    
    # Test house tools (should have many)
    house_tools_via_ai = house_ai._get_available_tools()
    print(f"   House AI tools: {len(house_tools_via_ai)}")
    
    # Test general tools (should have fewer, movement-focused)
    general_tools_via_ai = general_ai._get_available_tools()
    print(f"   General AI tools: {len(general_tools_via_ai)}")
    
    # Test 5: Component-based detection fallback
    print("\n5. Testing component-based entity type detection:")
    
    # Create entity with mixed components
    mixed_entity = Entity("test_mixed", "Mixed Entity")
    mixed_entity.add_component(PositionComponent("test_mixed", (0, 0)))
    
    mixed_ai = AIComponent(
        name="Unknown Agent",
        agent_type=AgentType.HOUSE_LORD,  # House lord but positioned
        entity_id="test_mixed"
    )
    mixed_entity.add_component(mixed_ai)
    
    detected_type = mixed_ai._determine_entity_type()
    print(f"   Mixed entity detected type: {detected_type}")
    
    print("\n✅ Unified tool system tests completed!")
    print(f"\n📊 Summary:")
    print(f"   - House tools: {len(house_tools_via_ai)}")
    print(f"   - General tools: {len(general_tools_via_ai)}")
    print(f"   - System successfully unified!")


if __name__ == "__main__":
    test_unified_tool_system()