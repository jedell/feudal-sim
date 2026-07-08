"""
House toolset factory — assembles the full set of tools for a house's AI agent.
"""

from agents import RunContextWrapper, function_tool

from feudal_sim.ai.context import SimulationContext  # noqa: F401
from feudal_sim.ai.tools.common import _balance_line
from feudal_sim.ai.tools.communication import (
    create_assess_border_tool,
    create_read_compendium_tool,
    create_send_raven_tool,
    create_rookery_toolset,
    create_write_compendium_tool,
    end_turn,
)
from feudal_sim.ai.tools.economy import (
    create_collect_taxes_tool,
    create_manage_household_tool,
)
from feudal_sim.ai.tools.territory import (
    create_deploy_general_tool,
    create_order_expansion_tool,
    create_view_cities_tool,
)
from feudal_sim.ai.tools.trade import (
    create_declare_war_tool,
    create_send_trade_caravan_tool,
    create_sue_for_peace_tool,
)


def create_house_toolset(house) -> list:
    """
    Create the complete set of tools available to a house's AI agent.

    Args:
        house: The House instance to create tools for
        
    Returns:
        List of tool functions bound to the house
    """
    tools = []

    # Communication tools
    tools.append(create_send_raven_tool(house))

    # Territory management tools
    tools.append(create_assess_border_tool(house))
    tools.append(create_order_expansion_tool(house))

    # assess_all_borders — scan all 6 directions in one call
    from feudal_sim.components.territory import TerritoryComponent as _TerritoryComponent
    territory_component_ab = house.get_component(_TerritoryComponent)

    @function_tool
    def assess_all_borders(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Assess all six border directions in a single call.
        Returns expansion opportunities, terrain, and cost for every direction.
        Use this instead of calling assess_border() six times.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.hex_grid or not territory_component_ab:
            return "Border assessment unavailable — missing context or territory."
        hex_grid = sim_context.hex_grid
        DIRECTIONS = ['N', 'NE', 'SE', 'S', 'SW', 'NW']
        lines = []
        for direction in DIRECTIONS:
            analysis = territory_component_ab.calculate_direction_value(direction, hex_grid)
            if not analysis.get('has_opportunities'):
                lines.append(f"  {direction:2s} — no expansion opportunities")
            else:
                opps = analysis.get('opportunities', [])
                terrains = []
                for opp in opps[:3]:
                    t = opp.get('terrain_type', '')
                    if t and t not in terrains:
                        terrains.append(t)
                terrain_str = ', '.join(terrains)
                if analysis['total_opportunities'] > 3:
                    terrain_str += f" (+{analysis['total_opportunities'] - 3} more)"
                costs = analysis.get('expansion_cost_estimate', {})
                lines.append(
                    f"  {direction:2s} — {analysis['total_opportunities']} tiles "
                    f"({terrain_str}). Cost: {costs.get('material', '?')} material, "
                    f"{costs.get('gold', '?')} gold"
                )
        return "Border assessment (all directions):\n" + "\n".join(lines)
    assess_all_borders.action_description = "**Assess All Borders**: Survey all six directions at once — use this instead of calling assess_border() multiple times"
    tools.append(assess_all_borders)
    # Compendium tools (strategic journal)
    tools.append(create_read_compendium_tool(house))
    tools.append(create_write_compendium_tool(house))

    # Tax collection tools
    tools.append(create_collect_taxes_tool(house))

    # Feasts / social actions
    from feudal_sim.components.population import PopulationComponent
    from feudal_sim.components.resource import ResourceComponent
    from feudal_sim.core.config import config

    @function_tool
    def hold_feast(ctx: RunContextWrapper["SimulationContext"], food_cost: int = 100, gold_cost: int = 50) -> str:
        """
        Hold a feast to increase population loyalty at the cost of food and gold. Has a short cooldown.
        Default costs can be overridden. Effects scale mildly with spend.
        """
        sim_context = ctx.context
        pop: PopulationComponent = house.get_component(PopulationComponent)
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not pop or not res:
            return "Cannot hold feast - missing population or resource management"
        # Cooldown
        current_turn = getattr(sim_context, 'current_turn', 0) if sim_context else 0
        cooldown = config.get('simulation.population.feast.cooldown_turns', 4)
        if hasattr(pop, 'last_feast_turn') and current_turn - pop.last_feast_turn < cooldown:
            return f"Cannot hold feast yet - available in {cooldown - (current_turn - pop.last_feast_turn)} turns"
        # Validate costs
        food_cost = max(0, int(food_cost))
        gold_cost = max(0, int(gold_cost))
        costs = {}
        if food_cost > 0:
            costs['food'] = food_cost
        if gold_cost > 0:
            costs['gold'] = gold_cost
        if costs and not res.can_afford_action(costs):
            return f"Insufficient resources for feast: need {food_cost} food and {gold_cost} gold"
        # Consume resources
        if costs:
            res.consume_for_action(costs, 'Hold Feast')
        # Loyalty effect (bounded, scaled by spend)
        base_boost = config.get('simulation.population.feast.base_loyalty_boost', 8)
        food_factor = config.get('simulation.population.feast.food_factor', 0.02)
        gold_factor = config.get('simulation.population.feast.gold_factor', 0.03)
        boost = int(base_boost + food_factor * food_cost + gold_factor * gold_cost)
        pop.loyalty = min(100, pop.loyalty + max(1, boost))
        # Set cooldown
        pop.last_feast_turn = current_turn
        # Observation for house AI
        try:
            from feudal_sim.components.ai import AIComponent
            ai: AIComponent = house.get_component(AIComponent)
            if ai:
                ai.add_observation(
                    f"Held a feast: -{food_cost} food, -{gold_cost} gold; loyalty increased to {pop.loyalty}",
                    phase="Actions"
                )
        except Exception:
            pass
        balance = _balance_line(res, ['food', 'gold'])
        return f"Feast held. Loyalty now {pop.loyalty}. {balance}"
    hold_feast.action_description = "**Hold Feast**: Spend food and gold to boost loyalty (cooldown applies)"
    tools.append(hold_feast)

    # Population management tools
    tools.append(create_manage_household_tool(house))

    # Resupply general tool (delayed delivery — arrives next turn)
    @function_tool
    def send_resupply(ctx: RunContextWrapper["SimulationContext"], general_name: str, gold: int = 20, food: int = 0) -> str:
        """
        Dispatch a resupply convoy to a deployed general. The convoy arrives next turn,
        restoring their supplies and morale. Costs gold (and optionally food) from your stores.

        Args:
            general_name: Name of the general to resupply
            gold: Gold to spend on supplies (each 10 gold = 20 supply points, max 100)
            food: Food to include in the convoy (each 10 food = 10 supply points)
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send resupply — no access to entity manager"
        from feudal_sim.components.resource import ResourceComponent
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not res:
            return "Cannot send resupply — missing resource management"
        costs = {}
        if gold > 0:
            costs['gold'] = gold
        if food > 0:
            costs['food'] = food
        if not costs:
            return "Must spend at least some gold or food to resupply"
        if not res.can_afford_action(costs):
            return f"Insufficient resources to send resupply (need {gold} gold, {food} food)"
        # Find general
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                      if getattr(g, 'house_id', None) == house.id and g.name == general_name]
        if not candidates:
            return f"No general named '{general_name}' found"
        general = candidates[0]
        # Calculate supply points: 10 gold = 20 points, 10 food = 10 points
        supply_points = min(100, (gold // 10) * 20 + (food // 10) * 10)
        if supply_points <= 0:
            return "Not enough resources to provide meaningful supplies (minimum 10 gold)"
        # Deduct resources and schedule delivery
        res.consume_for_action(costs, "Send Resupply")
        current_turn = getattr(sim_context, 'current_turn', 0)
        sim_context.simulation.deferred.schedule_at(
            current_turn + 1, 'resupply_general',
            {'general_id': general.id, 'general_name': general_name,
             'house_id': house.id, 'house_name': house.name,
             'supply_points': supply_points},
            phase='Events', owner_id=house.id
        )
        balance = _balance_line(res, ['gold', 'food'])
        return (f"Resupply convoy dispatched to {general_name} — "
                f"{supply_points} supply points will arrive next turn. "
                f"Cost: {gold} gold, {food} food. {balance}")
    send_resupply.action_description = "**Send Resupply**: Dispatch a supply convoy to a general (arrives next turn, costs gold/food)"
    tools.append(send_resupply)

    # Equip general tool — spend metal to raise equipment level
    @function_tool
    def equip_general(ctx: RunContextWrapper["SimulationContext"], general_name: str, metal: int) -> str:
        """
        Spend metal to equip a deployed general's forces with weapons and armour.
        Every 10 metal raises equipment level by 20 (max 100%).
        Unequipped soldiers fight at only 30% effectiveness; fully equipped at 100%.

        Args:
            general_name: Name of the general to equip
            metal: Metal to spend (minimum 10)
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot equip — no entity manager access"
        from feudal_sim.components.resource import ResourceComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        res: ResourceComponent = house.get_component(ResourceComponent)
        if not res:
            return "Cannot equip — missing resource management"
        if metal < 10:
            return "Minimum 10 metal required to equip"
        costs = {'metal': metal}
        if not res.can_afford_action(costs):
            return f"Insufficient metal (need {metal}, have {res.resources.metal:.0f})"
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                      if getattr(g, 'house_id', None) == house.id and g.name == general_name]
        if not candidates:
            return f"No general named '{general_name}' found"
        general = candidates[0]
        grp: SubAgentGroup = general.get_component(SubAgentGroup)
        if not grp:
            return "Cannot equip — general missing group component"
        points_gained = (metal // 10) * 20
        old_equip = grp.equipment_level
        grp.equipment_level = min(100, grp.equipment_level + points_gained)
        actually_gained = grp.equipment_level - old_equip
        if actually_gained == 0:
            return f"{general_name} is already fully equipped (100%)"
        res.consume_for_action(costs, "Equip General")
        balance = _balance_line(res, ['metal'])
        return (f"Equipped {general_name}: equipment {old_equip}% → {grp.equipment_level}% "
                f"(+{actually_gained}%). Cost: {metal} metal. {balance}")
    equip_general.action_description = "**Equip General**: Spend metal to arm your forces — critical before combat"
    tools.append(equip_general)

    # Update orders for a deployed general — delivered next turn (courier delay)
    @function_tool
    def update_general_orders(ctx: RunContextWrapper["SimulationContext"], general_name: str, orders: str, strategic_intent: str = "") -> str:
        """
        Send new orders to a deployed general. The courier arrives at the start of the
        next turn; the general will follow the new orders from then on.

        Args:
            general_name: Name of the deployed general
            orders: New natural language orders (e.g., "Return home", "Besiege the eastern outpost")
            strategic_intent: Why — the larger goal the general should keep in mind

        Returns:
            Confirmation that the courier was dispatched
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "Cannot send orders — no entity manager access"
        from feudal_sim.components.ai import AIComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                      if getattr(g, 'house_id', None) == house.id and g.name == general_name]
        if not candidates:
            return f"No general named '{general_name}' found"
        general = candidates[0]
        grp: SubAgentGroup = general.get_component(SubAgentGroup)
        if not grp:
            return "Cannot send orders — general missing group component"
        mission_type = "expansion" if "expand" in orders.lower() else grp.mission_parameters.mission_type
        grp.set_mission(mission_type,
                        target_area=grp.mission_parameters.target_area,
                        orders=orders,
                        priority=grp.mission_parameters.priority,
                        strategic_intent=strategic_intent or grp.mission_parameters.strategic_intent,
                        assigned_turn=getattr(sim_context, 'current_turn', 0))
        gen_ai: AIComponent = general.get_component(AIComponent)
        if gen_ai:
            intent_part = f" Strategic intent: {strategic_intent}" if strategic_intent else ""
            gen_ai.add_observation(
                f"New orders from your lord: {orders}.{intent_part}", "Events")
        return (f"Courier dispatched to {general_name} with new orders. "
                f"They will act on them starting next turn.")
    update_general_orders.action_description = "**Update General Orders**: Redirect a deployed general with new orders and intent"
    tools.append(update_general_orders)

    # Military deployment tools
    tools.append(create_deploy_general_tool(house))

    from feudal_sim.components.subagent_group import SubAgentGroup

    @function_tool
    def list_generals(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        List all currently deployed generals for your house with key details.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        mine = sim_context.entity_manager.get_entities_by_house_and_type(house.id, 'general')
        if not mine:
            return "No generals currently deployed"
        reports = []
        for g in mine:
            grp = g.get_component(SubAgentGroup)
            people = grp.assigned_population.total if grp else 0
            morale = grp.morale if grp else None
            supplies = grp.supplies if grp else None
            status = grp.mission_status if grp else "unknown"
            reports.append(f"{g.name} — {people} assigned, morale {morale}%, supplies {supplies}%, status {status}")
        return " | ".join(reports)
    list_generals.action_description = "**List Generals**: See all currently deployed generals and their status"
    tools.append(list_generals)

    # Management: disband a general (recall population and remove unit)
    @function_tool
    def disband_general(ctx: RunContextWrapper["SimulationContext"], general_name: str) -> str:
        """
        Disband a deployed general by name, recalling assigned population.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        # Find general by name and house
        candidates = [g for g in sim_context.entity_manager.get_entities_by_type('general')
                        if getattr(g, 'house_id', None) == house.id and getattr(g, 'name', '') == general_name]
        if not candidates:
            return f"No general found named '{general_name}'"
        g = candidates[0]
        # Schedule disband for Events phase to avoid race conditions via deferred queue
        if hasattr(sim_context, 'simulation') and sim_context.simulation and hasattr(sim_context.simulation, 'deferred'):
            current_turn = getattr(sim_context, 'current_turn', 0)
            sim_context.simulation.deferred.schedule_at(
                current_turn,
                'disband_general',
                {'general_id': g.id, 'general_name': general_name},
                phase='Events',
                owner_id=house.id,
            )
        # Add observation to house AI (scheduled)
        try:
            from feudal_sim.components.ai import AIComponent
            ai: AIComponent = house.get_component(AIComponent)
            if ai:
                ai.add_observation(f"General {general_name} disband scheduled; will complete this week", phase="Actions")
        except Exception:
            pass
        return f"Disband scheduled for '{general_name}'."
    disband_general.action_description = "**Disband General**: Recall a general and return assigned population"
    tools.append(disband_general)

    # City management tools
    tools.append(create_view_cities_tool(house))

    # Shared rookery tools (list only; house already has a specialized send tool)
    tools.extend(create_rookery_toolset(house, include_send=False))

    # Inbox / message history tool
    from feudal_sim.components.rookery import RookeryComponent as _RookeryComponent

    @function_tool
    def check_inbox(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Read received raven messages from other houses. Shows last 5 messages with sender and turn received.
        """
        rookery: _RookeryComponent = house.get_component(_RookeryComponent)
        if not rookery or not rookery.message_history:
            return "No messages in your raven history."
        recent = rookery.message_history[-5:]
        lines = []
        for msg in reversed(recent):
            preview = msg.message[:100] if hasattr(msg, 'message') else str(msg)[:100]
            turn = getattr(msg, 'turn_received', '?')
            sender = getattr(msg, 'sender_name', 'Unknown')
            lines.append(f"From {sender} (Turn {turn}): '{preview}'")
        return "\n".join(lines)
    check_inbox.action_description = "**Check Inbox**: Read received raven messages from other houses"
    tools.append(check_inbox)

    # General status query tool
    @function_tool
    def query_general_status(ctx: RunContextWrapper["SimulationContext"]) -> str:
        """
        Get a full status report of all your deployed generals including position and readiness.
        """
        sim_context = ctx.context
        if not sim_context or not sim_context.entity_manager:
            return "No access to entity manager"
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        mine = sim_context.entity_manager.get_entities_by_house_and_type(house.id, 'general')
        if not mine:
            return "No generals deployed"
        lines = []
        for g in mine:
            pos_comp = g.get_component(PositionComponent)
            grp = g.get_component(SubAgentGroup)
            position = pos_comp.position if pos_comp else "unknown"
            morale = grp.morale if grp else "?"
            supplies = grp.supplies if grp else "?"
            mission_status = grp.mission_status if grp else "unknown"
            mission_type = grp.mission_parameters.mission_type if grp and grp.mission_parameters else "unknown"
            orders = grp.mission_parameters.orders if grp and grp.mission_parameters else "none"
            lines.append(
                f"{g.name} | Position: {position} | Morale: {morale}% | Supplies: {supplies}% "
                f"| Status: {mission_status} | Mission: {mission_type} | Orders: {orders}"
            )
        return "\n".join(lines)
    query_general_status.action_description = "**Query Generals**: Get a full status report of all your deployed generals including position and readiness"
    tools.append(query_general_status)

    # Objective management tools
    @function_tool
    def set_objective(objective: str) -> str:
        """
        Set a new strategic objective. Objectives appear each turn to guide your decisions (max 5).

        Args:
            objective: Description of the objective to add
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot set objective - AI component unavailable"
        if len(ai_comp.current_objectives) >= 5:
            return f"Objective list full (max 5). Remove an objective first. Current: {ai_comp.current_objectives}"
        ai_comp.current_objectives.append(objective)
        return f"Objective added: '{objective}'. Total objectives: {len(ai_comp.current_objectives)}"
    set_objective.action_description = "**Set Objective**: Add a strategic goal that persists across turns (max 5)"
    tools.append(set_objective)

    @function_tool
    def remove_objective(objective: str) -> str:
        """
        Remove a strategic objective by name or partial match.

        Args:
            objective: Objective text or substring to remove
        """
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot remove objective - AI component unavailable"
        before = list(ai_comp.current_objectives)
        ai_comp.current_objectives = [o for o in ai_comp.current_objectives if objective.lower() not in o.lower()]
        removed = [o for o in before if o not in ai_comp.current_objectives]
        if removed:
            return f"Removed: {removed}. Remaining: {ai_comp.current_objectives}"
        return f"No matching objective found for '{objective}'. Current: {ai_comp.current_objectives}"
    remove_objective.action_description = "**Remove Objective**: Remove a strategic goal by name or partial match"
    tools.append(remove_objective)

    @function_tool
    def list_objectives() -> str:
        """List all current strategic objectives."""
        from feudal_sim.components.ai import AIComponent
        ai_comp: AIComponent = house.get_component(AIComponent)
        if not ai_comp:
            return "Cannot list objectives - AI component unavailable"
        if not ai_comp.current_objectives:
            return "No objectives currently set."
        return "Current objectives:\n" + "\n".join(f"  - {o}" for o in ai_comp.current_objectives)
    list_objectives.action_description = "**List Objectives**: View all current strategic objectives"
    tools.append(list_objectives)

    # Universal tools
    tools.append(end_turn)

    # Trade caravan tools
    tools.append(create_send_trade_caravan_tool(house))

    # War diplomacy tools
    tools.append(create_declare_war_tool(house))
    tools.append(create_sue_for_peace_tool(house))

    return tools
