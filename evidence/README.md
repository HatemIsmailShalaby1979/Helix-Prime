# Evidence Directory — Helix Prime Codex

**Convention:** `evidence/<YYYY-MM-DD>-<slug>/`

All verification runs produce machine-readable evidence here. No generated report may claim `verified`/`pilot`/`production-ready` without evidence in this directory.

## Layout

```
evidence/
├── README.md                    # this file
├── baseline/                    # C0 truth-lock snapshots
│   ├── capability-matrix.json   # canonical capability matrix
│   ├── smoketest.log            # python -m pytest + cockpit probe + engine imports
│   └── git-hygiene.log          # git status / hygiene diff
├── runs/<run-id>/               # per-run evidence (workflow, engine, agent)
│   ├── input.json
│   ├── output.json
│   ├── timeline.jsonl
│   └── approvals.json
└── releases/<label>/            # release evidence packs (see GOVERNANCE/RELEASE_LABELS.md)
```

## One test command (canonical, cross-platform)

```bash
python -m pytest -q
# or
pytest -q
```

`pytest.ini` defines `testpaths = tests` and `pythonpath = .`. No hardcoded Windows paths.

## One smoke command (no Ollama required)

```bash
python -m pytest -q -k "not smoke"
python -c "from orchestration.orchestrator import Orchestrator; o=Orchestrator(); print(o.status())"
python -c "from cockpit.memory.cognitive_log import query_interactions; print(query_interactions(limit=1))"
# Optional: launch cockpit
python launch.py --port 8501   # then http://127.0.0.1:8501
```

## Rules (Codex Principle: Evidence before status)

- `implemented` = code exists on branch, imports.
- `verified` = evidenced by a run in `evidence/baseline/` or `evidence/runs/` with input/output + environment.
- `pilot` / `production-ready` require release evidence pack per `GOVERNANCE/RELEASE_LABELS.md`.

## Retention

- Local evidence is git-ignored (`evidence/` in `.gitignore`) except `evidence/README.md` and checked-in baseline snapshots if signed.
- Backup/restore policy deferred to C3; for now manual copy + `git tag`.

## Baseline run

Run `python scripts/smoke.py` (C0) to populate `evidence/baseline/`. Commit only the signed `capability-matrix.json`; keep logs ignored.
