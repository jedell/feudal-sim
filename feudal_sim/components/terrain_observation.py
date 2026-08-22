"""
TerrainObservation Component - Enables sub-agents to observe and assess their surroundings.

This component allows sub-agents (generals, scouts, etc.) to autonomously scan terrain,
assess expansion opportunities, detect threats, and gather intelligence for decision-making.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.core.events import event_bus, EventType
from feudal_sim.core.config import config
from feudal_sim.components.position import PositionComponent


@dataclass
class TileObservation:
    """Represents observed information about a specific tile."""
    coordinates: Tuple[int, int]
    terrain_type: str
    owner: Optional[str] = None
    owner_house: Optional[str] = None
    resources: Dict[str, float] = None
    population_capacity: int = 0
    threat_level: str = "none"  # "none", "low", "medium", "high"
    settlement_viability: float = 0.0  # 0.0 to 1.0
    last_observed_turn: int = -1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'coordinates': self.coordinates,
            'terrain_type': self.terrain_type,
            'owner': self.owner,
            'owner_house': self.owner_house,
            'resources': self.resources or {},
            'population_capacity': self.population_capacity,
            'threat_level': self.threat_level,
            'settlement_viability': self.settlement_viability,
            'last_observed_turn': self.last_observed_turn
        }


@dataclass
class ThreatDetection:
    """Represents a detected threat in the observation area."""
    threat_type: str  # "enemy_entity", "contested_territory", "fortification"
    position: Tuple[int, int]
    threat_level: str  # "low", "medium", "high"
    description: str
    detected_turn: int


@dataclass
class ExpansionOpportunity:
    """Represents an identified expansion opportunity."""
    position: Tuple[int, int]
    opportunity_type: str  # "resource", "strategic", "defensive", "settlement"
    value_assessment: float  # 0.0 to 1.0
    requirements: List[str]  # What's needed to claim this opportunity
    estimated_difficulty: str  # "easy", "medium", "hard"


class TerrainObservation(Component):
    """
    Enables sub-agents to observe and assess terrain around their position.
    
    This component handles:
    - Automatic terrain scanning when moving or acting
    - Threat detection (enemy entities, contested areas)
    - Expansion opportunity identification
    - Intelligence gathering for parent house reporting
    """
    
    def __init__(self, entity_id: str = None, observation_range: int = 2):
        super().__init__(entity_id)
        
        # Core observation data
        self.observation_range = observation_range
        self.observed_tiles: Dict[Tuple[int, int], TileObservation] = {}
        self.last_observation_turn = -1
        
        # Intelligence gathering
        self.threats_detected: List[ThreatDetection] = []
        self.opportunities_found: List[ExpansionOpportunity] = []
        self.territorial_conflicts: List[Dict[str, Any]] = []
        
        # Configuration
        self.auto_observe_on_move = config.get('simulation.subagents.auto_observe_on_move', True)
        self.threat_detection_range = config.get('simulation.subagents.threat_detection_range', 3)
        self.intelligence_retention_turns = config.get('simulation.subagents.intelligence_retention_turns', 10)
    
    def observe_current_area(self, hex_grid, current_position: Tuple[int, int], 
                           current_turn: int) -> Dict[str, Any]:
        """
        Observe the area around the current position and update intelligence.
        
        Args:
            hex_grid: Hex grid for tile access
            current_position: Current position (q, r) of the observer
            current_turn: Current turn number
            
        Returns:
            Dictionary with observation results
        """
        if not hex_grid or not current_position:
            return {'success': False, 'message': 'Invalid observation parameters'}
        
        self.last_observation_turn = current_turn
        tiles_observed = []
        new_threats = []
        new_opportunities = []
        
        # Get tiles within observation range
        for q_offset in range(-self.observation_range, self.observation_range + 1):
            for r_offset in range(-self.observation_range, self.observation_range + 1):
                # Skip tiles outside hex range
                if abs(q_offset) + abs(r_offset) + abs(-q_offset - r_offset) > self.observation_range * 2:
                    continue
                
                tile_pos = (current_position[0] + q_offset, current_position[1] + r_offset)
                tile = hex_grid.get_tile(tile_pos[0], tile_pos[1])
                
                if tile:
                    # Observe the tile
                    observation = self._observe_tile(tile, current_turn)
                    self.observed_tiles[tile_pos] = observation
                    tiles_observed.append(observation)
                    
                    # Check for threats
                    threats = self._detect_threats_at_tile(tile, tile_pos, current_turn)
                    new_threats.extend(threats)
                    
                    # Check for expansion opportunities
                    opportunities = self._assess_expansion_opportunities(tile, tile_pos, current_turn)
                    new_opportunities.extend(opportunities)
        
        # Update threat and opportunity lists
        self.threats_detected.extend(new_threats)
        self.opportunities_found.extend(new_opportunities)
        
        # Clean up old intelligence
        self._cleanup_old_intelligence(current_turn)
        
        # Emit observation event
        if event_bus:
            event_bus.emit(
                EventType.VALUE_CHANGED,
                self,
                entity_type='terrain_observation',
                entity_name=self.entity.name if self.entity else self.entity_id,
                property='area_observed',
                position=current_position,
                tiles_observed=len(tiles_observed),
                threats_detected=len(new_threats),
                opportunities_found=len(new_opportunities),
                turn=current_turn
            )
        
        return {
            'success': True,
            'tiles_observed': len(tiles_observed),
            'new_threats': len(new_threats),
            'new_opportunities': len(new_opportunities),
            'total_intelligence': {
                'known_tiles': len(self.observed_tiles),
                'active_threats': len(self.threats_detected),
                'known_opportunities': len(self.opportunities_found)
            }
        }
    
    def _observe_tile(self, tile, current_turn: int) -> TileObservation:
        """
        Create a detailed observation of a single tile.
        
        Args:
            tile: The tile to observe
            current_turn: Current turn number
            
        Returns:
            TileObservation with gathered intelligence
        """
        # Extract basic tile information
        terrain_type = str(tile.terrain_type) if hasattr(tile, 'terrain_type') else 'unknown'
        
        # Extract ownership information
        owner = None
        owner_house = None
        if hasattr(tile, 'owner') and tile.owner:
            owner = str(tile.owner)
            if hasattr(tile.owner, 'name'):
                owner_house = tile.owner.name
            elif hasattr(tile.owner, 'id'):
                owner_house = tile.owner.id
        
        # Extract resource information
        resources = {}
        if hasattr(tile, 'food_output'):
            resources['food'] = float(tile.food_output)
        if hasattr(tile, 'material_output'):
            resources['material'] = float(tile.material_output)
        if hasattr(tile, 'metal_output'):
            resources['metal'] = float(tile.metal_output)
        
        # Extract population capacity
        population_capacity = getattr(tile, 'population_capacity', 0)
        
        # Calculate settlement viability
        settlement_viability = self._calculate_settlement_viability(tile, resources, terrain_type)
        
        return TileObservation(
            coordinates=(tile.q, tile.r),
            terrain_type=terrain_type,
            owner=owner,
            owner_house=owner_house,
            resources=resources,
            population_capacity=population_capacity,
            threat_level="none",  # Will be updated by threat detection
            settlement_viability=settlement_viability,
            last_observed_turn=current_turn
        )
    
    def _calculate_settlement_viability(self, tile, resources: Dict[str, float], 
                                      terrain_type: str) -> float:
        """
        Calculate how viable a tile is for settlement.
        
        Args:
            tile: The tile to assess
            resources: Resource output of the tile
            terrain_type: Type of terrain
            
        Returns:
            Settlement viability score (0.0 to 1.0)
        """
        viability = 0.0
        
        # Base viability by terrain type
        terrain_bonuses = {
            'PLAINS': 0.8,
            'GRASSLAND': 0.9,
            'FOREST': 0.7,
            'HILLS': 0.6,
            'MOUNTAINS': 0.3,
            'WATER': 0.0,
            'DESERT': 0.2
        }
        
        terrain_upper = terrain_type.upper()
        for terrain, bonus in terrain_bonuses.items():
            if terrain in terrain_upper:
                viability += bonus
                break
        else:
            viability += 0.5  # Default for unknown terrain
        
        # Resource bonuses
        total_resources = sum(resources.values())
        resource_bonus = min(0.3, total_resources / 100.0)  # Max 30% bonus
        viability += resource_bonus
        
        # Population capacity bonus
        if hasattr(tile, 'population_capacity'):
            capacity_bonus = min(0.2, tile.population_capacity / 50.0)  # Max 20% bonus
            viability += capacity_bonus
        
        return min(1.0, viability)
    
    def _detect_threats_at_tile(self, tile, tile_pos: Tuple[int, int], 
                                      current_turn: int) -> List[ThreatDetection]:
        """
        Detect threats at a specific tile location.
        
        Args:
            tile: The tile to check for threats
            tile_pos: Position coordinates of the tile
            current_turn: Current turn number
            
        Returns:
            List of detected threats
        """
        threats = []
        
        # Owned land by other houses is not considered a threat by itself.
        # Only actual enemy entities in the area are treated as threats.
        
        # Check for enemy entities (using spatial queries if available)
        if hasattr(self, '_entity_manager') and self._entity_manager:
            enemy_entities = self._entity_manager.get_enemy_entities_near(
                tile_pos, 1, self.entity.house_id if self.entity else None
            )
            
            for enemy_entity, distance in enemy_entities:
                threat_level = "high" if distance == 0 else "medium"
                threats.append(ThreatDetection(
                    threat_type="enemy_entity",
                    position=tile_pos,
                    threat_level=threat_level,
                    description=f"Enemy {getattr(enemy_entity, 'name', 'unit')} detected",
                    detected_turn=current_turn
                ))
        
        return threats
    
    def _assess_expansion_opportunities(self, tile, tile_pos: Tuple[int, int], 
                                      current_turn: int) -> List[ExpansionOpportunity]:
        """
        Assess expansion opportunities at a tile location.
        
        Args:
            tile: The tile to assess
            tile_pos: Position coordinates of the tile
            current_turn: Current turn number
            
        Returns:
            List of expansion opportunities
        """
        opportunities = []
        
        # Only consider unowned tiles as opportunities
        if hasattr(tile, 'owner') and tile.owner:
            return opportunities  # Skip owned tiles
        
        # Get tile observation for viability assessment
        tile_obs = self.observed_tiles.get(tile_pos)
        if not tile_obs:
            return opportunities
        
        # Resource opportunity
        total_resources = sum(tile_obs.resources.values())
        if total_resources > 50:  # Configurable threshold
            opportunities.append(ExpansionOpportunity(
                position=tile_pos,
                opportunity_type="resource",
                value_assessment=min(1.0, total_resources / 200.0),
                requirements=["settlement capability", "workers"],
                estimated_difficulty="easy" if tile_obs.settlement_viability > 0.7 else "medium"
            ))
        
        # Strategic opportunity (good settlement viability)
        if tile_obs.settlement_viability > 0.8:
            opportunities.append(ExpansionOpportunity(
                position=tile_pos,
                opportunity_type="settlement",
                value_assessment=tile_obs.settlement_viability,
                requirements=["workers", "supplies"],
                estimated_difficulty="easy"
            ))
        
        # Defensive opportunity (good for fortification)
        if 'HILL' in tile_obs.terrain_type.upper() or 'MOUNTAIN' in tile_obs.terrain_type.upper():
            opportunities.append(ExpansionOpportunity(
                position=tile_pos,
                opportunity_type="defensive",
                value_assessment=0.8,
                requirements=["soldiers", "construction capability"],
                estimated_difficulty="medium"
            ))
        
        return opportunities
    
    def _cleanup_old_intelligence(self, current_turn: int):
        """
        Remove old intelligence data to prevent memory bloat.
        
        Args:
            current_turn: Current turn number
        """
        # Remove old threats
        self.threats_detected = [
            threat for threat in self.threats_detected
            if current_turn - threat.detected_turn <= self.intelligence_retention_turns
        ]
        
        # Remove old tile observations (keep more recent ones)
        tiles_to_remove = []
        for pos, observation in self.observed_tiles.items():
            if current_turn - observation.last_observed_turn > self.intelligence_retention_turns * 2:
                tiles_to_remove.append(pos)
        
        for pos in tiles_to_remove:
            del self.observed_tiles[pos]
    
    def get_threats_in_area(self, center_position: Tuple[int, int], 
                          search_range: int = None) -> List[ThreatDetection]:
        """
        Get all known threats within a specified area.
        
        Args:
            center_position: Center position to search around
            search_range: Maximum distance to search (uses threat_detection_range if None)
            
        Returns:
            List of threats within the area
        """
        if search_range is None:
            search_range = self.threat_detection_range
        
        nearby_threats = []
        for threat in self.threats_detected:
            # Calculate distance using simple hex distance
            distance = PositionComponent.hex_distance(center_position, threat.position)
            if distance <= search_range:
                nearby_threats.append(threat)
        
        return nearby_threats
    
    def get_opportunities_in_area(self, center_position: Tuple[int, int], 
                                search_range: int = None) -> List[ExpansionOpportunity]:
        """
        Get all known expansion opportunities within a specified area.
        
        Args:
            center_position: Center position to search around
            search_range: Maximum distance to search (uses observation_range if None)
            
        Returns:
            List of opportunities within the area
        """
        if search_range is None:
            search_range = self.observation_range
        
        nearby_opportunities = []
        for opportunity in self.opportunities_found:
            # Calculate distance using simple hex distance
            distance = PositionComponent.hex_distance(center_position, opportunity.position)
            if distance <= search_range:
                nearby_opportunities.append(opportunity)
        
        return nearby_opportunities
    
    def get_best_expansion_target(self, opportunity_types: List[str] = None) -> Optional[ExpansionOpportunity]:
        """
        Get the best expansion opportunity based on value assessment.
        
        Args:
            opportunity_types: Filter by opportunity types (e.g., ['resource', 'settlement'])
            
        Returns:
            Best expansion opportunity or None if none found
        """
        filtered_opportunities = self.opportunities_found
        
        if opportunity_types:
            filtered_opportunities = [
                opp for opp in filtered_opportunities 
                if opp.opportunity_type in opportunity_types
            ]
        
        if not filtered_opportunities:
            return None
        
        # Sort by value assessment (highest first)
        filtered_opportunities.sort(key=lambda x: x.value_assessment, reverse=True)
        return filtered_opportunities[0]
    
    def get_observation_status(self) -> Dict[str, Any]:
        """Get current observation status for AI context or debugging."""
        return {
            'observation_range': self.observation_range,
            'last_observation_turn': self.last_observation_turn,
            'tiles_known': len(self.observed_tiles),
            'active_threats': len(self.threats_detected),
            'known_opportunities': len(self.opportunities_found),
            'threat_breakdown': {
                threat.threat_level: len([t for t in self.threats_detected if t.threat_level == threat.threat_level])
                for threat in self.threats_detected
            } if self.threats_detected else {},
            'opportunity_breakdown': {
                opp.opportunity_type: len([o for o in self.opportunities_found if o.opportunity_type == opp.opportunity_type])
                for opp in self.opportunities_found
            } if self.opportunities_found else {}
        }
    
    TERRAIN_SYMBOLS = {
        'grassland': '.', 'steppe': ',', 'temperate_forest': 'F',
        'boreal_forest': 'f', 'rainforest': 'J', 'hill': 'n',
        'mountain': '^', 'desert': 'd', 'tundra': 't', 'swamp': 'w',
        'ice_cap': 'i', 'ocean': '~', 'lake': '~', 'river': '~',
    }

    def render_local_map(self, center, hex_grid, current_turn: int, radius: int = 2,
                         own_house_name: str = None) -> str:
        """Compact ASCII hex window around the general, built from remembered
        observations. Terrain is static so remembered tiles render as known;
        tiles never observed render '?'. Ownership facts go in the notes with
        their observation age — memory is labeled, never passed off as truth."""
        q0, r0 = center
        rows = []
        notes = []
        for dr in range(-radius, radius + 1):
            symbols = []
            for dq in range(max(-radius, -dr - radius), min(radius, -dr + radius) + 1):
                coord = (q0 + dq, r0 + dr)
                if dq == 0 and dr == 0:
                    symbols.append('@')
                    continue
                obs = self.observed_tiles.get(coord)
                if not obs:
                    symbols.append('?')
                    continue
                sym = self.TERRAIN_SYMBOLS.get(
                    str(obs.terrain_type).lower().replace('hextiletype.', ''), '?')
                tile = hex_grid.get_tile(*coord) if hex_grid else None
                if tile is not None and getattr(tile, 'population_capacity', 0) >= 1000:
                    sym = '#'  # settlement overlay
                symbols.append(sym)
                if obs.owner_house and obs.owner_house != own_house_name:
                    age = current_turn - obs.last_observed_turn
                    age_note = "current" if age <= 1 else f"as of {age} turns ago"
                    notes.append(f"{self._direction_label(dq, dr)}: held by {obs.owner_house} ({age_note})")
            rows.append(' ' * abs(dr) + ' '.join(symbols))
        legend = ("@ you | ? unscouted | . grass | , steppe | F/f/J forest | n hill | "
                  "^ mountain | d desert | t tundra | w swamp | ~ water | # settlement")
        out = [f"Local map (radius {radius}, N at top):"] + rows + [f"Legend: {legend}"]
        if notes:
            out.append("Holdings in view: " + "; ".join(sorted(set(notes))[:6]))
        return "\n".join(out)

    @staticmethod
    def _direction_label(dq: int, dr: int) -> str:
        """Grid-direction label + distance for an axial offset."""
        from feudal_sim.utils.directions import offset_to_bearing
        dist = (abs(dq) + abs(dr) + abs(-dq - dr)) // 2
        bearing = offset_to_bearing(dq, dr)
        return f"{dist} {bearing}" if bearing != "CENTER" else "here"

    def get_passive_observation_text(self) -> str:
        """
        Generate a concise natural language summary of the current observation state.
        Used for automatic passive observation injected each turn without tool calls.
        """
        if not self.observed_tiles:
            return ""

        unowned_count = sum(1 for obs in self.observed_tiles.values() if obs.owner is None)
        foreign: Dict[str, int] = {}
        for obs in self.observed_tiles.values():
            if obs.owner_house:
                foreign[obs.owner_house] = foreign.get(obs.owner_house, 0) + 1

        parts = []
        parts.append(f"{len(self.observed_tiles)} tiles in view")

        if unowned_count:
            parts.append(f"{unowned_count} unowned (claimable)")

        for house_name, count in foreign.items():
            parts.append(f"{count} held by {house_name}")

        if self.threats_detected:
            high = sum(1 for t in self.threats_detected if t.threat_level == "high")
            med = sum(1 for t in self.threats_detected if t.threat_level == "medium")
            threat_parts = []
            if high:
                threat_parts.append(f"{high} high-threat")
            if med:
                threat_parts.append(f"{med} medium-threat")
            parts.append("threats: " + ", ".join(threat_parts))
        else:
            parts.append("no threats detected")

        best = self.get_best_expansion_target(['resource', 'settlement'])
        if best:
            parts.append(f"notable {best.opportunity_type} opportunity nearby ({best.estimated_difficulty})")

        return "Passive scan: " + " | ".join(parts) + "."

    def update(self, dt: float, event_bus=None):
        """Component update method - could be used for periodic observation."""
        pass