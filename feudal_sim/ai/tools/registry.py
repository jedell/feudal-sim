from typing import List


def get_tools_for_entity(entity, entity_type: str = 'house') -> List:
    """
    Temporary delegating registry for tool selection.
    Preserves current behavior while we migrate tools to modular files.
    """
    from feudal_sim.ai.tools import get_tools_for_entity as _legacy_get
    return _legacy_get(entity, entity_type) 