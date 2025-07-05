"""
Example extension: Resource monitoring system
Demonstrates how to extend the simulation without modifying core code.
"""

from feudal_sim.core.events import event_bus, EventType


class ResourceMonitor:
    """
    Extension that monitors resource changes and provides analytics.
    Shows how the event system enables extensibility.
    """
    
    def __init__(self):
        self.resource_history = {}
        self.alerts = []
        
        # Subscribe to events without modifying existing code
        event_bus.subscribe(EventType.VALUE_CHANGED, self.track_resource_changes)
        event_bus.subscribe(EventType.SIMULATION_STEP, self.check_alerts)
        
    def track_resource_changes(self, event):
        """Track all resource changes across the simulation."""
        if event.data.get('entity_type') == 'house' and event.data.get('property') == 'resources':
            house_name = event.data['entity_name']
            resource_type = event.data['resource_type']
            change = event.data['change']
            
            # Initialize tracking
            if house_name not in self.resource_history:
                self.resource_history[house_name] = {}
            if resource_type not in self.resource_history[house_name]:
                self.resource_history[house_name][resource_type] = []
            
            # Record change
            self.resource_history[house_name][resource_type].append({
                'change': change,
                'timestamp': event.timestamp,
                'new_total': event.data['new_value']
            })
    
    def check_alerts(self, event):
        """Check for resource-based alerts each simulation step."""
        step_count = event.data['step_count']
        
        # Example: Alert if any house has very high resources
        for house_name, resources in self.resource_history.items():
            for resource_type, history in resources.items():
                if history and history[-1]['new_total'] > 500:
                    alert = f"🚨 {house_name} has high {resource_type}: {history[-1]['new_total']}"
                    if alert not in self.alerts:
                        self.alerts.append(alert)
                        print(alert)
    
    def get_summary(self):
        """Get a summary of resource tracking."""
        summary = {}
        for house_name, resources in self.resource_history.items():
            summary[house_name] = {}
            for resource_type, history in resources.items():
                if history:
                    total_gained = sum(h['change'] for h in history if h['change'] > 0)
                    summary[house_name][resource_type] = {
                        'total_gained': total_gained,
                        'current_amount': history[-1]['new_total'],
                        'num_transactions': len(history)
                    }
        return summary


# Auto-initialize when imported (demonstrates plugin-like behavior)
resource_monitor = ResourceMonitor()