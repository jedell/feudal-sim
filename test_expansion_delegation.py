#!/usr/bin/env python3
"""
Test expansion delegation workflow: lord deploys general -> general expands territory autonomously.
"""

import asyncio
from feudal_sim.core.config import config
from feudal_sim.core.simulation import Simulation
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.components.subagent_group import SubAgentGroup
from feudal_sim.components.terrain_observation import TerrainObservation

async def main():
    # Load configs
    config.load_config('simulation')
    config.load_config('world')
    
    # Create simulation
    print("🏗️ Creating simulation...")
    simulation = Simulation()
    
    print(f"✅ Created {len(simulation.houses)} houses")
    
    # Find a house with sufficient population
    target_house = None
    for house in simulation.houses:
        population = house.get_component(PopulationComponent)
        if population and population.get_worker_count() >= 5 and population.get_soldier_count() >= 5:
            target_house = house
            break
    
    if not target_house:
        print("❌ No house found with sufficient population for testing")
        return
    
    print(f"🎯 Testing with {target_house.get_name()}")
    
    # Check initial state
    population = target_house.get_component(PopulationComponent)
    territory = target_house.get_component(TerritoryComponent)
    print(f"   Initial Workers: {population.get_worker_count()}")
    print(f"   Initial Soldiers: {population.get_soldier_count()}")
    print(f"   Initial Territory: {len(territory.territory)} tiles")
    
    # Execute production phase to ensure resources are updated
    print("\n⚙️ Executing Production Phase...")
    simulation.execute_production_phase()
    
    # Execute actions phase - this should trigger AI decision making including potential general deployment
    print("\n🧠 Executing Actions Phase (AI Decisions)...")
    await simulation.execute_actions_phase()
    
    # Check if any generals were deployed by looking at entity manager
    print(f"\n🔍 Checking for deployed generals...")
    generals = []
    
    # Use get_entities method to get proper entity objects
    all_entities = simulation.entity_manager.get_entities()
    for entity in all_entities:
        subagent_comp = entity.get_component(SubAgentGroup)
        if subagent_comp:
            generals.append(entity)
    
    if generals:
        print(f"✅ Found {len(generals)} deployed generals:")
        for entity in generals:
            subagent = entity.get_component(SubAgentGroup)
            print(f"   General {entity.entity_id}: {subagent.assigned_workers}W, {subagent.assigned_soldiers}S")
            if entity.get_component(TerrainObservation):
                print(f"   Has terrain observation capability")
    else:
        print("❌ No generals deployed in this turn")
    
    # Execute another turn to see general actions
    print("\n🔄 Executing second turn for general actions...")
    await simulation.execute_actions_phase()
    
    # Check final population state
    print(f"\n📊 Final State for {target_house.get_name()}:")
    population = target_house.get_component(PopulationComponent)
    territory = target_house.get_component(TerritoryComponent)
    print(f"   Available Workers: {population.get_worker_count()}")
    print(f"   Available Soldiers: {population.get_soldier_count()}")
    print(f"   Assigned Population: {population.assigned_population}")
    print(f"   Territory: {len(territory.territory)} tiles")
    
    # Check general activities
    if generals:
        print(f"\n🎖️ General Activities:")
        for entity in generals:
            subagent = entity.get_component(SubAgentGroup)
            print(f"   General {entity.entity_id}: Supply {subagent.supply}, Morale {subagent.morale}")
            obs_comp = entity.get_component(TerrainObservation)
            if obs_comp:
                print(f"   Observed {len(obs_comp.observed_tiles)} tiles")

if __name__ == "__main__":
    asyncio.run(main())