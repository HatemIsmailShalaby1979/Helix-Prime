---
id: C0-truth-lock
type: task
status: closed
labels: [wayfinder:task]
blocks: [C1-organization-contracts]
---

## Question

Can we reconcile README/ROADMAP/MASTER_STORY/GOVERNANCE/CHANGE_LOG and the source tree into one machine-readable capability matrix, fix repository hygiene (tracked .venv), and establish one test + one smoke command with evidence dir convention?

## Resolution

Closed 2026-08-27. Delivered: `GOVERNANCE/capability-matrix.json` (4 agents,6 engines,6 cockpit pages,keyword routing,2→26630 .venv hygiene via `git rm --cached .venv` + `.gitignore` .venv/, `pytest.ini` testpaths `AI OPS Engineering/*` → `tests`, `evidence/README.md` convention, `scripts/smoke.py` reports 6/6 engines OK + 4/4 agents import OK + orchestrator routing + 6/6 pytest, `GOVERNANCE/RELEASE_LABELS.md` alpha→production, `GOVERNANCE/GIT_HISTORY_RECONCILIATION.md` 2-commit vs 7-session, `run_tests.ps1` cross-platform. Evidence: `python3 -m pytest -q` 6 passed, `python3 scripts/smoke.py` C0 SMOKE PASS.

## Assets

- GOVERNANCE/capability-matrix.json
- GOVERNANCE/RELEASE_LABELS.md
- GOVERNANCE/GIT_HISTORY_RECONCILIATION.md
- evidence/README.md
- scripts/smoke.py
- .gitignore (21:.venv/)
- pytest.ini
- run_tests.ps1
