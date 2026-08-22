"""
Communication and intelligence tools for the feudal simulation.

Ravens, border assessment, and the strategic compendium, plus the shared rookery
toolset and the universal end_turn tool.
"""

from enum import Enum
from typing import Callable

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401


def create_send_raven_tool(house_entity) -> Callable:
    """
    Factory function to create a send_raven tool bound to a specific house entity.
    
    Args:
        house_entity: The House entity that this tool will operate on
        
    Returns:
        A send_raven tool function bound to the house
    """
    from feudal_sim.components.rookery import RookeryComponent

    # Get rookery component to access known recipients
    rookery = house_entity.get_component(RookeryComponent)

    if not rookery:
        # If no rookery, create a dummy tool that explains the limitation
        @function_tool
        def send_raven_unavailable(message: str) -> str:
            """No raven communication available - no rookery component."""
            return f"House {house_entity.name} has no rookery to send ravens"

        return send_raven_unavailable

    # Get known recipients and create dynamic enum
    known_recipients = rookery.get_known_recipients_list()

    if not known_recipients:
        # If no known recipients, create tool that explains this
        @function_tool
        def send_raven_no_recipients(message: str) -> str:
            """No known recipients for raven communication."""
            return f"House {house_entity.name} has no known recipients to send ravens to"

        return send_raven_no_recipients

    # Create dynamic enum for known recipients
    # Use a safe name format for enum creation - map each name to itself
    recipient_dict = {name: name for name in known_recipients}
    RecipientEnum = Enum('Recipient', recipient_dict)

    @function_tool
    def send_raven(recipient: RecipientEnum, message: str) -> str:
        """
        Send a raven message to another house or entity. Ravens take time to deliver — messages sent this week will arrive next week. Consider waiting for a response before sending additional messages.
        
        Args:
            recipient: The house or entity to send the message to (must be a known recipient)
            message: The message content to send
            
        Returns:
            String indicating success or failure of sending the raven
        """
        # Convert enum value back to original recipient name
        recipient_name = recipient.value

        # Use the rookery component to send the raven
        success = rookery.send_raven(recipient_name, message)

        if success:
            return f"Raven sent to {recipient_name}: '{message}' — message will arrive next week."
        else:
            return f"Failed to send raven to {recipient_name} — unknown recipient or other error"

    # Add action description for dynamic prompts
    send_raven.action_description = "**Send Ravens**: Dispatch messages to other lords (ravens arrive next week)"

    return send_raven


def create_assess_border_tool(house_entity) -> Callable:
    """
    Factory function to create an assess_border tool bound to a specific house entity.
    """
    from feudal_sim.components.territory import TerritoryComponent

    territory_component = house_entity.get_component(TerritoryComponent)

    if not territory_component:
        @function_tool
        def assess_border_unavailable(direction: str) -> str:
            """No territory assessment available - no territory component."""
            return f"House {house_entity.name} has no territory to assess"
        return assess_border_unavailable

    # Create enum for valid directions
    DirectionEnum = Enum('Direction', {'N': 'N', 'NE': 'NE', 'SE': 'SE', 'S': 'S', 'SW': 'SW', 'NW': 'NW'})

    @function_tool
    def assess_border(ctx: RunContextWrapper["SimulationContext"], direction: DirectionEnum) -> str:
        """
        Assess border in a specific direction for expansion opportunities. Assess a border direction to gather information before expanding.
        
        Args:
            direction: Direction to assess (N, NE, SE, S, SW, NW)
            
        Returns:
            Detailed border assessment with individual tile information including terrain infomation and cost to expand.
        """
        direction_str = direction.value

        # Get simulation context from RunContextWrapper
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return f"Border assessment for {direction_str} direction - map access not available"

        hex_grid = sim_context.hex_grid

        # Get direction analysis
        direction_analysis = territory_component.calculate_direction_value(direction_str, hex_grid)

        if not direction_analysis['has_opportunities']:
            return direction_analysis['message']

        # Create simplified observation
        terrain_types = []
        for opportunity in direction_analysis['opportunities'][:3]:  # Show first 3 terrain types
            terrain = opportunity['terrain_type']
            if terrain not in terrain_types:
                terrain_types.append(terrain)

        if direction_analysis['total_opportunities'] > 3:
            terrain_summary = f"{', '.join(terrain_types)} (and {direction_analysis['total_opportunities'] - 3} more tiles)"
        else:
            terrain_summary = ', '.join(terrain_types)

        costs = direction_analysis['expansion_cost_estimate']

        return f"Border assessment: {direction_analysis['total_opportunities']} tiles ({terrain_summary}). Cost: {costs['material']} material, {costs['gold']} gold"

    # Add action description for dynamic prompts
    assess_border.action_description = "**Assess Borders**: Scout a border direction to gather intelligence before expansion"

    return assess_border



def create_read_compendium_tool(house_entity) -> Callable:
    """
    Factory function to create a read_compendium tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent

    intelligence_component = house_entity.get_component(IntelligenceComponent)

    if not intelligence_component:
        @function_tool
        def read_compendium_unavailable(topic: str = None) -> str:
            """No compendium available."""
            return f"House {house_entity.name} has no compendium to consult"
        return read_compendium_unavailable

    @function_tool
    def read_compendium(topic: str = None) -> str:
        """
        Read from your strategic compendium - a journal of intelligence, observations, and strategic notes.
        If no topic is specified, shows a summary of all entries. If a topic is specified, shows detailed information about that house or subject.
        
        Args:
            topic: Optional specific house name or subject to read about (e.g. "Stark", "Lannister"). If not provided, shows all entries.
            
        Returns:
            Your compendium entries - either all summaries or detailed information about the specified topic
        """
        if topic:
            # Try to find specific house intelligence
            neighbors = intelligence_component.get_neighbors()
            if topic in neighbors:
                return intelligence_component.format_intelligence_report(topic)
            else:
                return f"No compendium entry found for '{topic}'. Available topics: {', '.join(neighbors)}"
        else:
            # Show all intelligence summary
            return intelligence_component.format_all_intelligence_summary()

    # Add action description for dynamic prompts
    read_compendium.action_description = "**Read Compendium**: Consult your strategic journal of intelligence and observations"

    return read_compendium


def create_write_compendium_tool(house_entity) -> Callable:
    """
    Factory function to create a write_compendium tool bound to a specific house entity.
    """
    from feudal_sim.components.intelligence import IntelligenceComponent

    intelligence_component = house_entity.get_component(IntelligenceComponent)

    if not intelligence_component:
        @function_tool
        def write_compendium_unavailable(topic: str, entry: str) -> str:
            """No compendium available."""
            return f"House {house_entity.name} has no compendium to write in"
        return write_compendium_unavailable

    @function_tool
    def write_compendium(topic: str, entry: str) -> str:
        """
        Write an entry in your strategic compendium - record intelligence, observations, strategic thoughts, or plans.
        Use this to keep track of important information about other houses, diplomatic relations, military assessments, or strategic plans.
        
        Args:
            topic: The subject of your entry (e.g. house name like "Stark" or general topics like "Military Strategy")
            entry: Your strategic notes, observations, or intelligence about this topic
            
        Returns:
            Confirmation of the compendium entry
        """
        # Check if this is a known house - if so, use intelligence system
        neighbors = intelligence_component.get_neighbors()
        if topic in neighbors:
            intelligence_component.update_notes(topic, entry)
            return f"Compendium updated - {topic}: {entry}"
        else:
            # For general topics, we can still record it as intelligence notes
            # The intelligence system can handle arbitrary topics
            intelligence_component.update_notes(topic, entry)
            return f"Compendium entry recorded - {topic}: {entry}"

    # Add action description for dynamic prompts
    write_compendium.action_description = "**Write Compendium**: Record strategic intelligence, observations, and plans in your journal"

    return write_compendium


@function_tool
def end_turn() -> str:
    """
    End your current turn.
    
    Returns:
        Confirmation of the turn ending
    """
    return "Turn ended"


def create_rookery_toolset(entity, include_send: bool = True) -> list:
    """
    Shared rookery tools for any entity with a RookeryComponent.
    - list_known_recipients: list all known recipient IDs
    - send_raven(recipient_id, message): send to any known recipient (optional)
    """
    tools = []
    from feudal_sim.components.rookery import RookeryComponent

    @function_tool
    def list_known_recipients(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        List all known recipients for sending ravens.
        """
        rookery: RookeryComponent = entity.get_component(RookeryComponent)
        if not rookery:
            return "No rookery available"
        known = rookery.get_known_recipients_list()
        return ", ".join(known) if known else "No known recipients"
    list_known_recipients.action_description = "**List Known Recipients**: See who you can send ravens to"
    tools.append(list_known_recipients)

    if include_send:
        @function_tool
        def send_raven(ctx: RunContextWrapper["SimulationContext"], recipient_id: str, message: str) -> str:
            """
            Send a raven message to another house or entity.
            """
            sim_context = ctx.context
            rookery: RookeryComponent = entity.get_component(RookeryComponent)
            if not rookery:
                return "Cannot send raven - no rookery"
            if sim_context:
                rookery.set_current_date_context(
                    getattr(sim_context, 'current_turn', 1),
                    getattr(sim_context, 'current_date', 'Week 1, Spring, Year 1')
                )
            ok = rookery.send_raven(recipient_id, message)
            return "Raven dispatched; arrives next week" if ok else "Failed to dispatch raven (unknown recipient)"
        send_raven.action_description = "**Send Raven**: Message any known recipient (arrives next week)"
        tools.append(send_raven)

    return tools
