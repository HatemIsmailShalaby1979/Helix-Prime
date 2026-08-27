# Security — Helix Prime C3

Local-first, deny-by-default, fail-closed.

## Modules

- `classification.py` — 6 canonical `DataClassification` (`public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk`), `ClassificationMetadata`, `validate_payload_classification` (unknown → `ValueError`). Used for task payloads, evidence, logs, workflow outputs.
- `identity.py` — `Identity(actor, actor_type human/agent/service, tenant_id, client_id, role_id)` with `scope_key` for isolation.
- `policy.py` — `AuthorizationRequest(identity, capability, tool, action, requires_approval, target_tenant/client, owning_role_id)` → `AuthorizationDecision(allowed, reason, code)` via `authorize()`. Enforces tenant/client isolation, role ownership (via C1a registry), allowed capability/tool (`is_tool_allowed`), approval, SOD, deny-by-default. No external IdP.
- `secrets.py` — `get_secret(name)` (env/OS store, clear error if missing), `redact(text)`, `redact_dict`, `is_secret_present`, `validate_no_secrets` (fail-closed if `api_key`, `password`, `bearer` etc. in payload). Redacts `api_key, bearer, password, secret, token, cookie`, emails, SSN, phone.
- `audit.py` — `AuditRecord` (audit_id, event_type, actor, actor_type, tenant/client, role, workflow/task/correlation, input/output refs, decision, approval, timestamp, previous_hash, current_hash `sha256(sorted_json)`, schema `1.0`) + `AuditTrail` SQLite `security/audit.db` WAL, `append` enforces `previous_hash == last.current_hash` (out-of-order/tamper → `ValueError`), `verify_chain` recomputes hashes, `clear_for_tests`. **Append-oriented, tamper-evident until deletion/backup proven — not immutable ledger.**
- `injection.py` — `is_suspicious_prompt`, `is_suspicious_tool_request`, `scan_for_injection` (regex for `ignore previous instructions`, `system:`, `pretend you are`, `drop table`, etc.) → route to review queue.

## Canonical DBs

- `security/audit.db` (gitignored via `*.db`), `control_plane/workflow.db` (gitignored). Both WAL, `BEGIN IMMEDIATE` for safe check-then-insert.

## Usage

```python
from security.classification import DataClassification, validate_payload_classification
from security.identity import Identity, ActorType
from security.policy import AuthorizationRequest, authorize
from security.secrets import redact, validate_no_secrets, get_secret
from security.audit import AuditRecord, AuditTrail

validate_payload_classification({"data_classification": "financial"}, "financial")
identity = Identity(actor="sami", actor_type=ActorType.AGENT, tenant_id="t", client_id="c", role_id="ops_gm")
decision = authorize(AuthorizationRequest(identity=identity, capability="wfm_forecast", tool="wfm_engine"))
assert decision.allowed  # or fail-closed

# Audit
trail = AuditTrail(db_path="security/audit.db")
rec = AuditRecord.new(event_type="workflow_created", actor="sami", actor_type="agent", decision="allowed", correlation_id="corr1")
trail.append(rec)
assert trail.verify_chain()[0] is True
```
