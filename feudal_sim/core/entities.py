"""
Component-Based Entity System for the Feudal Simulation.

This module provides the foundation for flexible, composable entities that can have
different combinations of behaviors through components.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, List, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from feudal_sim.core.entities import Entity


class Component(ABC):
    """
    Base class for all components in the entity system.
    
    Components encapsulate specific behaviors or data that can be attached to entities.
    Each component should have a single, well-defined responsibility.
    """
    
    def __init__(self, entity_id: str = None):
        self.entity_id: str = entity_id
        self.entity: Optional['Entity'] = None  # Will be set when component is added to entity
    
    @abstractmethod
    def update(self, dt: float, event_bus=None):
        """
        Update the component's state. Called each turn/frame.
        
        Args:
            dt: Time delta (for turn-based games, usually 1.0)
            event_bus: Global event bus for emitting events
        """
        pass
    
    def on_added_to_entity(self, entity: 'Entity'):
        """Called when this component is added to an entity."""
        self.entity = entity
    
    def on_removed_from_entity(self):
        """Called when this component is removed from an entity."""
        self.entity = None
    
    def get_lore_section(self) -> Optional[str]:
        """
        Return lore-friendly explanation of this component's mechanics for AI prompts.
        
        Returns:
            Medieval-style explanation of how this component works, or None if no lore needed
        """
        return None  # Default: no lore contribution


class Entity:
    """
    A container for components that represents a game object.
    
    Entities themselves have no behavior - all functionality comes from components.
    This allows for flexible composition of behaviors.
    """
    
    def __init__(self, entity_id: str = None, name: str = None):
        self.id = entity_id or str(uuid.uuid4())
        self.name = name or self.id
        self._components: Dict[Type[Component], Component] = {}
        self._active = True
    
    def add_component(self, component: Component) -> 'Entity':
        """
        Add a component to this entity.
        
        Args:
            component: The component instance to add
            
        Returns:
            Self for method chaining
        """
        component.entity_id = self.id
        component.on_added_to_entity(self)
        self._components[type(component)] = component
        return self
    
    def remove_component(self, component_type: Type[Component]) -> Optional[Component]:
        """
        Remove a component from this entity.
        
        Args:
            component_type: The type of component to remove
            
        Returns:
            The removed component, or None if not found
        """
        if component_type in self._components:
            component = self._components.pop(component_type)
            component.on_removed_from_entity()
            return component
        return None
    
    def get_component(self, component_type: Type[Component]) -> Optional[Component]:
        """
        Get a component of the specified type.
        
        Args:
            component_type: The type of component to retrieve
            
        Returns:
            The component instance, or None if not found
        """
        return self._components.get(component_type)
    
    def has_component(self, component_type: Type[Component]) -> bool:
        """
        Check if this entity has a component of the specified type.
        
        Args:
            component_type: The type of component to check for
            
        Returns:
            True if the component exists, False otherwise
        """
        return component_type in self._components
    
    def get_all_components(self) -> List[Component]:
        """Get all components attached to this entity."""
        return list(self._components.values())
    
    def update(self, dt: float, event_bus=None):
        """
        Update all components attached to this entity.
        
        Args:
            dt: Time delta
            event_bus: Global event bus for components to emit events
        """
        if not self._active:
            return
            
        for component in self._components.values():
            component.update(dt, event_bus)
    
    def destroy(self):
        """
        Mark this entity for destruction and clean up components.
        """
        self._active = False
        for component in list(self._components.values()):
            component.on_removed_from_entity()
        self._components.clear()
    
    def is_active(self) -> bool:
        """Check if this entity is active."""
        return self._active
    
    def __str__(self):
        component_types = [comp.__class__.__name__ for comp in self._components.values()]
        return f"Entity({self.name}) with components: {component_types}"


class EntityManager:
    """
    Manages the lifecycle of entities in the simulation.
    
    Provides centralized creation, retrieval, and cleanup of entities.
    Also handles batch operations like updating all entities.
    """
    
    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._entities_by_type: Dict[str, List[Entity]] = {}
    
    def create_entity(self, entity_id: str = None, name: str = None, entity_type: str = None) -> Entity:
        """
        Create a new entity and register it with the manager.
        
        Args:
            entity_id: Optional specific ID for the entity
            name: Human-readable name for the entity
            entity_type: Optional type classification (e.g., "house", "army", "scout")
            
        Returns:
            The newly created entity
        """
        entity = Entity(entity_id, name)
        self._entities[entity.id] = entity
        
        # Track by type if specified
        if entity_type:
            if entity_type not in self._entities_by_type:
                self._entities_by_type[entity_type] = []
            self._entities_by_type[entity_type].append(entity)
        
        return entity
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """
        Retrieve an entity by its ID.
        
        Args:
            entity_id: The ID of the entity to retrieve
            
        Returns:
            The entity, or None if not found
        """
        return self._entities.get(entity_id)
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """
        Get all entities of a specific type.
        
        Args:
            entity_type: The type of entities to retrieve
            
        Returns:
            List of entities of the specified type
        """
        return self._entities_by_type.get(entity_type, [])
    
    def get_entities_with_component(self, component_type: Type[Component]) -> List[Entity]:
        """
        Get all entities that have a specific component type.
        
        Args:
            component_type: The type of component to search for
            
        Returns:
            List of entities that have the specified component
        """
        return [entity for entity in self._entities.values() 
                if entity.has_component(component_type) and entity.is_active()]
    
    def get_all_entities(self) -> List[Entity]:
        """Get all active entities."""
        return [entity for entity in self._entities.values() if entity.is_active()]
    
    def destroy_entity(self, entity_id: str) -> bool:
        """
        Destroy an entity and remove it from all tracking.
        
        Args:
            entity_id: The ID of the entity to destroy
            
        Returns:
            True if the entity was found and destroyed, False otherwise
        """
        entity = self._entities.get(entity_id)
        if entity:
            entity.destroy()
            del self._entities[entity_id]
            
            # Remove from type tracking
            for entity_list in self._entities_by_type.values():
                if entity in entity_list:
                    entity_list.remove(entity)
            
            return True
        return False
    
    def update_all_entities(self, dt: float, event_bus=None):
        """
        Update all active entities.
        
        Args:
            dt: Time delta
            event_bus: Global event bus for components to emit events
        """
        for entity in self.get_all_entities():
            entity.update(dt, event_bus)
    
    def cleanup_destroyed_entities(self):
        """Remove any entities that have been marked for destruction."""
        to_remove = [entity_id for entity_id, entity in self._entities.items() 
                     if not entity.is_active()]
        
        for entity_id in to_remove:
            self.destroy_entity(entity_id)
    
    def get_entity_count(self) -> int:
        """Get the total number of active entities."""
        return len([entity for entity in self._entities.values() if entity.is_active()])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the entity manager."""
        stats = {
            'total_entities': len(self._entities),
            'active_entities': self.get_entity_count(),
            'entities_by_type': {
                entity_type: len(entities) 
                for entity_type, entities in self._entities_by_type.items()
            }
        }
        return stats