"""
Shared helpers for AI tool factories.

These utilities are extracted from patterns that were duplicated verbatim across
the tool factory functions. They are pure helpers only — no tool docstrings or
LLM-facing return strings live here.
"""


def _balance_line(resource_component, keys: list) -> str:
    """Return 'Remaining: X food, Y gold.' for the listed resource keys."""
    parts = [f"{resource_component.resources.get(k):.0f} {k}" for k in keys]
    return "Remaining: " + ", ".join(parts) + "."


def hex_distance(a: tuple, b: tuple) -> int:
    """Axial hex distance between two (q, r) coordinate tuples."""
    aq, ar = a
    bq, br = b
    return (abs(aq - bq) + abs(ar - br) + abs((-aq - ar) - (-bq - br))) // 2
