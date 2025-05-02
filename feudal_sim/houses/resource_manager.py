from feudal_sim.map.types import HexResourceType
from feudal_sim.territories.territory import Territory

class ResourceManager:
    def __init__(self, houses):
        self.houses = houses

    def gather_resources(self, hex_grid):
        for house in self.houses:
            house.gather_resources(hex_grid)

    def update_resources(self, house_territories: dict[any, list[Territory]]):
        # Update resources for each house based on their territories
        for house, territories in house_territories.items():
            total_resources = sum(territory.generate_resources() for territory in territories)
            for resource_type, amount in total_resources.items():
                self.house_resources[resource_type][house] += amount

    def get_resources(self, house):
        # Return current resources for a specific house
        return self.house_resources.get(house, 0)
