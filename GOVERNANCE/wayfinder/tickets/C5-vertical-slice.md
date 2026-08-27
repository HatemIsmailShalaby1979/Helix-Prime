---
id: C5-vertical-slice
type: prototype
status: in_progress
labels: [wayfinder:prototype]
blocked_by: [C4-engine-productization]
blocks: []
---

## Question (C5 milestone — Codex controlled-pilot evidence)

Can Helix Prime demonstrate the first governed contact-centre vertical slice end-to-end — interval/contact ingestion → WFM → RTA → OPS recommendation → Compliance approval/denial → HR/L&D action recommendation → CX impact → CRM impact → SAMI summary — with:

- actual C4 adapter output (`EngineResult` with real `metrics`, `is_sample=True` clearly labeled, not fabricated);
- typed contracts (`TaskRequest`/`TaskResult`/`Approval`/`EvidenceRef`/`AgentError` per `SCHEMA_VERSION=1.0`);
- durable C2 workflow (`Workflow` 11-state, `Event` sequence, `Store` SQLite WAL);
- C3 authorization (`security/policy.authorize` deny-by-default, `security/identity.Identity` with tenant/client isolation), audit (`security/audit.AuditRecord` hash chain, `security/audit.db`), secrets (`security/secrets.validate_no_secrets`, `redact`), injection (`security/injection.is_suspicious_prompt`);
- approval gate (`contracts/task.Approval` with `compliance_quality_gm` review, self-approval/SOD enforced);
- structured log (`observability/logging.log_structured` JSONL `observability/logs.jsonl`) with `correlation_id`, `causation_id`, `workflow_id`, `actor`, `capability`, `tool`, `duration_ms`;
- synthetic fixtures (`tests/fixtures/c5/fixtures.py` clearly `is_sample=True` per fixture);
- replayable evidence (`evidence/runs/` timeline + replay script);
- failure injection safe (missing data → `dead_letter`, timeout → `timeout`, denial → `approval_denied`);
- no production claim (`C1_CANONICAL` label, `C1A_MIRROR`, `C2_CANONICAL` still not production-ready, only `controlled_pilot`.

Status: C5 design and fixtures done; controller (`control_plane/vertical_slice/__init__.py`), evidence writer (`VerticalSliceEvidence.write_evidence`), synthetic fixtures, 30+ TDD tests scaffolded, C3 integration wired (`_audit`/_log/_run_engine_step/_submit_compliance`), missing only final `tests/test_c5_vertical_slice.py` execution pass and verification of evidence artifacts.

## Prototype expected (updated 2026-08-27, C5 sprint)

- `control_plane/vertical_slice/__init__.py` (VerticalSliceController, VerticalSliceRequest, VerticalSliceEvidence, 9 step sequence)
- `tests/fixtures/c5/fixtures.py` (synthetic/sample inputs clearly labeled `is_sample=True`)
- `tests/test_c5_vertical_slice.py` (26 focused tests: complete successful, ordering, adapter invocations, IDs, events, audit, logs, calculated/recommendation, approval granted/denied, tenant isolation, idempotency/restart/replay, failure injection for missing/invalid/dependency/timeout/unauthorized/denial, cockpit timeline, C0-C4 regression)
- Evidence artifacts: `evidence/runs/<vertical-slice-<id>>/timeline.jsonl`, `approvals.json`, `metrics.json`, `replay.py`
- `docs/C5-vertical-slice.md` or module docstring (add after final verification): complete workflow design, role/capability mapping per step, approval boundary (`STEP_COMPLIANCE` requires `Approval`), C3 integration points (`_audit` `_log` per step, `security/policy.authorize` on engine submit, `security/classification.validate_payload_classification`, `security/secrets.validate_no_secrets`, `security/injection.is_suspicious_prompt`), synthetic fixture labeling, limitation (no production claim), and C6/C7 pending.
- `GOVERNANCE/wayfinder/map.md` updated: C5 added to Decisions so far, frontier → C6.
