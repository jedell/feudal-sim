from feudal_sim.houses.house import House

class ActionDispatcher:
    """Routes and executes action requests on behalf of a house."""
    def __init__(self, house: House):
        self.house = house

        self.actions = {
            'gather_resources': self.house.gather_resources,
            'collect_taxes': self.house.collect_taxes,
            'send_message': self.house.send_message,
            'raise_army': self.house.raise_army,
        }

    def get_action(self, response: str):
        return self.actions.get(response)

    def dispatch(self, action: str, **kwargs):
        action_func = self.actions.get(action)
        if action_func:
            action_func(**kwargs)
        else:
            raise ValueError(f"Action {action} not found")
            