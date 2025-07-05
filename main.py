import click
from feudal_sim.core.config import config
from feudal_sim.core.simulation import Simulation
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.extensions.resource_monitor import resource_monitor

@click.command()
@click.option('--simulation_config', type=str, default='simulation', help='Name of simulation config json file (in config folder)')
@click.option('--world_config', type=str, default='world', help='Name of world config json file (in config folder)')
def main(simulation_config, world_config):
    config.load_config(simulation_config)
    config.load_config(world_config)
    simulation = Simulation()
    try:
        while True:
            simulation.step()
            simulation.render()
            input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Demonstrate extensibility: get analytics from extension
        print("\n📈 Resource Monitor Summary:")
        summary = resource_monitor.get_summary()
        for house_name, resources in summary.items():
            print(f"  {house_name}:")
            for resource_type, stats in resources.items():
                print(f"    {resource_type}: {stats['total_gained']:.0f} gained, {stats['current_amount']:.0f} current")
        
        # Emit simulation end event for extensions
        event_bus.emit(EventType.SIMULATION_ENDED, simulation)
        
        # Clean up shared memory resources
        simulation.hex_grid.terminate_renderer()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()