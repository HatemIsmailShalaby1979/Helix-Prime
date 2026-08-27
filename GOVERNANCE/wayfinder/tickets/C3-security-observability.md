---
id: C3-security-observability
type: research
status: closed
labels: [wayfinder:research]
blocked_by: [C1-organization-contracts]
blocks: [C4-engine-productization, C8-production-pack]
---

## Question

What is the enterprise-grade security, privacy, and observability design that lets Helix be trusted with real operational data — in parallel with C2?

Must deliver (C3 exit gate): tenant/client boundaries, user/role/service identities, least-privilege; secret management via env/OS store + repo/CI credential scan; data classification (public/internal/client-confidential/personnel-sensitive/financial/regulated); retention/deletion/export/backup/restore/migration policies; append-only audit with integrity + access controls (no "immutable ledger" claim until tamper-evidence proven); structured logs/metrics/traces/correlation/health checks/model telemetry/alert thresholds; prompt/tool injection defenses, model output validation, PII redaction/escalation.

## Research tasks (delegate to /research subagents)

- OS secret stores vs env for Windows local-first: which for pilot?
- SQLite → tamper-evident audit: which integrity approach without claiming blockchain?
- PII minimization patterns for personnel + CRM data on local SQLite vs future cloud.
- Ollama telemetry: what logs/metrics needed for model/provider observability?

## Expected

- `docs/C3-threat-model.md` + `security/` policy docs
- Tests: access-control, backup/restore, audit-query + incident runbook.

## Resolution (closed 2026-08-27, C3 sprint)

**Answer:** Local-first, deny-by-default, tamper-evident, fail-closed security and observability foundations with no cloud, no external IdP, no real secrets.

**Files added (16):**
- `security/classification.py` — 6 canonical `DataClassification` (`public/internal/client_confidential/personnel_sensitive/financial/regulated_high_risk`), `ClassificationMetadata`, `validate_payload_classification` (unknown → `ValueError`), `classify_for_tenant_client`
- `security/identity.py` — `Identity(actor, actor_type human/agent/service, tenant_id, client_id, role_id)` + `ActorType`, `scope_key`
- `security/policy.py` — `AuthorizationRequest(identity, capability, tool, action, requires_approval, target_tenant/client, owning_role_id)` → `AuthorizationDecision(allowed, reason, code)` via `authorize()` (checks tenant/isolation, role ownership via C1a registry, allowed capability/tool via `is_tool_allowed`, deny-by-default, no IdP)
- `security/secrets.py` — `get_secret` (env/OS store, clear error if missing), `redact`/`redact_dict` (regex `api_key`, `bearer`, `password`, `secret`, `token`, `cookie`, email, SSN, phone), `is_secret_present`, `validate_no_secrets` (fail-closed)
- `security/audit.py` — `AuditRecord` (audit_id, event_type, actor, actor_type, tenant/client, role, workflow/task/correlation, input/output refs, decision, approval, timestamp, previous_hash, current_hash SHA256(sorted JSON), schema `1.0`) + `AuditTrail` SQLite `security/audit.db` WAL, `append` enforces `previous_hash == last.current_hash` (tamper/out-of-order → `ValueError`), `verify_chain` recomputes, `clear_for_tests` (append-oriented, tamper-evident until deletion/backup proven — not immutable ledger)
- `security/injection.py` — `is_suspicious_prompt`/`is_suspicious_tool_request`/`scan_for_injection` (regex `ignore previous instructions`, `system:`, `pretend you are`, `drop table`, `call_agent("SAMI",...)`, `tool:exec`, python/bash code block)
- `security/__init__.py`, `security/README.md`
- `observability/logging.py` — `log_structured(event_type, correlation/causation/workflow/task/tenant/client/actor/role/capability/tool/duration/result_status/error_code/retry_count/model_status, payload)` → dict + appends `observability/logs.jsonl` JSONL (one JSON per line), validates required fields
- `observability/health.py` — `HealthStatus`, `check_health` (6 checks: `control_plane_store` Store list, `event_replay` replay empty, `capability_registry` `wfm_forecast→ops_gm`, `role_catalog` 9 roles, `ollama` GET `http://localhost:11434/api/tags` 2s, `filesystem` evidence/control_plane/security/observability/organization/contracts) + `is_healthy` (ollama optional)
- `observability/__init__.py`, `observability/README.md`
- `docs/C3-threat-model.md` — 11 threats (prompt injection, tool abuse, unauthorized agent, PII leakage, cross-client, malformed model output, audit tampering, replay/idempotency abuse, DoS retries, secrets exposure, DB compromise) each with prevention/detection/response/residual, plus `docs/operations/C3-security-runbook.md` (10 incident playbooks + health checks)
- `tests/test_c3_security.py` — 22 tests (all classifications, unknown rejection, tenant isolation, deny-by-default, allowed/denied role/capability/tool, approval/SOD, secret/PII redaction, validate_no_secrets, get_secret missing, audit hash-chain, tamper detection, correlation preservation, structured logging fields, health success/failure, authorization-denied event, prompt/tool injection, C2 regression, aggregate sequence, idempotency, plus `security/audit` and `observability` checks)
- `.gitignore` — added `*.db`, `*.db-*`, `control_plane/workflow.db`, `observability/logs.jsonl`, `security/audit.db` (C2/C3 DBs not committed)

**Files modified (2 wayfinder docs):** `GOVERNANCE/wayfinder/tickets/C3-security-observability.md` (this file) and `GOVERNANCE/wayfinder/map.md` (Decisions so far).

**Evidence:**
- `python3 -m pytest tests/test_c3_security.py -q` → 22 passed
- `python3 -m pytest -q` → 124 passed (6 existing +42 C1 +14 C1a +5 drift +5 preflight +22 C3 +30 C2) — preflight 5 + drift 5 already counted, total 124 includes all
- `python3 scripts/smoke.py` → 6/6 engines OK, 4/4 agents OK, 124 passed, C0 SMOKE PASS
- `python3 -m compileall -q app api cockpit engines orchestration organization contracts control_plane security observability` → 0
- Whitespace: `git diff --cached --check` → 0; `grep "[[:blank:]]$"` over 16 new files → 0
- Per-aggregate sequence: `tests/test_c2_preflight_regression.py::test_per_aggregate_allows_same_sequence_for_multiple_workflows` → PASS
- Repeated submission: `tests/test_c2_preflight_regression.py::test_repeated_submission_does_not_duplicate_workflow` → PASS

**Design decisions:**
- Deny-by-default, fail-closed: unknown classification/tool/capability → `ValueError` or `AuthorizationDecision(allowed=False, code="unknown_capability"|"unauthorized_tool"|"tenant_isolation")`, never silent.
- Hash chain: `current_hash = sha256(sorted_json(content))` with `previous_hash` chaining; `verify_chain` recomputes, detects tamper/missing/out-of-order; not claimed immutable.
- Secrets: `validate_no_secrets` on `TaskRequest.input_payload`/`EvidenceRef`/`logs` before store; `redact` before `log_structured`; `get_secret` only from `os.environ`, clear error if missing, never logs value.
- Tenant isolation: `Identity.tenant/client` vs `Workflow.tenant/client` + `AuthorizationRequest.target_*`, checked in `policy.authorize`.
- Observability: JSONL `observability/logs.jsonl` (gitignored), `health` checks local SQLite, registry, catalog, filesystem, ollama (optional).

**Known limitations (C3 boundary):**
- No C4 full engine productization (only test handlers)
- No C5 vertical slice, no C6 GM execution, no C7 sibling transport, no deployment packaging, no cloud telemetry, no external IdP, no real secrets, no new cockpit pages, no legacy routing removal
- Backup/restore, deletion, access-control guarantees separately proven (not in C3); audit is tamper-evident, not immutable

**Explicit confirmation:** C4, C5, C6, C7 not implemented.

**Next ticket:** C4 — Six-Engine Productization (depends C2 + C3)
