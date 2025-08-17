from dataclasses import dataclass, field
from typing import Dict, Any, List
import uuid


@dataclass
class DeferredAction:
    id: str
    action_type: str
    payload: Dict[str, Any]
    scheduled_turn: int
    phase: str = "Events"  # Which phase to run in
    owner_id: str | None = None


class DeferredActionQueue:
    def __init__(self):
        self._actions: List[DeferredAction] = []

    def schedule_at(self, turn: int, action_type: str, payload: Dict[str, Any], phase: str = "Events", owner_id: str | None = None) -> str:
        action_id = str(uuid.uuid4())
        self._actions.append(DeferredAction(action_id, action_type, payload, turn, phase, owner_id))
        return action_id

    def schedule_in(self, current_turn: int, turns_from_now: int, action_type: str, payload: Dict[str, Any], phase: str = "Events", owner_id: str | None = None) -> str:
        return self.schedule_at(current_turn + max(0, int(turns_from_now)), action_type, payload, phase, owner_id)

    def pop_due(self, current_turn: int, phase: str) -> List[DeferredAction]:
        due: List[DeferredAction] = []
        remaining: List[DeferredAction] = []
        for a in self._actions:
            if a.scheduled_turn <= current_turn and a.phase == phase:
                due.append(a)
            else:
                remaining.append(a)
        self._actions = remaining
        return due

    def cancel(self, action_id: str) -> bool:
        before = len(self._actions)
        self._actions = [a for a in self._actions if a.id != action_id]
        return len(self._actions) != before 