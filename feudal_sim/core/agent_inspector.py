"""
AgentInspector — per-agent observability snapshot in POSIX shared memory.

Gives the renderer subprocess a live view into each AI agent: identity, a
one-line status summary, current objectives, and a formatted excerpt of the
recent chat history (observations, reasoning, tool calls, decisions).

Layout:
  Header (28 bytes):
    [0:4]    int32  num_agents
    [4:8]    int32  turn (week within year)
    [8:12]   int32  year
    [12:16]  int32  season_idx (0=spring .. 3=winter)
    [16:20]  int32  phase_idx (0=production, 1=actions, 2=events, 3=cleanup)
    [20:24]  int32  step_count
    [24:28]  int32  write_seq (monotonic; renderer uses it to detect updates)

  Per-agent slot (29578 bytes, MAX_AGENTS slots):
    char[64]     name
    char[16]     kind        ("house", "general", "scout", ...)
    char[50]     house_name
    uint8[4]     color
    char[256]    status      (one-line stats summary)
    char[512]    objectives  (newline-separated)
    int32        chat_len
    char[28672]  chat_text   (pre-formatted transcript excerpt)

Total: 28 + 12 * 29578 = 354,964 bytes.
"""

import struct
import multiprocessing.shared_memory as shm
from typing import Any, Dict, List, Optional

MAX_AGENTS = 12
NAME_SIZE = 64
KIND_SIZE = 16
HOUSE_SIZE = 50
STATUS_SIZE = 256
OBJECTIVES_SIZE = 512
CHAT_MAX = 28672

SLOT_SIZE = (
    NAME_SIZE + KIND_SIZE + HOUSE_SIZE + 4 + STATUS_SIZE + OBJECTIVES_SIZE + 4 + CHAT_MAX
)
HEADER_SIZE = 28
TOTAL_SIZE = HEADER_SIZE + MAX_AGENTS * SLOT_SIZE

# Offsets within a slot
_OFF_NAME = 0
_OFF_KIND = _OFF_NAME + NAME_SIZE
_OFF_HOUSE = _OFF_KIND + KIND_SIZE
_OFF_COLOR = _OFF_HOUSE + HOUSE_SIZE
_OFF_STATUS = _OFF_COLOR + 4
_OFF_OBJECTIVES = _OFF_STATUS + STATUS_SIZE
_OFF_CHAT_LEN = _OFF_OBJECTIVES + OBJECTIVES_SIZE
_OFF_CHAT = _OFF_CHAT_LEN + 4

SEASON_INDEX = {"spring": 0, "summer": 1, "autumn": 2, "winter": 3}
PHASE_INDEX = {"production": 0, "actions": 1, "events": 2, "cleanup": 3}

# How many recent messages to consider when building the chat excerpt
_CHAT_MESSAGE_WINDOW = 40


def _put_fixed(buf, offset: int, size: int, text: str) -> None:
    """Write a null-padded fixed-size string field."""
    encoded = text[: size - 1].encode("utf-8", errors="replace")
    buf[offset : offset + size] = encoded.ljust(size, b"\x00")


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text")
                if t:
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def format_chat_excerpt(
    messages: List[Dict[str, Any]], agent_name: str, budget: int = CHAT_MAX
) -> str:
    """Format recent message history into a display transcript.

    Walks newest-first so the excerpt always ends with the latest activity;
    prepends an omission marker when earlier history didn't fit.
    """
    window = messages[-_CHAT_MESSAGE_WINDOW:] if messages else []
    lines: List[str] = []
    used = 0
    truncated = len(messages) > len(window)

    for msg in reversed(window):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        msg_type = msg.get("type")

        if role == "user":
            block = f"── GAME MASTER ──\n{_content_to_text(msg.get('content'))}\n"
        elif role == "assistant":
            text = _content_to_text(msg.get("content"))
            if not text.strip():
                continue
            block = f"── {agent_name.upper()} ──\n{text}\n"
        elif msg_type == "function_call":
            name = msg.get("name", "?")
            args = _truncate(msg.get("arguments", ""), 140)
            block = f"→ {name}({args})\n"
        elif msg_type == "function_call_output":
            out = _truncate(msg.get("output", ""), 240)
            block = f"  ↳ {out}\n"
        elif msg_type == "reasoning":
            summaries = msg.get("summary", []) or []
            text = " ".join(
                s.get("text", "") for s in summaries if isinstance(s, dict)
            ).strip()
            if not text:
                continue
            block = f"💭 {_truncate(text, 240)}\n"
        else:
            continue

        if used + len(block) > budget:
            truncated = True
            break
        lines.append(block)
        used += len(block)

    lines.reverse()
    body = "\n".join(lines)
    if truncated:
        body = "… (earlier history omitted) …\n\n" + body
    return body


def collect_agent_snapshots(houses: List[Any], generals: List[Any]) -> List[Dict[str, Any]]:
    """Build inspector snapshot dicts for every entity carrying an AIComponent.

    Houses first (the lords), then generals. Entities without an initialized
    AI agent are skipped.
    """
    from feudal_sim.components.ai import AIComponent
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.subagent_group import SubAgentGroup

    snapshots: List[Dict[str, Any]] = []

    def _color_of(entity) -> tuple:
        try:
            c = entity.color
            return (c.r, c.g, c.b, c.a)
        except Exception:
            return (128, 128, 128, 255)

    for house in houses or []:
        ai = house.get_component(AIComponent)
        if not ai or not ai.is_enabled:
            continue
        status = ""
        res: ResourceComponent = house.get_component(ResourceComponent)
        pop: PopulationComponent = house.get_component(PopulationComponent)
        if res:
            r = res.resources
            status = (
                f"Food {r.food:.0f} · Material {r.material:.0f} · "
                f"Metal {r.metal:.0f} · Gold {r.gold:.0f}"
            )
        if pop:
            status += f"  |  Pop {pop.population} · Loyalty {pop.loyalty:.0f}%"
        snapshots.append({
            "name": ai.agent_name or house.name,
            "kind": "house",
            "house_name": house.name,
            "color": _color_of(house),
            "status": status,
            "objectives": "\n".join(ai.current_objectives or []),
            "chat": format_chat_excerpt(ai.messages, ai.agent_name or house.name),
        })

    for general in generals or []:
        ai = general.get_component(AIComponent)
        if not ai or not ai.is_enabled:
            continue
        grp: SubAgentGroup = general.get_component(SubAgentGroup)
        status = ""
        if grp:
            mission = grp.mission_parameters
            status = (
                f"{grp.assigned_population.soldiers} soldiers · "
                f"{grp.assigned_population.workers} workers  |  "
                f"Morale {grp.morale}% · Supplies {grp.supplies}%"
            )
            if mission:
                status += f"  |  Mission: {mission.mission_type}"
            if grp.active_route:
                status += f"  |  En route: {grp.active_route.get('purpose', '')}"
        house_name = ""
        try:
            em = ai.context.entity_manager if ai.context else None
            house_id = getattr(general, "house_id", None)
            parent = em.get_entity(house_id) if em and house_id else None
            house_name = getattr(parent, "name", "") if parent else ""
        except Exception:
            pass
        snapshots.append({
            "name": ai.agent_name or getattr(general, "name", "general"),
            "kind": "general",
            "house_name": house_name,
            "color": _color_of(general),
            "status": status,
            "objectives": "\n".join(ai.current_objectives or []),
            "chat": format_chat_excerpt(ai.messages, ai.agent_name or "general"),
        })

    return snapshots


class AgentInspector:
    """Shared-memory writer for per-agent observability data."""

    SHM_NAME = "psm_agents"

    def __init__(self):
        try:
            self._shm = shm.SharedMemory(name=self.SHM_NAME, create=True, size=TOTAL_SIZE)
        except FileExistsError:
            old = shm.SharedMemory(name=self.SHM_NAME, create=False, size=TOTAL_SIZE)
            old.unlink()
            old.close()
            self._shm = shm.SharedMemory(name=self.SHM_NAME, create=True, size=TOTAL_SIZE)
        self._shm.buf[:TOTAL_SIZE] = b"\x00" * TOTAL_SIZE
        self._write_seq = 0

    def write(
        self,
        agents: List[Dict[str, Any]],
        turn: int = 0,
        year: int = 1,
        season: str = "spring",
        phase: str = "production",
        step_count: int = 0,
    ) -> None:
        """Write a full snapshot. Each agent dict needs:
        name, kind, house_name, color (4-tuple 0-255), status, objectives, chat.
        """
        buf = self._shm.buf
        agents = agents[:MAX_AGENTS]

        self._write_seq += 1
        struct.pack_into("<i", buf, 0, len(agents))
        struct.pack_into("<i", buf, 4, int(turn))
        struct.pack_into("<i", buf, 8, int(year))
        struct.pack_into("<i", buf, 12, SEASON_INDEX.get(str(season).lower(), 0))
        struct.pack_into("<i", buf, 16, PHASE_INDEX.get(str(phase).lower(), 0))
        struct.pack_into("<i", buf, 20, int(step_count))
        struct.pack_into("<i", buf, 24, self._write_seq)

        for i, agent in enumerate(agents):
            base = HEADER_SIZE + i * SLOT_SIZE
            _put_fixed(buf, base + _OFF_NAME, NAME_SIZE, str(agent.get("name", "")))
            _put_fixed(buf, base + _OFF_KIND, KIND_SIZE, str(agent.get("kind", "")))
            _put_fixed(buf, base + _OFF_HOUSE, HOUSE_SIZE, str(agent.get("house_name", "")))
            color = agent.get("color") or (128, 128, 128, 255)
            struct.pack_into("<4B", buf, base + _OFF_COLOR, *[int(c) & 0xFF for c in color][:4])
            _put_fixed(buf, base + _OFF_STATUS, STATUS_SIZE, str(agent.get("status", "")))
            _put_fixed(
                buf, base + _OFF_OBJECTIVES, OBJECTIVES_SIZE, str(agent.get("objectives", ""))
            )
            chat = str(agent.get("chat", ""))
            chat_bytes = chat[: CHAT_MAX - 1].encode("utf-8", errors="replace")
            struct.pack_into("<i", buf, base + _OFF_CHAT_LEN, len(chat_bytes))
            end = base + _OFF_CHAT + len(chat_bytes)
            buf[base + _OFF_CHAT : end] = chat_bytes
            buf[end : base + _OFF_CHAT + CHAT_MAX] = b"\x00" * (CHAT_MAX - len(chat_bytes))

    def close(self) -> None:
        try:
            self._shm.close()
            self._shm.unlink()
        except Exception:
            pass
