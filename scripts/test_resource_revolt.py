#!/usr/bin/env python3

from feudal_sim.core.simulation import Simulation
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.components.resource import ResourceComponent

def test_resource_revolt():
    """Test that revolts cause both territory and resource losses."""
    print("=== Testing Resource Loss During Revolts ===\n")
    
    # Create simulation
    sim = Simulation()
    
    # Get the first house
    house = sim.houses[0]
    print(f"Testing with House: {house.get_name()}")
    
    # Get components
    population_component = house.get_component(PopulationComponent)
    territory_component = house.get_component(TerritoryComponent)
    resource_component = house.get_component(ResourceComponent)
    
    if not all([population_component, territory_component, resource_component]):
        print("❌ Required components not found!")
        return
    
    # Show initial state
    print("\n🏰 Initial State:")
    print(f"  Territory tiles: {len(territory_component.territory)}")
    print(f"  Resources: {house.resources}")
    print(f"  Population loyalty: {population_component.loyalty}")
    
    # Force low loyalty to trigger revolt
    population_component.population_loyalty = 10  # Very low loyalty
    print(f"\n⚠️  Setting loyalty to {population_component.loyalty} to trigger revolt")
    
    # Force a revolt check (simulate multiple turns until revolt occurs)
    revolt_occurred = False
    for turn in range(1, 50):  # Try up to 50 turns
        if population_component.check_for_revolt(turn):
            print(f"\n🔥 Revolt triggered on turn {turn}!")
            
            # Execute the revolt
            revolt_result = population_component.execute_revolt(sim.hex_grid)
            
            if revolt_result['success']:
                print("✅ Revolt executed successfully!")
                print(f"  Message: {revolt_result['message']}")
                print(f"  Tiles lost: {revolt_result['tiles_lost']}")
                print(f"  Resource losses: {revolt_result['resource_losses']}")
                
                # Show final state
                print("\n🏰 Final State:")
                print(f"  Territory tiles: {len(territory_component.territory)}")
                print(f"  Resources: {house.resources}")
                
                revolt_occurred = True
                break
            else:
                print(f"❌ Revolt failed: {revolt_result['message']}")
    
    if not revolt_occurred:
        print("❌ No revolt occurred in 50 turns (this is possible with 25% chance)")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_resource_revolt() 