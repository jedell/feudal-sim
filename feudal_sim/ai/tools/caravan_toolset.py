"""
Toolset factories for army, scout, and caravan entities.
"""

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401
from feudal_sim.ai.tools.communication import end_turn


# Tool categories for different entity types
def create_army_toolset(_army_entity) -> list:
    """Create tools for army entities (future implementation)."""
    tools = []

    # Universal tools
    tools.append(end_turn)

    return tools


def create_scout_toolset(_scout_entity) -> list:
    """Create tools for scout entities (future implementation)."""
    tools = []

    # Universal tools
    tools.append(end_turn)

    return tools


def create_caravan_toolset(caravan_entity) -> list:
    """Create tools for caravan entities."""
    tools = []

    # Movement and status tools
    from feudal_sim.components.cargo import CargoComponent
    from feudal_sim.components.pathfinding import PathfindingComponent
    from feudal_sim.components.position import PositionComponent

    @function_tool
    def caravan_status(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Get current caravan status including position, destination, cargo, and progress.
        """
        position_comp = caravan_entity.get_component(PositionComponent)
        pathfinding_comp = caravan_entity.get_component(PathfindingComponent)
        cargo_comp = caravan_entity.get_component(CargoComponent)

        status_parts = [f"Caravan: {caravan_entity.name}"]

        # Position info
        if position_comp and position_comp.position:
            pos = position_comp.position
            movement_info = f"Position: ({pos[0]}, {pos[1]}), Movement: {position_comp.remaining_movement}/{position_comp.max_movement_points}"
            status_parts.append(movement_info)

        # Destination and progress
        if pathfinding_comp and pathfinding_comp.destination:
            dest = pathfinding_comp.destination
            remaining = pathfinding_comp.get_remaining_distance()
            status_parts.append(f"Destination: ({dest[0]}, {dest[1]}), Distance: {remaining} tiles")

            if pathfinding_comp.is_at_destination():
                status_parts.append("STATUS: At destination!")

        # Cargo info
        if cargo_comp:
            cargo_summary = cargo_comp.get_cargo_summary()
            trade_summary = cargo_comp.get_trade_summary()
            status_parts.append(f"Cargo: {cargo_summary}")
            status_parts.append(f"Mission: {trade_summary}")

        return " | ".join(status_parts)

    caravan_status.action_description = "**Caravan Status**: Check position, destination, cargo, and mission progress"
    tools.append(caravan_status)

    @function_tool
    def continue_journey(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Continue moving towards the destination (automatic movement handled by simulation).
        """
        pathfinding_comp = caravan_entity.get_component(PathfindingComponent)

        if not pathfinding_comp:
            return "Cannot continue journey - no pathfinding capability"

        if pathfinding_comp.is_at_destination():
            return "Already at destination - ready for trade negotiations"

        remaining_distance = pathfinding_comp.get_remaining_distance()
        return f"Continuing journey to destination. {remaining_distance} tiles remaining."

    continue_journey.action_description = "**Continue Journey**: Proceed towards trade destination"
    tools.append(continue_journey)

    # Communication with parent house
    @function_tool
    def send_trade_update(ctx: RunContextWrapper["SimulationContext"], message: str) -> str:
        """
        Send a status update back to your sponsoring house.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send update - simulation context unavailable"

        sender_house_id = getattr(caravan_entity, 'sender_house_id', None)
        if not sender_house_id:
            return "Cannot send update - no parent house identified"

        parent_house = sim_context.entity_manager.get_entity(sender_house_id)
        if not parent_house:
            return "Cannot send update - parent house not found"

        # Add observation to parent house AI
        from feudal_sim.components.ai import AIComponent
        ai_comp = parent_house.get_component(AIComponent)
        if ai_comp:
            caravan_update = f"Trade caravan update: {message}"
            ai_comp.add_observation(caravan_update, "Actions")
            return f"Trade update sent to {parent_house.name}: '{message}'"

        return "Update sent but parent house has no AI to receive it"

    send_trade_update.action_description = "**Send Trade Update**: Report status to sponsoring house"
    tools.append(send_trade_update)

    # Universal tools
    tools.append(end_turn)

    return tools
