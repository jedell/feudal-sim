"""
IntelligenceComponent - Simple agent notebook / compendium.

Acts as a lightweight read/write store for an agent's writings, notes, and thoughts.
Provides simple APIs to add/read/list topics, while keeping backward-compatibility
with the previous neighbor-intelligence interface used elsewhere in the codebase.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.components.territory import TerritoryComponent


@dataclass
class Note:
    """A single dated intelligence note stored in the compendium."""
    topic: str
    text: str
    turn: Optional[int] = None


class IntelligenceComponent(Component):
    """
    Agent notebook / compendium for storing notes by topic.

    Primary usage:
    - add_note(topic, text, turn=None)
    - read_topic(topic) -> str
    - list_topics() -> List[str]
    - read_all_summaries() -> str

    Backward compatibility:
    - add_neighbor/get_neighbors: retained as no-ops for legacy callers
    - generate_initial_intelligence: creates placeholder notes about other houses
    - format_intelligence_report/format_all_intelligence_summary: map to note reads
    """

    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        # Notes stored as topic -> list of Note
        self._notes: Dict[str, List[Note]] = {}
        # Legacy neighbor list (kept for compatibility)
        self.neighbor_names: List[str] = []

    # ---- Core note APIs ----
    def add_note(self, topic: str, text: str, turn: Optional[int] = None):
        if not topic:
            return
        self._notes.setdefault(topic, []).append(Note(topic=topic, text=text, turn=turn))

    def read_topic(self, topic: str) -> str:
        entries = self._notes.get(topic, [])
        if not entries:
            return f"No notes recorded for '{topic}'."
        lines = []
        for n in entries:
            if n.turn is not None:
                lines.append(f"[Turn {n.turn}] {n.text}")
            else:
                lines.append(n.text)
        return "\n".join(lines)

    def list_topics(self) -> List[str]:
        return list(self._notes.keys())

    def read_all_summaries(self) -> str:
        if not self._notes:
            return "No notes recorded."
        lines = ["═══ COMPENDIUM NOTES ═══\n"]
        for topic, entries in self._notes.items():
            preview = entries[-1].text if entries else ""
            lines.append(f"• {topic}: {preview[:80]}")
        return "\n".join(lines)

    # ---- Convenience alias for legacy API (tools may call update_notes) ----
    def update_notes(self, topic: str, notes: str):
        self.add_note(topic, notes)

    # ---- Legacy neighbor/intelligence shims ----
    def add_neighbor(self, neighbor_name: str):
        self.neighbor_names.append(neighbor_name)

    def get_neighbors(self) -> List[str]:
        return self.neighbor_names

    def _get_our_territory_center(self) -> Tuple[float, float]:
        territory_component = self.entity.get_component(TerritoryComponent)
        if not territory_component or not territory_component.territory:
            return (0.0, 0.0)
        total_q = sum(tile.q for tile in territory_component.territory)
        total_r = sum(tile.r for tile in territory_component.territory)
        return (total_q / len(territory_component.territory), total_r / len(territory_component.territory))

    def generate_initial_intelligence(self, all_houses: List):
        """Compatibility: create minimal placeholder notes about other houses."""
        our_name = self.entity.name if self.entity else self.entity_id
        for house in all_houses:
            if house.get_name() == our_name:
                continue
            topic = f"House {house.get_name()}"
            self.add_note(topic, "Initial contact recorded.")

    # Legacy-format helpers mapped to the new store
    def format_intelligence_report(self, house_name: str) -> str:
        topic = f"House {house_name}" if house_name else house_name
        return self.read_topic(topic)

    def format_all_intelligence_summary(self) -> str:
        return self.read_all_summaries()

    def get_lore_section(self) -> str:
        return """
**The Compendium:**
Your private compendium records thoughts, plans, and observations. Add entries under any topic
(e.g., neighboring houses, military plans, diplomacy) and consult them later. A disciplined record
keeps your strategy sharp across the changing tides of the realm.
"""

    def update(self, dt: float, event_bus=None):
        """Component update - not currently used."""
        pass