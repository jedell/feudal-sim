"""
Priority Action Handlers

Concrete implementations of priority action handlers for different event types.
Each handler defines the specific context, tools, and resolution mechanics
for their particular type of urgent situation.
"""

from typing import List, Dict, Any
from agents import function_tool

from feudal_sim.core.priority_actions import PriorityActionHandler, PriorityActionEvent
from feudal_sim.core.logger import get_logger

log = get_logger(__name__)


class TradeCaravanHandler(PriorityActionHandler):
    """
    Handler for trade caravan arrival events.
    
    Manages negotiations between house lords when a trade caravan arrives,
    including tools for accepting, rejecting, or negotiating trade terms.
    """
    
    def generate_context_message(self, event: PriorityActionEvent, agent_id: str) -> str:
        """Generate context message for trade caravan arrival."""
        caravan_data = event.context_data.get('caravan', {})
        sending_house = event.context_data.get('sending_house', {})
        receiving_house = event.context_data.get('receiving_house', {})
        
        # Get caravan details
        caravan_contents = caravan_data.get('contents', 'unknown goods')
        proposed_terms = caravan_data.get('proposed_terms', 'trade proposal')
        sender_name = sending_house.get('name', 'Unknown House') if sending_house else 'Unknown House'
        
        # Scarcity-aware valuation for this agent's eyes, if priced at dispatch
        valuation = event.context_data.get('valuations', {}).get(agent_id)
        value_note = f" You value this cargo at ~{valuation:.0f} given your current stocks." if valuation else ""

        # Different messages for sender vs receiver
        if agent_id == event.context_data.get('sending_house', {}).get('id'):
            # Message for the house that sent the caravan
            return f"🚚 URGENT: Your trade caravan has arrived at {receiving_house.get('name', 'the destination')}! Contents: {caravan_contents}. Your proposed terms: '{proposed_terms}'.{value_note} Await their response or negotiate."
        else:
            # Message for the receiving house
            return f"🚚 URGENT: Trade caravan from {sender_name} has arrived! Contents: {caravan_contents}. They propose: '{proposed_terms}'.{value_note} You may negotiate, accept, reject, or seize the goods."
    
    def get_situation_guidance(self, event, agent_id: str) -> str:
        cd = event.context_data
        if agent_id == cd.get('receiving_house', {}).get('id'):
            sender = cd.get('sending_house', {}).get('name', 'the sender')
            return (
                f"A trade caravan from {sender} has arrived. This event requires your decision.\n"
                f"• Use speak() to negotiate terms with {sender} (messages go to them directly)\n"
                f"• Call trade_decision('accept'/'reject'/'counter'/'seize') to resolve the event\n"
                f"• The event does NOT close until trade_decision() is called"
            )
        else:
            recipient = cd.get('receiving_house', {}).get('name', 'the recipient')
            return (
                f"Your trade caravan has arrived at {recipient}. Await their response or negotiate.\n"
                f"• Use speak() to make your case to {recipient}\n"
                f"• Call trade_negotiation('withdraw'/'accept_counter'/'modify_terms') if needed\n"
                f"• The event closes when {recipient} calls trade_decision() or you withdraw"
            )

    def create_conversation_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create conversation tools for trade negotiations."""
        return []
    
    def create_resolution_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create resolution tools for trade decisions."""
        tools = []
        
        # Different tools based on agent role
        caravan_owner_id = event.context_data.get('sending_house', {}).get('id')
        receiving_house_id = event.context_data.get('receiving_house', {}).get('id')
        
        if agent_id == receiving_house_id:
            # Receiving house gets decision tools
            @function_tool
            def trade_decision(decision: str, terms: str = "") -> str:
                """
                Make final decision about the trade caravan.
                
                Args:
                    decision: Your decision - 'accept', 'reject', 'counter', or 'seize'
                    terms: Additional terms or conditions (for counter offers)
                """
                if decision not in ['accept', 'reject', 'counter', 'seize']:
                    return "Invalid decision. Must be: accept, reject, counter, or seize"
                
                # Store resolution data
                event.context_data['trade_decision'] = {
                    'decision': decision,
                    'terms': terms,
                    'deciding_agent': agent_id
                }
                event.is_resolved = True
                
                if decision == 'accept':
                    return f"Trade accepted: {terms}" if terms else "Trade accepted with original terms"
                elif decision == 'reject':
                    return f"Trade rejected: {terms}" if terms else "Trade rejected"
                elif decision == 'counter':
                    return f"Counter-offer made: {terms}"
                elif decision == 'seize':
                    return f"Caravan seized: {terms}" if terms else "Caravan goods seized by force"
            
            tools.append(trade_decision)
            
        elif agent_id == caravan_owner_id:
            # Sending house gets negotiation tools
            @function_tool
            def trade_negotiation(action: str, terms: str = "") -> str:
                """
                Respond to trade negotiations as the caravan owner.
                
                Args:
                    action: Your action - 'withdraw', 'accept_counter', 'modify_terms'
                    terms: New terms or conditions (if modifying)
                """
                if action not in ['withdraw', 'accept_counter', 'modify_terms']:
                    return "Invalid action. Must be: withdraw, accept_counter, or modify_terms"
                
                # Store negotiation data
                event.context_data['trade_negotiation'] = {
                    'action': action,
                    'terms': terms,
                    'negotiating_agent': agent_id
                }
                
                if action == 'withdraw':
                    event.is_resolved = True
                    return "Caravan withdrawn - trade cancelled"
                elif action == 'accept_counter':
                    event.is_resolved = True
                    return f"Counter-offer accepted: {terms}" if terms else "Counter-offer accepted"
                elif action == 'modify_terms':
                    return f"Terms modified: {terms}"
            
            tools.append(trade_negotiation)
        
        return tools
    
    def execute_resolution(self, event: PriorityActionEvent, resolution_data: Dict[str, Any]) -> str:
        """Execute the trade resolution based on agent decisions."""
        trade_decision = event.context_data.get('trade_decision')
        trade_negotiation = event.context_data.get('trade_negotiation')

        if trade_decision:
            decision = trade_decision['decision']
            terms = trade_decision.get('terms', '')
            
            if decision == 'accept':
                # Execute successful trade
                result = self._execute_successful_trade(event, terms)
                return f"Trade completed successfully. {result} {terms}".strip()
            elif decision == 'reject':
                # Trade rejected - caravan returns
                self._return_caravan(event)
                return f"Trade rejected. Caravan returning to sender. {terms}" if terms else "Trade rejected. Caravan returning to sender."
            elif decision == 'seize':
                # Hostile action - seize goods by force
                result = self._execute_caravan_seizure(event, terms)
                return f"Caravan goods seized by force! {result} This may have diplomatic consequences. {terms}".strip()
            elif decision == 'counter':
                # Counter offer made - wait for response or timeout
                return f"Counter-offer made: {terms}. Awaiting caravan owner response."
        
        if trade_negotiation:
            action = trade_negotiation['action']
            terms = trade_negotiation.get('terms', '')
            
            if action == 'withdraw':
                self._return_caravan(event)
                return "Trade cancelled - caravan has withdrawn."
            elif action == 'accept_counter':
                result = self._execute_successful_trade(event, terms)
                return f"Trade completed with negotiated terms: {result} {terms}".strip()
        
        # Default fallback
        return "Trade negotiation concluded."
    
    def _transfer_cargo(self, event: PriorityActionEvent, recipient_house_id: str) -> str:
        """Transfer caravan cargo to a house's resource store. Returns summary string."""
        from feudal_sim.components.cargo import CargoComponent
        from feudal_sim.components.resource import ResourceComponent

        entity_manager = event.context_data.get('entity_manager')
        caravan_id = event.context_data.get('caravan', {}).get('id')
        if not entity_manager or not caravan_id:
            return "goods transferred."

        caravan = entity_manager.get_entity(caravan_id)
        recipient = entity_manager.get_entity(recipient_house_id)
        if not caravan or not recipient:
            return "goods transferred."

        cargo_comp = caravan.get_component(CargoComponent)
        recipient_res = recipient.get_component(ResourceComponent)
        if not cargo_comp or not recipient_res:
            return "goods transferred."

        goods = cargo_comp.cargo
        transferred = []
        for resource in ('food', 'material', 'metal', 'gold'):
            amount = getattr(goods, resource, 0.0)
            if amount > 0:
                recipient_res.resources.add(resource, amount)
                transferred.append(f"+{amount:.0f} {resource}")

        # Mark cargo delivered and remove caravan
        arrival_turn = event.context_data.get('arrival_turn', 0)
        cargo_comp.complete_trade("accepted", arrival_turn)
        try:
            entity_manager.destroy_entity(caravan_id)
        except Exception as _e:
            log.warning(f"⚠️  {_e}")

        # Journal the delivery on the recipient lord
        if transferred:
            from feudal_sim.components.ai import AIComponent
            recipient_ai = recipient.get_component(AIComponent)
            if recipient_ai:
                sender_name = event.context_data.get('sending_house', {}).get('name', 'unknown house')
                recipient_ai.record_journal_entry(
                    f"Caravan from {sender_name} delivered: {', '.join(transferred)}")

        return (f"{', '.join(transferred)} delivered to {recipient.name}."
                if transferred else "caravan arrived with no goods.")

    def _execute_successful_trade(self, event: PriorityActionEvent, terms: str) -> str:
        """Transfer caravan goods to the receiving house."""
        receiving_house_id = event.context_data.get('receiving_house', {}).get('id')
        return self._transfer_cargo(event, receiving_house_id)

    def _execute_caravan_seizure(self, event: PriorityActionEvent, terms: str) -> str:
        """Seize caravan goods — transferred to receiving house by force."""
        receiving_house_id = event.context_data.get('receiving_house', {}).get('id')
        summary = self._transfer_cargo(event, receiving_house_id)
        return f"Seized by force: {summary}"

    def _return_caravan(self, event: PriorityActionEvent):
        """Return caravan goods to the sender."""
        sending_house_id = event.context_data.get('sending_house', {}).get('id')
        self._transfer_cargo(event, sending_house_id)


class DiplomaticSummitHandler(PriorityActionHandler):
    """
    Handler for diplomatic summit events.
    
    Manages multi-party diplomatic negotiations including alliance formation,
    peace treaties, and trade agreements.
    """
    
    def generate_context_message(self, event: PriorityActionEvent, agent_id: str) -> str:
        """Generate context message for diplomatic summit."""
        summit_type = event.context_data.get('summit_type', 'diplomatic meeting')
        host_house = event.context_data.get('host_house', {})
        participants = event.context_data.get('participants', [])
        agenda = event.context_data.get('agenda', 'general diplomatic matters')
        
        host_name = host_house.get('name', 'Unknown House') if host_house else 'Unknown House'
        participant_names = [p.get('name', 'Unknown') for p in participants]
        
        return f"🏛️ URGENT: Diplomatic summit convened by {host_name}! Type: {summit_type}. Participants: {', '.join(participant_names)}. Agenda: {agenda}. Your participation is required."
    
    def create_conversation_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create conversation tools for diplomatic negotiations."""
        # Diplomatic summits rely heavily on the speak() tool from ConversationManager
        return []
    
    def create_resolution_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create resolution tools for diplomatic decisions."""
        @function_tool
        def diplomatic_decision(decision: str, terms: str = "") -> str:
            """
            Make your diplomatic decision for this summit.
            
            Args:
                decision: Your decision - 'agree', 'decline', 'propose_alternative', 'withdraw'
                terms: Details of your decision or alternative proposal
            """
            if decision not in ['agree', 'decline', 'propose_alternative', 'withdraw']:
                return "Invalid decision. Must be: agree, decline, propose_alternative, or withdraw"
            
            # Store diplomatic decision
            if 'diplomatic_decisions' not in event.context_data:
                event.context_data['diplomatic_decisions'] = {}
            
            event.context_data['diplomatic_decisions'][agent_id] = {
                'decision': decision,
                'terms': terms
            }
            
            # Check if all participants have decided
            if len(event.context_data['diplomatic_decisions']) >= len(event.involved_agents):
                event.is_resolved = True
            
            return f"Diplomatic decision recorded: {decision}. {terms}" if terms else f"Diplomatic decision recorded: {decision}"
        
        return [diplomatic_decision]
    
    def execute_resolution(self, event: PriorityActionEvent, resolution_data: Dict[str, Any]) -> str:
        """Execute diplomatic summit resolution."""
        decisions = event.context_data.get('diplomatic_decisions', {})
        
        if not decisions:
            return "Diplomatic summit concluded without clear decisions."
        
        # Analyze decisions
        agree_count = sum(1 for d in decisions.values() if d['decision'] == 'agree')
        decline_count = sum(1 for d in decisions.values() if d['decision'] == 'decline')
        
        if agree_count == len(decisions):
            return "Diplomatic agreement reached! All parties have agreed to the terms."
        elif decline_count > 0:
            return f"Diplomatic agreement failed. {decline_count} parties declined the proposal."
        else:
            return "Diplomatic summit concluded with mixed results. Further negotiations may be needed."


class EnemyEncounterHandler(PriorityActionHandler):
    """
    Handler for enemy encounter events.
    
    Manages situations where military units encounter enemy forces,
    requiring immediate tactical decisions.
    """
    
    def generate_context_message(self, event: PriorityActionEvent, agent_id: str) -> str:
        """Generate context message for enemy encounter."""
        enemy_force = event.context_data.get('enemy_force', {})
        location = event.context_data.get('location', 'unknown location')
        
        enemy_size = enemy_force.get('size', 'unknown size')
        enemy_house = enemy_force.get('house', 'unknown house')
        
        return f"⚔️ URGENT: Enemy encounter at {location}! Enemy forces ({enemy_size}) from {enemy_house} detected. Immediate tactical decision required."
    
    def create_conversation_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create conversation tools for tactical coordination."""
        return []  # Enemy encounters typically don't involve conversation
    
    def create_resolution_tools(self, event: PriorityActionEvent, agent_id: str) -> List:
        """Create resolution tools for tactical decisions."""
        @function_tool
        def tactical_decision(decision: str, details: str = "") -> str:
            """
            Make tactical decision for this enemy encounter.
            
            Args:
                decision: Your tactical decision - 'attack', 'defend', 'retreat', 'parley'
                details: Additional tactical details or conditions
            """
            if decision not in ['attack', 'defend', 'retreat', 'parley']:
                return "Invalid tactical decision. Must be: attack, defend, retreat, or parley"
            
            # Store tactical decision
            event.context_data['tactical_decision'] = {
                'decision': decision,
                'details': details,
                'deciding_agent': agent_id
            }
            event.is_resolved = True
            
            return f"Tactical decision: {decision}. {details}" if details else f"Tactical decision: {decision}"
        
        return [tactical_decision]
    
    def execute_resolution(self, event: PriorityActionEvent, resolution_data: Dict[str, Any]) -> str:
        """Execute enemy encounter resolution."""
        tactical_decision = event.context_data.get('tactical_decision')
        
        if not tactical_decision:
            return "Enemy encounter resolved without clear tactical decision."
        
        decision = tactical_decision['decision']
        details = tactical_decision.get('details', '')
        
        if decision == 'attack':
            return f"Battle initiated! {details}" if details else "Battle initiated against enemy forces!"
        elif decision == 'defend':
            return f"Defensive position taken. {details}" if details else "Defensive position taken against enemy forces."
        elif decision == 'retreat':
            return f"Tactical retreat executed. {details}" if details else "Forces have withdrawn from enemy contact."
        elif decision == 'parley':
            return f"Parley attempt made. {details}" if details else "Attempting to negotiate with enemy forces."
        
        return "Enemy encounter concluded."

class GeneralContactHandler(PriorityActionHandler):
    """
    Handler for general-to-general contact events.

    Two opposing generals have come within 1 tile of each other.
    Both participate in a short parley conversation, then each declares
    a tactic. Combat resolves immediately, applying casualties and
    triggering post-battle raven reports to their respective lords.

    context_data keys:
      attacker_id, attacker_name, attacker_house_id, attacker_house_name,
      attacker_soldiers, attacker_equip, attacker_morale,
      defender_id, defender_name, defender_house_id, defender_house_name,
      defender_soldiers, defender_equip, defender_morale,
      terrain_type,          # HexTileType.name string
      is_ambush,             # bool — defender is the ambush victim
      entity_manager,        # runtime reference for applying results
      hex_grid,
    """

    def generate_context_message(self, event, agent_id: str) -> str:
        cd = event.context_data
        is_ambush = cd.get('is_ambush', False)

        if agent_id == cd.get('attacker_id'):
            enemy_name  = cd.get('defender_name', 'enemy forces')
            enemy_house = cd.get('defender_house_name', 'an opposing house')
            enemy_sol   = cd.get('defender_soldiers', '?')
            terrain     = cd.get('terrain_type', 'open ground').lower().replace('_', ' ')
            if is_ambush:
                return (
                    f"⚔️  AMBUSH SPRUNG: You have launched a surprise attack on {enemy_name} of "
                    f"House {enemy_house} ({enemy_sol} soldiers) at {terrain}. "
                    f"Your forces have the element of surprise — the enemy cannot prepare. "
                    f"Declare your tactic now."
                )
            return (
                f"⚔️  CONTACT: Your forces have encountered {enemy_name} of House {enemy_house} "
                f"({enemy_sol} soldiers) at {terrain}. "
                f"You may parley before committing. Declare your intent."
            )
        else:
            enemy_name  = cd.get('attacker_name', 'enemy forces')
            enemy_house = cd.get('attacker_house_name', 'an opposing house')
            enemy_sol   = cd.get('attacker_soldiers', '?')
            terrain     = cd.get('terrain_type', 'open ground').lower().replace('_', ' ')
            if is_ambush:
                return (
                    f"⚔️  AMBUSH — You have walked into a prepared position! "
                    f"{enemy_name} of House {enemy_house} ({enemy_sol} soldiers) has sprung an "
                    f"ambush at {terrain}. Your options are limited. "
                    f"You may defend, withdraw, or surrender."
                )
            return (
                f"⚔️  CONTACT: {enemy_name} of House {enemy_house} ({enemy_sol} soldiers) "
                f"has been sighted at {terrain}. "
                f"You may parley or declare your intent."
            )

    def get_situation_guidance(self, event, agent_id: str) -> str:
        cd = event.context_data
        is_ambush = cd.get('is_ambush', False)
        is_attacker = (agent_id == cd.get('attacker_id'))
        enemy = cd.get('defender_name' if is_attacker else 'attacker_name', 'the enemy')

        if is_ambush and not is_attacker:
            return (
                f"AMBUSH — you have been surprised. Your options are limited.\n"
                f"• IMPORTANT: declare_tactic() is required to resolve this event — speak() alone does nothing\n"
                f"• speak() sends a message to {enemy} — use it briefly, then commit to a tactic\n"
                f"• Tactic outcomes:\n"
                f"    withdraw  → disengage and retreat (avoids combat, no morale cost)\n"
                f"    defensive → hold ground (COMBAT WILL HAPPEN)\n"
                f"    surrender → yield completely (no casualties, major morale loss)"
            )
        return (
            f"CONTACT EVENT with {enemy}. How this works:\n"
            f"\n"
            f"• speak() sends a message directly to {enemy} — use it to negotiate\n"
            f"• declare_tactic() is REQUIRED to close this event — both generals must call it\n"
            f"• IMPORTANT: declare_tactic() ends your turn immediately. "
            f"You cannot speak after declaring. Say everything you need to via speak() FIRST, then declare.\n"
            f"• WARNING: speak() agreements are purely diplomatic. They have NO mechanical effect.\n"
            f"  If you agree to peace in speak() but declare_tactic('defensive'), COMBAT STILL HAPPENS.\n"
            f"\n"
            f"Tactic → outcome mapping:\n"
            f"  withdraw   → you disengage and pull back. No combat. No morale cost.\n"
            f"  surrender  → you yield. No combat. Major morale loss.\n"
            f"  defensive  → you hold ground. COMBAT HAPPENS. Good vs assault.\n"
            f"  assault    → you charge. COMBAT HAPPENS. Risky but decisive.\n"
            f"  flanking   → you attempt to outmanoeuvre. COMBAT HAPPENS. Beats defensive.\n"
            f"  feint      → fake retreat to draw pursuit. COMBAT HAPPENS if enemy advances.\n"
            f"\n"
            f"If you negotiated peace via speak(), you MUST declare_tactic('withdraw') to honour it."
        )

    def create_conversation_tools(self, event, agent_id: str) -> List:
        return []  # speak() tool provided by ConversationManager

    def create_resolution_tools(self, event, agent_id: str) -> List:
        tools = []
        cd = event.context_data
        is_ambush   = cd.get('is_ambush', False)
        attacker_id = cd.get('attacker_id')
        is_attacker = (agent_id == attacker_id)

        allowed_tactics = ['assault', 'flanking', 'defensive', 'feint', 'withdraw', 'surrender']
        if is_ambush and not is_attacker:
            allowed_tactics = ['defensive', 'withdraw', 'surrender']

        @function_tool
        def declare_tactic(tactic: str, battle_cry: str = "") -> str:
            """
            Commit to a tactical approach for this engagement.
            Tactics: assault, flanking, defensive, feint, withdraw, surrender.
            assault   — all-out attack (+attack, +own casualties if losing)
            flanking  — attempt to outmanoeuvre (+attack if undetected)
            defensive — hold ground (+defence)
            feint     — simulate retreat to draw the enemy (+bonus if they advance)
            withdraw  — disengage without fighting (costs morale, avoids battle)
            surrender — yield the field (no casualties, but major morale/diplomatic cost)
            """
            t = tactic.lower().strip()
            if t not in allowed_tactics:
                return f"Invalid tactic '{tactic}'. Choose from: {', '.join(allowed_tactics)}"

            key = 'attacker_tactic' if is_attacker else 'defender_tactic'
            cd[key] = t
            if battle_cry:
                cd.setdefault('battle_cries', {})[agent_id] = battle_cry

            # Mark this agent as resolved
            cd.setdefault('resolved_agents', set()).add(agent_id)
            all_agents = set(event.involved_agents)
            if all_agents.issubset(cd.get('resolved_agents', set())):
                event.is_resolved = True

            flavour = {
                'assault':   "Your forces prepare to charge.",
                'flanking':  "Your scouts move to find an angle of attack.",
                'defensive': "Your line holds firm.",
                'feint':     "You begin a deliberate, ordered withdrawal to draw pursuit.",
                'withdraw':  "You disengage and pull back from contact.",
                'surrender': "You lower your colours and send a herald forward.",
            }
            return flavour.get(t, f"Tactic declared: {t}.")

        tools.append(declare_tactic)
        return tools

    def execute_resolution(self, event, resolution_data: Dict[str, Any]) -> str:
        from feudal_sim.core.combat import resolve_combat
        from feudal_sim.map.types import HexTileType

        cd = event.context_data
        em = cd.get('entity_manager')
        if not em:
            return "Contact event concluded (no entity manager for resolution)."

        a_id = cd.get('attacker_id')
        d_id = cd.get('defender_id')
        a_tactic = cd.get('attacker_tactic', 'assault')
        d_tactic = cd.get('defender_tactic', 'defensive')
        is_ambush = cd.get('is_ambush', False)

        # Surrender short-circuit
        if a_tactic == 'surrender':
            self._apply_surrender(event, loser_id=a_id, winner_id=d_id, em=em)
            return f"{cd.get('attacker_name')} has surrendered to {cd.get('defender_name')}."
        if d_tactic == 'surrender':
            self._apply_surrender(event, loser_id=d_id, winner_id=a_id, em=em)
            return f"{cd.get('defender_name')} has surrendered to {cd.get('attacker_name')}."

        # Mutual withdraw — no engagement
        if a_tactic == 'withdraw' and d_tactic == 'withdraw':
            return "Both forces disengaged without fighting."

        # Get terrain
        terrain_str = cd.get('terrain_type', '')
        terrain_type = None
        try:
            terrain_type = HexTileType[terrain_str] if terrain_str else None
        except KeyError:
            pass

        result = resolve_combat(
            attacker_soldiers=cd.get('attacker_soldiers', 1),
            attacker_equip=cd.get('attacker_equip', 0),
            attacker_morale=cd.get('attacker_morale', 100),
            defender_soldiers=cd.get('defender_soldiers', 1),
            defender_equip=cd.get('defender_equip', 0),
            defender_morale=cd.get('defender_morale', 100),
            attacker_tactic=a_tactic,
            defender_tactic=d_tactic,
            terrain_type=terrain_type,
            ambush=is_ambush,
        )

        # Apply casualties
        loser_id  = d_id if result.attacker_wins else a_id
        self._apply_combat_result(event, result, em)

        # Loser retreats
        self._retreat_general(loser_id, em)

        # Both generals send ravens to their lords
        self._send_battle_ravens(event, result, em)

        outcome = "victory" if result.attacker_wins else "defeat"
        decisive = " (decisive)" if result.was_decisive else ""
        return (
            f"Battle resolved{decisive}: {cd.get('attacker_name')} — {outcome}. "
            f"Attacker lost {result.attacker_casualties}, defender lost {result.defender_casualties}."
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _apply_combat_result(self, event, result, em):
        from feudal_sim.components.subagent_group import SubAgentGroup
        cd = event.context_data
        for gen_id, casualties, final_soldiers, won in [
            (cd['attacker_id'], result.attacker_casualties, result.attacker_final_soldiers, result.attacker_wins),
            (cd['defender_id'], result.defender_casualties, result.defender_final_soldiers, not result.attacker_wins),
        ]:
            gen = em.get_entity(gen_id)
            if not gen:
                continue
            grp = gen.get_component(SubAgentGroup)
            if grp:
                grp.assigned_population.soldiers = max(0, final_soldiers)
                morale_change = 10 if won else (-25 if result.was_decisive else -15)
                grp.adjust_morale(morale_change)
                grp.experience += 3 if won else 1
                grp.in_contact_event = False

    def _apply_surrender(self, event, loser_id: str, winner_id: str, em):
        from feudal_sim.components.subagent_group import SubAgentGroup
        loser = em.get_entity(loser_id)
        if loser:
            grp = loser.get_component(SubAgentGroup)
            if grp:
                grp.adjust_morale(-40)
                grp.in_contact_event = False
        winner = em.get_entity(winner_id)
        if winner:
            grp = winner.get_component(SubAgentGroup)
            if grp:
                grp.in_contact_event = False

    def _retreat_general(self, loser_id: str, em):
        """Move loser 2 tiles back toward their home territory."""
        from feudal_sim.components.position import PositionComponent
        from feudal_sim.components.subagent_group import SubAgentGroup
        from feudal_sim.components.territory import TerritoryComponent
        gen = em.get_entity(loser_id)
        if not gen:
            return
        pos = gen.get_component(PositionComponent)
        grp = gen.get_component(SubAgentGroup)
        if not pos or not pos.position or not grp:
            return
        parent = em.get_entity(grp.parent_house_id)
        if not parent:
            return
        terr = parent.get_component(TerritoryComponent)
        if not terr or not terr.territory:
            return
        # Find closest home tile and move toward it (2 steps)
        q, r = pos.position
        best_dist = float('inf')
        target = None
        for tile in terr.territory:
            d = (abs(q - tile.q) + abs(r - tile.r) + abs((-q - r) - (-tile.q - tile.r))) // 2
            if d < best_dist:
                best_dist = d
                target = (tile.q, tile.r)
        if target:
            # Simple interpolation toward target
            tq, tr = target
            step_q = max(-1, min(1, tq - q))
            step_r = max(-1, min(1, tr - r))
            pos.position = (q + step_q * 2, r + step_r * 2)

    def _send_battle_ravens(self, event, result, em):
        """Each general sends a raven to their lord describing the battle."""
        from feudal_sim.components.rookery import RookeryComponent
        cd = event.context_data

        reports = [
            (cd.get('attacker_id'), cd.get('attacker_house_id'),
             cd.get('attacker_name'), cd.get('defender_name'), result.attacker_wins,
             result.attacker_casualties, result.defender_casualties),
            (cd.get('defender_id'), cd.get('defender_house_id'),
             cd.get('defender_name'), cd.get('attacker_name'), not result.attacker_wins,
             result.defender_casualties, result.attacker_casualties),
        ]
        for gen_id, house_id, gen_name, enemy_name, won, own_cas, enemy_cas in reports:
            gen = em.get_entity(gen_id)
            house = em.get_entity(house_id)
            if not gen or not house:
                continue
            outcome_word = "victory" if won else "defeat"
            # Record the battle in the lord's realm journal so the outcome
            # survives message-history compaction
            from feudal_sim.components.ai import AIComponent
            house_ai = house.get_component(AIComponent)
            if house_ai:
                house_ai.record_journal_entry(
                    f"Battle: {gen_name} vs {enemy_name} — {outcome_word}, "
                    f"lost {own_cas} soldiers (enemy lost {enemy_cas})")
            rookery = gen.get_component(RookeryComponent)
            if not rookery:
                continue
            decisive_note = " — the engagement was decisive" if result.was_decisive else ""
            msg = (
                f"Field report: engaged {enemy_name} at {cd.get('terrain_type','?').lower()}{decisive_note}. "
                f"Outcome: {outcome_word}. Our losses: {own_cas}. Enemy losses: {enemy_cas}. "
                f"{'Holding the field.' if won else 'We have withdrawn.'}"
            )
            if house_id in rookery.get_known_recipients_list():
                rookery.send_raven(house_id, msg)
