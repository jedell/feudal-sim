import random
import dspy

lm = dspy.LM(model="openai/gpt-4o-mini", cache=False)
dspy.configure(lm=lm)

SCOUT_STEPS = 10
NUM_SCOUTS = 3

def make_scout(house_name: str):

    scout = dspy.make_signature(
        signature="raw_data -> report",
        instructions="""
        You are a scout for House {house_name}.
        You are tasked with exploring the surrounding area and reporting on the state of the land.
        You will be given raw data collected from a series of tiles you have scouted.
        You must parse this data and summarize your findings into a concise report for your lord.
        """.format(house_name=house_name),
        signature_name="House {house_name} Scout".format(house_name=house_name)
    )
    return dspy.Predict(scout)

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
            print(f"{house.name} has no border tiles to deploy scouts from.")
            break

        # Randomly select a border tile as the starting point
        start_tile = random.choice(list(border_tiles))

        # Perform a random walk and collect data
        walk_data = perform_random_walk(hex_grid, start_tile)
        scout_reports[f"scout_{i}"].extend(walk_data)

    return scout_reports