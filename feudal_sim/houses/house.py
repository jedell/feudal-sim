import numpy as np
import math
from feudal_sim.map.types import Color
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.houses.observations.scout import gather_scout_data, make_scout
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.rookery import RookeryComponent
from feudal_sim.core.entities import Entity

class House(Entity):
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
    
    def __init__(self, name, starting_attributes={}, color: Color = Color(0, 0, 0, 0), known_recipients: list = None):
        # Initialize as Entity
        super().__init__(entity_id=name, name=name)
        
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
        
        # Store known recipients for component setup
        self.known_recipients = known_recipients or []
        
        # Add components using Entity system
        self._setup_components()
    
    def _setup_components(self):
        """Set up all components for this house entity."""
        # Add Rookery Component FIRST so it's available when AI component is initialized
        rookery_component = RookeryComponent(entity_id=self.id)
        self.add_component(rookery_component)
        
        # Set up known recipients immediately
        for recipient_name in self.known_recipients:
            if recipient_name != self.name:  # Don't add self as recipient
                rookery_component.add_known_recipient(recipient_name, recipient_name)
        
        # AI Component for intelligent decision making (added after rookery so tools work)
        ai_component = self._create_ai_component()
        self.add_component(ai_component)
    
    def _create_ai_component(self):
        """Create an AI component with personality based on house name."""
        personalities = {
            "Stark": "You are Lord Eddard Stark, honorable ruler of Winterfell. You value honor above all else, protect your family and the North, and are wary of southern politics. You make decisions based on duty and justice.",
            "Lannister": "You are Lord Tywin Lannister, cunning ruler of Casterly Rock. You are strategic, wealthy, and ruthless when necessary. You believe in the power of gold and legacy, making calculated decisions for House Lannister's advantage.",
            # Default personality for other houses
            "default": f"You are the Lord/Lady of House {self.name}. You are a capable ruler who must balance the needs of your people, resources, and territory while navigating the complex politics of the realm."
        }
        
        personality = personalities.get(self.name, personalities["default"])
        
        return AIComponent(
            name=f"Lord/Lady of House {self.name}",
            instructions=personality,
            entity_id=self.id
        )
    

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
        # Store old values
        old_population = self.population
        old_loyalty = self.population_loyalty
        
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

        # Add observations for AI component
        ai_component = self.get_component(AIComponent)
        if ai_component:
            if self.population != old_population:
                change = self.population - old_population
                if change > 0:
                    ai_component.add_observation(f"Your population grew by {change} people (now {self.population})", "Production")
                elif change < 0:
                    ai_component.add_observation(f"Your population decreased by {abs(change)} people (now {self.population})", "Production")
            
            if abs(self.population_loyalty - old_loyalty) > 0:
                if self.population_loyalty > old_loyalty:
                    ai_component.add_observation(f"Population loyalty increased to {self.population_loyalty}", "Production")
                else:
                    ai_component.add_observation(f"Population loyalty decreased to {self.population_loyalty}", "Production")

        # Check if population loyalty is low
        if self.population_loyalty < 50:
            # Implement population revolt logic here
            print(f"{self.name} is experiencing a population revolt!")
            if ai_component:
                ai_component.add_observation("Your people are on the brink of revolt due to low loyalty!", "Production")
            # Additional logic can be added, such as reducing military power, changing territory, etc.

    def population_efficiency(self, population_ratio):
        # as pop nears capacity, resources efficiency decreases
        return 1 + 1/math.exp(population_ratio)
        

    def gather_resources(self, seasonal_modifier=1.0):
        """Gather resources based on the current population and territory outputs,
        enforcing a production cap based on population."""
        # Store old values for event emission
        old_resources = dict(self.resources)
        
        population_ratio = self.population / self.population_capacity
        efficiency = self.population_efficiency(population_ratio)
        for hex_tile in self.territory:
            # Apply seasonal modifier to farming output
            food_modifier = seasonal_modifier if 'food' in ['food'] else 1.0
            gathering_multiplier = config.get('simulation.resources.gathering_multiplier')
            self.resources['food'] += math.ceil(hex_tile.food_output * gathering_multiplier * efficiency * food_modifier)
            self.resources['material'] += math.ceil(hex_tile.material_output * gathering_multiplier * efficiency)
            self.resources['metal'] += math.ceil(hex_tile.metal_output * gathering_multiplier * efficiency)
        
        # Add observations for AI component
        resource_changes = {}
        for resource_type in ['food', 'material', 'metal']:
            old_value = old_resources[resource_type]
            new_value = self.resources[resource_type]
            change = new_value - old_value
            if change > 0:
                resource_changes[resource_type] = change
        
        if resource_changes:
            # Create natural language observation for AI
            changes_text = ", ".join([f"+{amount} {resource}" for resource, amount in resource_changes.items()])
            ai_component = self.get_component(AIComponent)
            if ai_component:
                ai_component.add_observation(f"Your territories produced {changes_text} this turn", "Production")
        
        # Emit events for resource changes (makes system extensible)
        for resource_type in ['food', 'material', 'metal']:
            old_value = old_resources[resource_type]
            new_value = self.resources[resource_type]
            if new_value != old_value:
                event_bus.emit(
                    EventType.VALUE_CHANGED,
                    self,
                    entity_type='house',
                    entity_name=self.name,
                    property='resources',
                    resource_type=resource_type,
                    old_value=old_value,
                    new_value=new_value,
                    change=new_value - old_value
                )

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
    
    def make_ai_decisions(self, current_turn: int, current_phase: str, current_season: str, current_year: int):
        """
        Have the AI component make decisions for this house.
        Called during the Actions phase.
        
        Args:
            current_turn: Current turn number
            current_phase: Current phase name
            current_season: Current season name
            current_year: Current year
            
        Returns:
            String containing the AI's decisions
        """
        # Update AI context with current simulation state
        game_state = {
            'population': self.population,
            'population_capacity': self.population_capacity,
            'population_loyalty': self.population_loyalty,
            'resources': dict(self.resources),
            'military_power': self.military_power,
            'territory_size': len(self.territory)
        }
        
        ai_component = self.get_component(AIComponent)
        if not ai_component:
            return f"House {self.name} has no AI component"
        
        ai_component.update_context(
            current_turn=current_turn,
            current_phase=current_phase,
            current_season=current_season,
            current_year=current_year,
            game_state=game_state
        )
        
        # Make AI decisions
        return ai_component.make_decisions()
