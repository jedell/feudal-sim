"""
Trade and diplomacy tools for the feudal simulation.

Trade-caravan dispatch and war/peace declarations.
"""

from enum import Enum
from typing import Callable

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401
from feudal_sim.ai.tools.common import hex_distance


def create_send_trade_caravan_tool(house_entity) -> Callable:
    """
    Factory function to create a send_trade_caravan tool bound to a specific house entity.
    """
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.components.rookery import RookeryComponent
    from feudal_sim.components.territory import TerritoryComponent

    rookery_component = house_entity.get_component(RookeryComponent)
    resource_component = house_entity.get_component(ResourceComponent)
    territory_component = house_entity.get_component(TerritoryComponent)

    if not rookery_component:
        @function_tool
        def send_trade_caravan_no_rookery(recipient: str, goods_offered: str, terms: str) -> str:
            """No rookery available for trade communications."""
            return f"House {house_entity.name} has no rookery to coordinate trade caravans"
        return send_trade_caravan_no_rookery

    if not resource_component or not territory_component:
        @function_tool
        def send_trade_caravan_missing_components(recipient: str, goods_offered: str, terms: str) -> str:
            """Missing required components for trade caravan dispatch."""
            return f"House {house_entity.name} cannot send trade caravans - missing required components"
        return send_trade_caravan_missing_components

    # Get known recipients for trade targets
    known_recipients = rookery_component.get_known_recipients_list()

    if not known_recipients:
        @function_tool
        def send_trade_caravan_no_recipients(recipient: str, goods_offered: str, terms: str) -> str:
            """No known recipients for trade."""
            return f"House {house_entity.name} has no known houses to trade with"
        return send_trade_caravan_no_recipients

    # Create dynamic enum for recipients
    recipient_dict = {name: name for name in known_recipients}
    RecipientEnum = Enum('TradeRecipient', recipient_dict)

    @function_tool
    def send_trade_caravan(ctx: RunContextWrapper["SimulationContext"],
                          recipient: RecipientEnum,
                          food_offered: int = 0,
                          material_offered: int = 0,
                          metal_offered: int = 0,
                          gold_offered: int = 0,
                          terms: str = "Standard trade agreement",
                          direction: str = "") -> str:
        """
        Dispatch a trade caravan to another house with specified goods and terms.
        The caravan will physically travel to the recipient and trigger a priority negotiation.
        
        Args:
            recipient: The house to send the trade caravan to (must be known recipient)
            food_offered: Amount of food to offer in trade (default 0)
            material_offered: Amount of material to offer in trade (default 0) 
            metal_offered: Amount of metal to offer in trade (default 0)
            gold_offered: Amount of gold to offer in trade (default 0)
            terms: Description of trade terms and what you want in return
            direction: Optional direction hint for route planning (N, NE, SE, S, SW, NW)
            
        Returns:
            Result of dispatching the trade caravan
        """
        sim_context = ctx.context
        if not sim_context or not hasattr(sim_context, 'hex_grid') or not sim_context.hex_grid:
            return "Trade caravan dispatch failed - map access not available"

        recipient_name = recipient.value

        # Validate that we have goods to trade
        total_goods = food_offered + material_offered + metal_offered + gold_offered
        if total_goods <= 0:
            return "Cannot send empty trade caravan - must offer at least some goods"

        # Check if we have the resources to offer
        current_resources = resource_component.resources
        insufficient = []
        if food_offered > current_resources.food:
            insufficient.append(f"food (need {food_offered}, have {current_resources.food:.0f})")
        if material_offered > current_resources.material:
            insufficient.append(f"material (need {material_offered}, have {current_resources.material:.0f})")
        if metal_offered > current_resources.metal:
            insufficient.append(f"metal (need {metal_offered}, have {current_resources.metal:.0f})")
        if gold_offered > current_resources.gold:
            insufficient.append(f"gold (need {gold_offered}, have {current_resources.gold:.0f})")

        if insufficient:
            return f"Cannot send trade caravan - insufficient resources: {', '.join(insufficient)}"

        # Find recipient house
        if not hasattr(sim_context, 'entity_manager') or not sim_context.entity_manager:
            return "Trade caravan dispatch failed - cannot access entity manager"

        recipient_house = None
        for entity in sim_context.entity_manager.get_all_entities():
            if hasattr(entity, 'name') and entity.name == recipient_name:
                recipient_house = entity
                break

        if not recipient_house:
            return f"Cannot find recipient house '{recipient_name}'"

        # Create trade goods
        from feudal_sim.components.cargo import TradeGoods
        trade_goods = TradeGoods(
            food=float(food_offered),
            material=float(material_offered),
            metal=float(metal_offered),
            gold=float(gold_offered)
        )

        # Consume resources from sending house
        costs = {}
        if food_offered > 0:
            costs['food'] = food_offered
        if material_offered > 0:
            costs['material'] = material_offered
        if metal_offered > 0:
            costs['metal'] = metal_offered
        if gold_offered > 0:
            costs['gold'] = gold_offered

        resource_component.consume_for_action(costs, "Send Trade Caravan")

        # Find starting position (center of our territory)
        starting_position = None
        if territory_component.territory:
            # Convert set to list for calculation
            territory_tiles = list(territory_component.territory)

            # Use center of territory as starting position
            total_q = sum(tile.q for tile in territory_tiles)
            total_r = sum(tile.r for tile in territory_tiles)
            center_q = int(total_q / len(territory_tiles))
            center_r = int(total_r / len(territory_tiles))

            # Find closest territory tile to centroid
            min_distance = float('inf')
            for tile in territory_tiles:
                distance = abs(tile.q - center_q) + abs(tile.r - center_r)
                if distance < min_distance:
                    min_distance = distance
                    starting_position = (tile.q, tile.r)

        if not starting_position:
            return "Cannot determine starting position for trade caravan"

        # Create and dispatch trade caravan
        from feudal_sim.entities.caravan import TradeCaravan

        caravan = TradeCaravan.create_trade_caravan(
            sender_house_id=house_entity.id,
            recipient_house_id=recipient_house.id,
            cargo=trade_goods,
            proposed_terms=terms,
            starting_position=starting_position,
            caravan_name=f"{house_entity.name} Trade Mission"
        )

        caravan.created_turn = sim_context.current_turn

        # Plan route to recipient house
        # Clean and validate direction parameter
        preferred_direction = direction.strip().upper() if direction else None
        valid_directions = {'N', 'NE', 'SE', 'S', 'SW', 'NW'}
        if preferred_direction and preferred_direction not in valid_directions:
            preferred_direction = None  # Invalid direction, ignore

        route_success = caravan.plan_route_to_house(recipient_house, sim_context.hex_grid, preferred_direction)
        if not route_success:
            return f"Could not plan route to {recipient_name} - no accessible territory found"

        # Register caravan with entity manager
        sim_context.entity_manager._entities[caravan.id] = caravan

        # Track by type for easy lookup
        if 'caravan' not in sim_context.entity_manager._entities_by_type:
            sim_context.entity_manager._entities_by_type['caravan'] = []
        sim_context.entity_manager._entities_by_type['caravan'].append(caravan)

        # Immediately update renderer to show newly dispatched caravan
        try:
            positioned_entities = []
            generals = sim_context.entity_manager.get_entities_by_type('general') or []
            caravans = sim_context.entity_manager.get_entities_by_type('caravan') or []
            positioned_entities.extend(generals)
            positioned_entities.extend(caravans)
            sim_context.hex_grid.render(sim_context.houses, positioned_entities)
        except Exception:
            pass  # Don't fail caravan dispatch if render update fails

        # Log the trade mission
        goods_summary = str(trade_goods)

        # Estimate arrival: caravan moves 3 tiles/turn; calculate hex distance to recipient
        eta_turns = "unknown"
        try:
            from feudal_sim.components.position import PositionComponent
            caravan_pos = caravan.get_component(PositionComponent)
            if caravan_pos and caravan_pos.position and recipient_house:
                from feudal_sim.components.territory import TerritoryComponent
                r_terr = recipient_house.get_component(TerritoryComponent)
                if r_terr and r_terr.territory:
                    rq = sum(t.q for t in r_terr.territory) // len(r_terr.territory)
                    rr = sum(t.r for t in r_terr.territory) // len(r_terr.territory)
                    dist = hex_distance(caravan_pos.position, (rq, rr))
                    import math as _math
                    eta_turns = _math.ceil(dist / 3)
        except Exception:
            pass

        eta_text = f"~{eta_turns} turn(s)" if isinstance(eta_turns, int) else "a few turns"
        return (f"Trade caravan dispatched to {recipient_name}! "
                f"Carrying: {goods_summary}. "
                f"Terms: '{terms}'. "
                f"Estimated arrival: {eta_text}.")

    # Add action description for dynamic prompts
    send_trade_caravan.action_description = "**Send Trade Caravan**: Dispatch goods to another house for negotiation (physical caravan travels across map)"

    return send_trade_caravan


def create_declare_war_tool(house_entity):
    """Declare war on another house."""
    @function_tool
    def declare_war(ctx: RunContextWrapper["SimulationContext"], target_house_name: str) -> str:
        """
        Formally declare war on another house. This signals hostile intent and changes how contact events are resolved.
        Use when you want open conflict rather than negotiation.
        """
        sim = getattr(ctx.context, 'simulation', None)
        if not sim or not hasattr(sim, 'war_registry'):
            return "War declaration unavailable."
        # Find target house id by name
        target = next((h for h in sim.houses if h.name == target_house_name), None)
        if not target:
            return f"No house named '{target_house_name}' found."
        if target.id == house_entity.id:
            return "You cannot declare war on yourself."
        success = sim.war_registry.declare_war(house_entity.id, target.id)
        if not success:
            return f"You are already at war with House {target_house_name}."
        msg = f"House {house_entity.name} has declared war on House {target_house_name}!"
        # Notify both parties
        from feudal_sim.components.ai import AIComponent as _AIC
        ai_self = house_entity.get_component(_AIC)
        ai_tgt = target.get_component(_AIC)
        if ai_self:
            ai_self.add_observation(f"You declared war on House {target_house_name}.", "Events")
            ai_self.record_journal_entry(f"War declared against House {target_house_name}")
        if ai_tgt:
            ai_tgt.add_observation(f"House {house_entity.name} has declared war on you!", "Events")
            ai_tgt.record_journal_entry(f"House {house_entity.name} declared war on us")
        print(f"⚔️  {msg}")
        return msg
    return declare_war


def create_sue_for_peace_tool(house_entity):
    """Offer peace to a house you are at war with."""
    @function_tool
    def sue_for_peace(ctx: RunContextWrapper["SimulationContext"], target_house_name: str) -> str:
        """
        Offer peace to a house you are currently at war with.
        If accepted (i.e., you call this), the war ends immediately. Ravens are the diplomatic channel — use this when you want to end a conflict.
        """
        sim = getattr(ctx.context, 'simulation', None)
        if not sim or not hasattr(sim, 'war_registry'):
            return "Peace negotiation unavailable."
        target = next((h for h in sim.houses if h.name == target_house_name), None)
        if not target:
            return f"No house named '{target_house_name}' found."
        success = sim.war_registry.sue_for_peace(house_entity.id, target.id)
        if not success:
            return f"You are not at war with House {target_house_name}."
        msg = f"Peace concluded between House {house_entity.name} and House {target_house_name}."
        from feudal_sim.components.ai import AIComponent as _AIC
        ai_self = house_entity.get_component(_AIC)
        ai_tgt = target.get_component(_AIC)
        if ai_self:
            ai_self.add_observation(f"You made peace with House {target_house_name}.", "Events")
            ai_self.record_journal_entry(f"Peace concluded with House {target_house_name}")
        if ai_tgt:
            ai_tgt.add_observation(f"House {house_entity.name} has offered peace — the war is over.", "Events")
            ai_tgt.record_journal_entry(f"War with House {house_entity.name} ended")
        print(f"🕊️  {msg}")
        return msg
    return sue_for_peace
