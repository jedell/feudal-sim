from typing import Tuple, List

# Axial neighbor deltas to direction codes
_DELTA_TO_DIR = {
    (0, -1): "N",
    (1, -1): "NE",
    (1, 0): "SE",
    (0, 1): "S",
    (-1, 1): "SW",
    (-1, 0): "NW",
}

# Direction code to prose mapping
_DIR_TO_PROSE = {
    "N": "north",
    "NE": "northeast",
    "SE": "southeast",
    "S": "south",
    "SW": "southwest",
    "NW": "northwest",
    "CENTER": "here",
}


def neighbor_delta_to_dir(delta: Tuple[int, int]) -> str:
    """Map an axial neighbor delta (dq, dr) to a direction code (N, NE, SE, S, SW, NW)."""
    return _DELTA_TO_DIR.get(delta)


def offset_to_bearing(dq: float, dr: float) -> str:
    """Snap an arbitrary axial offset to the nearest of the grid's six
    directions (N, NE, SE, S, SW, NW) by cosine similarity in cartesian
    space — keeps all bearing language consistent with movement directions."""
    import math
    x, y = dq + dr / 2.0, dr * 0.866
    norm = math.hypot(x, y)
    if norm < 1e-9:
        return "CENTER"
    best_dir, best_cos = "N", -2.0
    for (ddq, ddr), code in _DELTA_TO_DIR.items():
        ux, uy = ddq + ddr / 2.0, ddr * 0.866
        unorm = math.hypot(ux, uy)
        cos = (x * ux + y * uy) / (norm * unorm)
        if cos > best_cos:
            best_cos, best_dir = cos, code
    return best_dir


def dir_code_to_prose(code: str) -> str:
    """Convert a direction code (e.g., 'NE') to prose ('northeast')."""
    return _DIR_TO_PROSE.get(code, code.lower())


def join_directions_prose(directions: List[str]) -> str:
    """Join a list of direction prose words into a natural string ("north and northeast")."""
    if not directions:
        return ""
    if len(directions) == 1:
        return directions[0]
    if len(directions) == 2:
        return f"{directions[0]} and {directions[1]}"
    return ", ".join(directions[:-1]) + f" and {directions[-1]}" 