### Simulation Stability and Emergence Plan

#### Context
This document summarizes observed behaviors in the current feudal simulation (based on the attached run log) and proposes targeted changes to improve stability and enable richer, emergent behaviors from AI agents. The plan balances quick wins, medium-term system upgrades, and longer-term features.

### Current flow and what works
- **Phases**: Production → Actions → Events → Cleanup run correctly; observations are delivered and AI acts each turn.
- **Tooling**: Generals can move by direction, observe one-tile area, settle nearby tiles, and send ravens. Houses deploy generals, manage household, assess borders, send ravens, and collect taxes.
- **Grounding**: Observations and tool responses avoid raw coordinates and use natural, directional phrasing.
- **Comms**: Raven delivery and two-way messaging work; generals report status; houses receive turn-context observations.
- **New feature**: When generals auto-disband, the relevant house receives an observation (confirmed in log).

### Key failure modes observed
- **1) General disband churn**
  - Generals frequently auto-disband within 1–3 weeks due to upkeep/supply/morale failures. This causes thrash and prevents sustained campaigns.
- **2) Coastal movement dead-ends**
  - Generals near coasts repeatedly attempt moving into water tiles, wasting turns until a valid land step is chosen.
- **3) Tax-induced loyalty collapse**
  - High tax rates generate large gold but loyalty drops rapidly (e.g., −40 in one action), leading to continuous revolt risks and frequent revolts.
- **4) Material bottlenecks**
  - Houses accumulate gold but cannot deploy or expand due to low material. Plans stall despite abundant gold.
- **5) Plateaued behaviors**
  - After settling, generals mostly continue pushing in one direction and sending ravens. Limited diversification: few fortifications, garrisons, or logistics actions.
- **6) Logistics gap**
  - Supplies only deplete. No explicit resupply on friendly territory, no logistics orders, and disbanding is the common end state.

### Root causes (inferred)
- Supply consumption and upkeep exceed natural recovery; no built-in resupply channel.
- Movement is greedy towards requested direction without land-aware fallback.
- Taxation penalty curve is too steep; there are few positive loyalty actions.
- Economy lacks conversion (gold→material), making gold stockpiles less useful.
- Toolset misses mid-game actions (fortify, garrison, public works) to vary behaviors and stabilize.

### Quick wins (low-risk changes)
- **Supply/resupply**
  - Auto-resupply general supplies each turn when on owned tiles or adjacent to a friendly city (cap to 100%).
  - Reduce supply consumption per turn by ~20%.
  - Replace instant disband with staged degradation: warnings → morale decline → partial desertion → final disband.
- **Directional movement fallback**
  - If the requested neighbor is invalid (water/blocked), choose the nearest land neighbor in the same sector (or adjacent sector) and return a helpful message: “Coast blocks NE; moving N instead.”
- **Taxation/loyalty tuning**
  - Soften loyalty penalty function for moderate taxes; impose diminishing returns and a seasonal cooldown (e.g., heavy tax inflicts a lockout for a few turns).
  - Add small, passive loyalty recovery if food surplus is positive.
- **Economy conversion**
  - Introduce a simple market exchange: spend gold to buy material at a dynamic rate unlocked by a capital city; prevent hard stalls.
- **Observability**
  - Add pre-disband warnings to the house: “General X supply low (18%), morale falling; resupply advised.”

### Medium-term system upgrades
- **Logistics and upkeep**
  - House tool: `send_supplies_to_general(general_name, food, material)` – consumes house stockpiles; restores general supplies/morale.
  - General tool: `establish_camp()` – reduce consumption for N turns; `forage()` – small supplies gain with risk.
  - Gold-based upkeep payments per turn for deployed units; unpaid increases disband risk.
- **Movement/pathfinding**
  - Add small-step land pathfinding (BFS/A*) for `move(direction)` to pick an alternative safe neighbor when the exact direction is water.
  - General tool: `move_towards_border(direction)` – picks a land-safe neighbor in that sector.
- **Territorial actions**
  - General tools: `fortify_position()` and `build_outpost()` on owned border tiles to reduce revolt impact and improve local supply.
  - `garrison(tile)`: leave a portion of soldiers to stabilize tile and border security.
- **Revolt and loyalty loop**
  - New house tools: `hold_feast()`, `public_works(project)` with meaningful loyalty boosts and small future bonuses.
  - Revolt risk scales smoothly; recent public works/feasts create a temporary “stability buffer.”
- **Economy breadth**
  - Trade events in Events phase that allow metal→material exchange or inter-house barter.

### Longer-term features (emergence enablers)
- **Diplomacy and aid**
  - Alliances yield small loyalty boosts, shared intel, and occasional aid shipments.
  - House-to-house `send_aid(resources)` with delivery delays.
- **Campaign planning**
  - Mission-level orders from house (e.g., “stabilize south,” “create fortified northern line”). Generals split tasks across fortify, patrol, settle.
- **Supply lines**
  - Roads/outposts provide supply corridors; extended operations require maintaining lines.

### AI policy and prompting updates
- Add rules into `AIComponent` dynamic instructions:
  - “Avoid new taxes if loyalty < 60; prefer feasts or public works when loyalty < 50.”
  - “Resupply units before further expansion when supplies < 30%.”
  - “Prefer land-safe paths; avoid moving into water.”
  - “Convert gold to material when blocked on material-dependent actions.”
  - “If multiple generals are deployed, diversify: patrol, fortify, settle rather than only expand.”

### Proposed new/updated tools (API sketch)
- **House**
  - `send_supplies_to_general(general_name: str, food: int, material: int) -> str`
  - `hold_feast(cost_food: int, cost_gold: int) -> str`
  - `public_works(project: str, budget_gold: int, budget_material: int) -> str`
  - `convert_gold_to_material(gold: int) -> str`
  - `issue_orders_to_general(general_name: str, orders: str) -> str`
  - `prioritize_border(direction: str) -> str`
- **General**
  - `establish_camp() -> str`
  - `forage() -> str`
  - `fortify_position() -> str`
  - `build_outpost() -> str`
  - `garrison(percent_soldiers: int) -> str`
  - `move_towards_border(direction: str) -> str`
  - `request_resupply(message: str) -> str` (raven helper)

### Config and balance knobs (data-driven)
- `simulation.subagents.supply_consumption_per_turn`
- `simulation.subagents.low_supply_threshold`
- `simulation.economy.tax_loyalty_curve` (piecewise or polynomial)
- `simulation.market.material_exchange_rate`
- `simulation.territory.fortification_effects`
- `simulation.events.revolt_base_probability`

### File touchpoints (where to implement)
- `feudal_sim/components/subagent_group.py`: staged disband, supply logic, morale changes, new group actions (camp/forage), upkeep.
- `feudal_sim/ai/tools.py` (or modularized `ai/tools/*`): new house/general tools above; movement fallback; markets; public works/feast.
- `feudal_sim/core/simulation.py`: pre-disband warnings; seasonal taxation cooldown; Events hooks for trade/barter.
- `feudal_sim/components/territory.py`: fortification/outpost/garrison effects; border stability calculations.
- `feudal_sim/map/hex_grid.py`: helpers for land-safe neighbor selection; simple path hints.
- `feudal_sim/components/resource.py`: exchange mechanics and upkeep payments.
- `feudal_sim/ai/prompt_builder.py`: add policy nudges.

### Telemetry and observability
- Emit structured events for: supply warnings, morale dips, tax changes, feast/works effects, fortify/garrison actions, revolt triggers.
- Add per-turn summary to houses: loyalty trend, revolt risk, deployed generals with supply/morale snapshot.

### Phased roadmap
- **Sprint 1 (stability + economy) – 1–2 days**
  - Auto-resupply on owned tiles; reduce supply consumption; pre-disband warnings.
  - Movement fallback around water; suggest alternative direction.
  - Soften tax penalties; add seasonal cooldown; passive loyalty recovery on food surplus.
  - Gold→material exchange; add house `convert_gold_to_material` tool.
  - Acceptance: generals stay deployed >3 weeks on average; failed water moves <10% of moves; tax does not instantly crash loyalty.
- **Sprint 2 (logistics + territory) – 2–4 days**
  - House resupply tool; general camp/forage; upkeep payments.
  - Fortify/outpost/garrison with effects; settle limited to 2–3 tiles/turn or higher supply cost.
  - Acceptance: fewer disbands; fortifications measurably reduce revolt losses; expansion pace stabilizes.
- **Sprint 3 (emergence + diplomacy) – 3–5 days**
  - Patrol-border; move-towards-border; issue-orders to general; prioritize-border.
  - Diplomacy/aid hooks and stability buffer from public works/feasts.
  - Acceptance: diversified behaviors (settle/patrol/fortify/resupply/aid) observed in logs without handholding.

### Risks and mitigations
- Overcomplexity: keep tools concise with clear effects and costs; hide advanced actions behind config flags initially.
- Balance drift: use config and add simple tests for loyalty/tax curves, supply consumption, and upkeep.
- Performance: keep pathfinding to 1–2 step local heuristics; avoid global searches.

### Acceptance criteria & KPIs
- **Deployment longevity**: Median general lifetime ≥ 4 weeks.
- **Failed moves**: < 10% invalid move attempts over 50 moves.
- **Revolt frequency**: ≤ 1 revolt per 10 turns per house at moderate taxes (≤20%) and neutral conditions.
- **Action diversity**: Each general uses ≥ 3 distinct action types across 5 turns (move, settle, fortify/garrison, resupply/camp, raven).
- **Stability**: No hard stalls due to material bottlenecks when gold is abundant (market active).

### Summary
The simulation is structurally sound and already exhibits coherent expansions and communications. Stability issues center on logistics (supply/upkeep), movement over water, aggressive taxation, and economy imbalances. The outlined phased plan addresses these with minimal disruption, adds much-needed mid-game actions, and sets conditions for emergent, varied AI behavior across campaigns, logistics, fortification, and diplomacy. 