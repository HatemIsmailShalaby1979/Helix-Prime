# Wayfinder Map — Helix Prime Codex Upgrade

## Destination

Helix Prime Codex: a human-supervised, enterprise-grade AI organization (8 GMs + SAMI CEO + 6 engines + workflow control plane) proven by one complete contact-centre vertical slice (WFM → RTA → OPS → Compliance → HR/L&D → CRM/CX → SAMI summary) that runs with durable workflows, typed contracts, approvals, audit evidence, tenant isolation, and failure-injection verification. Codex name claimed after C0–C5; production-ready only after C8 evidence pack.

## Notes

- Domain: contact-centre & business operations AI org; local-first (Ollama+SQLite) → replaceable storage.
- Every session: read `docs/HELIX_CODEX_UPGRADE_PLAN.md`, `GOVERNANCE/capability-matrix.json`, `GOVERNANCE/RELEASE_LABELS.md`.
- Skills to use: `domain-modeling` + `grilling` for GM boundaries, `tdd` for contracts, `diagnosing-bugs` for workflow runtime, `research` for sibling integration.
- Non-negotiables: Expand not erase; human approval for irreversible actions; every action typed/attributable; fail-closed; one source of truth; evidence before status.
- Tracker: local-markdown (`GOVERNANCE/wayfinder/tickets/*.md` linked from this map). Each ticket filename is its id; priority = label; blocking wired via `Blocks:`/`BlockedBy:` front-matter. Frontier = open tickets with no open blockers.
- Label `wayfinder:map` on this file; tickets carry `wayfinder:<type>`.

## Decisions so far

- [C0 Truth Lock — Capability Matrix + Hygiene + Smoke](tickets/C0-truth-lock.md) — Closed 2026-08-27: `GOVERNANCE/capability-matrix.json` (4 agents,6 engines,6 cockpit pages,keyword routing,2→26630 .venv hygiene fix via `git rm --cached`, `pytest.ini` → `tests`, `evidence/README.md` convention, `scripts/smoke.py` 6/6 engines + 4/4 agents + 6/6 pytest green, `GOVERNANCE/RELEASE_LABELS.md` + `GIT_HISTORY_RECONCILIATION.md`; test cmd `python3 -m pytest -q`, smoke `python3 scripts/smoke.py`).
- [C1 Organization Model & Typed Contracts](tickets/C1-organization-contracts.md) — Closed 2026-08-27 (corrected): 9 new files (`organization/` 4 + `contracts/` 4 + `tests/test_c1_contracts.py` 1; `GOVERNANCE/wayfinder` 2 modified) `organization/role-catalog.yaml` (9 roles: sami + 8 GMs, PHILI→hr_personnel_gm/WILI→ld_gm/SUBY→ops_gm/SAMI→sami, catalog_only for new GMs, SOD compliance can_review OPS/Sales/HR/Fraud) + `organization/role_catalog.py` validator + `contracts/task.py` 8 models `SCHEMA_VERSION = "1.0"` (canonical, not 12, consistent across all) + `contracts/adapter.py` (parse_legacy_calls + to_task_request + validate_request_against_catalog, fail-closed) + `tests/test_c1_contracts.py` 42 tests (38 + 4 schema_version `1.0` consistency); 48 total tests green, smoke 6/6 engines 4/4 agents unchanged, compileall clean.
- [C1a Capability-Based Discovery](tickets/C1a-capability-discovery.md) — Closed 2026-08-27: `organization/capability-registry.yaml` + `organization/capabilities.json` + `contracts/capabilities.yaml` (16 engine caps) + `organization/capability_registry.py` (7 helpers, deterministic, fail-closed unknown/ambiguous) + `orchestration/registry.py` + `orchestration/discovery.py` + `tests/test_c1a_capability_discovery.py` 14 tests (agent/engine discovery, role ownership, allowed/denied tools, unknown, ambiguous, legacy compatibility, deterministic routing, no regression); 62 total tests green, smoke 6/6 engines 4/4 agents unchanged, compileall clean, legacy `orchestration/orchestrator.py:211` preserved.
- [C2 Control Plane and Workflow Runtime](tickets/C2-control-plane.md) — Closed 2026-08-27: `control_plane/` (workflow.py 11-state machine, events.py envelope, store.py SQLite WAL, engine.py deterministic handler+retry/timeout/approval, README) 6 new files + `tests/test_c2_control_plane.py` 30 tests (valid/invalid transitions, event replay, sequence, idempotent duplicate, duplicate event, deadline, bounded retry, cancellation, dead_letter, approval required/granted/denied, SOD self/same-role, unknown capability, unauthorized tool, handler success/failure, restart persistence, tenant/client, correlation/causation, drift, no silent retry, no duplicate execution) + `tests/test_c2_preflight_regression.py` 5 tests (per-aggregate, duplicate, idempotent, DB ignored, restart); 102 total tests green, smoke 6/6 engines 4/4 agents, compileall clean, `control_plane/workflow.db` durable (Harden C2 persistence invariants).
- [C3 Security, Data Governance and Observability](tickets/C3-security-observability.md) — Closed 2026-08-27: `security/` (classification 6, identity, policy deny-by-default, secrets redact, audit hash-chain, injection) + `observability/` (logging JSONL, health 6 checks) + `docs/C3-threat-model.md` (11 threats) + `docs/operations/C3-security-runbook.md` (10 playbooks) + `tests/test_c3_security.py` 22 tests (all classifications, unknown, tenant isolation, deny-by-default, allowed/denied, SOD, secret/PII redaction, audit chain/tamper/correlation, logging, health, auth-denied event, injection, C2 regressions); 124 total tests green, smoke 6/6 engines 4/4 agents, compileall clean, `.gitignore` `*.db`/`logs.jsonl`.

## Not yet specified

- Sibling integration transport: file/event exchange locally first vs network services; competency event schema details (`CompetencyGapDetected` etc.) need contract-test draft.
- Deployment profiles (local single-node, private-network pilot, optional cloud) — build/migration/rollback evidence needed at C8.
- Marketing GM attribution model and approved-content boundary (CRM feedback loop).
- C4 engine productization details per engine (typed I/O, validation, provenance) — pending C3 classification/policy integration.

## Out of scope

- Branding / dashboards beyond one verified contact-centre slice (per sprint backlog note).
- Patent / blockchain / quantum claims (explicitly excluded in ROADMAP).
- Full cloud hosting or client deployments before C8 gate.
- Rewriting 2-commit public git history with `push --force` without owner approval (see `GIT_HISTORY_RECONCILIATION.md`).

## Frontier (open tickets — take topmost unblocked)

See `tickets/` — order below is charter order, blocking wired second-pass:

1. C4 — Six-Engine Productization (depends C2 + C3 seam) ← **next frontier**
2. C5 — Contact-Centre Vertical Slice Proof (depends C4)
3. C6 — GM Expansion (Compliance,Fraud,HR,L&D,Sales,Marketing,ICT) (depends C5)
4. C7 — Sibling-Project Integration (depends C1; implement after C5 contracts)
5. C8 — Production Candidate & Controlled Pilot Pack (depends C5)
