# Helix Prime Codex C8 — Incident Response Guide

Status: **Production Candidate / Controlled Pilot** (NOT production)

This guide provides runbooks for the failure modes covered by the C8
`failure_recovery` gate. All procedures are local-first and reversible.

## Severity definitions

- **SEV-3 (Info)**: cosmetic; no user impact.
- **SEV-2 (Degraded)**: a component unavailable; pilot continues with the rest.
- **SEV-1 (Critical)**: control-plane, audit, or persistence unavailable.

## Incident runbooks

### 1. Control-plane store unavailable / corrupted DB
Symptom: `Store` open/query raises; `health_check.py` reports
`control_plane_store` not ready.
Action:
1. Stop writers.
2. Restore from the latest backup (see `backup-restore-guide.md`).
3. Verify `scripts/health_check.py` reports ready.
4. Confirm idempotency prevents duplicate re-application on resume.

### 2. Audit chain tamper detection
Symptom: `security.audit.verify_chain` returns false.
Action:
1. Stop processing immediately (SEV-1).
2. Preserve the audit DB; do not mutate.
3. Compare against the latest backup's audit chain.
4. Investigate and, if confirmed tampering, escalate and do not continue.

### 3. Engine timeout / dead-letter
Symptom: a workflow dead-letters after retries.
Action:
1. Inspect the typed `ENGINE_TIMEOUT` / error envelope in the log.
2. Re-drive via idempotency-safe resubmission.
3. If persistent, treat the engine as degraded (SEV-2) and reroute.

### 4. Sibling unavailable
Symptom: empty receive / `sibling_unavailable` typed error.
Action: local-only release has no network sibling transport; expected.
No irreversible change occurs; the event stays acknowledged or dead-lettered.

### 5. Corrupted event (out-of-order / duplicate)
Symptom: `Store.append_event` raises ValueError on sequence.
Action: the event is rejected deterministically; ignore and resubmit with a
correct sequence via the workflow service.

## Escalation

- Contact the operator on-call; record all actions in the audit trail.
- Do not perform any irreversible, financial, personnel, compliance, ICT, or
  external-communication action without explicit approval.
