from typing import List

from feudal_sim.ai.tools import create_house_toolset
from feudal_sim.ai.tools import create_general_toolset


def get_tools_for_entity(entity, entity_type: str = 'house') -> List:
    """Return the toolset for the entity type using modular creators."""
    if entity_type == 'house':
        return create_house_toolset(entity)
    if entity_type == 'general':
        return create_general_toolset(entity)
    # Fallback to legacy for others (army/scout/caravan)
    try:
        from feudal_sim.ai.tools import get_tools_for_entity as _legacy_get
        return _legacy_get(entity, entity_type)
    except Exception:
        return [] 