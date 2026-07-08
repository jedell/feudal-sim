# Priority Action System Implementation Plan

## Overview

This document outlines the implementation plan for the Priority Action System - a seamless event-driven mechanism that allows AI agents to handle urgent situations (like trade caravan arrivals, diplomatic summits, enemy encounters) within their normal conversation flow while having access to specialized tools and structured outputs.

## System Architecture

The Priority Action System integrates into the existing AI decision-making flow without breaking the agent's message history continuity. Agents experience priority actions as natural extensions of their turn where they temporarily have different tools available.

## Core Components

### 1. PriorityActionEvent Data Structure
**File:** `feudal_sim/core/priority_actions.py` (NEW FILE)
**Integration Point:** New core system component

```python
@dataclass
class PriorityActionEvent:
    event_id: str
    event_type: str  # "trade_caravan_arrival", "diplomatic_summit", etc.
    context_data: Dict[str, Any]
    
    # Participants
    involved_agents: List[str]  # Entity IDs
    allows_conversation: bool = False
    max_conversation_rounds: int = 3
    
    # Resolution
    resolution_tools: Dict[str, List[str]]  # agent_id -> [tool_names]
    is_resolved: bool = False
    resolution_outcome: str = ""
    created_turn: int = 0
```

### 2. PriorityActionEventProcessor
**File:** `feudal_sim/core/priority_actions.py` (NEW FILE)
**Integration Point:** New core system component

```python
class PriorityActionEventProcessor:
    def __init__(self, simulation):
        self.simulation = simulation
        self.active_events: List[PriorityActionEvent] = []
        self.resolution_handlers: Dict[str, PriorityActionHandler] = {}
    
    async def process_all_events(self) -> List[str]
    async def process_single_event(self, event: PriorityActionEvent) -> str
    def _add_context_to_agents(self, event: PriorityActionEvent)
    async def _handle_conversation(self, event: PriorityActionEvent)
    async def _get_resolution_decisions(self, event: PriorityActionEvent)
```

## Integration Points

### 1. Simulation Class Modifications
**File:** `feudal_sim/core/simulation.py`
**Lines to modify:** 22-51, 210-321

#### A. Constructor Addition (Line ~45)
```python
# Add after self.setup_event_listeners()
self.priority_processor = PriorityActionEventProcessor(self)
```

#### B. Actions Phase Modification (Line 210-321)
Replace existing `execute_actions_phase()` with:

```python
async def execute_actions_phase(self):
    """Handle AI decisions and actions, including priority action events."""
    
    # ... existing setup code from lines 212-276 ...
    
    # NEW: Process priority action events BEFORE normal decisions
    print("🎯 Processing priority action events...")
    priority_results = await self.priority_processor.process_all_events()
    for result in priority_results:
        print(f"   {result}")
    
    # ... existing entity decision code from lines 277-321 ...
```

### 2. AIComponent Class Modifications  
**File:** `feudal_sim/components/ai.py`
**Lines to modify:** None (no changes needed!)

The AIComponent requires **NO MODIFICATIONS** as the priority action system works by:
1. Adding messages directly to existing `self.messages` (line 274, 340, 402)
2. Using existing `make_decisions()` method (line 320)
3. Leveraging existing message history and context systems

### 3. New Priority Action Handler System
**File:** `feudal_sim/core/priority_action_handlers.py` (NEW FILE)

```python
class PriorityActionHandler(ABC):
    @abstractmethod
    def generate_context_message(self, event: PriorityActionEvent) -> str
    
    @abstractmethod
    def create_conversation_tools(self, event: PriorityActionEvent, agent_id: str) -> List
    
    @abstractmethod
    def create_resolution_tools(self, event: PriorityActionEvent, agent_id: str) -> List
    
    @abstractmethod
    def execute_resolution(self, event: PriorityActionEvent, resolution_data: Dict[str, Any])
```

### 4. Agent-to-Agent Conversation System
**File:** `feudal_sim/core/conversation_manager.py` (NEW FILE)
**Integration Point:** Core conversation handling within priority actions

The conversation system enables seamless agent-to-agent communication during priority actions. Each agent experiences the conversation from their own perspective, with messages from other agents appearing as `user` role messages.

```python
class ConversationManager:
    def __init__(self, event: PriorityActionEvent):
        self.event = event
        self.conversation_log = []
        self.round_counter = 0
        self.agents_spoken_this_round = set()
    
    def create_speak_tool(self, speaker_agent_id: str):
        """Create agent-specific speak tool for conversations"""
        @function_tool
        def speak(message: str) -> str:
            """
            Speak to other participants in this negotiation.
            Your message will be delivered to all other parties involved.
            """
            # Log conversation
            speaker_entity = self._get_entity(speaker_agent_id)
            speaker_name = speaker_entity.name if speaker_entity else speaker_agent_id
            
            # Add to conversation log
            self.conversation_log.append({
                'speaker_id': speaker_agent_id,
                'speaker_name': speaker_name,
                'message': message,
                'round': self.round_counter
            })
            
            # Deliver to other participants
            for recipient_id in self.event.involved_agents:
                if recipient_id != speaker_agent_id:
                    self._deliver_message_to_agent(recipient_id, speaker_name, message)
            
            return f"You said: '{message}' - Message delivered to all participants."
        
        return speak
    
    def _deliver_message_to_agent(self, recipient_id: str, speaker_name: str, message: str):
        """Deliver conversation message to recipient's message history"""
        recipient_entity = self._get_entity(recipient_id)
        if not recipient_entity:
            return
        
        ai_component = recipient_entity.get_component(AIComponent)
        if not ai_component:
            return
        
        # Format message with round context for clarity
        formatted_message = f"{speaker_name} says to you"
        if self.round_counter > 0:
            formatted_message += f" (Round {self.round_counter + 1})"
        formatted_message += f": '{message}'"
        
        # Add to recipient's message history as user message
        ai_component.messages.append({
            "role": "user",
            "content": formatted_message
        })
    
    def get_conversation_summary(self) -> str:
        """Generate conversation summary for context"""
        if not self.conversation_log:
            return "No conversation yet."
        
        summary_parts = []
        for entry in self.conversation_log[-3:]:  # Last 3 messages
            summary_parts.append(f"{entry['speaker_name']}: {entry['message']}")
        
        return "Recent conversation: " + " | ".join(summary_parts)
```

#### **Conversation Flow Integration:**
```python
# In PriorityActionEventProcessor._handle_conversation()
async def _handle_conversation_round(self, event: PriorityActionEvent, round_num: int):
    """Handle one round of multi-agent conversation"""
    
    conversation_manager = ConversationManager(event)
    conversation_manager.round_counter = round_num
    
    # Each agent gets a turn to speak
    for agent_id in event.involved_agents:
        if event.is_resolved:
            break
            
        entity = self.simulation.entity_manager.get_entity(agent_id)
        ai_component = entity.get_component(AIComponent)
        
        # Create conversation tools (speak + resolution)
        conversation_tools = [
            conversation_manager.create_speak_tool(agent_id),
            *self._create_resolution_tools(event, agent_id)
        ]
        
        # Add turn prompt
        ai_component.messages.append({
            "role": "user",
            "content": f"Your turn to speak in the negotiation (Round {round_num + 1}/{event.max_conversation_rounds}). Use speak() to communicate or a resolution tool to conclude."
        })
        
        # Get agent response
        await self._get_agent_response_with_tools(ai_component, conversation_tools)
    
    return not event.is_resolved
```

#### **Message History Examples:**

**Agent A (House Stark) sees:**
```json
[
  {"role": "user", "content": "🚚 URGENT: Trade caravan from House Lannister arrived!"},
  {"role": "user", "content": "Your turn to speak (Round 1/3)"},
  {"role": "assistant", "content": "[Tool: speak] We can offer 60 gold plus resupply rights."},
  {"role": "user", "content": "House Lannister says to you (Round 1): 'We need at least 65 gold. Resupply rights are acceptable.'"},
  {"role": "assistant", "content": "[Tool: trade_decision] accept - 65 gold plus resupply rights"}
]
```

**Agent B (House Lannister) sees:**
```json
[
  {"role": "user", "content": "🚚 URGENT: Your caravan arrived at House Stark!"},
  {"role": "user", "content": "House Stark says to you (Round 1): 'We can offer 60 gold plus resupply rights.'"},
  {"role": "user", "content": "Your turn to speak (Round 1/3)"},
  {"role": "assistant", "content": "[Tool: speak] We need at least 65 gold. Resupply rights are acceptable."},
  {"role": "user", "content": "RESOLUTION: Trade accepted by House Stark for 65 gold plus resupply rights."}
]
```

### 5. Entity Manager Integration
**File:** `feudal_sim/core/entities.py`
**Integration Point:** Add helper method at line ~560

```python
def add_priority_action_event(self, event: PriorityActionEvent):
    """Add priority action event to simulation processor"""
    if hasattr(self, '_simulation_ref') and self._simulation_ref:
        self._simulation_ref.priority_processor.add_event(event)
```

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 days)
1. **Create `feudal_sim/core/priority_actions.py`**
   - Implement `PriorityActionEvent` dataclass
   - Implement `PriorityActionEventProcessor` class
   - Add basic conversation handling

2. **Modify `feudal_sim/core/simulation.py`**
   - Add processor initialization (line ~45)
   - Modify `execute_actions_phase()` (lines 210-321)

3. **Create `feudal_sim/core/priority_action_handlers.py`**
   - Implement base `PriorityActionHandler` abstract class

### Phase 2: Trade Caravan Implementation (2 days)
1. **Create Trade Caravan Entity System**
   - File: `feudal_sim/entities/caravan.py` (NEW FILE)
   - Components: Position, Cargo, AI
   - Integration with entity manager

2. **Implement TradeCaravanHandler**
   - Context message generation
   - Conversation tools (negotiate, speak)
   - Resolution tools (accept_trade, reject_trade, counter_offer, seize_caravan)
   - Trade mechanics execution

3. **Create Caravan Movement System**
   - Path finding from sender to recipient
   - Integration with existing movement system
   - Arrival event triggering

### Phase 3: Additional Priority Actions (1-2 days each)
1. **Diplomatic Summit Handler**
   - Multi-party conversation
   - Alliance/war declaration tools
   - Summit resolution mechanics

2. **Enemy Encounter Handler**
   - Battle initiation
   - Combat resolution tools
   - Tactical decision making

3. **Resource Crisis Handler**
   - Famine/plague events
   - Cooperation vs hoarding decisions
   - Resource sharing mechanics

### Phase 4: Testing & Polish (2 days)
1. **Integration Testing**
   - End-to-end trade caravan scenarios
   - Multi-agent conversation testing
   - Message history continuity validation

2. **Error Handling & Edge Cases**
   - Agent disconnection during events
   - Timeout handling for conversations
   - Invalid resolution tool usage

3. **Performance Optimization**
   - Concurrent event processing
   - Message history memory management

## Detailed Implementation Examples

### Trade Caravan Arrival Flow

1. **Event Creation** (when caravan reaches destination):
```python
# In caravan movement system
def on_caravan_arrival(caravan_entity, receiving_house):
    event = PriorityActionEvent(
        event_id=f"trade_{caravan_entity.id}",
        event_type="trade_caravan_arrival",
        context_data={
            'caravan': caravan_entity,
            'sending_house': caravan_entity.origin_house,
            'receiving_house': receiving_house
        },
        involved_agents=[receiving_house.id, caravan_entity.origin_house.id],
        allows_conversation=True,
        max_conversation_rounds=3,
        resolution_tools={
            receiving_house.id: ["trade_decision"],
            caravan_entity.origin_house.id: ["trade_negotiation"]
        }
    )
    simulation.priority_processor.add_event(event)
```

2. **Context Addition** (seamless message history integration):
```python
# Automatically added to agent's message history
{
    "role": "user",
    "content": "🚚 URGENT: A trade caravan from House Stark has arrived! Contents: 100 metal, 50 food. They propose: 'Trade our goods for 80 gold and safe passage rights.'"
}
```

3. **Conversation Flow** (if enabled):
```python
# Agent 1 speaks using conversation tools
Lannister: "Your terms are acceptable, but we request 20 additional gold for escort services."

# Agent 2 responds  
Stark: "We agree to 15 additional gold, but require a formal trade agreement."
```

4. **Resolution** (using specialized tools):
```python
# Agent uses resolution tool to end negotiation
@function_tool
def trade_decision(decision: str, terms: str = "") -> str:
    """Final trade decision: accept/reject/counter/seize"""
    event.is_resolved = True
    event.resolution_outcome = f"Trade {decision}: {terms}"
    # Execute actual trade mechanics
    return f"Trade decision: {decision}"
```

5. **Outcome Integration**:
```python
# Added to all agents' message history
{
    "role": "user", 
    "content": "RESOLUTION: Trade accepted. 100 metal and 50 food exchanged for 95 gold. Trade agreement established."
}
```

## Testing Strategy

### Unit Tests
- `test_priority_action_event.py` - Event creation and validation
- `test_priority_action_processor.py` - Event processing logic
- `test_trade_caravan_handler.py` - Trade-specific functionality

### Integration Tests  
- `test_priority_action_flow.py` - End-to-end event processing
- `test_message_history_continuity.py` - Agent message history validation
- `test_multi_agent_conversation.py` - Conversation system testing

### Performance Tests
- `test_concurrent_priority_events.py` - Multiple simultaneous events
- `test_large_conversation_history.py` - Memory usage with long conversations

## Configuration Integration

### New Config Section
**File:** `config/simulation.json`

```json
{
  "priority_actions": {
    "max_concurrent_events": 5,
    "conversation_timeout_turns": 2,
    "default_conversation_rounds": 3,
    "trade_caravan": {
      "negotiation_enabled": true,
      "max_negotiation_rounds": 3,
      "auto_timeout_turns": 2
    },
    "diplomatic_summit": {
      "max_participants": 4,
      "negotiation_rounds": 5
    }
  }
}
```

## Benefits

1. **Seamless Integration**: Agents experience priority actions as natural conversation flow
2. **Flexible Event Types**: Easy to add new priority action types (diplomatic summits, crises, etc.)
3. **Agent-to-Agent Communication**: Rich multi-party negotiations within the event system
4. **No Breaking Changes**: Existing AI components require zero modifications
5. **Scalable Architecture**: Can handle multiple concurrent priority events

## Migration Strategy

1. **Phase 1**: Implement core infrastructure without disrupting existing systems
2. **Phase 2**: Add first priority action type (trade caravans) as optional feature
3. **Phase 3**: Gradually migrate existing event-driven mechanics to priority action system
4. **Phase 4**: Enhanced features like diplomatic summits and crisis management

This implementation maintains full backward compatibility while providing a powerful foundation for rich agent interactions and emergent gameplay scenarios.