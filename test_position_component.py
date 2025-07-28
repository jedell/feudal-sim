#!/usr/bin/env python3
"""
Test script for PositionComponent functionality.
"""

from feudal_sim.components.position import PositionComponent
from feudal_sim.core.entities import Entity


def test_position_component():
    """Test basic PositionComponent functionality."""
    print("🧪 Testing PositionComponent...")
    
    # Test 1: Basic position management
    print("\n1. Testing basic position management:")
    entity = Entity("test_general", "General Stark")
    position_comp = PositionComponent(entity.id, position=(5, 3), operational_range=3, movement_points=2)
    entity.add_component(position_comp)
    
    print(f"   Initial position: {position_comp.position}")
    print(f"   Operational range: {position_comp.operational_range}")
    print(f"   Movement points: {position_comp.movement_points}")
    
    # Test 2: Movement validation
    print("\n2. Testing movement:")
    result = position_comp.move_to((6, 3), current_turn=1)
    print(f"   Move to (6, 3): {result['success']} - {result['message']}")
    print(f"   Remaining movement: {result.get('remaining_movement', 'N/A')}")
    
    # Test 3: Invalid movement (too far)
    result = position_comp.move_to((10, 10), current_turn=1)
    print(f"   Move to (10, 10): {result['success']} - {result['message']}")
    
    # Test 4: Hex distance calculation
    print("\n3. Testing hex distance calculation:")
    distances = [
        ((0, 0), (1, 0), 1),
        ((0, 0), (1, -1), 1), 
        ((0, 0), (2, -1), 2),
        ((0, 0), (3, -2), 3),
        ((5, 3), (8, 1), 3)
    ]
    
    for pos1, pos2, expected in distances:
        calculated = PositionComponent.hex_distance(pos1, pos2)
        status = "✅" if calculated == expected else "❌"
        print(f"   {status} Distance {pos1} to {pos2}: {calculated} (expected {expected})")
    
    # Test 5: Operational range
    print("\n4. Testing operational range:")
    position_comp.position = (5, 5)
    tiles_in_range = position_comp.get_tiles_in_range(range_override=2)
    print(f"   Tiles in range 2 from (5, 5): {len(tiles_in_range)} tiles")
    
    # Test a few specific tiles
    test_tiles = [(5, 6), (5, 7), (5, 8), (7, 4), (8, 3)]
    for tile in test_tiles:
        can_reach = position_comp.can_reach_tile(tile, range_override=2)
        distance = position_comp.hex_distance(position_comp.position, tile)
        print(f"   Can reach {tile} (distance {distance}): {can_reach}")
    
    # Test 6: Movement reset
    print("\n5. Testing movement reset:")
    print(f"   Movement before reset: {position_comp.remaining_movement}")
    position_comp.reset_movement(current_turn=2)
    print(f"   Movement after reset: {position_comp.remaining_movement}")
    
    # Test 7: Movement status
    print("\n6. Testing movement status:")
    status = position_comp.get_movement_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    print("\n✅ PositionComponent tests completed!")


if __name__ == "__main__":
    test_position_component()