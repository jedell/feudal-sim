"""
Economic tools for the feudal simulation.

Tax collection and household population allocation.
"""

from typing import Callable

from agents import function_tool


def create_collect_taxes_tool(house_entity) -> Callable:
    """
    Factory function to create a collect_taxes tool bound to a specific house entity.
    """
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.resource import ResourceComponent

    resource_component = house_entity.get_component(ResourceComponent)
    population_component = house_entity.get_component(PopulationComponent)

    if not resource_component or not population_component:
        @function_tool
        def collect_taxes_unavailable(tax_rate: float) -> str:
            """Tax collection unavailable - missing required components."""
            return f"House {house_entity.name} cannot collect taxes - missing required components"
        return collect_taxes_unavailable

    @function_tool
    def collect_taxes(tax_rate: float) -> str:
        """
        Collect taxes from your population to raise gold. Higher tax rates collect more gold but reduce population loyalty.
        Disloyal subjects hide their wealth: at low loyalty the same rate yields as little as half the gold, so taxing an
        unhappy population is wasteful — restore loyalty first (feasts, full granaries), or build settlements that pay
        steady gold income without angering anyone (Walled Town, Castle, City).

        Args:
            tax_rate: Tax rate as a decimal (0.1 = 10% taxes, 0.2 = 20% taxes, etc.). Must be between 0.1 and 1.0.

        Returns:
            Result of tax collection including gold gained and loyalty impact
        """
        try:
            if not (0.01 <= tax_rate <= 1.0):
                return "Tax rate must be between 0.1 (10%) and 1.0 (100%)"

            # Get current values for comparison
            old_gold = resource_component.resources.gold
            old_loyalty = population_component.loyalty
            population = population_component.population

            # Collect taxes using the house method
            tax_collected = house_entity.collect_taxes(tax_rate)

            # Get new values
            new_gold = resource_component.resources.gold
            new_loyalty = population_component.loyalty
            loyalty_lost = old_loyalty - new_loyalty

            # Format tax rate as percentage
            tax_percentage = int(tax_rate * 100)

            return (f"Collected {tax_collected} gold from {population} population with {tax_percentage}% tax rate. "
                   f"Gold: {old_gold:.0f} → {new_gold:.0f} (+{tax_collected}). "
                   f"Population loyalty: {old_loyalty:.0f} → {new_loyalty:.0f} (-{loyalty_lost:.0f})")

        except Exception as e:
            return f"Failed to collect taxes: {str(e)}"

    # Add action description for dynamic prompts
    collect_taxes.action_description = "**Collect Taxes**: Levy tribute from your subjects to raise gold (reduces population loyalty)"

    return collect_taxes


def create_manage_household_tool(house_entity) -> Callable:
    """
    Factory function to create a manage_household tool bound to a specific house entity.
    """
    from feudal_sim.components.population import PopulationComponent

    population_component = house_entity.get_component(PopulationComponent)

    if not population_component:
        @function_tool
        def manage_household_unavailable(worker_ratio: float, soldier_ratio: float) -> str:
            """No population management available."""
            return f"House {house_entity.name} has no population to manage"
        return manage_household_unavailable

    @function_tool
    def manage_household(worker_ratio: float, soldier_ratio: float) -> str:
        """
        Manage your household by allocating your population between workers and soldiers.
        Workers improve resource production efficiency. Soldiers improve territorial expansion success rates.
        The ratios must add up to 1.0 (e.g., 0.7 workers + 0.3 soldiers = 1.0).
        
        Args:
            worker_ratio: Percentage of population allocated to work (0.0 to 1.0, e.g., 0.7 = 70%)
            soldier_ratio: Percentage of population allocated to military service (0.0 to 1.0, e.g., 0.3 = 30%)
            
        Returns:
            Result of the household management including efficiency changes
        """
        # Validate ratios
        if worker_ratio < 0 or soldier_ratio < 0:
            return "Ratios cannot be negative"

        if abs((worker_ratio + soldier_ratio) - 1.0) > 0.001:
            return f"Ratios must add up to 1.0. Current total: {worker_ratio + soldier_ratio:.3f}"

        # Get current status for comparison
        old_status = population_component.get_population_status()

        # Set the new ratios
        success = population_component.set_population_ratios(worker_ratio, soldier_ratio)

        if not success:
            return "Failed to set population ratios - invalid values"

        # Get new status
        new_status = population_component.get_population_status()

        # Calculate the effects
        worker_count = new_status['worker_count']
        soldier_count = new_status['soldier_count']
        worker_efficiency = new_status['worker_efficiency']
        soldier_expansion_bonus = new_status['soldier_expansion_bonus']

        # Format efficiency changes
        old_efficiency = old_status['worker_efficiency']
        efficiency_change = worker_efficiency - old_efficiency
        efficiency_change_text = f"+{efficiency_change:.2f}" if efficiency_change > 0 else f"{efficiency_change:.2f}"

        old_expansion_bonus = old_status['soldier_expansion_bonus']
        expansion_change = soldier_expansion_bonus - old_expansion_bonus
        expansion_change_text = f"+{expansion_change:.2f}" if expansion_change > 0 else f"{expansion_change:.2f}"

        return (f"Household management updated: {worker_count} workers ({worker_ratio*100:.0f}%), "
                f"{soldier_count} soldiers ({soldier_ratio*100:.0f}%). "
                f"Resource efficiency: {worker_efficiency:.2f} ({efficiency_change_text}), "
                f"Expansion bonus: +{soldier_expansion_bonus:.1%} ({expansion_change_text})")

    # Add action description for dynamic prompts
    manage_household.action_description = "**Manage Household**: Allocate your people between labor (improves resources) and military service (improves expansion)"

    return manage_household
