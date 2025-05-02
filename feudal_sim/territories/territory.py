from map.hex_tile import HexTile
from map.types import HexResourceType

class Territory:
    def __init__(self, tiles: list[HexTile]):
        self.tiles = tiles
        self.current_population = 0

    def increase_population(self, amount):
        # Increase population in the territory, ensuring it doesn't exceed capacity
        self.current_population = min(self.current_population + amount, self.tile.support_population())

    def decrease_population(self, amount):
        # Decrease population in the territory
        self.current_population = max(self.current_population - amount, 0)

    def generate_resources(self) -> dict[HexResourceType, int]: 
        return self.tile.generate_resources()

    def get_owner(self):
        # Return the owner of this territory
        return self.tile.owner

    def set_owner(self, new_owner):
        # Change the owner of this territory
        self.tile.change_owner(new_owner)
