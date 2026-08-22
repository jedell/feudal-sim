#!/usr/bin/env python3
"""
Test script to verify positioned entity rendering works.
Creates a general and displays it in the renderer.
"""

import asyncio
import multiprocessing.shared_memory as shm
from feudal_sim.core.simulation import Simulation
from feudal_sim.core.entities import Entity
from feudal_sim.components.position import PositionComponent
from feudal_sim.components.ai import AIComponent
from feudal_sim.ai.prompts import AgentType


def cleanup_shared_memory():
    """Clean up any leftover shared memory segments."""
    memory_names = ["psm_hex_grid", "psm_houses", "psm_entities"]
    for name in memory_names:
        try:
            existing_shm = shm.SharedMemory(name=name)
            existing_shm.close()
            existing_shm.unlink()
            print(f"🧹 Cleaned up existing shared memory: {name}")
        except FileNotFoundError:
            pass  # Doesn't exist, which is fine
        except Exception as e:
            print(f"⚠️  Warning: Could not clean up {name}: {e}")

async def test_positioned_entity_rendering():
    """Test deploying a general and rendering it."""
    print("🧪 Testing positioned entity rendering...")
    
    # Clean up any existing shared memory
    cleanup_shared_memory()
    
    # Create simulation
    simulation = Simulation(debug=False)  # Enable renderer by not using debug mode
    
    # Find Stark house for deployment
    stark_house = None
    for house in simulation.houses:
        if house.name == "Stark":
            stark_house = house
            break
    
    if not stark_house:
        print("❌ Could not find Stark house")
        return
    
    # Get stark's territory to find a deployment position
    stark_territory = list(stark_house.territory)
    if not stark_territory:
        print("❌ Stark has no territory")
        return
    
    deployment_tile = stark_territory[0]
    deployment_pos = (deployment_tile.q, deployment_tile.r)
    
    print(f"📍 Deploying general at position {deployment_pos}")
    
    # Create a general entity manually
    general_id = f"{stark_house.id}_test_general"
    general_entity = Entity(general_id, "General Snow")
    general_entity.house_id = stark_house.id
    general_entity.assigned_soldiers = 100
    
    # Add position component
    position_comp = PositionComponent(
        entity_id=general_id,
        position=deployment_pos,
        operational_range=3,
        movement_points=2
    )
    general_entity.add_component(position_comp)
    
    # Add AI component
    ai_comp = AIComponent(
        name="General Snow",
        agent_type=AgentType.GENERAL,
        entity_id=general_id,
        house_name=stark_house.name
    )
    general_entity.add_component(ai_comp)
    
    # Register with entity manager
    simulation.entity_manager._entities[general_id] = general_entity
    if 'general' not in simulation.entity_manager._entities_by_type:
        simulation.entity_manager._entities_by_type['general'] = []
    simulation.entity_manager._entities_by_type['general'].append(general_entity)
    
    print(f"✅ Created general: {general_entity.name} at {deployment_pos}")
    print(f"   - Assigned soldiers: {general_entity.assigned_soldiers}")
    print(f"   - Movement points: {position_comp.remaining_movement}/{position_comp.movement_points}")
    
    # Render to display the general
    print("🎨 Rendering with positioned entities...")
    simulation.render()
    
    print("✅ Positioned entity rendering test completed!")
    print("   Check the renderer window to see the general displayed as ⚔ symbol")
    
    # Keep the simulation running briefly to see the visual result
    print("\n🖥️  Renderer is running. Check the visual window.")
    print("   Running for 3 seconds to demonstrate sprite rendering...")
    
    try:
        for i in range(10):
            print(f"   Renderer running... {3-i} seconds remaining")
            await asyncio.sleep(1)
        print("\n✅ Sprite integration test completed successfully!")
        print("   You should see:")
        print("   - Tree sprites on forest tiles")
        print("   - Keep sprites for cities")
        print("   - Knight sprites for generals")
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        print("🧹 Cleaning up renderer...")
        simulation.hex_grid.terminate_renderer()


if __name__ == "__main__":
    asyncio.run(test_positioned_entity_rendering())