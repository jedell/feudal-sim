from map.hex_grid import HexGrid

class MapManager:
    def __init__(self, width, height):
        self.hex_grid = HexGrid(width, height)

    def update_map(self):
        # Update the map based on house actions
        for (x, y), tile in self.hex_grid.tiles.items():
            # Placeholder: Add logic to update tiles (e.g., change ownership)
            pass

    def get_territory(self, x, y):
        # Get the territory (tile) at the given coordinates
        return self.hex_grid.get_tile(x, y)

    def allocate_territory(self, x, y, house):
        # Allocate a specific tile to a house
        self.hex_grid.set_tile_owner(x, y, house)
