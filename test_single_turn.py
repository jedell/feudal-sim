#!/usr/bin/env python3
"""
Test a single turn of the simulation to see AI decision making with ravens.
"""

from feudal_sim.core.config import config
from feudal_sim.core.simulation import Simulation
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.rookery import RookeryComponent

def main():
    # Load configs
    config.load_config('simulation')
    config.load_config('world')
    
    # Create simulation
    print("🏗️ Creating simulation...")
    simulation = Simulation()
    
    print(f"✅ Created {len(simulation.houses)} houses")
    
    # Check communication setup
    for house in simulation.houses:
        rookery = house.get_component(RookeryComponent)
        known = rookery.get_known_recipients_list() if rookery else []
        print(f"📍 {house.get_name()} knows: {known}")
    
    # Execute a few phases to get to AI decisions
    print("\n⚙️ Executing Production Phase...")
    simulation.execute_production_phase()
    
    print("\n🧠 Executing Actions Phase (AI Decisions)...")
    simulation.execute_actions_phase()
    
    print("\n📬 Executing Events Phase (Raven Delivery)...")
    simulation.execute_events_phase()
    
    print("\n📊 Executing Cleanup Phase...")
    simulation.execute_cleanup_phase()
    
    # Check final state
    print(f"\n📈 Final State:")
    for house in simulation.houses:
        ai = house.get_component(AIComponent)
        rookery = house.get_component(RookeryComponent)
        print(f"🏠 {house.get_name()}:")
        print(f"   Resources: {house.resources}")
        print(f"   AI Status: {ai.get_ai_status() if ai else 'No AI'}")
        print(f"   Rookery Status: {rookery.get_communication_status() if rookery else 'No Rookery'}")

if __name__ == "__main__":
    main()