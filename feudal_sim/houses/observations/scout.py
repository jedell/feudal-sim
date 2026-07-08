import random

SCOUT_STEPS = 10
NUM_SCOUTS = 3

class ScoutReport:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self.report = self._generate_report()
    
    def _generate_report(self):
        if not self.raw_data:
            return "Scouts report: No tiles explored."

        total = len(self.raw_data)

        # Count terrain types
        terrain_counts = {}
        for tile in self.raw_data:
            terrain = tile.get("terrain_type", "unknown").lower().replace("_", " ")
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1

        sorted_terrains = sorted(terrain_counts.items(), key=lambda kv: kv[1], reverse=True)
        primary = sorted_terrains[0][0]
        if len(sorted_terrains) > 1:
            secondary = sorted_terrains[1][0]
            terrain_summary = f"mostly {primary} and {secondary}"
        else:
            terrain_summary = f"mostly {primary}"

        # Ownership
        unowned = [t for t in self.raw_data if t.get("owner") in (None, "None", "")]
        foreign: dict = {}
        for tile in self.raw_data:
            owner = tile.get("owner")
            if owner and owner != "None":
                foreign[owner] = foreign.get(owner, 0) + 1

        # Military presence
        military_tiles = [t for t in self.raw_data if t.get("military_presence", 0) > 0]

        parts = [f"Scouts report: {total} tiles explored — {terrain_summary}."]

        if unowned:
            parts.append(f"{len(unowned)} tiles unowned (expansion opportunities).")
        dir_prose = {"N": "north", "NE": "northeast", "SE": "southeast",
                     "S": "south", "SW": "southwest", "NW": "northwest"}
        for owner_name, count in foreign.items():
            # Get direction hints if available
            owner_tiles = [t for t in self.raw_data if t.get("owner") == owner_name]
            directions = list({t.get("direction", "").upper() for t in owner_tiles if t.get("direction")})
            dir_text = f" to the {dir_prose.get(directions[0], directions[0].lower())}" if len(directions) == 1 else ""
            parts.append(f"{count} tiles owned by {owner_name}{dir_text}.")
        if military_tiles:
            parts.append(f"Military presence detected on {len(military_tiles)} tile(s).")
        else:
            parts.append("No military presence detected.")

        return " ".join(parts)

def make_scout(house_name: str):
    def scout_function(raw_data):
        return ScoutReport(raw_data)
    return scout_function

# utils

def perform_random_walk(hex_grid, start_tile, steps: int = SCOUT_STEPS):
    """
    Simulate a scout performing a random walk across the hex grid.

    Args:
        hex_grid (HexGrid): The hex grid of the simulation.
        start_tile (HexTile): The starting tile for the scout.
        steps (int): Number of steps the scout will take.

    Returns:
        list of dict: Collected data from each tile visited.
    """
    current_tile = start_tile
    data_collected = []

    for _ in range(steps):
        neighbors = list(hex_grid.get_neighbors(current_tile.q, current_tile.r))
        if not neighbors:
            break  # No more tiles to move to

        # Randomly choose the next tile to move to
        next_tile, direction = random.choice(neighbors)
        current_tile = next_tile

        # Collect data from the current tile
        data = {
            "direction": direction,
            "terrain_type": current_tile.terrain_type.name,
            "owner": current_tile.owner.name if current_tile.owner else "None",
            "military_presence": getattr(current_tile, 'military_strength', 0)
        }
        data_collected.append(data)

    return data_collected


def get_border_tiles(house):
    """
    Retrieve border tiles of the house's territory.

    Args:
        house (House): The house whose border tiles are to be retrieved.

    Returns:
        list of HexTile: Border tiles.
    """
    return house.border_tiles


def gather_scout_data(house, hex_grid):
    """
    Dispatch N scouts to perform random walks and gather data.

    Args:
        house (House): The house dispatching scouts.
        hex_grid (HexGrid): The hex grid of the simulation.

    Returns:
        list of dict: Aggregated scout data.
    """
    scout_reports = {
        f"scout_{i}": [] for i in range(NUM_SCOUTS)
    }
    border_tiles = get_border_tiles(house)

    for i in range(NUM_SCOUTS):
        if not border_tiles:
            print(f"{house.get_name()} has no border tiles to deploy scouts from.")
            break

        # Randomly select a border tile as the starting point
        start_tile = random.choice(list(border_tiles))

        # Perform a random walk and collect data
        walk_data = perform_random_walk(hex_grid, start_tile)
        scout_reports[f"scout_{i}"].extend(walk_data)

    return scout_reports