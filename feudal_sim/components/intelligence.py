"""
IntelligenceComponent - Simple neighbor intelligence for entities.

Maintains basic intelligence reports on other houses including distance, 
direction, and territory size.
"""

import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from feudal_sim.core.entities import Component
from feudal_sim.components.territory import TerritoryComponent


@dataclass
class IntelligenceReport:
    """Simple intelligence report on another house."""
    target_house: str
    distance: float
    direction: str
    territory_size: int
    notes: str = ""


class IntelligenceComponent(Component):
    """
    Manages simple neighbor intelligence.
    
    Tracks distance, direction, and territory size for other houses.
    """
    
    def __init__(self, entity_id: str = None):
        super().__init__(entity_id)
        
        # Intelligence reports keyed by house name
        self.intelligence_reports: Dict[str, IntelligenceReport] = {}
        self.neighbor_names: List[str] = []

    def add_neighbor(self, neighbor_name: str):
        """Add a neighbor to the list of neighbors."""
        self.neighbor_names.append(neighbor_name)

    def get_neighbors(self) -> List[str]:
        """Get the list of neighbors."""
        return self.neighbor_names
    
    def get_territory_center(self) -> Tuple[float, float]:
        """Calculate the centroid of our controlled territory."""
        
        territory_component = self.entity.get_component(TerritoryComponent)
        if not territory_component or not territory_component.territory:
            return (0.0, 0.0)
        
        total_q = sum(tile.q for tile in territory_component.territory)
        total_r = sum(tile.r for tile in territory_component.territory)
        
        center_q = total_q / len(territory_component.territory)
        center_r = total_r / len(territory_component.territory)
        
        return (center_q, center_r)
    
    def calculate_distance(self, center1: Tuple[float, float], center2: Tuple[float, float]) -> float:
        """Calculate hex distance between two points."""
        q1, r1 = center1
        q2, r2 = center2
        
        # Convert to cube coordinates for distance calculation
        x1, y1, z1 = q1, -q1-r1, r1
        x2, y2, z2 = q2, -q2-r2, r2
        
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))
    
    def calculate_direction(self, from_center: Tuple[float, float], to_center: Tuple[float, float]) -> str:
        """Calculate cardinal/intercardinal direction from one point to another."""
        dq = to_center[0] - from_center[0]
        dr = to_center[1] - from_center[1]
        
        # Handle case where points are the same
        if abs(dq) < 0.01 and abs(dr) < 0.01:
            return "Same location"
        
        # Convert to angle (in radians)
        angle = math.atan2(dr, dq)
        
        # Convert to degrees and normalize to 0-360
        angle_degrees = math.degrees(angle) % 360
        
        # Map to 8 cardinal directions
        # Starting from East (0°) and going counter-clockwise
        directions = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
        direction_index = round(angle_degrees / 45) % 8
        
        return directions[direction_index]
    
    def _calculate_territory_center_for_house(self, house) -> Tuple[float, float]:
        """Calculate territory center for another house."""
        territory_component = house.get_component(TerritoryComponent)
        if not territory_component or not territory_component.territory:
            return (0.0, 0.0)
        
        total_q = sum(tile.q for tile in territory_component.territory)
        total_r = sum(tile.r for tile in territory_component.territory)
        
        center_q = total_q / len(territory_component.territory)
        center_r = total_r / len(territory_component.territory)
        
        return (center_q, center_r)
    
    def generate_initial_intelligence(self, all_houses: List):
        """Generate initial intelligence reports for all other houses."""
        our_center = self.get_territory_center()
        our_house_name = self.entity.name if self.entity else self.entity_id
        
        for house in all_houses:
            # Skip ourselves
            if house.get_name() == our_house_name:
                continue
            
            # Calculate their territory center
            territory_component = house.get_component(TerritoryComponent)
            if not territory_component or not territory_component.territory:
                continue
            
            their_center = self._calculate_territory_center_for_house(house)
            distance = self.calculate_distance(our_center, their_center)
            direction = self.calculate_direction(our_center, their_center)
            territory_size = len(territory_component.territory)
            
            # Create intelligence report
            report = IntelligenceReport(
                target_house=house.get_name(),
                distance=distance,
                direction=direction,
                territory_size=territory_size,
                notes="Initial survey data."
            )
            
            self.intelligence_reports[house.get_name()] = report
    
    def get_intelligence_report(self, house_name: str) -> Optional[IntelligenceReport]:
        """Get intelligence report for a specific house."""
        return self.intelligence_reports.get(house_name)
    
    def get_all_intelligence_reports(self) -> Dict[str, IntelligenceReport]:
        """Get all intelligence reports."""
        return self.intelligence_reports.copy()
    
    def update_notes(self, house_name: str, notes: str):
        """Update notes for a house intelligence report."""
        if house_name in self.intelligence_reports:
            self.intelligence_reports[house_name].notes = notes
    
    def format_intelligence_report(self, house_name: str) -> str:
        """Format an intelligence report for display to AI agent."""
        report = self.intelligence_reports.get(house_name)
        if not report:
            return f"No intelligence available on House {house_name}."
        
        formatted_report = f"""House {report.target_house} Intelligence Report
═══════════════════════════════════
Distance: {report.distance:.0f} tiles {report.direction.lower()}
Territory Size: {report.territory_size} tiles
Direction: {report.direction}

Notes: {report.notes}"""
        
        return formatted_report
    
    def format_all_intelligence_summary(self) -> str:
        """Format a summary of all intelligence reports."""
        if not self.intelligence_reports:
            return "No intelligence reports available."
        
        summary = "═══ NEIGHBOR INTELLIGENCE SUMMARY ═══\n\n"
        
        for house_name, report in self.intelligence_reports.items():
            summary += f"House {house_name}: Located {report.distance:.0f} tiles to the {report.direction}, territory size: {report.territory_size} tiles\n"
        
        summary += "\nUse read_intelligence_report(house_name) for detailed reports."
        return summary
    
    def get_lore_section(self) -> str:
        """Return lore explanation of intelligence mechanics for AI prompts."""
        return """
**The Spymaster's Web:**
Knowledge of your rivals' movements, territories, and strength proves invaluable in the great game. Your intelligence network maintains dossiers on neighboring houses - their distances, territorial holdings, and any strategic observations you've gathered. 

Update these records as you learn more about the realm's players, for intelligence wins more battles than swords. A lord who knows their neighbors' weaknesses and strengths can plan accordingly, while one who remains ignorant invites defeat.
"""

    def update(self, dt: float, event_bus=None):
        """Component update - not currently used."""
        pass