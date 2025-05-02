import numpy as np
import math
from feudal_sim.map.types import Color
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.houses.observations.scout import gather_scout_data, make_scout
class House:
    def default_attributes(self):
        return {
            "resources": {"food": 100, "material": 100, "metal": 100, "gold": 100},
            "population": 100,
            "military_power": 0,
            "population_loyalty": 100
        }
    
    def get_dtype():
        return np.dtype([
            ('name', '|S50'),
            ('color', np.uint8, (4,)),
            ('food', np.float32),
            ('material', np.float32),
            ('metal', np.float32),
            ('population', np.int32),
            ('military_power', np.int32)
        ])
    
    def __init__(self, name, starting_attributes={}, color: Color = Color(0, 0, 0, 0)):
        self.name = name
        self.color = color
        self.territory = set()
        self.border_tiles = set()
        starting_attributes = self.default_attributes()
        self.resources = starting_attributes["resources"]
        self.population = starting_attributes["population"]
        self.military_power = starting_attributes["military_power"]
        self.population_capacity = self.get_population_capacity()
        self.population_loyalty = starting_attributes["population_loyalty"] 

        # observations per step
        self.observations = []
        self.scout = make_scout(self.name)

    def collect_observations(self, hex_grid, step_count: int):
        observation = {}

        observation['scout_report'] = []
        scout_data = gather_scout_data(self, hex_grid)
        for report in scout_data:
            report = self.scout(report).report
            observation['scout_report'].append(report)
            
        self.observations.append(observation)

    def manage_population(self):
        """Manage population based on resource availability."""
        # Calculate total food production
        total_food = self.resources['food']
        
        # Calculate population growth based on food availability
        population_growth = min(total_food // 2, self.population_capacity - self.population)
        
        # Update population
        self.population = min(self.population + population_growth, self.population_capacity)
        
        # Ensure population doesn't exceed capacity
        if self.population > self.population_capacity:
            self.population = self.population_capacity


        # Update population loyalty, grows slowly over time, decreases when resources are low
        self.population_loyalty = min(self.population_loyalty + 1, 100)
        if self.resources['food'] < 100:
            self.population_loyalty = max(self.population_loyalty - 1, 0)

        # Check if population loyalty is low
        if self.population_loyalty < 50:
            # Implement population revolt logic here
            print(f"{self.name} is experiencing a population revolt!")
            # Additional logic can be added, such as reducing military power, changing territory, etc.

    def population_efficiency(self, population_ratio):
        # as pop nears capacity, resources efficiency decreases
        return 1 + 1/math.exp(population_ratio)
        

    def gather_resources(self):
        """Gather resources based on the current population and territory outputs,
        enforcing a production cap based on population."""
        population_ratio = self.population / self.population_capacity
        efficiency = self.population_efficiency(population_ratio)
        for hex_tile in self.territory:
            self.resources['food'] = math.ceil(hex_tile.food_output * 10 * efficiency)
            self.resources['material'] = math.ceil(hex_tile.material_output * 10 * efficiency)
            self.resources['metal'] = math.ceil(hex_tile.metal_output * 10 * efficiency)

    def get_population_capacity(self):
        return sum([tile.population_capacity for tile in self.territory])

    def expand_territory(self, new_territory: list[HexTile], hex_grid):
        # Add new territory to the house's control
        self.territory.update(new_territory)
        self.population_capacity = self.get_population_capacity()
        for tile in new_territory:
            tile.set_owner(self)
            tile.owner_color = self.color
            neighbors = hex_grid.get_neighbors(tile.q, tile.r)
            for neighbor, _ in neighbors:
                if neighbor not in self.territory:
                    self.border_tiles.add(neighbor)

    def collect_taxes(self, tax_rate):
        if not (0 < tax_rate < 1):
            raise ValueError("Tax rate must be between 0 and 1")
        tax_collected = math.ceil(self.population * tax_rate)
        self.resources['gold'] += tax_collected
        # loyalty decreases with higher tax rate
        loyalty_decrease = math.ceil(tax_rate * 80)  # Higher tax rate leads to more loyalty decrease
        self.population_loyalty = max(0, self.population_loyalty - loyalty_decrease)

    def send_message(self, message: str, recipient: str):
        print(f"{self.name} sends a message to {recipient}: {message}")

    def raise_army(self, troop_type: str, quantity: int):
        """
        Raise an army by recruiting or training troops.

        Args:
            troop_type (str): The type of troops to raise.
            quantity (int): Number of troops to raise.
        """
        # Define resource costs per troop type
        troop_costs = {
            'infantry': {'food': 2, 'material': 1},
            'cavalry': {'food': 3, 'material': 2},
            'archers': {'food': 2, 'material': 2}
        }

        if troop_type not in troop_costs:
            raise ValueError(f"Invalid troop type: {troop_type}")

        cost = troop_costs[troop_type]
        total_food_cost = cost['food'] * quantity
        total_material_cost = cost['material'] * quantity

        if self.resources['food'] >= total_food_cost and self.resources['material'] >= total_material_cost:
            self.resources['food'] -= total_food_cost
            self.resources['material'] -= total_material_cost
            self.military_power += quantity  # Simplistic scaling
            print(f"{self.name} has raised {quantity} {troop_type} troops.")
        else:
            print(f"{self.name} does not have enough resources to raise {quantity} {troop_type} troops.")
