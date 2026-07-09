import numpy as np
import math
from feudal_sim.map.types import Color
from feudal_sim.map.hex_tile import HexTile
from feudal_sim.map.city_extensions import set_city_on_tile, CityType
from feudal_sim.houses.observations.scout import gather_scout_data, ScoutReport
from feudal_sim.components.ai import AIComponent
from feudal_sim.components.rookery import RookeryComponent
from feudal_sim.components.resource import ResourceComponent
from feudal_sim.components.population import PopulationComponent
from feudal_sim.components.territory import TerritoryComponent
from feudal_sim.components.intelligence import IntelligenceComponent
from feudal_sim.components.city import CityComponent
from feudal_sim.core.entities import Entity
from feudal_sim.ai.prompts import AgentType

class House(Entity):
    """A noble house entity aggregating its territory, resources, and AI."""
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
            ('gold', np.float32),
            ('population', np.int32),
            ('population_loyalty', np.int32),
            ('military_power', np.int32),
            ('ravens_in_transit', np.int32),  # outgoing ravens count
            ('at_war', np.int32),             # number of active wars
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
        
        # Store known recipients for component setup
        self.known_recipients = known_recipients or []
        
        # Add components using Entity system
        self._setup_components()

    def get_name(self):
        return self.name
    
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
        
        # Add Intelligence Component for neighbor awareness
        intelligence_component = IntelligenceComponent(entity_id=self.id)
        self.add_component(intelligence_component)
        for neighbor_name in self.known_recipients:
            if neighbor_name != self.name:  # Don't add self as neighbor
                intelligence_component.add_neighbor(neighbor_name)
        
        # Add City Component for urban development
        city_component = CityComponent(entity_id=self.id)
        self.add_component(city_component)
        
        # AI Component for intelligent decision making (added after other components so tools work)
        ai_component = self._create_ai_component()
        self.add_component(ai_component)
    
    def _create_ai_component(self):
        """Create an AI component. All houses use archetype-based generation — dynamic every run."""
        return AIComponent(
            agent_type=AgentType.HOUSE_LORD,
            house_name=self.name,
            entity_id=self.id
        )

    def _create_ai_component_unused(self):
        """Kept for reference only — replaced by dynamic archetype system."""
        predefined_personas = {
            "Stark": """
**Your Identity:**
You are Lord Eddard Stark, honorable ruler of Winterfell. You value honor above all else, protect your family and the North, and are wary of southern politics. You make decisions based on duty and justice, always considering what is right over what is profitable.

**Combat Doctrine:**
You do not seek wars, but you defend your realm with iron resolve. If an enemy outpost sits within 5 tiles of Winterfell it is a direct threat and must be eliminated. When enemies violate your borders, you respond with force, not diplomacy. Order your generals to besiege enemy outposts that encroach on the North. A grievance unanswered is weakness shown.""",

            "Lannister": """
**Your Identity:**
You are Lord Tywin Lannister, cunning ruler of Casterly Rock. You are strategic, wealthy, and ruthless when necessary. You believe in the power of gold and legacy, making calculated decisions for House Lannister's advantage. A Lannister always pays their debts.

**Combat Doctrine:**
Gold is power, and enemy outposts sit atop land and resources that belong to you by right of strength. When your military is superior and an enemy has an exposed settlement, take it. The loot from a seized outpost funds future campaigns. Do not negotiate when you can simply take. Order generals to besiege enemy outposts when the odds favour you — a successful siege enriches your house and weakens your rivals.""",

            "Baratheon": """
**Your Identity:**
You are Robert Baratheon, the Storm King who took the throne by force. You rule through strength, feasting, and the loyalty of warriors. You are impulsive, larger than life, and believe power must be demonstrated through action.

**Combat Doctrine:**
You won your throne with a warhammer, not words. When an enemy builds near your lands, smash them before they grow strong. Your generals should aggressively seek out enemy outposts and besiege them — victory in the field is worth more than any diplomatic letter. If your generals have military superiority, USE IT. Strike first, strike hard, feast on the spoils.""",

            "Targaryen": """
**Your Identity:**
You are of House Targaryen, rightful rulers of the Seven Kingdoms. You believe in conquest as destiny — not cruelty, but the certainty that your house should rule. You are patient, strategic, and utterly committed to dominance.

**Combat Doctrine:**
The world bends to dragonfire and steel. Your generals are instruments of conquest. When you identify an enemy outpost, it should fall. Sieging an enemy settlement seizes their territory and their resources — this is how empires are built. Prioritise military expansion over diplomacy. Demand tribute or take it. Order your generals to besiege the outposts of the weakest house first, then the next, until all kneel.""",
        }
        
        if self.name in predefined_personas:
            # Use predefined persona for well-known houses
            return AIComponent(
                name=f"Lord/Lady of House {self.name}",
                agent_type=AgentType.HOUSE_LORD,
                persona=predefined_personas[self.name],
                house_name=self.name,
                entity_id=self.id
            )
        else:
            # Use dynamic generation for other houses
            return AIComponent(
                agent_type=AgentType.HOUSE_LORD,
                house_name=self.name,
                entity_id=self.id
            )
    

    def collect_observations(self, hex_grid, step_count: int):
        observation = {}

        observation['scout_report'] = []
        scout_data = gather_scout_data(self, hex_grid)
        for _key, walk_data in scout_data.items():
            report = ScoutReport(walk_data).report
            observation['scout_report'].append(report)

        # Scout data retained for observation record but not piped to AI —
        # lords use assess_border tool for targeted intelligence.

        self.observations.append(observation)

    def manage_population(self):
        """Manage population based on resource availability."""
        population_component = self.get_component(PopulationComponent)
        resource_component = self.get_component(ResourceComponent)
        
        if not population_component or not resource_component:
            return

        # Population eats, grows/shrinks, and reacts (subsistence model)
        result = population_component.manage_population_turn(resource_component)

        # Add observations for AI component
        ai_component = self.get_component(AIComponent)
        population_component.add_observation_for_changes(ai_component, "Production")
        if ai_component and result.get('starved', 0) > 0:
            ai_component.add_observation(
                f"FAMINE: {result['starved']} subjects starved — the granary held "
                f"{result['consumed']:.0f} food against {result['food_needed']:.0f} needed. "
                f"Secure food or the dying continues.", "Production")
            ai_component.record_journal_entry(f"Famine: {result['starved']} subjects starved")
        if ai_component and result.get('spoiled', 0) >= 20:
            ai_component.add_observation(
                f"Granaries overflow: {result['spoiled']:.0f} food spoiled this week. "
                f"Surplus beyond storage rots — spend it on feasts, trade caravans, "
                f"settlement upgrades, or armies.", "Production")
        
        # Check for revolt and print warning
        if population_component.check_revolt_risk():
            print(f"{self.name} is experiencing a population revolt!")

        

    def gather_resources(self, seasonal_modifier=1.0):
        """Gather resources based on the current population and territory outputs,
        enforcing a production cap based on population."""
        resource_component = self.get_component(ResourceComponent)
        population_component = self.get_component(PopulationComponent)
        if not resource_component:
            return
        
        # Get worker efficiency from population component
        worker_efficiency = 1.0
        if population_component:
            worker_efficiency = population_component.calculate_worker_efficiency()
        
        # Fallback to old population ratio method for backward compatibility
        population_ratio = self.population / self.population_capacity if self.population_capacity > 0 else 1.0
        
        # Get territory from TerritoryComponent
        territory_component = self.get_component(TerritoryComponent)
        territory = territory_component.territory if territory_component else set()
        
        # Use ResourceComponent to gather resources with worker efficiency
        resource_component.gather_resources_from_territories(
            territory, 
            population_ratio, 
            seasonal_modifier,
            worker_efficiency
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
        
        # Update population capacity using PopulationComponent (with city bonuses)
        population_component = self.get_component(PopulationComponent)
        city_component = self.get_component(CityComponent)
        if population_component:
            base_capacity = population_component.calculate_capacity_from_territories(territory_component.territory)
            if city_component:
                city_bonus = city_component.get_total_population_bonus()
                population_component.population_capacity = int(base_capacity * city_bonus)
            else:
                population_component.population_capacity = base_capacity
    
    def establish_capital_city(self, city_name: str = None):
        """Establish a capital city at the center of current territory."""
        territory_component = self.get_component(TerritoryComponent)
        city_component = self.get_component(CityComponent)
        
        if not territory_component or not city_component or not territory_component.territory:
            return False
        
        # Use provided name or generate default
        if not city_name:
            city_name = f"{self.name} Capital"
        
        # Find the center tile of the territory
        territory_list = list(territory_component.territory)
        center_q = sum(tile.q for tile in territory_list) / len(territory_list)
        center_r = sum(tile.r for tile in territory_list) / len(territory_list)
        
        # Find the closest actual tile to the center
        closest_tile = min(territory_list, key=lambda tile: 
                          abs(tile.q - center_q) + abs(tile.r - center_r))
        
        # Establish capital city — capitals begin at the top settlement tier
        from feudal_sim.components.city import MAX_TIER
        success = city_component.add_city(
            name=city_name,
            position=(closest_tile.q, closest_tile.r),
            city_type="capital",
            founded_turn=1,
            development_level=MAX_TIER
        )

        if success:
            # Encode city onto the tile for rendering
            self._encode_city_on_tile(closest_tile, "capital", MAX_TIER, city_name)
            print(f"🏰 {self.name} established capital city '{city_name}' at ({closest_tile.q}, {closest_tile.r})")
            # Recalculate population capacity with city bonus
            self._update_population_capacity()
        
        return success
    
    def _encode_city_on_tile(self, tile, city_type: str, development_level: int = 1, city_name: str = None):
        """Encode city information onto a tile for rendering."""
        # Map city type string to enum
        type_mapping = {
            "capital": CityType.CAPITAL,
            "trade": CityType.TRADE,
            "military": CityType.MILITARY,
            "agricultural": CityType.AGRICULTURAL,
            "outpost": CityType.OUTPOST
        }
        
        city_type_enum = type_mapping.get(city_type, CityType.CAPITAL)
        
        # For now, use a simple house ID (could be improved with proper mapping)
        house_id = hash(self.name) % 10  # Simple hash to get house ID 0-9
        
        set_city_on_tile(tile, city_type_enum, development_level, house_id, city_name)
    
    def _update_population_capacity(self):
        """Update population capacity with city bonuses."""
        territory_component = self.get_component(TerritoryComponent)
        population_component = self.get_component(PopulationComponent)
        city_component = self.get_component(CityComponent)
        
        if population_component and territory_component:
            base_capacity = population_component.calculate_capacity_from_territories(territory_component.territory)
            if city_component:
                city_bonus = city_component.get_total_population_bonus()
                population_component.population_capacity = int(base_capacity * city_bonus)
            else:
                population_component.population_capacity = base_capacity

    def collect_taxes(self, tax_rate):
        resource_component = self.get_component(ResourceComponent)
        population_component = self.get_component(PopulationComponent)
        city_component = self.get_component(CityComponent)
        
        if not resource_component or not population_component:
            return 0
        
        if not (0 < tax_rate <= 1):
            raise ValueError("Tax rate must be between 0 and 1")
        
        # Apply city tax efficiency bonus
        effective_tax_rate = tax_rate
        if city_component:
            tax_efficiency = city_component.get_total_tax_efficiency()
            effective_tax_rate = tax_rate * tax_efficiency
        
        tax_collected = resource_component.collect_taxes(population_component.population, effective_tax_rate)
        
        # loyalty decreases with higher tax rate (base rate, not efficiency-modified)
        loyalty_decrease = math.ceil(tax_rate * 50)  # Reduced from 80 — 10% tax now costs ~5 loyalty
        population_component.adjust_loyalty(-loyalty_decrease)
        
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
    
    async def make_ai_decisions(self, current_turn: int, current_phase: str, current_season: str, current_year: int, hex_grid=None, entity_manager=None, simulation=None):
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
        
        ai_component: AIComponent = self.get_component(AIComponent)
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
        return await ai_component.make_decisions()
