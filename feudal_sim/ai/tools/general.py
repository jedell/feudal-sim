from typing import List


def create_general_toolset(general_entity) -> List:
    """
    Temporary delegating wrapper for the general toolset.
    This preserves existing behavior while we incrementally migrate
    general tools into this module.
    """
    from feudal_sim.ai.tools import create_general_toolset as _legacy_create
    return _legacy_create(general_entity) 