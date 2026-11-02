"""
Token-aware message compaction with LLM summarization.

Replaces the naive message-count-based truncation with a proper compaction
pipeline modeled after modern agent harnesses (Pi, Claude Code, etc.):

1. Estimate token usage per message (chars/4 heuristic)
2. Compact when estimated tokens exceed (context_window - reserve_tokens)
3. Find a clean cut point that keeps ~keep_recent_tokens of recent context
4. Send dropped messages to a separate LLM call for structured summarization
5. Maintain a rolling summary that gets updated (not replaced) each compaction
6. Insert the summary as a system-level context message in the retained history
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from feudal_sim.core.config import config

log = logging.getLogger(__name__)

# ── Token estimation ──────────────────────────────────────────────────────────

CHARS_PER_TOKEN = 4  # conservative heuristic


def estimate_tokens_for_message(msg: Dict[str, Any]) -> int:
    """Estimate token count for a single message dict.

    Handles the OpenAI Agents SDK message types:
    - {role: user/assistant, content: str}
    - {type: function_call, call_id, name, arguments}
    - {type: function_call_output, call_id, output}
    - {type: reasoning, summary: [{text}]}
    - {role: tool, tool_call_id, content}
    """
    chars = 0

    msg_type = msg.get("type")
    role = msg.get("role")

    if role == "user" or role == "assistant":
        content = msg.get("content", "")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        chars += len(block.get("text", ""))
                    elif block.get("type") == "image":
                        chars += 4800  # rough image estimate
                elif isinstance(block, str):
                    chars += len(block)

    elif msg_type == "function_call":
        chars += len(msg.get("name", ""))
        chars += len(msg.get("arguments", ""))

    elif msg_type == "function_call_output":
        output = msg.get("output", "")
        chars += len(str(output))

    elif msg_type == "reasoning":
        for summary in msg.get("summary", []):
            if isinstance(summary, dict):
                chars += len(summary.get("text", ""))

    elif role == "tool":
        content = msg.get("content", "")
        chars += len(str(content))

    else:
        # Fallback: serialize the whole thing
        try:
            chars += len(json.dumps(msg))
        except (TypeError, ValueError):
            chars += 100  # arbitrary fallback

    return max(1, (chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def estimate_total_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens across a message list."""
    return sum(estimate_tokens_for_message(m) for m in messages)


# ── Cut-point selection ──────────────────────────────────────────────────────


def _is_user_boundary(msg: Dict[str, Any]) -> bool:
    """Return True if this message is a safe place to start kept history."""
    return msg.get("role") == "user"


def find_cut_point(
    messages: List[Dict[str, Any]],
    keep_recent_tokens: int,
) -> int:
    """Find the index where kept history should start.

    Walks backwards from the end, accumulating tokens, until we've covered
    approximately keep_recent_tokens. Then snaps forward to the nearest user
    message boundary so we never start mid-turn (orphaned function_call_output
    or reasoning items cause OpenAI 400 errors).

    Returns the index of the first message to keep.
    """
    if not messages:
        return 0

    # Find the token budget cut point walking backwards
    accumulated = 0
    budget_index = len(messages)  # default: keep everything

    for i in range(len(messages) - 1, -1, -1):
        tokens = estimate_tokens_for_message(messages[i])
        accumulated += tokens
        if accumulated >= keep_recent_tokens:
            budget_index = i
            break

    if budget_index >= len(messages):
        return 0

    # Snap forward to the nearest user message boundary
    for i in range(budget_index, len(messages)):
        if _is_user_boundary(messages[i]):
            return i

    # If no user message found, keep from budget_index anyway
    # (shouldn't happen in practice)
    return budget_index


# ── Compaction decision ──────────────────────────────────────────────────────


@dataclass
class CompactionSettings:
    """Configuration for the compaction system."""

    enabled: bool = True
    context_window: int = 128_000
    reserve_tokens: int = 8_000
    keep_recent_tokens: int = 20_000
    max_output_tokens: int = 2_000

    @classmethod
    def from_config(cls, agent_type: str = "") -> "CompactionSettings":
        """Build settings from simulation config, with per-agent-type overrides."""
        prefix = "simulation.ai.compaction"
        agent_prefix = f"{prefix}.{agent_type}" if agent_type else ""

        def _get(key: str, default: Any) -> Any:
            # Try agent-specific override first, then global
            if agent_prefix:
                try:
                    val = config.get(f"{agent_prefix}.{key}")
                    if val is not None:
                        return val
                except KeyError:
                    pass
            try:
                return config.get(f"{prefix}.{key}", default)
            except KeyError:
                return default

        return cls(
            enabled=_get("enabled", True),
            context_window=_get("context_window", 128_000),
            reserve_tokens=_get("reserve_tokens", 8_000),
            keep_recent_tokens=_get("keep_recent_tokens", 20_000),
            max_output_tokens=_get("max_output_tokens", 2_000),
        )


def should_compact(
    messages: List[Dict[str, Any]],
    settings: CompactionSettings,
) -> bool:
    """Return True if the message history should be compacted."""
    if not settings.enabled:
        return False
    total = estimate_total_tokens(messages)
    threshold = settings.context_window - settings.reserve_tokens
    return total > threshold


# ── Summarization prompts ────────────────────────────────────────────────────

SUMMARIZATION_SYSTEM = (
    "You are a context summarization assistant. Your task is to read a conversation "
    "between a game master and an AI agent in a feudal simulation, then produce a "
    "structured summary following the exact format specified.\n\n"
    "Do NOT continue the conversation. Do NOT respond to any questions in the "
    "conversation. ONLY output the structured summary."
)

SUMMARIZATION_PROMPT = """\
The messages above are a conversation to summarize. Create a structured context \
checkpoint summary that the AI agent will use to continue making decisions.

Use this EXACT format:

## Agent Identity & Role
[Who is this agent? What is their role, house, and persona?]

## Strategic Objectives
- [Current goals and priorities the agent has set]

## Key Decisions & Actions Taken
- [x] [Completed actions with outcomes]

## Current State
- [Resources, territory, population, military status]
- [Any active missions, routes, or deployments]

## Critical Intelligence
- [Key facts learned: enemy positions, threats, opportunities, alliances]

## Relationships & Diplomacy
- [Status with other houses: wars, truces, trade agreements]

## Immediate Priorities
1. [What the agent should focus on next]

Keep each section concise. Preserve exact numbers, place names, and house names.\
"""

UPDATE_SUMMARIZATION_PROMPT = """\
The messages above are NEW conversation messages to incorporate into the existing \
summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new decisions, intelligence, and state changes from the new messages
- UPDATE the Current State section with the latest resource/territory numbers
- UPDATE Immediate Priorities based on what was accomplished
- PRESERVE exact numbers, place names, and house names
- If something is no longer relevant (e.g. a completed mission), remove it

Use this EXACT format:

## Agent Identity & Role
[Preserve from previous]

## Strategic Objectives
- [Preserve existing, add new, remove completed]

## Key Decisions & Actions Taken
- [x] [Include previously done items AND newly completed items]

## Current State
- [Update with latest numbers]

## Critical Intelligence
- [Preserve important, add new, remove stale]

## Relationships & Diplomacy
- [Update based on recent events]

## Immediate Priorities
1. [Update based on current state]

Keep each section concise. Preserve exact numbers, place names, and house names.\
"""


def _serialize_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
    """Convert message dicts to a readable text format for the summarizer LLM."""
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        msg_type = msg.get("type", "")

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(f"[Game Master]: {content}")
            elif isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                parts.append(f"[Game Master]: {' '.join(texts)}")

        elif role == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(f"[Agent]: {content}")
            elif isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if texts:
                    parts.append(f"[Agent]: {' '.join(texts)}")

        elif msg_type == "function_call":
            name = msg.get("name", "?")
            args = msg.get("arguments", "")
            parts.append(f"[Action]: {name}({args})")

        elif msg_type == "function_call_output":
            output = str(msg.get("output", ""))
            # Truncate long outputs for the summarizer
            if len(output) > 500:
                output = output[:500] + "..."
            parts.append(f"[Result]: {output}")

        elif msg_type == "reasoning":
            summaries = msg.get("summary", [])
            texts = [
                s.get("text", "") for s in summaries
                if isinstance(s, dict)
            ]
            if texts:
                combined = " ".join(texts)
                if len(combined) > 300:
                    combined = combined[:300] + "..."
                parts.append(f"[Thinking]: {combined}")

    return "\n".join(parts)


# ── Main compaction pipeline ─────────────────────────────────────────────────


@dataclass
class CompactionResult:
    """Result of a compaction run."""

    summary: str
    tokens_before: int
    tokens_after: int
    messages_dropped: int
    messages_kept: int


async def compact_messages(
    messages: List[Dict[str, Any]],
    settings: CompactionSettings,
    model: Any = None,
    previous_summary: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], CompactionResult]:
    """Compact a message history, returning (new_messages, result).

    The returned message list has the summary injected as a system message
    after the first system message, followed by the retained recent messages.

    Args:
        messages: Full message history (including system prompt at [0])
        settings: Compaction configuration
        model: Optional LLM model for summarization (uses agents SDK).
               If None, falls back to naive extraction.
        previous_summary: Rolling summary from previous compaction.

    Returns:
        Tuple of (new_message_list, CompactionResult)
    """
    tokens_before = estimate_total_tokens(messages)

    # Separate system message from conversation
    system_msg = None
    conversation = messages
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        system_msg = messages[0]
        conversation = messages[1:]

    # Find cut point
    cut_index = find_cut_point(conversation, settings.keep_recent_tokens)
    dropped = conversation[:cut_index]
    kept = conversation[cut_index:]

    if not dropped:
        # Nothing to compact
        return messages, CompactionResult(
            summary=previous_summary or "",
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            messages_dropped=0,
            messages_kept=len(messages),
        )

    # Generate summary
    if model is not None:
        summary = await _llm_summarize(dropped, model, settings, previous_summary)
    else:
        summary = _naive_summarize(dropped, previous_summary)

    # Build new message list: system + summary + kept
    new_messages = []
    if system_msg:
        new_messages.append(system_msg)

    # Inject summary as a system-level context message
    summary_content = f"[Prior Context Summary]\n{summary}"
    new_messages.append({"role": "user", "content": summary_content})

    new_messages.extend(kept)

    # Clean up orphaned tool responses at the boundary
    new_messages = _remove_orphaned_tool_outputs(new_messages)

    tokens_after = estimate_total_tokens(new_messages)

    result = CompactionResult(
        summary=summary,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_dropped=len(dropped),
        messages_kept=len(kept),
    )

    log.info(
        f"📦 Compacted: {tokens_before:,} → {tokens_after:,} tokens "
        f"({len(dropped)} dropped, {len(kept)} kept, "
        f"summary {estimate_tokens_for_message({'role': 'user', 'content': summary}):,} tokens)"
    )

    return new_messages, result


async def _llm_summarize(
    dropped_messages: List[Dict[str, Any]],
    model: Any,
    settings: CompactionSettings,
    previous_summary: Optional[str] = None,
) -> str:
    """Generate a structured summary using an LLM call."""
    try:
        from agents import Agent, Runner

        conversation_text = _serialize_messages_for_summary(dropped_messages)

        prompt = f"<conversation>\n{conversation_text}\n</conversation>\n\n"
        if previous_summary:
            prompt += f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
            prompt += UPDATE_SUMMARIZATION_PROMPT
        else:
            prompt += SUMMARIZATION_PROMPT

        summarizer = Agent(
            name="compaction-summarizer",
            instructions=SUMMARIZATION_SYSTEM,
            model=model,
        )

        result = await Runner.run(
            starting_agent=summarizer,
            input=[{"role": "user", "content": prompt}],
            max_turns=1,
        )

        return result.final_output or _naive_summarize(dropped_messages, previous_summary)

    except Exception as e:
        log.warning(f"LLM summarization failed, falling back to naive: {e}")
        return _naive_summarize(dropped_messages, previous_summary)


def _naive_summarize(
    dropped_messages: List[Dict[str, Any]],
    previous_summary: Optional[str] = None,
) -> str:
    """Fallback: extract key actions without LLM. Used when LLM is unavailable."""
    actions = []
    for msg in dropped_messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "function_call":
            name = msg.get("name", "")
            if name and name not in ("end_turn", "write_compendium", "read_compendium"):
                args_str = msg.get("arguments", "")
                # Truncate long args
                if len(args_str) > 100:
                    args_str = args_str[:100] + "..."
                actions.append(f"{name}({args_str})")

    parts = []
    if previous_summary:
        parts.append(f"[Previous context]\n{previous_summary}")
    if actions:
        parts.append(f"[Actions taken]\n" + "\n".join(f"- {a}" for a in actions[:20]))

    return "\n\n".join(parts) if parts else "No prior context."


def _remove_orphaned_tool_outputs(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove function_call_output / tool messages whose call was dropped."""
    # Collect all function_call IDs present
    call_ids = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "function_call":
            cid = msg.get("call_id")
            if cid:
                call_ids.add(cid)
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict) and tc.get("id"):
                call_ids.add(tc["id"])

    # Remove orphaned outputs
    cleaned = []
    for msg in messages:
        if isinstance(msg, dict):
            msg_type = msg.get("type")
            if msg_type == "function_call_output":
                if msg.get("call_id") not in call_ids:
                    continue
            elif msg.get("role") == "tool":
                if msg.get("tool_call_id") not in call_ids:
                    continue
        cleaned.append(msg)

    return cleaned
