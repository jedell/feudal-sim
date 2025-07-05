"""
AI Tools for the feudal simulation.

This module contains tool functions that AI agents can call to interact with the simulation.
Each tool is decorated with @function_tool to make it available to the OpenAI Agents SDK.

Tools need access to the current entity/house context, so they will be created by factory functions
that bind the specific house instance to the tool.
"""

from agents import function_tool
from typing import Callable
from enum import Enum


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
        Send a raven message to another house or entity.
        
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
            # Also add observation to AI about sending the raven
            from feudal_sim.components.ai import AIComponent
            ai_component = house_entity.get_component(AIComponent)
            if ai_component:
                ai_component.add_observation(f"You sent a raven to {recipient_name}: '{message}'", "Actions")
            
            return f"Successfully sent raven to {recipient_name}: '{message}'"
        else:
            return f"Failed to send raven to {recipient_name} - unknown recipient or other error"
    
    return send_raven


def create_house_toolset(house) -> list:
    """
    Create the complete set of tools available to a house's AI agent.
    
    Args:
        house: The House instance to create tools for
        
    Returns:
        List of tool functions bound to the house
    """
    tools = []
    
    # Communication tools
    tools.append(create_send_raven_tool(house))
    
    # Future tools can be added here:
    # tools.append(create_dispatch_army_tool(house))
    # tools.append(create_dispatch_scout_tool(house))
    # tools.append(create_manage_resources_tool(house))
    # tools.append(create_collect_taxes_tool(house))
    
    return tools


# Tool categories for different entity types
def create_army_toolset(army_entity) -> list:
    """Create tools for army entities (future implementation)."""
    return []


def create_scout_toolset(scout_entity) -> list:
    """Create tools for scout entities (future implementation).""" 
    return []


def create_caravan_toolset(caravan_entity) -> list:
    """Create tools for caravan entities (future implementation)."""
    return []


# Registry of tool factories by entity type
TOOL_FACTORIES = {
    'house': create_house_toolset,
    'army': create_army_toolset,
    'scout': create_scout_toolset,
    'caravan': create_caravan_toolset,
}


def get_tools_for_entity(entity, entity_type: str = 'house') -> list:
    """
    Get the appropriate toolset for an entity.
    
    Args:
        entity: The entity to create tools for
        entity_type: Type of entity ('house', 'army', 'scout', 'caravan')
        
    Returns:
        List of tool functions for the entity
    """
    factory = TOOL_FACTORIES.get(entity_type)
    if factory:
        return factory(entity)
    else:
        print(f"Warning: No tool factory found for entity type '{entity_type}'")
        return []