"""
WarRegistry — tracks formal war declarations between houses.

Wars are symmetric: if A declares war on B, both are at war with each other.
"""

from typing import Set, FrozenSet, List, Tuple


class WarRegistry:
    def __init__(self):
        self._wars: Set[FrozenSet[str]] = set()

    def declare_war(self, house_a: str, house_b: str) -> bool:
        """Returns False if already at war."""
        key = frozenset({house_a, house_b})
        if key in self._wars:
            return False
        self._wars.add(key)
        return True

    def sue_for_peace(self, house_a: str, house_b: str) -> bool:
        """Returns False if not at war."""
        key = frozenset({house_a, house_b})
        if key not in self._wars:
            return False
        self._wars.discard(key)
        return True

    def at_war(self, house_a: str, house_b: str) -> bool:
        return frozenset({house_a, house_b}) in self._wars

    def get_enemies(self, house_id: str) -> List[str]:
        return [list(pair - {house_id})[0] for pair in self._wars if house_id in pair]

    def enemy_count(self, house_id: str) -> int:
        return sum(1 for pair in self._wars if house_id in pair)

    def all_wars(self) -> List[Tuple[str, str]]:
        return [tuple(pair) for pair in self._wars]  # type: ignore[return-value]
