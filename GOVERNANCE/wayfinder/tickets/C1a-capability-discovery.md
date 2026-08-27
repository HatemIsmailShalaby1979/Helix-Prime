---
id: C1a-capability-discovery
type: prototype
status: closed
labels: [wayfinder:prototype]
blocked_by: [C1-organization-contracts]
blocks: [C2-control-plane]
---

## Question

How do we replace hardcoded `AGENT_CLASSES` / `ENGINE_MODULE_PATHS` name-only routing with capability-based discovery so tasks resolve by required capabilities, not agent names?

Current: `orchestration/orchestrator.py:172` `AGENT_CLASSES` (4) + `ENGINE_MODULE_PATHS` (6) + `ROUTING_KEYWORD_LOOKUP:166` `DEFAULT_AGENTS`. Target: registry where each agent/GM declares capabilities, tools, data access; orchestrator matches `TaskRequest.required_capabilities` to candidate agents, returns deterministic ownership with segregation-of-duties checks.

## Prototype expected

- `contracts/capabilities.yaml` or `organization/capabilities.json`
- `orchestration/registry.py` + `discovery.py` (capability index, tenant-aware)
- Tests: same request → deterministic owner; conflicting ownership → review queue not silent execution.

## Resolution (closed 2026-08-27, C1a sprint)

**Answer:** Deterministic, fail-closed capability registry that preserves legacy name-only routing via compatibility adapters.

**Files added (7 new):**
- `organization/capability-registry.yaml` — canonical engine capability → engine (16 mappings: erlang_c/ variance_analysis/ wfm_forecast_engine etc. → WFM Forecasting, rta_adherence → RTA, churn_risk_scoring → CX, b2b_onboarding → B2B, talent_acquisition_engine → Personnel, sales_pipeline → CRM). Agent capabilities remain canonical in `organization/role-catalog.yaml` (merged at load).
- `organization/capabilities.json` — JSON mirror of above (satisfies `organization/capabilities.json` expected path)
- `contracts/capabilities.yaml` — contracts view mirror (satisfies `contracts/capabilities.yaml` expected path)
- `organization/capability_registry.py` — `CapabilityRegistry` class + module helpers: `get_agent_for_capability`, `get_engine_for_capability`, `get_capabilities_for_role`, `is_capability_owned_by_role`, `is_tool_allowed`, `discover`, `route_task_request`, `build_registry_from_catalog`; deterministic, fail-closed for unknown/ambiguous, tenant-aware via correlation.
- `orchestration/registry.py` — thin re-export wrapper for `organization.capability_registry` (satisfies `orchestration/registry.py` expected path)
- `orchestration/discovery.py` — deterministic routing: `discover_agent`, `discover_engine`, `route_by_capability` (satisfies `orchestration/discovery.py` expected path), preserves `orchestration/orchestrator.py:211` legacy keyword routing as fallback
- `tests/test_c1a_capability_discovery.py` — 14 tests: agent discovery (8 caps), engine discovery (6 caps), role-to-capability ownership, allowed/denied tool access, unknown capability fail-closed, ambiguous capability fail-closed (synthetic duplicate wfm_forecast), legacy name-based compatibility (orchestrator keyword routing + parse_legacy_calls), legacy engine paths preserved, deterministic routing (repeated calls same owner, cross-capability different owners), deterministic engine routing, no regression orchestrator keyword routing (C0 smoke), no regression C1 contracts.

**Files modified (2 wayfinder docs):** `GOVERNANCE/wayfinder/tickets/C1a-capability-discovery.md` (this file) and `GOVERNANCE/wayfinder/map.md` (Decisions so far).

**Evidence:**
- `python3 -m pytest tests/test_c1a_capability_discovery.py -q` → 14 passed
- `python3 -m pytest -q` → 62 passed (6 existing + 42 C1 + 14 C1a)
- `python3 scripts/smoke.py` → 6/6 engines OK, 4/4 agents OK, 62 passed, C0 SMOKE PASS
- `python3 -m compileall -q app api cockpit engines orchestration organization contracts` → 0
- Whitespace: `git diff --check` (tracked) 0; `grep "[[:blank:]]$"` over 7 new files 0

**Design decisions:**
- Agent capabilities canonical in `role-catalog.yaml` (single source, not duplicated); engine capabilities canonical in `capability-registry.yaml`; Python registry merges both and validates at load — no silent ambiguous.
- Fail-closed: unknown → `ValueError: unknown capability`, ambiguous → `ValueError: ambiguous capability ... — fail closed to review queue` (never silent execution).
- Tool allow-list checked via `is_tool_allowed` against `allowed_tools` per role; unauthorized → `False` (or ValueError for unknown role).
- Legacy preserved: `orchestration/orchestrator.py:211` `_resolve_agents` still keyword-based; new `discover`/`route_task_request` are additive and require `TaskRequest.capability` validation; `contracts/adapter.parse_legacy_calls` still supported via `orchestration/discovery` bridge.

**Known limitations (C1a boundary):**
- No workflow durability/correlation persistence (C2)
- No C3 security/observability, no C4 engine productization beyond capability→engine map, no C5 vertical slice, no sibling transport
- Catalog-only GMs still have no functional agents (no fake execution)
- No network/secrets, local-first Ollama unchanged

**Explicit confirmation:** C2, C3, C4, C5, sibling transport not implemented.

**Next ticket:** C2 — Control Plane & Workflow Runtime (depends C1a)
