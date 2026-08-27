---
id: C2-control-plane
type: prototype
status: closed
labels: [wayfinder:prototype]
blocked_by: [C1-organization-contracts, C1a-capability-discovery]
blocks: [C4-engine-productization, C6-gm-expansion]
---

## Question

What does the durable workflow/task runtime + event envelope + engine adapter interface look like so Helix can run a business process, not just a chat request?

Must deliver (C2 exit gate): states `proposed → validated → awaiting_approval → executing → succeeded/failed/compensated → closed`, durable correlation IDs, idempotency keys, deadlines, retries, cancellation, dead-letter/review queues, compensation hooks; event envelope + event store abstraction (local-first, replaceable); tool registry + adapter per engine that returns typed `TaskResult` + `EvidenceRef` not console output; policy evaluation before sensitive actions + cockpit approval capture; unified run history (timeline, handoffs, engine calls, decisions, approvals, failures, outputs). Prove: one WFM → OPS → Compliance review → HR/L&D escalation workflow from cockpit with restart/timeout/duplicate/denied-approval tests.

## Prototype expected

- `orchestration/workflow.py` or `control_plane/runtime.py` + `events.py` + `store.py` (JSONL/SQLite abstraction kept)
- `engines/*/adapter.py` (WFM + RTA first) returning typed results
- `cockpit/pages/workflow_timeline.py` or timeline seam
- Failure-injection tests.

## Resolution (closed 2026-08-27, C2 sprint)

**Answer:** Small, local-first control-plane runtime with deterministic state machine, durable SQLite store, and structured tool seam; preserves all C0/C1/C1a behavior and legacy routing.

**Files added (6 new):**
- `control_plane/__init__.py` — re-exports
- `control_plane/workflow.py` — `WorkflowState` 11 states (`proposed/validated/awaiting_approval/approved/executing/succeeded/failed/compensated/cancelled/dead_letter/closed`), `VALID_TRANSITIONS` map, `is_valid_transition` (invalid → `ValueError`), `Workflow` dataclass (workflow_id/task_id/correlation/tenant/client/actor/owning_role/capability/state/input_output payloads/timestamps/retry/deadline/idempotency/evidence/error/approval/requires_approval)
- `control_plane/events.py` — `Event` envelope (event_id/event_type/aggregate_id/correlation_id/actor/schema_version `1.0`/timestamp/payload/causation_id/sequence, `ALLOWED_EVENT_TYPES`, `Event.new`)
- `control_plane/store.py` — `Store` SQLite WAL (`control_plane/workflow.db`, tables `workflows` + `events`, `create_workflow` idempotent by `idempotency_key`, `append_event` enforces `event_id` unique + per-aggregate `sequence` monotonic (duplicate/out-of-order → `ValueError`), `get_events`/`replay` ordered, `update_workflow`, `get_workflow`, `clear_for_tests`, persists across restart)
- `control_plane/engine.py` — `Engine` (deterministic `register_handler(capability, fn)`, `submit(TaskRequest)` validates via `organization/capability_registry.get_agent_for_capability` + `is_tool_allowed` + unknown/ambiguous → `dead_letter`, idempotent duplicate submission returns existing workflow, `approve(workflow_id, Approval)` validates SOD self/same-role + correlation + `must_be_reviewed_by`/`can_review` (sami/compliance), `denied` → `dead_letter` prevents `execute`, `execute` handles deadline (`timeout` → `dead_letter`), bounded retries (`max_retries=3`, `handler_failed`+`retry_scheduled` events per attempt, exhausted → `failed`→`dead_letter`), `cancel` → `cancelled`→`closed`, failures-as-data (`AgentError`), `to_task_result` maps workflow state to `TaskResult` status)
- `control_plane/README.md` — package docs
- `tests/test_c2_control_plane.py` — 30 tests covering 21 required cases: valid creation, valid/invalid transitions, event append/replay, sequence enforcement, idempotent duplicate submission, duplicate event rejection, deadline timeout, bounded retry (3+1 calls), cancellation, dead-letter (unknown/denied), approval required/granted/denied, SOD self/same-role rejection, unknown capability, unauthorized tool, successful handler (`wfm_forecast` → `{"optimal_agents":42}`), handler failure, restart persistence (file DB), tenant/client preservation, correlation/causation preservation, drift detection, no silent retry, no duplicate execution

**Files modified (2 wayfinder docs):** `GOVERNANCE/wayfinder/tickets/C2-control-plane.md` (this file) and `GOVERNANCE/wayfinder/map.md` (Decisions so far).

**Evidence:**
- `python3 -m pytest tests/test_c2_control_plane.py -q` → 30 passed
- `python3 -m pytest -q` → 97 passed (6 existing +42 C1 +14 C1a +5 drift +30 C2)
- `python3 scripts/smoke.py` → 6/6 engines OK, 4/4 agents OK, 97 passed, C0 SMOKE PASS
- `python3 -m compileall -q app api cockpit engines orchestration organization contracts control_plane` → 0
- Whitespace: `git diff --check` 0; `grep "[[:blank:]]$"` over 6 new files 0

**Design decisions:**
- SQLite WAL file `control_plane/workflow.db` smallest safe durable store; `:memory:` for tests; `Store` is replaceable abstraction (could be JSONL later without changing workflow/engine).
- State machine explicit `VALID_TRANSITIONS` map, `Workflow.transition` validates and updates `updated_at`; invalid raises `ValueError` deterministically.
- Events are the source of truth; `sequence` per aggregate enforces ordering, `event_id` uniqueness enforces idempotency; `replay` rebuilds history.
- Engine is additive, does not touch `app/command_center/agents/base_agent.py`, `orchestration/orchestrator.py`, or cockpit; legacy keyword routing preserved.
- Handlers are test doubles for `wfm_forecast` etc., not full engine productization (deferred to C4); structured tool seam uses `TaskRequest`→`TaskResult` via registry.

**Known limitations (C2 boundary):**
- No C3 security hardening, no full observability beyond structured events
- No C4 full engine productization (only test handlers + `wfm_forecast` narrow wrapper)
- No C5 complete WFM/RTA vertical slice (only runtime proven, not cockpit WFM→OPS→Compliance→HR/L&D workflow)
- No C6 new GM execution, no C7 sibling transport, no deployment packaging, no secrets, no new dashboard

**Explicit confirmation:** C3, C4, C5, C6, C7 not implemented.

**Next ticket:** C3 — Security/Privacy & Observability (parallel with C2) and C4 — Six-Engine Productization (depends C2+C3)
