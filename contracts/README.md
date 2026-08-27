# Contracts — Helix Prime C1 Typed Contracts

Canonical location: `contracts/task.py` (plus `contracts/adapter.py` compatibility seam).

## Models

- `CorrelationContext` — correlation_id, idempotency_key, tenant/client, timestamp, schema_version
- `EvidenceRef` — evidence_id, type, uri, timestamp, hash, actor
- `AgentError` — error_id, correlation_id, code, message, timestamp, retryable, evidence_ref
- `Approval` — approval_id, correlation_id, subject_id, approver_actor/role, decision (approved/denied), reason, timestamp
- `Action` — action_id, correlation, tenant/client, actor, owning_role_id, capability, payload, requires_approval, status (proposed/approved/denied/executing/succeeded/...), approval, evidence_refs, idempotency_key
- `Recommendation` — recommendation_id, correlation, owning_role_id, capability, confidence (0-1), rationale, requires_approval, proposed_action, evidence_refs
- `TaskRequest` — request_id, correlation, requesting_actor, owning_role_id, capability, input_payload, requires_approval, status (proposed/validated/...), evidence_refs, idempotency_key, timeout
- `TaskResult` — result_id, request_id, correlation, owning_role_id, capability, status (succeeded/failed/refused/timed_out/...), output_payload, confidence, evidence_refs, error, recommendation, action

Each model carries `schema_version: "1.0"` and validates deterministically on construction (`__post_init__` raises `ValueError` with field path).

## Usage

```python
from contracts.task import CorrelationContext, TaskRequest
from contracts.adapter import parse_legacy_calls, to_task_request, validate_request_against_catalog
from organization.role_catalog import load_role_catalog

corr = CorrelationContext.new(client_id="Account Alpha", tenant_id="helix-prime")
req = TaskRequest(
    request_id="req_abc123",
    correlation=corr,
    requesting_actor="sami",
    owning_role_id="ops_gm",
    capability="wfm_forecast",
    input_payload={"client": "Account Alpha"},
    requires_approval=False,
    status="proposed",
    created_at="2026-08-27T18:00:00Z",
)

# C1 catalog validation (fail-closed, no bypass)
catalog = load_role_catalog("organization/role-catalog.yaml")
validate_request_against_catalog(req, catalog)  # raises on SOD/peer violation
```

Legacy text bridge (compatibility, will be replaced in C2):

```python
for agent, msg in parse_legacy_calls('call_agent("PHILI", "headcount?")'):
    req = to_task_request(corr, "sami", "sami", "hr_personnel_gm", "workforce_planning", {"question": msg})
```

## Guarantees (C1)

- Every contract rejects malformed required data deterministically (see `tests/test_c1_contracts.py`).
- Self-approval forbidden: `Action` with `requires_approval=True` must have `approval.approver_actor != actor` and `approver_role_id != owning_role_id`.
- Approval/action ownership checked via `validate_request_against_catalog`: capability must be owned, peer call must be allowed.
- Model text cannot bypass: `parse_legacy_calls` only parses; `validate_request_against_catalog` must pass before execution.

## What C1 does not do

- No workflow runtime (C2)
- No capability-based discovery (C1a)
- No engine execution; catalog-only GMs have no agents

## Validation

```bash
python3 -m pytest tests/test_c1_contracts.py -q
python3 -m pytest -q  # all 6+new tests
```
