# Helix Prime — C3 Threat Model (Local-First)

**Status:** C3 implementation — threat model for security governance and observability foundations.
**Scope:** Control plane, capability registry, audit, secrets, prompt/tool, tenant isolation, DB.
**Not production-ready:** Audit is tamper-evident, not immutable ledger; backup/restore, deletion, access-control guarantees separately proven.

## Assets & Trust Boundary

- **Assets:** Workflow/task state, correlation/causation IDs, tenant/client data (personnel_sensitive, financial, regulated_high_risk), audit trail, role catalog, capability registry, Ollama model outputs.
- **Trust boundary:** Local process + SQLite files (`control_plane/workflow.db`, `security/audit.db`, `observability/logs.jsonl`) on operator laptop. No cloud, no external IdP in C3. Actor identities are local `Identity(actor, actor_type human/agent/service, tenant, client, role)`.

## Threats — Prevention / Detection / Response / Residual Risk

### 1. Prompt Injection (LLM `call_agent("...")` invented)

- **Prevention:** `security/injection.py:is_suspicious_prompt` (regex `ignore previous instructions`, `system:`, `pretend you are`, `drop table`, `call_agent("SAMI",...)` as if system), `contracts/adapter.parse_legacy_calls` still validated via `validate_request_against_catalog` (capability must be owned, peer allowed). Structured `TaskRequest` is primary; model text is compatibility only.
- **Detection:** `scan_for_injection` on every `input_payload` before `Engine.submit`; `security/audit.AuditRecord(event_type="suspicious_prompt")` + `observability.logging.log_structured(event_type="suspicious_prompt", error_code="injection")`.
- **Response:** Fail-closed to `dead_letter` (`policy_denied`), record audit, no execution, surface in `control_plane` dead-letter queue.
- **Residual:** Regex is heuristic, not LLM-based; bypass via obfuscation possible — mitigate by allow-listing capabilities/tools, not block-listing prompts.

### 2. Tool Abuse (unauthorized `tool` in payload)

- **Prevention:** `security/policy.authorize` checks `is_tool_allowed(role, tool)` via `role-catalog.yaml:allowed_tools`; `control_plane/engine.submit` checks `tool` in `input_payload` → `unauthorized` → `dead_letter`.
- **Detection:** `AuthorizationDecision(code="unauthorized_tool")` + audit `authorization_denied` + structured log `error_code="unauthorized_tool"`.
- **Response:** Deny, `dead_letter`, `AgentError(code="unauthorized")`, audit `workflow_dead_letter`.
- **Residual:** New tools added to catalog must be explicitly allow-listed; default deny may block legitimate new tool until catalog updated.

### 3. Unauthorized Agent Calls (peer violation)

- **Prevention:** `policy.authorize` checks `allowed_peer_calls` (e.g., `marketing_gm`→`ops_gm` denied) and `get_agent_for_capability` deterministic owner check (`sales_gm` cannot claim `wfm_forecast`). `Engine.submit` validates `owner == request.owning_role_id` else `conflict`.
- **Detection:** `code="unauthorized_role"` + audit.
- **Response:** `dead_letter`, `conflict`, review queue.
- **Residual:** Catalog must be kept accurate; privilege creep if `allowed_peer_calls` overly broad.

### 4. PII Leakage (email, SSN, phone, personnel_sensitive)

- **Prevention:** `security/secrets.redact` / `redact_dict` (email → `[REDACTED_EMAIL]`, SSN `\d{3}-\d{2}-\d{4}` → `[REDACTED_SSN]`, phone → `[REDACTED_PHONE]`), `validate_no_secrets` on `TaskRequest.input_payload`, `EvidenceRef`, logs; `DataClassification.personnel_sensitive` requires explicit handling.
- **Detection:** `is_secret_present` + `validate_no_secrets` raises `ValueError` before store; audit `secret_redaction` event.
- **Response:** Fail-closed or redacted copy stored; original not logged. `C3` redaction is regex-based, not NER.
- **Residual:** Regex misses novel PII formats; residual risk mitigated by `client_confidential` default for workflows with tenant/client.

### 5. Cross-Client Data Access (tenant/client isolation)

- **Prevention:** `Identity.tenant_id/client_id` + `AuthorizationRequest.target_tenant/client` → `policy.authorize` checks `tenant_isolation` (deny if `identity.tenant != target.tenant`), `Workflow.correlation` preserves `tenant/client`, `Store` does not cross-aggregate.
- **Detection:** `code="tenant_isolation"` + audit `tenant_boundary_violation`.
- **Response:** Deny, `dead_letter`, audit.
- **Residual:** Local SQLite has no row-level ACL; isolation is application-level, not DB-level.

### 6. Malicious or Malformed Model Output (handler returns non-dict, injection in output)

- **Prevention:** `Engine.execute` validates `handler` returns `dict` else `ValueError` → `failed`→`dead_letter`; `validate_payload_classification` checks `output_payload` classification.
- **Detection:** `handler_failed` event, `AgentError(code="engine_error")`, structured log `error_code`.
- **Response:** Bounded retry (max 3) then `dead_letter`, no silent retry loop.
- **Residual:** Model output that is dict but semantically malicious (e.g., wrong numbers) not detected — requires C4 engine validation.

### 7. Audit Tampering (hash chain)

- **Prevention:** `security/audit.AuditTrail` SHA-256 chain `current_hash = sha256(sorted_json(content))`, `previous_hash` must equal previous `current_hash`, `BEGIN IMMEDIATE` transaction, `audit_id`/`current_hash` unique.
- **Detection:** `verify_chain()` recomputes hashes and chain order; returns `(False, "tamper detected")` if `previous_hash` mismatch or `current_hash` wrong, or missing/out-of-order.
- **Response:** `audit_verification_failure` event, alert, do not auto-repair.
- **Residual:** Append-only until deletion; `DELETE` or file truncation not prevented by DB—mitigate via filesystem permissions + backup verification (separately proven, not claimed immutable).

### 8. Replay / Idempotency Abuse (duplicate `idempotency_key` or `event_id`)

- **Prevention:** `Store.create_workflow` `idempotency_key UNIQUE` + `BEGIN IMMEDIATE` check-then-insert → idempotent return existing; `Store.append_event` `event_id` unique + per-aggregate `sequence` monotonic (`UNIQUE(aggregate_id, sequence)` + `MAX(sequence)` check); `Engine.submit` checks `get_workflow_by_idempotency` before create.
- **Detection:** Duplicate `idempotency_key` → return existing (no duplicate workflow); duplicate `event_id` → idempotent return; duplicate `(aggregate, sequence)` → `ValueError: out-of-order`.
- **Response:** No duplicate execution for same `idempotency_key` (handler not re-run, `test_no_duplicate_execution_for_same_idempotency`).
- **Residual:** Concurrent threads with same key at same ms will have one win, other gets existing via `IntegrityError` handling — safe but not distributed.

### 9. Denial of Service through Retries (flaky handler)

- **Prevention:** `Engine.execute` bounded `max_retries=3` (configurable per workflow), `retry_count` persisted, `handler_failed` + `retry_scheduled` events per attempt, no `sleep` loop, no unbounded.
- **Detection:** `retry_count` in workflow, structured log `retry_count`, audit `repeated_handler_failure`.
- **Response:** After `max_retries+1` attempts → `failed` → `dead_letter` (`engine_error`), not infinite.
- **Residual:** Local resource exhaustion via many distinct workflows still possible — rate-limiting deferred to C3/C4.

### 10. Secrets Exposure (source, payload, logs)

- **Prevention:** `security/secrets.validate_no_secrets` on `TaskRequest.input_payload`, `EvidenceRef`, logs; `redact_dict` before `log_structured`; `get_secret` only from `os.environ`, clear error if missing, never logs value; `.gitignore` has `*.db`, `*.sqlite`, `.env`, `*.db-wal` etc.
- **Detection:** `is_secret_present` heuristic (`api_key`, `password`, `bearer`, `token`, 32+ hex) + `secret_redaction` audit/log; `git diff --check` + `validate_no_secrets` in tests.
- **Response:** Fail-closed (`ValueError: appears to contain secret`) or redacted copy.
- **Residual:** Heuristic may miss novel secret format; residual mitigated by deny-by-default and audit.

### 11. Local Database Compromise (file deletion, SQLite tampering)

- **Prevention:** WAL mode, `PRAGMA foreign_keys`, `BEGIN IMMEDIATE` for atomic check-then-insert, filesystem permissions (operator laptop), `.gitignore` prevents commit of `*.db`.
- **Detection:** `health.check_control_plane_store` (`SELECT count(*) FROM events`), `check_event_replay`, `audit.verify_chain`, `is_healthy` overall.
- **Response:** `health` `ok=False` → operator runbook, restore from backup (backup verification separately proven).
- **Residual:** File deletion not recoverable without backup; tamper-evidence detects but does not prevent — document as tamper-evident, not immutable.

## Residual Risk Summary

C3 provides **tamper-evident, append-oriented, deny-by-default, local-first** foundations. Not yet: backup/restore verification, row-level DB ACL, NER PII, LLM-based injection detection, distributed idempotency, full observability metrics. These are C4/C5/C8.

## References

- `security/classification.py` (6 canonical), `security/policy.py` (deny-by-default), `security/secrets.py` (redaction), `security/audit.py` (hash chain), `security/injection.py`, `observability/logging.py`, `observability/health.py`, `control_plane/store.py` (WAL+UNIQUE+BEGIN IMMEDIATE).
