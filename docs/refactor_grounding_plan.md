### Refactor and Grounding Plan

#### Objectives
- Improve code health and extensibility without regressions.
- Ground all agent-facing outputs (natural language, no raw grid coordinates).
- Reduce duplication and clarify boundaries between tools, ECS components, and the simulation loop.

#### Scope (What we will change)
- Standardize direction/observation formatting via shared utilities.
- Cleanly separate tool modules by entity type.
- Centralize sub-agent configuration and lifecycle helpers.
- Make entity lookups efficient with indexed queries.
- Remove implicit/hidden dependencies between components.
- Improve logging, types, and docstrings; add basic tests over time.

#### Guardrails (Protect functionality)
- Small, incremental edits; feature-flag new formatters if needed.
- Keep old code paths until new ones are proven; do not change tool signatures.
- After each step, do a manual run; watch logs for behavior/phrasing changes only.

---

### Phase 1: Low-risk, high-leverage

1) Direction and observation utilities
- Add `feudal_sim/utils/directions.py`:
  - neighbor_delta_to_dir((dq, dr)) -> "N"/"NE"/…
  - dir_code_to_prose("NE") -> "northeast"
  - join_directions(["north", "northeast"]) -> "north and northeast"
- Add `feudal_sim/utils/observations.py`:
  - formatters for movement text, border summary, unit summary, settlement results, raven phrasing
- Wire movement + general `observe_area` to use these utilities.

Success criteria:
- No logic changes; only phrasing standardized and grounded.

2) EntityManager indices
- Add indexed getters: `get_entities_by_type`, `get_entities_by_house_and_type`.
- Replace ad-hoc scans in hot paths with indexed queries.

Success criteria:
- Same results; less scanning.

3) Consolidate observation/reporting sources
- Simulation loop: keep movement observation only (terrain intel only from explicit tools).
- Use observation formatter across rookery/tool outputs for consistent tone.

Success criteria:
- No duplicate/conflicting intel; cleaner, consistent phrasing.

---

### Phase 2: Architectural cleanup

4) Split AI tools into cohesive modules
- `ai/tools/house.py`, `ai/tools/general.py`, `ai/tools/registry.py`, `ai/tools/shared.py`.
- Keep `get_tools_for_entity` central in `registry.py`.

Success criteria:
- Zero behavior change; easier to add tools and entity-specific features.

5) Sub-agent lifecycle clarity
- In `SubAgentGroup`: extract `apply_upkeep()` and `perform_observation()` from `update_turn`.
- Emit events on deploy/disband (ACTION_PERFORMED with details).
- In `TerritoryComponent`: use `register_general`, `unregister_general`, `sync_generals`; add `get_general_cap(territory_size)` for one-source-of-truth.

Success criteria:
- Behavior unchanged; smaller testable units; unified cap logic.

6) Remove implicit coupling in `TerrainObservation`
- Stop using `_entity_manager`. Pass `entity_manager` explicitly or via `RunContextWrapper`.

Success criteria:
- Dependencies explicit; no hidden state.

7) Config consolidation
- Add `feudal_sim/config/subagents.py` typed helpers for deploy caps/costs, upkeep costs, morale thresholds.
- Replace scattered `config.get(...)` calls.

Success criteria:
- Configuration lives in one place; fewer stringly-typed keys.

---

### Phase 3: Developer experience

8) Logging
- Replace `print` with `logging` and levels; guard verbose logs behind config.

9) Types and docs
- Add type hints/docstrings for public APIs (tools/components).
- Enable ruff/mypy in dev.

10) Tests
- Add pytest-asyncio; convert async tests.
- Add unit tests for:
  - ObservationFormatter outputs
  - TerritoryComponent general tracking
  - SubAgentGroup upkeep/disband thresholds

---

### Execution Order (Start here)
1. Phase 1.1: Add `utils/directions.py` and `utils/observations.py`; wire movement + `observe_area` only.
2. Phase 1.2: Add `EntityManager` indexed queries; migrate safe call-sites.
3. Phase 1.3: Route rookery/tool phrasing through observation formatter (no logic changes).
4. Phase 2.4: Split tool files (start with general tools), keep registry stable.
5. Phase 2.5+: Small lifecycle refactors, config consolidation, and explicit dependencies.
6. Phase 3: Logging/types/tests improvements.

---

### Rollback Plan
- Keep feature toggles for new formatters and fast queries; fallback to legacy paths if issues arise.
- Changes are isolated; revert individual modules without affecting tool signatures.

### Notes
- Already Done: general caps/costs/upkeep/disband; grounded outputs; general tracking helpers and sync.
- Next PR: Phase 1.1 utilities + minimal wiring. 