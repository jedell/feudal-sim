import numpy as np
import math
from feudal_sim.map.types import Color
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.houses.observations.scout import gather_scout_data, make_scout
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.rookery import RookeryComponent
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.core.entities import Entity
from feudal_sim.ai.prompts import HOUSE_LEADER_INSTRUCTIONS

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
        # Territory now handled by TerritoryComponent
        starting_attributes = self.default_attributes()
        # Resources now handled by ResourceComponent
        # Population now handled by PopulationComponent
        self.military_power = starting_attributes["military_power"] 

        # observations per step
        self.observations = []
        self.scout = make_scout(self.name)
        
        # Store known recipients for component setup
        self.known_recipients = known_recipients or []
        
        # Add components using Entity system
        self._setup_components()
    
    @property
    def resources(self):
        """Backward compatibility property for accessing resources."""
        resource_component = self.get_component(ResourceComponent)
        return resource_component.resources.to_dict() if resource_component else {}
    
    @property
    def population(self):
        """Backward compatibility property for accessing population."""
        population_component = self.get_component(PopulationComponent)
        return population_component.population if population_component else 0
    
    @property
    def population_capacity(self):
        """Backward compatibility property for accessing population capacity."""
        population_component = self.get_component(PopulationComponent)
        return population_component.population_capacity if population_component else 0
    
    @property
    def population_loyalty(self):
        """Backward compatibility property for accessing population loyalty."""
        population_component = self.get_component(PopulationComponent)
        return population_component.population_loyalty if population_component else 0
    
    @property
    def territory(self):
        """Backward compatibility property for accessing territory."""
        territory_component = self.get_component(TerritoryComponent)
        return territory_component.territory if territory_component else set()
    
    @property
    def border_tiles(self):
        """Backward compatibility property for accessing border tiles."""
        territory_component = self.get_component(TerritoryComponent)
        return territory_component.border_tiles if territory_component else set()
    
    def _setup_components(self):
        """Set up all components for this house entity."""
        starting_attributes = self.default_attributes()
        
        # Add Resource Component FIRST
        resource_component = ResourceComponent(entity_id=self.id, starting_resources=starting_attributes["resources"])
        self.add_component(resource_component)
        
        # Add Territory Component
        territory_component = TerritoryComponent(entity_id=self.id)
        self.add_component(territory_component)
        
        # Add Population Component
        population_component = PopulationComponent(
            entity_id=self.id, 
            starting_population=starting_attributes["population"],
            starting_loyalty=starting_attributes["population_loyalty"]
        )
        self.add_component(population_component)
        
        # Note: Population capacity will be calculated after territory is assigned
        
        # Add Rookery Component so it's available when AI component is initialized
        rookery_component = RookeryComponent(entity_id=self.id)
        self.add_component(rookery_component)
        
        # Set up known recipients immediately (without discovery observations)
        for recipient_name in self.known_recipients:
            if recipient_name != self.name:  # Don't add self as recipient
                rookery_component.add_known_recipient(recipient_name, recipient_name, discovered=False)
        
        # AI Component for intelligent decision making (added after other components so tools work)
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
            instructions=HOUSE_LEADER_INSTRUCTIONS + personality,
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
        population_component = self.get_component(PopulationComponent)
        resource_component = self.get_component(ResourceComponent)
        
        if not population_component or not resource_component:
            return
        
        # Get total food available
        total_food = resource_component.resources.food
        
        # Use PopulationComponent to manage population
        population_component.manage_population_turn(total_food)
        
        # Add observations for AI component
        ai_component = self.get_component(AIComponent)
        population_component.add_observation_for_changes(ai_component, "Production")
        
        # Check for revolt and print warning
        if population_component.check_revolt_risk():
            print(f"{self.name} is experiencing a population revolt!")

        

    def gather_resources(self, seasonal_modifier=1.0):
        """Gather resources based on the current population and territory outputs,
        enforcing a production cap based on population."""
        resource_component = self.get_component(ResourceComponent)
        if not resource_component:
            return
        
        population_ratio = self.population / self.population_capacity if self.population_capacity > 0 else 1.0
        
        # Get territory from TerritoryComponent
        territory_component = self.get_component(TerritoryComponent)
        territory = territory_component.territory if territory_component else set()
        
        # Use ResourceComponent to gather resources
        resource_component.gather_resources_from_territories(
            territory, 
            population_ratio, 
            seasonal_modifier
        )
        
        # Add observations for AI component
        ai_component = self.get_component(AIComponent)
        resource_component.add_observation_for_changes(ai_component, "Production")
        
        # Add in-transit raven observations
        rookery_component = self.get_component(RookeryComponent)
        if rookery_component:
            rookery_component.add_in_transit_observations(ai_component, "Production")

    def get_population_capacity(self):
        """Backward compatibility method."""
        population_component = self.get_component(PopulationComponent)
        return population_component.population_capacity if population_component else 0

    def expand_territory(self, new_territory: list[HexTile], hex_grid):
        # Use TerritoryComponent to expand territory
        territory_component = self.get_component(TerritoryComponent)
        if not territory_component:
            return
        
        territory_component.expand_territory(new_territory, hex_grid, self.color)
        
        # Update population capacity using PopulationComponent
        population_component = self.get_component(PopulationComponent)
        if population_component:
            population_component.calculate_capacity_from_territories(territory_component.territory)

    def collect_taxes(self, tax_rate):
        resource_component = self.get_component(ResourceComponent)
        if not resource_component:
            return 0
        
        if not (0 < tax_rate <= 1):
            raise ValueError("Tax rate must be between 0 and 1")
        
        tax_collected = resource_component.collect_taxes(self.population, tax_rate)
        
        # loyalty decreases with higher tax rate
        loyalty_decrease = math.ceil(tax_rate * 80)  # Higher tax rate leads to more loyalty decrease
        self.population_loyalty = max(0, self.population_loyalty - loyalty_decrease)
        
        return tax_collected

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

        resource_component = self.get_component(ResourceComponent)
        if not resource_component:
            print(f"{self.name} has no resource component to raise troops.")
            return
        
        costs = {'food': total_food_cost, 'material': total_material_cost}
        
        if resource_component.consume_for_action(costs, f"raise_{troop_type}_army"):
            self.military_power += quantity  # Simplistic scaling
            print(f"{self.name} has raised {quantity} {troop_type} troops.")
        else:
            print(f"{self.name} does not have enough resources to raise {quantity} {troop_type} troops.")
    
    def make_ai_decisions(self, current_turn: int, current_phase: str, current_season: str, current_year: int, hex_grid=None, entity_manager=None, simulation=None):
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
            'population': self.get_component(PopulationComponent).population if self.get_component(PopulationComponent) else 0,
            'population_capacity': self.get_component(PopulationComponent).population_capacity if self.get_component(PopulationComponent) else 0,
            'population_loyalty': self.get_component(PopulationComponent).population_loyalty if self.get_component(PopulationComponent) else 0,
            'resources': self.get_component(ResourceComponent).resources.to_dict() if self.get_component(ResourceComponent) else {},
            'military_power': self.military_power,
            'territory_size': self.get_component(TerritoryComponent).get_territory_size() if self.get_component(TerritoryComponent) else 0
        }
        
        ai_component = self.get_component(AIComponent)
        if not ai_component:
            return f"House {self.name} has no AI component"
        
        ai_component.update_context(
            current_turn=current_turn,
            current_phase=current_phase,
            current_season=current_season,
            current_year=current_year,
            game_state=game_state,
            hex_grid=hex_grid,
            entity_manager=entity_manager,
            simulation=simulation
        )
        
        # Make AI decisions
        return ai_component.make_decisions()
