from typing import List, Dict

from feudal_sim.utils.directions import dir_code_to_prose, join_directions_prose


class ObservationFormatter:
    """Formats observation events into human-readable prose strings."""
    @staticmethod
    def movement_single_step(direction_code: str, remaining_mp: int) -> str:
        direction = dir_code_to_prose(direction_code)
        return f"Moved one tile {direction} — {remaining_mp} movement points remain"

    @staticmethod
    def movement_multi_step(distance: int, remaining_mp: int) -> str:
        return f"Moved {distance} tiles — {remaining_mp} movement points remain"

    @staticmethod
    def borders_summary(ours: List[str], unowned: List[str], others: Dict[str, List[str]]) -> str:
        parts = []
        if ours:
            parts.append(f"our territory to {join_directions_prose(ours)}")
        if unowned:
            parts.append(f"unclaimed to {join_directions_prose(unowned)}")
        for house, dirs in others.items():
            if dirs:
                parts.append(f"{house} to {join_directions_prose(dirs)}")
        if not parts:
            return "no adjacent claimed borders"
        return "; ".join(parts)

    @staticmethod
    def units_summary(friendly_dirs: List[str], enemy_dirs: List[str]) -> str:
        parts = []
        if friendly_dirs:
            parts.append(f"friendly units: {len(friendly_dirs)} ({', '.join(friendly_dirs[:3])})")
        if enemy_dirs:
            parts.append(f"enemy units: {len(enemy_dirs)} ({', '.join(enemy_dirs[:3])})")
        return " | ".join(parts) if parts else ""

    @staticmethod
    def settlement_result(count: int) -> str:
        if count <= 0:
            return "No unowned tiles within range to settle"
        return f"Settled {count} nearby tiles"

    @staticmethod
    def raven_received(sender_name: str, message: str) -> str:
        return f"📜 A raven arrived from {sender_name}: '{message}'"

    @staticmethod
    def raven_delivered(recipient_name: str) -> str:
        return f"📜 Your raven to {recipient_name} was delivered" 