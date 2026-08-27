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

## Not yet specified

- Exact shape of C3 secret management (OS keyring vs env vs vault) — pending C1 contract + ICT GM approval matrix.
- Data-classification schema and retention windows for personnel-sensitive / financial / regulated data.
- Sibling integration transport: file/event exchange locally first vs network services; competency event schema details (`CompetencyGapDetected` etc.) need contract-test draft.
- Observability stack: local-first structured logs vs OpenTelemetry; alert thresholds per KPI.
- Deployment profiles (local single-node, private-network pilot, optional cloud) — build/migration/rollback evidence needed at C8.
- Marketing GM attribution model and approved-content boundary (CRM feedback loop).

## Out of scope

- Branding / dashboards beyond one verified contact-centre slice (per sprint backlog note).
- Patent / blockchain / quantum claims (explicitly excluded in ROADMAP).
- Full cloud hosting or client deployments before C8 gate.
- Rewriting 2-commit public git history with `push --force` without owner approval (see `GIT_HISTORY_RECONCILIATION.md`).

## Frontier (open tickets — take topmost unblocked)

See `tickets/` — order below is charter order, blocking wired second-pass:

1. C1a — Capability-Based Discovery (depends C1) ← **next frontier**
2. C2 — Control Plane & Workflow Runtime (depends C1a)
3. C3 — Security/Privacy & Observability (parallel with C2, depends C1)
4. C4 — Six-Engine Productization (depends C2 + C3 seam)
5. C5 — Contact-Centre Vertical Slice Proof (depends C4)
6. C6 — GM Expansion (Compliance,Fraud,HR,L&D,Sales,Marketing,ICT) (depends C5)
7. C7 — Sibling-Project Integration (depends C1; implement after C5 contracts)
8. C8 — Production Candidate & Controlled Pilot Pack (depends C5)
