# Control Plane — Helix Prime C2 Workflow Runtime

Local-first, durable, fail-closed. SQLite-backed, no cloud, no secrets.

## Package

- `workflow.py` — `WorkflowState` (11 states), `Workflow` dataclass, `is_valid_transition` (deterministic, invalid → `ValueError`)
- `events.py` — `Event` envelope (event_id, event_type, aggregate_id, correlation_id, actor, schema_version `1.0`, timestamp, payload, causation_id, sequence)
- `store.py` — `Store` (SQLite `workflow.db` WAL, `workflows` + `events` tables, `create_workflow` idempotent by `idempotency_key`, `append_event` enforces `event_id` unique + per-aggregate `sequence` monotonic, `get_events`/`replay` ordered, `update_workflow`, `get_workflow`, `clear_for_tests`, persists across `Store` restarts)
- `engine.py` — `Engine` (deterministic handler registry `register_handler(capability, fn)`, `submit(TaskRequest)` → `Workflow` with C1a capability/tool validation, `approve(workflow_id, Approval)` with SOD, `execute(workflow_id)` with bounded retries/timeout/dead_letter/failures-as-data, `cancel`, `to_task_result` → `TaskResult`, `close`)

## States

`proposed → validated → awaiting_approval → approved → executing → succeeded → failed → compensated → cancelled → dead_letter → closed` (plus `dead_letter` as review queue). `is_valid_transition` enforces `VALID_TRANSITIONS`; invalid raises `ValueError`.

## Durability

- `Store(db_path="control_plane/workflow.db")` — file `control_plane/workflow.db` persists; tests use `:memory:` or `tmp_path/c2.db`.
- Idempotency: same `idempotency_key` → same `workflow_id` (no duplicate execution).
- Duplicate/out-of-order: same `event_id` idempotent return, `sequence` must be `max+1` else `ValueError: out-of-order`.

## Execution

- `register_handler("wfm_forecast", fn)` — `fn(Workflow) -> dict` or raise.
- `submit` validates via `organization/capability_registry.get_agent_for_capability` and `is_tool_allowed`; unknown/unauthorized → `dead_letter` with `AgentError` (no silent).
- Deadline: `Workflow.deadline` ISO; `_is_past_deadline` → `dead_letter`/`timeout`.
- Retries: `max_retries=3` default; `retry_count` increments per failure, `handler_failed` + `retry_scheduled` events each attempt, no silent loop, exhausted → `failed` → `dead_letter`.
- Cancellation: `cancel` from non-terminal → `cancelled` → `closed`.
- Failures-as-data: handler exception → `handler_failed` event + `AgentError`, not crash.
- Dead-letter: policy denied, timeout, no handler, retries exhausted, unknown capability/tool all go to `dead_letter` with `error.code`.
- No duplicate execution: same `idempotency_key` returns existing workflow, handler not re-run.

## Approval

- `requires_approval` → `awaiting_approval`; `approve` checks `approval.correlation_id == workflow.correlation`, `approver_actor != requesting_actor` (self-approval forbidden), `approver_role_id != owning_role_id` (same-role forbidden), and catalog SOD (`must_be_reviewed_by`/`can_review`). `approved` → `executing`, `denied` → `dead_letter` with `approval_denied` and prevents `execute`.

## Tool seam

- `submit(TaskRequest)` resolves `capability` via C1a registry, enforces `is_tool_allowed` for `tool` in `input_payload`, returns `TaskResult` via `to_task_result` (succeeded/failed/refused/timed_out).

## Scope (C2)

- Test handlers or narrow engine wrappers only; not full six-engine productization.
- No C3/C4/C5/C6/C7, no dashboard, no legacy routing removal, no BaseAgent change.

## Verification

```bash
python3 -m pytest tests/test_c2_control_plane.py -q  # 30 tests
python3 -m pytest -q  # 97 total
python3 scripts/smoke.py  # 6/6 engines 4/4 agents
python3 -m compileall -q app api cockpit engines orchestration organization contracts control_plane
```

## Example

```python
from control_plane.engine import Engine
from contracts.task import TaskRequest, CorrelationContext
from organization.capability_registry import get_agent_for_capability

store = Store(db_path=":memory:")
engine = Engine(store=store)
engine.register_handler("wfm_forecast", lambda w: {"optimal_agents": 42})

corr = CorrelationContext(correlation_id="c1", idempotency_key="k1", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z")
req = TaskRequest(request_id="r1", correlation=corr, requesting_actor="sami", owning_role_id="ops_gm", capability="wfm_forecast", input_payload={}, requires_approval=False, status="proposed", created_at="2026-08-27T18:00:00Z", client_id="c")
wf = engine.submit(req)
wf = engine.execute(wf.workflow_id)
print(wf.state)  # closed
```
