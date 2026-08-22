import click
import asyncio
import logging
from feudal_sim.core.config import config
from feudal_sim.core.logger import setup_logging, get_logger
from feudal_sim.core.simulation import Simulation
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.extensions.resource_monitor import resource_monitor

log = get_logger(__name__)

@click.command()
@click.option('--debug', is_flag=True, help='Run debug mode')
@click.option('--auto', is_flag=True, help='Run continuously without waiting for input')
@click.option('--turns', type=int, default=0, help='Stop after N turns (0 = run forever, requires --auto)')
@click.option('--simulation_config', type=str, default='simulation', help='Name of simulation config json file (in config folder)')
@click.option('--world_config', type=str, default='world', help='Name of world config json file (in config folder)')
def main(simulation_config, world_config, debug, auto, turns):
    setup_logging(logging.DEBUG if debug else logging.INFO)

    async def run_simulation():
        config.load_config(simulation_config)
        config.load_config(world_config)
        simulation = Simulation(debug=debug)
        try:
            while not simulation.game_over:
                await simulation.step()
                if not debug:
                    simulation.render()
                if simulation.game_over:
                    log.info(f"\n🏆 Simulation ended: {simulation.winner} wins!")
                    break
                if auto:
                    current_turn = simulation.time_manager.get_current_status()['turn']
                    if turns and current_turn >= turns:
                        log.info(f"\nReached turn {current_turn}, stopping.")
                        break
                else:
                    input("Press Enter to continue...")
        except KeyboardInterrupt:
            log.info("\nShutting down (interrupted)...")
        finally:
            log.info("\n📈 Resource Monitor Summary:")
            summary = resource_monitor.get_summary()
            for house_name, resources in summary.items():
                log.info(f"  {house_name}:")
                for resource_type, stats in resources.items():
                    log.info(f"    {resource_type}: {stats['total_gained']:.0f} gained, {stats['current_amount']:.0f} current")

            event_bus.emit(EventType.SIMULATION_ENDED, simulation)

            if not debug:
                simulation.hex_grid.terminate_renderer()
            log.info("Cleanup complete.")

    asyncio.run(run_simulation())

if __name__ == "__main__":
    main()
