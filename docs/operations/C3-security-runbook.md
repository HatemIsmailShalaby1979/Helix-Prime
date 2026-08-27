# Helix Prime — C3 Security Runbook (Local-First)

**Scope:** C3 foundations — classification, authorization, secrets, audit, observability, health. For operator use on local laptop. No cloud.

## Quick Health

```bash
python3 -c "from observability.health import check_health, is_healthy; import json; h=check_health(); print(json.dumps({k: v.to_dict() for k,v in h.items()}, indent=2)); print('HEALTHY' if is_healthy(h) else 'UNHEALTHY')"
python3 -m pytest tests/test_c3_security.py -q
python3 -m pytest tests/test_c2_preflight_regression.py -q
python3 scripts/smoke.py
```

## Incident Types & Playbooks

### 1. Authorization Denied (`authorization_denied`, `policy_denied`, `tenant_isolation`)

- **Signal:** `observability/logs.jsonl` `event_type="authorization_denied"` `error_code="unauthorized_role"` / `tenant_isolation`, `security/audit.db` `event_type="authorization_denied"` `decision="denied"`, `control_plane` workflow `dead_letter`.
- **Triage:** Check `actor`, `role_id`, `capability`, `tool`, `target_tenant/client` in log/audit. Verify `organization/role-catalog.yaml:allowed_peer_calls` and `organization/capability_registry.py`.
- **Response:** If legitimate, update `allowed_peer_calls` or `allowed_tools` via catalog (requires review). Do not bypass policy. If malicious, keep in `dead_letter`, audit `workflow_dead_letter`, notify `sami`/`compliance_quality_gm`.
- **Verify:** `python3 -c "from security.policy import AuthorizationRequest, authorize; from security.identity import Identity; ..."` repro.

### 2. Invalid Identity (`invalid_identity`)

- **Signal:** `Identity` creation `ValueError: actor_type must be human/agent/service`, audit `invalid_identity`.
- **Triage:** Check `Identity(actor, actor_type, tenant, client, role)` fields.
- **Response:** Fix caller to provide valid `actor_type`; deny-by-default remains.

### 3. Secret Redaction (`secret_redaction`)

- **Signal:** `security/secrets.validate_no_secrets` raises `ValueError: appears to contain secret`, log `event_type="secret_redaction"` `error_code="secret_detected"`, payload not stored.
- **Triage:** Inspect `input_payload` for `api_key`, `password`, `bearer`, `token`, `cookie`, `aws_secret`, or high-entropy 32+ hex, or email/SSN. Use `redact_dict` to see redacted view.
- **Response:** Remove secret from payload, use `get_secret("HELIX_API_KEY")` env lookup instead. Do not log secret value. Ensure `.env` not committed (`.gitignore`).
- **Verify:** `python3 -c "from security.secrets import validate_no_secrets; validate_no_secrets({'x': 'test'})"`

### 4. Suspicious Prompt / Tool Request (`suspicious_prompt`, `tool_abuse`)

- **Signal:** `security/injection.is_suspicious_prompt` returns `True` for `ignore previous instructions`, `system:`, `pretend you are`, `drop table`, or tool payload injection; audit `suspicious_prompt`, log `error_code="injection"`.
- **Triage:** Review `input_payload` text via `scan_for_injection`.
- **Response:** Route to `dead_letter` (`policy_denied`), do not execute handler. Record `security/audit.db` and `control_plane` dead-letter. Escalate to `compliance_quality_gm`.

### 5. Tenant Boundary Violation (`tenant_boundary_violation`)

- **Signal:** `policy.authorize` `code="tenant_isolation"` (`identity.tenant != target.tenant`), audit `tenant_boundary_violation`.
- **Triage:** Check `Identity.tenant_id/client_id` vs `Workflow.tenant_id/client_id`.
- **Response:** Deny, `dead_letter`, verify `DataClassification.client_confidential` handling. Check SQLite not cross-aggregate (per-aggregate `UNIQUE(aggregate_id, sequence)`).

### 6. Audit Verification Failure (`audit_verification_failure`)

- **Signal:** `security/audit.AuditTrail.verify_chain()` returns `(False, "tamper detected")`, health `audit` check fails.
- **Triage:** Run `python3 -c "from security.audit import AuditTrail; print(AuditTrail().verify_chain())"`. Check `audit.db` file for `DELETE`, `UPDATE`, or manual edit.
- **Response:** Do not auto-repair. Preserve file, copy for forensics, restore from backup if available. Note: audit is tamper-evident, not immutable — deletion not prevented.
- **Verify:** After restore, `verify_chain` should be `True`.

### 7. Repeated Handler Failure (`repeated_handler_failure`, `engine_error`)

- **Signal:** `control_plane` workflow `retry_count` increments, events `handler_failed` + `retry_scheduled` per attempt, then `workflow_failed` → `dead_letter` `engine_error`, structured log `retry_count`, `error_code`.
- **Triage:** Check `observability/logs.jsonl` `retry_count`, `handler` logs, `Store.get_events(workflow_id)`.
- **Response:** Bounded retries (`max_retries=3`) already enforced, no silent loop. Investigate handler, fix, resubmit with new `idempotency_key` (do not reuse same key to avoid idempotent return of old workflow).
- **Verify:** `python3 -m pytest tests/test_c2_control_plane.py::test_bounded_retry -q`

### 8. Secrets Exposure (source/payload/logs)

- **Signal:** `validate_no_secrets` fails on `TaskRequest` or `grep -r "api_key"` prior to commit, `git diff --check` would have caught trailing secret, or `is_secret_present` true.
- **Response:** Rotate exposed secret, remove from source/payload, use `get_secret` env, `redact` before logging, ensure `.gitignore` has `*.db`, `*.sqlite`, `.env`.

### 9. Local Database Compromise (deletion, SQLite tampering)

- **Signal:** `health.check_control_plane_store` `ok=False`, `check_event_replay` fails, `audit.verify_chain` fails, file missing.
- **Response:** Check `control_plane/workflow.db` and `security/audit.db` existence and `PRAGMA integrity_check`. Restore from backup (backup/restore separately proven, not in C3). After restore, verify `Store.list_workflows` and `AuditTrail.verify_chain`.
- **Verify:** `python3 -c "from observability.health import check_health; print(check_health())"`

### 10. Replay / Idempotency Abuse

- **Signal:** Duplicate `idempotency_key` submitted, `Store.create_workflow` returns existing workflow (no new workflow), `append_event` duplicate `event_id` idempotent, duplicate `(aggregate_id, sequence)` → `ValueError: out-of-order`.
- **Triage:** Check `workflow_id` same for same `idempotency_key`, `events` sequence monotonic per aggregate (allows same sequence for different aggregates).
- **Response:** No duplicate execution — handler not re-run for same `idempotency_key`. If abuse via many distinct keys, rate-limit (deferred).

## Health & Observability

- **Structured logs:** `observability/logs.jsonl` (JSONL, one JSON per line) fields: `timestamp, event_type, correlation_id, causation_id, workflow_id, task_id, tenant_id, client_id, actor, actor_type, role_id, capability, tool, duration_ms, result_status, error_code, retry_count, model_status, payload`.
- **Health:** `observability/health.check_health()` checks `control_plane_store`, `event_replay`, `capability_registry`, `role_catalog`, `ollama` (optional), `filesystem` (evidence/control_plane/security/observability/organization/contracts). `is_healthy` overall (ollama optional).

## Contacts & Escalation

- **SAMI** (executive) and `compliance_quality_gm` are escalation owners per `organization/role-catalog.yaml:escalation_owner`.
- For C3, all `dead_letter` review queue is operator console + `control_plane` store; no external on-call yet.

## Residual

See `docs/C3-threat-model.md` residual risks — C3 is local-first, tamper-evident, not backup/ACL-proven.
