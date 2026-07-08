# Simulation Realism & Agent Enablement — Feature Scope

**Status: F1-F8 implemented 2026-07-08** (commits 2e9a7a1..74c0fa7). Balance
constants were tuned against `scripts/balance_check.py`; deviations from this
scope are noted in the commit messages (notably: expansion costs became
8 material / 0 gold per tile after harness data showed gold-gating, the
renderer weather HUD became an event-log line, and the pacing target was
recalibrated to ~5-8% border-only by year 2 with loyalty as the brake).

Scoped 2026-07-08 from the design review. Seven features, each self-contained and
independently shippable. Guiding principle: every mechanic must close a loop an
agent can perceive and act on — no simulation depth that agents can't see, no
agent context that the simulation doesn't back with real mechanics.

---

## F1. Victory conditions & goal framing in prompts

**Problem.** `check_victory_conditions()` (simulation.py) ends the game at >60%
land-tile dominance or last-survivor, but no prompt ever tells agents this.
Agents optimize vibes ("rule with wisdom") instead of playing the actual game.

**Design.** Single source of truth: move the two thresholds into
`config/simulation.json` under `victory` (`territorial_dominance_pct: 0.60`,
`last_survivor: true`), have `check_victory_conditions()` read them, and have
`PromptBuilder` render a **Victory** section in the shared base template from
the same config:

> *The realm can be won: a house that controls more than 60% of all land, or
> stands as the last house with living subjects, rules all. Every season you do
> not advance toward this, another house does.*

Also add rough game-scale framing (16 turns = 1 year) so lords can weigh
short-term vs long-term.

**What agents do NOT get:** live standings ("you rank 2nd") — that's global
state and must stay behind fog-of-war. Rules are public; positions are earned
via scouting and diplomacy.

**Files:** `config/simulation.json`, `core/simulation.py` (read config),
`ai/prompts.py` + `ai/prompt_builder.py` (render section).
**Effort:** S. **Out of scope:** new victory types (economic, prestige).

---

## F2. Downward command channel + mission persistence (generals)

**Problem.** A general's mission is seeded into its message history once at
deployment; after history compaction it is silently gone. Lords have no way to
update a deployed general's orders, and generals never know the strategic
*why* behind their mission.

**Design — two halves:**

1. **Mission block in every general turn context.** In
   `_generate_turn_context_message()` (components/ai.py), when
   `agent_type == GENERAL`, render from the always-current component state:

   ```
   Mission: {mission_type} — {orders}
   Strategic intent: {strategic_intent}
   Deployed since: Turn {n} ({k} turns in the field)
   ```

   Component state can't be truncated, so mission amnesia is structurally
   impossible. ~3 lines of context per turn; no new storage.

2. **`update_general_orders` house tool** (new, in house_toolset.py):
   `update_general_orders(general_name, orders, strategic_intent="")` writes
   `SubAgentGroup.mission_parameters` and queues an observation on the
   general's AI component ("New orders from your lord: …"). Because pending
   observations are processed at the *next* actions phase, orders naturally
   arrive with a one-turn courier delay — consistent with raven latency, zero
   extra machinery.

   `deploy_general` gains an optional `strategic_intent` arg so intent exists
   from turn one.

**Files:** `components/ai.py`, `components/subagent_group.py`
(mission_parameters field), `ai/tools/house_toolset.py`.
**Effort:** S–M. **Out of scope:** general→lord free-form reports (ravens and
observations already cover upward flow); interceptable couriers.

---

## F3. Deferred-outcome feedback loop (realm journal auto-writes)

**Problem.** Immediate tool results are visible in-message, but outcomes that
resolve *later* (battles, expansions, sieges, revolts) reach the agent only as
one-shot observations that scroll out of the 80-message window. The realm
journal (`deque(maxlen=5)`, surfaced every turn) exists for exactly this but
has one writer (general disbands).

**Design.** Instrument the deferred-outcome sites to call
`ai.record_journal_entry()` on the affected house(s):

| Site | Entry example |
|---|---|
| combat resolution (priority_action_handlers) | "Battle at (q,r): defeated Lannister force, lost 14 soldiers" |
| siege outcome | "Siege of Casterly outpost succeeded — tile captured" |
| war declared / peace concluded (trade.py) | "War declared on House Stark" |
| expansion order resolved (simulation.py) | "Expansion NE failed — contested ground" |
| outpost completed/failed | "Outpost 'Greywatch' completed at northern border" |
| revolt (process_population_revolts) | "Revolt! Lost 1 tile, granaries raided" |
| caravan arrived / intercepted | "Caravan from Tyrell arrived: +120 food" |
| starvation event (after F4) | "Famine: 23 subjects perished" |

Bump journal `maxlen` 5 → 10 (still ~10 lines of context, worth it).
Entries are one factual sentence, written at the resolution site where the
cause is known — the agent reads *what happened and why* without any new
query tools.

**Files:** `core/priority_action_handlers.py`, `core/simulation.py`,
`ai/tools/trade.py`, `components/ai.py` (maxlen).
**Effort:** M (many small touch points, each trivial).
**Out of scope:** echoing immediate tool results (already visible);
LLM-summarized histories.

---

## F4. Closed-loop economy

**Problem.** Nothing consumes at home: population "eats" only by capping
growth, the configured birth/death rates are dead code (growth is hardcoded
`food // 2`), loyalty regenerates +1/turn unconditionally, and generals on
home turf resupply for free. Resources accumulate unboundedly; scarcity — the
engine of every interesting feudal decision — only exists if agents create it.

**Design — four coupled changes, one balance harness:**

### 4a. Population subsistence
Each cleanup phase: `food_needed = population * food_per_capita`
(config, default **0.05**/person/turn). Consume from house stores.
Shortfall ratio `s = unfed / population` drives:
- **starvation deaths:** `population -= ceil(population * s * starvation_mortality)`
  (default 0.10) — famine kills, journal entry written (→F3)
- **loyalty:** −(1 + 4·s) per turn while short (scaled, replaces the binary
  `food < 100` check)

### 4b. Demographics: wire the dead config
Replace `food // 2` growth with:
```
fed        = 1 - s                      # food security 0..1
births     = population * (birth_rate / turns_per_year) * fed
deaths     = population * (death_rate / turns_per_year) * (2 - fed)
growth     = births - deaths            # capped by carrying capacity
```
Existing config values (0.035 / 0.030 annual) become live. Well-fed house:
~+0.5%/year net → slow, meaningful growth. Starving house: shrinking.

### 4c. Loyalty earns its recovery
Replace unconditional +1 with: **+1 only when fully fed this turn**; 0 when
short; scaled penalty per 4a when starving. Feasts remain the active lever
(and become genuinely valuable).

### 4d. Logistics with teeth
- Auto-resupply on owned territory now **costs house food** at the existing
  manual rate (10 food = 10 supply). No food in the treasury → no auto-resupply.
- At `supplies == 0`: **desertion attrition** — lose
  `max(1, soldiers * 0.05)` soldiers/turn (config), morale −5. Combat already
  halves strength at low supply; attrition is what finally forces a starving
  army home. No hard action-gating (agents keep agency; the costs persuade).

### 4e. Balance harness (required, ships first)
`scripts/balance_check.py`: run the sim headless with `ai.enabled = false`
(passive houses) for 32 turns (2 years) and assert invariants: no house
starves out doing nothing on defaults; food stocks neither explode (>5x start)
nor collapse; a deployed 50-soldier general drains treasury at the expected
rate. Every constant above lands in `config/simulation.json` — the harness is
how we tune them without eyeballing LLM runs.

**Agent-facing:** turn context already shows food trends/depletion; add one
line: `Subsistence: ~{food_needed}/wk for {population} subjects`. Urgency flag
when projected shortfall < 3 weeks.

**Files:** `components/population.py`, `components/resource.py`,
`components/subagent_group.py`, `core/simulation.py`, `components/ai.py`
(context line), `config/simulation.json`, new `scripts/balance_check.py`.
**Effort:** L — the mechanics are small; the balancing pass is the work.
**Out of scope:** population classes, disease, crop rotation/soil (roadmap
Phase 4 material; subsistence + demographics give 80% of the decision
pressure at 20% of the complexity).

---

## F5. Trade economics

**Problem.** All resources are implicitly 1:1; caravans are gift deliveries
with negotiation theater. Nothing makes trade positive-sum, so rational agents
shouldn't bother.

**Design.** Two layers, both cheap:

1. **Base value table** (config): `food 1.0, material 1.5, metal 3.0, gold 5.0`.
2. **Per-house scarcity multiplier:** perceived value of a resource scales
   with need — `mult = clamp(norm_stock / current_stock, 0.5, 2.0)` where
   `norm_stock` is a config baseline per resource. A hungry house values food
   at up to 2x; a hoarder at 0.5x.

`perceived_value(house, goods)` becomes one function in a new
`core/trade_economics.py`. Surfaced in exactly two places:
- **TradeCaravanHandler event context:** each party sees the deal priced *in
  their own valuation* ("Their offer is worth ~340 to you; they ask goods
  worth ~270 to you") — asymmetric by design, that IS the gains-from-trade.
- **`send_trade_caravan` tool result:** sender sees their own valuation of
  what they're shipping.

This makes mutually beneficial trades *discoverable by the agents themselves*:
food-rich/metal-poor Tyrell and mountain-bound Lannister both see a surplus on
the same exchange. No market, no order books, no dynamic price simulation.

**Files:** new `core/trade_economics.py` (~60 lines),
`core/priority_action_handlers.py`, `ai/tools/trade.py`,
`config/simulation.json`.
**Effort:** M. **Out of scope:** global markets, tariffs, trade routes,
merchant reputation.

---

## F6. Seasonal weather states

**Problem.** Seasonal modifiers are deterministic — autumn is always exactly
1.8x farming. No shocks means no stockpiling incentive beyond winter, and
planning is trivially safe.

**Design.** One weather state per **season** (not per turn — a season-long
condition matches the fiction and the 4-turn cadence; per-turn noise would
just be static agents can't plan around). Rolled at season start from a
config table:

| Weather | P | Farming | Other |
|---|---|---|---|
| normal | 0.65 | ±0 | — |
| bountiful | 0.15 | +0.25 | trade +0.1 |
| drought / harsh (by season) | 0.20 | −0.35 | military movement −0.2 in storms |

Applied as an additive modifier on the existing seasonal multipliers in
`time.py::get_seasonal_modifier`. **Public information, announced:** every
house gets an observation at season start ("A drought grips the realm — the
harvest will be lean") and one HUD line in the renderer's turn/season display.
Weather is realm-wide (shared sky) — per-region weather is complexity without
agent-visible payoff at current map scale.

**Files:** `core/time.py`, `config/simulation.json`, `core/simulation.py`
(announcement), `components/ai.py` (context line), minor renderer HUD text.
**Effort:** S. **Out of scope:** localized weather, multi-season climate
events, weather forecasting tools.

---

## F7. Context hygiene: compendium bounds

**Problem.** `IntelligenceComponent` notes grow unboundedly; at 100+ turns the
"Recent intelligence" selection stays small but storage and `read_compendium`
results balloon.

**Design.** Retention caps, nothing clever: keep the most recent
**20 notes per topic** and **30 topics** (LRU by last write) — both config.
On overflow, drop oldest silently; compaction summaries (which write here)
count like any note. `read_compendium` unchanged — it now just reads bounded
data. Objectives need no work: they live in component state, are surfaced
every turn, and agent-managed objectives are working as designed.

**Files:** `components/intelligence.py`, `config/simulation.json`.
**Effort:** S. **Out of scope:** summarization/archival, embeddings, cross-
agent shared intelligence.

---

## F8. Expansion, territory & convergence

**Problem (diagnosed 2026-07-08).** Games do not converge: no lord accumulates
significant territory and competitive pressure never arises. Three structural
causes, verified in code:

1. **Dead pipeline.** `TerritoryComponent.create_expansion_order` (costs,
   success probability, failure narratives) and
   `Simulation.process_expansion_orders` (runs every turn) are fully built —
   and no tool ever creates an order. Lords can *view* expansion opportunities
   (`view_expansion_options`) but cannot act on them. The only agent-reachable
   territory gain is outposts.
2. **Spacing math makes dominance unreachable.** An outpost claims ~7 tiles
   (center + unowned neighbors, simulation.py:1036-1053) but must sit ≥5 tiles
   from any settlement (`min_spacing_tiles: 5`). Tiles 2-4 away from
   settlements are permanently unclaimable — no infill exists. Packing density
   tops out around ~35-40% of land per house; the 60% dominance condition can
   never fire, and last-survivor (population extinction) never happens either.
3. **Pace.** Each outpost costs a deployed general (30g+18m+0.6/soldier), a
   multi-turn march, a 1-turn build — ~7 tiles per several turns per general.

**Design — four parts:**

### 8a. Revive lord-level border expansion (infill + organic growth)
New house tool `order_expansion(direction, max_tiles=3)` calling the existing
`create_expansion_order`. Resolves next turn through the already-running
pipeline. Calibration fixes while reviving:
- Loyalty cost 5/tile → **1/tile** (5/tile vs +1/turn regen made sustained
  expansion self-destructive; with F4's earned loyalty this stays a real but
  sane brake).
- Cap tiles per order at 3 (config) and one pending order per direction
  (natural via the pending list) so pace is bounded and predictable.
- Costs stay config (`base_material_cost 20`, `base_gold_cost 20` per tile).
Outposts remain the long-range play (seed a distant cluster); border
expansion is the infill that makes the map actually fillable.

### 8b. Contested expansion → manufactured early contact
`ExpansionOrder.status` already has a "contested" value nothing sets. When two
houses' same-turn orders target overlapping tiles: both orders resolve as
contested, the higher success roll takes the tiles, and **both lords get
observations naming the rival** — which also adds the rival to raven
`known_recipients`. Early border friction creates diplomacy/grievance material
long before armies meet, at near-zero mechanical cost.

### 8c. Victory that can actually happen (revises F1 values)
Absolute 60% is the wrong shape even after infill. Replace with two
config-driven conditions:
- **Hegemony:** ≥40% of land AND ≥2x the tiles of every rival — reachable,
  and creates late-game incentive for others to coalition against the leader.
- **Capital elimination:** sieges already capture settlement tiles; extend so
  a house whose *capital* falls is eliminated and its territory transfers to
  the conqueror. This gives the military path a decisive endpoint and makes
  last-survivor a real condition instead of a theoretical one.
F1's prompt section renders whichever conditions config enables.

### 8d. Pacing target + harness invariant
Target: a decisive 4-house game on the default map in **3-5 years (48-80
turns)**. Add an expansion-pacing check to the F4 balance harness: a scripted
expander (no LLM) should hold ~25% of land by end of year 2 on defaults. Tune
`max_tiles`, costs, and `min_spacing_tiles` (candidate: 5 → 4) against this,
not by eyeballing LLM runs.

**Known config wrinkle to fix in passing:** `world_generation.num_houses: 2`
while `create_houses` hardcodes 4 houses — reconcile (config wins).

**Files:** `components/territory.py` (calibration, contested),
`ai/tools/house_toolset.py` or `territory.py` (new tool),
`core/simulation.py` (contested resolution, capital-fall rule, house-count),
`core/priority_action_handlers.py` (siege → elimination hook),
`config/simulation.json`, `ai/prompts.py` (victory text via F1).
**Effort:** M-L. **Out of scope:** naval expansion, colonization of
non-adjacent regions without outposts, vassalage (elimination transfers
territory outright; vassal mechanics are a future feature).

## Sequencing & dependencies

```
Wave 1 (agent enablement, no balance risk):  F1, F2, F3, F7, F8a (revive tool)
Wave 2 (economy + pacing, gated on harness): F4 (harness first), F8b-d
Wave 3 (depth on top of a closed economy):   F5, F6
```

F3 should land before F4 (starvation/famine events want journal writes).
F8a is Wave 1 — it's unblocking existing machinery, and expansion spending is
the main resource sink until F4 lands. F8c (victory rework) and F1's prompt
text ship together. F8d shares the harness with F4 — build it once.
F5's scarcity multiplier only means something once F4 makes scarcity real.
F6 is independent but its stockpiling pressure only bites after F4.

## Explicitly not doing (and why)

- **Population classes / craft specialization** — no agent decision today
  would use them; revisit when trade (F5) creates demand differentiation.
- **Per-region weather, disease, soil depletion** — simulation depth invisible
  to agents at current map scale.
- **Hiding enemy identity within observation radius** — accepted playability
  trade-off from the review; revisit only if espionage becomes a feature.
- **LLM-judged combat/negotiation outcomes** — rules-based resolution is
  deterministic, debuggable, and cheap; the LLMs' job is deciding, not dice.
