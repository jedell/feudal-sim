"""
Component-Based Entity System for the Feudal Simulation.

This module provides the foundation for flexible, composable entities that can have
different combinations of behaviors through components.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, List, TypeVar, TYPE_CHECKING, overload
import uuid

T = TypeVar('T', bound='Component')

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
    
    @overload
    def get_component(self, component_type: Type[T]) -> Optional[T]: ...
    @overload
    def get_component(self, component_type: Type['Component']) -> Optional['Component']: ...
    def get_component(self, component_type):
        """
        Get a component of the specified type.

        Returns:
            The component instance typed as the requested subclass, or None if not found.
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
    
    def get_positioned_entities_near(self, center_position: tuple, range_tiles: int, 
                                   entity_types: List[str] = None, exclude_entity_id: str = None) -> List[tuple]:
        """
        Get positioned entities within a specified range of a center position.
        
        Args:
            center_position: Center position (q, r) to search around
            range_tiles: Maximum distance in hex tiles
            entity_types: Optional list of entity types to filter by (e.g., ['general', 'scout'])
            exclude_entity_id: Optional entity ID to exclude from results
            
        Returns:
            List of tuples: (entity, distance) sorted by distance
        """
        from feudal_sim.components.position import PositionComponent
        
        results = []
        
        # Get all positioned entities
        positioned_entities = self.get_entities_with_component(PositionComponent)
        
        for entity in positioned_entities:
            # Skip excluded entity
            if exclude_entity_id and entity.id == exclude_entity_id:
                continue
            
            # Filter by entity types if specified
            if entity_types:
                # Check if entity is in any of the specified types
                entity_found = False
                for entity_type in entity_types:
                    if entity in self._entities_by_type.get(entity_type, []):
                        entity_found = True
                        break
                if not entity_found:
                    continue
            
            # Get entity position
            position_comp = entity.get_component(PositionComponent)
            if not position_comp or not position_comp.position:
                continue
            
            # Calculate distance
            distance = PositionComponent.hex_distance(center_position, position_comp.position)
            
            # Check if within range
            if distance <= range_tiles:
                results.append((entity, distance))
        
        # Sort by distance (closest first)
        results.sort(key=lambda x: x[1])
        return results
    
    def get_adjacent_entities(self, center_position: tuple, entity_types: List[str] = None, 
                            exclude_entity_id: str = None) -> List[tuple]:
        """
        Get entities that are directly adjacent (1 tile away) to a position.
        
        Args:
            center_position: Center position (q, r) to search around
            entity_types: Optional list of entity types to filter by
            exclude_entity_id: Optional entity ID to exclude from results
            
        Returns:
            List of tuples: (entity, distance) where distance is always 1
        """
        return self.get_positioned_entities_near(center_position, 1, entity_types, exclude_entity_id)
    
    def get_entity_distance(self, entity1_id: str, entity2_id: str) -> int:
        """
        Calculate distance between two positioned entities.
        
        Args:
            entity1_id: ID of first entity
            entity2_id: ID of second entity
            
        Returns:
            Distance in hex tiles, or -1 if either entity is not positioned
        """
        from feudal_sim.components.position import PositionComponent
        
        entity1 = self.get_entity(entity1_id)
        entity2 = self.get_entity(entity2_id)
        
        if not entity1 or not entity2:
            return -1
        
        pos1_comp = entity1.get_component(PositionComponent)
        pos2_comp = entity2.get_component(PositionComponent)
        
        if not pos1_comp or not pos2_comp or not pos1_comp.position or not pos2_comp.position:
            return -1
        
        return PositionComponent.hex_distance(pos1_comp.position, pos2_comp.position)
    
    def get_entities_by_house(self, house_id: str) -> List[Entity]:
        """
        Get all entities belonging to a specific house.
        
        Args:
            house_id: ID of the house to search for
            
        Returns:
            List of entities belonging to the house
        """
        return [entity for entity in self._entities.values() 
                if hasattr(entity, 'house_id') and entity.house_id == house_id and entity.is_active()]
    
    def find_nearest_entity(self, center_position: tuple, entity_types: List[str] = None, 
                          exclude_entity_id: str = None, max_range: int = None) -> tuple:
        """
        Find the nearest entity to a position.
        
        Args:
            center_position: Center position (q, r) to search around
            entity_types: Optional list of entity types to filter by
            exclude_entity_id: Optional entity ID to exclude from results
            max_range: Optional maximum range to search within
            
        Returns:
            Tuple (entity, distance) of nearest entity, or (None, -1) if none found
        """
        search_range = max_range if max_range is not None else 999999  # Large number for unlimited search
        
        nearby_entities = self.get_positioned_entities_near(
            center_position, search_range, entity_types, exclude_entity_id
        )
        
        if nearby_entities:
            return nearby_entities[0]  # First item is closest due to sorting
        
        return (None, -1)
    
    def get_enemy_entities_near(self, center_position: tuple, range_tiles: int, 
                               friendly_house_id: str) -> List[tuple]:
        """
        Get enemy entities (belonging to different houses) near a position.
        
        Args:
            center_position: Center position (q, r) to search around
            range_tiles: Maximum distance in hex tiles
            friendly_house_id: House ID to consider as friendly (exclude from results)
            
        Returns:
            List of tuples: (entity, distance) of enemy entities sorted by distance
        """
        from feudal_sim.components.position import PositionComponent
        
        results = []
        positioned_entities = self.get_entities_with_component(PositionComponent)
        
        for entity in positioned_entities:
            # Skip entities without house affiliation
            if not hasattr(entity, 'house_id'):
                continue
                
            # Skip friendly entities
            if entity.house_id == friendly_house_id:
                continue
            
            # Get entity position
            position_comp = entity.get_component(PositionComponent)
            if not position_comp or not position_comp.position:
                continue
            
            # Calculate distance
            distance = PositionComponent.hex_distance(center_position, position_comp.position)
            
            # Check if within range
            if distance <= range_tiles:
                results.append((entity, distance))
        
        # Sort by distance (closest first)
        results.sort(key=lambda x: x[1])
        return results
    
    def get_friendly_entities_near(self, center_position: tuple, range_tiles: int, 
                                 friendly_house_id: str, exclude_entity_id: str = None) -> List[tuple]:
        """
        Get friendly entities (same house) near a position.
        
        Args:
            center_position: Center position (q, r) to search around
            range_tiles: Maximum distance in hex tiles
            friendly_house_id: House ID to consider as friendly
            exclude_entity_id: Optional entity ID to exclude from results
            
        Returns:
            List of tuples: (entity, distance) of friendly entities sorted by distance
        """
        from feudal_sim.components.position import PositionComponent
        
        results = []
        positioned_entities = self.get_entities_with_component(PositionComponent)
        
        for entity in positioned_entities:
            # Skip excluded entity
            if exclude_entity_id and entity.id == exclude_entity_id:
                continue
                
            # Only include entities from the same house
            if not hasattr(entity, 'house_id') or entity.house_id != friendly_house_id:
                continue
            
            # Get entity position
            position_comp = entity.get_component(PositionComponent)
            if not position_comp or not position_comp.position:
                continue
            
            # Calculate distance
            distance = PositionComponent.hex_distance(center_position, position_comp.position)
            
            # Check if within range
            if distance <= range_tiles:
                results.append((entity, distance))
        
        # Sort by distance (closest first)
        results.sort(key=lambda x: x[1])
        return results
    
    def is_position_contested(self, position: tuple, check_range: int = 1) -> Dict[str, Any]:
        """
        Check if a position is contested (has entities from multiple houses nearby).
        
        Args:
            position: Position (q, r) to check
            check_range: Range to check for entities (default 1 tile)
            
        Returns:
            Dictionary with contest information:
            {
                'contested': bool,
                'houses_present': List[str],
                'entities_by_house': Dict[str, List[Entity]],
                'total_entities': int
            }
        """
        
        nearby_entities = self.get_positioned_entities_near(position, check_range)
        
        houses_present = set()
        entities_by_house = {}
        
        for entity, distance in nearby_entities:
            if hasattr(entity, 'house_id') and entity.house_id:
                house_id = entity.house_id
                houses_present.add(house_id)
                
                if house_id not in entities_by_house:
                    entities_by_house[house_id] = []
                entities_by_house[house_id].append(entity)
        
        return {
            'contested': len(houses_present) > 1,
            'houses_present': list(houses_present),
            'entities_by_house': entities_by_house,
            'total_entities': len(nearby_entities)
        }

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

    def get_entities_by_house_and_type(self, house_id: str, entity_type: str) -> List['Entity']:
        """Get entities by house and type using internal indexing."""
        typed = self._entities_by_type.get(entity_type, [])
        return [entity for entity in typed
                if hasattr(entity, 'house_id') and entity.house_id == house_id and entity.is_active()]
    
    def add_priority_action_event(self, event):
        """Add priority action event to simulation processor."""
        if hasattr(self, '_simulation_ref') and self._simulation_ref:
            self._simulation_ref.priority_processor.add_event(event)