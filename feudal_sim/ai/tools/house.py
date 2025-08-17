from typing import List


def create_house_toolset(house_entity) -> List:
    """
    Temporary delegating wrapper for the house toolset.
    This preserves existing behavior while we incrementally migrate
    house tools into this module.
    """
    from feudal_sim.ai.tools import create_house_toolset as _legacy_create
    return _legacy_create(house_entity) 